"""A bounded, deterministic brief of the current research state.

Research Brief is a disposable context projection.  It is deliberately
domain neutral: scientific interpretation belongs to the agent and domain
skills, while this module reports what is present, missing, contradictory, or
still running in the canonical research records.
"""
from __future__ import annotations

import json

from . import relations
from .brief_selection import build as build_selection
from .records import digest
from .results import get_result, publication_order


def _size(value):
    return len(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode())


def _state_digest(graph, selection, jobs, projection, source_bindings):
    """Track scoped facts, including omitted records; unrelated activity is irrelevant."""
    basis = selection['_basis']
    nodes = set(basis['node_ids'])
    job_ids = set(basis['job_ids'])
    state = {
        "selection": selection['scope'],
        "sources": source_bindings,
        "projection": projection,
        "nodes": [
            node
            for node in sorted(graph["nodes"].values(), key=lambda item: item["id"])
            if node['id'] in nodes
        ],
        "results": [
            result
            for result in sorted(graph["results"].values(), key=lambda item: item["id"])
            if result.get('node_id') in nodes
        ],
        "relations": basis['relations'],
        "diagnostics": basis['diagnostics'],
        "notices": basis['notices'],
        "notes": basis['notes'],
        "jobs": [
            {k: job.get(k) for k in ("job_id", "node_id", "state", "collection_state", "error", "execution_conflict", "latest_result_receipt_ref")}
            for job in sorted(jobs, key=lambda item: item.get("job_id", ""))
            if job.get('node_id') in nodes or job.get('job_id') in job_ids
        ],
    }
    return "sha256:" + digest(state)


def _source(ref, kind, summary, **extra):
    item = {"ref": ref, "kind": kind, "summary": summary or ''}
    item.update(extra)
    return item


def build(root, *, max_bytes=8000, session_id=None, entry_node_ids=(),
          focus_node_ids=(), events=(), jobs=(), waited_job_ids=(), projection=None,
          source_bindings=()):
    if not 2048 <= max_bytes <= 32000:
        raise ValueError("brief_budget_invalid: use 2048..32000 bytes")

    graph = relations.graph(root)
    selection = build_selection(root, max_bytes=min(12000, max_bytes), session_id=session_id,
                              entry_node_ids=entry_node_ids, focus_node_ids=focus_node_ids,
                              events=events, jobs=jobs, waited_job_ids=waited_job_ids,
                              projection=projection)
    state_digest = _state_digest(graph, selection, jobs, projection, source_bindings)
    selected = {node["id"] for node in selection.get("nodes", [])}
    selected_jobs = {job["job_id"] for job in selection.get("jobs", [])}
    findings, contradictions, uncertainties, limitations, follow_up = [], [], [], [], []
    source_refs = []

    for node in selection.get("nodes", []):
        ref = node["id"]
        source_refs.append(ref)
        status = node.get("status")
        assessment = node.get("assessment") or {}
        summary = node.get("goal", '')
        omitted_fields = [field for field in node['omitted_fields'] if field in {'goal', 'plan'}]
        finding = _source(ref, "node", summary, status=status, assessment_ref=node.get("assessment_ref"),
                          title=node['title'], updated_at=node['updated_at'],
                          read={'tool': 'research_read', 'ref': ref}, omitted_fields=omitted_fields)
        if node.get("plan"):
            finding['plan'] = node['plan']
        findings.append(finding)
        if node.get("review_notice_count"):
            codes = sorted({notice.get("code", "review_required") for notice in node.get("review_notices", [])})
            changed = [notice for notice in node.get('review_notices', [])
                       if notice['code'] == 'new_evidence_after_assessment']
            for notice in changed:
                source_refs.extend(notice['references'])
                uncertainties.append(_source(ref, 'assessment_review',
                    'Evidence was recorded after the selected assessment; review its relevance before continuing.',
                    assessment_ref=node['assessment_ref'], references=notice['references'],
                    code=notice['code']))
                follow_up.append({'action': 'review_new_evidence', 'ref': ref,
                                  'reason': 'Newer evidence does not automatically invalidate the selected assessment.',
                                  'read': {'tool': 'research_read', 'ref': ref}})
            review_codes = [code for code in codes if code != 'new_evidence_after_assessment']
            if review_codes or not codes:
                contradictions.append(_source(ref, "node_review", "; ".join(review_codes) or 'Review notices omitted; read the node.',
                                              codes=review_codes, read={'tool': 'research_read', 'ref': ref}))
        if status in {"open", "paused"} and not node.get("assessment_ref"):
            uncertainties.append(_source(ref, "node", "No selected assessment is recorded", status=status,
                                         code='current_assessment_missing'))
            follow_up.append({"action": "inspect_or_continue_node", "ref": ref,
                              "reason": "Read the recorded progress and select a current judgment before relying on this brief.",
                              'read': {'tool': 'research_read', 'ref': ref}})
        if node.get("assessment_ref"):
            source_refs.append(node["assessment_ref"])
            if assessment:
                refs = list(dict.fromkeys(assessment.get('evidence_refs', []) + assessment.get('inputs', [])))
                source_refs.extend(refs)
                findings.append(_source(node['assessment_ref'],
                    assessment['kind'] if assessment['kind'] in {'result', 'note'} else 'record',
                    assessment.get('conclusion'), node_id=ref, selected_assessment=True,
                    created_at=assessment['created_at'],
                    limitations=assessment.get('limitations', ''), references=refs,
                    content_omitted=assessment.get('content_omitted', False),
                    read={'tool': 'research_read', 'ref': node['assessment_ref']}))
                if node.get('review_notice_count'):
                    findings[-1]['review_required'] = True
                    findings[-1]['review_codes'] = codes or ['review_notices_omitted']
        for note in node.get('recent_notes', {}).get('records', []):
            if note['ref'] == node.get('assessment_ref'):
                continue
            source_refs.append(note['ref'])
            source_refs.extend(note['references'])
            findings.append(_source(note['ref'], 'note', note['content'], node_id=ref,
                sequence=note['sequence'], created_at=note['created_at'], references=note['references'],
                reference_count=note['reference_count'], selected_assessment=False,
                content_omitted=note['content_omitted'], read={'tool': 'research_read', 'ref': note['ref']}))

    # Published Results remain distinct from the selected assessment. Their
    # summaries and explicit citations compete for the same bounded context.
    for result in publication_order(root, graph):
        if result.get("node_id") not in selected:
            continue
        source_refs.append(result["id"])
        full_result = get_result(root, result["id"])
        refs = list(dict.fromkeys(full_result.get('inputs', []) + full_result.get('evidence_refs', [])
                    + full_result.get('check_refs', []) + list(full_result.get('subjects', {}).values())
                    + [item['artifact_ref'] for item in full_result.get('files', [])
                       if isinstance(item, dict) and item.get('artifact_ref')]))
        source_refs.extend(refs)
        if result["id"] not in {item.get("ref") for item in findings}:
            summary = full_result['conclusion']
            findings.append(_source(result["id"], "result", summary,
                                    node_id=result.get("node_id"), supersedes=result.get("supersedes"),
                                    created_at=result['created_at'],
                                    limitations=full_result.get('limitations') or '',
                                    references=refs, reference_count=len(refs), content_omitted=False,
                                    read={'tool': 'research_read', 'ref': result['id']}))

    terminal = {"succeeded", "failed", "timed_out", "cancelled"}
    for job in selection.get("jobs", []):
        ref = job["job_id"]
        source_refs.append(ref)
        state = job.get("state")
        findings.append(_source(ref, "job", state or "unknown", node_id=job.get("node_id"), state=state,
                                collection_state=job.get("collection_state"), waited=ref in waited_job_ids,
                                read={'tool': 'job_status', 'job_id': ref}))
        if state == "failed" or job.get("execution_conflict"):
            reason = job.get("error") or "Execution failed or conflicted"
            contradictions.append(_source(ref, "job_failure", reason, state=state))
            follow_up.append({"action": "inspect_job", "ref": ref, "reason": reason,
                              "read": {"tool": "job_status", "job_id": ref}})
        elif state not in terminal or job.get("collection_state") != "complete":
            uncertainties.append(_source(ref, "job", "Execution or result collection is incomplete", state=state))
            follow_up.append({"action": "reconcile_job", "ref": ref, "reason": "Job evidence is not complete.",
                              "read": {"tool": "job_status", "job_id": ref}})

    for diagnostic in selection.get("diagnostics", []):
        code = diagnostic.get("code", "diagnostic")
        ids = diagnostic.get("node_ids", [])
        contradictions.append(_source(ids[0] if ids else code, "diagnostic", code,
                                      node_ids=ids, node_count=diagnostic.get("node_count", len(ids))))
        source_refs.extend(ids)

    omitted = selection.get("bounds", {}).get("omitted", {})
    if any(omitted.values()):
        limitations.append(_source("research-brief", "bounded_view", "Some scoped records were omitted; read current records before deciding."))
    if projection and projection.get("pending"):
        limitations.append(_source("runtime-projection", "pending_projection", "Runtime Job events still need reconciliation."))

    status = "attention" if contradictions else "uncertain" if uncertainties else "oriented"
    brief = {
        "schema_version": "research-brief/1",
        "brief_id": "brief_" + state_digest.removeprefix("sha256:"),
        "state_digest": state_digest,
        "status": status,
        "scope": {"selection": selection.get("scope", {}).get("selection", "unbound"),
                  "entry_node_ids": list(entry_node_ids), "focus_node_ids": list(focus_node_ids)},
        "user_sources": list(source_bindings),
        "coverage": {"nodes": len(selected),
                     "jobs": len(selected_jobs), "results": sum(r.get('node_id') in selected for r in graph['results'].values()),
                     "notes": 0, "events": len(events), "omitted": dict(omitted)},
        "findings": findings,
        "contradictions": contradictions,
        "uncertainties": uncertainties,
        "limitations": limitations,
        "follow_up": follow_up,
        "source_refs": list(dict.fromkeys(source_refs)),
        "read_more": {"research": {"tool": "research_read"}, "jobs": {"tool": "job_status"},
                      "history": {"tool": "research_search", "kind": "note"}},
        "guidance": "This is a derived brief of recorded evidence. Notes are process records; only assessment_ref selects the current judgment. Read content_omitted records and omitted_fields before relying on them; no text is partially quoted. Newer evidence needs review, not automatic rejection. This brief does not certify validity or completion.",
        "projection_status": "incomplete" if projection and projection.get('pending') else "complete",
    }
    scoped = set(selection['_basis']['node_ids'])
    totals = {'nodes': len(scoped), 'jobs': len(selection['_basis']['job_ids']),
              'results': sum(result.get('node_id') in scoped for result in graph['results'].values()),
              'notes': sum(item['total'] for item in selection['_basis']['notes'].values())}
    known_refs = set(source_refs)

    def refresh():
        # Citations name actual visible facts or their explicit references;
        # truncating prose must not leave an unbounded hidden citation list.
        refs = []
        for item in sum((brief[key] for key in ('findings', 'contradictions', 'uncertainties', 'limitations', 'follow_up')), []):
            refs.extend([item.get('ref'), item.get('assessment_ref'), item.get('node_id')])
            refs.extend(item.get('references', []))
            refs.extend(item.get('node_ids', []))
        brief['source_refs'] = list(dict.fromkeys(ref for ref in refs if ref in known_refs))
        for category, kind in [('nodes', 'node'), ('jobs', 'job'), ('results', 'result'), ('notes', 'note')]:
            included = len({item['ref'] for item in brief['findings'] if item['kind'] == kind})
            brief['coverage'][category] = included
            brief['coverage']['omitted'][category] = max(0, totals[category] - included)
        brief['brief_digest'] = 'sha256:' + digest({key: value for key, value in brief.items() if key != 'brief_digest'})

    refresh()
    # Current judgments and live Job identities take precedence over process
    # history. Full conclusions, caveats and references are kept or omitted
    # together, never independently trimmed by a transport byte budget.
    note_nodes = set()
    older_notes = []
    for item in findings:
        if item['kind'] == 'note' and not item.get('selected_assessment'):
            if item['node_id'] in note_nodes:
                older_notes.append(item)
            note_nodes.add(item['node_id'])
    optional = (list(reversed(older_notes))
        + [item for item in findings if item['kind'] == 'result' and not item.get('selected_assessment')]
        + [item for item in reversed(findings) if item['kind'] == 'note'
           and not item.get('selected_assessment') and item not in older_notes])
    for item in optional:
        if _size(brief) <= max_bytes:
            break
        brief['findings'].remove(item)
        refresh()
    for item in brief['findings']:
        if _size(brief) <= max_bytes:
            break
        if item.pop('plan', None) is not None:
            item['omitted_fields'] = list(dict.fromkeys(item.get('omitted_fields', []) + ['plan']))
            refresh()

    # Remove duplicate navigation prose before making the selected judgment
    # unread. Every finding already carries its own exact read operation.
    for key in ('follow_up', 'limitations', 'uncertainties', 'contradictions'):
        while brief[key] and _size(brief) > max_bytes:
            brief[key].pop()
            refresh()
    for item in brief['findings']:
        if _size(brief) <= max_bytes:
            break
        if item['kind'] == 'node' and item['summary']:
            item['summary'] = ''
            item['omitted_fields'] = list(dict.fromkeys(item['omitted_fields'] + ['goal']))
            refresh()
    for item in reversed(brief['findings']):
        if _size(brief) <= max_bytes:
            break
        if item.get('selected_assessment') and not item['content_omitted']:
            item.update(summary='', limitations='', references=[], content_omitted=True)
            refresh()
    # If even identities exceed the budget, omit peripheral entries first.
    # Coverage reports their absence; no prefix is presented as evidence.
    removal = sorted(brief['findings'], key=lambda item: (
        bool(item.get('selected_assessment')), bool(item.get('waited')),
        item['kind'] == 'job'), reverse=False)
    for item in removal:
        if _size(brief) <= max_bytes:
            break
        brief['findings'].remove(item)
        refresh()
    if _size(brief) > max_bytes:
        raise ValueError('brief_budget_too_small')
    return brief
