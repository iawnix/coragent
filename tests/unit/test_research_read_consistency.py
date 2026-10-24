"""User-facing reads preserve full evidence, source times and review notices."""
import json

import pytest

from research_agent.application.api import execute
from research_agent.research.records import digest, record
from tests.unit.test_job_recovery import workspace


def test_read_pages_share_content_digest_and_detect_notes_without_node_revision_change(tmp_path):
    workspace(tmp_path)
    created = execute('research_create', tmp_path, {'goal': 'Read all evidence', 'plan': '观察😀' * 1000})
    node_id = created['node']['id']
    first = execute('research_read', tmp_path, {'ref': node_id, 'limit': 32000})
    pages, offset = [], 0
    while offset is not None:
        page = execute('research_read', tmp_path, {'ref': node_id, 'offset': offset, 'limit': 700})
        assert page['content_sha256'] == first['content_sha256']
        pages.append(page['text'])
        offset = page['next_offset']
    full = ''.join(pages)
    assert 'sha256:' + digest(full) == first['content_sha256']
    assert json.loads(full)['node']['plan'] == created['node']['plan']
    execute('research_update', tmp_path, {'node_id': node_id, 'note': 'A new measurement arrived'})
    later = execute('research_read', tmp_path, {'ref': node_id})
    assert later['node_revision'] == first['node_revision']
    assert later['content_sha256'] != first['content_sha256']


@pytest.mark.parametrize('kind', ['note', 'result'])
def test_detail_and_brief_share_review_notices_and_source_timestamps(tmp_path, kind):
    workspace(tmp_path)
    created = execute('research_create', tmp_path, {'title': 'Pathway comparison', 'goal': 'Compare alternatives'})
    node_id = created['node']['id']
    request = {'node_id': node_id, 'as_assessment': True, 'read_basis': created['read_basis']}
    if kind == 'note':
        saved = execute('research_update', tmp_path, {**request, 'note': 'Current judgment remains tentative'})
        assessment = record(tmp_path, saved['ref'])
    else:
        saved = execute('research_result', tmp_path, {**request, 'conclusion': 'Current judgment remains tentative'})
        assessment = saved['result']
    evidence = execute('research_result', tmp_path, {'node_id': node_id, 'conclusion': 'New observation to review'})['result']
    read = execute('research_read', tmp_path, {'ref': node_id})
    detail = json.loads(read['text'])
    notice = next(item for item in detail['review_notices'] if item.get('code') == 'new_evidence_after_assessment')
    assert notice['references'] == [evidence['id']]
    brief = execute('research_read', tmp_path, {'view': 'brief', 'focus_node_ids': [node_id], 'limit': 32000})
    node = next(item for item in brief['findings'] if item['ref'] == node_id)
    judgment = next(item for item in brief['findings'] if item.get('selected_assessment'))
    observation = next(item for item in brief['findings'] if item['ref'] == evidence['id'])
    assert node['title'] == created['node']['title']
    assert node['updated_at'] == detail['node']['updated_at']
    assert judgment['created_at'] == assessment['created_at']
    assert observation['created_at'] == evidence['created_at']
    assert notice['code'] in judgment['review_codes']
    execute('research_update', tmp_path, {'node_id': node_id, 'note': 'Reviewed the new observation',
        'assessment_ref': node['assessment_ref'], 'read_basis': read['read_basis']})
    reviewed = execute('research_read', tmp_path, {'ref': node_id})
    assert not any(item.get('code') == 'new_evidence_after_assessment' for item in reviewed['review_notices'])
