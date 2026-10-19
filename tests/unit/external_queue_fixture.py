"""A persistent deterministic queue CLI for external Job integration tests."""
import json
import os
from pathlib import Path
import sys


def main():
    root = Path(os.environ["QUEUE_FIXTURE_ROOT"])
    command = Path(sys.argv[0]).name
    args = sys.argv[1:]
    state_file = root / "tasks.json"
    tasks = json.loads(state_file.read_text()) if state_file.exists() else []
    if command == "tri_sub":
        def option(name):
            return args[args.index(name) + 1]
        request = option("--external-id")
        task = next((item for item in tasks if item["external_id"] == request), None)
        if task is None:
            task = {"id": len(tasks) + 1, "external_id": request, "state": "wait", "attempt": 0,
                    "started_at": None, "finished_at": None, "lease_id": None, "exit_code": None,
                    "cwd": option("--chdir"), "script": args[-1], "arguments": args}
            tasks.append(task)
            state_file.write_text(json.dumps(tasks))
        if (root / "lose-submit-response").exists():
            print("lost response", file=sys.stderr)
            return 1
        print(json.dumps({"task": task, "created": True}))
        return 0
    if len(args) == 1:
        print(json.dumps(tasks))
        return 0
    if "--external-id" in args:
        task = next(item for item in tasks if item["external_id"] == args[-1])
    else:
        task = next(item for item in tasks if item["id"] == int(args[-1]))
    if command == "tri_del":
        task["state"] = "cancel"
        if not task["started_at"]:
            task["finished_at"] = "now"
        state_file.write_text(json.dumps(tasks))
    if (root / "invalid-status").exists():
        print("bad json")
    else:
        print(json.dumps(task))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
