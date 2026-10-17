from pathlib import Path
import subprocess
import sys

import pytest

from research_agent.jobs import JobReceipt, JobSpec, JobState, RemoteSSHPlatform


PLUGIN_SRC = Path(__file__).resolve().parents[2] / "plugins" / "tspi-execution-tri" / "src"
if str(PLUGIN_SRC) not in sys.path:
    sys.path.insert(0, str(PLUGIN_SRC))

from tspi_execution_tri.scheduler import TriRemoteScheduler


def scheduler(config=None):
    return TriRemoteScheduler(config or {})


def test_tri_submission_maps_native_resources_and_timeout(tmp_path):
    spec = JobSpec(
        command=("/bin/true",), cwd=tmp_path, job_id="job_17", timeout_seconds=30,
        metadata={"resources": {"cpus": 2, "memory_mb": 128, "gpus": 1, "walltime": "00:00:20"}},
    )
    assert scheduler().submit_arguments(spec) == [
        "tri_sub", "--name", "job_17", "--request-id", "job_17",
        "--cpu", "2", "--mem", "128M", "--gpu", "1", "--timeout", "20",
    ]


def test_tri_custom_commands_override_defaults(tmp_path):
    adapter = scheduler({"commands": {"submit": "/opt/tri/sub", "status": "/opt/tri/stat", "cancel": "/opt/tri/del"}})
    spec = JobSpec(command=("true",), cwd=tmp_path, job_id="job_1")
    assert adapter.submit_arguments(spec)[0] == "/opt/tri/sub"
    assert adapter.probe_commands() == ("/opt/tri/sub", "/opt/tri/stat", "/opt/tri/del")


def test_tri_rejects_queue_compatibility_settings(tmp_path):
    spec = JobSpec(command=("true",), cwd=tmp_path, job_id="job_1", metadata={"queue": "batch"})
    with pytest.raises(ValueError, match="does not support scheduler queues"):
        scheduler().submit_arguments(spec)


@pytest.mark.parametrize(
    ("state", "expected"),
    [("wait", JobState.QUEUED), ("run", JobState.RUNNING), ("blocked", JobState.HELD),
     ("done", JobState.SUCCEEDED), ("fail", JobState.FAILED), ("cancel", JobState.CANCELLED)],
)
def test_tri_state_mapping(state, expected):
    assert scheduler().map_state(state) == expected


def test_tri_details_reads_json_task_record(tmp_path, monkeypatch):
    adapter = scheduler()
    platform = RemoteSSHPlatform({"ssh_host": "fixture", "remote_root": "/scratch"}, scheduler=adapter)
    payload = '{"id": 9, "state": "done", "exit_code": 0, "node": "n1", "error": null}'
    monkeypatch.setattr(platform, "_run_ssh", lambda *args, **kwargs: subprocess.CompletedProcess([], 0, payload, ""))
    state, details = adapter.details(platform, JobReceipt("job_1", "tri", "now", ("true",), str(tmp_path), metadata={"scheduler_id": "9"}))
    assert state == "done"
    assert details["exit_status"] == 0
    assert details["node"] == "n1"
    assert adapter.completed_with_exit(state, details)


def test_tri_cancel_uses_native_command(monkeypatch):
    adapter = scheduler()
    calls = []
    platform = type("Platform", (), {"_run_ssh": lambda self, command, **kwargs: calls.append(command) or subprocess.CompletedProcess([], 0, "", "")})()
    adapter.cancel(platform, "9")
    assert calls == ["tri_del --json 9"]
