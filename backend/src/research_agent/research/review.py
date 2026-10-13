"""A bounded, deterministic review of the current research state.

Research Review is a disposable context projection.  It is deliberately
domain neutral: scientific interpretation belongs to the agent and domain
skills, while this module reports what is present, missing, contradictory, or
still running in the canonical research records.
"""
from __future__ import annotations

import json

from . import relations
from .decision_view import build as build_decision
from .records import digest, journal
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


def _state_digest(graph, index, jobs, events):
    """Digest facts that can change the review, without embedding their text."""
    state = {
        "sequence": index["sequence"],
        "nodes": [
            {k: node.get(k) for k in ("id", "revision", "status", "assessment_ref")}
            for node in sorted(graph["nodes"].values(), key=lambda item: item["id"])
        ],
        "results": [
            {k: result.get(k) for k in ("id", "node_id", "supersedes", "content_digest")}
            for result in sorted(graph["results"].values(), key=lambda item: item["id"])
        ],
        "relations": [
            {k: edge.get(k) for k in ("id", "source", "kind", "target", "active")}
            for edge in sorted(graph["relations"].values(), key=lambda item: item["id"])
            if edge.get("active")
        ],
        "jobs": [
            {k: job.get(k) for k in ("job_id", "node_id", "state", "collection_state", "error", "execution_conflict", "latest_result_receipt_ref")}
            for job in sorted(jobs, key=lambda item: item.get("job_id", ""))
        ],
        "events": [
            {k: event.get(k) for k in ("event_id", "job_id", "node_id", "state", "status_digest")}
            for event in sorted(events, key=lambda item: item.get("event_id", ""))
        ],
    }
    return "sha256:" + digest(state)


def _source(ref, kind, summary, **extra):
    item = {"ref": ref, "kind": kind, "summary": _text(summary)}
    item.update(extra)
    return item


def build(root, *, max_bytes=8000, session_id=None, entry_node_ids=(),
          focus_node_ids=(), events=(), jobs=(), waited_job_ids=(), projection=None,
          trigger="context_refresh", source_bindings=()):
    if not 2048 <= max_bytes <= 32000:
        raise ValueError("review_budget_invalid: use 2048..32000 bytes")

    graph, index = relations.graph(root), journal(root)
    decision = build_decision(root, max_bytes=min(12000, max_bytes), session_id=session_id,
                              entry_node_ids=entry_node_ids, focus_node_ids=focus_node_ids,
                              events=events, jobs=jobs, waited_job_ids=waited_job_ids,
                              projection=projection)
    state_digest = _state_digest(graph, index, jobs, events)
    selected = {node["id"] for node in decision.get("nodes", [])}
    selected_jobs = {job["job_id"] for job in decision.get("jobs", [])}
    findings, contradictions, uncertainties, limitations, follow_up = [], [], [], [], []
    source_refs = []

    for node in decision.get("nodes", []):
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

    # A review cites every published Result attached to the selected Nodes,
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
    for job in decision.get("jobs", []):
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

    for diagnostic in decision.get("diagnostics", []):
        code = diagnostic.get("code", "diagnostic")
        ids = diagnostic.get("node_ids", [])
        contradictions.append(_source(ids[0] if ids else code, "diagnostic", code,
                                      node_ids=ids, node_count=diagnostic.get("node_count", len(ids))))

    omitted = decision.get("bounds", {}).get("omitted", {})
    if any(value for key, value in omitted.items() if key in {"nodes", "jobs", "relations", "diagnostics"}):
        limitations.append(_source("research-decision", "bounded_view", "Some scoped records were omitted; read current records before deciding."))
    if projection and projection.get("pending"):
        limitations.append(_source("runtime-projection", "pending_projection", "Runtime Job events still need reconciliation."))

    status = "attention" if contradictions else "uncertain" if uncertainties else "oriented"
    review = {
        "schema_version": "research-review/1",
        "review_id": "review_" + state_digest.removeprefix("sha256:"),
        "state_digest": state_digest,
        "status": status,
        "scope": {"selection": decision.get("scope", {}).get("selection", "unbound"),
                  "entry_node_ids": list(entry_node_ids), "focus_node_ids": list(focus_node_ids)},
        "user_sources": list(source_bindings),
        "coverage": {"research_sequence": index["sequence"], "nodes": len(selected),
                     "jobs": len(selected_jobs), "results": len(graph["results"]),
                     "events": len(events), "omitted": omitted},
        "findings": findings,
        "contradictions": contradictions,
        "uncertainties": uncertainties,
        "limitations": limitations,
        "follow_up": follow_up,
        "source_refs": list(dict.fromkeys(source_refs)),
        "read_more": {"research": {"tool": "research_read"}, "jobs": {"tool": "job_status"}},
        "guidance": "This is a derived review of recorded evidence. It does not certify scientific validity, authorize writes, schedule a run, or declare completion.",
    }
    pending_trigger = trigger in {"new_evidence", "goal_changed", "explicit"}
    review["trigger"] = (trigger if pending_trigger else
                          ("new_evidence" if projection and projection.get("pending") else "context_refresh"))
    review["review_status"] = "pending" if pending_trigger or (projection and projection.get("pending")) else "current"
    review["review_digest"] = "sha256:" + digest({key: value for key, value in review.items() if key != "review_digest"})
    if _size(review) > max_bytes:
        # Keep the report useful under a tight transport budget.  Counts and
        # source references remain explicit when prose findings are truncated.
        for key in ("findings", "uncertainties", "limitations"):
            while review[key] and _size(review) > max_bytes:
                review[key].pop()
        if _size(review) > max_bytes:
            review["follow_up"] = review["follow_up"][:4]
        if _size(review) > max_bytes:
            raise ValueError("review_budget_too_small")
        review["review_digest"] = "sha256:" + digest({key: value for key, value in review.items() if key != "review_digest"})
    return review
