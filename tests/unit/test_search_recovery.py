import json
import os

import pytest

from tests.unit.chemical_paths import configure

configure()
from recovery import decide


def spec(route="qst3", primary="optimization_limit", *, status="failed"):
    return {
        "schema_version": "chemical-search-recovery-input/1",
        "attempt": {
            "id": "attempt-1",
            "input_sha256": "sha256:" + "a" * 64,
            "evidence_refs": ["artifact:diagnosis-1"],
            "route": route,
            "status": status,
            "diagnosis": {"primary": primary, "events": [primary]},
        },
        "context": {
            "mapping": "verified",
            "endpoint_compatibility": "verified",
            "geometry_preflight": "passed",
            "endpoints_minima": "verified",
            "reaction_coordinates": [{"kind": "distance", "atoms": ["atom_1", "atom_2"]}],
            "candidate": {"available": False, "geometry_safe": False, "finite_gradients": False},
        },
        "policy": {
            "allowed_routes": ["qst3", "qst2", "scan-xtb", "neb-xtb", "direct-ts"],
            "attempted_routes": [route],
            "max_jobs": 6,
            "jobs_used": 1,
        },
    }


def test_qst3_coordinate_failure_degrades_to_qst2():
    result = decide(spec(primary="coordinate_transform"))
    assert result["status"] == "auto_continue"
    assert result["next_route"] == "qst2"
    assert result["parent_attempt_id"] == "attempt-1"
    assert "remove_intermediate_guess" in result["changed_variables"]


def test_qst2_numerical_failure_degrades_to_bounded_xtb_scan():
    result = decide(spec(route="qst2", primary="scf_convergence"))
    assert result["status"] == "auto_continue"
    assert result["next_route"] == "scan-xtb"
    assert "declared_reaction_coordinate" in result["requires"]


def test_scan_candidate_promotes_to_direct_ts():
    value = spec(route="scan-xtb", primary="optimization_limit")
    value["context"]["candidate"] = {"available": True, "geometry_safe": True, "finite_gradients": True}
    result = decide(value)
    assert result["status"] == "auto_continue"
    assert result["next_route"] == "direct-ts"


def test_scan_without_candidate_uses_neb_only_with_verified_endpoints():
    value = spec(route="scan-xtb", primary="optimization_limit")
    result = decide(value)
    assert result["next_route"] == "neb-xtb"
    value["context"]["endpoints_minima"] = "unknown"
    result = decide(value)
    assert result["status"] == "needs_review"
    assert result["next_route"] is None


@pytest.mark.parametrize("diagnostic", ["input_syntax", "mapping_mismatch", "route_mismatch", "execution_error"])
def test_input_and_execution_failures_never_degrade(diagnostic):
    result = decide(spec(primary=diagnostic))
    assert result["status"] == "needs_review"
    assert result["next_route"] is None


def test_bare_solver_signal_requires_review():
    result = decide(spec(primary="segmentation"))
    assert result["status"] == "needs_review"
    assert result["reason"] == "solver_crash_requires_review"


def test_unknown_job_requires_reconciliation():
    value = spec(primary="unknown_job", status="unknown")
    result = decide(value)
    assert result["status"] == "needs_review"
    assert result["reason"] == "reconcile_required"


def test_route_loop_and_budget_are_exhausted():
    value = spec(route="qst3", primary="optimization_limit")
    value["policy"]["attempted_routes"].append("qst2")
    result = decide(value)
    assert result["status"] == "auto_continue"
    assert result["next_route"] == "scan-xtb"
    value["policy"]["jobs_used"] = value["policy"]["max_jobs"]
    assert decide(value)["status"] == "exhausted"


def test_cli_writes_new_decision_directory(tmp_path):
    from recovery_cli import parse_arguments, run

    source = tmp_path / "input.json"
    source.write_text(json.dumps(spec()), encoding="utf-8")
    output = tmp_path / "results"
    result = run(parse_arguments(["--input", str(source), "--output-dir", str(output)]))
    assert result["next_route"] == "qst2"
    assert json.loads((output / "result.json").read_text(encoding="utf-8")) == result


def test_registered_recovery_executor_prepares_a_pinned_job(tmp_path):
    from research_agent.application.executors import prepare

    source = tmp_path / "input.json"
    source.write_text(json.dumps(spec()), encoding="utf-8")
    request = prepare(os.environ["CORAGENT_JOB_CONFIG"], {'platform': 'local', 'scheduler_entry': 'main'}, "chemical.search-recovery", "1", {"input": source})
    assert request["metadata"]["executor"] == {"id": "chemical.search-recovery", "version": "1"}
    assert request["outputs"] == [{"path": "results", "recursive": True, "required": False, "min_bytes": 0},
                                  {"path": "results/result.json", "required": True, "min_bytes": 2,
                                   "media_type": "application/json"}]
