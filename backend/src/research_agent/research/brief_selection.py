"""Internal selection of bounded facts for the canonical Research Brief."""
import json

from . import relations
from .context import result_notices
from .records import journal, record, recent_notes
from .results import get_result, publication_order


def size(value):
    return len(json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode())


def excerpt(text, budget):
    """Include a complete field or leave it unread; a prefix can omit its caveat."""
    text = text or ''
    return text if len(text.encode()) <= budget else ''


def assessment_notices(root, assessment_ref, headers):
    """Report newer evidence by journal order, without judging scientific validity."""
    if not assessment_ref:
        return []
    assessment_sequence = next((header['sequence'] for header in headers
                                if header['ref'] == assessment_ref), None)
    publications = {}
    if assessment_ref.startswith('result_'):
        for header in reversed(headers):
            if header['kind'] == 'result_published':
                value = record(root, header['ref'])
                publications[header['ref']] = value
                if value['data']['result_id'] == assessment_ref:
                    assessment_sequence = header['sequence']
                    break
    if assessment_sequence is None:
        return []
    # Explicitly selecting the same historical judgment records that review
    # happened now. An unrelated plan/status edit cannot acknowledge evidence.
    for header in reversed(headers):
        if header['sequence'] < assessment_sequence:
            break
        if header['kind'] == 'node_updated':
            data = record(root, header['ref'])['data']
            if data.get('assessment_selected') and data['node']['assessment_ref'] == assessment_ref:
                assessment_sequence = header['sequence']
                break
    newer = []
    for header in headers:
        if header['sequence'] <= assessment_sequence or header['kind'] not in {'result_published', 'job'}:
            continue
        value = publications.get(header['ref']) or record(root, header['ref'])
        data = value['data']
        if header['kind'] == 'result_published':
            newer.append(data['result_id'])
        elif data.get('state') in {'succeeded', 'failed', 'timed_out', 'cancelled'} or data.get('collection_state') == 'complete':
            newer.append(header['ref'])
    return ([{'code': 'new_evidence_after_assessment', 'assessment_ref': assessment_ref,
              'references': list(dict.fromkeys(newer)), 'evidence_count': len(newer)}] if newer else [])


def build(root, *, max_bytes=8000, session_id=None, entry_node_ids=(),
          focus_node_ids=(), events=(), jobs=(), waited_job_ids=(), projection=None):
    if not 2048 <= max_bytes <= 32000:
        raise ValueError('snapshot_budget_invalid: use 2048..32000 bytes')
    graph, index = relations.graph(root), journal(root)
    entries, focus = list(dict.fromkeys(entry_node_ids)), list(dict.fromkeys(focus_node_ids))
    if any(ref not in graph['nodes'] for ref in entries + focus):
        raise ValueError('research_scope_node_not_found')
    event_nodes = [e['node_id'] for e in events if e.get('node_id') in graph['nodes']]
    waited = set(waited_job_ids)
    waited_nodes = [j['node_id'] for j in jobs if j['job_id'] in waited and j.get('node_id') in graph['nodes']]
    primary = list(dict.fromkeys(focus + event_nodes + waited_nodes))
    selection = 'explicit_focus' if focus else 'event_or_wait' if primary else 'task_entries'
    if not primary:
        primary = entries.copy()
    if not primary:
        # An unbound session gets one navigation hint, not the whole workspace.
        activity = {r['node_id']: r['sequence'] for r in index['records'] if r.get('node_id')}
        own = [n for n in graph['nodes'].values() if session_id and n.get('author', {}).get('session_id') == session_id]
        if own:
            primary = [max(own, key=lambda n: activity.get(n['id'], 0))['id']]
        selection = 'session_recent_fallback' if primary else 'unbound'
    reasons = {ref: ('explicit_focus' if ref in focus else 'event' if ref in event_nodes
                     else 'task_wait' if ref in waited_nodes else selection) for ref in primary}
    reasons.update({ref: 'task_entry' for ref in entries if ref not in reasons})
    owners = {ref: result['node_id'] for ref, result in graph['results'].items()}
    selected_assessments = {graph['nodes'][ref].get('assessment_ref') for ref in primary} - {None}
    edges = []
    for edge in sorted(graph['relations'].values(), key=lambda e: e['id']):
        if not edge['active']:
            continue
        source, target = owners.get(edge['source'], edge['source']), owners.get(edge['target'], edge['target'])
        declared = edge['kind'] in relations.DECLARED
        cited = edge['kind'] in {'uses', 'cites'} and (edge['source'] in selected_assessments
            or bool(selected_assessments.intersection(edge['basis_refs'])))
        if not (declared or cited) or target not in graph['nodes']:
            continue
        if source in primary or target in primary:
            for ref in (source, target):
                if ref in graph['nodes']:
                    reasons.setdefault(ref, 'direct_relation')
            edges.append({key: edge[key] for key in ('source', 'kind', 'target')})

    event_jobs = {}
    for event in events:
        event_jobs.setdefault(event['job_id'], []).append(event)
    candidates = {j['job_id']: j for j in jobs if j.get('node_id') in reasons or j['job_id'] in waited | event_jobs.keys()}
    for job_id in waited | event_jobs.keys():
        candidates.setdefault(job_id, {'job_id': job_id, 'state': 'unavailable', 'collection_state': 'unknown'})
    running = {'started', 'submitted', 'queued', 'held', 'running', 'unknown', 'unavailable'}
    candidates = [j for j in candidates.values() if j['job_id'] in waited | event_jobs.keys()
                  or j.get('state') in running or j.get('collection_state') != 'complete' or j.get('execution_conflict')]
    candidates.sort(key=lambda j: (j['job_id'] not in event_jobs, j['job_id'] not in waited,
                                   not bool(j.get('execution_conflict')), j.get('state') in running, j['job_id']))
    diagnostics = [d for d in relations.diagnostics(root) if any(ref in reasons for ref in d['node_ids'])]
    notes = recent_notes(root, reasons)
    note_identities = {ref: [] for ref in reasons}
    for header in index['records']:
        if header.get('node_id') in reasons and header['origin'] == 'agent' and header['kind'] == 'note':
            note_identities[header['node_id']].append({'ref': header['ref'], 'sequence': header['sequence']})
    view = {'scope': {'selection': selection},
            'nodes': [], 'jobs': [], 'relations': [],
            'wake_events': {'requested': len(events), 'included': 0, 'omitted': len(events)},
            'bounds': {'max_bytes': max_bytes, 'omitted': {'nodes': len(reasons), 'jobs': len(candidates),
                                                        'relations': len(edges), 'diagnostics': len(diagnostics),
                                                        'notes': sum(item['total'] for item in notes.values())}},
            'read_more': {'nodes': {'tool': 'research_read'}, 'history': {'tool': 'research_search'}}}
    # Scope counts are fixed even if a small transport budget cannot fit a card.
    view['scope'].update(entry_count=len(entries), focus_count=len(focus))
    if projection and projection.get('pending'):
        view['projection'] = {'pending': projection['pending']}
    if diagnostics:
        view['diagnostics'] = []

    def fits():
        # Reserve room for counter digit changes and final metadata.
        return size(view) <= max_bytes - 64

    def add(key, item, ceiling=max_bytes):
        view[key].append(item)
        view['bounds']['omitted'][key] -= 1
        if not fits() or size(view) > ceiling:
            view[key].pop()
            view['bounds']['omitted'][key] += 1
            return False
        return True

    def field(card, name, value):
        previous = card.get(name)
        existed = name in card
        card[name] = value
        if not fits():
            if existed:
                card[name] = previous
            else:
                del card[name]
            return False
        return True

    published = publication_order(root, graph)
    superseded = {r.get('supersedes') for r in published}
    other_results = {}
    for result in published:
        ref = result['node_id']
        if ref in reasons and result['id'] != graph['nodes'][ref].get('assessment_ref') and result['id'] not in superseded:
            other_results.setdefault(ref, []).append(result)
    assessments, cards = {}, {}
    # Bound identity lists too: a flood must not consume all room for findings
    # and failures. Counts and read paths make any omitted questions explicit.
    node_ceiling = size(view) + (max_bytes - size(view) - 64) * (0.45 if candidates else 0.65)
    # Reserve identities and review flags for all focal questions before detail.
    for ref, reason in reasons.items():
        node = graph['nodes'][ref]
        assessment_ref = node.get('assessment_ref')
        assessment = (get_result(root, assessment_ref) if assessment_ref.startswith('result_') else record(root, assessment_ref)) if assessment_ref else None
        notices = result_notices(root, assessment, graph) if assessment else []
        notices += assessment_notices(root, assessment_ref,
            [row for row in index['records'] if row.get('node_id') == ref])
        assessments[ref] = (assessment, notices)
        title = excerpt(node['title'], 120)
        card = {'id': ref, 'revision': node['revision'], 'status': node['status'], 'title': title,
                'assessment_ref': assessment_ref, 'selection': reason,
                'review_notice_count': len(notices), 'other_result_count': len(other_results.get(ref, [])),
                'omitted_fields': ['goal', 'plan']}
        card['omitted_fields'].extend(name for name in ('subjects',) if node.get(name))
        if notes[ref]['total']:
            card['recent_notes'] = {'records': [], 'total': notes[ref]['total'], 'omitted': notes[ref]['total'],
                                    'read': {'tool': 'research_search', 'node_id': ref, 'kind': 'note'}}
        if title != node['title']:
            card['omitted_fields'].append('title')
        if assessment:
            card['omitted_fields'].append('assessment')
            card['assessment'] = {'ref': assessment_ref,
                'kind': 'result' if assessment_ref.startswith('result_') else assessment['kind'],
                'conclusion': '', 'limitations': '', 'evidence_refs': [], 'content_omitted': True}
        if notices:
            card['omitted_fields'].append('review_notices')
        if add('nodes', card, node_ceiling):
            cards[ref] = card

    # Events are folded into the current Job state, never duplicate job cards.
    job_details = []
    job_ceiling = size(view) + (max_bytes - size(view) - 64) * 0.55
    for job in candidates:
        card = {k: job.get(k) for k in ('job_id', 'node_id', 'state', 'collection_state')}
        card['read'] = {'tool': 'job_status', 'job_id': job['job_id']}
        if job.get('execution_conflict'):
            card['execution_conflict'] = True
        wake = event_jobs.get(job['job_id'], [])
        if wake:
            card['event_ids'] = [e['event_id'] for e in wake]
        if job.get('error'):
            card['error_omitted'] = True
        if add('jobs', card, job_ceiling):
            job_details.append((job, card))
            view['wake_events']['included'] += len(wake)
            view['wake_events']['omitted'] -= len(wake)

    # Failure context precedes optional scientific excerpts and plans.
    for job, card in job_details:
        if job.get('error'):
            error = job['error'] if isinstance(job['error'], str) else json.dumps(job['error'], ensure_ascii=False)
            if field(card, 'error', excerpt(error, 400)):
                card['error_omitted'] = card['error'] != error

    # A selected judgment, its limitations and its citations are one unit.
    # Scientific text is never a prefix: missing content has an explicit ref.
    for ref, card in cards.items():
        assessment, notices = assessments[ref]
        if notices and field(card, 'review_notices', notices):
            card['omitted_fields'].remove('review_notices')
        if assessment:
            is_result = card['assessment_ref'].startswith('result_')
            content = assessment.get('conclusion', '') if is_result else assessment['content']
            limitations = assessment.get('limitations') or ''
            judgment = {'ref': card['assessment_ref'], 'conclusion': content,
                        'kind': 'result' if is_result else assessment['kind'],
                        'limitations': limitations,
                        'evidence_refs': assessment.get('evidence_refs', assessment.get('references', [])),
                        'content_omitted': False}
            if assessment.get('inputs'):
                judgment['inputs'] = assessment['inputs']
            if is_result:
                judgment['evidence_refs'] = list(dict.fromkeys(judgment['evidence_refs']
                    + assessment.get('check_refs', []) + list(assessment.get('subjects', {}).values())
                    + [item['artifact_ref'] for item in assessment.get('files', [])]))
            if field(card, 'assessment', judgment):
                card['omitted_fields'].remove('assessment')

    for name in ('goal', 'plan'):
        for ref, card in cards.items():
            original = graph['nodes'][ref].get(name)
            if field(card, name, original):
                card['omitted_fields'].remove(name)

    # Give each selected question its newest note before adding older notes.
    for index in range(max((len(item['records']) for item in notes.values()), default=0)):
        for ref, card in cards.items():
            records = notes[ref]['records']
            if index >= len(records):
                continue
            note = records[index]
            value = {'ref': note['ref'], 'sequence': note['sequence'], 'created_at': note['created_at'],
                     'content': note['content'], 'references': note['references'],
                     'content_omitted': False, 'reference_count': len(note['references'])}
            card['recent_notes']['records'].append(value)
            card['recent_notes']['omitted'] -= 1
            view['bounds']['omitted']['notes'] -= 1
            if not fits():
                value.update(content='', references=[], content_omitted=True)
                if not fits():
                    card['recent_notes']['records'].pop()
                    card['recent_notes']['omitted'] += 1
                    view['bounds']['omitted']['notes'] += 1

    for ref, card in cards.items():
        # Do not infer that collection, delivery or a newer output means review.
        other = other_results.get(ref, [])
        if other:
            field(card, 'other_results', [{'ref': r['id'], 'summary': excerpt(r['summary'], 200),
                                          'content_omitted': True} for r in other[-2:]])

    for edge in edges:
        if owners.get(edge['source'], edge['source']) in cards and owners.get(edge['target'], edge['target']) in cards:
            add('relations', edge)
    if diagnostics:
        for item in diagnostics:
            add('diagnostics', {'code': item['code'], 'node_ids': item['node_ids'][:3], 'node_count': len(item['node_ids'])})
    if size(view) > max_bytes:
        raise ValueError('brief_selection_budget_too_small')
    # Internal dependency set, including candidates omitted by the byte budget.
    # It is consumed by the brief builder, never included in model context.
    view['_basis'] = {'node_ids': sorted(reasons), 'job_ids': sorted({j['job_id'] for j in candidates}),
                      'relations': edges, 'diagnostics': diagnostics,
                      'notices': [(ref, notices) for ref, (_, notices) in sorted(assessments.items())],
                      'notes': {ref: {'total': notes[ref]['total'],
                                      'identities': sorted(note_identities[ref], key=lambda item: item['sequence']),
                                      'recent': [{'ref': item['ref'], 'content_digest': item['content_digest']}
                                                 for item in notes[ref]['records']]} for ref in sorted(notes)}}
    return view
