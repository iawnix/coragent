"""Chemical report email orchestration over the generic SMTP Skill."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any


def _email_scripts() -> Path:
    configured = os.environ.get("CORAGENT_EMAIL_SKILL", "").strip()
    if configured:
        return Path(configured).expanduser().resolve(strict=True)
    # Source and installed skill trees keep core and chemical under the same skills root.
    return Path(__file__).resolve().parents[3] / "core" / "email" / "scripts"


EMAIL_SCRIPTS = _email_scripts()
if str(EMAIL_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(EMAIL_SCRIPTS))

from notify_lib import delivery  # noqa: E402
from notify_lib.errors import notification_error_payload  # noqa: E402
from notify_lib.artifacts import workspace_path, sha256_path  # noqa: E402


REPORT_EVENTS = frozenset({
    "progress",
    "report_ready",
    "calculation_failed",
    "calculation_ambiguous",
    "study_completed",
})


def _report_request(path: Path, workspace: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("report email request must be an object")
    allowed = {"notification_id", "event", "subject", "summary", "report_refs"}
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise ValueError("report email request contains unknown fields: " + ", ".join(unknown))
    notification_id = delivery.bounded_text(value.get("notification_id"), "notification_id", 256)
    event = delivery.bounded_text(value.get("event"), "report email event", 64)
    if event not in REPORT_EVENTS:
        raise ValueError("unsupported report email event: " + event)
    subject = delivery.bounded_text(value.get("subject"), "report email subject", 300)
    summary = delivery.bounded_content(value.get("summary"), "report email summary", 20_000)
    refs = value.get("report_refs", [])
    attachments, manifests = _validated_report_refs(workspace, refs)
    return {
        "notification_id": notification_id,
        "event": event,
        "subject": subject,
        "summary": summary,
        "report_refs": attachments,
        "manifest_digests": manifests,
    }


def _validated_report_refs(
    workspace: Path,
    refs: Any,
) -> tuple[list[str], list[dict[str, str]]]:
    if not isinstance(refs, list) or len(refs) > 8:
        raise ValueError("report_refs must be an array with at most 8 entries")
    attachments: list[str] = []
    manifests: list[dict[str, str]] = []
    for index, item in enumerate(refs):
        ref, attachment_path = workspace_path(workspace, item, must_exist=True)
        if ref in attachments:
            raise ValueError("report_refs contains duplicates")
        _validate_report_manifest(workspace, ref, attachment_path)
        attachments.append(ref)
        manifests.append({"ref": ref, "sha256": sha256_path(attachment_path)})
    return attachments, manifests


def _validate_report_manifest(workspace: Path, ref: str, path: Path) -> None:
    parts = ref.split("/")
    if len(parts) < 3:
        raise ValueError("report email attachments must belong to a report package")
    package_ref = "/".join(parts[:2])
    member_ref = "/".join(parts[2:])
    manifest_ref = f"{package_ref}/package_manifest.json"
    _, manifest_path = workspace_path(workspace, manifest_ref, must_exist=False, allow_existing=True)
    # Legacy report builders may emit a report directory without a package
    # manifest. The report layer still pins the file digest; once a manifest
    # exists, membership and its digest are mandatory.
    if not manifest_path.exists():
        return
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"report package manifest is invalid: {manifest_ref}") from exc
    if not isinstance(manifest, dict) or manifest.get("schema_version") != "ts-report-package/5":
        raise ValueError(f"report package manifest has an unsupported schema: {manifest_ref}")
    files = manifest.get("files")
    if not isinstance(files, list):
        raise ValueError(f"report package manifest has no file index: {manifest_ref}")
    matches = [item for item in files if isinstance(item, dict) and item.get("ref") == member_ref]
    if len(matches) != 1:
        raise ValueError(f"report attachment is not listed in its package manifest: {ref}")
    listed = matches[0]
    if listed.get("sha256") != sha256_path(path) or listed.get("size_bytes") != path.stat().st_size:
        raise ValueError(f"report attachment does not match its package manifest: {ref}")


def prepare_report_email(root: Path, request_file: Path) -> dict[str, Any]:
    workspace = root.resolve(strict=True)
    request = _report_request(request_file, workspace)
    generic = {
        "message_id": request["notification_id"],
        "subject": request["subject"],
        "body": request["summary"],
        "attachments": request["report_refs"],
        "metadata": {
            "domain": "chemical.report",
            "event": request["event"],
            "report_refs": request["report_refs"],
            "manifest_digests": request["manifest_digests"],
        },
    }
    return delivery.prepare_email(root, generic)


def _validate_prepared_report_email(root: Path, request_file: Path) -> dict[str, Any]:
    """Validate the domain contract carried by a prepared generic message."""
    value = json.loads(request_file.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("prepared report email must be an object")
    delivery.validate_email_message(value)
    metadata = value.get("metadata")
    if not isinstance(metadata, dict) or metadata.get("domain") != "chemical.report":
        raise ValueError("prepared email is missing chemical.report metadata")
    event = delivery.bounded_text(metadata.get("event"), "report email event", 64)
    if event not in REPORT_EVENTS:
        raise ValueError("unsupported report email event: " + event)
    refs = metadata.get("report_refs")
    attachments = value.get("attachments")
    if not isinstance(attachments, list):
        raise ValueError("prepared report email attachments must be an array")
    attachment_refs = []
    for index, item in enumerate(attachments):
        if not isinstance(item, dict):
            raise ValueError(f"attachments[{index}] must be an object")
        attachment_refs.append(item.get("ref"))
    if refs != attachment_refs:
        raise ValueError("prepared report email metadata does not match attachments")
    _, manifests = _validated_report_refs(root.resolve(strict=True), refs)
    if metadata.get("manifest_digests") != manifests:
        raise ValueError("prepared report email manifest digests are stale")
    return value


def send_report_email(root: Path, request_file: Path) -> dict[str, Any]:
    """Revalidate report policy, then delegate delivery to generic SMTP."""
    _validate_prepared_report_email(root, request_file)
    return delivery.send_email(root, request_file)


def _journal(root: Path, command: str, result: dict[str, Any], request_file: Path | None) -> dict[str, Any]:
    try:
        from research_agent.application.delivery_evidence import record_delivery_evidence

        fact = result
        receipt_ref = result.get("receipt_ref")
        if receipt_ref:
            _, receipt_path = workspace_path(root, receipt_ref, must_exist=True)
            fact = json.loads(receipt_path.read_text(encoding="utf-8"))
        if request_file is not None:
            source = json.loads(request_file.read_text(encoding="utf-8"))
            metadata = source.get("metadata") if isinstance(source, dict) else {}
            event = metadata.get("event") if isinstance(metadata, dict) else None
            if event is None and isinstance(source, dict):
                event = source.get("event")
            fact = {**fact, "domain": "chemical.report", "event": event}
        identity = ["chemical-report-email", receipt_ref, fact.get("state")] if receipt_ref else ["chemical-report-email", command, fact]
        error = record_delivery_evidence(root, fact, title="Report email " + command,
                                         receipt_ref=receipt_ref, identity=identity)
        if error:
            return {**result, "journal_error": error}
    except Exception as error:
        return {**result, "journal_error": str(error)}
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("check", "prepare", "send", "status"))
    parser.add_argument("--root", required=True)
    parser.add_argument("--request-file")
    parser.add_argument("--output", required=True)
    parser.add_argument("--receipt-ref")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    request_file = Path(args.request_file) if args.request_file else None
    try:
        if args.command == "check":
            config = delivery.load_notification_config()
            result = {"enabled": config.enabled, "recipient": config.recipient, "transport": config.provider}
        elif args.command == "status":
            if not args.receipt_ref:
                raise ValueError("--receipt-ref is required for status")
            _, receipt = workspace_path(root, args.receipt_ref, must_exist=True)
            result = json.loads(receipt.read_text(encoding="utf-8"))
        elif args.command == "prepare":
            if request_file is None:
                raise ValueError("--request-file is required for prepare")
            result = prepare_report_email(root, request_file)
        else:
            if request_file is None:
                raise ValueError("--request-file is required for send")
            result = send_report_email(root, request_file)
        code = 0
        if args.command in {"prepare", "send"}:
            result = _journal(root, args.command, result, request_file)
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
