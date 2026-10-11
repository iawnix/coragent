"""One durable allocator serves research and execution identities."""
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

import pytest

from research_agent.research.operational_ids import allocate_id, STATE_FILE
from research_agent.research.workspace import admit_research_workspace, initialize_workspace, WorkspaceModeError
from research_agent.foundation.transactions import workspace_transaction, TransactionError


def workspace(root):
    initialize_workspace(root, root.name, 'research')
    admit_research_workspace(root)


def test_concurrent_reservations_and_retries(tmp_path):
    workspace(tmp_path)
    with ThreadPoolExecutor(max_workers=8) as pool:
        ids = list(pool.map(lambda n: allocate_id(tmp_path, 'task', ['session', n]), range(24)))
    assert set(ids) == {f'task_{n}' for n in range(1, 25)}
    with ThreadPoolExecutor(max_workers=8) as pool:
        assert list(pool.map(lambda n: allocate_id(tmp_path, 'task', ['session', n]), range(24))) == ids
    assert allocate_id(tmp_path, 'task', ['another-session', 0]) == 'task_25'
    assert allocate_id(tmp_path, 'node') == 'node_1'


def test_reservation_survives_process_restart_and_deletion(tmp_path):
    workspace(tmp_path)
    assert allocate_id(tmp_path, 'job', 'request') == 'job_1'
    script = 'from research_agent.research.operational_ids import allocate_id; import sys; assert allocate_id(sys.argv[1], "job", "request") == "job_1"; assert allocate_id(sys.argv[1], "job", "next") == "job_2"'
    subprocess.run([sys.executable, '-B', '-c', script, str(tmp_path)], check=True)
    assert allocate_id(tmp_path, 'job', 'third') == 'job_3'


def test_failed_transaction_never_recycles_reserved_identity(tmp_path):
    workspace(tmp_path)
    @workspace_transaction('test.failed')
    def abort(root, request):
        assert allocate_id(root, 'result', 'publication') == 'result_1'
        raise ValueError('publication rejected')
    with pytest.raises(ValueError, match='publication rejected'):
        abort(tmp_path, {})
    assert allocate_id(tmp_path, 'result', 'other') == 'result_2'
    assert allocate_id(tmp_path, 'result', 'publication') == 'result_1'


def test_old_manifest_rejected_without_modification(tmp_path):
    workspace(tmp_path)
    manifest = tmp_path / 'workspace_manifest.json'
    value = json.loads(manifest.read_text()); value['schema_version'] = 'research_workspace/2'
    manifest.write_text(json.dumps(value))
    before = {p: p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}
    with pytest.raises(WorkspaceModeError, match='create a new research workspace'):
        initialize_workspace(tmp_path, tmp_path.name, 'research')
    with pytest.raises(WorkspaceModeError):
        allocate_id(tmp_path, 'node')
    assert {p: p.read_bytes() for p in before} == before


def test_invalid_kind_and_symlink_state_rejected(tmp_path):
    workspace(tmp_path)
    with pytest.raises(ValueError, match='unsupported identifier kind'):
        allocate_id(tmp_path, 'unknown')
    path = tmp_path / STATE_FILE
    path.unlink(); path.symlink_to(tmp_path / 'workspace_manifest.json')
    with pytest.raises(TransactionError, match='symlink'):
        allocate_id(tmp_path, 'node')


def test_independent_processes_allocate_distinct_ids(tmp_path):
    workspace(tmp_path)
    script = 'from research_agent.research.operational_ids import allocate_id; import sys; allocate_id(sys.argv[1], "node", sys.argv[2])'
    processes = [subprocess.Popen([sys.executable, '-B', '-c', script, str(tmp_path), str(n)]) for n in range(8)]
    try:
        assert all(process.wait(timeout=20) == 0 for process in processes)
    finally:
        for process in processes:
            if process.poll() is None:
                process.kill(); process.wait()
    assert {allocate_id(tmp_path, 'node', str(n)) for n in range(8)} == {f'node_{n}' for n in range(1, 9)}


def test_failed_artifact_publication_cannot_rebind_leftover_payload(tmp_path, monkeypatch):
    from research_agent.application.api import execute
    from research_agent.artifacts import registry
    workspace(tmp_path)
    with monkeypatch.context() as patch:
        def reject(*args, **kwargs):
            raise OSError('publication interrupted')
        patch.setattr(registry, 'register_manifest', reject)
        with pytest.raises(OSError, match='publication interrupted'):
            execute('artifact.create', tmp_path, {'name': 'first', 'content': 'retained bytes'})
    other = execute('artifact.create', tmp_path, {'name': 'second', 'content': 'different bytes'})
    recovered = execute('artifact.create', tmp_path, {'name': 'first', 'content': 'retained bytes'})
    assert recovered['artifact_id'] == 'art_1'
    assert other['artifact_id'] == 'art_2'
    assert execute('artifact.read', tmp_path, {'artifact_id': 'art_1'})['content'] == 'retained bytes'


def test_task_allocation_is_shared_across_sessions_and_replays(tmp_path):
    from research_agent.application.api import execute
    workspace(tmp_path)
    def begin(session):
        return execute('research.allocate_task', tmp_path, {'session_id': session, 'request_id': 'same-request'})
    assert begin('first') == {'identifier': 'task_1'}
    assert begin('second') == {'identifier': 'task_2'}
    assert begin('first') == {'identifier': 'task_1'}
