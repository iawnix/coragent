"""Optional service settings have one contract and do not gate research startup."""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from research_agent.bootstrap.launcher import configure_notifications
from research_agent.configuration.configuration import Configuration, toml_text
from research_agent.integrations.email_config import (
    parse_email_config, project_notification_config, validate_password_file,
)


def email_settings(**changes):
    return {"enabled": True, "provider": "smtp", "preset": "custom", "host": "smtp.example.invalid",
            "recipient": "recipient@example.invalid", "username": "sender@example.invalid",
            "password_env": "TEST_SMTP_PASSWORD", **changes}


def notification_file(tmp_path, email):
    path = tmp_path / "email.toml"
    path.write_text(toml_text({"notifications": {"email": email}}))
    path.chmod(0o600)
    return path


def test_email_configuration_does_not_read_secret_or_connect(tmp_path, monkeypatch):
    from notify_lib import delivery

    missing = tmp_path / "missing-secret"
    raw = email_settings()
    raw.pop("password_env")
    raw["password_file"] = str(missing)
    config = parse_email_config(raw)
    assert config["password_file"] == str(missing)
    assert config["from_address"] == raw["username"]
    assert (config["port"], config["security"]) == (465, "ssl")
    path = notification_file(tmp_path, raw)
    monkeypatch.setenv("CORAGENT_NOTIFICATION_CONFIG", str(path))
    monkeypatch.setattr(delivery, "_run_transport", lambda *a, **k: pytest.fail("startup must not send"))
    configure_notifications(SimpleNamespace(notification_config_default=path))
    assert os.environ["CORAGENT_NOTIFICATION_DISPLAY_TARGET"] == raw["recipient"]
    with pytest.raises(ValueError, match="regular file"):
        delivery.load_notification_config(path)


def test_disabled_email_needs_no_recipient_or_credentials(tmp_path, monkeypatch):
    from notify_lib import delivery

    path = notification_file(tmp_path, {"enabled": False})
    monkeypatch.setenv("CORAGENT_NOTIFICATION_CONFIG", str(path))
    configure_notifications(SimpleNamespace(notification_config_default=path))
    assert os.environ["CORAGENT_NOTIFICATION_DISPLAY_TARGET"] == "disabled"
    assert delivery.load_notification_config(path).enabled is False


@pytest.mark.parametrize("change", [{"binding": "smtp"}, {"port": True}, {"recipient": "invalid"},
                                     {"security": "plaintext"}, {"password_file": "/unused"}])
def test_same_invalid_settings_are_rejected_by_install_and_delivery(tmp_path, monkeypatch, capsys, change):
    from notify_lib import delivery

    raw = email_settings(**change)
    with pytest.raises(ValueError) as parsed:
        parse_email_config(raw)
    path = notification_file(tmp_path, raw)
    with pytest.raises(ValueError) as runtime:
        delivery.load_notification_config(path)
    assert str(runtime.value) == str(parsed.value)
    monkeypatch.setenv("CORAGENT_NOTIFICATION_CONFIG", str(path))
    configure_notifications(SimpleNamespace(notification_config_default=path))
    assert os.environ["CORAGENT_NOTIFICATION_DISPLAY_TARGET"] == "configuration error"
    assert "email operations are unavailable" in capsys.readouterr().err


def test_main_configuration_reads_without_interpreting_optional_smtp(tmp_path):
    configuration = Configuration(tmp_path / "config.toml")
    configuration.write({"schema_version": 1, "notifications": {"email": {"enabled": "invalid"}}})
    assert configuration.read()["notifications"]["email"]["enabled"] == "invalid"
    with pytest.raises(ValueError, match="boolean"):
        parse_email_config(configuration.read()["notifications"]["email"])


def test_generated_email_failure_remains_visible_without_blocking_startup(tmp_path, monkeypatch, capsys):
    path = tmp_path / "email.toml"
    (tmp_path / "configuration-status.json").write_text(json.dumps({
        "email": {"state": "invalid", "error": "email configuration is invalid; ValueError"}}))
    monkeypatch.delenv("CORAGENT_NOTIFICATION_CONFIG", raising=False)
    configure_notifications(SimpleNamespace(notification_config_default=path))
    assert os.environ["CORAGENT_NOTIFICATION_DISPLAY_TARGET"] == "configuration error"
    assert os.environ["CORAGENT_NOTIFICATION_CONFIG"] == str(path)
    assert "email configuration is invalid" in capsys.readouterr().err


def test_relative_password_path_uses_configuration_directory(tmp_path):
    raw = email_settings()
    raw.pop("password_env")
    raw["password_file"] = "smtp-password"
    assert parse_email_config(raw, base_dir=tmp_path)["password_file"] == str(tmp_path / "smtp-password")
    with pytest.raises(ValueError, match="absolute"):
        parse_email_config(raw)
    secret = tmp_path / "smtp-password"
    secret.write_text("test-only-password")
    secret.chmod(0o600)
    assert validate_password_file(secret) == secret
    secret.chmod(0o644)
    with pytest.raises(ValueError, match="0600"):
        validate_password_file(secret)


def test_email_projection_keeps_secret_out_of_derived_configuration(tmp_path):
    raw = email_settings()
    raw.pop("password_env")
    raw["password"] = "fixture-secret"
    path = tmp_path / "smtp-password"
    projected, secret = project_notification_config({"notifications": {"email": raw}}, password_path=path)
    assert secret == "fixture-secret"
    assert projected["notifications"]["email"]["password_file"] == str(path)
    assert "password" not in projected["notifications"]["email"]
    assert not path.exists()
    assert raw["password"] == "fixture-secret"


def test_name_resolver_contract_loads_without_scientific_runtime():
    root = Path(__file__).resolve().parents[2]
    path = root / "skills/chemical/material-preparation/scripts/materials/name_resolver_config.py"
    spec = importlib.util.spec_from_file_location("standalone_name_resolver_config", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    settings = module.parse_name_resolver_config({"backends": {"pubchem": {"cache": False}}})
    assert settings["backends"]["pubchem"]["endpoint"] == "https://pubchem.ncbi.nlm.nih.gov/rest/pug"
    assert settings["backends"]["pubchem"]["cache"] is False
    with pytest.raises(ValueError, match="unsupported"):
        module.parse_name_resolver_config({"backends": {"pubchem": {"unknown": True}}})
