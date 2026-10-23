"""Work-item admission shares Job Manager's durable intent and observations."""
import json
import os
from pathlib import Path
import pytest

from research_agent.application.execution import dispatch
from tests.unit.test_job_recovery import workspace


def request(root, identifier="a"):
    selection = dispatch('resolve_target', {'root': str(root)})
    return {'root': str(root), 'request_id': 'plan-' + identifier, 'work_id': identifier,
            'session_id': 'plan-session', 'user_task_id': 'task_1',
            'command': ['/bin/sh', '-c', 'sleep 1; printf done'],
            'execution_context': {'selection': {key: selection[key] for key in ('target', 'route_digest')},
                'policy': {'max_in_flight': 1, 'max_attempts': 2},
                'item': {'id': identifier, 'work_id': identifier, 'plan_revision': 1,
                         'resources': {'cpus': 1, 'memory_mb': 512}, 'input_artifact_ids': []}}}


def test_item_submission_replays_original_receipt_and_is_visible_in_job_list(tmp_path):
    workspace(tmp_path)
    params = request(tmp_path)
    first = dispatch('start', params)
    assert dispatch('start', params)['job_id'] == first['job_id']
    rows = dispatch('list', {'root': str(tmp_path), 'user_task_id': 'task_1'})['jobs']
    assert len(rows) == 1 and rows[0]['execution_item']['id'] == 'a'
    with pytest.raises(ValueError, match='budget_reached|already_submitted'):
        dispatch('start', {**params, 'request_id': 'different-attempt'})
    dispatch('cancel', {'root': str(tmp_path), 'job_id': first['job_id']})


def test_unknown_dispatch_holds_budget_and_prevents_other_item_submission(tmp_path):
    workspace(tmp_path)
    first = dispatch('start', request(tmp_path))
    observation = tmp_path / 'operations/executions' / (first['job_id'] + '.json')
    record = json.loads(observation.read_text())
    observation.write_text(json.dumps({**record, 'state': 'unknown'}))
    with pytest.raises(ValueError, match='budget_reached'):
        dispatch('start', request(tmp_path, 'b'))
    assert len(list((tmp_path / 'operations/jobs').glob('*.json'))) == 1
    dispatch('cancel', {'root': str(tmp_path), 'job_id': first['job_id']})


def test_item_rejects_work_and_input_override_before_dispatch(tmp_path):
    workspace(tmp_path)
    params = request(tmp_path)
    with pytest.raises(ValueError, match='work_id_mismatch'):
        dispatch('start', {**params, 'work_id': 'different'})
    params['execution_context']['item']['input_artifact_ids'] = ['art_1']
    with pytest.raises(ValueError, match='dependency_inputs_missing'):
        dispatch('start', params)
    assert not list((tmp_path / 'operations/jobs').glob('*.json'))


def test_submitted_job_uses_recorded_route_after_current_handler_changes(tmp_path):
    workspace(tmp_path)
    first = dispatch('start', request(tmp_path))
    config = Path(os.environ['CORAGENT_JOB_CONFIG'])
    config.write_text(config.read_text().replace('schedulers.main.executor = "qrun"',
        'schedulers.main.executor = "external"\nschedulers.main.handler = ["/does/not/exist"]'))
    assert dispatch('status', {'root': str(tmp_path), 'job_id': first['job_id']})['state'] != 'unknown'
    assert dispatch('cancel', {'root': str(tmp_path), 'job_id': first['job_id']})['state'] in {'cancelled', 'running', 'succeeded'}


def test_preparation_stages_handoff_artifact_and_rejects_changed_bytes(tmp_path, monkeypatch):
    from research_agent.application.api import execute
    from research_agent.application.executors import prepare_script
    workspace(tmp_path)
    artifact = execute('artifact_create', tmp_path, {'name': 'upstream.txt', 'content': 'verified result'})
    identifier = artifact['artifact_id']
    context = request(tmp_path)['execution_context']
    context['workspace_root'] = str(tmp_path)
    context['item']['input_artifact_ids'] = [identifier]
    monkeypatch.setenv('CORAGENT_TASK_EXECUTION', json.dumps(context))
    script = tmp_path / 'consumer.py'
    script.write_text('print("downstream")\n')
    prepared = prepare_script(os.environ['CORAGENT_JOB_CONFIG'], None, 'validation', script)
    assert prepared['work_id'] == 'a'
    assert prepared['input_artifact_ids'] == [identifier]
    staged = next(row for row in prepared['inputs'] if row['destination'].startswith('inputs/artifacts/'))
    assert Path(staged['source']).read_text() == 'verified result'
    assert prepared['metadata']['resources'] == {'cpus': 1, 'memory_mb': 512}
    context['item']['backend'] = 'structure'
    monkeypatch.setenv('CORAGENT_TASK_EXECUTION', json.dumps(context))
    with pytest.raises(ValueError, match='backend_mismatch'):
        prepare_script(os.environ['CORAGENT_JOB_CONFIG'], None, 'validation', script)
    context['item']['backend'] = 'validation'
    monkeypatch.setenv('CORAGENT_TASK_EXECUTION', json.dumps(context))
    payload = Path(staged['source'])
    payload.chmod(0o600)
    payload.write_text('changed')
    with pytest.raises(ValueError, match='resource_changed'):
        prepare_script(os.environ['CORAGENT_JOB_CONFIG'], None, 'validation', script)
