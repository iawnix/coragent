import importlib.util
import json
from pathlib import Path

import pytest

from notify_lib import delivery


def load_adapter():
    path = Path(__file__).resolve().parents[2] / "skills/chemical/chemical-report/scripts/email_delivery.py"
    spec = importlib.util.spec_from_file_location("report_email_delivery_fixture", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_report_adapter_owns_event_and_manifest_policy(tmp_path, monkeypatch):
    adapter = load_adapter()
    report_dir = tmp_path / "reports" / "package-v1"
    report_dir.mkdir(parents=True)
    report = report_dir / "report.md"
    report.write_text("Report evidence", encoding="utf-8")
    manifest = report_dir / "package_manifest.json"
    manifest.write_text(json.dumps({
        "schema_version": "ts-report-package/5",
        "files": [{"ref": "report.md", "sha256": delivery.sha256_path(report), "size_bytes": report.stat().st_size}],
    }), encoding="utf-8")
    cfg = delivery.EmailConfig(
        source=tmp_path / "notifications.toml",
        enabled=True,
        recipient="reader@example.test",
        digest="config1",
        provider="smtp",
        from_address="sender@example.test",
    )
    monkeypatch.setattr(delivery, "load_notification_config", lambda *args: cfg)
    request = tmp_path / "report-email.json"
    request.write_text(json.dumps({
        "notification_id": "report-ready-v1",
        "event": "report_ready",
        "subject": "Report",
        "summary": "The report is ready.",
        "report_refs": ["reports/package-v1/report.md"],
    }), encoding="utf-8")

    prepared = adapter.prepare_report_email(tmp_path, request)
    assert prepared["schema_version"] == delivery.REQUEST_SCHEMA
    assert prepared["message_id"] == "report-ready-v1"
    assert prepared["metadata"]["event"] == "report_ready"
    assert prepared["attachments"][0]["ref"] == "reports/package-v1/report.md"

    manifest.write_text(json.dumps({
        "schema_version": "ts-report-package/5",
        "files": [{"ref": "report.md", "sha256": "sha256:" + "0" * 64, "size_bytes": report.stat().st_size}],
    }), encoding="utf-8")
    with pytest.raises(ValueError, match="package manifest"):
        adapter.prepare_report_email(tmp_path, request)
