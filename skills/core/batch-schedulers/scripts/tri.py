#!/usr/bin/env python3
"""TRI native CLI bridge for coragent-external-job/1; stdlib only."""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time


SCHEMA = "coragent-external-job/1"


def resource_failure(task, state):
    """Normalize TRI's resource enforcement outcomes for Job consumers."""
    if state != "failed":
        return None
    error = str(task.get("error") or "").lower()
    if "memory limit exceeded" in error or "memorymax" in error:
        return "memory_limit"
    if task.get("exit_code") == 78 or "resource enforcement" in error:
        return "resource_enforcement"
    return None


class QueueError(RuntimeError):
    def __init__(self, code, message, *, retryable=False, action_outcome="unknown"):
        super().__init__(message)
        self.details = {"code": code, "message": message, "retryable": retryable,
                        "action_outcome": action_outcome}


def identity(task, request, *, existing=False):
    if not isinstance(task, dict) or task.get("external_id") != request["request_id"]:
        raise QueueError("task_identity_mismatch", "TRI external identity does not match this Job")
    if type(task.get("id")) is not int or task["id"] < 1:
        raise QueueError("task_identity_mismatch", "TRI returned an invalid task ID")
    if existing and str(task["id"]) != request["scheduler_id"]:
        raise QueueError("task_identity_mismatch", "TRI scheduler identity does not match this Job")
    return task


def native(command, *args):
    executable = os.environ.get("CORAGENT_" + command.upper(), command)
    try:
        result = subprocess.run([executable, *args], text=True, capture_output=True, timeout=45)
    except OSError as exc:
        raise QueueError("cli_unavailable", f"{command}: {exc.strerror}",
                         action_outcome="not_submitted" if command == "tri_sub" else "unknown") from None
    try:
        value = json.loads(result.stdout)
    except ValueError:
        raise RuntimeError(f"{command}: invalid JSON (exit {result.returncode})") from None
    if result.returncode:
        error = value.get("error", {}) if isinstance(value, dict) else {}
        code = error.get("code", "request_failed")
        # Identity conflicts may refer to an already accepted task. A transport
        # failure can also hide acceptance: neither proves non-submission.
        raise QueueError(code, f"{command}: {error.get('message', result.stderr.strip())}",
                         retryable=error.get("retryable") is True,
                         action_outcome="not_submitted" if command == "tri_sub" and code == "invalid_request" else "unknown")
    return value


def observation(task):
    state = {"wait": "queued", "run": "running", "done": "succeeded", "fail": "failed",
             "timed_out": "timed_out", "cancel": "cancelled", "blocked": "held", "lost": "unknown"}.get(task["state"], "unknown")
    finished = bool(task.get("finished_at")) and not task.get("lease_id")
    if (state == "cancelled" and finished and task.get("started_at")
            and not task.get("cancel_confirmed", False)
            and ("cancel_confirmed" in task or task.get("exit_code") is None)):
        # TRI also closes cancelled records when a node lease expires. That
        # does not establish that the process on the unreachable node exited.
        state, finished = "unknown", False
    if state == "cancelled" and not finished:
        state = "running" if task.get("started_at") else "submitted"
    created = task.get("created_at")
    wait_seconds = None
    if state in {"queued", "held"}:
        try:
            stamp = float(created)
            if math.isfinite(stamp) and stamp >= 0:
                wait_seconds = max(0., time.time() - stamp)
        except (TypeError, ValueError):
            pass  # Missing evidence is not a fabricated zero-second wait.
    requested_node = os.environ.get("CORAGENT_TRI_NODE")
    assigned_node = task.get("node")
    node_mismatch = (requested_node is not None and assigned_node is not None
                     and assigned_node != requested_node)
    spec = task.get("spec") or {}
    resource_kind = resource_failure(task, state)
    return {"schema_version": SCHEMA, "scheduler_id": str(task["id"]), "state": state,
            "execution_finished": finished, "exit_code": task.get("exit_code"),
            "started_at": task.get("started_at"), "finished_at": task.get("finished_at"),
            "error": task.get("error"), "diagnostics": {
                "native_state": task["state"], "node": task.get("node"), "attempt": task.get("attempt"),
                "lease_id": task.get("lease_id"), "stdout_path": task.get("stdout_path"),
                "stderr_path": task.get("stderr_path"), "cancellation_requested": task["state"] == "cancel",
                "cancel_confirmed": task.get("cancel_confirmed", False),
                "completion_reason": task.get("completion_reason"),
                "external_id": task.get("external_id"), "created_at": created,
                "wait_seconds": wait_seconds,
                "requested_resources": {"cpus": spec.get("requested_cpu"),
                                        "memory_bytes": spec.get("requested_mem_bytes"),
                                        "gpus": spec.get("requested_gpus")},
                "effective_memory_limit_bytes": spec.get("requested_mem_bytes"),
                "memory_swap_limit_bytes": 0,
                "assigned_cpus": task.get("assigned_cpus"),
                "assigned_gpus": task.get("assigned_gpus"),
                "requested_node": requested_node,
                "node_match": not node_mismatch,
                "resource_failure": resource_kind}}


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
            raise QueueError("invalid_request", "TRI resources use cpu/mem/gpu; configure the target without queue or PBS select",
                             action_outcome="not_submitted")
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
        # The verification code and expected digest travel in TRI's task argv.
        # A guard inside run.sh cannot protect against a stale run.sh on a node
        # whose identical path points to a different filesystem.
        digest = hashlib.sha256(Path(request["script"]).read_bytes()).hexdigest()
        reject = "{ printf '%s\\n' CORAGENT_EXECUTION_ERROR=execution_script_changed >&2; exit 125; }"
        bootstrap = ('coragent_script_hash=$(sha256sum < "$2") || ' + reject + '\n'
                     'test "${coragent_script_hash%% *}" = "$1" || ' + reject + '\n'
                     'exec /bin/sh "$2"\n')
        task = native("tri_sub", *args, "--", "/bin/sh", "-c", bootstrap,
                      "coragent-tri", digest, request["script"])["task"]
        return observation(identity(task, request))
    if action == "recover":
        # A read-only lookup by persistent workflow identity. An unavailable
        # server or removed record remains unresolved; recovery never submits.
        task = native("tri_stat", "--json", "--external-id", request["request_id"])
        return observation(identity(task, request))
    if action in {"status", "cancel"}:
        task = identity(native("tri_stat", "--json", "--external-id", request["request_id"]), request, existing=True)
        if action == "status":
            return observation(task)
        # Check before the destructive command, then verify its response too.
        # TRI's numeric-only cancel API cannot make this lookup atomic with cancel.
        task = identity(native("tri_del", "--json", request["scheduler_id"]), request, existing=True)
        return {**observation(task), "accepted": task["state"] in {"cancel", "done", "fail", "timed_out"}}
    raise ValueError("unknown external Job action: " + str(action))


def main():
    try:
        response = handle(json.load(sys.stdin))
        print(json.dumps(response))
        return 0
    except QueueError as exc:
        print(json.dumps({"schema_version": SCHEMA, "error": exc.details}))
        return 0
    except (OSError, ValueError, KeyError, TypeError, RuntimeError, subprocess.SubprocessError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
