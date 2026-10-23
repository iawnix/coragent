"""Owned queue lifecycle with deterministic service management; no SSH or user units."""
import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from research_agent.jobs import qrun
from coragent_packaging.installer import _qrun_install as installer
from tests.unit.test_qrun import Runtime, request

REPO = Path(__file__).resolve().parents[2]


@pytest.fixture
def managed(tmp_path, monkeypatch):
    monkeypatch.setenv('XDG_CONFIG_HOME', str(tmp_path / 'config'))
    root = tmp_path / 'pool'
    runtime = Runtime(root)
    state = {'active': False, 'enabled': False, 'calls': []}
    monkeypatch.setattr(qrun, 'Systemd', lambda _root: runtime)
    monkeypatch.setattr(qrun, 'check_service_manager', lambda _root: None)

    def command(_root, *argv):
        state['calls'].append(argv)
        if argv[0] == 'show':
            return ('ActiveState=' + ('active' if state['active'] else 'inactive') +
                    '\nUnitFileState=' + ('enabled' if state['enabled'] else 'disabled'))
        if argv[0] in {'start', 'stop'}:
            state['active'] = argv[0] == 'start'
        if argv[0] in {'enable', 'disable'}:
            state['enabled'] = argv[0] == 'enable'
        return ''

    def activate(root, record):
        command(root, 'enable', record['unit'])
        command(root, 'start', record['unit'])

    monkeypatch.setattr(qrun, 'service_command', command)
    monkeypatch.setattr(qrun, 'activate', activate)
    value = {'owner': installer.owner(tmp_path / 'app'), 'operation': 'install', 'start': True,
             'cpus': 2, 'memory_mb': 1024, 'work_roots': [str(tmp_path / 'work')]}
    return root, value, runtime, state


def perform(managed, operation, **values):
    root, request, _, _ = managed
    return qrun.maintain(root, {**request, 'operation': operation, **values})


def test_install_upgrade_uses_stable_handler_and_preserves_history(managed):
    root, value, runtime, state = managed
    first = perform(managed, 'install')
    perform(managed, 'commit')
    queue = qrun.Queue(root)
    work = Path(value['work_roots'][0])
    req = request(work, cpus=1, memory=128)
    queue.handle(req)
    queue.handle({**req, 'action': 'cancel'})
    queue.close()
    second = perform(managed, 'install', cpus=4)
    assert first['handler'] == second['handler']
    assert json.loads((root / 'config.json').read_text())['cpus'] == 4
    queue = qrun.Queue(root)
    try:
        assert queue.rows()[0]['state'] == 'cancelled'
    finally:
        queue.close()
    assert state['active'] and state['enabled']
    perform(managed, 'commit')
    assert not (root / 'maintenance-snapshot.json').exists()


def test_upgrade_preserves_live_budget_unless_explicitly_overridden(managed):
    root, _, _, _ = managed
    perform(managed, 'install')
    perform(managed, 'commit')
    queue = qrun.Queue(root)
    try:
        queue.handle({'schema_version': qrun.PROTOCOL, 'action': 'configure', 'cpus': 3, 'memory_mb': 2048})
    finally:
        queue.close()
    result = perform(managed, 'install', capacity_overrides=[])
    assert result['capacity'] == {'cpus': 3, 'memory_mb': 2048}
    perform(managed, 'commit')
    result = perform(managed, 'install', cpus=4, capacity_overrides=['cpus'])
    assert result['capacity'] == {'cpus': 4, 'memory_mb': 2048}
    perform(managed, 'commit')


@pytest.mark.parametrize('operation', ['install', 'remove'])
def test_unfinished_jobs_block_upgrade_and_default_removal(managed, operation):
    root, value, runtime, state = managed
    perform(managed, 'install')
    perform(managed, 'commit')
    queue = qrun.Queue(root)
    queue.handle(request(Path(value['work_roots'][0]), cpus=1, memory=128))
    queue.close()
    with pytest.raises(ValueError, match='unfinished jobs'):
        perform(managed, operation)
    assert state['active'] and state['enabled']
    assert runtime.starts == runtime.stops == []
    assert perform(managed, 'restore') == {'restored': False}


@pytest.mark.parametrize('running', [False, True])
def test_explicit_cancellation_then_removal_retains_work_and_optional_history(managed, running):
    root, value, runtime, state = managed
    record = perform(managed, 'install')
    perform(managed, 'commit')
    work = Path(value['work_roots'][0])
    queue = qrun.Queue(root)
    queue.handle(request(work, cpus=1, memory=128))
    if running:
        queue.tick()
    queue.close()
    result = perform(managed, 'remove', cancel_jobs=True)
    assert result['state_retained'] and root.exists() and work.exists()
    assert not Path(record['unit_path']).exists()
    assert not state['active'] and not state['enabled']
    queue = qrun.Queue(root)
    try:
        assert queue.rows()[0]['state'] == 'cancelled'
        assert queue.rows()[0]['cleaned']
    finally:
        queue.close()
    perform(managed, 'remove', purge=True)
    assert not root.exists() and (work / 'first/run.sh').exists()
    assert perform(managed, 'remove', purge=True)['removed']
    assert not root.exists()


@pytest.mark.parametrize('tamper', ['owner', 'unit', 'symlink'])
def test_unowned_or_modified_service_is_not_stopped(managed, tamper):
    root, value, _, state = managed
    record = perform(managed, 'install')
    state['calls'].clear()
    if tamper == 'owner':
        value['owner'] = 'coragent-' + '0' * 64
    elif tamper == 'unit':
        Path(record['unit_path']).write_text('someone else owns this unit')
    else:
        manifest = root / 'installation.json'
        manifest.rename(root / 'original.json')
        manifest.symlink_to(root / 'original.json')
    with pytest.raises(ValueError):
        perform(managed, 'remove', purge=True, cancel_jobs=True)
    assert state['calls'] == []
    assert root.exists()


@pytest.mark.parametrize('upgrade', [False, True])
def test_activation_failure_restores_service_and_capacity(managed, monkeypatch, upgrade):
    root, _, _, state = managed
    if upgrade:
        first = perform(managed, 'install')
        perform(managed, 'commit')

    def failed(*_args):
        state.update(active=True, enabled=True)
        raise RuntimeError('fixture activation failed after starting')

    monkeypatch.setattr(qrun, 'activate', failed)
    with pytest.raises(RuntimeError, match='fixture activation failed'):
        perform(managed, 'install', cpus=4)
    assert state['active'] == state['enabled'] == upgrade
    if upgrade:
        assert json.loads((root / 'config.json').read_text())['cpus'] == 2
        assert json.loads((root / 'installation.json').read_text()) == {k: v for k, v in first.items() if k not in {'snapshot', 'capacity'}}
        assert Path(first['unit_path']).exists()
    else:
        assert json.loads((root / 'installation.json').read_text())['removed']
    assert not (root / 'maintenance-snapshot.json').exists()


def test_restore_returns_to_old_capacity_and_is_idempotent(managed):
    root, _, _, state = managed
    first = perform(managed, 'install')
    perform(managed, 'commit')
    perform(managed, 'install', cpus=3)
    perform(managed, 'restore', cancel_jobs=True)
    assert json.loads((root / 'config.json').read_text())['cpus'] == 2
    assert state['active'] and state['enabled']
    assert perform(managed, 'restore') == {'restored': False}
    assert Path(first['unit_path']).exists()


def args(tmp_path, **overrides):
    return SimpleNamespace(install_root=str(tmp_path / 'app'), service_scope='none', **overrides)


def target(tmp_path, **overrides):
    return {'transport': 'local', 'executor': 'qrun', 'handler': ['qrun', 'handler'],
            'work_root': str(tmp_path / 'work'), **overrides}


def test_plan_shares_local_pool_and_never_creates_files(tmp_path):
    settings = {'targets': {'one': target(tmp_path, connect_timeout_seconds=10),
                            'two': target(tmp_path, connect_timeout_seconds=30)}}
    planned = installer.plan(args(tmp_path, qrun_cpus=['two=4']), settings)
    assert len(planned) == 1 and planned[0]['targets'] == ['one', 'two']
    assert planned[0]['cpus'] == 4
    assert planned[0]['capacity_overrides'] == ['cpus']
    assert not (tmp_path / 'app').exists()


def test_custom_handlers_and_remote_pools_are_not_adopted_implicitly(tmp_path):
    settings = {'targets': {'custom': target(tmp_path, handler=['/opt/qrun']),
                            'remote': target(tmp_path, transport='ssh', ssh_host='fixture')}}
    assert installer.plan(args(tmp_path), settings) == []
    with pytest.raises(ValueError, match='separately managed'):
        installer.plan(args(tmp_path, manage_qrun=['custom']), settings)
    with pytest.raises(ValueError, match='new managed SSH'):
        installer.plan(args(tmp_path, manage_qrun=['remote']), settings)
    planned = installer.plan(args(tmp_path, manage_qrun=['remote'], qrun_state_dir=['remote=/queue'],
        qrun_cpus=['remote=8'], qrun_memory_mb=['remote=4096']), settings)
    assert len(planned) == 1 and planned[0]['route']['ssh_host'] == 'fixture'


def transaction(tmp_path, **extra):
    options = args(tmp_path, **extra)
    settings = {'targets': {'local/main': target(tmp_path)}}
    value = {'install_root': options.install_root, 'settings': settings,
             'qrun': installer.plan(options, settings)}
    return options, value


@pytest.mark.parametrize(('before', 'after'), [
    (None, '/fixture/ssh-config'),
    ('/fixture/old-config', '/fixture/ssh-config'),
    ('/fixture/ssh-config', None),
])
def test_ssh_configuration_update_keeps_one_owned_pool_and_updates_maintenance(tmp_path, monkeypatch, before, after):
    options = args(tmp_path, manage_qrun=['remote/main'], qrun_state_dir=['remote/main=/queue'],
                   qrun_cpus=['remote/main=8'], qrun_memory_mb=['remote/main=4096'])
    configured = target(tmp_path, transport='ssh', ssh_host='fixture',
                        **({'ssh_config': before} if before is not None else {}))
    settings = {'targets': {'remote/main': configured}}
    value = {'install_root': options.install_root, 'settings': settings,
             'qrun': installer.plan(options, settings)}
    calls = []

    def invoke(pool, operation, *_args, **_fields):
        calls.append((operation, pool['route'].get('ssh_config')))
        return {'handler': ['/stable/handler'], 'unit': 'fixture.service'}

    monkeypatch.setattr(installer, 'invoke', invoke)
    installer.commit(installer.prepare(value, options, REPO))
    configured.pop('ssh_config', None)
    if after is not None:
        configured['ssh_config'] = after
    upgrade = args(tmp_path)
    value['qrun'] = installer.plan(upgrade, settings)
    assert len(value['qrun']) == 1
    pool = value['qrun'][0]
    assert pool['state_dir'] == '/queue'
    assert (pool['cpus'], pool['memory_mb']) == (8, 4096)
    transaction = installer.prepare(value, upgrade, REPO)
    rows = installer.registry(options.install_root)['pools']
    assert len(rows) == 1
    assert rows[0]['previous']['route'].get('ssh_config') == before
    assert rows[0]['route'].get('ssh_config') == after
    installer.commit(transaction)
    rows = installer.registry(options.install_root)['pools']
    assert len(rows) == 1 and rows[0]['published'] and not rows[0]['pending']
    assert rows[0]['handler'] == ['/stable/handler'] and 'previous' not in rows[0]
    installer.remove(Path(options.install_root), upgrade, REPO)
    assert calls == [('install', before), ('commit', before),
                     ('install', after), ('commit', after), ('remove', after)]


@pytest.mark.parametrize('change', ['host', 'transport', 'state_dir'])
def test_connection_update_does_not_allow_moving_an_owned_pool(tmp_path, change):
    options = args(tmp_path)
    state = installer.registry(options.install_root)
    state['pools'] = [{'route': {'transport': 'ssh', 'ssh_host': 'fixture'},
                       'targets': ['remote/main'], 'state_dir': '/queue',
                       'handler': ['/stable/handler'], 'cpus': 8, 'memory_mb': 4096}]
    installer.save(options.install_root, state)
    configured = target(tmp_path, transport='ssh', ssh_host='fixture',
                        ssh_config='/fixture/ssh-config', handler=['/stable/handler'])
    if change == 'host':
        configured['ssh_host'] = 'other'
    elif change == 'transport':
        configured['transport'] = 'local'
    else:
        options.qrun_state_dir = ['remote/main=/other-queue']
    with pytest.raises(ValueError, match='managed Qrun (route changed|state directory cannot change)'):
        installer.plan(options, {'targets': {'remote/main': configured}})


def test_shared_remote_pool_rejects_conflicting_ssh_configuration(tmp_path):
    names = ['one/main', 'two/main']
    options = args(tmp_path, manage_qrun=names,
                   qrun_state_dir=[name + '=/queue' for name in names],
                   qrun_cpus=[name + '=8' for name in names],
                   qrun_memory_mb=[name + '=4096' for name in names])
    settings = {'targets': {name: target(tmp_path, transport='ssh', ssh_host='fixture',
                                         ssh_config='/fixture/' + name.split('/')[0]) for name in names}}
    with pytest.raises(ValueError, match='same SSH configuration'):
        installer.plan(options, settings)


def test_controller_records_ownership_before_effect_and_rolls_back_lost_response(tmp_path, monkeypatch):
    options, value = transaction(tmp_path)
    calls = []

    def invoke(pool, operation, root, package, **fields):
        calls.append(operation)
        assert installer.registry(root)['pools'][0]['pending']
        if operation == 'install':
            raise RuntimeError('fixture response lost')
        return {'restored': True}

    monkeypatch.setattr(installer, 'invoke', invoke)
    with pytest.raises(RuntimeError, match='response lost'):
        installer.prepare(value, options, REPO)
    assert calls == ['install', 'restore']
    assert installer.registry(options.install_root)['pools'][0]['removed']


def test_controller_commit_and_upgrade_retain_handler(tmp_path, monkeypatch):
    options, value = transaction(tmp_path)
    calls = []

    def invoke(pool, operation, root, package, **fields):
        calls.append(operation)
        return {'handler': ['/stable/handler'], 'unit': 'fixture.service'}

    monkeypatch.setattr(installer, 'invoke', invoke)
    tx = installer.prepare(value, options, REPO)
    installer.commit(tx)
    assert value['settings']['targets']['local/main']['handler'] == ['/stable/handler']
    assert installer.plan(options, value['settings'])
    row = installer.registry(options.install_root)['pools'][0]
    assert row['published'] and not row['pending'] and 'previous' not in row
    assert calls == ['install', 'commit']
    installer.remove(Path(options.install_root), options, REPO)
    assert installer.registry(options.install_root)['pools'][0]['removed']
    # Preserved configuration still points at the stable handler after uninstall.
    assert installer.plan(options, value['settings'])


def test_rollback_failure_retains_pending_pool_for_retry(tmp_path, monkeypatch):
    options, value = transaction(tmp_path)
    calls = []

    def broken(pool, operation, root, package, **fields):
        calls.append(operation)
        raise RuntimeError('fixture offline')

    monkeypatch.setattr(installer, 'invoke', broken)
    with pytest.raises(RuntimeError, match='ownership record retained'):
        installer.prepare(value, options, REPO)
    assert installer.registry(options.install_root)['pools'][0]['pending']

    def recovered(pool, operation, root, package, **fields):
        calls.append(operation)
        return {'handler': ['/stable/handler'], 'unit': 'fixture.service'}

    monkeypatch.setattr(installer, 'invoke', recovered)
    installer.commit(installer.prepare(value, options, REPO))
    assert calls == ['install', 'restore', 'restore', 'install', 'commit']
    assert not installer.registry(options.install_root)['pools'][0]['pending']


def test_interrupted_commit_recovers_forward(tmp_path, monkeypatch):
    options, value = transaction(tmp_path)
    calls = []
    fail_commit = True

    def invoke(pool, operation, root, package, **fields):
        calls.append(operation)
        if operation == 'commit' and fail_commit:
            raise RuntimeError('fixture lost commit reply')
        return {'handler': ['/stable/handler'], 'unit': 'fixture.service'}

    monkeypatch.setattr(installer, 'invoke', invoke)
    tx = installer.prepare(value, options, REPO)
    with pytest.raises(RuntimeError, match='lost commit reply'):
        installer.commit(tx)
    assert installer.registry(options.install_root)['pools'][0]['published']
    fail_commit = False
    installer.commit(installer.prepare(value, options, REPO))
    assert calls == ['install', 'commit', 'commit', 'install', 'commit']
    assert not installer.registry(options.install_root)['pools'][0]['pending']


def test_standalone_install_cannot_modify_managed_pool(managed):
    root, value, _, _ = managed
    perform(managed, 'install')
    before = (root / 'config.json').read_bytes()
    with pytest.raises(ValueError, match='owning installer'):
        qrun.install(root, 99, 99, value['work_roots'], start=False)
    assert (root / 'config.json').read_bytes() == before


def test_failed_initial_file_setup_can_be_retried(managed):
    root, value, _, _ = managed
    with pytest.raises(ValueError, match='must not overlap'):
        perform(managed, 'install', work_roots=[str(root / 'work')])
    assert not (root / 'config.json').exists()
    assert not (root / 'maintenance-snapshot.json').exists()
    perform(managed, 'install')


def test_unavailable_manager_does_not_replace_or_stop_old_service(managed, monkeypatch):
    root, _, _, state = managed
    perform(managed, 'install')
    perform(managed, 'commit')
    before = (root / 'installation.json').read_bytes()
    state['calls'].clear()

    def unavailable(_root):
        raise RuntimeError('fixture manager unavailable')

    monkeypatch.setattr(qrun, 'check_service_manager', unavailable)
    with pytest.raises(RuntimeError, match='manager unavailable'):
        perform(managed, 'install', cpus=4)
    assert state['calls'] == []
    assert (root / 'installation.json').read_bytes() == before
    assert not (root / 'maintenance-snapshot.json').exists()


def test_existing_unrelated_directory_cannot_be_adopted_and_purged(managed):
    root, _, _, state = managed
    root.mkdir(mode=0o700)
    unrelated = root / 'important.txt'
    unrelated.write_text('must survive')
    with pytest.raises(ValueError, match='must be empty'):
        perform(managed, 'install')
    assert unrelated.read_text() == 'must survive'
    assert state['calls'] == []


def test_ssh_lifecycle_sends_only_program_and_pool_request(tmp_path, monkeypatch):
    _, value = transaction(tmp_path)
    pool = copy.deepcopy(value['qrun'][0])
    pool['route'] = {'transport': 'ssh', 'ssh_host': 'fixture-host', 'ssh_config': '/fixture/ssh-config'}

    def run(command, **kwargs):
        assert command[0] == 'ssh' and 'fixture-host' in command
        assert '-F' in command and 'BatchMode=yes' in command
        payload = json.loads(kwargs['input'])
        assert set(payload) == {'program', 'state_dir', 'request'}
        assert payload['request']['operation'] == 'remove'
        return SimpleNamespace(returncode=0, stdout='{"removed":true}')

    monkeypatch.setattr(installer.subprocess, 'run', run)
    assert installer.invoke(pool, 'remove', tmp_path / 'app', REPO)['removed']


def test_root_removal_cannot_bypass_history_retention(tmp_path, monkeypatch):
    options, value = transaction(tmp_path)
    state = installer.registry(options.install_root)
    state['pools'] = value['qrun']
    state['pools'][0]['state_dir'] = str(Path(options.install_root) / 'queue')
    installer.save(options.install_root, state)
    monkeypatch.setattr(installer, 'invoke', lambda *_a, **_kw: pytest.fail('must reject before removal'))
    options.remove_root = True
    with pytest.raises(ValueError, match='--purge-qrun-state'):
        installer.remove(Path(options.install_root), options, REPO)
