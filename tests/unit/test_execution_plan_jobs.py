"""Work-item admission shares Job Manager's durable intent and observations."""
import json
import hashlib
import os
import time
from pathlib import Path
import pytest

from research_agent.application.execution import dispatch
from tests.unit.test_job_recovery import workspace


def request(root, identifier="a"):
    selection = dispatch('resolve_target', {'root': str(root)})
    return {'root': str(root), 'request_id': 'plan-' + identifier, 'work_id': identifier,
            'session_id': 'plan-session', 'user_task_id': 'task_1',
            'command': ['/bin/sh', '-c', 'sleep 1; printf done-' + identifier],
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
    duplicate = dispatch('start', {**params, 'request_id': 'different-attempt'})
    assert duplicate['code'] == 'duplicate_execution' and duplicate['job_id'] == first['job_id']
    dispatch('cancel', {'root': str(tmp_path), 'job_id': first['job_id']})


def test_unknown_dispatch_holds_budget_and_prevents_other_item_submission(tmp_path):
    workspace(tmp_path)
    first = dispatch('start', request(tmp_path))
    observation = tmp_path / 'operations/executions' / (first['job_id'] + '.json')
    record = json.loads(observation.read_text())
    observation.write_text(json.dumps({**record, 'state': 'unknown'}))
    deferred = dispatch('start', request(tmp_path, 'b'))
    assert deferred['code'] == 'execution_task_capacity_reached'
    assert deferred['used'] == deferred['limit'] == 1
    assert deferred['job_ids'] == [first['job_id']] and deferred['retryable']
    assert len(list((tmp_path / 'operations/jobs').glob('*.json'))) == 1
    assert not list((tmp_path / 'operations/staging').glob('*.json'))
    assert not (tmp_path / 'runs/jobs/job_2').exists()
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


def finish(root, job_id):
    for _ in range(200):
        status = dispatch('status', {'root': str(root), 'job_id': job_id})
        if status['state'] in {'failed', 'succeeded', 'cancelled', 'timed_out'}:
            return status
        time.sleep(.02)
    raise AssertionError('test Job did not finish')


def test_capacity_deferral_can_resume_same_request_without_consuming_total_budget(tmp_path):
    workspace(tmp_path)
    first = dispatch('start', request(tmp_path))
    second_request = request(tmp_path, 'b')
    deferred = dispatch('start', second_request)
    assert deferred['code'] == 'execution_task_capacity_reached'
    finish(tmp_path, first['job_id'])
    second = dispatch('start', second_request)
    assert second['job_id'] != first['job_id']
    assert dispatch('start', second_request)['job_id'] == second['job_id']
    finish(tmp_path, second['job_id'])
    refused = dispatch('start', request(tmp_path, 'c'))
    assert refused['code'] == 'execution_task_job_limit_reached'
    assert refused['used'] == refused['limit'] == 2 and not refused['retryable']
    assert len(list((tmp_path / 'operations/jobs').glob('*.json'))) == 2
    second_request['execution_context']['policy']['max_attempts'] = None
    assert dispatch('start', second_request)['job_id'] == second['job_id']


def test_no_implicit_task_total_or_concurrency_cap(tmp_path):
    workspace(tmp_path)
    params = request(tmp_path)
    params['execution_context']['policy'] = {'max_in_flight': None, 'max_attempts': None}
    first = dispatch('start', params)
    intent = json.loads((tmp_path / 'operations/jobs' / (first['job_id'] + '.json')).read_text())
    observation = json.loads((tmp_path / 'operations/executions' / (first['job_id'] + '.json')).read_text())
    # Synthetic historical Jobs avoid running 100 processes merely to exercise
    # cumulative admission. The first real Job also holds an in-flight slot.
    for number in range(1000, 1100):
        job_id = f'job_{number}'
        (tmp_path / 'operations/jobs' / (job_id + '.json')).write_text(json.dumps({
            **intent, 'job_id': job_id, 'request_id': job_id, 'execution_fingerprint': job_id,
            'work_id': job_id, 'execution_item': {'id': job_id, 'work_id': job_id}}))
        (tmp_path / 'operations/executions' / (job_id + '.json')).write_text(json.dumps({
            **observation, 'job_id': job_id, 'state': 'succeeded'}))
    next_request = request(tmp_path, 'b')
    next_request['execution_context']['policy'] = params['execution_context']['policy']
    second = dispatch('start', next_request)
    assert second['job_id'] != first['job_id']
    finish(tmp_path, first['job_id'])
    finish(tmp_path, second['job_id'])


def test_retry_limit_counts_only_the_same_work_and_preserves_failed_attempts(tmp_path):
    workspace(tmp_path)
    params = request(tmp_path)
    params['execution_context']['policy'] = {'max_in_flight': None, 'max_attempts': None, 'max_retries_per_work': 1}
    params['command'] = ['/bin/sh', '-c', 'exit 3']
    first = dispatch('start', params)
    assert finish(tmp_path, first['job_id'])['state'] == 'failed'
    retried = {**params, 'request_id': 'retry-a', 'command': ['/bin/sh', '-c', 'exit 4']}
    second = dispatch('start', retried)
    assert finish(tmp_path, second['job_id'])['state'] == 'failed'
    third = dispatch('start', {**params, 'request_id': 'retry-a-again', 'command': ['/bin/sh', '-c', 'exit 5']})
    assert third['code'] == 'execution_work_retry_limit_reached'
    assert third['used'] == third['limit'] == 1
    assert third['job_ids'] == [first['job_id'], second['job_id']]
    independent = request(tmp_path, 'b')
    independent['execution_context']['policy'] = params['execution_context']['policy']
    independent['command'] = ['/bin/sh', '-c', 'printf independent']
    other = dispatch('start', independent)
    assert finish(tmp_path, other['job_id'])['state'] == 'succeeded'
    assert len(list((tmp_path / 'operations/jobs').glob('*.json'))) == 3


@pytest.mark.parametrize('state,conflict', [('unknown', False), ('succeeded', True), ('succeeded', False)])
def test_same_item_cannot_be_retried_while_uncertain_or_successful(tmp_path, state, conflict):
    workspace(tmp_path)
    params = request(tmp_path)
    params['execution_context']['policy'] = {'max_in_flight': None, 'max_attempts': None}
    first = dispatch('start', params)
    finish(tmp_path, first['job_id'])
    path = tmp_path / 'operations/executions' / (first['job_id'] + '.json')
    path.write_text(json.dumps({**json.loads(path.read_text()), 'state': state, 'execution_conflict': conflict}))
    with pytest.raises(ValueError, match='execution_item_already_submitted'):
        dispatch('start', {**params, 'request_id': 'unsafe-retry', 'command': ['/bin/sh', '-c', 'printf changed']})


def test_raw_retries_require_settled_work_even_without_task_concurrency_limit(tmp_path):
    workspace(tmp_path)
    params = request(tmp_path)
    params['execution_context'].pop('item')
    params['execution_context']['policy'] = {'max_in_flight': None, 'max_attempts': None, 'max_retries_per_work': 1}
    first = dispatch('start', params)
    finish(tmp_path, first['job_id'])
    path = tmp_path / 'operations/executions' / (first['job_id'] + '.json')
    path.write_text(json.dumps({**json.loads(path.read_text()), 'state': 'unknown'}))
    with pytest.raises(ValueError, match='execution_work_unsettled'):
        dispatch('start', {**params, 'request_id': 'raw-retry', 'command': ['/bin/sh', '-c', 'printf corrected']})
    with pytest.raises(ValueError, match='repeat_predecessor_unsettled'):
        dispatch('start', {**params, 'request_id': 'raw-repeat', 'repeat': {
            'predecessor_job_id': first['job_id'], 'reason': 'Explicit repeat', 'budget': 'one retry'}})
    assert len(list((tmp_path / 'operations/jobs').glob('*.json'))) == 1


def test_zero_retry_allowance_permits_first_attempt_and_legacy_digests_still_replay(tmp_path):
    from research_agent.application.execution import _request_digest
    workspace(tmp_path)
    params = request(tmp_path)
    params['execution_context']['policy'] = {'max_in_flight': None, 'max_attempts': None, 'max_retries_per_work': 0}
    params['command'] = ['/bin/sh', '-c', 'exit 3']
    first = dispatch('start', params)
    assert finish(tmp_path, first['job_id'])['state'] == 'failed'
    # Reproduce the pre-upgrade digest using this fixture's recorded target.
    path = tmp_path / 'operations/jobs' / (first['job_id'] + '.json')
    intent = json.loads(path.read_text())
    intent.pop('request_digest_version')
    intent['request_digest'] = _request_digest({**params, 'job_id': first['job_id'],
        'execution_target': params['execution_context']['selection']['target']}, include_policy=True)
    path.write_text(json.dumps(intent))
    assert dispatch('start', params)['job_id'] == first['job_id']
    blocked = dispatch('start', {**params, 'request_id': 'no-retries', 'command': ['/bin/sh', '-c', 'exit 4']})
    assert blocked['code'] == 'execution_work_retry_limit_reached'
    assert blocked['used'] == blocked['limit'] == 0


@pytest.mark.parametrize('form', ['file', 'reference'])
def test_prepared_repeat_preserves_work_and_bytes_but_gets_an_idempotent_attempt(tmp_path, form):
    from research_agent.application.references import prepare_job
    workspace(tmp_path)
    params = request(tmp_path)
    params['command'] = ['/bin/sh', '-c', 'exit 3']
    params['execution_context']['policy'] = {'max_in_flight': None, 'max_attempts': None, 'max_retries_per_work': 1}
    transport = {key: params[key] for key in ('root', 'session_id', 'user_task_id', 'execution_context')}
    payload = {key: value for key, value in params.items() if key not in transport}
    path = tmp_path / 'prepared-request.json'
    path.write_text(json.dumps(payload))
    original = path.read_bytes()
    prepared = {'request_file': str(path), 'request_sha256': hashlib.sha256(original).hexdigest()}
    if form == 'reference':
        prepared = {'prepared_ref': prepare_job(tmp_path, prepared)['prepared_ref']}
    first = dispatch('start', {**prepared, **transport})
    assert finish(tmp_path, first['job_id'])['state'] == 'failed'
    repeat = {'predecessor_job_id': first['job_id'], 'reason': 'Retry the settled failure', 'budget': 'one retry'}
    second = dispatch('start', {**prepared, **transport, 'repeat': repeat})
    assert second['job_id'] != first['job_id']
    assert finish(tmp_path, second['job_id'])['state'] == 'failed'
    assert dispatch('start', {**prepared, **transport, 'repeat': repeat})['job_id'] == second['job_id']
    refused = dispatch('start', {**prepared, **transport, 'repeat': {**repeat, 'predecessor_job_id': second['job_id']}})
    assert refused['code'] == 'execution_work_retry_limit_reached'
    intents = [json.loads(p.read_text()) for p in (tmp_path / 'operations/jobs').glob('*.json')]
    assert len(intents) == 2 and {row['work_id'] for row in intents} == {'a'}
    assert path.read_bytes() == original
