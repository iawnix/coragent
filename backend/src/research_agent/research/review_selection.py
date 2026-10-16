"""Internal selection of bounded facts for the canonical Research Review."""
import json
import re

from . import relations
from .context import result_notices
from .records import journal, record
from .results import get_result, publication_order


def size(value):
    return len(json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode())


def excerpt(text, budget):
    """Prefer whole paragraphs/sentences; never paraphrase scientific content."""
    text = text or ''
    if len(text.encode()) <= budget:
        return text
    prefix = text.encode()[:budget].decode('utf-8', errors='ignore')
    boundaries = list(re.finditer(r'\n|[。！？.!?](?:\s|$)', prefix))
    if boundaries and boundaries[-1].end() >= len(prefix) // 2:
        prefix = prefix[:boundaries[-1].end()]
    return prefix


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
    selected_results = {graph['nodes'][ref].get('assessment_ref') for ref in primary}
    edges = []
    for edge in sorted(graph['relations'].values(), key=lambda e: e['id']):
        if not edge['active']:
            continue
        source, target = owners.get(edge['source'], edge['source']), owners.get(edge['target'], edge['target'])
        declared = edge['kind'] in relations.DECLARED
        cited = edge['kind'] in {'uses', 'cites'} and edge['source'] in selected_results
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
    view = {'scope': {'selection': selection},
            'nodes': [], 'jobs': [], 'relations': [],
            'wake_events': {'requested': len(events), 'included': 0, 'omitted': len(events)},
            'bounds': {'max_bytes': max_bytes, 'omitted': {'nodes': len(reasons), 'jobs': len(candidates),
                                                        'relations': len(edges), 'diagnostics': len(diagnostics)}},
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
        card[name] = value
        if not fits():
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
        notices = result_notices(root, assessment, graph) if assessment and assessment_ref.startswith('result_') else []
        assessments[ref] = (assessment, notices)
        title = excerpt(node['title'], 120)
        card = {'id': ref, 'revision': node['revision'], 'status': node['status'], 'title': title,
                'assessment_ref': assessment_ref, 'selection': reason,
                'review_notice_count': len(notices), 'other_result_count': len(other_results.get(ref, [])),
                'omitted_fields': ['goal', 'progress', 'plan']}
        card['omitted_fields'].extend(name for name in ('proposal', 'subjects') if node.get(name))
        if title != node['title']:
            card['omitted_fields'].append('title')
        if assessment:
            card['omitted_fields'].append('assessment')
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

    # A modest per-field allowance distributes detail across multiple focuses.
    text_budget = max(96, min(720, (max_bytes - size(view)) // max(1, len(cards) * 6)))
    for ref, card in cards.items():
        assessment, notices = assessments[ref]
        if notices and field(card, 'review_notices', notices):
            card['omitted_fields'].remove('review_notices')
        if assessment:
            is_result = card['assessment_ref'].startswith('result_')
            content = assessment.get('conclusion', '') if is_result else assessment['content']
            limitations = assessment.get('limitations') or ''
            judgment = {'ref': card['assessment_ref'], 'conclusion': excerpt(content, text_budget),
                        'limitations': excerpt(limitations, text_budget),
                        'evidence_refs': assessment.get('evidence_refs', [])[:4]}
            if assessment.get('inputs'):
                judgment['inputs'] = assessment['inputs'][:4]
            judgment['content_omitted'] = (judgment['conclusion'] != content or judgment['limitations'] != limitations
                                           or len(assessment.get('evidence_refs', [])) > 4 or len(assessment.get('inputs', [])) > 4)
            if field(card, 'assessment', judgment):
                card['omitted_fields'].remove('assessment')

    for name in ('goal', 'progress', 'plan'):
        for ref, card in cards.items():
            original = graph['nodes'][ref].get(name)
            value = excerpt(original, text_budget) if isinstance(original, str) else original
            if field(card, name, value) and value == original:
                card['omitted_fields'].remove(name)

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
        raise ValueError('review_selection_budget_too_small')
    return view
