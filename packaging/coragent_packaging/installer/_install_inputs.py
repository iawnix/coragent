"""Private configuration directory inputs for the shared installer."""
from __future__ import annotations


from research_agent.bootstrap.layout import paths as app_paths

import argparse
import os
import stat
import tomllib
from pathlib import Path

def _regular_file(path: Path, label: str, *, private: bool = False) -> Path:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"{label} must be a regular file: {path}")
    if private and stat.S_IMODE(path.stat().st_mode) & 0o077:
        raise ValueError(f"{label} must be mode 0600: {path}")
    return path


def email_options(config: Path) -> list[str] | None:
    """Read explicit email settings without copying or printing credentials."""
    source = config / "email.toml"
    if not source.exists() and not source.is_symlink():
        return None
    _regular_file(source, "email.toml")
    try:
        document = tomllib.loads(source.read_text(encoding="utf-8"))
    except (UnicodeError, tomllib.TOMLDecodeError) as exc:
        raise ValueError("invalid email.toml") from exc
    notifications = document.get("notifications")
    email = notifications.get("email") if isinstance(notifications, dict) else None
    fields = {
        "provider": ("email_binding", "--email-binding"),
        "preset": ("email_preset", "--email-preset"),
        "host": ("email_host", "--email-host"),
        "port": ("email_port", "--email-port"),
        "security": ("email_security", "--email-security"),
        "recipient": ("email_recipient", "--email-recipient"),
        "username": ("email_username", "--email-address"),
        "password_file": ("email_password_file", "--email-password-file"),
        "password_env": ("email_password_env", "--email-password-env"),
    }
    if not isinstance(email, dict) or set(email) - {*fields, "enabled"}:
        raise ValueError("email.toml requires [notifications.email] with supported fields; store passwords separately")
    from research_agent.integrations.email_config import parse_notification_config
    email = parse_notification_config(document, base_dir=config)
    if not email['enabled']:
        return []
    command = []
    for key, (_, flag) in fields.items():
        if key not in email:
            continue
        value = email[key]
        command.extend([flag, str(value)])
    return command


def environment_defaults(parser: argparse.ArgumentParser, argv=None) -> None:
    """Environment variables are defaults; explicit CLI flags take precedence."""
    aliases = {
        "coragent_repo": "CORAGENT_INSTALL_REPO",
        "coragent_ref": "CORAGENT_INSTALL_REF",
        "relay_state_dir": "CORAGENT_LINK_RELAY_STATE_DIR",
        "relay_listen": "CORAGENT_LINK_RELAY_LISTEN",
        "relay_port": "CORAGENT_LINK_RELAY_PORT",
        "relay_service_scope": "CORAGENT_LINK_RELAY_SERVICE_SCOPE",
        "relay_service_user": "CORAGENT_LINK_RELAY_SERVICE_USER",
        "relay_enable_services": "CORAGENT_LINK_RELAY_ENABLE_SERVICES",
        "relay_start_services": "CORAGENT_LINK_RELAY_START_SERVICES",
    }
    defaults = {}
    for action in parser._actions:
        if action.dest in {"help", "source_root", "coragent_commit", "yes", "non_interactive", "dry_run", "json", "allow_dirty",
                           "job_config", "agent_config_dir", "config_dir", "name_resolver_config"}:
            continue
        name = aliases.get(action.dest, "CORAGENT_" + action.dest.upper())
        value = os.environ.get(name)
        if not value:
            continue
        if isinstance(action, (argparse._StoreTrueAction, argparse._StoreFalseAction)):
            if value.lower() not in {"1", "true", "yes", "on", "0", "false", "no", "off"}:
                parser.error(f"{name} must be a boolean")
            value = value.lower() in {"1", "true", "yes", "on"}
        elif isinstance(action, argparse._AppendAction):
            if any(token.split('=', 1)[0] in action.option_strings for token in (argv or [])):
                continue
            value = [part.strip() for part in value.split(',') if part.strip()]
        elif action.choices and value not in action.choices:
            parser.error(f"{name} must be one of {', '.join(action.choices)}")
        defaults[action.dest] = value
    parser.set_defaults(**defaults)


def apply_config_directory(args: argparse.Namespace) -> None:
    """Import optional private inputs without writing installation files."""
    if not args.config_dir:
        return
    config = Path(args.config_dir).expanduser()
    if config.is_symlink() or not config.is_dir():
        raise ValueError("--import-config must be a physical configuration directory")
    config = config.resolve()
    args.config_dir = str(config)
    for filename, attribute in (("job.toml", "job_config"), ("name-resolver.toml", "name_resolver_config")):
        source = config / filename
        if getattr(args, attribute) is None and (source.exists() or source.is_symlink()):
            setattr(args, attribute, str(_regular_file(source, filename)))
    if args.agent_config_dir is None:
        for filename in ("models.json", "auth.json"):
            source = config / filename
            if source.exists() or source.is_symlink():
                _regular_file(source, filename)
        args.agent_config_dir = str(config)
    values = email_options(config)
    if values is None:
        return
    if not values:
        if not any(option.startswith('email_') for option in args._explicit_options):
            from coragent_packaging.installer.install_wizard import _clear_email_options
            _clear_email_options(args)
            args.email_binding = None
            args._clear_email = True
            args.__dict__.pop('_email_password', None)
        return
    from coragent_packaging.installer.install_wizard import parse_args, validate_email_options
    configured = parse_args(["--non-interactive", *values], use_environment=False)
    explicit_password = args.email_password_file is not None or args.email_password_env is not None
    for attribute in ("email_binding", "email_preset", "email_host", "email_port", "email_security",
                      "email_recipient", "email_username", "email_password_file", "email_password_env"):
        if attribute in {"email_password_file", "email_password_env"} and explicit_password:
            continue
        if getattr(args, attribute) is None:
            setattr(args, attribute, getattr(configured, attribute))
    if not explicit_password and args.email_password_file:
        args._email_password_source = args.email_password_file
    if args.email_binding is None:
        raise ValueError("notifications.email.provider is required")
    validate_email_options(args)
