"""Bind installer options and runtime projections to the single operator config."""
from __future__ import annotations

import json
import os
from pathlib import Path
import tomllib
from research_agent.bootstrap.layout import paths, Configuration, atomic_write


def apply(args, *, validate_credentials=True):
    selected = getattr(args, 'config', None) or os.environ.get('CORAGENT_CONFIG')
    if selected:
        selected = str(Path(selected).expanduser().absolute())
        os.environ['CORAGENT_CONFIG'] = selected
    layout = paths(getattr(args, 'install_root', None), config_file=selected)
    args.config = str(layout.config_file)
    args.install_root = str(layout.root)
    os.environ['CORAGENT_CONFIG'] = args.config
    document = layout.configuration.read(required=False)
    if validate_credentials:
        layout.configuration.resolve_credentials(document)
    if hasattr(args, 'workspace_root') and not args.workspace_root: args.workspace_root = str(layout.workspace_root)
    service = document.get('service', {})
    for key, option in {'scope':'service_scope', 'user':'service_user'}.items():
        if key in service and hasattr(args, option) and getattr(args, option) in (None, 'auto'):
            setattr(args, option, service[key])
    web = document.get('web', {})
    for key, option in {'enabled':'with_web', 'port':'web_port', 'host':'web_host', 'allow_remote':'allow_remote'}.items():
        if key in web and hasattr(args, option) and option not in getattr(args, '_explicit_options', set()):
            if key != 'port' or getattr(args, 'with_web', True) is not False: setattr(args, option, web[key])
    for key, option in {'access':'phone_access', 'relay_url':'link_url'}.items():
        if key in document.get('phone', {}) and hasattr(args, option) and getattr(args, option) is None:
            setattr(args, option, document['phone'][key])
    if hasattr(args, 'conda_root') and args.conda_root is None:
        args.conda_root = document.get('runtime', {}).get('conda_root')
    remote = document.get('remote_host', {})
    for key, option in {'ssh_host':'remote_host', 'host_socket':'remote_host_socket', 'proxy_path':'remote_proxy_path', 'ssh_config':'ssh_config', 'ssh_options':'ssh_option'}.items():
        if key in remote and hasattr(args, option) and getattr(args, option) is None: setattr(args, option, remote[key])
    if getattr(args, 'job_profile', None):
        raise ValueError('prepare scientific environments separately with install_job_environment.py, then bind them in config.toml')
    # Component inputs are generated only after the installer has entered its
    # maintenance boundary. Preview and validation read the document directly.
    return layout


def prepare(args):
    layout = paths(args.install_root).initialize()
    return layout


def publish(args):
    """Commit explicit installer changes to the authoritative config before activation."""
    layout = paths(args.install_root)
    configuration = layout.configuration
    document = configuration.read()
    for section, path in (('execution', layout.job_config), ('name_resolver', layout.resolver_config)):
        # Persist validated bindings while keeping the operator's credential references.
        if path.is_file():
            value = tomllib.loads(path.read_text())
            if section == 'execution':
                value = value['execution']
            # Preserve operator credential references across normalization.
            def references(current, original):
                if isinstance(original, str) and original.startswith('credential:'):
                    return original if current == configuration.resolve_credentials(original) else current
                if isinstance(current, dict) and isinstance(original, dict):
                    return {key: references(item, original.get(key)) for key, item in current.items()}
                if isinstance(current, list) and isinstance(original, list):
                    return [references(item, original[index] if index < len(original) else None)
                            for index, item in enumerate(current)]
                return current
            document[section] = references(value, document.get(section))
    credentials = configuration.credentials()
    auth = layout.pi_config / 'auth.json'
    if auth.exists():
        credentials['models'] = {**json.loads(auth.read_text()), **credentials.get('models', {})}
        auth.unlink()
    models = layout.pi_config / 'models.json'
    if 'models' not in document and models.exists(): document['models'] = json.loads(models.read_text())
    if layout.email_config.exists() and (getattr(args, 'email_binding', None) or 'notifications' not in document):
        document['notifications'] = tomllib.loads(layout.email_config.read_text())['notifications']
    if getattr(args, '_clear_email', False): document['notifications'] = {'email': {'enabled': False}}
    # Imported inline secrets move to credentials.json; references are stable.
    def redact(value, prefix):
        if isinstance(value, dict):
            for key, item in list(value.items()):
                name = prefix + '.' + key
                if isinstance(item, str) and (key in {'apiKey', 'password', 'TRI_AUTH_TOKEN'}):
                    if not item.startswith('credential:'):
                        credentials.setdefault('secrets', {})[name] = item
                        value[key] = 'credential:' + name
                else: redact(item, name)
        elif isinstance(value, list):
            for index, item in enumerate(value): redact(item, prefix + '.' + str(index))
    for name in ('models', 'execution', 'notifications'):
        if name in document: redact(document[name], name)
    email = document.get('notifications', {}).get('email', {})
    generated_password = layout.generated / 'secrets/smtp-password'
    if email.get('password_file') == str(generated_password) and generated_password.exists():
        credentials.setdefault('secrets', {})['smtp_password'] = generated_password.read_text().rstrip('\n')
        email.pop('password_file')
        email['password'] = 'credential:smtp_password'
    if layout.remote_config.exists(): document['remote_host'] = json.loads(layout.remote_config.read_text())
    if getattr(args, 'conda_root', None):
        document.setdefault('runtime', {})['conda_root'] = str(Path(args.conda_root).expanduser().resolve())
    document['phone'] = {'access': args.phone_access or 'disabled'}
    if args.link_url: document['phone']['relay_url'] = args.link_url
    document['web'] = {'enabled': bool(args.with_web), 'host': args.web_host, 'port': args.web_port or 8766, 'allow_remote': bool(args.allow_remote)}
    token = layout.generated / 'web/auth.token'
    if token.is_file(): credentials.setdefault('secrets', {})['web_token'] = token.read_text().strip()
    configuration.write(document)
    atomic_write(layout.credentials, json.dumps(credentials, indent=2)+'\n')
    layout.materialize()
