"""One standard-library SMTP configuration contract for installation and use."""
from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
import re
import stat


SMTP_PRESETS = {
    "163": {"host": "smtp.163.com", "port": 465, "security": "ssl"},
    "qq": {"host": "smtp.qq.com", "port": 465, "security": "ssl"},
    "custom": {"host": None, "port": 465, "security": "ssl"},
}
SMTP_SECURITY = frozenset({"ssl", "starttls"})
_ENV_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_FIELDS = {"enabled", "provider", "preset", "host", "port", "security", "recipient",
           "username", "from_address", "password", "password_env", "password_file"}


def _text(value, label, maximum):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string")
    result = value.strip()
    if len(result) > maximum or any(ord(character) < 32 for character in result):
        raise ValueError(f"{label} exceeds its safe limit")
    return result


def validate_email_address(value, label="email address") -> str:
    address = _text(value, label, 320)
    if address.count("@") != 1 or any(character.isspace() for character in address):
        raise ValueError(f"{label} must be one email address")
    local, domain = address.split("@")
    if not local or "." not in domain or domain.startswith(".") or domain.endswith("."):
        raise ValueError(f"{label} must be one email address")
    return address


def _password_path(value, *, base_dir=None) -> Path:
    path = Path(_text(str(value) if isinstance(value, Path) else value,
                      "notifications.email.password_file", 4096)).expanduser()
    if not path.is_absolute():
        if base_dir is None or not Path(base_dir).is_absolute():
            raise ValueError("notifications.email.password_file must be an absolute path")
        path = Path(base_dir) / path
    return path


def validate_password_file(value: str | Path, *, base_dir: Path | None = None) -> Path:
    """Check the selected secret only when installing or using email."""
    path = _password_path(value, base_dir=base_dir)
    if path.is_symlink() or not path.is_file():
        raise ValueError("notifications.email.password_file must be a regular file")
    if stat.S_IMODE(path.stat().st_mode) & 0o077:
        raise ValueError("notifications.email.password_file must have mode 0600")
    return path.resolve(strict=True)


def parse_email_config(raw: Mapping, *, base_dir: Path | None = None) -> dict:
    """Normalize one email table without reading secrets, files or the network."""
    if not isinstance(raw, Mapping) or set(raw) - _FIELDS:
        raise ValueError("notifications.email requires supported SMTP settings")
    enabled = raw.get("enabled", True)
    if type(enabled) is not bool:
        raise ValueError("notifications.email.enabled must be a boolean")
    if not enabled:
        return {"enabled": False}
    if raw.get("provider") != "smtp":
        raise ValueError("notifications.email.provider must be smtp")
    preset = _text(raw.get("preset"), "notifications.email.preset", 32).lower()
    if preset not in SMTP_PRESETS:
        raise ValueError("notifications.email.preset must be 163, qq, or custom")
    defaults = SMTP_PRESETS[preset]
    host = _text(raw.get("host", defaults["host"]), "notifications.email.host", 255)
    if any(character.isspace() for character in host) or "/" in host or "@" in host:
        raise ValueError("notifications.email.host must be a hostname")
    if preset != "custom" and host != defaults["host"]:
        raise ValueError("notifications.email.host must match the selected SMTP preset")
    port = raw.get("port", defaults["port"])
    if type(port) is not int or not 1 <= port <= 65535:
        raise ValueError("notifications.email.port must be an integer from 1 to 65535")
    security = _text(raw.get("security", defaults["security"]),
                     "notifications.email.security", 16).lower()
    if security not in SMTP_SECURITY:
        raise ValueError("notifications.email.security must be ssl or starttls")
    username = validate_email_address(raw.get("username"), "notifications.email.username")
    result = {"enabled": True, "provider": "smtp", "preset": preset, "host": host,
              "port": port, "security": security, "username": username,
              "recipient": validate_email_address(raw.get("recipient"), "notifications.email.recipient"),
              "from_address": validate_email_address(raw.get("from_address", username),
                                                     "notifications.email.from_address")}
    selected = [name for name in ("password", "password_env", "password_file") if name in raw]
    if len(selected) != 1:
        raise ValueError("notifications.email requires exactly one password source")
    name = selected[0]
    value = raw[name]
    if name == "password_file":
        value = str(_password_path(value, base_dir=base_dir))
    elif name == "password_env":
        value = _text(value, "notifications.email.password_env", 128)
        if not _ENV_NAME.fullmatch(value):
            raise ValueError("notifications.email.password_env must be an environment variable name")
    elif not isinstance(value, str) or not value or "\x00" in value:
        raise ValueError("notifications.email.password must be a non-empty credential value or reference")
    result[name] = value
    return result


def parse_notification_config(raw: Mapping, *, base_dir: Path | None = None) -> dict:
    """Parse the derived notification document using the same email contract."""
    if not isinstance(raw, Mapping) or set(raw) != {"notifications"}:
        raise ValueError("notification configuration must contain only [notifications]")
    notifications = raw["notifications"]
    if not isinstance(notifications, Mapping) or set(notifications) != {"email"}:
        raise ValueError("notification configuration must contain only [notifications.email]")
    return parse_email_config(notifications["email"], base_dir=base_dir)


def project_notification_config(raw: Mapping, *, password_path: Path) -> tuple[dict, str | None]:
    """Project a resolved notification document without writing its secret."""
    email = parse_notification_config(raw)
    secret = email.pop("password", None)
    if secret is not None:
        email["password_file"] = str(_password_path(password_path))
    return {"notifications": {"email": email}}, secret
