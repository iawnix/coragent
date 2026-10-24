"""Recent process notes refresh scoped context without manufacturing conclusions."""
import json

import pytest

from research_agent.application.api import execute
from research_agent.research import nodes, relations
from research_agent.research.brief import build
from research_agent.research.brief_selection import build as select
from research_agent.research.records import append_record, recent_notes, record
from tests.unit.test_job_recovery import workspace


def create(root, goal, **params):
    return execute('research_create', root, {'goal': goal, **params})


def add_note(root, node_id, text):
    return execute('research_update', root, {'node_id': node_id, 'note': text})


def read_brief(root, node_id, limit=8000):
    return execute('research_read', root, {'view': 'brief', 'focus_node_ids': [node_id], 'limit': limit})


def test_recent_notes_share_immutable_sequence_order_and_full_history_count(tmp_path):
    workspace(tmp_path)
    selected = create(tmp_path, 'Selected question')
    other = create(tmp_path, 'Other question')
    node_id = selected['node']['id']
    saved = [add_note(tmp_path, node_id, f'Observation {index}')['ref'] for index in range(5)]
    add_note(tmp_path, other['node']['id'], 'Unrelated observation')
    notes = recent_notes(tmp_path, [node_id])[node_id]
    assert notes['total'] == 5
    assert [item['ref'] for item in notes['records']] == saved[-3:][::-1]
    assert all(item == record(tmp_path, item['ref']) for item in notes['records'])
    assert [item['sequence'] for item in notes['records']] == sorted(
        (item['sequence'] for item in notes['records']), reverse=True)
    assert recent_notes(tmp_path, [node_id], limit_per_node=1)[node_id]['records'][0]['ref'] == saved[-1]


def test_plain_note_refreshes_only_its_selected_scope_without_changing_node_revision(tmp_path):
    workspace(tmp_path)
    selected = create(tmp_path, 'Determine the recorded target')
    other = create(tmp_path, 'Unrelated question')
    node_id = selected['node']['id']
    initial = read_brief(tmp_path, node_id)
    add_note(tmp_path, other['node']['id'], 'A separate investigation advanced')
    assert read_brief(tmp_path, node_id)['state_digest'] == initial['state_digest']
    saved = add_note(tmp_path, node_id, 'The latest attempt stopped before comparison')
    refreshed = read_brief(tmp_path, node_id)
    assert refreshed['state_digest'] != initial['state_digest']
    assert nodes.get_node(tmp_path, node_id)['revision'] == selected['node']['revision']
    assert nodes.get_node(tmp_path, node_id)['assessment_ref'] is None
    assert relations.graph(tmp_path)['results'] == {}
    finding = next(item for item in refreshed['findings'] if item['ref'] == saved['ref'])
    assert finding['kind'] == 'note' and finding['selected_assessment'] is False
    assert finding['summary'] == 'The latest attempt stopped before comparison'
    assert saved['ref'] in refreshed['source_refs']
    assert read_brief(tmp_path, node_id)['state_digest'] == refreshed['state_digest']


def test_brief_restores_question_assessment_recent_note_and_pending_job_separately(tmp_path):
    workspace(tmp_path)
    selected = create(tmp_path, 'Compare the two candidates', plan='Inspect recorded structures')
    node_id = selected['node']['id']
    result = execute('research_result', tmp_path, {'node_id': node_id, 'conclusion': 'Comparison remains inconclusive',
        'as_assessment': True, 'read_basis': selected['read_basis']})['result']
    note = add_note(tmp_path, node_id, 'A follow-up calculation is queued')
    brief = build(tmp_path, focus_node_ids=[node_id], jobs=[
        {'job_id': 'job_1', 'node_id': node_id, 'state': 'queued', 'collection_state': 'not_collected'}])
    findings = {item['ref']: item for item in brief['findings']}
    assert findings[node_id]['summary'] == 'Compare the two candidates'
    assert findings[node_id]['assessment_ref'] == result['id']
    assert findings[result['id']]['selected_assessment'] is True
    assert findings[result['id']]['summary'] == 'Comparison remains inconclusive'
    assert findings[note['ref']]['selected_assessment'] is False
    assert findings['job_1']['state'] == 'queued'
    assert brief['coverage']['notes'] == 1
    assert 'Notes are process records' in brief['guidance']


def test_note_citations_use_explicit_references_and_do_not_parse_its_text(tmp_path):
    workspace(tmp_path)
    node_id = create(tmp_path, 'Inspect evidence')['node']['id']
    artifact = execute('artifact_create', tmp_path, {'name': 'observation', 'content': 'raw observation'})['artifact_id']
    note = append_record(tmp_path, origin='agent', kind='note', title='Process note',
        content='The string artifact_99999 is an unverified example, not evidence.',
        references=[artifact], node_id=node_id)
    brief = read_brief(tmp_path, node_id)
    finding = next(item for item in brief['findings'] if item['ref'] == note['ref'])
    assert finding['references'] == [artifact]
    assert artifact in brief['source_refs']
    assert 'artifact_99999' not in brief['source_refs']
    assert nodes.get_node(tmp_path, node_id)['assessment_ref'] is None


@pytest.mark.parametrize('budget', [2048, 4096, 8000])
def test_large_notes_are_bounded_and_history_remains_paginated(tmp_path, budget):
    workspace(tmp_path)
    node_id = create(tmp_path, 'Review the latest attempt')['node']['id']
    refs = [add_note(tmp_path, node_id, f'Attempt {index}. ' + '步骤与观察。' * 2000)['ref'] for index in range(5)]
    brief = read_brief(tmp_path, node_id, budget)
    assert len(json.dumps(brief, ensure_ascii=False, separators=(',', ':')).encode()) <= budget
    included = [item for item in brief['findings'] if item['kind'] == 'note']
    assert brief['coverage']['notes'] == len(included)
    assert brief['coverage']['notes'] + brief['coverage']['omitted']['notes'] == 5
    assert len(included) <= 3
    assert all(item['content_omitted'] for item in included)
    if included:
        assert included[0]['ref'] == refs[-1]
    if budget == 8000:
        assert [item['ref'] for item in included] == refs[-3:][::-1]
    page = execute('research_search', tmp_path, {'node_id': node_id, 'kind': 'note', 'limit': 2})
    assert page['total'] == 5 and page['next_offset'] == 2
    assert [item['ref'] for item in page['records']] == refs[-2:][::-1]
    next_page = execute('research_search', tmp_path, {'node_id': node_id, 'kind': 'note', 'limit': 2, 'offset': page['next_offset']})
    assert next_page['records'][0]['ref'] == refs[-3]
    if included:
        assert len(record(tmp_path, refs[-1])['content']) > len(included[0]['summary'])


def test_note_on_an_omitted_direct_dependency_still_refreshes_state(tmp_path):
    workspace(tmp_path)
    dependencies = [create(tmp_path, f'Dependency {index}') for index in range(12)]
    parent = create(tmp_path, 'Main question', relations=[
        {'kind': 'requires', 'target': child['node']['id']} for child in dependencies])
    focus = [parent['node']['id']]
    selection = select(tmp_path, max_bytes=4096, focus_node_ids=focus)
    visible = {item['id'] for item in selection['nodes']}
    omitted = next(item['node']['id'] for item in dependencies if item['node']['id'] not in visible)
    initial = build(tmp_path, max_bytes=4096, focus_node_ids=focus)
    note = add_note(tmp_path, omitted, 'A dependency needs another measurement')
    updated = build(tmp_path, max_bytes=4096, focus_node_ids=focus)
    assert updated['state_digest'] != initial['state_digest']
    assert updated['coverage']['omitted']['notes'] == 1
    assert note['ref'] not in {item['ref'] for item in updated['findings']}


@pytest.mark.parametrize('selected_kind', ['note', 'record'])
def test_only_explicit_selection_marks_a_note_or_other_record_as_assessment(tmp_path, selected_kind):
    workspace(tmp_path)
    created = create(tmp_path, 'Evaluate the record')
    node_id = created['node']['id']
    note = add_note(tmp_path, node_id, 'Tentative interpretation, still needs checking')
    selected_ref = note['ref'] if selected_kind == 'note' else created['ref']
    execute('research_update', tmp_path, {'node_id': node_id, 'note': 'Select current assessment explicitly',
        'assessment_ref': selected_ref, 'read_basis': created['read_basis']})
    brief = read_brief(tmp_path, node_id)
    finding = next(item for item in brief['findings'] if item['ref'] == selected_ref)
    assert finding['kind'] == selected_kind
    assert finding['selected_assessment'] is True
    assert relations.graph(tmp_path)['results'] == {}


def test_cold_context_retains_selected_judgment_caveat_and_citations_after_note_flood(tmp_path):
    workspace(tmp_path)
    created = create(tmp_path, 'Compare reaction pathways', plan='Check structures, frequencies and reaction paths')
    node_id = created['node']['id']
    evidence = [execute('artifact_create', tmp_path, {'name': f'evidence {index}',
        'content': f'raw evidence {index}'})['artifact_id'] for index in range(6)]
    judgment = 'Endpoint energies have been checked. ' + 'The stationary point analysis is preliminary. ' * 12
    caveat = 'These are minima, not transition states; no kinetic preference or IRC connectivity is established.'
    current = execute('research_result', tmp_path, {'node_id': node_id,
        'conclusion': judgment, 'limitations': caveat, 'evidence_refs': evidence,
        'as_assessment': True, 'read_basis': created['read_basis']})['result']
    for index in range(8):
        add_note(tmp_path, node_id, f'Routine follow-up observation {index}')

    # No transcript or model summary is supplied: only persisted research state.
    brief = build(tmp_path, focus_node_ids=[node_id], waited_job_ids=['job_8'], jobs=[
        {'job_id': 'job_5', 'node_id': node_id, 'state': 'succeeded', 'collection_state': 'complete'},
        {'job_id': 'job_8', 'node_id': node_id, 'state': 'running', 'collection_state': 'not_collected'}])
    findings = {item['ref']: item for item in brief['findings']}
    restored = findings[current['id']]
    assert restored['summary'] == judgment
    assert restored['limitations'] == caveat
    assert restored['references'] == evidence
    assert restored['content_omitted'] is False
    assert findings['job_8']['waited'] is True
    assert 'job_5' not in findings
    assert findings[node_id]['plan'] == 'Check structures, frequencies and reaction paths'
    assert not any(item.get('code') == 'new_evidence_after_assessment' for item in brief['uncertainties'])


@pytest.mark.parametrize('budget', [2048, 4096, 8000])
def test_oversized_selected_judgment_is_explicitly_unread_never_partial(tmp_path, budget):
    workspace(tmp_path)
    created = create(tmp_path, 'Determine what the evidence supports')
    node_id = created['node']['id']
    text = 'Endpoint observation. ' * 2000 + 'No barrier or mechanism is established.'
    saved = execute('research_update', tmp_path, {'node_id': node_id, 'note': text,
        'as_assessment': True, 'read_basis': created['read_basis']})
    for index in range(5):
        add_note(tmp_path, node_id, f'Later routine observation {index}')
    brief = read_brief(tmp_path, node_id, budget)
    selected = next(item for item in brief['findings'] if item.get('selected_assessment'))
    assert selected['ref'] == saved['ref']
    assert selected['summary'] == ''
    assert selected['content_omitted'] is True
    assert selected['read'] == {'tool': 'research_read', 'ref': saved['ref']}
    assert len(json.dumps(brief, ensure_ascii=False, separators=(',', ':')).encode()) <= budget
    assert record(tmp_path, saved['ref'])['content'] == text


def test_new_result_and_runtime_evidence_request_review_without_invalidating_assessment(tmp_path):
    workspace(tmp_path)
    created = create(tmp_path, 'Investigate alternatives')
    node_id = created['node']['id']
    selected = execute('research_update', tmp_path, {'node_id': node_id,
        'note': 'Initial interpretation remains tentative.', 'as_assessment': True,
        'read_basis': created['read_basis']})
    initial = read_brief(tmp_path, node_id)
    runtime = append_record(tmp_path, origin='runtime', kind='job', title='New calculation evidence',
        content='Calculation completed; analysis is pending.', references=['job_8'], node_id=node_id,
        data={'job_id': 'job_8', 'state': 'succeeded', 'collection_state': 'complete'})
    later = execute('research_result', tmp_path, {'node_id': node_id,
        'conclusion': 'New observation has not yet been compared with the current judgment.'})['result']
    brief = read_brief(tmp_path, node_id)
    cue = next(item for item in brief['uncertainties'] if item.get('code') == 'new_evidence_after_assessment')
    assert cue['references'] == [runtime['ref'], later['id']]
    assert cue['assessment_ref'] == selected['ref']
    assert brief['state_digest'] != initial['state_digest']
    assert nodes.get_node(tmp_path, node_id)['assessment_ref'] == selected['ref']
    assert not any('new_evidence_after_assessment' in item.get('codes', []) for item in brief['contradictions'])
    assert any(item['action'] == 'review_new_evidence' for item in brief['follow_up'])
    updated = execute('research_update', tmp_path, {'node_id': node_id,
        'note': 'Reviewed the new evidence; the initial interpretation is still tentative.',
        'as_assessment': True, 'read_basis': selected['read_basis']})
    refreshed = read_brief(tmp_path, node_id)
    assert not any(item.get('code') == 'new_evidence_after_assessment' for item in refreshed['uncertainties'])
    assert next(item for item in refreshed['findings'] if item.get('selected_assessment'))['ref'] == updated['ref']


def test_selected_note_includes_only_its_direct_research_citations(tmp_path):
    workspace(tmp_path)
    dependency = create(tmp_path, 'Recorded comparison')
    related_result = execute('research_result', tmp_path, {'node_id': dependency['node']['id'],
        'conclusion': 'A comparison with a stated limitation'})['result']
    other = create(tmp_path, 'Previously inspected question')
    created = create(tmp_path, 'Main investigation')
    node_id = created['node']['id']
    execute('research_update', tmp_path, {'node_id': node_id, 'note': 'Past process note',
        'references': [other['node']['id']]})
    execute('research_update', tmp_path, {'node_id': node_id, 'note': 'Current judgment cites the comparison.',
        'references': [related_result['id']], 'as_assessment': True, 'read_basis': created['read_basis']})
    selection = select(tmp_path, focus_node_ids=[node_id])
    assert set(selection['_basis']['node_ids']) == {node_id, dependency['node']['id']}


@pytest.mark.parametrize('kind', ['note', 'result'])
def test_explicit_reselection_reviews_new_evidence_but_plan_change_does_not(tmp_path, kind):
    workspace(tmp_path)
    created = create(tmp_path, 'Review later evidence')
    node_id = created['node']['id']
    request = {'node_id': node_id, 'as_assessment': True, 'read_basis': created['read_basis']}
    selected = execute('research_update' if kind == 'note' else 'research_result', tmp_path,
        {**request, 'note' if kind == 'note' else 'conclusion': 'Tentative judgment.'})
    assessment_ref = selected['ref'] if kind == 'note' else selected['result']['id']
    execute('research_result', tmp_path, {'node_id': node_id, 'conclusion': 'A later observation.'})
    assert any(item.get('code') == 'new_evidence_after_assessment' for item in read_brief(tmp_path, node_id)['uncertainties'])
    reviewed = execute('research_update', tmp_path, {'node_id': node_id,
        'note': 'Reviewed the later observation; retain the selected judgment.',
        'assessment_ref': assessment_ref, 'read_basis': selected['read_basis']})
    assert not any(item.get('code') == 'new_evidence_after_assessment' for item in read_brief(tmp_path, node_id)['uncertainties'])
    append_record(tmp_path, origin='runtime', kind='job', title='Additional calculation',
        content='New evidence awaiting review.', node_id=node_id, data={'state': 'succeeded'})
    assert any(item.get('code') == 'new_evidence_after_assessment' for item in read_brief(tmp_path, node_id)['uncertainties'])
    execute('research_update', tmp_path, {'node_id': node_id, 'note': 'Arrange the work.',
        'plan': 'Schedule an additional comparison', 'read_basis': reviewed['read_basis']})
    assert any(item.get('code') == 'new_evidence_after_assessment' for item in read_brief(tmp_path, node_id)['uncertainties'])


def test_selected_note_reports_a_cited_result_correction_without_replacing_it(tmp_path):
    workspace(tmp_path)
    source = create(tmp_path, 'Source evidence')['node']['id']
    first = execute('research_result', tmp_path, {'node_id': source, 'conclusion': 'Preliminary observation.'})['result']
    target = create(tmp_path, 'Interpret the source')
    selected = execute('research_update', tmp_path, {'node_id': target['node']['id'],
        'note': 'Tentative interpretation based on the cited observation.', 'references': [first['id']],
        'as_assessment': True, 'read_basis': target['read_basis']})
    correction = execute('research_result', tmp_path, {'node_id': source,
        'conclusion': 'Corrected observation.', 'supersedes': first['id']})['result']
    brief = read_brief(tmp_path, target['node']['id'])
    finding = next(item for item in brief['findings'] if item.get('selected_assessment'))
    assert finding['ref'] == selected['ref'] and finding['references'] == [first['id']]
    assert finding['review_required'] is True
    assert 'cited_result_superseded' in finding['review_codes']
    assert correction['id'] in brief['source_refs']
    assert nodes.get_node(tmp_path, target['node']['id'])['assessment_ref'] == selected['ref']


def test_optional_old_large_result_is_removed_before_recent_small_result(tmp_path):
    workspace(tmp_path)
    created = create(tmp_path, 'Keep the current question and useful new evidence')
    node_id = created['node']['id']
    selected = execute('research_update', tmp_path, {'node_id': node_id,
        'note': 'Current assessment remains tentative.', 'as_assessment': True, 'read_basis': created['read_basis']})
    older = execute('research_result', tmp_path, {'node_id': node_id, 'conclusion': 'Long historical analysis. ' * 1000})['result']
    newer = execute('research_result', tmp_path, {'node_id': node_id, 'conclusion': 'A useful new observation.'})['result']
    brief = read_brief(tmp_path, node_id, 4096)
    findings = {item['ref']: item for item in brief['findings']}
    assert older['id'] not in findings and newer['id'] in findings
    assert findings[selected['ref']]['selected_assessment'] is True
