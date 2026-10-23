import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from types import SimpleNamespace

import pytest

from research_agent.application import job_manager
from research_agent.jobs.command_scope import ObservationTimeout, observation_deadline
from research_agent.jobs.environment import _capture
from tests.unit.test_external_jobs import queue, spec
from tests.unit.test_job_recovery import workspace
from tests.unit.test_job_tracking import binding_record


def monitor(root, number, platform):
    directory = root / 'operations/monitors' / f'monitor_{number}'
    directory.mkdir(parents=True)
    binding = {**binding_record(), 'monitor_id': f'monitor_{number}', 'job_id': f'job_{number}'}
    (directory / 'binding.json').write_text(json.dumps(binding))
    intents = root / 'operations/jobs'
    intents.mkdir(exist_ok=True)
    (intents / f'job_{number}.json').write_text(json.dumps({
        'schema_version': 'job_intent/4', 'job_id': f'job_{number}', 'platform': platform,
    }))
    return directory


def test_observation_inventory_uses_recorded_routes_without_reading_event_history(tmp_path):
    workspace(tmp_path)
    first = monitor(tmp_path, 1, 'Com30/qrun')
    monitor(tmp_path, 2, 'FEDCluster/tri')
    (first / 'events').mkdir()
    (first / 'events/event_1.json').write_text('unavailable event history')
    result = job_manager.command(tmp_path, 'observations', {})
    assert result == {'observations': [
        {'monitor_id': 'monitor_1', 'platform': 'Com30/qrun'},
        {'monitor_id': 'monitor_2', 'platform': 'FEDCluster/tri'},
    ], 'registration_errors': []}
    (first / 'binding.json').write_text('{}')
    result = job_manager.command(tmp_path, 'observations', {})
    assert result['observations'] == [{'monitor_id': 'monitor_2', 'platform': 'FEDCluster/tri'}]
    assert result['registration_errors'] == ['monitor_1: monitor_binding_schema_invalid']


def test_one_observation_budget_covers_multiple_subprocesses_and_resets_afterwards(tmp_path):
    import research_agent.jobs.command_scope as scope
    # Advance a deterministic clock between two real commands. The second
    # command must never start after the first has exhausted the shared budget.
    clock = [100.0]
    from unittest.mock import patch
    marker = tmp_path / 'must-not-run'
    with patch.object(scope.time, 'monotonic', side_effect=lambda: clock[0]):
        with observation_deadline(5):
            assert _capture(['/bin/true'], timeout=60).returncode == 0
            clock[0] = 106.0
            with pytest.raises(ObservationTimeout, match='job_observation_timed_out'):
                _capture([sys.executable, '-c', 'import pathlib,sys;pathlib.Path(sys.argv[1]).touch()', str(marker)], timeout=60)
    assert not marker.exists()
    assert _capture(['/bin/true'], timeout=60).returncode == 0


def test_observation_timeout_leaves_last_job_state_and_other_jobs_observable(tmp_path, monkeypatch):
    workspace(tmp_path)
    first = monitor(tmp_path, 1, 'slow/qrun')
    monitor(tmp_path, 2, 'healthy/qrun')
    before = (first / 'binding.json').read_bytes()
    monkeypatch.setattr(job_manager, '_receipt', lambda root, params, runtime: SimpleNamespace(job_id=params['job_id']))
    def runtime(_root, job_id):
        def status(_receipt):
            if job_id == 'job_1':
                _capture([sys.executable, '-c', 'import time;time.sleep(60)'], timeout=60)
            return SimpleNamespace(state=SimpleNamespace(value='running'), exit_code=None)
        return SimpleNamespace(job_status=status)
    monkeypatch.setattr(job_manager, '_recorded_job_manager', runtime)
    committed = []
    monkeypatch.setattr(job_manager, '_commit_observation', lambda root, value: committed.append(value) or value)
    result = job_manager.command(tmp_path, 'tick', {'timeout_seconds': .2})
    assert result['registration_errors'] == ['job_observation_timed_out']
    assert [row['monitor_id'] for row in committed] == ['monitor_2']
    assert (first / 'binding.json').read_bytes() == before
    assert not list(first.glob('events/*'))


def test_external_status_timeout_is_not_converted_to_an_unknown_job(queue, tmp_path):
    from research_agent.jobs import JobState
    from research_agent.jobs.external import ExternalJobPlatform

    config, state = queue
    platform = ExternalJobPlatform(config)
    receipt = platform.start(spec(tmp_path, command=('/bin/true',)))
    status_command = state / 'tri_stat'
    status_command.unlink()
    status_command.write_text('#!' + sys.executable + '\nimport time\ntime.sleep(60)\n')
    status_command.chmod(0o700)
    with observation_deadline(.2), pytest.raises(ObservationTimeout, match='job_observation_timed_out'):
        platform.status(receipt)
    assert not (Path(receipt.cwd) / 'status.json').exists()
    status_command.unlink()
    status_command.symlink_to(state / 'cli')
    assert platform.status(receipt).state == JobState.QUEUED


@pytest.mark.parametrize('stop', ['timeout', 'signal'])
def test_observation_stop_reaps_query_process_group(tmp_path, stop):
    child_file = tmp_path / 'child.pid'
    command = ['/bin/bash', '-c', 'sleep 60 & echo $! > "$1"; wait', 'observation', str(child_file)]
    supervisor = None
    try:
        if stop == 'timeout':
            with observation_deadline(.3), pytest.raises(ObservationTimeout):
                _capture(command, timeout=60)
        else:
            script = (
                'import sys\n'
                'from research_agent.jobs.command_scope import cancel_observation_on_signal, observation_deadline\n'
                'from research_agent.jobs.environment import _capture\n'
                'with cancel_observation_on_signal(), observation_deadline(30):\n'
                '    _capture(sys.argv[1:], timeout=60)\n'
            )
            supervisor = subprocess.Popen([sys.executable, '-c', script, *command])
            deadline = time.monotonic() + 5
            while not child_file.exists() and time.monotonic() < deadline:
                time.sleep(.01)
            assert child_file.exists()
            supervisor.terminate()
            assert supervisor.wait(timeout=5) == 128 + signal.SIGTERM
        pid = int(child_file.read_text())
        deadline = time.monotonic() + 3
        while Path('/proc', str(pid)).exists() and time.monotonic() < deadline:
            time.sleep(.01)
        assert not Path('/proc', str(pid)).exists()
    finally:
        if supervisor is not None and supervisor.poll() is None:
            supervisor.terminate()
            supervisor.wait(timeout=5)
        if child_file.exists():
            try:
                os.kill(int(child_file.read_text()), signal.SIGKILL)
            except ProcessLookupError:
                pass
