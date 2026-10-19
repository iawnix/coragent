"""The operator-owned configuration; stdlib only so installation can use it."""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import tempfile
import tomllib

SCHEMA = 1
SECTIONS = {'schema_version', 'paths', 'service', 'models', 'execution', 'notifications',
            'name_resolver', 'web', 'remote_host', 'phone', 'runtime'}


def atomic_write(path: Path, content: str | bytes):
    if path.is_symlink():
        raise ValueError(f'configuration cannot be a symbolic link: {path}')
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor, name = tempfile.mkstemp(prefix='.' + path.name + '.', dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(content.encode() if isinstance(content, str) else content)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def toml_text(document):
    """Encode JSON-shaped configuration, including inline tables in arrays."""
    def value(item):
        if isinstance(item, str): return json.dumps(item, ensure_ascii=True)
        if isinstance(item, bool): return str(item).lower()
        if isinstance(item, (int, float)): return repr(item)
        if isinstance(item, list): return '[' + ', '.join(value(v) for v in item) + ']'
        if isinstance(item, dict):
            return '{' + ', '.join(json.dumps(k) + ' = ' + value(v) for k, v in item.items()) + '}'
        raise ValueError('configuration values must be strings, numbers, booleans, arrays or tables')
    lines = []
    def table(keys, obj):
        if keys: lines.append('[' + '.'.join(json.dumps(k) for k in keys) + ']')
        for key, item in obj.items():
            if item is not None and not isinstance(item, dict): lines.append(json.dumps(key) + ' = ' + value(item))
        for key, item in obj.items():
            if isinstance(item, dict):
                lines.append('')
                table([*keys, key], item)
    table([], document)
    return '\n'.join(lines) + '\n'


class Configuration:
    def __init__(self, path):
        self.path = Path(path).expanduser().absolute()
        if self.path.is_symlink(): raise ValueError('configuration must be a regular file')

    @property
    def credentials_path(self): return self.path.parent / 'credentials.json'

    def read(self, *, required=True):
        if not self.path.exists():
            if required: raise ValueError(f'configuration is missing: {self.path}')
            return {'schema_version': SCHEMA}
        try:
            value = tomllib.loads(self.path.read_text())
        except tomllib.TOMLDecodeError as exc:
            raise ValueError(f'invalid configuration: {self.path}') from exc
        if value.get('schema_version') != SCHEMA or set(value) - SECTIONS:
            raise ValueError('unsupported configuration schema or section')
        for key in set(value) - {'schema_version'}:
            if not isinstance(value[key], dict): raise ValueError(f'{key} must be a table')
        path_keys = set(value.get('paths', {}))
        if path_keys - {'software_root', 'state_root', 'workspace_root'}:
            raise ValueError('unsupported paths setting')
        for name, path in value.get('paths', {}).items():
            if not isinstance(path, str) or not Path(path).expanduser().is_absolute():
                raise ValueError(f'paths.{name} must be absolute')
        validate_settings(value)
        return value

    def write(self, value):
        atomic_write(self.path, toml_text(value))

    def update(self, **sections):
        document = self.read(required=False)
        document.update(sections)
        self.write(document)

    def credentials(self):
        path = self.credentials_path
        if not path.exists(): return {'models': {}, 'secrets': {}}
        if path.is_symlink() or path.stat().st_mode & 0o077:
            raise ValueError('credentials.json must be a private regular file (0600)')
        value = json.loads(path.read_text())
        if not isinstance(value, dict) or set(value) - {'models', 'secrets'}:
            raise ValueError('invalid credentials.json structure')
        if 'models' not in value or any(not isinstance(v, dict) for v in value.values()):
            raise ValueError('credentials sections must be objects')
        return value

    def resolve_credentials(self, value):
        """Resolve explicit credential references only in generated runtime files."""
        secrets = self.credentials().get('secrets', {})
        def resolve(item):
            if isinstance(item, dict): return {key: resolve(v) for key, v in item.items()}
            if isinstance(item, list): return [resolve(v) for v in item]
            if isinstance(item, str) and item.startswith('credential:'):
                key = item.removeprefix('credential:')
                if key not in secrets or not isinstance(secrets[key], str):
                    raise ValueError(f'missing credential reference: {key}')
                return secrets[key]
            return item
        return resolve(copy.deepcopy(value))


def validate_settings(document):
    """Reject malformed operator settings before any installation mutation."""
    fields = {
        'service': {'scope', 'user', 'runtime_dir', 'schema_version'},
        'web': {'enabled', 'host', 'port', 'allow_remote'},
        'runtime': {'env_root', 'conda_root'},
        'phone': {'access', 'relay_url'},
        'execution': {'default_target', 'targets'},
        'notifications': {'email'},
    }
    for section, allowed in fields.items():
        if set(document.get(section, {})) - allowed:
            raise ValueError(f'unsupported {section} setting')
    if document.get('service', {}).get('scope', 'user') not in {'none', 'user', 'system'}:
        raise ValueError('service.scope must be none, user or system')
    for section, keys in {'web': ('enabled', 'allow_remote')}.items():
        for key in keys:
            if key in document.get(section, {}) and type(document[section][key]) is not bool:
                raise ValueError(f'{section}.{key} must be a boolean')
    if 'notifications' not in document: return
    email = document['notifications'].get('email')
    allowed = {'enabled', 'provider', 'preset', 'host', 'port', 'security', 'recipient',
               'username', 'from_address', 'password', 'password_env', 'password_file'}
    if not isinstance(email, dict) or set(email) - allowed:
        raise ValueError('notifications.email requires supported SMTP settings')
    if type(email.get('enabled', True)) is not bool:
        raise ValueError('notifications.email.enabled must be a boolean')
    if email.get('enabled') is False: return
    if email.get('provider') != 'smtp' or email.get('preset') not in {'163', 'qq', 'custom'}:
        raise ValueError('notifications.email requires provider=smtp and a supported preset')
    for field in ('username', 'recipient'):
        value = email.get(field)
        if not isinstance(value, str) or value.count('@') != 1 or any(c.isspace() for c in value):
            raise ValueError(f'notifications.email.{field} must be an email address')
    if email['preset'] == 'custom' and not isinstance(email.get('host'), str):
        raise ValueError('notifications.email.host is required for custom SMTP')
    port = email.get('port', 465)
    if type(port) is not int or not 1 <= port <= 65535:
        raise ValueError('notifications.email.port must be an integer between 1 and 65535')
    if email.get('security', 'ssl') not in {'ssl', 'starttls'}:
        raise ValueError('notifications.email.security must be ssl or starttls')
    selected = [key for key in ('password', 'password_file', 'password_env') if key in email]
    if len(selected) != 1 or not isinstance(email[selected[0]], str) or not email[selected[0]]:
        raise ValueError('notifications.email requires exactly one password source')
