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


def _thinking_levels(value, *, encode):
    """TOML false represents Pi's null (unsupported) thinking level."""
    if isinstance(value, list):
        return [_thinking_levels(item, encode=encode) for item in value]
    if not isinstance(value, dict):
        return value
    result = {}
    for key, item in value.items():
        if key == 'thinkingLevelMap' and isinstance(item, dict):
            result[key] = {level: (False if mapped is None else mapped) if encode
                           else (None if mapped is False else mapped)
                           for level, mapped in item.items()}
        else:
            result[key] = _thinking_levels(item, encode=encode)
    return result


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
        if 'models' in value:
            value['models'] = _thinking_levels(value['models'], encode=False)
        return value

    def write(self, value):
        if 'models' in value:
            value = {**value, 'models': _thinking_levels(value['models'], encode=True)}
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
