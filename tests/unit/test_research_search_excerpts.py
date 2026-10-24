"""Search keeps literal matching while showing readable, relevant passages."""
import pytest

from research_agent.research import nodes, results, retrieval
from tests.unit.test_job_recovery import workspace


def test_note_excerpt_contains_match_after_initial_600_characters(tmp_path):
    workspace(tmp_path)
    node = nodes.create(tmp_path, {'goal': 'Compare reaction mechanisms'})['node']
    note = nodes.update(tmp_path, {'node_id': node['id'],
        'note': 'Earlier observations. ' * 80 + 'The Fe–O signal requires another check. ' + 'Later observations. ' * 80})

    page = retrieval.search(tmp_path, query='fe–o signal', kind='note')

    assert page['total'] == 1
    hit = page['records'][0]
    assert hit['ref'] == note['ref']
    assert 'The Fe–O signal requires another check.' in hit['excerpt']
    assert hit['excerpt'].startswith('… ') and hit['excerpt'].endswith(' …')
    assert len(hit['excerpt']) <= 600
    assert hit['read'] == {'ref': note['ref']}
    assert 'content' not in hit


@pytest.mark.parametrize('kind', ['node', 'result'])
def test_structured_search_excerpts_show_authored_fields_instead_of_json(tmp_path, kind):
    workspace(tmp_path)
    node = nodes.create(tmp_path, {'title': 'Pathway comparison', 'goal': 'Compare reaction barriers',
                                 'plan': 'Validate both transition states'})['node']
    result = results.publish(tmp_path, {'node_id': node['id'], 'summary': 'Preliminary comparison',
        'conclusion': 'The barriers remain uncertain', 'observation': 'One stationary point was found',
        'limitations': 'The second transition state still needs verification'})['result']

    page = retrieval.search(tmp_path, kind=kind)

    assert page['total'] == 1
    hit = page['records'][0]
    assert hit['ref'] == (node if kind == 'node' else result)['id']
    assert 'schema_version' not in hit['excerpt']
    assert not hit['excerpt'].startswith('{')
    if kind == 'node':
        assert hit['excerpt'] == 'Goal: Compare reaction barriers\n\nPlan: Validate both transition states'
    else:
        assert 'Conclusion: The barriers remain uncertain' in hit['excerpt']
        assert 'Observation: One stationary point was found' in hit['excerpt']
        assert 'Limitations: The second transition state still needs verification' in hit['excerpt']


@pytest.mark.parametrize('kind', ['node', 'result'])
def test_structured_excerpt_finds_late_match_with_casefold_expansion(tmp_path, kind):
    workspace(tmp_path)
    passage = 'ß' * 900 + ' Straße criterion remains unverified. ' + 'Further analysis. ' * 80
    node = nodes.create(tmp_path, {'goal': 'Compare pathways', 'plan': passage})['node']
    results.publish(tmp_path, {'node_id': node['id'], 'conclusion': 'Comparison remains inconclusive',
                              'observation': passage})

    page = retrieval.search(tmp_path, query='STRASSE criterion', kind=kind)

    assert page['total'] == 1
    excerpt = page['records'][0]['excerpt']
    assert 'Straße criterion remains unverified.' in excerpt
    assert excerpt.startswith('… ') and len(excerpt) <= 600


def test_search_matching_and_pagination_remain_literal(tmp_path):
    workspace(tmp_path)
    node = nodes.create(tmp_path, {'goal': 'Compare pathways'})['node']
    saved = [nodes.update(tmp_path, {'node_id': node['id'], 'note': f'Attempt {index}: distance.* is literal text'})
             for index in range(3)]
    nodes.update(tmp_path, {'node_id': node['id'], 'note': 'Distance matrix calculation finished'})

    page = retrieval.search(tmp_path, query='DISTANCE.*', kind='note', limit=2)
    remaining = retrieval.search(tmp_path, query='DISTANCE.*', kind='note', limit=2, offset=page['next_offset'])

    assert page['total'] == 3 and page['next_offset'] == 2
    assert [item['ref'] for item in page['records'] + remaining['records']] == [item['ref'] for item in reversed(saved)]
    assert remaining['next_offset'] is None
    assert all('distance.*' in item['excerpt'] for item in page['records'])
    # Excerpt presentation does not change the existing indexed search space.
    assert retrieval.search(tmp_path, query='research-node/2', kind='node')['total'] == 1
