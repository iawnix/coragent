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


def _text(value, limit=320):
    if not value:
        return ""
    value = str(value)
    encoded = value.encode("utf-8")
    if len(encoded) <= limit:
        return value
    return encoded[:limit].decode("utf-8", errors="ignore")


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
    item = {"ref": ref, "kind": kind, "summary": _text(summary)}
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
        summary = node.get("goal") or node.get("title")
        finding = _source(ref, "node", summary, status=status, assessment_ref=node.get("assessment_ref"))
        if node.get("plan"):
            finding['plan'] = _text(node['plan'])
        findings.append(finding)
        if node.get("review_notice_count"):
            codes = sorted({notice.get("code", "review_required") for notice in node.get("review_notices", [])})
            contradictions.append(_source(ref, "node_review", "; ".join(codes), codes=codes))
        if status in {"open", "paused"} and not node.get("assessment_ref"):
            uncertainties.append(_source(ref, "node", "No selected assessment is recorded", status=status))
            follow_up.append({"action": "inspect_or_continue_node", "ref": ref,
                              "reason": "The research question remains unresolved."})
        if node.get("assessment_ref"):
            source_refs.append(node["assessment_ref"])
            if assessment:
                refs = list(dict.fromkeys(assessment.get('evidence_refs', []) + assessment.get('inputs', [])))
                source_refs.extend(refs)
                findings.append(_source(node['assessment_ref'],
                    assessment['kind'] if assessment['kind'] in {'result', 'note'} else 'record',
                    assessment.get('conclusion'), node_id=ref, selected_assessment=True,
                    references=refs, content_omitted=assessment.get('content_omitted', False)
                    or _text(assessment.get('conclusion')) != assessment.get('conclusion')))
            if assessment.get("limitations"):
                limitations.append(_source(node["assessment_ref"], "result_limitation", assessment["limitations"]))
        for note in node.get('recent_notes', {}).get('records', []):
            if note['ref'] == node.get('assessment_ref'):
                continue
            source_refs.append(note['ref'])
            source_refs.extend(note['references'])
            findings.append(_source(note['ref'], 'note', note['content'], node_id=ref,
                sequence=note['sequence'], created_at=note['created_at'], references=note['references'],
                reference_count=note['reference_count'], selected_assessment=False,
                content_omitted=note['content_omitted'] or _text(note['content']) != note['content']))

    # Published Results remain distinct from the selected assessment. Their
    # summaries and explicit citations compete for the same bounded context.
    for result in publication_order(root, graph):
        if result.get("node_id") not in selected:
            continue
        source_refs.append(result["id"])
        full_result = get_result(root, result["id"])
        refs = list(dict.fromkeys(full_result.get('inputs', []) + full_result.get('evidence_refs', [])
                    + [item['artifact_ref'] for item in full_result.get('files', [])
                       if isinstance(item, dict) and item.get('artifact_ref')]))
        source_refs.extend(refs[:4])
        if result["id"] not in {item.get("ref") for item in findings}:
            summary = result.get("summary") or result.get("conclusion") or ''
            findings.append(_source(result["id"], "result", summary,
                                    node_id=result.get("node_id"), supersedes=result.get("supersedes"),
                                    references=refs[:4], reference_count=len(refs),
                                    content_omitted=_text(summary) != summary or len(refs) > 4))
        if result.get("limitations"):
            limitations.append(_source(result["id"], "result_limitation", result["limitations"]))

    terminal = {"succeeded", "failed", "timed_out", "cancelled"}
    for job in selection.get("jobs", []):
        ref = job["job_id"]
        source_refs.append(ref)
        state = job.get("state")
        findings.append(_source(ref, "job", state or "unknown", node_id=job.get("node_id"), state=state,
                                collection_state=job.get("collection_state")))
        if state == "failed" or job.get("execution_conflict"):
            reason = _text(job.get("error") or "Execution failed or conflicted")
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
        "guidance": "This is a derived brief of recorded evidence. Notes are process records; only an explicit assessment_ref selects a current assessment. It does not certify scientific validity, authorize writes, schedule a run, or declare completion.",
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
    # Keep at least each question's latest note ahead of older process detail.
    note_nodes = set()
    older_notes = []
    for item in findings:
        if item['kind'] == 'note' and not item.get('selected_assessment'):
            if item['node_id'] in note_nodes:
                older_notes.append(item)
            note_nodes.add(item['node_id'])
    optional = list(reversed(older_notes)) + [item for item in reversed(findings)
                if item['kind'] == 'result' and not item.get('selected_assessment')]
    for item in optional:
        if _size(brief) <= max_bytes:
            break
        brief['findings'].remove(item)
        refresh()
    for item in brief['findings']:
        if _size(brief) <= max_bytes:
            break
        if item.pop('plan', None) is not None:
            refresh()
    for key in ('uncertainties', 'limitations', 'follow_up', 'findings', 'contradictions'):
        while brief[key] and _size(brief) > max_bytes:
            brief[key].pop()
            refresh()
    if _size(brief) > max_bytes:
        raise ValueError('brief_budget_too_small')
    return brief
