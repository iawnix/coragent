"""Bind installer options and runtime projections to the single operator config."""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
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
    if validate_credentials and "models" in document:
        layout.configuration.resolve_credentials(document["models"])
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


def commit_sections(root, **sections):
    """Publish explicit candidate sections, never infer them from generated files."""
    layout = paths(root)
    configuration = layout.configuration
    document = configuration.read(required=False)
    credentials = configuration.credentials()

    def preserve_references(current, original):
        if isinstance(original, str) and original.startswith('credential:'):
            secret = credentials.get('secrets', {}).get(original.removeprefix('credential:'))
            return original if current == secret else current
        if isinstance(current, dict) and isinstance(original, dict):
            return {key: preserve_references(item, original.get(key)) for key, item in current.items()}
        if isinstance(current, list) and isinstance(original, list):
            return [preserve_references(item, original[index] if index < len(original) else None)
                    for index, item in enumerate(current)]
        return current

    def redact(value, prefix):
        if isinstance(value, dict):
            for key, item in list(value.items()):
                name = prefix + '.' + key
                if isinstance(item, str) and key in {'apiKey', 'password', 'TRI_AUTH_TOKEN'}:
                    if not item.startswith('credential:'):
                        credentials.setdefault('secrets', {})[name] = item
                        value[key] = 'credential:' + name
                else:
                    redact(item, name)
        elif isinstance(value, list):
            for index, item in enumerate(value):
                redact(item, prefix + '.' + str(index))

    for name, candidate in sections.items():
        if candidate is None:
            document.pop(name, None)
            continue
        candidate = preserve_references(copy.deepcopy(candidate), document.get(name))
        redact(candidate, name)
        document[name] = candidate
    # InstallationMaintenance snapshots both files and restores them together
    # on failed publication. Credentials precede references to those credentials.
    atomic_write(layout.credentials, json.dumps(credentials, indent=2) + '\n')
    configuration.write(document)
    return layout


def publish(args):
    """Finalize explicit installation choices, then rebuild derived inputs."""
    layout = paths(args.install_root)
    document = layout.configuration.read()
    sections = {}
    if getattr(args, 'conda_root', None):
        sections['runtime'] = {**document.get('runtime', {}),
                               'conda_root': str(Path(args.conda_root).expanduser().resolve())}
    sections['phone'] = {'access': args.phone_access or 'disabled'}
    if args.link_url:
        sections['phone']['relay_url'] = args.link_url
    sections['web'] = {'enabled': bool(args.with_web), 'host': args.web_host,
                       'port': args.web_port or 8766, 'allow_remote': bool(args.allow_remote)}
    commit_sections(args.install_root, **sections).materialize(strict=True)
