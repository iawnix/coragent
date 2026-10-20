import json
import os
from pathlib import Path
import shlex
import subprocess
import sys

import pytest
from jsonschema import Draft202012Validator

from research_agent.jobs import JobOutput, JobSpec, JobState, JobRuntime, platforms_from_config
from research_agent.jobs.config_contract import job_config_schema, validate_job_config, resolve_submission, validate_catalog_bindings
from research_agent.jobs.external import ExternalJobPlatform


ROOT = Path(__file__).resolve().parents[2]
HANDLER = ROOT / "skills/tri-operations/scripts/queue.py"


@pytest.fixture
def queue(tmp_path):
    state = tmp_path / "queue"
    state.mkdir()
    executable = state / "cli"
    executable.write_text("#!" + sys.executable + "\n" + (Path(__file__).with_name("external_queue_fixture.py")).read_text())
    executable.chmod(0o700)
    for name in ("tri_sub", "tri_stat", "tri_del"):
        (state / name).symlink_to(executable)
    shared = tmp_path / "shared files"
    shared.mkdir()
    config = {"driver": "external", "transport": "local", "work_root": str(shared),
              "cluster_name": "compute", "handler": [sys.executable, str(HANDLER)],
              "handler_environment": {"QUEUE_FIXTURE_ROOT": str(state),
                  **{"CORAGENT_" + name.upper(): str(state / name) for name in ("tri_sub", "tri_stat", "tri_del")}}}
    return config, state


def spec(tmp_path, command=None, **kw):
    cwd = tmp_path / "controller"
    cwd.mkdir(exist_ok=True)
    return JobSpec(command=command or ("/bin/sh", "-c", "cat input.txt > result.txt"), cwd=cwd,
                   job_id="job_1", **kw)


def tasks(state):
    return json.loads((state / "tasks.json").read_text())


def update_task(queue_dir, **fields):
    records = tasks(queue_dir)
    records[0].update(fields)
    (queue_dir / "tasks.json").write_text(json.dumps(records))


def finish(state, env=None):
    task = tasks(state)[0]
    result = subprocess.run(["/bin/sh", task["script"]], env={**os.environ, **(env or {})})
    timeout_path = Path(task["cwd"]) / "status.state"
    native_state = "timed_out" if timeout_path.exists() else "done" if result.returncode == 0 else "fail"
    update_task(state, state=native_state, exit_code=result.returncode, finished_at="now", lease_id=None)


def test_queue_lifecycle_uses_shared_files_without_ssh(queue, tmp_path):
    config, state = queue
    request = spec(tmp_path, outputs=(JobOutput("result.txt", required=True),),
                   metadata={"resources": {"cpus": 2, "memory_mb": 128, "gpus": 1}})
    (request.cwd / "input.txt").write_text("computed from declared input")
    receipt = ExternalJobPlatform(config).start(request)
    platform = ExternalJobPlatform(config)  # Controller restart, no Popen handle.
    assert platform.status(receipt).state == JobState.QUEUED
    with pytest.raises(RuntimeError, match="not complete"):
        platform.collect(receipt)
    finish(state)
    result = platform.collect(receipt)
    assert result["status"]["state"] == JobState.SUCCEEDED
    assert result["output_validation"]["complete"]
    assert (request.cwd / "result.txt").read_text() == "computed from declared input"
    assert len(tasks(state)) == 1
    assert "--gpu" in tasks(state)[0]["arguments"]
    (state / "invalid-status").touch()
    assert platform.status(receipt).state == JobState.SUCCEEDED  # Durable terminal receipt.


def test_recover_lost_submission_response_without_resubmitting(queue, tmp_path):
    config, state = queue
    request = spec(tmp_path, command=("/bin/true",))
    (state / "lose-submit-response").touch()
    with pytest.raises(RuntimeError):
        ExternalJobPlatform(config).start(request)
    platform = ExternalJobPlatform(config)
    receipt = platform.recover_receipt("job_1", request.cwd)
    assert receipt.metadata["scheduler_id"] == "1"
    assert platform.status(receipt).state == JobState.QUEUED
    assert len(tasks(state)) == 1


def test_identity_is_scoped_across_workspaces(queue, tmp_path):
    config, state = queue
    for name in ("workspace-a", "workspace-b"):
        directory = tmp_path / name
        directory.mkdir()
        ExternalJobPlatform(config).start(spec(directory, command=("/bin/true",)))
    assert len(tasks(state)) == 2
    assert tasks(state)[0]["external_id"] != tasks(state)[1]["external_id"]


def test_running_cancellation_waits_for_execution_to_finish(queue, tmp_path):
    config, state = queue
    platform = ExternalJobPlatform(config)
    receipt = platform.start(spec(tmp_path, command=("/bin/true",)))
    update_task(state, state="run", started_at="earlier", lease_id="lease-1", attempt=1)
    assert platform.cancel(receipt).state == JobState.RUNNING
    assert not (Path(receipt.cwd) / "status.json").exists()
    update_task(state, finished_at="now", lease_id=None, exit_code=-15)
    assert ExternalJobPlatform(config).status(receipt).state == JobState.CANCELLED


def test_cancelled_lease_expiry_does_not_prove_process_exit(queue, tmp_path):
    config, state = queue
    platform = ExternalJobPlatform(config)
    receipt = platform.start(spec(tmp_path, command=("/bin/true",)))
    update_task(state, state="cancel", started_at="earlier", finished_at="now", lease_id=None, exit_code=None)
    assert platform.status(receipt).state == JobState.UNKNOWN


def test_confirmed_cancellation_without_exit_code_is_terminal(queue, tmp_path):
    config, state = queue
    platform = ExternalJobPlatform(config)
    receipt = platform.start(spec(tmp_path, command=("/bin/true",)))
    update_task(state, state="cancel", started_at="earlier", lease_id="lease-1",
                cancel_confirmed=False)
    assert platform.status(receipt).state == JobState.RUNNING
    update_task(state, finished_at="now", lease_id=None, exit_code=None,
                cancel_confirmed=True, completion_reason="node_completion")
    assert platform.status(receipt).state == JobState.CANCELLED
    assert ExternalJobPlatform(config).collect(receipt)["status"]["state"] == JobState.CANCELLED


@pytest.mark.parametrize("exit_code", [None, -15])
def test_explicit_unconfirmed_cancel_remains_unknown(queue, tmp_path, exit_code):
    config, state = queue
    platform = ExternalJobPlatform(config)
    receipt = platform.start(spec(tmp_path, command=("/bin/true",)))
    update_task(state, state="cancel", started_at="earlier", finished_at="now",
                lease_id=None, exit_code=exit_code, cancel_confirmed=False,
                completion_reason="lease_expired")
    assert platform.status(receipt).state == JobState.UNKNOWN
    assert not (Path(receipt.cwd) / "status.json").exists()
    with pytest.raises(RuntimeError, match="not complete"):
        platform.collect(receipt)


def test_queued_cancel_and_config_change(queue, tmp_path):
    config, state = queue
    platform = ExternalJobPlatform(config)
    platform.target_config_digest = "original"
    receipt = platform.start(spec(tmp_path, command=("/bin/true",)))
    changed = ExternalJobPlatform(config)
    changed.target_config_digest = "different"
    assert changed.cancel(receipt).state == JobState.UNKNOWN
    assert tasks(state)[0]["state"] == "wait"
    assert platform.cancel(receipt).state == JobState.CANCELLED
    with pytest.raises(ValueError, match="configuration changed"):
        changed.collect(receipt)


def test_collection_preserves_controller_receipts(queue, tmp_path):
    config, state = queue
    platform = ExternalJobPlatform(config)
    receipt = platform.start(spec(tmp_path, command=("/bin/true",), outputs=(JobOutput("receipt.json"),)))
    original = (Path(receipt.cwd) / "receipt.json").read_bytes()
    finish(state)
    with pytest.raises(ValueError, match="control files"):
        platform.collect(receipt)
    assert (Path(receipt.cwd) / "receipt.json").read_bytes() == original


def test_shared_root_can_be_a_mount_alias(queue, tmp_path):
    config, state = queue
    alias = tmp_path / "shared-alias"
    alias.symlink_to(config["work_root"], target_is_directory=True)
    platform = ExternalJobPlatform({**config, "work_root": str(alias)})
    receipt = platform.start(spec(tmp_path, command=("/bin/echo", "hello")))
    finish(state)
    assert Path(platform.collect(receipt)["stdout"]).read_text() == "hello\n"


@pytest.mark.parametrize("command,timeout,expected", [
    (("/bin/sh", "-c", "exit 7"), None, JobState.FAILED),
    (("/bin/sleep", "5"), .05, JobState.TIMED_OUT),
])
def test_failure_and_timeout(queue, tmp_path, command, timeout, expected):
    config, state = queue
    platform = ExternalJobPlatform(config)
    receipt = platform.start(spec(tmp_path, command=command, timeout_seconds=timeout))
    finish(state)
    assert platform.status(receipt).state == expected


def test_bad_status_and_lost_node_remain_unknown(queue, tmp_path):
    config, state = queue
    platform = ExternalJobPlatform(config)
    receipt = platform.start(spec(tmp_path, command=("/bin/true",)))
    (state / "invalid-status").touch()
    assert platform.status(receipt).state == JobState.UNKNOWN
    (state / "invalid-status").unlink()
    update_task(state, state="lost", finished_at="now")
    assert platform.status(receipt).state == JobState.UNKNOWN
    assert not (Path(receipt.cwd) / "status.json").exists()


def test_execution_preserves_assigned_gpu_but_scrubs_provider_env(queue, tmp_path):
    config, state = queue
    command = (sys.executable, "-c", "import os; print(os.getenv('CUDA_VISIBLE_DEVICES')); print(os.getenv('FIXTURE_SECRET'))")
    platform = ExternalJobPlatform(config)
    receipt = platform.start(spec(tmp_path, command=command))
    finish(state, {"CUDA_VISIBLE_DEVICES": "2", "FIXTURE_SECRET": "private"})
    result = platform.collect(receipt)
    assert Path(result["stdout"]).read_text() == "2\nNone\n"


def test_external_config_supports_multiple_local_clusters_and_gpu(queue, tmp_path):
    config, state = queue
    value = {"execution": {"default_target": "tri", "targets": {
        "tri": config, "second": config, "direct": {"type": "local", "driver": "process"}}}}
    Draft202012Validator(job_config_schema()).validate(value)
    normalized = validate_job_config(value)
    assert validate_catalog_bindings(value, []) == {"tri": {}, "second": {}, "direct": {}}
    assert validate_catalog_bindings(normalized, []) == {"tri": {}, "second": {}, "direct": {}}
    assert resolve_submission(normalized, "tri", requested={"resources": {"gpus": 1}})["resources"]["gpus"] == 1
    path = tmp_path / "job.toml"
    path.write_text('[execution]\ndefault_target="tri"\n[execution.targets.tri]\n'
                    'driver="external"\ntransport="local"\ncluster_name="compute"\n'
                    f'work_root={json.dumps(config["work_root"])}\nhandler={json.dumps(config["handler"])}\n'
                    '[execution.targets.tri.handler_environment]\n' +
                    ''.join(f'{key}={json.dumps(value)}\n' for key, value in config['handler_environment'].items()))
    platforms, default = platforms_from_config(path)
    assert isinstance(platforms[default], ExternalJobPlatform)
    runtime = JobRuntime(platforms, default)
    receipt = runtime.job_start(spec(tmp_path, command=("/bin/echo", "configured target")))
    assert receipt.metadata["cluster_name"] == "compute"
    assert receipt.metadata["target_config_digest"].startswith("sha256:")
    platforms, default = platforms_from_config(path)
    restored = JobRuntime(platforms, default)
    receipt = restored.receipt_from_disk(str(Path(receipt.cwd) / "receipt.json"))
    assert restored.job_reconcile(receipt).state == JobState.QUEUED
    finish(state)
    assert Path(restored.job_collect(receipt)["stdout"]).read_text() == "configured target\n"


@pytest.mark.parametrize("change", [
    {"transport": "http"}, {"transport": "ssh"}, {"handler": "script.py"},
    {"work_root": "relative"}, {"type": "remote"}, {"command_timeout_seconds": 0},
])
def test_invalid_external_targets_fail_schema_and_runtime(queue, change):
    config, _ = queue
    value = {"execution": {"default_target": "tri", "targets": {"tri": {**config, **change}}}}
    assert list(Draft202012Validator(job_config_schema()).iter_errors(value))
    with pytest.raises(ValueError):
        validate_job_config(value)


def test_handler_runs_over_ssh_with_same_lifecycle(queue, tmp_path, monkeypatch):
    config, state = queue
    config = {**config, "transport": "ssh", "ssh_host": "fixture"}
    platform = ExternalJobPlatform(config)
    from research_agent.jobs.transport import LocalTransport
    local = LocalTransport(config)
    calls = []
    def run(argv, *, timeout):
        calls.append(argv)
        assert argv[0] == "ssh"
        return local.run(shlex.split(argv[-1])[2], check=False)
    monkeypatch.setattr(platform.transport, "capture", run)
    monkeypatch.setattr(platform.transport, "copy", local.copy)
    monkeypatch.setattr(platform.transport, "pull", local.pull)
    receipt = platform.start(spec(tmp_path, command=("/bin/true",)))
    finish(state)
    assert platform.collect(receipt)["status"]["state"] == JobState.SUCCEEDED
    assert calls


@pytest.mark.parametrize("lose_response", [False, True])
@pytest.mark.parametrize("file_mode", ["staged", "shared"])
def test_application_jobs_reconcile_and_collect_external_tasks(queue, tmp_path, monkeypatch, lose_response, file_mode):
    from research_agent.application.execution import dispatch, _RUNTIMES
    from tests.unit.test_job_recovery import workspace
    from scripts._job_install import toml_bytes

    config, state = queue
    config = {**config, "file_mode": file_mode}
    path = tmp_path / "external.toml"
    path.write_bytes(toml_bytes({"execution": {"default_target": "compute", "targets": {"compute": config}}}))
    monkeypatch.setenv("CORAGENT_JOB_CONFIG", str(path))
    root = (Path(config["work_root"]) if file_mode == "shared" else tmp_path) / "research"
    workspace(root)
    if lose_response:
        (state / "lose-submit-response").touch()
    request = {"root": str(root), "request_id": "external-check",
               "command": ["/bin/sh", "-c", "echo result > result.txt"],
               "outputs": [{"path": "result.txt", "required": True}]}
    if lose_response:
        with pytest.raises(RuntimeError, match="submission_ambiguous"):
            dispatch("start", request)
    else:
        assert dispatch("start", request)["job_id"] == "job_1"
    _RUNTIMES.clear()
    selector = {"root": str(root), "job_id": "job_1"}
    assert dispatch("reconcile", selector)["state"] == "queued"
    finish(state)
    result = dispatch("collect", selector)
    assert result["status"]["state"] == "succeeded"
    assert result["output_validation"]["complete"]
    assert len(tasks(state)) == 1
