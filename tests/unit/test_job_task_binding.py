import json
import sys

import pytest

from research_agent.application.api import execute
from research_agent.application.execution import dispatch
from research_agent.application.job_monitor import command
from tests.unit.test_job_recovery import workspace


def test_task_ownership_survives_job_submission_and_read_only_pagination(tmp_path):
    workspace(tmp_path)
    for suffix, task in [('a', 'task_1'), ('b', 'task_2')]:
        dispatch('start', {'root': str(tmp_path), 'request_id': 'job_' + suffix,
                          'session_id': 'session_owner', 'user_task_id': task,
                          'command': [sys.executable, '-c', 'pass # ' + suffix]})
    before = {p: p.read_bytes() for p in (tmp_path / 'operations').rglob('*.json')}
    first = execute('job.list', tmp_path, {'session_id': 'session_owner', 'limit': 1})
    assert first['jobs'][0]['user_task_id'] == 'task_1'
    assert first['next_cursor'] == 'job_1'
    second = execute('job.list', tmp_path, {'session_id': 'session_owner', 'cursor': first['next_cursor']})
    assert [row['job_id'] for row in second['jobs']] == ['job_2']
    assert second['next_cursor'] is None
    selected = execute('job.list', tmp_path, {'user_task_id': 'task_1'})
    assert [row['job_id'] for row in selected['jobs']] == ['job_1']
    assert execute('job.list', tmp_path, {'session_id': 'session_other'})['jobs'] == []
    assert {p: p.read_bytes() for p in before} == before
    bindings = command(tmp_path, 'list', {})['monitors']
    assert {row['job_id']: row['user_task_id'] for row in bindings} == {
        'job_1': 'task_1', 'job_2': 'task_2'}


def test_submission_identity_cannot_be_rebound_to_another_task(tmp_path):
    workspace(tmp_path)
    params = {'root': str(tmp_path), 'request_id': 'job_bound', 'session_id': 'session_owner',
              'user_task_id': 'task_1', 'command': [sys.executable, '-c', 'pass']}
    dispatch('start', params)
    with pytest.raises(ValueError, match='different parameters'):
        dispatch('start', {**params, 'user_task_id': 'task_2'})
    intent = json.loads((tmp_path / 'operations/jobs/job_1.json').read_text())
    assert intent['user_task_id'] == 'task_1'


def test_task_ownership_is_not_a_model_supplied_metadata_field(tmp_path):
    workspace(tmp_path)
    with pytest.raises(ValueError, match='runtime_only'):
        dispatch('start', {'root': str(tmp_path), 'request_id': 'job_forged',
                          'command': [sys.executable, '-c', 'pass'],
                          'metadata': {'user_task_id': 'task_forged'}})


def test_job_pages_follow_numeric_order(tmp_path):
    from research_agent.application.job_state import list_executions
    workspace(tmp_path)
    directory = tmp_path / 'operations/executions'
    directory.mkdir()
    for number in range(1, 13):
        (directory / f'job_{number}.json').write_text(json.dumps({'job_id': f'job_{number}', 'state': 'succeeded'}))
    page = list_executions(tmp_path, limit=9)
    assert [row['job_id'] for row in page['jobs']] == [f'job_{n}' for n in range(1, 10)]
    next_page = list_executions(tmp_path, cursor=page['next_cursor'])
    assert [row['job_id'] for row in next_page['jobs']] == ['job_10', 'job_11', 'job_12']
