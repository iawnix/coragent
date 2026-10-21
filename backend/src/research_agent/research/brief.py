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
        summary = assessment.get("conclusion") or node.get("progress") or node.get("goal") or node.get("title")
        findings.append(_source(ref, "node", summary, status=status,
                                assessment_ref=node.get("assessment_ref")))
        if node.get("review_notice_count"):
            codes = sorted({notice.get("code", "review_required") for notice in node.get("review_notices", [])})
            contradictions.append(_source(ref, "node_review", "; ".join(codes), codes=codes))
        if status in {"open", "paused"} and not node.get("assessment_ref"):
            uncertainties.append(_source(ref, "node", "No selected assessment is recorded", status=status))
            follow_up.append({"action": "inspect_or_continue_node", "ref": ref,
                              "reason": "The research question remains unresolved."})
        if node.get("assessment_ref"):
            source_refs.append(node["assessment_ref"])
            if assessment.get("limitations"):
                limitations.append(_source(node["assessment_ref"], "result_limitation", assessment["limitations"]))

    # A brief cites every published Result attached to the selected Nodes,
    # including preliminary results that were not selected as assessments.
    # The result body remains available through research_read; only its bounded
    # summary is projected here.
    for result in publication_order(root, graph):
        if result.get("node_id") not in selected:
            continue
        source_refs.append(result["id"])
        full_result = get_result(root, result["id"])
        source_refs.extend(full_result.get("inputs", []))
        source_refs.extend(full_result.get("evidence_refs", []))
        source_refs.extend(item.get("artifact_ref") for item in full_result.get("files", [])
                           if isinstance(item, dict) and item.get("artifact_ref"))
        if result["id"] not in {item.get("ref") for item in findings}:
            findings.append(_source(result["id"], "result", result.get("summary") or result.get("conclusion"),
                                    node_id=result.get("node_id"), supersedes=result.get("supersedes")))
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

    omitted = selection.get("bounds", {}).get("omitted", {})
    if any(value for key, value in omitted.items() if key in {"nodes", "jobs", "relations", "diagnostics"}):
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
                     "events": len(events), "omitted": omitted},
        "findings": findings,
        "contradictions": contradictions,
        "uncertainties": uncertainties,
        "limitations": limitations,
        "follow_up": follow_up,
        "source_refs": list(dict.fromkeys(source_refs)),
        "read_more": {"research": {"tool": "research_read"}, "jobs": {"tool": "job_status"}},
        "guidance": "This is a derived brief of recorded evidence. It does not certify scientific validity, authorize writes, schedule a run, or declare completion.",
        "projection_status": "incomplete" if projection and projection.get('pending') else "complete",
    }
    brief["brief_digest"] = "sha256:" + digest({key: value for key, value in brief.items() if key != "brief_digest"})
    if _size(brief) > max_bytes:
        # Keep the report useful under a tight transport budget.  Counts and
        # source references remain explicit when prose findings are truncated.
        for key in ("findings", "uncertainties", "limitations"):
            while brief[key] and _size(brief) > max_bytes:
                brief[key].pop()
        if _size(brief) > max_bytes:
            brief["follow_up"] = brief["follow_up"][:4]
        if _size(brief) > max_bytes:
            raise ValueError("brief_budget_too_small")
        brief["brief_digest"] = "sha256:" + digest({key: value for key, value in brief.items() if key != "brief_digest"})
    return brief
