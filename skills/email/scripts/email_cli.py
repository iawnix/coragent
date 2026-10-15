"""Generic SMTP email interface: inspect, prepare, send, and inspect receipts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from notify_lib import delivery
from notify_lib.artifacts import workspace_path
from notify_lib.errors import notification_error_payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("check", "prepare", "send", "status"))
    parser.add_argument("--root", required=True)
    parser.add_argument("--request-file")
    parser.add_argument("--output", required=True, help="prepared message or command result")
    parser.add_argument("--receipt-ref")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    try:
        if args.command == "check":
            config = delivery.load_notification_config()
            result = {
                "enabled": config.enabled,
                "recipient": config.recipient,
                "transport": config.provider,
            }
        elif args.command == "status":
            if not args.receipt_ref:
                raise ValueError("--receipt-ref is required for status")
            _, path = workspace_path(root, args.receipt_ref, must_exist=True)
            result = json.loads(path.read_text(encoding="utf-8"))
        elif args.command == "prepare":
            if not args.request_file:
                raise ValueError("--request-file is required for prepare")
            request = json.loads(Path(args.request_file).read_text(encoding="utf-8"))
            result = delivery.prepare_email(root, request)
        else:
            if not args.request_file:
                raise ValueError("--request-file is required for send")
            result = delivery.send_email(root, Path(args.request_file))
        code = 0
    except Exception as exc:
        result = notification_error_payload(exc)
        code = 2

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
