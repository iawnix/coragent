"""Subjects, corrections and report freshness without scientific truth gates."""
import json
import pytest
from jsonschema import Draft202012Validator
from research_agent.application.api import execute as execute_api, COMMAND_DEFINITIONS
from research_agent.research import results, nodes, relations, views
from research_agent.research.review import build as build_review
from tests.unit.test_job_recovery import workspace


def execute(command, root, params):
    value = execute_api(command, root, params)
    Draft202012Validator(COMMAND_DEFINITIONS[command]['result']).validate(json.loads(json.dumps(value)))
    return value


def material(root, name):
    return execute('artifact_create', root, {'name': name, 'content': name})['artifact_id']


def test_subjects_and_uncertain_checks_survive_publication_and_read(tmp_path):
    workspace(tmp_path)
    target, actual, check = [material(tmp_path, name) for name in ['target', 'actual', 'inconclusive']]
    node = execute('research_create', tmp_path, {'goal': 'Compare identities', 'subjects': {'target': target}})
    saved = execute('research_result', tmp_path, {'node_id': node['node']['id'],
        'subjects': {'target': target, 'calculated': actual}, 'check_refs': [check],
        'observation': 'A structure comparison was inconclusive', 'conclusion': 'The identity remains unresolved'})
    assert saved['result']['subjects']['calculated'] == actual
    assert saved['result']['checks'] == [{'ref': check, 'kind': 'artifact', 'validation': None}]
    assert saved['result_saved'] and not saved['assessment_selected']
    read = execute('research_read', tmp_path, {'ref': saved['result']['id']})
    assert read['result'] == saved['result'] and read['review_notices'] == []
    with pytest.raises(ValueError, match='subjects_require_fixed'):
        execute('research_result', tmp_path, {'node_id': node['node']['id'], 'conclusion': 'No', 'subjects': {'target': node['node']['id']}})


def test_atomic_correction_stale_read_does_not_publish_or_change_progress(tmp_path):
    workspace(tmp_path)
    initial = execute('research_create', tmp_path, {'goal': 'Study'})
    node_id = initial['node']['id']
    old = execute('research_result', tmp_path, {'node_id': node_id, 'conclusion': 'Initial'})['result']
    latest = execute('research_update', tmp_path, {'node_id': node_id, 'note': 'New evidence',
        'progress': 'New observation', 'read_basis': initial['read_basis']})
    request = {'node_id': node_id, 'conclusion': 'Correction', 'supersedes': old['id'], 'as_assessment': True,
               'progress': 'Identity unresolved', 'read_basis': initial['read_basis']}
    with pytest.raises(ValueError, match='revision_conflict'):
        execute('research_result', tmp_path, request)
    assert len(relations.graph(tmp_path)['results']) == 1
    assert nodes.get_node(tmp_path, node_id)['progress'] == 'New observation'
    saved = execute('research_result', tmp_path, {**request, 'read_basis': latest['read_basis']})
    assert saved['assessment_selected'] and saved['node']['progress'] == 'Identity unresolved'
    assert results.get_result(tmp_path, old['id']) == old
    assert execute('research_read', tmp_path, {'ref': saved['result']['id']})['review_notices'] == []
    assert execute('research_read', tmp_path, {'ref': old['id']})['review_notice_count'] > 0
    execute('research_update', tmp_path, {'node_id': node_id, 'note': 'Just a note'})
    assert execute('research_read', tmp_path, {'ref': saved['result']['id']})['review_notices'] == []
    execute('research_update', tmp_path, {'node_id': node_id, 'note': 'Revise goal', 'goal': 'Different target',
                                        'read_basis': saved['read_basis']})
    read = execute('research_read', tmp_path, {'ref': saved['result']['id']})
    assert any(n['code'] == 'node_context_changed' for n in read['review_notices'])
    assert read['result'] == saved['result']
    snapshot = execute('research_read', tmp_path, {})
    assert snapshot['nodes'][0]['review_notice_count'] > 0
    assert 'needs review' in views.documents(tmp_path)[f'research/nodes/{node_id}/README.md']


def test_report_citing_corrected_result_requests_review_without_rewriting(tmp_path):
    workspace(tmp_path)
    source = execute('research_create', tmp_path, {'goal': 'Source'})['node']['id']
    one = execute('research_result', tmp_path, {'node_id': source, 'conclusion': 'Preliminary'})['result']
    report_node = execute('research_create', tmp_path, {'goal': 'Report'})['node']['id']
    report = execute('research_result', tmp_path, {'node_id': report_node, 'conclusion': 'Report', 'inputs': [one['id']]})['result']
    two = execute('research_result', tmp_path, {'node_id': source, 'conclusion': 'Corrected', 'supersedes': one['id']})['result']
    read = execute('research_read', tmp_path, {'ref': report['id']})
    assert {'code': 'cited_result_superseded', 'used': one['id'], 'superseded_by': two['id']} in read['review_notices']
    assert results.get_result(tmp_path, report['id']) == report


def test_research_review_is_bounded_derived_state_and_preserves_source_refs(tmp_path):
    workspace(tmp_path)
    node = execute('research_create', tmp_path, {'goal': 'Compare two recorded alternatives'})['node']['id']
    result = execute('research_result', tmp_path, {'node_id': node,
        'conclusion': 'Preliminary comparison', 'limitations': 'Needs an independent check'})['result']['id']
    review = execute('research_read', tmp_path, {'view': 'review', 'focus_node_ids': [node], 'limit': 8000})
    assert review['schema_version'] == 'research-review/1'
    assert review['state_digest'].startswith('sha256:')
    assert review['review_id'].startswith('review_')
    assert result in review['source_refs']
    assert review['review_status'] == 'current'
    assert review['guidance'].startswith('This is a derived review')
    Draft202012Validator(COMMAND_DEFINITIONS['research_read']['result']).validate(json.loads(json.dumps(review)))


def test_research_review_reports_failed_or_incomplete_jobs_as_follow_up(tmp_path):
    workspace(tmp_path)
    node = execute('research_create', tmp_path, {'goal': 'Inspect execution evidence'})['node']['id']
    review = build_review(tmp_path, focus_node_ids=[node], jobs=[{
        'job_id': 'job_1', 'node_id': node, 'state': 'failed', 'collection_state': 'not_collected',
        'error': 'solver stopped', 'execution_conflict': False,
    }])
    assert review['status'] == 'attention'
    assert any(item['ref'] == 'job_1' for item in review['contradictions'])
    assert any(item['action'] == 'inspect_job' for item in review['follow_up'])


def test_research_review_trigger_marks_new_evidence_pending(tmp_path):
    workspace(tmp_path)
    node = execute('research_create', tmp_path, {'goal': 'Review new evidence'})['node']['id']
    review = execute('research_read', tmp_path, {
        'view': 'review', 'focus_node_ids': [node], 'trigger': 'new_evidence', 'limit': 8000,
    })
    assert review['trigger'] == 'new_evidence'
    assert review['review_status'] == 'pending'
