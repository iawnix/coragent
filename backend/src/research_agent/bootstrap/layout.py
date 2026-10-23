"""Canonical software, configuration, local state and workspace layout."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
from research_agent.configuration.configuration import Configuration, atomic_write, toml_text

SCHEMA = 'coragent-installation/3'


def _dedicated(value, label):
    path = Path(value).expanduser()
    if not path.is_absolute(): raise ValueError(f'{label} must be absolute')
    resolved = path.resolve()
    if resolved in {Path('/'), Path.home().resolve(), Path.home().resolve().parent}:
        raise ValueError(f'{label} must be a dedicated directory')
    return resolved


class AppLayout:
    def __init__(self, root=None, *, config_file=None):
        selected = config_file or os.environ.get('CORAGENT_CONFIG')
        if root is None:
            initial = selected or Path.home() / 'soft/coragent/config/config.toml'
            # Discover existing split installations without changing their ownership.
            legacy = Path.home() / '.config/coragent/config.toml'
            if not selected and not Path(initial).exists() and legacy.exists():
                initial = legacy
                selected = str(legacy)
            root = Configuration(initial).read(required=False).get('paths', {}).get('software_root')
        self.root = _dedicated(root or Path.home() / 'soft/coragent', 'software root')
        for name in ('config', 'state', 'generated', 'jobs', 'backups'):
            if (self.root / name).is_symlink():
                raise ValueError(f'installation directory cannot be a symlink: {self.root / name}')
        self.locator = self.root / 'installation.json'
        locator = {}
        if self.locator.exists():
            if self.locator.is_symlink(): raise ValueError('installation locator cannot be a symlink')
            locator = json.loads(self.locator.read_text())
            if locator.get('schema_version') != SCHEMA or locator.get('install_root') != str(self.root):
                raise ValueError('unsupported installation layout; a fresh installation is required')
            if selected and str(Path(selected).expanduser().resolve()) != locator.get('config_file'):
                raise ValueError('configuration does not match installation ownership record')
            selected = locator['config_file']
        config_path = Path(selected or self.root / 'config/config.toml').expanduser().absolute()
        self.config_file = config_path.parent.resolve() / config_path.name
        self.configuration = Configuration(self.config_file)
        document = self.configuration.read(required=bool(locator))
        configured = document.get('paths', {})
        if root is None and configured.get('software_root'):
            self.root = _dedicated(configured['software_root'], 'software root')
            self.locator = self.root / 'installation.json'
        if configured.get('software_root') and _dedicated(configured['software_root'], 'software root') != self.root:
            raise ValueError('configuration software_root does not match installation')
        self._state = _dedicated(configured.get('state_root', self.root / 'state'), 'state root')
        self.workspace_root = _dedicated(configured.get('workspace_root', Path.home() / 'DATA/coragent/workspaces'), 'workspace root')
        roots = (self.root, self.config, self.state, self.workspace_root)
        for i, left in enumerate(roots):
            for right in roots[i+1:]:
                if left == self.root and right in (self.root / 'config', self.root / 'state'):
                    continue
                if left == right or left.is_relative_to(right) or right.is_relative_to(left):
                    raise ValueError('software, configuration, state and workspace roots must be separate dedicated directories')
        if locator and locator.get('state_root') != str(self.state):
            raise ValueError('state_root differs from installation ownership record; reinstall explicitly')

    @property
    def config(self): return self.config_file.parent.resolve()
    @property
    def marker(self): return self.state / 'installation/installation.json'
    @property
    def releases(self): return self.root / 'releases'
    @property
    def current(self): return self.root / 'current'
    @property
    def state(self): return self._state
    @property
    def generated(self): return self.data_root / 'generated'
    @property
    def data_root(self):
        # Preserve explicitly configured split layouts until an offline migration.
        return self.root if self.state == self.root / 'state' else self.state
    @property
    def jobs(self): return self.data_root / 'jobs'
    @property
    def backups(self): return self.data_root / 'backups'
    @property
    def install_state(self): return self.state / 'installation/install-state.json'
    @property
    def runtime_home(self): return self.state / 'installation/python'
    @property
    def host_state(self): return self.state / 'host'
    @property
    def sessions(self): return self.state / 'pi/sessions'
    @property
    def log(self): return self.state / 'logs'
    @property
    def cache(self): return self.state / 'cache'
    @property
    def pi_runtime(self): return self.root / 'runtimes/pi'
    @property
    def pi_config(self): return self.state / 'pi/agent'
    @property
    def job_config(self): return self.generated / 'job.toml'
    @property
    def email_config(self): return self.generated / 'email.toml'
    @property
    def resolver_config(self): return self.generated / 'name-resolver.toml'
    @property
    def remote_config(self): return self.generated / 'remote-host.json'
    @property
    def credentials(self): return self.configuration.credentials_path
    @property
    def guards(self):
        service = self.read_config().get('service') or {}
        base = service.get('runtime_dir') or str(Path(os.environ.get('XDG_RUNTIME_DIR', f'/run/user/{os.getuid()}')) / 'coragent')
        return Path(base) / self.identity / 'guards'
    @property
    def identity(self): return hashlib.sha256(os.fsencode(self.root)).hexdigest()[:16]

    def read_config(self):
        if self.marker.exists():
            if self.marker.is_symlink(): raise ValueError('installation record cannot be a symbolic link')
            value = json.loads(self.marker.read_text())
            if value.get('schema_version') != SCHEMA or value.get('install_root') != str(self.root):
                raise ValueError('unsupported or mismatched installation layout')
        else: value = {}
        document = self.configuration.read(required=False)
        value['workspace_root'] = str(self.workspace_root)
        value.pop('service', None)
        if 'service' in document: value['service'] = document['service']
        return value

    def update_config(self, **fields):
        self.initialize()
        value = self.read_config()
        if 'service' in fields:
            service = self.configuration.read().get('service', {})
            self.configuration.update(service={**service, **fields['service']})
        if 'workspace_root' in fields:
            doc = self.configuration.read()
            doc['paths']['workspace_root'] = fields['workspace_root']
            self.configuration.write(doc)
        value.update(fields)
        atomic_write(self.marker, json.dumps(value, indent=2)+'\n')
        return self.marker

    @property
    def env_root(self):
        configured = self.configuration.read(required=False).get('runtime', {}).get('env_root')
        value = _dedicated(configured or os.environ.get('CORAGENT_HOST_ENV_ROOT', self.root / 'host-envs'), 'Host environment store')
        if value == self.root or self.root.is_relative_to(value):
            raise ValueError('Host environment store must be a dedicated directory')
        for protected in (self.config, self.state, self.generated, self.jobs, self.backups, self.workspace_root):
            if value == protected or value.is_relative_to(protected) or protected.is_relative_to(value):
                raise ValueError('Host environment store must be separate from configuration, state and workspaces')
        return value

    def initialize(self):
        if any((self.root / name).exists() or (self.root / name).is_symlink() for name in ('.pi', '.agents', 'etc', 'var')):
            raise ValueError('old installation layout is unsupported; use a fresh installation directory')
        for directory in (self.root, self.config, self.state, self.state/'installation', self.runtime_home,
                          self.host_state, self.sessions, self.log, self.cache, self.pi_runtime, self.pi_config,
                          self.generated/'secrets', self.jobs, self.backups):
            anchor = next(base for base in (self.root, self.config, self.state) if directory.is_relative_to(base))
            current = anchor
            for part in ('', *directory.relative_to(anchor).parts):
                current = current / part
                if current.is_symlink(): raise ValueError(f'installation directory cannot be a symlink: {current}')
                current.mkdir(mode=0o700, parents=True, exist_ok=True)
                current.chmod(0o700)
        document = self.configuration.read(required=False)
        document['paths'] = {'software_root': str(self.root), 'state_root': str(self.state), 'workspace_root': str(self.workspace_root)}
        self.configuration.write(document)
        locator = {'schema_version': SCHEMA, 'install_root': str(self.root), 'config_file': str(self.config_file), 'state_root': str(self.state)}
        atomic_write(self.locator, json.dumps(locator, indent=2)+'\n')
        if not self.marker.exists():
            atomic_write(self.marker, json.dumps({**locator, 'installation_id': self.identity, 'env_root': str(self.env_root), 'workspace_root': str(self.workspace_root)}, indent=2)+'\n')
        if not self.credentials.exists(): atomic_write(self.credentials, '{"models": {}, "secrets": {}}\n')
        return self

    def materialize(self, *, strict=False):
        """Build disposable inputs from the operator document in one direction.

        Optional component errors do not prevent reading the research workspace.
        Installation uses strict mode before activation; runtime diagnostics keep
        the component error explicit without retaining an obsolete projection.
        """
        from research_agent.integrations.email_config import project_notification_config
        document = self.configuration.read()
        # Environment passwords belong to the caller or service environment;
        # a previous generated capture must never become a second secret source.
        projections = {self.generated / 'secrets/service.env': None}
        status = {}
        secret_path = self.generated / 'secrets/smtp-password'
        for component, section, target in (
                ('execution', 'execution', self.job_config),
                ('name_resolver', 'name_resolver', self.resolver_config),
                ('email', 'notifications', self.email_config)):
            if section not in document:
                projections[target] = None
                status[component] = {'state': 'not_configured'}
                if component == 'email':
                    projections[secret_path] = None
                continue
            try:
                raw = document[section]
                if component == 'email':
                    # Disabled email never reads a password reference.
                    from research_agent.integrations.email_config import parse_notification_config
                    parsed = parse_notification_config({'notifications': raw}, base_dir=self.config)
                    resolved = self.configuration.resolve_credentials({'email': parsed})
                    value, password = project_notification_config({'notifications': resolved}, password_path=secret_path)
                    projections[secret_path] = password + '\n' if password is not None else None
                    state = 'configured' if parsed['enabled'] else 'disabled'
                else:
                    resolved = self.configuration.resolve_credentials(raw)
                    value = {'execution': resolved} if component == 'execution' else resolved
                    if component == 'execution':
                        from research_agent.jobs.config_contract import validate_job_config
                        validate_job_config(value)
                    else:
                        from .name_resolver_config import parse_config
                        parse_config(value)
                    state = 'configured'
                projections[target] = toml_text(value)
                status[component] = {'state': state}
            except ValueError as error:
                if strict:
                    raise ValueError(f'{component} configuration is invalid: {error}') from error
                projections[target] = None
                if component == 'email':
                    projections[secret_path] = None
                status[component] = {'state': 'invalid',
                    'error': f'{component} configuration is invalid; check config.toml and its credential references'}
        # Core model configuration remains a startup requirement when present.
        models = document.get('models')
        projections[self.pi_config / 'models.json'] = (json.dumps(self.configuration.resolve_credentials(models), indent=2)
                                                       + '\n' if models is not None else None)
        remote = document.get('remote_host')
        projections[self.remote_config] = json.dumps(remote, indent=2) + '\n' if remote is not None else None
        web_token = self.configuration.credentials().get('secrets', {}).get('web_token')
        projections[self.generated / 'web/auth.token'] = web_token + '\n' if web_token else None
        for target, content in projections.items():
            if content is None:
                target.unlink(missing_ok=True)
            else:
                atomic_write(target, content)
        atomic_write(self.generated / 'configuration-status.json', json.dumps(status, indent=2) + '\n')
        return self


def paths(root=None, *, config_file=None): return AppLayout(root, config_file=config_file)


def inspect_installation(root):
    findings=[]; release=None
    try:
        layout=paths(root)
        if not layout.marker.is_file(): raise ValueError('installation configuration is missing')
        layout.read_config()
        selected=layout.current.resolve(strict=True)
        if selected.parent != layout.releases: raise ValueError('current must select one direct release')
        release=selected.name
        state=json.loads(layout.install_state.read_text())
        if state.get('current_release_id')!=release or state.get('package_root')!=str(selected):
            raise ValueError('current and installation receipt disagree')
    except (OSError,ValueError,RuntimeError) as error: findings.append({'code':'invalid_layout','message':str(error)})
    return {'schema_version':SCHEMA,'root':str(root),'layout':'standalone','ok':not findings,'release_id':release,'findings':findings}
