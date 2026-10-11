"""Directory guidance is derived without changing stored research history."""
from research_agent.research import nodes, retrieval
from tests.unit.test_job_recovery import workspace


def test_node_work_dir_is_derived_and_available_on_paged_reads(tmp_path):
    workspace(tmp_path)
    created = nodes.create(tmp_path, {'goal': 'Study a fixture'})
    node_id = created['node']['id']
    work = tmp_path / 'research/nodes' / node_id / 'work'
    assert created['work_dir'] == str(work)
    assert work.is_dir()
    assert retrieval.read(tmp_path, ref=node_id, limit=1)['work_dir'] == str(work)
    assert retrieval.read(tmp_path, ref=node_id, field='goal')['work_dir'] == str(work)
    assert 'work_dir' not in nodes.get_node(tmp_path, node_id)
