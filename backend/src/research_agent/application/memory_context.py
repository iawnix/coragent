"""Compose runtime-owned facts with Memory without inverting ownership."""
import re
from pathlib import Path
from research_agent.foundation.transactions import TransactionCoordinator, read_json
from research_agent.foundation.path_safety import path_has_symlink
from research_agent.research import retrieval, views
from research_agent.research.records import workspace


def jobs(root):
    from .job_state import list_execution_summaries
    return [{**row, 'read': {'tool': 'job_status', 'job_id': row['job_id']}}
            for row in list_execution_summaries(root)]


def _source_bindings(root, submission_ids, session_id=None, *, require=False):
    """Resolve Pi submission IDs to exact immutable Research Memory refs.

    Pi's submission sequence and Research Memory's operational record IDs are
    deliberately different namespaces.  Resolve by the recorded provenance
    instead of allowing callers to guess a ``user_<submission_id>`` ref.
    """
    if submission_ids is None:
        return []
    if (not isinstance(submission_ids, list) or len(submission_ids) > 64
            or any(not isinstance(value, str) or not value.strip() for value in submission_ids)
            or len(set(submission_ids)) != len(submission_ids)):
        raise ValueError('source_submission_ids_invalid: use unique submission ID strings')
    from research_agent.research.records import record, journal
    output = []
    for submission_id in submission_ids:
        matches = []
        for item in journal(root).get('records', []):
            if item.get('origin') != 'user':
                continue
            ref = item.get('ref')
            try:
                value = record(root, ref)
            except (FileNotFoundError, ValueError):
                continue
            data = value.get('data') or {}
            if str(data.get('message_id')) != submission_id:
                continue
            if session_id is not None and str(data.get('session_id')) != str(session_id):
                continue
            matches.append(value)
        if len(matches) > 1:
            raise ValueError('source_submission_ambiguous: ' + submission_id)
        if not matches:
            if require:
                raise ValueError('source_submission_not_found: ' + submission_id)
            continue
        value = matches[0]
        output.append({'submission_id': submission_id, 'research_ref': value['ref']})
    return output


def resolve_source_submission_ids(root, submission_ids, session_id=None):
    if submission_ids and not session_id:
        raise ValueError('source_submission_session_required: runtime session_id is required to resolve task inputs')
    return [item['research_ref'] for item in _source_bindings(root, submission_ids, session_id, require=True)]


def read(root, *, ref=None, offset=0, limit=16000, session_id=None, event_ids=(), entry_node_ids=(), focus_node_ids=(), field=None,
         view=None, waited_job_ids=(), source_submission_ids=None):
    from .job_state import project_events
    from .job_manager import assess
    with TransactionCoordinator(root).locked():
        workspace(root)
        errors = project_events(root)
        current = jobs(root)
        if view not in (None, 'brief'):
            raise ValueError('research_view_invalid: use brief')
        if view == 'brief':
            if ref or field or offset:
                raise ValueError('review_view_requires_snapshot')
            from research_agent.research.brief import build
            events = [assess(root, event_id, session_id)['event'] for event_id in event_ids]
            return build(root, max_bytes=max(2048, limit), session_id=session_id, entry_node_ids=entry_node_ids,
                         focus_node_ids=focus_node_ids, events=events, jobs=current, waited_job_ids=waited_job_ids,
                         projection={'pending': len(errors)},
                         source_bindings=_source_bindings(root, source_submission_ids, session_id))
        if ref:
            return retrieval.read(root, ref=ref, offset=offset, limit=limit, session_id=session_id, jobs=current, field=field)
        events = [assess(root, event_id, session_id)['event'] for event_id in event_ids]
        return views.build_snapshot(root, max_bytes=max(2048, limit), session_id=session_id,
                                    entry_node_ids=entry_node_ids, focus_node_ids=focus_node_ids,
                                    jobs=current, events=events, projection={'pending': len(errors), 'errors': errors[:3]})


def reference_details(root, request):
    from research_agent.artifacts.registry import read_manifest
    from .job_state import execution
    details = {}
    refs = request.get('input_refs', []) + request.get('inputs', []) + request.get('evidence_refs', [])
    refs += list(request.get('subjects', {}).values()) + request.get('check_refs', [])
    refs += [item.get('artifact_ref') for item in request.get('files', []) if isinstance(item, dict)]
    for ref in refs:
        if not isinstance(ref, str):
            raise ValueError('reference_invalid')
        if ref.startswith('record_'):
            from research_agent.research.records import record
            fact = record(root, ref)
            data = fact['data']
            if fact['origin'] == 'runtime' and fact['kind'] == 'job':
                details[ref] = {'kind': 'runtime_fact', 'research_binding': data.get('metadata', {}).get('research_binding'),
                                'input_refs': list(data.get('metadata', {}).get('input_evidence_basis', {}))}
            continue
        if ref.startswith(('node_', 'result_', 'note_', 'user_')):
            continue
        if re.fullmatch(r'job_result_[1-9][0-9]*', ref):
            path = Path(root) / 'operations/results' / (ref + '.json')
            if path_has_symlink(path):
                raise ValueError('reference_symlink')
            receipt = read_json(path)
            observation = execution(root, receipt['job_id'])
            details[ref] = {'kind': 'collection_receipt', 'research_binding': observation.get('metadata', {}).get('research_binding'),
                            'validation': receipt.get('validator_result'),
                            'input_refs': list(observation.get('metadata', {}).get('input_evidence_basis', {}))}
        elif re.fullmatch(r'job_[1-9][0-9]*', ref):
            observation = execution(root, ref)
            details[ref] = {'kind': 'job', 'research_binding': observation.get('metadata', {}).get('research_binding'),
                            'input_refs': list(observation.get('metadata', {}).get('input_evidence_basis', {}))}
        else:
            identity = ref
            material = read_manifest(root, identity)
            provenance = material.get('provenance', {})
            binding = {k: provenance[k] for k in ('node_id', 'node_revision') if k in provenance}
            details[ref] = {'kind': 'artifact', 'artifact_id': identity, 'sha256': material['sha256'],
                            'research_binding': binding if binding.get('node_id') else None}
    return details
