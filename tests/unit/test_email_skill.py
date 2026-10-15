import json
from dataclasses import replace
from pathlib import Path

import pytest

from notify_lib import delivery


def test_email_cli_starts_in_a_fresh_interpreter(tmp_path):
    import os
    import subprocess
    import sys

    script = Path(__file__).resolve().parents[2] / "skills/email/scripts/email_cli.py"
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    result = subprocess.run(
        [sys.executable, str(script), "--help"], cwd=tmp_path,
        env=env, capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 0, result.stderr
    assert "prepare" in result.stdout and "send" in result.stdout


def fixture(root, monkeypatch):
    attachment = root / "artifacts" / "result.md"
    attachment.parent.mkdir(parents=True)
    attachment.write_text("Evidence report", encoding="utf-8")
    cfg = delivery.EmailConfig(
        source=root / "notifications.toml",
        enabled=True,
        recipient="reader@example.test",
        digest="config1",
        provider="smtp",
        from_address="sender@example.test",
    )
    monkeypatch.setattr(delivery, "load_notification_config", lambda *args: cfg)
    request = {
        "schema_version": delivery.REQUEST_SCHEMA,
        "message_id": "message-v1",
        "recipient": cfg.recipient,
        "subject": "Results",
        "body": "See report",
        "metadata": {"domain": "chemical.report", "event": "future-event"},
        "attachments": [{
            "ref": "artifacts/result.md",
            "sha256": delivery.sha256_path(attachment),
            "size_bytes": attachment.stat().st_size,
        }],
    }
    path = root / "request.json"
    path.write_text(json.dumps(request), encoding="utf-8")
    return path, cfg


def test_generic_message_accepts_opaque_caller_metadata(tmp_path, monkeypatch):
    request, _ = fixture(tmp_path, monkeypatch)
    calls = []
    monkeypatch.setattr(delivery, "_run_transport", lambda *args, **kwargs: calls.append(kwargs) or "accepted")
    result = delivery.send_email(tmp_path, request)
    assert result["state"] == "sent"
    assert result["message_id"] == "message-v1"
    assert calls and calls[0]["body"].startswith("See report")


def test_prepare_pins_recipient_and_attachment_digest(tmp_path, monkeypatch):
    request, cfg = fixture(tmp_path, monkeypatch)
    value = json.loads(request.read_text())
    value.pop("schema_version")
    value["attachments"] = ["artifacts/result.md"]
    prepared = delivery.prepare_email(tmp_path, value)
    assert prepared["schema_version"] == delivery.REQUEST_SCHEMA
    assert prepared["recipient"] == cfg.recipient
    assert prepared["attachments"][0]["sha256"].startswith("sha256:")


def test_old_notification_schema_is_rejected_before_transport(tmp_path, monkeypatch):
    request, _ = fixture(tmp_path, monkeypatch)
    value = json.loads(request.read_text())
    value["schema_version"] = "ts-user-notification/2"
    request.write_text(json.dumps(value))
    monkeypatch.setattr(delivery, "_run_transport", lambda *a, **kw: pytest.fail("transport started"))
    with pytest.raises(ValueError, match="schema_version"):
        delivery.send_email(tmp_path, request)


def test_unknown_delivery_and_changed_attachment_do_not_send(tmp_path, monkeypatch):
    request, _ = fixture(tmp_path, monkeypatch)
    calls = []

    def ambiguous(*args, **kwargs):
        calls.append(kwargs)
        raise delivery._DeliveryAmbiguous("connection lost after DATA")

    monkeypatch.setattr(delivery, "_run_transport", ambiguous)
    with pytest.raises(Exception, match="ambiguous"):
        delivery.send_email(tmp_path, request)
    with pytest.raises(ValueError, match="unknown"):
        delivery.send_email(tmp_path, request)
    assert len(calls) == 1

    (tmp_path / "artifacts/result.md").write_text("changed")
    with pytest.raises(ValueError, match="attachment"):
        delivery.send_email(tmp_path, request)
    assert len(calls) == 1


@pytest.mark.parametrize("error", [OSError("after DATA"), ValueError("unexpected response"), RuntimeError("transport interrupted")])
def test_unclassified_transport_errors_never_become_retryable(tmp_path, monkeypatch, error):
    request, _ = fixture(tmp_path, monkeypatch)
    calls = []

    def fail(*args, **kwargs):
        calls.append(1)
        raise error

    monkeypatch.setattr(delivery, "_run_transport", fail)
    with pytest.raises(delivery.NotificationError) as caught:
        delivery.send_email(tmp_path, request)
    assert caught.value.state == "unknown"
    assert caught.value.retry_disposition == "reconcile_only"
    with pytest.raises(ValueError, match="unknown"):
        delivery.send_email(tmp_path, request)
    assert calls == [1]


def test_content_change_under_same_identity_is_rejected(tmp_path, monkeypatch):
    request, _ = fixture(tmp_path, monkeypatch)
    calls = []
    monkeypatch.setattr(delivery, "_run_transport", lambda *args, **kwargs: calls.append(1) or "accepted")
    delivery.send_email(tmp_path, request)
    value = json.loads(request.read_text())
    value["body"] = "Changed body"
    request.write_text(json.dumps(value))
    with pytest.raises(ValueError, match="message_id_reused"):
        delivery.send_email(tmp_path, request)
    assert calls == [1]


def test_concurrent_delivery_and_crash_before_sent_receipt_do_not_resend(tmp_path, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor

    request, _ = fixture(tmp_path, monkeypatch)
    calls = []
    monkeypatch.setattr(delivery, "_run_transport", lambda *args, **kwargs: calls.append(1) or "accepted")
    original = delivery._write_private_json

    def fail_sent(path, value, **kwargs):
        if value.get("state") == "sent":
            raise OSError("crash before sent receipt")
        return original(path, value, **kwargs)

    monkeypatch.setattr(delivery, "_write_private_json", fail_sent)
    with pytest.raises(OSError):
        delivery.send_email(tmp_path, request)
    monkeypatch.setattr(delivery, "_write_private_json", original)
    with pytest.raises(delivery.NotificationError) as caught:
        delivery.send_email(tmp_path, request)
    assert caught.value.state == "unknown" and calls == [1]

    value = json.loads(request.read_text())
    value["message_id"] = "concurrent"
    request.write_text(json.dumps(value))
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: delivery.send_email(tmp_path, request), range(2)))
    assert {r["state"] for r in results} == {"sent", "already_sent"}
    assert calls == [1, 1]


def test_password_rotation_does_not_resend(tmp_path, monkeypatch):
    request, cfg = fixture(tmp_path, monkeypatch)
    calls = []
    monkeypatch.setattr(delivery, "_run_transport", lambda *args, **kwargs: calls.append(kwargs) or "accepted")
    assert delivery.send_email(tmp_path, request)["state"] == "sent"
    monkeypatch.setattr(delivery, "load_notification_config", lambda *args: replace(cfg, digest="rotated"))
    assert delivery.send_email(tmp_path, request)["state"] == "already_sent"
    assert len(calls) == 1
