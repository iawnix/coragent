"""Evidence-directed recovery decisions for reaction-path searches.

The recovery planner never reruns or rewrites an attempt.  It consumes a
canonical attempt record and returns one immutable next decision for the
control plane to turn into a new Job.
"""

from __future__ import annotations

ROUTES = (
    "qst3",
    "qst2",
    "scan-xtb",
    "scan-gaussian",
    "neb-xtb",
    "neb-gaussian",
    "direct-ts",
)

STATUSES = ("failed", "partial", "completed", "succeeded", "unknown")
HARD_STOP = {
    "input_syntax",
    "route_mismatch",
    "mapping_mismatch",
    "electronic_state_mismatch",
    "execution_error",
    "unknown_job",
}


def _string(value: object, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} must be a non-empty string")
    return value


def _boolean(value: object, name: str) -> bool:
    if type(value) is not bool:
        raise ValueError(f"{name} must be boolean")
    return value


def _validate(spec: dict) -> tuple[dict, dict, dict]:
    if not isinstance(spec, dict) or spec.get("schema_version") != "chemical-search-recovery-input/1":
        raise ValueError("chemical-search-recovery-input/1 required")
    attempt = spec.get("attempt")
    context = spec.get("context")
    policy = spec.get("policy")
    if not isinstance(attempt, dict) or not isinstance(context, dict) or not isinstance(policy, dict):
        raise ValueError("attempt, context and policy are required objects")
    _string(attempt.get("id"), "attempt.id")
    _string(attempt.get("input_sha256"), "attempt.input_sha256")
    evidence_refs = attempt.get("evidence_refs")
    if not isinstance(evidence_refs, list) or not evidence_refs or any(not isinstance(item, str) or not item for item in evidence_refs):
        raise ValueError("attempt.evidence_refs must contain evidence references")
    route = _string(attempt.get("route"), "attempt.route")
    if route not in ROUTES:
        raise ValueError("attempt.route is not a supported search route")
    status = _string(attempt.get("status"), "attempt.status")
    if status not in STATUSES:
        raise ValueError("attempt.status is not supported")
    diagnosis = attempt.get("diagnosis")
    if not isinstance(diagnosis, dict):
        raise ValueError("attempt.diagnosis is required")
    primary = _string(diagnosis.get("primary"), "attempt.diagnosis.primary")
    events = diagnosis.get("events", [primary])
    if not isinstance(events, list) or not events or any(not isinstance(item, str) or not item for item in events):
        raise ValueError("attempt.diagnosis.events must contain diagnostic names")
    if events[0] != primary:
        raise ValueError("attempt.diagnosis.primary must be the first event")

    for key in ("mapping", "endpoint_compatibility", "geometry_preflight", "endpoints_minima"):
        value = _string(context.get(key), f"context.{key}")
        if value not in {"verified", "passed", "failed", "unknown", "unavailable"}:
            raise ValueError(f"context.{key} has unsupported status")
    coordinates = context.get("reaction_coordinates")
    if not isinstance(coordinates, list) or any(not isinstance(item, dict) for item in coordinates):
        raise ValueError("context.reaction_coordinates must be a list of coordinate declarations")
    candidate = context.get("candidate")
    if not isinstance(candidate, dict):
        raise ValueError("context.candidate is required")
    for key in ("available", "geometry_safe", "finite_gradients"):
        _boolean(candidate.get(key), f"context.candidate.{key}")

    allowed = policy.get("allowed_routes")
    if not isinstance(allowed, list) or not allowed or any(item not in ROUTES for item in allowed):
        raise ValueError("policy.allowed_routes must list supported routes")
    attempted = policy.get("attempted_routes", [])
    if not isinstance(attempted, list) or any(item not in ROUTES for item in attempted):
        raise ValueError("policy.attempted_routes must list supported routes")
    max_jobs = policy.get("max_jobs")
    jobs_used = policy.get("jobs_used")
    if type(max_jobs) is not int or max_jobs < 1 or type(jobs_used) is not int or jobs_used < 0:
        raise ValueError("policy job budget must be non-negative integers")
    if jobs_used > max_jobs:
        raise ValueError("policy.jobs_used cannot exceed policy.max_jobs")
    return attempt, context, policy


def _decision(attempt: dict, status: str, reason: str, *, next_route: str | None = None,
              changed_variables: list[str] | None = None, requires: list[str] | None = None) -> dict:
    return {
        "schema_version": "chemical-search-recovery-decision/1",
        "status": status,
        "parent_attempt_id": attempt["id"],
        "parent_route": attempt["route"],
        "parent_input_sha256": attempt["input_sha256"],
        "evidence_refs": attempt["evidence_refs"],
        "next_route": next_route,
        "reason": reason,
        "changed_variables": changed_variables or [],
        "requires": requires or [],
    }


def _can(policy: dict, route: str) -> bool:
    return route in policy["allowed_routes"] and route not in policy["attempted_routes"]


def _budget(policy: dict) -> bool:
    return policy["jobs_used"] < policy["max_jobs"]


def decide(spec: dict) -> dict:
    attempt, context, policy = _validate(spec)
    route = attempt["route"]
    status = attempt["status"]
    primary = attempt["diagnosis"]["primary"]
    events = attempt["diagnosis"]["events"]

    if status == "unknown" or primary == "unknown_job":
        return _decision(attempt, "needs_review", "reconcile_required", requires=["job_reconciliation"])
    if primary in HARD_STOP:
        return _decision(attempt, "needs_review", primary, requires=["repair_input_or_execution_route"])
    if primary == "segmentation" or primary == "signal":
        return _decision(attempt, "needs_review", "solver_crash_requires_review", requires=["inspect_primary_solver_diagnostic"])
    if not _budget(policy):
        return _decision(attempt, "exhausted", "search_job_budget_exhausted")

    if route == "qst3" and primary in {"coordinate_transform", "optimization_limit"}:
        if context["mapping"] == "verified" and context["endpoint_compatibility"] == "verified" and _can(policy, "qst2"):
            return _decision(attempt, "auto_continue", "qst3_guess_or_coordinate_failure", next_route="qst2",
                             changed_variables=["remove_intermediate_guess", "use_qst2_endpoint_interpolation"],
                             requires=["verified_mapping", "verified_endpoint_compatibility"])
    if route in {"qst3", "qst2"} and primary in {"optimization_limit", "scf_convergence", "coordinate_transform"}:
        if context["geometry_preflight"] == "passed" and context["reaction_coordinates"] and _can(policy, "scan-xtb"):
            return _decision(attempt, "auto_continue", "ts_search_failed_use_bounded_scan", next_route="scan-xtb",
                             changed_variables=["search_strategy", "backend", "bounded_reaction_coordinate"],
                             requires=["passed_geometry_preflight", "declared_reaction_coordinate"])

    if route in {"scan-xtb", "scan-gaussian"}:
        candidate = context["candidate"]
        if candidate["available"] and candidate["geometry_safe"] and candidate["finite_gradients"] and _can(policy, "direct-ts"):
            return _decision(attempt, "auto_continue", "promote_path_candidate_to_ts_search", next_route="direct-ts",
                             changed_variables=["seed", "optimization_task"],
                             requires=["highest_successful_candidate", "geometry_preflight", "finite_gradient"])
        if context["endpoints_minima"] == "verified" and context["endpoint_compatibility"] == "verified" and _can(policy, "neb-xtb"):
            return _decision(attempt, "auto_continue", "scan_does_not_supply_candidate_use_neb", next_route="neb-xtb",
                             changed_variables=["search_strategy", "backend", "path_images"],
                             requires=["verified_endpoint_minima", "verified_endpoint_compatibility"])

    if route in {"neb-xtb", "neb-gaussian"}:
        candidate = context["candidate"]
        if candidate["available"] and candidate["geometry_safe"] and candidate["finite_gradients"] and _can(policy, "direct-ts"):
            return _decision(attempt, "auto_continue", "promote_neb_candidate_to_ts_search", next_route="direct-ts",
                             changed_variables=["seed", "optimization_task"],
                             requires=["highest_fully_evaluated_internal_image", "geometry_preflight", "finite_gradient"])

    if status in {"completed", "succeeded"} and route not in {"scan-xtb", "scan-gaussian", "neb-xtb", "neb-gaussian"}:
        return _decision(attempt, "no_action", "route_completed_requires_next_scientific_check")
    if events and primary in {"irc_corrector_limit", "irc_hessian_missing"}:
        return _decision(attempt, "needs_review", primary, requires=["irc_specific_recovery"])
    return _decision(attempt, "needs_review", "no_evidence_safe_transition", requires=["revise_search_hypothesis"])
