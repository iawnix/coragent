"""Secure credential provisioning for installed CoRAgent services."""

from __future__ import annotations


from research_agent.bootstrap.layout import paths as app_paths

import json
import os
import re
import secrets
import stat
import tempfile
from pathlib import Path


TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9_-]{8,100}$")
TOKEN_BYTES = 32


def provision_service_credentials(
    install_root: Path,
    *,
    with_web: bool,
    web_token_path: Path | None = None,
    web_token_value: str | None = None,
) -> dict[str, dict[str, str]]:
    """Create missing service credentials and preserve valid existing values."""
    expanded_root = install_root.expanduser()
    if expanded_root.is_symlink():
        raise ValueError(f"installation root cannot be a symbolic link: {expanded_root}")
    root = expanded_root.resolve()
    specifications: list[tuple[str, Path]] = []
    if with_web:
        token = web_token_path.expanduser() if web_token_path is not None else app_paths(root).generated / 'web' / "auth.token"
        if not token.is_absolute():
            raise ValueError("CoRAgent Web token path must be an absolute path inside the local state directory")
        if token.is_symlink():
            raise ValueError(f"CoRAgent Web token path cannot be a symbolic link: {token}")
        if not any(parent in token.resolve().parents for parent in (app_paths(root).state, app_paths(root).generated)):
            raise ValueError("CoRAgent Web token path must be an absolute path inside the local state directory")
        specifications.append(("web_http", token.resolve()))
    if not specifications:
        return {}

    if web_token_value is not None:
        _validate_token_value(web_token_value)

    directories: list[Path] = []
    for _, path in specifications:
        for directory in (app_paths(root).generated, path.parent):
            if directory not in directories:
                directories.append(directory)
    for directory in directories:
        directory.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        _ensure_private_directory(directory)

    layout = app_paths(root)
    credentials = layout.configuration.credentials()
    canonical_token = credentials.get('secrets', {}).get('web_token')
    if web_token_value is not None:
        value, status = web_token_value, 'configured'
    elif canonical_token is not None:
        _validate_token_value(canonical_token)
        value, status = canonical_token, 'preserved'
    else:
        value, status = secrets.token_urlsafe(TOKEN_BYTES), 'created'
    credentials.setdefault('secrets', {})['web_token'] = value
    from research_agent.configuration.configuration import atomic_write
    atomic_write(layout.credentials, json.dumps(credentials, indent=2) + '\n')
    result = {}
    for name, path in specifications:
        _write_secret(path, value)
        result[name] = {'path': str(path), 'status': status, 'mode': '0600'}
    return result


def _ensure_private_directory(path: Path) -> None:
    created = False
    try:
        os.mkdir(path, 0o700)
        created = True
    except FileExistsError:
        pass
    info = os.lstat(path)
    if stat.S_ISLNK(info.st_mode):
        raise ValueError(f"credential directory cannot be a symbolic link: {path}")
    if not stat.S_ISDIR(info.st_mode):
        raise ValueError(f"credential path must be a directory: {path}")
    if info.st_uid != os.getuid() and os.geteuid() != 0:
        raise ValueError(f"credential directory must be owned by the installing user: {path}")
    if created and stat.S_IMODE(info.st_mode) != 0o700:
        os.chmod(path, 0o700, follow_symlinks=False)
        info = os.lstat(path)
    if stat.S_IMODE(info.st_mode) != 0o700:
        raise ValueError(f"credential directory must have mode 0700: {path}")


def _validate_secret_file(path: Path, info: os.stat_result) -> None:
    if not stat.S_ISREG(info.st_mode):
        raise ValueError(f"credential must be a regular file: {path}")
    if info.st_uid != os.getuid() and os.geteuid() != 0:
        raise ValueError(f"credential must be owned by the installing user: {path}")
    if info.st_nlink != 1:
        raise ValueError(f"credential must not have hard links: {path}")
    if stat.S_IMODE(info.st_mode) != 0o600:
        raise ValueError(f"credential must have mode 0600: {path}")


def _validate_token_value(value: str) -> None:
    if TOKEN_PATTERN.fullmatch(value) is None:
        raise ValueError("CoRAgent Web token must contain 8 to 100 URL-safe characters")


def _write_secret(path: Path, value: str) -> None:
    """Atomically install an explicitly selected token without following links."""
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        payload = f"{value}\n".encode("ascii")
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = -1
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        _validate_secret_file(path, os.stat(path))
    finally:
        if descriptor != -1:
            os.close(descriptor)
        temporary.unlink(missing_ok=True)
