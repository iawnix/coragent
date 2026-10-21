"""Subjects, corrections and report freshness without scientific truth gates."""
import json
import pytest
from jsonschema import Draft202012Validator
from research_agent.application.api import execute as execute_api, COMMAND_DEFINITIONS
from research_agent.research import results, nodes, relations, views
from research_agent.research.brief import build as build_review
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


def test_research_context_is_bounded_derived_state_and_preserves_source_refs(tmp_path):
    workspace(tmp_path)
    node = execute('research_create', tmp_path, {'goal': 'Compare two recorded alternatives'})['node']['id']
    result = execute('research_result', tmp_path, {'node_id': node,
        'conclusion': 'Preliminary comparison', 'limitations': 'Needs an independent check'})['result']['id']
    review = execute('research_read', tmp_path, {'view': "brief", 'focus_node_ids': [node], 'limit': 8000})
    assert review['schema_version'] == 'research-brief/1'
    assert review['state_digest'].startswith('sha256:')
    assert review['brief_id'].startswith('brief_')
    assert result in review['source_refs']
    assert review['projection_status'] == 'complete'
    assert review['guidance'].startswith('This is a derived brief')
    Draft202012Validator(COMMAND_DEFINITIONS['research_read']['result']).validate(json.loads(json.dumps(review)))


def test_research_context_reports_failed_or_incomplete_jobs_as_follow_up(tmp_path):
    workspace(tmp_path)
    node = execute('research_create', tmp_path, {'goal': 'Inspect execution evidence'})['node']['id']
    review = build_review(tmp_path, focus_node_ids=[node], jobs=[{
        'job_id': 'job_1', 'node_id': node, 'state': 'failed', 'collection_state': 'not_collected',
        'error': 'solver stopped', 'execution_conflict': False,
    }])
    assert review['status'] == 'attention'
    assert any(item['ref'] == 'job_1' for item in review['contradictions'])
    assert any(item['action'] == 'inspect_job' for item in review['follow_up'])


def test_brief_refresh_depends_on_scoped_facts_not_global_activity(tmp_path):
    workspace(tmp_path)
    selected = execute('research_create', tmp_path, {'goal': 'Selected'})
    other = execute('research_create', tmp_path, {'goal': 'Unrelated'})
    params = {'view': 'brief', 'focus_node_ids': [selected['node']['id']], 'limit': 8000}
    initial = execute('research_read', tmp_path, params)
    execute('research_update', tmp_path, {'node_id': other['node']['id'], 'note': 'Change other progress',
        'progress': 'Unrelated progress', 'read_basis': other['read_basis']})
    assert execute('research_read', tmp_path, params)['state_digest'] == initial['state_digest']
    execute('research_update', tmp_path, {'node_id': selected['node']['id'], 'note': 'Change focus',
        'progress': 'Relevant progress', 'read_basis': selected['read_basis']})
    assert execute('research_read', tmp_path, params)['state_digest'] != initial['state_digest']


def test_brief_tracks_direct_dependencies(tmp_path):
    workspace(tmp_path)
    parent = execute('research_create', tmp_path, {'goal': 'Root'})
    child = execute('research_create', tmp_path, {'goal': 'Dependency'})
    execute('research_update', tmp_path, {'node_id': parent['node']['id'], 'note': 'Bind dependency',
        'add_relations': [{'kind': 'requires', 'target': child['node']['id']}], 'read_basis': parent['read_basis']})
    params = {'view': 'brief', 'focus_node_ids': [parent['node']['id']], 'limit': 2048}
    first = execute('research_read', tmp_path, params)
    execute('research_result', tmp_path, {'node_id': child['node']['id'], 'conclusion': 'Dependency result'})
    second = execute('research_read', tmp_path, params)
    assert first['state_digest'] != second['state_digest']


def test_brief_tracks_candidates_that_do_not_fit_in_context(tmp_path):
    from research_agent.research.brief_selection import build as select
    workspace(tmp_path)
    children = [execute('research_create', tmp_path, {'goal': f'Dependency {i}'}) for i in range(12)]
    parent = execute('research_create', tmp_path, {'goal': 'Root',
        'relations': [{'kind': 'requires', 'target': child['node']['id']} for child in children]})
    focus = [parent['node']['id']]
    selection = select(tmp_path, max_bytes=4096, focus_node_ids=focus)
    included = {node['id'] for node in selection['nodes']}
    omitted = next(child for child in children if child['node']['id'] not in included)
    assert selection['bounds']['omitted']['nodes'] > 0
    first = build_review(tmp_path, max_bytes=4096, focus_node_ids=focus)
    execute('research_update', tmp_path, {'node_id': omitted['node']['id'], 'note': 'New evidence',
        'progress': 'Changed omitted dependency', 'read_basis': omitted['read_basis']})
    second = build_review(tmp_path, max_bytes=4096, focus_node_ids=focus)
    assert first['state_digest'] != second['state_digest']


def test_incomplete_projection_is_not_a_model_review_state(tmp_path):
    workspace(tmp_path)
    brief = build_review(tmp_path, projection={'pending': 1})
    assert brief['projection_status'] == 'incomplete'
    assert 'review_status' not in brief and 'trigger' not in brief
    with pytest.raises(Exception):
        execute('research_read', tmp_path, {'view': 'review'})
    with pytest.raises(Exception):
        execute('research_read', tmp_path, {'view': 'brief', 'trigger': 'new_evidence'})
