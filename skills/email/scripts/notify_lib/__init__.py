"""Deterministic, installation-configured email delivery."""

from .delivery import (
    EmailConfig,
    load_notification_config,
    prepare_email,
    send_email,
    validate_email_message,
)
from .errors import NotificationError

__all__ = [
    "EmailConfig",
    "NotificationError",
    "load_notification_config",
    "prepare_email",
    "send_email",
    "validate_email_message",
]
