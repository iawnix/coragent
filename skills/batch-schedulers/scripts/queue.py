#!/usr/bin/env python3
"""PBS/Torque/Slurm command handler for coragent-external-job/1 (stdlib only)."""
from datetime import datetime
import fcntl
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

PROTOCOL = "coragent-external-job/1"


def command(name, *args, cwd=None):
    executable = os.environ.get("CORAGENT_" + name.upper(), name)
    return subprocess.run([executable, *map(str, args)], cwd=cwd, text=True,
                          capture_output=True, timeout=45)


def checked(result):
    if result.returncode:
        raise RuntimeError(result.stderr.strip()[:2000] or "scheduler command failed")
    return result.stdout


def save(path, value):
    with tempfile.NamedTemporaryFile("w", dir=path.parent, delete=False) as stream:
        temporary = Path(stream.name)
        try:
            json.dump(value, stream)
            stream.flush()
            os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)
    fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def pbs_records(scheduler, identity=None):
    args = ["-x", "-f", "-F", "json"] if scheduler == "pbs" else ["-x"]
    result = command("qstat", *args, *([identity] if identity else []))
    text = checked(result)
    if scheduler == "pbs":
        jobs = json.loads(text)["Jobs"]
        return [{**value, "id": key} for key, value in jobs.items()]
    root = ET.fromstring(text)
    return [{**{child.tag: child.text for child in job}, "id": job.findtext("Job_Id")}
            for job in root.findall("Job")]


def pbs_request(record):
    variables = record.get("Variable_List", {})
    if isinstance(variables, str):
        variables = dict(item.split("=", 1) for item in variables.split(",") if "=" in item)
    return variables.get("CORAGENT_REQUEST_ID")


def slurm_records(identity=None, *, since=None):
    live = command("squeue", "--noheader", "--format=%i|%k|%T|%R", *(["--jobs", identity] if identity else []))
    records = []
    if live.returncode == 0:
        for line in live.stdout.splitlines():
            fields = line.strip().split("|", 3)
            if len(fields) != 4:
                raise ValueError("invalid squeue response")
            records.append(dict(zip(("id", "request_id", "state", "reason"), fields)))
    if identity and any(record["id"] == identity for record in records):
        return records
    args = ["-X", "-n", "-P", "--format=JobIDRaw,Comment%128,State%64,ExitCode"]
    if identity:
        args += ["--jobs", identity]
    if since:
        args += ["--starttime", since]
    accounting = command("sacct", *args)
    # Recovery also searches history even when live tasks exist.
    if accounting.returncode:
        raise RuntimeError(accounting.stderr.strip()[:2000] or "Slurm accounting unavailable")
    for line in accounting.stdout.splitlines():
        fields = line.strip().split("|")
        if len(fields) < 4:
            raise ValueError("invalid sacct response")
        records.append(dict(zip(("id", "request_id", "state", "exit"), fields[:4])))
    return records


def recover(scheduler, request, journal):
    if journal.get("scheduler_id"):
        return journal["scheduler_id"]
    if scheduler == "slurm":
        records = slurm_records(since=journal.get("created_at"))
        matches = {r["id"] for r in records if r["request_id"] == request["request_id"]}
    else:
        matches = {r["id"] for r in pbs_records(scheduler) if pbs_request(r) == request["request_id"]}
    if len(matches) > 1:
        raise RuntimeError("multiple scheduler jobs match request_id; inspect scheduler records")
    return next(iter(matches), None)


def submit_arguments(scheduler, request):
    resources = request.get("resources", {})
    timeout = request.get("timeout_seconds")
    if resources.get("walltime"):
        h, m, s = map(int, resources["walltime"].split(":"))
        seconds = h * 3600 + m * 60 + s
        timeout = min(timeout, seconds) if timeout is not None else seconds
    directory = request["cwd"]
    if scheduler == "slurm":
        if "select" in resources:
            raise ValueError("Slurm resources use cpus, memory_mb and gpus")
        args = ["--parsable", "--no-requeue", "--comment=" + request["request_id"],
                "--job-name=" + request["job_id"], "--chdir=" + directory,
                "--output=" + directory + "/logs/scheduler.stdout", "--error=" + directory + "/logs/scheduler.stderr"]
        for field, flag in (("cpus", "cpus-per-task"), ("memory_mb", "mem"), ("gpus", "gpus")):
            if field in resources:
                args.append(f"--{flag}={resources[field]}")
        if request.get("queue"):
            args.append("--partition=" + request["queue"])
        if timeout is not None:
            args.append("--time=" + str(math.ceil(timeout / 60)))
        return "sbatch", args + [request["script"]]
    args = ["-N", "ca" + request["request_id"][-12:], "-v", "CORAGENT_REQUEST_ID=" + request["request_id"],
            "-m", "n", "-r", "n", "-o", directory + "/logs/scheduler.stdout", "-e", directory + "/logs/scheduler.stderr"]
    if request.get("queue"):
        args += ["-q", request["queue"]]
    if scheduler == "torque":
        if {"select", "gpus"} & resources.keys():
            raise ValueError("Torque handler supports cpus and memory_mb; configure site GPU syntax in this script")
        if "cpus" in resources:
            args += ["-l", "nodes=1:ppn=" + str(resources["cpus"])]
        if "memory_mb" in resources:
            args += ["-l", "mem=" + str(resources["memory_mb"]) + "mb"]
    else:
        if "select" in resources and {"cpus", "memory_mb", "gpus"} & resources.keys():
            raise ValueError("use select or individual resource fields")
        select = resources.get("select", "1")
        for field, name, suffix in (("cpus", "ncpus", ""), ("memory_mb", "mem", "mb"), ("gpus", "ngpus", "")):
            if field in resources:
                select += f":{name}={resources[field]}{suffix}"
        args += ["-l", "select=" + select]
    if timeout is not None:
        seconds = math.ceil(timeout)
        args += ["-l", f"walltime={seconds//3600:02}:{seconds//60%60:02}:{seconds%60:02}"]
    return "qsub", args + [request["script"]]


def status(scheduler, request, journal):
    identity = request["scheduler_id"]
    result = {"scheduler_id": identity, "state": "unknown", "execution_finished": False}
    if scheduler == "slurm":
        records = [r for r in slurm_records(identity, since=journal.get("created_at")) if r["id"] == identity]
        if len(records) != 1:
            return {**result, "error": "scheduler record unavailable or ambiguous"}
        record = records[0]
        if record["request_id"] != request["request_id"]:
            raise ValueError("Slurm request identity mismatch")
        native = record["state"].split()[0].rstrip("+")
        state = {"PENDING": "queued", "CONFIGURING": "submitted", "RUNNING": "running",
                 "COMPLETING": "running", "SUSPENDED": "held", "COMPLETED": "succeeded",
                 "FAILED": "failed", "OUT_OF_MEMORY": "failed", "NODE_FAIL": "failed",
                 "BOOT_FAIL": "failed", "DEADLINE": "timed_out", "TIMEOUT": "timed_out",
                 "CANCELLED": "cancelled", "PREEMPTED": "failed"}.get(native, "unknown")
        code = None
        if "exit" in record:
            exit_code, signal = map(int, record["exit"].split(":"))
            code = 128 + signal if signal else exit_code
        if state == "succeeded" and code != 0:
            state = "failed" if code is not None else "unknown"
    else:
        records = [r for r in pbs_records(scheduler, identity) if r["id"] == identity]
        if len(records) != 1:
            return {**result, "error": "scheduler record unavailable or ambiguous"}
        record = records[0]
        if pbs_request(record) != request["request_id"]:
            raise ValueError("PBS request identity mismatch")
        native = record.get("job_state")
        code = record.get("Exit_status", record.get("exit_status"))
        code = int(code) if code is not None else None
        state = {"Q": "queued", "W": "queued", "H": "held", "R": "running", "E": "running",
                 "T": "submitted", "S": "held", "B": "running"}.get(native, "unknown")
        if native in {"F", "C"}:
            state = "succeeded" if code == 0 else "cancelled" if journal.get("cancellation_requested") else "failed" if code is not None else "unknown"
    finished = state in {"succeeded", "failed", "cancelled", "timed_out"}
    if finished:
        marker = Path(request["cwd"]) / "status.state"
        if marker.is_file() and marker.read_text().strip() == "timed_out":
            state = "timed_out"
    return {**result, "state": state, "exit_code": code, "execution_finished": finished,
            "diagnostics": {"scheduler_state": native, "scheduler_record": record}}


def handle(scheduler, request):
    if request.get("schema_version") != PROTOCOL:
        raise ValueError("unsupported external Job protocol")
    action = request["action"]
    if action == "probe":
        names = ("sbatch", "squeue", "sacct", "scancel") if scheduler == "slurm" else ("qsub", "qstat", "qdel")
        missing = [name for name in names if not shutil.which(os.environ.get("CORAGENT_" + name.upper(), name))]
        return {"available": not missing, "error": ", ".join(missing) or None}
    if not re.fullmatch(r"coragent-[a-f0-9]{64}", request["request_id"]):
        raise ValueError("invalid request_id")
    folder = Path(request["cwd"]) / ".coragent"
    # Staging creates this private directory before the handler is invoked.
    path = folder / "batch-submission.json"
    with (folder / "batch-submission.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        journal = json.loads(path.read_text()) if path.exists() else {}
        if journal and (journal["request_id"] != request["request_id"] or journal["scheduler"] != scheduler):
            raise ValueError("submission journal identity mismatch")
        if action == "recover":
            identity = recover(scheduler, request, journal)
            return {"found": bool(identity), **({"scheduler_id": identity} if identity else {})}
        if action == "submit":
            if journal:
                identity = recover(scheduler, request, journal)
                if identity:
                    return {"scheduler_id": identity}
                raise RuntimeError("submission outcome unresolved; inspect scheduler history before creating another Job")
            name, args = submit_arguments(scheduler, request)
            journal = {"request_id": request["request_id"], "scheduler": scheduler,
                       "created_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S")}
            save(path, journal)
            output = checked(command(name, *args, cwd=request["cwd"])).strip()
            identity = output.split(";", 1)[0] if scheduler == "slurm" else output
            pattern = r"[1-9][0-9]*" if scheduler == "slurm" else r"[1-9][0-9]*(?:\.[A-Za-z0-9_.-]+)?"
            if not re.fullmatch(pattern, identity):
                raise ValueError("invalid submission response; recover by request_id")
            save(path, {**journal, "scheduler_id": identity})
            return {"scheduler_id": identity}
        identity = request["scheduler_id"]
        recovered = recover(scheduler, request, journal)
        if recovered != identity:
            raise ValueError("scheduler identity does not match submission journal")
        if action == "status":
            return status(scheduler, request, journal)
        if action == "cancel":
            current = status(scheduler, request, journal)
            if current["execution_finished"]:
                return {"scheduler_id": identity, "accepted": True}
            checked(command("scancel" if scheduler == "slurm" else "qdel", identity))
            save(path, {**journal, "cancellation_requested": True})
            return {"scheduler_id": identity, "accepted": True}
        raise ValueError("unknown action")


def main():
    try:
        scheduler = sys.argv[1]
        if scheduler not in {"pbs", "torque", "slurm"}:
            raise ValueError("select pbs, torque or slurm")
        response = handle(scheduler, json.load(sys.stdin))
        print(json.dumps({"schema_version": PROTOCOL, **response}))
    except Exception as error:
        print(str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
