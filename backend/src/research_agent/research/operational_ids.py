"""Durable workspace sequences; reserved ordinals are never recycled."""
from research_agent.foundation.transactions import read_json, TransactionCoordinator, _safe_path
from .records import digest

KINDS = frozenset({'node', 'result', 'task', 'job', 'job_result',
                   'art', 'note', 'record', 'user', 'link', 'prepared', 'monitor', 'event', 'obs', 'runtime'})
STATE_FILE = 'operations/identifiers.json'
STATE_SCHEMA = 'coragent-identifiers/1'


def allocate_id(root, kind, identity=None):
    """Commit a reservation before any caller writes files or dispatches work.

    This is an independent commit even inside an owning transaction. Failure
    may leave a gap, but a leftover payload can never acquire another identity.
    """
    from .workspace import validate_workspace_manifest
    coordinator = TransactionCoordinator(root)
    with coordinator.locked():
        root = coordinator.root
        validate_workspace_manifest(read_json(root / 'workspace_manifest.json'), root,
                                    require_ready=True, validate_documents=False)
        if kind not in KINDS:
            raise ValueError(f'unsupported identifier kind: {kind}')
        state = read_json(_safe_path(root, STATE_FILE))
        key = digest(identity) if identity is not None else None
        reservation = f'operations/identifiers/{kind}/{key}.json' if key is not None else None
        if reservation is not None:
            try:
                return read_json(_safe_path(root, reservation))['identifier']
            except FileNotFoundError:
                pass
        ordinal = state['high_water'].get(kind, 0) + 1
        identifier = f'{kind}_{ordinal}'
        state['high_water'][kind] = ordinal
        writes = {STATE_FILE: state}
        if reservation is not None:
            writes[reservation] = {'identifier': identifier}
        coordinator.commit_files(f'identity:{identifier}', 'identity.allocate',
                                 {'kind': kind, 'identity': identity},
                                 writes=writes, result=identifier)
        return identifier
