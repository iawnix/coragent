"""Installation-configured, idempotent SMTP email delivery."""

from __future__ import annotations

import fcntl
import json
import mimetypes
import os
import re
import smtplib
import socket
import ssl
import stat
import tempfile
import time
import tomllib
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from email.message import EmailMessage
from email.utils import formatdate
from pathlib import Path
from typing import Any

from .artifacts import bounded_content, bounded_text, sha256_json, sha256_path, workspace_path, workspace_root
from .errors import NotificationError

CONFIG_ENV = "CORAGENT_NOTIFICATION_CONFIG"
SMTP_CONFIG_SCHEMA = "ts-notification-config/2"
REQUEST_SCHEMA = "ts-email-message/1"
RECEIPT_SCHEMA = "ts-email-receipt/1"
DELIVERY_DIR_REF = "artifacts/email/deliveries"
SMTP_PRESETS: dict[str, dict[str, Any]] = {
    "163": {"host": "smtp.163.com", "port": 465, "security": "ssl"},
    "qq": {"host": "smtp.qq.com", "port": 465, "security": "ssl"},
    "custom": {"host": None, "port": 465, "security": "ssl"},
}
SMTP_SECURITY = frozenset({"ssl", "starttls"})
SMTP_CONNECT_TIMEOUT = 120
ENV_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_SYSTEM_SMTP = smtplib.SMTP
_SYSTEM_SMTP_SSL = smtplib.SMTP_SSL
@dataclass(frozen=True)
class EmailConfig:
    source: Path
    enabled: bool
    recipient: str
    digest: str = ""
    provider: str = "smtp"
    from_address: str | None = None
    smtp_preset: str | None = None
    smtp_host: str | None = None
    smtp_port: int | None = None
    smtp_security: str | None = None
    smtp_username: str | None = None
    smtp_password_env: str | None = None
    smtp_password_file: Path | None = None


# Kept as a source-level alias for callers that imported the old descriptive
# name. The transport itself has no notification or domain semantics.
EmailNotificationConfig = EmailConfig


class _DeliveryNotStarted(RuntimeError):
    """The provider process was not started, so no message was sent."""


class _DeliveryAmbiguous(RuntimeError):
    """The provider process started, so delivery cannot be retried safely."""


def send_email(root: Path, request_file: Path) -> dict[str, Any]:
    """Send one bounded email message using the installation-owned address."""
    workspace = workspace_root(root)
    request = _load_request(request_file)
    identity = bounded_text(request.get("message_id"), "message_id", 256)
    lock_path = workspace / DELIVERY_DIR_REF / ("id-" + sha256_json(identity).removeprefix('sha256:') + ".guard")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    # Serialize by logical identity as well as content, so changing a body
    # cannot turn a retry into a second delivery under the same identity.
    with _delivery_lock(lock_path, touch=False):
        return _send_email(workspace, request)


def prepare_email(root: Path, request: dict[str, Any]) -> dict[str, Any]:
    """Pin attachment digests and the configured recipient for one message."""
    workspace = workspace_root(root)
    config = load_notification_config()
    if not config.enabled:
        raise ValueError("email notifications are disabled by the installation configuration")
    value = dict(request)
    value["schema_version"] = REQUEST_SCHEMA
    value["recipient"] = config.recipient
    _validate_message(value)
    _, _, records = _resolve_attachments(workspace, value.get("attachments", []), prepared=False)
    value["attachments"] = records
    return value


def validate_email_message(request: dict[str, Any]) -> None:
    """Validate the generic message shape without reading SMTP configuration."""
    if not isinstance(request, dict):
        raise ValueError("email message must be an object")
    _validate_message(request)


def notify_user(root: Path, request_file: Path) -> dict[str, Any]:
    """Compatibility alias for the generic email interface."""
    return send_email(root, request_file)


def _send_email(workspace: Path, request: dict[str, Any]) -> dict[str, Any]:

    config = load_notification_config()
    if not config.enabled:
        raise ValueError("email notifications are disabled by the installation configuration")
    message_id = bounded_text(request.get("message_id"), "message_id", 256)
    subject = bounded_text(request.get("subject"), "email subject", 300)
    body = bounded_content(request.get("body"), "email body", 20_000)
    attachment_refs, attachment_paths, attachment_records = _resolve_attachments(
        workspace, request.get("attachments", []), prepared=True,
    )
    message = {
        "schema_version": REQUEST_SCHEMA,
        "message_id": message_id,
        "subject": subject,
        "body": body,
        "attachments": attachment_records,
    }
    if request.get("recipient") != config.recipient:
        raise ValueError("configured recipient changed since preparation")
    metadata = request.get("metadata")
    if metadata is not None and not isinstance(metadata, dict):
        raise ValueError("metadata must be an object")
    if metadata is not None:
        message["metadata"] = metadata
    message["recipient"] = config.recipient
    message_digest = sha256_json(message)
    for path in (workspace / DELIVERY_DIR_REF).glob("*.json"):
        if not path.stat().st_size: continue
        old = json.loads(path.read_text())
        if old.get("message_id") == message_id and old.get("message_digest") != message_digest:
            raise ValueError("message_id_reused: changed delivery content requires a new message_id")
    receipt_ref = f"{DELIVERY_DIR_REF}/{message_digest.removeprefix('sha256:')}.json"
    _, receipt_path = workspace_path(workspace, receipt_ref, must_exist=False, allow_existing=True)
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    with _delivery_lock(receipt_path):
        if receipt_path.stat().st_size:
            existing = _existing_delivery_result(receipt_ref, receipt_path, message_digest)
            if existing is not None:
                return existing

        guard = {
            "schema_version": RECEIPT_SCHEMA,
            "state": "sending",
            "message_id": message_id,
            "created_at": _now(),
            "subject": subject,
            "provider": config.provider,
            "message_digest": message_digest,
            "email_config_digest": config.digest,
            "attachments": attachment_records,
            "metadata": metadata,
        }
        _write_private_json(receipt_path, guard, exclusive=False)

        transport_started = False
        try:
            _revalidate_email_inputs(
                workspace,
                config,
                attachment_records,
            )
            transport_started = True
            provider_output = _run_transport(
                config,
                message_digest=message_digest,
                recipient=config.recipient,
                subject=subject,
                body=body,
                attachments=list(zip(attachment_paths, attachment_records, strict=True)),
            )
        except _DeliveryNotStarted as exc:
            failed = {
                **guard,
                "state": "failed",
                "updated_at": _now(),
                "error_class": "delivery_not_started",
                "error": _safe_error(exc),
            }
            _write_private_json(receipt_path, failed, exclusive=False)
            raise NotificationError(
                f"email notification was not started: {_safe_error(exc)}; receipt={receipt_ref}",
                code="NOTIFICATION_DELIVERY_NOT_STARTED",
                error_class="delivery_not_started",
                state="failed",
                retry_disposition="retry_after_fix",
                receipt_ref=receipt_ref,
            ) from exc
        except _DeliveryAmbiguous as exc:
            diagnostic = _safe_error(exc)
            unknown = {
                **guard,
                "state": "unknown",
                "updated_at": _now(),
                "error_class": "delivery_ambiguous",
                "error": diagnostic,
            }
            _write_private_json(receipt_path, unknown, exclusive=False)
            raise NotificationError(
                f"email notification result is ambiguous: {diagnostic}; "
                f"do not retry automatically; receipt={receipt_ref}",
                code="NOTIFICATION_DELIVERY_AMBIGUOUS",
                error_class="delivery_ambiguous",
                state="unknown",
                retry_disposition="reconcile_only",
                receipt_ref=receipt_ref,
            ) from exc
        except Exception as exc:
            # Once transport was entered, an unclassified error is not proof
            # of non-delivery (including OSError/ValueError after DATA).
            diagnostic = _safe_error(exc)
            failed = {
                **guard,
                "state": "unknown" if transport_started else "failed",
                "updated_at": _now(),
                "error_class": "delivery_ambiguous" if transport_started else "delivery_not_started",
                "error": diagnostic,
            }
            _write_private_json(receipt_path, failed, exclusive=False)
            raise NotificationError(
                f"email notification failed: {diagnostic}; receipt={receipt_ref}",
                code="NOTIFICATION_DELIVERY_AMBIGUOUS" if transport_started else "NOTIFICATION_DELIVERY_NOT_STARTED",
                error_class=failed["error_class"],
                state=failed["state"],
                retry_disposition="reconcile_only" if transport_started else "retry_after_fix",
                receipt_ref=receipt_ref,
            ) from exc

        receipt = {
            **guard,
            "state": "sent",
            "sent_at": _now(),
            "provider_result_digest": sha256_json({"stdout": provider_output}),
        }
        _write_private_json(receipt_path, receipt, exclusive=False)
        return _delivery_result(
            state="sent",
            message_id=message_id,
            subject=subject,
            message_digest=message_digest,
            provider=config.provider,
            attachment_refs=attachment_refs,
            receipt_ref=receipt_ref,
            external_side_effects=True,
        )


def load_notification_config(path: str | Path | None = None) -> EmailConfig:
    source = _configured_path(path)
    try:
        with source.open("rb") as handle:
            raw = tomllib.load(handle)
    except tomllib.TOMLDecodeError as exc:
        raise ValueError(f"invalid notification configuration: {source}: {exc}") from exc
    if set(raw) != {"notifications"}:
        raise ValueError("notification configuration must contain only [notifications]")
    notifications = _mapping(raw.get("notifications"), "notifications")
    if set(notifications) != {"email"}:
        raise ValueError("notification configuration must contain only [notifications.email]")
    email = _mapping(notifications.get("email"), "notifications.email")
    email = _normalize_notification_provider(email)
    enabled = email.get("enabled")
    if not isinstance(enabled, bool):
        raise ValueError("notifications.email.enabled must be true or false")
    recipient = _email_address(email.get("recipient"))
    return _load_smtp_config(source, email, enabled=enabled, recipient=recipient)


def _normalize_notification_provider(email: dict[str, Any]) -> dict[str, Any]:
    """Read configs emitted with the short-lived installer-only binding key."""
    if "binding" not in email:
        return email
    if "provider" in email:
        raise ValueError("notifications.email cannot set both provider and binding")
    normalized = dict(email)
    normalized["provider"] = normalized.pop("binding")
    return normalized


def _load_smtp_config(
    source: Path,
    email: dict[str, Any],
    *,
    enabled: bool,
    recipient: str,
) -> EmailConfig:
    allowed = {
        "enabled",
        "provider",
        "preset",
        "recipient",
        "from_address",
        "username",
        "password_env",
        "password_file",
        "host",
        "port",
        "security",
    }
    _validate_config_fields(email, allowed, required={"provider", "preset", "username"})
    if email.get("provider") != "smtp":
        raise ValueError("invalid notifications.email configuration")
    preset = bounded_text(email.get("preset"), "notifications.email.preset", 32).lower()
    if preset not in SMTP_PRESETS:
        raise ValueError(
            "notifications.email.preset must be one of: "
            + ", ".join(sorted(SMTP_PRESETS))
        )
    defaults = SMTP_PRESETS[preset]
    host = bounded_text(email.get("host", defaults["host"]), "notifications.email.host", 255)
    if any(character.isspace() for character in host) or "/" in host or "@" in host:
        raise ValueError("notifications.email.host must be a hostname")
    if preset != "custom" and host != defaults["host"]:
        raise ValueError(f"notifications.email.host must be {defaults['host']} for preset {preset}")
    port = email.get("port", defaults["port"])
    if not isinstance(port, int) or isinstance(port, bool) or not 1 <= port <= 65535:
        raise ValueError("notifications.email.port must be an integer from 1 to 65535")
    security = bounded_text(
        email.get("security", defaults["security"]),
        "notifications.email.security",
        16,
    ).lower()
    if security not in SMTP_SECURITY:
        raise ValueError("notifications.email.security must be ssl or starttls")
    username = _email_address(email.get("username"))
    from_address = _email_address(email.get("from_address", username))
    password_env, password_file = _secret_source(email)
    canonical = {
        "schema_version": SMTP_CONFIG_SCHEMA,
        "email": {
            "enabled": enabled,
            "provider": "smtp",
            "preset": preset,
            "recipient": recipient,
            "from_address": from_address,
            "username": username,
            "host": host,
            "port": port,
            "security": security,
            "credential": {
                "env": password_env,
                "file": str(password_file) if password_file is not None else None,
            },
        },
    }
    return EmailNotificationConfig(
        source=source,
        enabled=enabled,
        recipient=recipient,
        provider="smtp",
        digest=sha256_json(canonical),
        from_address=from_address,
        smtp_preset=preset,
        smtp_host=host,
        smtp_port=port,
        smtp_security=security,
        smtp_username=username,
        smtp_password_env=password_env,
        smtp_password_file=password_file,
    )


def _validate_config_fields(
    value: dict[str, Any],
    allowed: set[str],
    *,
    required: set[str] | None = None,
) -> None:
    unknown = sorted(set(value) - allowed)
    missing = sorted((required or allowed) - set(value))
    if unknown or missing:
        details = []
        if unknown:
            details.append(f"unknown fields: {', '.join(unknown)}")
        if missing:
            details.append(f"missing fields: {', '.join(missing)}")
        raise ValueError(f"invalid notifications.email configuration ({'; '.join(details)})")


def _private_install_path(
    value: Any,
    label: str,
    *,
    must_exist: bool,
    directory: bool = True,
) -> Path:
    raw = bounded_text(value, label, 4096)
    path = Path(raw).expanduser()
    if not path.is_absolute() or path.is_symlink():
        raise ValueError(f"{label} must be an absolute non-symbolic-link path")
    try:
        resolved = path.resolve(strict=must_exist)
    except OSError as exc:
        raise ValueError(f"{label} is unavailable") from exc
    if must_exist and directory and not resolved.is_dir():
        raise ValueError(f"{label} must be a directory")
    return resolved


def _secret_source(email: dict[str, Any]) -> tuple[str | None, Path | None]:
    password_env = email.get("password_env")
    password_file_raw = email.get("password_file")
    if (password_env is None) == (password_file_raw is None):
        raise ValueError(
            "notifications.email must set exactly one of password_env or password_file"
        )
    if password_env is not None:
        name = bounded_text(password_env, "notifications.email.password_env", 128)
        if not ENV_NAME.fullmatch(name):
            raise ValueError("notifications.email.password_env must be an environment variable name")
        return name, None
    path = _private_install_path(
        password_file_raw,
        "notifications.email.password_file",
        must_exist=True,
        directory=False,
    )
    if not path.is_file():
        raise ValueError("notifications.email.password_file must be a regular file")
    if path.stat().st_mode & 0o077:
        raise ValueError("notifications.email.password_file must have mode 0600")
    return None, path


def _configured_path(path: str | Path | None) -> Path:
    raw = str(path) if path is not None else os.environ.get(CONFIG_ENV, "").strip()
    if not raw:
        raise ValueError(f"{CONFIG_ENV} is not configured")
    source = Path(raw).expanduser()
    if not source.is_absolute():
        raise ValueError(f"{CONFIG_ENV} must be an absolute path")
    if source.is_symlink() or not source.is_file():
        raise ValueError(f"{CONFIG_ENV} is not a regular file: {source}")
    if source.stat().st_mode & 0o077:
        raise ValueError(f"{CONFIG_ENV} must have mode 0600: {source}")
    return source.resolve(strict=True)


def _load_request(request_file: Path) -> dict[str, Any]:
    value = json.loads(request_file.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("email message must be an object")
    _validate_message(value)
    return value


def _validate_message(value: dict[str, Any]) -> None:
    allowed = {"schema_version", "message_id", "subject", "body", "attachments", "recipient", "metadata"}
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise ValueError(f"email message contains unknown fields: {', '.join(unknown)}")
    if value.get("schema_version") != REQUEST_SCHEMA:
        raise ValueError(f"email message schema_version must be {REQUEST_SCHEMA}")
    bounded_text(value.get("message_id"), "message_id", 256)
    bounded_text(value.get("subject"), "email subject", 300)
    bounded_content(value.get("body"), "email body", 20_000)
    metadata = value.get("metadata")
    if metadata is not None:
        if not isinstance(metadata, dict):
            raise ValueError("metadata must be an object")
        if len(json.dumps(metadata, ensure_ascii=False)) > 16_000:
            raise ValueError("metadata exceeds its safe limit")


def _resolve_attachments(
    workspace: Path,
    value: Any,
    *,
    prepared: bool,
) -> tuple[list[str], list[Path], list[dict[str, Any]]]:
    if not isinstance(value, list) or len(value) > 8:
        raise ValueError("attachments must be an array with at most 8 entries")
    refs: list[str] = []
    paths: list[Path] = []
    records: list[dict[str, Any]] = []
    for index, item in enumerate(value):
        if isinstance(item, str):
            item = {"ref": item}
        if not isinstance(item, dict):
            raise ValueError(f"attachments[{index}] must be an object")
        ref, path = workspace_path(workspace, item.get("ref"), must_exist=True)
        if ref in refs:
            raise ValueError("attachments contains duplicates")
        if not path.is_file() or path.is_symlink():
            raise ValueError(f"attachments[{index}] must select a regular file")
        digest = sha256_path(path)
        size = path.stat().st_size
        if prepared and (item.get("sha256") != digest or item.get("size_bytes") != size):
            raise ValueError("attachment no longer matches prepared message")
        refs.append(ref)
        paths.append(path)
        records.append({
            "ref": ref,
            "sha256": digest,
            "size_bytes": size,
        })
    return refs, paths, records


def _run_transport(
    config: EmailConfig,
    *,
    message_digest: str,
    recipient: str,
    subject: str,
    body: str,
    attachments: list[tuple[Path, dict[str, Any]]],
) -> str:
    if config.provider != "smtp":
        raise _DeliveryNotStarted(f"unsupported email provider: {config.provider}")
    return _run_smtp(
        config,
        message_digest=message_digest,
        recipient=recipient,
        subject=subject,
        body=body,
        attachments=attachments,
    )


def _run_smtp(
    config: EmailConfig,
    *,
    message_digest: str,
    recipient: str,
    subject: str,
    body: str,
    attachments: list[tuple[Path, dict[str, Any]]],
) -> str:
    if not config.smtp_host or not config.smtp_port or not config.smtp_security:
        raise _DeliveryNotStarted("SMTP configuration is incomplete")
    if "\r" in subject or "\n" in subject:
        raise _DeliveryNotStarted("SMTP subject must not contain line breaks")
    password = _smtp_password(config)
    message = EmailMessage()
    message["From"] = config.from_address or config.smtp_username or ""
    message["To"] = recipient
    message["Subject"] = subject
    message["Date"] = formatdate(localtime=True)
    message["Message-ID"] = (
        f"<coragent-{message_digest.removeprefix('sha256:')}"
        f"@{message['From'].split('@', 1)[-1]}>"
    )
    message["X-CoRAgent-Message-Digest"] = message_digest
    message.set_content(body)
    for source, record in attachments:
        try:
            payload = source.read_bytes()
        except OSError as exc:
            raise _DeliveryNotStarted(f"unable to read email attachment: {source.name}") from exc
        if sha256_path(source) != record.get("sha256") or len(payload) != record.get("size_bytes"):
            raise _DeliveryNotStarted(f"email attachment changed while composing: {source.name}")
        mime_type, _ = mimetypes.guess_type(source.name, strict=False)
        maintype, subtype = (mime_type or "application/octet-stream").split("/", 1)
        message.add_attachment(
            payload,
            maintype=maintype,
            subtype=subtype,
            filename=source.name,
        )

    client: smtplib.SMTP | smtplib.SMTP_SSL | None = None
    connected = False
    authenticated = False
    try:
        context = ssl.create_default_context()
        if config.smtp_security == "ssl":
            client = _smtp_client_class(ssl_enabled=True)(
                config.smtp_host,
                config.smtp_port,
                timeout=SMTP_CONNECT_TIMEOUT,
                context=context,
            )
        else:
            client = _smtp_client_class(ssl_enabled=False)(
                config.smtp_host,
                config.smtp_port,
                timeout=SMTP_CONNECT_TIMEOUT,
            )
            client.ehlo()
            client.starttls(context=context)
            client.ehlo()
        connected = True
        client.login(config.smtp_username, password)
        authenticated = True
        refused = client.send_message(message)
        if refused:
            raise _DeliveryNotStarted(
                "SMTP refused recipient(s): " + ", ".join(sorted(refused))
            )
        return "smtp message accepted"
    except _DeliveryNotStarted:
        raise
    except (smtplib.SMTPAuthenticationError, smtplib.SMTPRecipientsRefused) as exc:
        raise _DeliveryNotStarted(_smtp_exception_text(exc)) from exc
    except smtplib.SMTPResponseException as exc:
        raise _DeliveryNotStarted(_smtp_exception_text(exc)) from exc
    except (smtplib.SMTPServerDisconnected, TimeoutError, OSError) as exc:
        if connected and authenticated:
            raise _DeliveryAmbiguous(
                "SMTP connection ended before delivery was confirmed: "
                + _smtp_exception_text(exc)
            ) from exc
        raise _DeliveryNotStarted(_smtp_exception_text(exc)) from exc
    except smtplib.SMTPException as exc:
        if connected and authenticated:
            raise _DeliveryAmbiguous(_smtp_exception_text(exc)) from exc
        raise _DeliveryNotStarted(_smtp_exception_text(exc)) from exc
    finally:
        if client is not None:
            try:
                client.quit()
            except (OSError, smtplib.SMTPException):
                pass


def _smtp_client_class(*, ssl_enabled: bool) -> type[smtplib.SMTP]:
    """Return an SMTP client that resolves and connects over IPv4 only.

    ``smtplib`` delegates hostname resolution to ``socket.create_connection``.
    That helper follows the platform resolver order, which can leave a broken
    IPv6 route waiting for the full connect timeout before trying IPv4.  The
    dynamic subclass constrains the stdlib clients to AF_INET while TLS still
    receives the original hostname for certificate/SNI verification.  If
    callers inject a different SMTP class (as tests and embedders may), that
    class is returned unchanged so its construction contract is preserved.
    """

    base = smtplib.SMTP_SSL if ssl_enabled else smtplib.SMTP
    system_base = _SYSTEM_SMTP_SSL if ssl_enabled else _SYSTEM_SMTP
    if base is not system_base:
        return base
    if ssl_enabled:

        class IPv4SMTPSSL(base):  # type: ignore[misc,valid-type]
            def _get_socket(self, host: str, port: int, timeout: float | None):
                if self.debuglevel > 0:
                    self._print_debug("connect:", (host, port))
                plain_socket = _create_ipv4_connection(
                    host,
                    port,
                    timeout,
                    self.source_address,
                )
                try:
                    return self.context.wrap_socket(plain_socket, server_hostname=self._host)
                except BaseException:
                    plain_socket.close()
                    raise

        return IPv4SMTPSSL

    class IPv4SMTP(base):  # type: ignore[misc,valid-type]
        def _get_socket(self, host: str, port: int, timeout: float | None):
            if timeout is not None and not timeout:
                raise ValueError("Non-blocking socket (timeout=0) is not supported")
            if self.debuglevel > 0:
                self._print_debug("connect: to", (host, port), self.source_address)
            return _create_ipv4_connection(host, port, timeout, self.source_address)

    return IPv4SMTP


def _create_ipv4_connection(
    host: str,
    port: int,
    timeout: float | None,
    source_address: tuple[str, int] | None = None,
) -> socket.socket:
    """Connect to one of the host's IPv4 addresses within one total timeout.

    ``socket.create_connection`` retries every address with the full timeout.
    Keep the timeout bounded across all IPv4 candidates so a DNS response with
    several dead addresses cannot outlive the monitor worker's command limit.
    IPv6 answers are intentionally ignored; this is a deployment-level choice
    for SMTP because the supported installation environments may have no IPv6
    default route.
    """

    if timeout is not None and timeout <= 0:
        raise ValueError("Non-blocking socket (timeout=0) is not supported")
    deadline = time.monotonic() + timeout if timeout is not None else None
    addresses = socket.getaddrinfo(
        host,
        port,
        family=socket.AF_INET,
        type=socket.SOCK_STREAM,
        proto=socket.IPPROTO_TCP,
    )
    errors: list[OSError] = []
    for family, socktype, proto, _canonname, sockaddr in addresses:
        if family != socket.AF_INET:
            continue
        client_socket: socket.socket | None = None
        try:
            client_socket = socket.socket(family, socktype, proto)
            if timeout is not None:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("timed out while connecting to SMTP server")
                client_socket.settimeout(remaining)
            if source_address is not None:
                client_socket.bind(source_address)
            client_socket.connect(sockaddr)
            return client_socket
        except OSError as exc:
            errors.append(exc)
            if client_socket is not None:
                try:
                    client_socket.close()
                except OSError:
                    pass
    if errors:
        raise errors[-1]
    raise OSError(f"SMTP host {host!r} has no IPv4 address")


def _smtp_password(config: EmailConfig) -> str:
    if config.smtp_password_env is not None:
        value = os.environ.get(config.smtp_password_env, "")
    elif config.smtp_password_file is not None:
        try:
            value = config.smtp_password_file.read_text(encoding="utf-8")
        except OSError as exc:
            raise _DeliveryNotStarted("SMTP password file is unavailable") from exc
    else:
        raise _DeliveryNotStarted("SMTP password source is not configured")
    value = value.strip()
    if not value:
        raise _DeliveryNotStarted("SMTP password source is empty")
    return value


def _smtp_exception_text(exc: BaseException) -> str:
    if isinstance(exc, smtplib.SMTPResponseException):
        detail = exc.smtp_error.decode("utf-8", "replace") if isinstance(exc.smtp_error, bytes) else str(exc.smtp_error)
        detail = " ".join(detail.split())
        return f"SMTP server returned {exc.smtp_code}: {detail[:500]}"
    detail = " ".join(str(exc).split())
    return detail[:500] or exc.__class__.__name__


def _revalidate_email_inputs(
    workspace: Path,
    config: EmailConfig,
    attachment_records: list[dict[str, Any]],
) -> None:
    current_config = load_notification_config(config.source)
    if current_config.digest != config.digest:
        raise ValueError("notification configuration changed after preflight")
    for record in attachment_records:
        ref, path = workspace_path(workspace, record.get("ref"), must_exist=True)
        if sha256_path(path) != record.get("sha256") or path.stat().st_size != record.get("size_bytes"):
            raise ValueError(f"email attachment changed after preflight: {ref}")


def _existing_delivery_result(
    receipt_ref: str,
    receipt_path: Path,
    message_digest: str,
) -> dict[str, Any] | None:
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    if not isinstance(receipt, dict) or receipt.get("schema_version") != RECEIPT_SCHEMA:
        raise ValueError("existing email receipt is invalid")
    if receipt.get("message_digest") != message_digest:
        raise ValueError("existing email receipt does not match the message")
    state = receipt.get("state")
    if state == "failed" and receipt.get("error_class") in {
        "delivery_not_started",
    }:
        return None
    if state == "sending":
        # The exclusive delivery lock means the writer that created this
        # receipt has already exited.  A process can be killed by the Host
        # timeout or cancellation before it writes a terminal state; expose
        # that outcome as ambiguous instead of leaving callers stuck on
        # `sending` forever or blindly resending a possibly accepted message.
        diagnostic = "email process exited before delivery was confirmed"
        reconciled = {
            **receipt,
            "state": "unknown",
            "updated_at": _now(),
            "error_class": "delivery_ambiguous",
            "error": diagnostic,
        }
        _write_private_json(receipt_path, reconciled, exclusive=False)
        raise NotificationError(
            f"email delivery result is ambiguous: {diagnostic}; "
            f"do not retry automatically; receipt={receipt_ref}",
            code="NOTIFICATION_DELIVERY_AMBIGUOUS",
            error_class="delivery_ambiguous",
            state="unknown",
            retry_disposition="reconcile_only",
            receipt_ref=receipt_ref,
        )
    if state != "sent":
        raise ValueError(f"email delivery remains {state}; do not retry automatically; receipt={receipt_ref}")
    return _delivery_result(
        state="already_sent",
        message_id=str(receipt.get("message_id")),
        subject=str(receipt.get("subject")),
        message_digest=message_digest,
        provider=str(receipt.get("provider", "smtp")),
        attachment_refs=[
            str(record.get("ref"))
            for record in receipt.get("attachments", [])
            if isinstance(record, dict) and isinstance(record.get("ref"), str)
        ],
        receipt_ref=receipt_ref,
        external_side_effects=False,
    )


def _delivery_result(
    *,
    state: str,
    message_id: str,
    subject: str,
    message_digest: str,
    provider: str,
    attachment_refs: list[str],
    receipt_ref: str,
    external_side_effects: bool,
) -> dict[str, Any]:
    return {
        "ok": True,
        "operation": "send",
        "state": state,
        "message_id": message_id,
        "subject": subject,
        "provider": provider,
        "message_digest": message_digest,
        "attachment_refs": attachment_refs,
        "receipt_ref": receipt_ref,
        "artifact_refs": [*attachment_refs, receipt_ref],
        "external_side_effects": external_side_effects,
    }


def _mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a TOML table")
    return value


def _email_address(value: Any) -> str:
    address = bounded_text(value, "notifications.email.recipient", 320)
    if address.count("@") != 1 or any(character.isspace() for character in address):
        raise ValueError("notifications.email.recipient must be one email address")
    local, domain = address.split("@")
    if not local or "." not in domain or domain.startswith(".") or domain.endswith("."):
        raise ValueError("notifications.email.recipient must be one email address")
    return address


@contextmanager
def _delivery_lock(path: Path, *, touch=True):
    flags = os.O_RDWR | os.O_CREAT
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path.with_suffix(".lock"), flags, 0o600)
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise ValueError("email receipt must be a regular file")
        os.fchmod(descriptor, 0o600)
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        if touch: path.touch(exist_ok=True, mode=0o600)
        yield
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


def _write_private_json(path: Path, value: dict[str, Any], *, exclusive: bool) -> None:
    if exclusive and path.exists(): raise FileExistsError(path)
    payload = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")
    descriptor, temporary = tempfile.mkstemp(prefix=".receipt-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload); stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try: os.fsync(directory)
        finally: os.close(directory)
    finally:
        Path(temporary).unlink(missing_ok=True)


def _safe_error(exc: BaseException) -> str:
    return bounded_text(str(exc) or exc.__class__.__name__, "delivery error", 2000)


def _now() -> str:
    return datetime.now(UTC).astimezone().isoformat(timespec="seconds")
