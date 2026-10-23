from __future__ import annotations

from pathlib import Path
import sys
import time

import pytest

from research_agent.jobs import JobOutput, JobManager, JobSpec, JobState, ExternalJobPlatform, platforms_from_config
from research_agent.application.execution import _spec


def _job_manager() -> JobManager:
    platforms, default = platforms_from_config()
    return JobManager(platforms, default)


def _wait(runtime: JobManager, receipt):
    for _ in range(300):
        status = runtime.job_status(receipt)
        if status.state not in {JobState.QUEUED, JobState.RUNNING, JobState.SUBMITTED}:
            return status
        time.sleep(0.01)
    raise AssertionError("job did not reach a terminal state")


def test_arbitrary_argv_job_collects_declared_output(tmp_path: Path) -> None:
    work = tmp_path / "work"
    work.mkdir()
    runtime = _job_manager()
    spec = JobSpec(metadata={"resources": {"cpus": 1, "memory_mb": 512}}, job_id="job_1",
        command=(sys.executable, "-c", "from pathlib import Path; Path('result.txt').write_text('ok')"),
        cwd=work,
        outputs=(JobOutput("result.txt", required=True, media_type="text/plain"),),
    )

    receipt = runtime.job_start(spec)
    status = _wait(runtime, receipt)
    collected = runtime.job_collect(receipt)

    assert status.state is JobState.SUCCEEDED
    assert collected["outputs"] == [{
        "path": "result.txt",
        "required": True,
        "exists": True,
        "size": 2,
        "sha256": "2689367b205c16ce32ed4200942b8b8b1e262dfc70d9bc9fbc77c49699a4f1df",
    }]


def test_job_probe_reports_missing_cwd_or_inputs_without_execution(tmp_path: Path) -> None:
    runtime = _job_manager()
    spec = JobSpec(metadata={"resources": {"cpus": 1, "memory_mb": 512}}, job_id="job_1", command=(sys.executable, "-c", "raise SystemExit(99)"), cwd=tmp_path / "missing")

    probe = runtime.job_probe(spec)

    assert probe["platform"] == "local/main"
    assert probe["cwd_exists"] is False


def test_output_paths_cannot_escape_job_cwd(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="stay below cwd"):
        JobSpec(metadata={"resources": {"cpus": 1, "memory_mb": 512}}, job_id="job_1", command=(sys.executable,), cwd=tmp_path, outputs=(JobOutput("../outside"),))


def test_job_runtime_preserves_research_identity_without_domain_parsing(tmp_path: Path) -> None:
    tmp_path = tmp_path / "job"
    tmp_path.mkdir()
    runtime = _job_manager()
    request = JobSpec(
        metadata={"resources": {"cpus": 1, "memory_mb": 512}},
        command=(sys.executable, "-c", "print('raw evidence')"),
        cwd=tmp_path,
        workspace_id="ws_demo",
        job_id="job_1",
    )

    receipt = runtime.job_start(request)
    status = _wait(runtime, receipt)

    assert status.state is JobState.SUCCEEDED
    assert receipt.job_id == "job_1"
    assert receipt.workspace_id == "ws_demo"
    assert runtime.job_collect(receipt)["job_id"] == "job_1"


def test_execution_targets_support_one_local_and_multiple_ssh_targets(tmp_path: Path) -> None:
    config = tmp_path / "job.toml"
    config.write_text(
        '[execution]\nschema_version = 2\ndefault_platform = "local"\n\n[execution.platforms.local]\ndefault_scheduler = "main"\nschedulers.main.executor = "qrun"\ntransport = "local"\nstorage.work_root = "/fixture/qrun/jobs"\nsubmission = {resources = {cpus = 1, memory_mb = 512}}\n\n[execution.platforms.cluster_1w]\ndefault_scheduler = "main"\nschedulers.main.executor = "external"\ntransport = "ssh"\nschedulers.main.handler = ["/usr/bin/python3", "/opt/coragent/skills/core/batch-schedulers/scripts/batch.py", "pbs"]\nschedulers.main.cluster_name = "1w"\nssh_host = "login.1w"\nstorage.work_root = "/scratch/coragent"\n\n[execution.platforms.cluster_2w]\ndefault_scheduler = "main"\nschedulers.main.executor = "external"\ntransport = "ssh"\nschedulers.main.handler = ["/usr/bin/python3", "/opt/coragent/skills/core/batch-schedulers/scripts/batch.py", "pbs"]\nschedulers.main.cluster_name = "2w"\nssh_host = "login.2w"\nstorage.work_root = "/scratch/coragent"\n',
        encoding="utf-8",
    )
    platforms, default = platforms_from_config(config)
    assert default == "local/main"
    assert set(platforms) == {"local/main", "cluster_1w/main", "cluster_2w/main"}
    assert platforms["local/main"].scope == "local"
    assert platforms["cluster_1w/main"].scope == "remote"
    assert platforms["cluster_1w/main"].cluster_name == "1w"
    assert platforms["cluster_2w/main"].host == "login.2w"


def test_execution_target_identity_is_persisted_in_local_receipt(tmp_path: Path) -> None:
    config = tmp_path / "job.toml"
    config.write_text(
        '[execution]\nschema_version = 2\ndefault_platform = "local"\n\n[execution.platforms.local]\ndefault_scheduler = "main"\nschedulers.main.executor = "qrun"\ntransport = "local"\nstorage.work_root = "/fixture/qrun/jobs"\nsubmission = {resources = {cpus = 1, memory_mb = 512}}\n',
        encoding="utf-8",
    )
    platforms, default = platforms_from_config(config)
    runtime = JobManager(platforms, default=default)
    spec = JobSpec(
        metadata={"resources": {"cpus": 1, "memory_mb": 512}},
        job_id="job_1",
        command=(sys.executable, "-c", "print('target')"),
        cwd=tmp_path / "job",
    )
    spec.cwd.mkdir()
    receipt = runtime.job_start(spec)
    assert receipt.metadata["target_name"] == "local/main"
    assert receipt.metadata["scope"] == "local"
    assert receipt.metadata["driver"] == "external"
    assert receipt.metadata["target_config_digest"].startswith("sha256:")
    assert _wait(runtime, receipt).state is JobState.SUCCEEDED


def test_job_spec_separates_execution_target_from_process_environment(tmp_path: Path) -> None:
    spec = _spec(tmp_path, {
        'job_id': "job_1",
        "command": [sys.executable, "-c", "pass"],
        "execution_target": {"platform": "cluster_1w", "scheduler_entry": "main"},
        "environment": {"SCIENTIFIC_RUNTIME": "configured"},
    })
    assert spec.env == {"SCIENTIFIC_RUNTIME": "configured"}
