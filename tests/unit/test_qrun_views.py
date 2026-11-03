"""Queue accounting, operator controls and retained observations."""
import json
import re
import subprocess
import sys
from pathlib import Path
import sqlite3

import pytest

from research_agent.jobs import qrun
from tests.unit.test_qrun import pool, request


@pytest.mark.parametrize('tty,term,no_color,expected', [
    (True, 'xterm-256color', None, True),
    (False, 'xterm-256color', None, False),
    (True, 'dumb', None, False),
    (True, 'xterm-256color', '1', False),
    (True, 'xterm-256color', '', False),
])
def test_color_respects_terminal_and_environment(monkeypatch, capsys, tty, term, no_color, expected):
    monkeypatch.setattr(sys.stdout, 'isatty', lambda: tty)
    monkeypatch.setenv('TERM', term)
    monkeypatch.delenv('NO_COLOR', raising=False)
    if no_color is not None:
        monkeypatch.setenv('NO_COLOR', no_color)
    value = {'job': {'id': '1', 'state': 'failed', 'error': 'script exited'}}
    qrun.display(value)
    shown = capsys.readouterr().out
    assert ('\033[' in shown) == expected
    assert 'failed' in shown and 'script exited' in shown
    qrun.display(value, as_json=True)
    raw = capsys.readouterr().out
    assert '\033[' not in raw and json.loads(raw) == value


def test_colored_views_preserve_text_alignment_and_offline_warning(pool, capsys):
    queue, _, work = pool
    queue.handle(request(work, cpus=4))
    queue.tick()
    queue.handle(request(work, 'second'))
    call(queue, 'pause')
    call(queue, 'configure', cpus=2)
    views = [call(queue, 'resources'), call(queue, 'jobs'), call(queue, 'show', identifier=1)]
    views.append({**views[0], 'online': False, 'paused': False})
    for view in views:
        qrun.display(view, color=False)
        plain = capsys.readouterr().out
        qrun.display(view, color=True)
        colored = capsys.readouterr().out
        assert '\033[' in colored
        assert re.sub(r'\x1b\[[0-9;]*m', '', colored) == plain
    assert 'OFFLINE' in plain and 'dispatching' not in plain


def test_cli_help_groups_public_commands_and_hides_internal_entries(capsys):
    with pytest.raises(SystemExit) as result:
        qrun.main(['--help'])
    assert result.value.code == 0
    text = capsys.readouterr().out
    assert 'usage: qrun ' in text and 'COMMAND ...' in text
    for heading in ('Inspect jobs:', 'Control the queue:', 'Installation and service:'):
        assert heading in text
    for internal in ('==SUPPRESS==', '_run', '_portable-run', 'maintenance', 'handler'):
        assert internal not in text
    with pytest.raises(SystemExit) as result:
        qrun.main(['--help-all'])
    assert result.value.code == 0
    full = capsys.readouterr().out
    assert 'qrun-cli/1' in full and 'coragent-external-job/1' in full
    assert 'recover after response loss' in full
    for command in ('handler', 'maintenance', 'serve', '_run', '_portable-run'):
        assert command in full
        with pytest.raises(SystemExit) as result:
            qrun.main([command, '--help'])
        assert result.value.code == 0
        capsys.readouterr()


def test_list_preserves_legacy_array_in_tty_and_pipes(pool, monkeypatch, capsys):
    queue, _, work = pool
    for number in range(52):
        queue.handle(request(work, str(number)))
    def offline(*args, **kwargs):
        raise ConnectionRefusedError()
    monkeypatch.setattr(qrun, 'client', offline)
    prefix = ['--state-dir', str(queue.root), 'list']
    results = []
    for tty in (True, False):
        monkeypatch.setattr(sys.stdout, 'isatty', lambda: tty)
        for suffix in ([], ['--json']):
            assert qrun.main(prefix + suffix) == 0
            raw = capsys.readouterr().out
            assert '\033[' not in raw
            results.append(json.loads(raw))
    assert all(value == results[0] for value in results)
    exported = results[0]
    assert len(exported) == 52 and exported[0]['id'] == '1' and exported[-1]['id'] == '52'
    assert set(exported[0]) == {'id', 'state', 'cpus', 'memory_mb', 'created_at',
                                'started_at', 'finished_at', 'error'}


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


def test_cli_json_metadata_pagination_and_log_continuation(pool, monkeypatch, capsys):
    queue, _, work = pool
    for name in ('first', 'second', 'third'):
        queue.handle(request(work, name))
    monkeypatch.setattr(qrun, 'client', lambda root, req, **kw: qrun.response(queue, req))
    prefix = ['--state-dir', str(queue.root)]
    identifiers, offset = [], 0
    while offset is not None:
        assert qrun.main(prefix + ['jobs', '--all', '--limit', '2', '--offset', str(offset), '--json']) == 0
        page = json.loads(capsys.readouterr().out)
        assert page['ok'] and page['cli_version'] == 'qrun-cli/1' and page['command'] == 'jobs'
        assert page['view_version'] == 'qrun-view/1' and page['source'] == 'daemon'
        assert page['state_basis'] == 'ledger' and page['order'] == 'newest_first'
        assert page['has_more'] == (page['next_offset'] is not None)
        identifiers.extend(job['id'] for job in page['jobs'])
        offset = page['next_offset']
    assert identifiers == ['3', '2', '1']
    page = call(queue, 'jobs', offset=99)
    assert page['jobs'] == [] and page['next_offset'] is None and not page['has_more']
    queue.tick()
    path = queue.directory(queue.rows()[0]) / 'stdout.log'
    path.write_text('abc')
    assert qrun.main(prefix + ['logs', '1', '--json']) == 0
    chunk = json.loads(capsys.readouterr().out)
    path.write_text('abcdef')
    assert qrun.main(prefix + ['logs', '1', '--offset', str(chunk['offset']),
                              '--identity', chunk['identity'], '--json']) == 0
    chunk = json.loads(capsys.readouterr().out)
    assert chunk['text'] == 'def' and not chunk['reset'] and chunk['command'] == 'logs'


def test_incomplete_usage_is_not_a_measured_zero_and_offline_is_explicit(pool, monkeypatch, capsys):
    queue, _, work = pool
    queue.handle(request(work))
    queue.tick()
    resources = call(queue, 'resources')
    assert not resources['job_usage']['complete']
    assert resources['job_usage']['total_cpu_cores'] is None
    assert resources['job_usage']['total_memory_mb'] is None
    assert call(queue, 'show', identifier=1)['job']['usage']['cpu_cores'] is None
    qrun.atomic_json(queue.directory(queue.rows()[0]) / 'usage.json', {
        'sampled_at': qrun.now(), 'cpu_cores': 0, 'memory_mb': 0, 'final': False})
    resources = call(queue, 'resources')
    assert resources['job_usage']['complete'] and resources['job_usage']['total_cpu_cores'] == 0
    def offline(*args, **kwargs):
        raise ConnectionRefusedError()
    monkeypatch.setattr(qrun, 'client', offline)
    assert qrun.main(['--state-dir', str(queue.root), 'resources', '--json']) == 0
    saved = json.loads(capsys.readouterr().out)
    assert saved['ok'] and not saved['online'] and saved['stale'] and saved['source'] == 'ledger'
    assert not saved['job_usage']['complete'] and saved['job_usage']['total_cpu_cores'] is None


@pytest.mark.parametrize('arguments,code,exit_code', [
    (['jobs', '--limit', 'no'], 'invalid_arguments', 2),
    (['jobs', '--limit', '101'], 'invalid_arguments', 1),
    (['logs', '1', '--bytes', '0'], 'invalid_arguments', 1),
    (['show'], 'invalid_arguments', 2),
    (['show', '999'], 'job_not_found', 1),
    (['jobs', '--state', 'bogus'], 'invalid_arguments', 2),
    (['watch', '--count', '0'], 'invalid_arguments', 1),
])
def test_json_cli_errors_are_structured(pool, monkeypatch, capsys, arguments, code, exit_code):
    queue, _, work = pool
    queue.handle(request(work))
    monkeypatch.setattr(qrun, 'client', lambda root, req, **kw: qrun.response(queue, req))
    assert qrun.main(['--state-dir', str(queue.root), *arguments, '--json']) == exit_code
    captured = capsys.readouterr()
    error = json.loads(captured.out)
    assert not error['ok'] and error['cli_version'] == 'qrun-cli/1'
    assert error['error']['code'] == code and not error['error']['retryable']
    assert error['error']['recovery'] and not captured.err and '\033' not in captured.out


def test_lost_mutation_ack_is_not_treated_as_rejection_or_retried(pool, monkeypatch, capsys):
    queue, _, _ = pool
    requests = []
    def lose_ack(root, req, **kwargs):
        requests.append(req)
        qrun.response(queue, req)
        raise TimeoutError('lost response after applying mutation')
    monkeypatch.setattr(qrun, 'client', lose_ack)
    assert qrun.main(['--state-dir', str(queue.root), 'pause', '--json']) == 1
    error = json.loads(capsys.readouterr().out)
    assert error['error']['code'] == 'qrun_unavailable'
    assert error['error']['action_outcome'] == 'unknown' and error['error']['retryable']
    assert len(requests) == 1 and call(queue, 'overview')['paused']


def test_cli_keeps_remote_error_metadata_and_cancel_ack_separate_from_exit(pool, monkeypatch, capsys):
    queue, _, work = pool
    queue.handle(request(work))
    queue.tick()
    monkeypatch.setattr(qrun, 'client', lambda root, req, **kw: qrun.response(queue, req))
    prefix = ['--state-dir', str(queue.root)]
    assert qrun.main(prefix + ['cancel', '1', '--json']) == 0
    ack = json.loads(capsys.readouterr().out)
    assert ack['ok'] and ack['accepted'] and ack['scheduler_id'] == '1'
    assert qrun.main(prefix + ['show', '1', '--json']) == 0
    job = json.loads(capsys.readouterr().out)['job']
    assert job['cancel_requested'] and not job['execution_finished']
    failure = {'code': 'qrun_error', 'message': 'identity conflict',
               'retryable': False, 'action_outcome': 'unknown'}
    monkeypatch.setattr(qrun, 'client', lambda *a, **kw: {'error': failure})
    assert qrun.main(prefix + ['resume', '--json']) == 1
    error = json.loads(capsys.readouterr().out)['error']
    assert all(error[key] == value for key, value in failure.items())


def test_real_cli_missing_pool_and_protocol_errors_keep_separate_contracts(tmp_path):
    prefix = [sys.executable, '-B', qrun.__file__, '--state-dir', str(tmp_path / 'absent')]
    cli = subprocess.run(prefix + ['status', '--json'], capture_output=True, text=True, timeout=10)
    assert cli.returncode == 1 and not cli.stderr
    error = json.loads(cli.stdout)
    assert error['error']['code'] == 'state_unavailable' and error['cli_version'] == 'qrun-cli/1'
    for payload in ('[]', '{broken', json.dumps({'schema_version': qrun.PROTOCOL, 'action': 'probe'})):
        protocol = subprocess.run(prefix + ['handler'], input=payload, capture_output=True, text=True, timeout=10)
        assert protocol.returncode == 0 and not protocol.stderr
        error = json.loads(protocol.stdout)
        assert error['schema_version'] == qrun.PROTOCOL and 'cli_version' not in error
        assert error['error']['action_outcome'] == 'unknown'
    assert not (tmp_path / 'absent').exists()


@pytest.mark.parametrize('payload', [
    {'action': []}, {'action': 'jobs', 'states': [[]]},
    {'action': 'jobs', 'states': False}, {'action': 'jobs', 'all': 'false'},
])
def test_invalid_machine_query_types_return_protocol_error(pool, payload):
    queue, _, _ = pool
    answer = qrun.response(queue, {'schema_version': qrun.PROTOCOL, **payload})
    assert answer['schema_version'] == qrun.PROTOCOL
    assert answer['error']['code'] == 'invalid_arguments' and not answer['error']['retryable']


def test_corrupt_pool_config_is_a_state_error_in_json(tmp_path, capsys):
    root = tmp_path / 'broken-pool'
    root.mkdir()
    (root / 'config.json').write_text('{broken')
    assert qrun.main(['--state-dir', str(root), 'status', '--json']) == 1
    captured = capsys.readouterr()
    assert json.loads(captured.out)['error']['code'] == 'state_unavailable' and not captured.err


def test_watch_json_flushes_each_record_before_next_refresh(pool, monkeypatch, capsys):
    queue, _, _ = pool
    monkeypatch.setattr(qrun, 'client', lambda root, req, **kw: qrun.response(queue, req))
    flushed = []
    monkeypatch.setattr(sys.stdout, 'flush', lambda: flushed.append(True))
    def interrupt_after_record(seconds):
        assert flushed
        raise KeyboardInterrupt()
    monkeypatch.setattr(qrun.time, 'sleep', interrupt_after_record)
    assert qrun.main(['--state-dir', str(queue.root), 'watch', '--json']) == 130
    lines = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert len(lines) == 2 and lines[0]['ok'] and lines[0]['command'] == 'watch'
    assert not lines[1]['ok'] and lines[1]['error']['code'] == 'interrupted'


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
