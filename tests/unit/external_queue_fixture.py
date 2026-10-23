"""A persistent deterministic queue CLI for external Job integration tests."""
import json
import os
from pathlib import Path
import sys
import subprocess
import time


def main():
    root = Path(os.environ["QUEUE_FIXTURE_ROOT"])
    command = Path(sys.argv[0]).name
    args = sys.argv[1:]
    state_file = root / "tasks.json"
    tasks = json.loads(state_file.read_text()) if state_file.exists() else []
    overrides = root / 'response-overrides.json'
    changes = json.loads(overrides.read_text()) if overrides.exists() else {}
    if command == "tri_sub":
        failure = root / 'submit-error.json'
        if failure.exists():
            print(json.dumps({'error': json.loads(failure.read_text())}))
            return 1
        def option(name, default=None):
            return args[args.index(name) + 1] if name in args else default
        request = option("--external-id")
        task = next((item for item in tasks if item["external_id"] == request), None)
        if task is None:
            task = {"id": len(tasks) + 1, "external_id": request, "state": "wait", "attempt": 0,
                    "started_at": None, "finished_at": None, "lease_id": None, "exit_code": None,
                    "created_at": str(time.time()), "node": None, "assigned_cpus": None, "assigned_gpus": None,
                    "spec": {"requested_cpu": int(option('--cpu', '1')),
                             "requested_mem_bytes": int(option('--mem', '64M')[:-1]) * 1024**2,
                             "requested_gpus": int(option('--gpu', '0'))},
                    "cwd": option("--chdir"), "script": args[-1],
                    "command": args[args.index('--') + 1:], "arguments": args}
            if (root / 'auto-run').exists():
                result = subprocess.run(task['command'], cwd=task['cwd'], capture_output=True)
                task.update(node=option('--node', 'fed1'), state='done' if result.returncode == 0 else 'fail',
                            exit_code=result.returncode, started_at=str(time.time()), finished_at=str(time.time()),
                            assigned_cpus='0', assigned_gpus='')
            tasks.append(task)
            state_file.write_text(json.dumps(tasks))
        if (root / "lose-submit-response").exists():
            print("lost response", file=sys.stderr)
            return 1
        print(json.dumps({"task": {**task, **changes.get(command, {})}, "created": True}))
        return 0
    if len(args) == 1:
        print(json.dumps(tasks))
        return 0
    if "--external-id" in args:
        task = next(item for item in tasks if item["external_id"] == args[-1])
    else:
        task = next(item for item in tasks if item["id"] == int(args[-1]))
    if command == "tri_del":
        (root / 'cancel-called').touch()
        task["state"] = "cancel"
        if not task["started_at"]:
            task["finished_at"] = "now"
        state_file.write_text(json.dumps(tasks))
    if (root / "invalid-status").exists():
        print("bad json")
    else:
        print(json.dumps({**task, **changes.get(command, {})}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
