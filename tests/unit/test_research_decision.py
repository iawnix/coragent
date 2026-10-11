"""Request views preserve decisions and provenance without replaying the journal."""
import json

import pytest
from jsonschema import Draft202012Validator

from research_agent.application.api import execute, COMMAND_DEFINITIONS
from research_agent.application.memory_context import read
from research_agent.research import basis, nodes, records, results
from research_agent.research.decision_view import build, size
from tests.unit.test_job_recovery import workspace


def create(root, title, **kwargs):
    return nodes.create(root, {'title': title, 'goal': title, **kwargs})


def test_scope_ignores_unrelated_history_and_does_not_change_explicit_reads(tmp_path):
    workspace(tmp_path)
    root = create(tmp_path, 'Original objective')['node']['id']
    focus = create(tmp_path, 'Current question', plan='Check measurements', relations=[{'kind': 'part_of', 'target': root}])['node']['id']
    before = read(tmp_path, view='decision', entry_node_ids=[root], focus_node_ids=[focus])
    for i in range(12):
        other = create(tmp_path, f'Unrelated work {i}', session_id='other')['node']['id']
        records.record_event(tmp_path, {'kind': 'job', 'title': 'Log', 'node_id': other, 'content': 'irrelevant output ' * 100})
    after = read(tmp_path, view='decision', entry_node_ids=[root], focus_node_ids=[focus])
    assert before == after
    assert {n['id'] for n in after['nodes']} == {root, focus}
    assert 'new_records' not in after
    assert read(tmp_path)['schema_version'] == 'research-snapshot/3'
    assert read(tmp_path, ref=focus, field='plan')['value'] == 'Check measurements'
    Draft202012Validator(COMMAND_DEFINITIONS['research.read']['result']).validate(after)


def test_fallback_is_session_navigation_not_a_task_binding(tmp_path):
    workspace(tmp_path)
    mine = create(tmp_path, 'My question', session_id='mine')['node']['id']
    create(tmp_path, 'Other question', session_id='other')
    view = read(tmp_path, view='decision', session_id='mine')
    assert [n['id'] for n in view['nodes']] == [mine]
    assert view['scope'] == {'selection': 'session_recent_fallback', 'entry_count': 0, 'focus_count': 0}
    assert read(tmp_path, view='decision', session_id='new')['nodes'] == []


def test_assessment_and_limitations_are_not_replaced_by_latest_output(tmp_path):
    workspace(tmp_path)
    initial = create(tmp_path, 'Compare models')
    ref = initial['node']['id']
    first = results.publish(tmp_path, {'node_id': ref, 'conclusion': 'Only model A was evaluated.',
        'limitations': 'Model B remains untested.', 'as_assessment': True, 'read_basis': initial['read_basis']})['result']
    latest = results.publish(tmp_path, {'node_id': ref, 'conclusion': 'A new measurement requires review.', 'supersedes': first['id']})['result']
    view = read(tmp_path, view='decision', focus_node_ids=[ref])
    card = view['nodes'][0]
    assert card['assessment']['ref'] == first['id']
    assert card['assessment']['limitations'] == 'Model B remains untested.'
    assert card['other_results'][0]['ref'] == latest['id']
    assert card['review_notice_count'] > 0
    assert any(n['code'] == 'result_superseded' for n in card['review_notices'])
    assert nodes.get_node(tmp_path, ref)['assessment_ref'] == first['id']


def test_events_merge_into_current_jobs_and_explicit_waits_survive_scope(tmp_path):
    workspace(tmp_path)
    focus = create(tmp_path, 'Current question')['node']['id']
    unrelated = create(tmp_path, 'Separate question')['node']['id']
    jobs = [{'job_id': 'job_failed', 'node_id': focus, 'state': 'failed', 'collection_state': 'not_collected', 'error': 'Invalid parameters'},
            {'job_id': 'job_elsewhere', 'node_id': unrelated, 'state': 'running', 'collection_state': 'not_collected'}]
    events = [{'event_id': 'event_1', 'job_id': 'job_failed', 'node_id': focus, 'state': 'running'},
              {'event_id': 'event_2', 'job_id': 'job_failed', 'node_id': focus, 'state': 'failed'}]
    view = build(tmp_path, focus_node_ids=[focus], jobs=jobs, events=events, waited_job_ids=['job_missing'])
    assert {j['job_id'] for j in view['jobs']} == {'job_failed', 'job_missing'}
    failed = next(j for j in view['jobs'] if j['job_id'] == 'job_failed')
    assert failed['state'] == 'failed' and failed['error'] == 'Invalid parameters'
    assert failed['event_ids'] == ['event_1', 'event_2']
    assert view['wake_events'] == {'requested': 2, 'included': 2, 'omitted': 0}
    assert next(j for j in view['jobs'] if j['job_id'] == 'job_missing')['state'] == 'unavailable'


@pytest.mark.parametrize('budget', [2048, 3000, 8000, 16000])
def test_budget_and_partial_field_receipts(tmp_path, budget):
    workspace(tmp_path)
    initial = create(tmp_path, '研究问题', plan='第一段计划。\n' * 500, proposal='A hypothesis still requiring validation')
    ref = initial['node']['id']
    view = read(tmp_path, view='decision', focus_node_ids=[ref], session_id='reader', limit=budget)
    assert size(view) <= budget
    assert view['nodes'][0]['id'] == ref
    assert 'plan' in view['nodes'][0]['omitted_fields']
    assert 'proposal' in view['nodes'][0]['omitted_fields']
    basis.observe(tmp_path, {'session_id': 'reader', 'read_basis': view['read_basis']})
    with pytest.raises(ValueError, match='fields_not_read'):
        nodes.update(tmp_path, {'node_id': ref, 'session_id': 'reader', 'note': 'Change', 'plan': 'New plan'})
    # The full title was visible, unlike the plan and undisplayed proposal.
    basis.check(tmp_path, nodes.get_node(tmp_path, ref), {'session_id': 'reader'}, {'title'})
    with pytest.raises(ValueError, match='fields_not_read'):
        basis.check(tmp_path, nodes.get_node(tmp_path, ref), {'session_id': 'reader'}, {'proposal'})
    assert read(tmp_path, ref=ref, field='plan', limit=32000)['value'] == initial['node']['plan']


def test_multiple_focuses_receive_detail_and_do_not_expand_containment_tree(tmp_path):
    workspace(tmp_path)
    first = create(tmp_path, 'First focus', plan='Measure A')['node']['id']
    second = create(tmp_path, 'Second focus', plan='Measure B')['node']['id']
    child = create(tmp_path, 'Child', relations=[{'kind': 'part_of', 'target': first}])['node']['id']
    deeper = create(tmp_path, 'Deep unrelated detail', relations=[{'kind': 'part_of', 'target': child}])['node']['id']
    view = read(tmp_path, view='decision', focus_node_ids=[first, second])
    cards = {n['id']: n for n in view['nodes']}
    assert deeper not in cards
    assert cards[first]['plan'] == 'Measure A' and cards[second]['plan'] == 'Measure B'


def test_journal_growth_does_not_increase_decision_view(tmp_path):
    workspace(tmp_path)
    ref = create(tmp_path, 'Inspect measurement', plan='Check the uncertainty')['node']['id']
    initial = build(tmp_path, focus_node_ids=[ref])
    for i in range(40):
        records.record_event(tmp_path, {'kind': 'job', 'title': f'Artifact registered {i}', 'node_id': ref, 'content': 'Execution log ' * 80})
    compact = build(tmp_path, focus_node_ids=[ref])
    legacy = read(tmp_path, focus_node_ids=[ref])
    assert compact == initial
    assert size(compact) < size(legacy) * 0.5


def test_internal_view_parameters_are_not_model_parameters_and_reject_mixed_reads(tmp_path):
    workspace(tmp_path)
    ref = create(tmp_path, 'Question')['node']['id']
    with pytest.raises(ValueError, match='decision_view_requires_snapshot'):
        execute('research.read', tmp_path, {'view': 'decision', 'ref': ref})


@pytest.mark.parametrize('budget', [2048, 8000])
def test_execution_and_relation_flood_keep_focus_failure_and_omission_counts(tmp_path, budget):
    workspace(tmp_path)
    focus = create(tmp_path, 'Focused question', plan='Inspect failed calculation')['node']['id']
    for i in range(15):
        create(tmp_path, f'Child {i}', relations=[{'kind': 'part_of', 'target': focus}])
    jobs = [{'job_id': f'job_{i:03}', 'node_id': focus, 'state': 'failed', 'collection_state': 'not_collected', 'error': 'Invalid parameters'} for i in range(40)]
    events = [{'event_id': 'event_' + j['job_id'], 'job_id': j['job_id'], 'node_id': focus, 'state': 'failed'} for j in jobs]
    view = build(tmp_path, max_bytes=budget, focus_node_ids=[focus], jobs=jobs, events=events)
    assert size(view) <= budget
    assert view['nodes'][0]['id'] == focus
    assert view['jobs'][0]['error'] == 'Invalid parameters'
    assert view['bounds']['omitted']['nodes'] + len(view['nodes']) == 16
    assert view['bounds']['omitted']['jobs'] + len(view['jobs']) == 40
    assert view['wake_events']['included'] + view['wake_events']['omitted'] == 40


def test_current_assessment_dependencies_and_stale_receipts_remain_explicit(tmp_path):
    workspace(tmp_path)
    source = create(tmp_path, 'Measurement')['node']['id']
    evidence = results.publish(tmp_path, {'node_id': source, 'conclusion': 'Measured with uncertainty'})['result']['id']
    target = create(tmp_path, 'Interpretation')
    ref = target['node']['id']
    selected = results.publish(tmp_path, {'node_id': ref, 'conclusion': 'Conditional interpretation', 'inputs': [evidence],
                                        'as_assessment': True, 'read_basis': target['read_basis']})
    view = read(tmp_path, view='decision', focus_node_ids=[ref], session_id='reader')
    assert {n['id'] for n in view['nodes']} == {ref, source}
    assert any(e['target'] == evidence for e in view['relations'])
    basis.observe(tmp_path, {'session_id': 'reader', 'read_basis': view['read_basis']})
    nodes.update(tmp_path, {'node_id': ref, 'note': 'Changed', 'goal': 'Different question', 'read_basis': selected['read_basis']})
    with pytest.raises(ValueError, match='revision_conflict'):
        nodes.update(tmp_path, {'node_id': ref, 'session_id': 'reader', 'note': 'Update', 'status': 'closed'})
