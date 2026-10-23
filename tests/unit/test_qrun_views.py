"""Queue accounting, operator controls and retained observations."""
import json
from pathlib import Path
import sqlite3

import pytest

from research_agent.jobs import qrun
from tests.unit.test_qrun import pool, request


def call(queue, action, **fields):
    return queue.handle({'schema_version': qrun.PROTOCOL, 'action': action, **fields})


def test_reservations_survive_uncertain_workers_and_are_not_actual_usage(pool):
    queue, runtime, work = pool
    queue.handle(request(work, cpus=3))
    queue.tick()
    runtime.units.clear()
    queue.tick()
    view = call(queue, 'resources')
    assert view['reserved'] == {'cpus': 3, 'memory_mb': 1024}
    assert view['free'] == {'cpus': 1, 'memory_mb': 3072}
    assert view['states'] == {'unknown': 1}
    assert view['job_usage']['missing_or_stale_jobs'] == 1
    assert view['host']['memory_total_mb'] > 0
    assert call(queue, 'probe')['queue']['reserved'] == view['reserved']
    for state in qrun.ACTIVE:
        queue.update(queue.rows()[0], state=state)
        assert call(queue, 'resources')['reserved'] == view['reserved']


def test_live_shrink_keeps_running_work_and_fifo_explains_blockers(pool):
    queue, runtime, work = pool
    for name, cpu in [('first', 4), ('second', 3), ('third', 1)]:
        queue.handle(request(work, name, cpus=cpu))
    queue.tick()
    view = call(queue, 'configure', cpus=2, memory_mb=512)
    assert view['overcommitted'] == {'cpus': 2, 'memory_mb': 512}
    assert view['free'] == {'cpus': 0, 'memory_mb': 0}
    queue.tick()
    assert runtime.stops == [] and len(runtime.starts) == 1
    jobs = call(queue, 'jobs')['jobs']
    assert jobs[1]['wait_reason']['code'] == 'exceeds_capacity'
    assert jobs[2]['wait_reason'] == {'code': 'fifo', 'blocked_by': jobs[1]['id']}
    runtime.finish(queue.rows()[0])
    queue.tick()
    call(queue, 'configure', cpus=4, memory_mb=4096)
    queue.tick()
    assert len(runtime.starts) == 3


def test_wait_reason_and_normal_status_agree(pool):
    queue, _, work = pool
    queue.handle(request(work, cpus=2, memory=3500))
    second = request(work, 'second', cpus=3)
    queue.handle(second)
    queue.tick()
    reason = call(queue, 'show', identifier=2)['job']['wait_reason']
    assert reason == {'code': 'insufficient_resources', 'shortfall': {'cpus': 1, 'memory_mb': 428}}
    assert queue.handle({**second, 'action': 'status'})['diagnostics']['wait_reason'] == reason


def test_pause_persists_and_still_allows_cancellation_and_cleanup(pool):
    queue, runtime, work = pool
    first, second = request(work, cpus=4), request(work, 'second')
    queue.handle(first)
    queue.tick()
    call(queue, 'pause')
    queue.handle(second)
    call(queue, 'cancel_job', identifier=1)
    for _ in range(3):
        queue.tick()
    assert queue.rows()[0]['state'] == 'cancelled' and queue.rows()[0]['cleaned']
    restored = qrun.Queue(queue.root, runtime=runtime)
    try:
        restored.tick()
        assert call(restored, 'show', identifier=2)['job']['wait_reason']['code'] == 'paused'
        call(restored, 'resume')
        restored.tick()
        assert len(runtime.starts) == 2
    finally:
        restored.close()


def test_offline_queries_label_saved_state_and_never_create_a_pool(pool, tmp_path, monkeypatch):
    queue, _, work = pool
    queue.handle(request(work))
    queue.tick()
    def offline(*args, **kwargs):
        raise ConnectionRefusedError()
    monkeypatch.setattr(qrun, 'client', offline)
    original = (queue.root / 'config.json').read_bytes()
    assert not qrun.query(queue.root, {'action': 'resources'})['online']
    assert qrun.query(queue.root, {'action': 'show', 'identifier': 1})['stale']
    with pytest.raises(RuntimeError, match='unavailable'):
        qrun.query(queue.root, {'action': 'configure', 'cpus': 1})
    assert (queue.root / 'config.json').read_bytes() == original
    with pytest.raises((OSError, sqlite3.Error)):
        qrun.query(tmp_path / 'absent', {'action': 'jobs'})
    assert not (tmp_path / 'absent').exists()


def test_job_filter_pagination_and_numeric_ids(pool):
    queue, _, work = pool
    for name in ('first', 'second', 'third'):
        queue.handle(request(work, name))
    first = queue.rows()[0]
    assert call(queue, 'show', identifier='1')['job']['seq'] == 1
    call(queue, 'cancel_job', identifier='1')
    assert call(queue, 'jobs')['total'] == 2
    history = call(queue, 'jobs', all=True, limit=1, offset=1)
    assert history['total'] == 3 and history['jobs'][0]['seq'] == 2
    assert call(queue, 'jobs', states=['cancelled'])['jobs'][0]['seq'] == 1
    assert call(queue, 'show', identifier='1')['job']['id'] == '1'
    with pytest.raises(ValueError, match='unknown'):
        call(queue, 'show', identifier=first['id'])
    with pytest.raises(ValueError):
        call(queue, 'jobs', limit=101)


def test_log_tail_cursor_rotation_and_safe_paths(pool):
    queue, _, work = pool
    queue.handle(request(work))
    assert not call(queue, 'logs', identifier=1)['available']
    queue.tick()
    path = queue.directory(queue.rows()[0]) / 'stdout.log'
    path.write_text('abcdef')
    first = call(queue, 'logs', identifier=1, bytes=3)
    assert first['text'] == 'def' and first['truncated']
    path.write_text('abcdefgh')
    second = call(queue, 'logs', identifier=1, offset=first['offset'], identity=first['identity'])
    assert second['text'] == 'gh'
    path.unlink()
    path.write_text('new')
    rotated = call(queue, 'logs', identifier=1, offset=second['offset'], identity=second['identity'])
    assert rotated['reset'] and rotated['text'] == 'new'
    staged = work / 'first/logs'
    staged.mkdir()
    (staged / 'stdout.log').write_text('application output')
    assert call(queue, 'logs', identifier=1)['text'] == 'application output'
    (staged / 'stdout.log').unlink()
    (staged / 'stdout.log').symlink_to(path)
    with pytest.raises(ValueError, match='symlink'):
        call(queue, 'logs', identifier=1)
    with pytest.raises(ValueError):
        call(queue, 'logs', identifier=1, stream='../../config.json')


def test_cli_views_watch_and_controls(pool, monkeypatch, capsys):
    queue, _, work = pool
    queue.handle(request(work))
    monkeypatch.setattr(qrun, 'client', lambda root, req, **kw: qrun.response(queue, req))
    prefix = ['--state-dir', str(queue.root)]
    assert qrun.main(prefix + ['resources']) == 0
    assert 'Reserved' in capsys.readouterr().out
    assert qrun.main(prefix + ['jobs', '--json']) == 0
    assert json.loads(capsys.readouterr().out)['jobs'][0]['state'] == 'queued'
    assert qrun.main(prefix + ['watch', '--count', '1', '--json']) == 0
    assert json.loads(capsys.readouterr().out)['overview']['online']
    assert qrun.main(prefix + ['pause', '--json']) == 0
    assert json.loads(capsys.readouterr().out)['paused']
    assert qrun.main(prefix + ['config', '--cpus', '0']) == 1
    assert queue.config['cpus'] == 4
    assert qrun.main(prefix + ['cancel', '1']) == 0
    capsys.readouterr()
    assert qrun.main(prefix + ['logs', '1', '--follow', '--json']) == 0
    assert json.loads(capsys.readouterr().out)['finished']


def test_stale_usage_is_not_summed_as_live_usage(pool):
    queue, _, work = pool
    queue.handle(request(work))
    queue.tick()
    row = queue.rows()[0]
    qrun.atomic_json(queue.directory(row) / 'usage.json', {'sampled_at': '2000-01-01T00:00:00+00:00',
        'cpu_cores': 2, 'memory_mb': 100, 'final': False})
    assert call(queue, 'show', identifier=1)['job']['usage']['stale']
    assert call(queue, 'resources')['job_usage']['cpu_cores'] == 0
    assert call(queue, 'resources')['reserved']['cpus'] == 2


def test_numeric_receipts_survive_restart_and_guard_execution_identity(pool, capsys):
    queue, runtime, work = pool
    first = request(work)
    second = request(work, 'second')
    assert queue.handle(first)['scheduler_id'] == '1'
    assert queue.handle(second)['scheduler_id'] == '2'
    assert queue.handle(first)['scheduler_id'] == '1'
    with pytest.raises(qrun.RequestError, match='identity mismatch'):
        queue.handle({**first, 'action': 'cancel', 'scheduler_id': '2'})
    # Existing ledger keys remain private; old exact receipts can still reconcile.
    legacy = queue.rows()[0]['id']
    assert queue.handle({**first, 'action': 'status', 'scheduler_id': legacy})['scheduler_id'] == legacy
    restored = qrun.Queue(queue.root, runtime=runtime)
    try:
        assert restored.handle({**first, 'action': 'recover'})['scheduler_id'] == '1'
        assert restored.handle({**first, 'action': 'status', 'scheduler_id': '1'})['scheduler_id'] == '1'
        assert call(restored, 'logs', identifier='1')['id'] == '1'
        qrun.display(call(restored, 'jobs'))
        qrun.display(call(restored, 'show', identifier='1'))
        shown = capsys.readouterr().out
        assert legacy not in shown and 'id: 1' in shown
    finally:
        restored.close()
