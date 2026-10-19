#!/usr/bin/env python3
"""TRI native CLI bridge for coragent-external-job/1; stdlib only."""
from __future__ import annotations

import json
import math
import os
import shutil
import subprocess
import sys


SCHEMA = "coragent-external-job/1"


def native(command, *args):
    executable = os.environ.get("CORAGENT_" + command.upper(), command)
    result = subprocess.run([executable, *args], text=True, capture_output=True, timeout=45)
    try:
        value = json.loads(result.stdout)
    except ValueError:
        raise RuntimeError(f"{command}: invalid JSON (exit {result.returncode})") from None
    if result.returncode:
        error = value.get("error", {}) if isinstance(value, dict) else {}
        raise RuntimeError(f"{command}: {error.get('message', result.stderr.strip())}")
    return value


def observation(task):
    state = {"wait": "queued", "run": "running", "done": "succeeded", "fail": "failed",
             "timed_out": "timed_out", "cancel": "cancelled", "blocked": "held", "lost": "unknown"}.get(task["state"], "unknown")
    finished = bool(task.get("finished_at")) and not task.get("lease_id")
    if state == "cancelled" and finished and task.get("started_at") and task.get("exit_code") is None:
        # TRI also closes cancelled records when a node lease expires. That
        # does not establish that the process on the unreachable node exited.
        state, finished = "unknown", False
    if state == "cancelled" and not finished:
        state = "running" if task.get("started_at") else "submitted"
    return {"schema_version": SCHEMA, "scheduler_id": str(task["id"]), "state": state,
            "execution_finished": finished, "exit_code": task.get("exit_code"),
            "started_at": task.get("started_at"), "finished_at": task.get("finished_at"),
            "error": task.get("error"), "diagnostics": {
                "native_state": task["state"], "node": task.get("node"), "attempt": task.get("attempt"),
                "lease_id": task.get("lease_id"), "stdout_path": task.get("stdout_path"),
                "stderr_path": task.get("stderr_path"), "cancellation_requested": task["state"] == "cancel"}}


def handle(request):
    if request.get("schema_version") != SCHEMA:
        raise ValueError("unsupported external Job protocol")
    action = request["action"]
    if action == "probe":
        missing = [command for command in ("tri_sub", "tri_stat", "tri_del")
                   if not shutil.which(os.environ.get("CORAGENT_" + command.upper(), command))]
        if missing:
            return {"schema_version": SCHEMA, "available": False, "error": "missing commands: " + ", ".join(missing)}
        native("tri_stat", "--json")
        return {"schema_version": SCHEMA, "available": True}
    if action == "submit":
        resources = request.get("resources", {})
        if request.get("queue") or resources.get("select"):
            raise ValueError("TRI resources use cpu/mem/gpu; configure the target without queue or PBS select")
        args = ["--json", "--name", request["job_id"], "--request-id", request["request_id"],
                "--external-id", request["request_id"], "--chdir", request["cwd"],
                "--output", "logs/scheduler.stdout", "--error", "logs/scheduler.stderr"]
        for key, flag in (("cpus", "--cpu"), ("memory_mb", "--mem"), ("gpus", "--gpu")):
            if resources.get(key) is not None:
                args += [flag, str(resources[key]) + ("M" if key == "memory_mb" else "")]
        if request.get("timeout_seconds") is not None:
            args += ["--timeout", str(math.ceil(request["timeout_seconds"]))]
        if os.environ.get("CORAGENT_TRI_NODE"):
            args += ["--node", os.environ["CORAGENT_TRI_NODE"]]
        # Absolute wrapper path remains valid on the assigned node's shared filesystem.
        task = native("tri_sub", *args, "--", request["script"])["task"]
        return observation(task)
    if action == "recover":
        # A read-only lookup by persistent workflow identity. An unavailable
        # server or removed record remains unresolved; recovery never submits.
        task = native("tri_stat", "--json", "--external-id", request["request_id"])
        if task.get("external_id") != request["request_id"]:
            raise ValueError("TRI recovery identity mismatch")
        return observation(task)
    if action == "status":
        return observation(native("tri_stat", "--json", request["scheduler_id"]))
    if action == "cancel":
        task = native("tri_del", "--json", request["scheduler_id"])
        return {**observation(task), "accepted": task["state"] in {"cancel", "done", "fail", "timed_out"}}
    raise ValueError("unknown external Job action: " + str(action))


def main():
    try:
        response = handle(json.load(sys.stdin))
        print(json.dumps(response))
        return 0
    except (OSError, ValueError, KeyError, TypeError, RuntimeError, subprocess.SubprocessError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
