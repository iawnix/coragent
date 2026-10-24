"""A Node retains one research question across repeated attempts."""
from pathlib import Path
from .operational_ids import allocate_id
import re
import uuid
from research_agent.foundation.transactions import read_json, write_json, workspace_transaction
from research_agent.foundation.path_safety import path_has_symlink
from .records import workspace, append_record, record, now
from . import basis, relations


NODE_SCHEMA = 'research-node/2'
NODE_FIELDS = frozenset({'schema_version', 'id', 'workspace_id', 'title', 'goal', 'plan', 'status',
                        'assessment_ref', 'source_refs', 'input_refs', 'subjects', 'revision',
                        'created_at', 'updated_at', 'author'})


def validate_node(value, node_id, workspace_id):
    if (not isinstance(value, dict) or value.get('id') != node_id or value.get('schema_version') != NODE_SCHEMA
            or value.get('workspace_id') != workspace_id or set(value) != NODE_FIELDS):
        raise ValueError('node_identity_invalid')
    return value


def text(value, name, *, required=False, limit=16000):
    if value is None and not required:
        return None
    if not isinstance(value, str) or required and not value.strip():
        raise ValueError(name + '_invalid: use a string' + (' with non-whitespace text' if required else ''))
    if len(value) > limit:
        raise ValueError(f'{name}_invalid: maximum {limit} Unicode characters; received {len(value)}')
    return value


def get_node(root, node_id):
    if not isinstance(node_id, str) or not re.fullmatch(r'node_[1-9][0-9]*', node_id):
        raise ValueError('node_id_invalid: use a returned Node reference')
    path = Path(root) / 'research/nodes' / node_id / 'node.json'
    if path_has_symlink(path):
        raise ValueError('node_path_symlink')
    return validate_node(read_json(path), node_id,
                         read_json(Path(root) / 'workspace_manifest.json')['workspace_id'])


def save(root, node):
    write_json(Path(root) / 'research/nodes' / node['id'] / 'node.json', node)
    graph = relations.graph(root)
    graph['nodes'][node['id']] = node
    write_json(Path(root) / 'research/map.json', graph)


def validate_refs(root, refs, external=None):
    from .results import get_result
    if not isinstance(refs, list) or len(refs) > 128 or any(not isinstance(r, str) for r in refs) or len(set(refs)) != len(refs):
        raise ValueError('references_invalid: use unique returned references')
    for ref in refs:
        if ref.startswith('node_'):
            get_node(root, ref)
        elif ref.startswith('result_'):
            get_result(root, ref)
        elif ref.startswith(('user_', 'record_', 'note_')):
            try:
                record(root, ref)
            except FileNotFoundError as exc:
                if re.fullmatch(r'user_[1-9][0-9]*', ref):
                    raise ValueError(
                        f'source_ref_invalid: {ref} looks like a Task Controller submission ID; '
                        'use source_submission_ids or the exact Research Memory user_* reference returned by research_read'
                    ) from exc
                raise
        elif ref not in (external or {}):
            raise ValueError('reference_not_verified: ' + ref)
    return refs


def response(root, node, request, **values):
    return {'accepted': True, 'node': node, 'work_dir': work_dir(root, node['id']), 'relations': relations.links(root, node['id']), 'read_basis': basis.issue(root, [node], request.get('session_id')), **values}


def work_dir(root, node_id):
    """Derived guidance, never persisted into historical Node records."""
    return str(Path(root).resolve() / 'research/nodes' / node_id / 'work')


# Durable receipt identity; not a callable command name. Keep existing digests stable.
@workspace_transaction('research.create')
def create(root, request):
    root = workspace(root)
    goal = text(request.get('goal'), 'goal', required=True, limit=8000)
    title = text(request.get('title', goal[:100]), 'title', required=True, limit=1000)
    source_refs = validate_refs(root, request.get('source_refs', []))
    if any(not ref.startswith('user_') for ref in source_refs):
        raise ValueError('source_refs_require_user_messages')
    input_refs = validate_refs(root, request.get('input_refs', []), request.get('_reference_details'))
    from .context import subjects
    subject_refs = subjects(root, request.get('subjects', {}), request.get('_reference_details', {}))
    node = dict(schema_version=NODE_SCHEMA, id=allocate_id(root, 'node'),
                workspace_id=read_json(root / 'workspace_manifest.json')['workspace_id'],
                title=title, goal=goal, plan=text(request.get('plan'), 'plan'), status='open', assessment_ref=None,
                source_refs=source_refs, input_refs=input_refs, subjects=subject_refs, revision=1, created_at=now(), updated_at=now(),
                author={'session_id': request.get('session_id')})
    save(root, node)
    log = append_record(root, origin='agent', kind='node_created', title=title, content=goal,
                        references=source_refs + input_refs, node_id=node['id'], node_revision=1,
                        data={'node': node}, identity=['create', node['id']])
    relations.change(root, node['id'], request.get('relations', []), author=node['author'])
    for ref in dict.fromkeys(input_refs + list(subject_refs.values())):
        relations.cite(root, node['id'], ref, basis_ref=log['ref'])
    (root / 'research/nodes' / node['id'] / 'work').mkdir(parents=True, exist_ok=True)
    return response(root, node, request, ref=log['ref'])


# Durable receipt identity; not a callable command name. Keep existing digests stable.
@workspace_transaction('research.update')
def update(root, request):
    root = workspace(root)
    node = get_node(root, request['node_id'])
    note = text(request.get('note'), 'note', required=True, limit=64000)
    selected = request.get('as_assessment', False)
    if type(selected) is not bool:
        raise ValueError('as_assessment_requires_boolean')
    if selected and 'assessment_ref' in request:
        raise ValueError('assessment_selection_conflict: use as_assessment or assessment_ref, not both')
    references = validate_refs(root, request.get('references', []), request.get('_reference_details'))
    changed = set(request) & basis.EDIT_FIELDS
    if selected:
        changed.add('assessment_ref')
    if request.get('add_relations') or request.get('remove_relations'):
        changed.add('relations')
    basis.check(root, node, request, changed)
    for key in changed - {'relations', 'status', 'assessment_ref', 'subjects'}:
        node[key] = text(request[key], key, required=key in {'goal', 'title'},
                         limit={'goal': 8000, 'title': 1000}.get(key, 16000))
    if 'subjects' in changed:
        from .context import subjects
        node['subjects'] = subjects(root, request['subjects'], request.get('_reference_details', {}))
    if 'status' in changed:
        if request['status'] not in {'open', 'paused', 'closed'}:
            raise ValueError('node_status_invalid')
        node['status'] = request['status']
    if 'assessment_ref' in request:
        ref = request['assessment_ref']
        if ref is not None:
            validate_refs(root, [ref])
            from .results import get_result
            assessment = get_result(root, ref) if ref.startswith('result_') else record(root, ref)
            if assessment.get('node_id') != node['id'] or assessment.get('origin', 'agent') != 'agent':
                raise ValueError('assessment_must_belong_to_node')
        node['assessment_ref'] = ref
    if changed:
        node['revision'] += 1
        node['updated_at'] = now()
    identity = ['note', request.get('request_id') or uuid.uuid4().hex]
    if selected:
        # Reserve the exact immutable record identity before persisting its Node snapshot.
        node['assessment_ref'] = allocate_id(root, 'note', identity)
    log = append_record(root, origin='agent', kind='node_updated' if changed else 'note', title=node['title'],
                        content=note, references=references, node_id=node['id'], node_revision=node['revision'],
                        data={**({'node': node} if changed else {}),
                              **({'assessment_selected': True} if selected or request.get('assessment_ref') else {}),
                              'author': {'session_id': request.get('session_id')}},
                        identity=identity)
    if changed:
        save(root, node)
        relations.change(root, node['id'], request.get('add_relations', []), request.get('remove_relations', []),
                         author={'session_id': request.get('session_id')})
    for ref in references:
        relations.cite(root, node['id'], ref, basis_ref=log['ref'])
    return response(root, node, request, ref=log['ref'])
