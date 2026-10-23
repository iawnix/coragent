"""Real local Linux process trees; all state belongs to the private test fixture."""
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import time

import pytest

from research_agent.jobs import qrun
from coragent_packaging.installer import _qrun_install
from tests.unit.test_qrun import request


def until(predicate, timeout=10):
    deadline = time.monotonic() + timeout
    while not predicate():
        if time.monotonic() >= deadline:
            pytest.fail('portable runtime did not reach expected state')
        time.sleep(.03)


@pytest.fixture
def pool(tmp_path):
    root, work = tmp_path / 'pool', tmp_path / 'work'
    qrun.initialize(root, 2, 256, [str(work)], runtime='portable')
    queue = qrun.Queue(root)
    yield queue, work
    for row in queue.rows():
        queue.handle({**json.loads(row['request']), 'action': 'cancel'})
    def cleaned():
        queue.tick()
        return all(row['cleaned'] for row in queue.rows())
    until(cleaned)
    for child in queue.runtime.children:
        child.wait(timeout=5)
    queue.close()


def complete(queue):
    queue.tick()
    return all(row['cleaned'] for row in queue.rows())


def test_real_script_completes_with_affinity_and_durable_result(pool):
    queue, work = pool
    script = shlex.join([sys.executable, '-c', 'import os,pathlib; pathlib.Path("affinity").write_text(str(len(os.sched_getaffinity(0))))'])
    queue.handle(request(work, cpus=1, memory=128, script=script))
    until(lambda: complete(queue))
    assert queue.rows()[0]['state'] == 'succeeded'
    assert (work / 'first/affinity').read_text() == '1'
    result = json.loads((queue.directory(queue.rows()[0]) / 'result.json').read_text())
    assert result['descendants_reaped']


def test_real_usage_stdout_stderr_and_online_capacity_checks(pool):
    queue, work = pool
    req = request(work, cpus=1, memory=128,
        script='echo output; echo problem >&2; ' + shlex.join([sys.executable, '-c',
            'import time; data=bytearray(16*1024*1024); end=time.monotonic()+1.2\nwhile time.monotonic()<end: pass']))
    queue.handle(req)
    queue.tick()
    def sampled():
        view = queue.view().job(queue.rows()[0])
        return view['usage']['available'] and view['usage'].get('cpu_seconds', 0) > 0
    until(sampled)
    view = queue.view().job(queue.rows()[0])
    assert view['usage']['peak_memory_mb'] > 10
    assert not view['usage']['stale']
    with pytest.raises(ValueError, match='affinity'):
        queue.handle({'schema_version': qrun.PROTOCOL, 'action': 'configure', 'cpus': len(os.sched_getaffinity(0)) + 1})
    until(lambda: complete(queue))
    details = queue.view().job(queue.rows()[0])
    assert details['usage']['final'] and details['usage']['cpu_seconds'] > 0
    for stream, expected in [('stdout', 'output\n'), ('stderr', 'problem\n')]:
        logs = queue.view().query({'action': 'logs', 'identifier': 1, 'stream': stream})
        assert logs['text'] == expected and logs['finished']


@pytest.mark.parametrize('cancel', [False, True])
def test_double_fork_and_setsid_descendants_are_removed(pool, cancel):
    queue, work = pool
    payload = '''import os,time,pathlib
if os.fork() == 0:
 os.setsid()
 if os.fork() == 0:
  pathlib.Path("escaped.pid").write_text(str(os.getpid()))
  while True: time.sleep(1)
 os._exit(0)
time.sleep(60 if CANCEL else .3)
'''.replace('CANCEL', repr(cancel))
    req = request(work, cpus=1, memory=128, script=shlex.join([sys.executable, '-c', payload]))
    queue.handle(req)
    queue.tick()
    until(lambda: (work / 'first/escaped.pid').exists())
    pid = int((work / 'first/escaped.pid').read_text())
    if cancel:
        queue.handle({**req, 'action': 'cancel'})
    until(lambda: complete(queue))
    assert queue.rows()[0]['state'] == ('cancelled' if cancel else 'succeeded')
    assert qrun.process_info(pid) is None


def test_fifo_and_distinct_cpu_assignments(pool):
    queue, work = pool
    for name in ('one', 'two', 'three'):
        queue.handle(request(work, name, cpus=1, memory=64, script='sleep 30'))
    queue.tick()
    first, second, third = queue.rows()
    masks = [json.loads((queue.directory(row) / 'worker.json').read_text())['affinity'] for row in (first, second)]
    assert not set(masks[0]) & set(masks[1])
    assert third['state'] == 'queued'


def test_timeout_cleans_process_tree(pool):
    queue, work = pool
    queue.handle(request(work, cpus=1, memory=64, timeout=.2, script='sleep 60'))
    until(lambda: complete(queue))
    assert queue.rows()[0]['state'] == 'timed_out'


def test_memory_monitor_terminates_over_budget_job(pool):
    queue, work = pool
    script = shlex.join([sys.executable, '-c', 'import time; x=bytearray(80*1024*1024); time.sleep(60)'])
    queue.handle(request(work, cpus=1, memory=32, script=script))
    until(lambda: complete(queue))
    row = queue.rows()[0]
    assert row['state'] == 'failed'
    assert 'RSS exceeded' in row['error']


def test_queue_restart_reconciles_live_worker_without_resubmission(pool):
    queue, work = pool
    req = request(work, cpus=1, memory=64, script='sleep .5; echo done > result')
    receipt = queue.handle(req)
    queue.tick()
    other = qrun.Queue(queue.root)
    try:
        assert other.handle(req) == receipt
        until(lambda: complete(other))
        assert other.rows()[0]['state'] == 'succeeded'
        assert (work / 'first/result').read_text() == 'done\n'
    finally:
        other.close()


def test_failed_spawn_can_be_cancelled_without_leaking_cpu_reservations(pool, monkeypatch):
    queue, work = pool
    req = request(work, cpus=2, memory=64, script='echo should-not-run > result')
    queue.handle(req)
    with monkeypatch.context() as patch:
        def failure(*_args, **_kwargs):
            raise OSError('fixture spawn failed')
        patch.setattr(qrun.subprocess, 'Popen', failure)
        queue.tick()
    assert queue.rows()[0]['state'] == 'unknown'
    queue.handle({**req, 'action': 'cancel'})
    until(lambda: complete(queue))
    assert not (work / 'first/result').exists()
    queue.handle(request(work, 'second', cpus=2, memory=64, script='exit 0'))
    until(lambda: complete(queue))
    assert queue.rows()[1]['state'] == 'succeeded'


def test_pid_identity_mismatch_retains_reservation_and_cancellation_uses_fence(pool):
    queue, work = pool
    req = request(work, cpus=1, memory=64, script='sleep 30')
    queue.handle(req)
    queue.tick()
    directory = queue.directory(queue.rows()[0])
    until(lambda: (directory / 'started.json').exists())
    identity = json.loads((directory / 'worker.json').read_text())
    identity['start'] = 'invalid-identity'
    qrun.atomic_json(directory / 'worker.json', identity)
    queue.tick()
    assert queue.rows()[0]['state'] == 'unknown'
    queue.handle({**req, 'action': 'cancel'})
    until(lambda: complete(queue))
    assert queue.rows()[0]['state'] == 'cancelled'


def test_cancel_before_late_worker_launch_prevents_execution(pool):
    queue, work = pool
    req = request(work, cpus=1, memory=64, script='echo wrong > result')
    queue.handle(req)
    row = queue.rows()[0]
    directory = queue.directory(row)
    directory.mkdir()
    qrun.atomic_json(directory / 'run.json', req)
    qrun.atomic_json(directory / 'allocation.json', {'boot': qrun.boot_id(), 'affinity': [min(os.sched_getaffinity(0))]})
    qrun.atomic_json(directory / 'cancel.json', {})
    result = subprocess.run([sys.executable, '-B', qrun.__file__, '--state-dir', str(queue.root),
                             '_portable-run', row['id']], capture_output=True)
    assert result.returncode != 0
    assert not (work / 'first/result').exists()
    assert json.loads((directory / 'result.json').read_text())['state'] == 'cancelled'


@pytest.fixture
def cron(monkeypatch):
    state = {'text': 'MAILTO=fixture\n17 * * * * /fixture/unrelated\n'}
    def command(args, *, content=None):
        if args == ['-']:
            state['text'] = content
        return subprocess.CompletedProcess(args, 0, state['text'] if args == ['-l'] else '', '')
    monkeypatch.setattr(qrun, 'cron_command', command)
    return state


def test_owned_portable_install_restart_upgrade_and_uninstall(tmp_path, cron):
    root, work = tmp_path / 'pool', tmp_path / 'work'
    original = cron['text']
    owner = _qrun_install.owner(tmp_path / 'app')
    def lifecycle(operation, **fields):
        return qrun.maintain(root, {'owner': owner, 'operation': operation, **fields})
    try:
        installed = lifecycle('install', cpus=2, memory_mb=256, work_roots=[str(work)], runtime='portable', start=True)
        lifecycle('commit')
        assert installed['runtime'] == 'portable'
        assert '@reboot' in cron['text'] and '* * * * *' in cron['text']
        assert cron['text'].startswith(original)
        probe = qrun.client(root, {'schema_version': qrun.PROTOCOL, 'action': 'probe'})
        assert probe['runtime'] == 'portable' and probe['memory_enforcement'] == 'sampled-rss'
        command = [sys.executable, '-B', installed['program'], '--state-dir', str(root)]
        def cli(*args):
            result = subprocess.run([*command, *args], capture_output=True, text=True, timeout=10, check=True)
            return json.loads(result.stdout)
        assert cli('pause', '--json')['paused']
        assert cli('config', '--cpus', '1', '--json')['capacity']['cpus'] == 1
        assert cli('watch', '--count', '1', '--json')['overview']['paused']
        assert not cli('resume', '--json')['paused']
        req = request(work, cpus=1, memory=64, script='sleep .4; echo done > result')
        receipt = qrun.client(root, req)
        until(lambda: qrun.client(root, {**req, 'action': 'status'})['state'] == 'running')
        qrun.service_command(root, 'stop')
        qrun.activate(root, installed)
        assert qrun.client(root, req) == receipt
        until(lambda: qrun.client(root, {**req, 'action': 'status'})['execution_finished'])
        assert cli('logs', '1', '--follow', '--json')['finished']
        assert cli('show', '1', '--json')['job']['state'] == 'succeeded'
        assert cli('jobs', '--all', '--json')['total'] == 1
        updated = lifecycle('install', cpus=1, memory_mb=256, work_roots=[str(work)], runtime='portable', start=True)
        lifecycle('commit')
        assert updated['handler'] == installed['handler']
        result = lifecycle('remove')
        assert result['state_retained'] and cron['text'] == original
        assert not qrun.daemon_locked(root)
        lifecycle('remove', purge=True)
        assert not root.exists() and (work / 'first/result').exists()
    finally:
        if root.exists():
            lifecycle('remove', cancel_jobs=True, purge=True)
        assert cron['text'] == original


def test_portable_manager_failure_does_not_adopt_pool(tmp_path, monkeypatch):
    monkeypatch.setattr(qrun, 'cron_command', lambda *a, **kw: subprocess.CompletedProcess(a, 1, '', 'permission denied'))
    root = tmp_path / 'pool'
    with pytest.raises(RuntimeError, match='crontab'):
        qrun.maintain(root, {'owner': _qrun_install.owner(tmp_path / 'app'), 'operation': 'install',
            'cpus': 1, 'memory_mb': 128, 'work_roots': [str(tmp_path / 'work')], 'runtime': 'portable', 'start': True})
    assert not (root / 'installation.json').exists()
