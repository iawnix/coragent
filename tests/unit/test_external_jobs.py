
from tests.support.platforms import execution_config
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import time

import pytest
from jsonschema import Draft202012Validator

from research_agent.jobs import JobOutput, JobSpec, JobState, JobManager, platforms_from_config
from research_agent.jobs.config_contract import job_config_schema, validate_job_config, resolve_submission, validate_catalog_bindings
from research_agent.jobs.external import ExternalJobPlatform


ROOT = Path(__file__).resolve().parents[2]
HANDLER = ROOT / "skills/core/batch-schedulers/scripts/tri.py"


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
    config = {'executor': 'tri', 'transport': 'local', 'work_root': str(shared), 'cluster_name': 'compute', 'handler': [sys.executable, str(HANDLER)], 'handler_environment': {'QUEUE_FIXTURE_ROOT': str(state), **{'CORAGENT_' + name.upper(): str(state / name) for name in ('tri_sub', 'tri_stat', 'tri_del')}}}
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


@pytest.mark.parametrize('fields', [{'id': 99}, {'external_id': 'another-workflow'}])
def test_status_and_cancel_refuse_replaced_task_identity(queue, tmp_path, fields):
    config, state = queue
    platform = ExternalJobPlatform(config)
    receipt = platform.start(spec(tmp_path, command=('/bin/true',)))
    (state / 'response-overrides.json').write_text(json.dumps({'tri_stat': fields}))
    status = platform.status(receipt)
    assert status.state == JobState.UNKNOWN
    assert status.diagnostics['handler_error']['code'] == 'task_identity_mismatch'
    assert platform.cancel(receipt).state == JobState.UNKNOWN
    assert not (state / 'cancel-called').exists()
    assert tasks(state)[0]['state'] == 'wait'


def test_submission_and_recovery_verify_external_identity(queue, tmp_path):
    from research_agent.jobs.external import ExternalHandlerError
    config, state = queue
    platform = ExternalJobPlatform(config)
    request = spec(tmp_path, command=('/bin/true',))
    (state / 'response-overrides.json').write_text(json.dumps({
        name: {'external_id': 'wrong-workflow'} for name in ('tri_sub', 'tri_stat')}))
    with pytest.raises(ExternalHandlerError) as error:
        platform.start(request)
    assert error.value.details['action_outcome'] == 'unknown'
    with pytest.raises(ExternalHandlerError, match='task_identity_mismatch'):
        platform.recover_receipt(request.job_id, request.cwd)
    assert len(tasks(state)) == 1
    assert not (request.cwd / 'receipt.json').exists()


@pytest.mark.parametrize('code,retryable', [('request_id_reused', False), ('external_id_conflict', False), ('request_failed', True)])
def test_native_errors_preserve_ambiguity_and_retryability(queue, tmp_path, code, retryable):
    from research_agent.jobs.external import ExternalHandlerError
    config, state = queue
    (state / 'submit-error.json').write_text(json.dumps({'code': code, 'message': 'fixture error', 'retryable': retryable}))
    with pytest.raises(ExternalHandlerError) as error:
        ExternalJobPlatform(config).start(spec(tmp_path, command=('/bin/true',)))
    assert error.value.details == {'code': code, 'message': 'tri_sub: fixture error',
                                  'retryable': retryable, 'action_outcome': 'unknown'}


def application_queue(queue, tmp_path, monkeypatch, file_mode='staged'):
    from tests.unit.test_job_recovery import workspace
    from coragent_packaging.installer._job_install import toml_bytes
    config, state = queue
    config = {**config, 'file_mode': file_mode, 'submission': {'queue_wait_seconds': 60}}
    path = tmp_path / 'external.toml'
    path.write_bytes(toml_bytes({'execution': execution_config('compute', {'compute': config})}))
    monkeypatch.setenv('CORAGENT_JOB_CONFIG', str(path))
    root = (Path(config['work_root']) if file_mode == 'shared' else tmp_path) / 'research'
    workspace(root)
    request = {'root': str(root), 'request_id': 'external-check', 'session_id': 'fixture', 'command': ['/bin/true']}
    return root, request, state


@pytest.mark.parametrize('file_mode', ['staged', 'shared'])
def test_rejected_submission_is_durable_failed_job_without_scheduler_retries(queue, tmp_path, monkeypatch, file_mode):
    from research_agent.application.execution import dispatch, _JOB_MANAGERS
    from research_agent.application.job_manager import command
    root, request, state = application_queue(queue, tmp_path, monkeypatch, file_mode)
    (state / 'submit-error.json').write_text(json.dumps({'code': 'invalid_request', 'message': 'invalid resources', 'retryable': False}))
    first = dispatch('start', request)
    assert first['state'] == 'failed'
    assert first['action_outcome'] == 'not_submitted'
    assert first['metadata']['scheduler_id'] is None
    schema = json.loads((ROOT / 'contracts/commands/results.json').read_text())['definitions']['JobReceipt']
    Draft202012Validator(schema).validate(first)
    _JOB_MANAGERS.clear()
    assert dispatch('start', request) == first
    selector = {'root': str(root), 'job_id': first['job_id']}
    for action in ('status', 'reconcile', 'cancel'):
        assert dispatch(action, selector)['state'] == 'failed'
    assert not command(root, 'tick', {})['registration_errors']
    deliveries = command(root, 'pending', {})['deliveries']
    assert len(deliveries) == 1
    assert command(root, 'event', {'event_id': deliveries[0]['event_id']})['state'] == 'failed'
    assert dispatch('collect', selector)['status']['state'] == 'failed'
    assert not (state / 'tasks.json').exists()
    assert not (state / 'cancel-called').exists()


def test_rejection_recovers_after_receipt_write_failure(queue, tmp_path, monkeypatch):
    config, state = queue
    (state / 'submit-error.json').write_text(json.dumps({'code': 'invalid_request', 'message': 'invalid resources', 'retryable': False}))
    platform = ExternalJobPlatform(config)
    request = spec(tmp_path, command=('/bin/true',))
    monkeypatch.setattr(platform, '_receipt', lambda *args: (_ for _ in ()).throw(OSError('fixture disk error')))
    with pytest.raises(OSError):
        platform.start(request)
    restored = ExternalJobPlatform(config)
    receipt = restored.recover_receipt(request.job_id, request.cwd)
    assert restored.status(receipt).state == JobState.FAILED
    assert not (state / 'tasks.json').exists()


def test_real_handler_queue_age_wakes_monitor_once_and_reports_allocation(queue, tmp_path, monkeypatch):
    from research_agent.application.execution import dispatch
    from research_agent.application.job_manager import command
    root, request, state = application_queue(queue, tmp_path, monkeypatch)
    request['submission'] = {'resources': {'cpus': 12, 'memory_mb': 16384, 'gpus': 1}}
    dispatch('start', request)
    command(root, 'tick', {})
    assert command(root, 'pending', {})['deliveries'] == []
    update_task(state, created_at=str(time.time() - 120))
    for _ in range(3):
        assert not command(root, 'tick', {})['registration_errors']
    deliveries = command(root, 'pending', {})['deliveries']
    assert len(deliveries) == 1
    event = command(root, 'event', {'event_id': deliveries[0]['event_id']})
    assert event['status']['reason'] == 'queue_wait_exceeded'
    diagnostics = event['status']['diagnostics']
    assert diagnostics['wait_seconds'] >= 120
    assert diagnostics['requested_resources'] == {'cpus': 12, 'memory_bytes': 16384 * 1024**2, 'gpus': 1}
    assert diagnostics['assigned_cpus'] is None
    update_task(state, state='run', node='fed1', assigned_cpus='0-11', assigned_gpus='2')
    diagnostics = dispatch('status', {'root': str(root), 'job_id': 'job_1'})['diagnostics']
    assert diagnostics['node'] == 'fed1'
    assert diagnostics['assigned_cpus'] == '0-11'
    assert diagnostics['assigned_gpus'] == '2'
    assert diagnostics['wait_seconds'] is None


@pytest.mark.parametrize('error,exit_code,kind', [
    ('memory limit exceeded (MemoryMax)', None, 'memory_limit'),
    ('resource enforcement verification failed; see task stderr', 78, 'resource_enforcement'),
    ('task exited with status 7', 7, None),
])
def test_tri_resource_failures_are_structured_without_changing_job_state(queue, tmp_path, error, exit_code, kind):
    config, state = queue
    platform = ExternalJobPlatform(config)
    receipt = platform.start(spec(tmp_path, command=('/bin/true',),
                                  metadata={'resources': {'cpus': 2, 'memory_mb': 128}}))
    update_task(state, state='fail', finished_at='now', lease_id=None,
                exit_code=exit_code, error=error)
    status = platform.status(receipt)
    assert status.state == JobState.FAILED
    assert status.diagnostics['resource_failure'] == kind
    assert status.diagnostics['effective_memory_limit_bytes'] == 128 * 1024**2
    assert status.diagnostics['memory_swap_limit_bytes'] == 0


def test_tri_fixed_node_is_reported_in_resource_diagnostics(queue, tmp_path):
    config, state = queue
    config = {**config, 'handler_environment': {**config['handler_environment'], 'CORAGENT_TRI_NODE': 'fed1'}}
    platform = ExternalJobPlatform(config)
    receipt = platform.start(spec(tmp_path, command=('/bin/true',)))
    update_task(state, state='run', node='fed2', started_at='now', lease_id='lease-1')
    status = platform.status(receipt)
    assert status.state == JobState.RUNNING
    assert status.diagnostics['requested_node'] == 'fed1'
    assert status.diagnostics['node_match'] is False


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
    value = {"execution": execution_config("tri", {
        "tri": config, "second": config, "direct": {'executor': 'qrun', 'transport': 'local', 'work_root': '/fixture/qrun/jobs'}})}
    Draft202012Validator(job_config_schema()).validate(value)
    normalized = validate_job_config(value)
    assert validate_catalog_bindings(value, []) == {"tri/main": {}, "second/main": {}, "direct/main": {}}
    assert validate_catalog_bindings(normalized, []) == {"tri/main": {}, "second/main": {}, "direct/main": {}}
    assert resolve_submission(normalized, 'tri/main', requested={"resources": {"gpus": 1}})["resources"]["gpus"] == 1
    path = tmp_path / "job.toml"
    path.write_text(f"""[execution]\nschema_version = 2\ndefault_platform="tri"\n[execution.platforms.tri]\ndefault_scheduler = "main"\nschedulers.main.executor="external"\ntransport="local"\nschedulers.main.cluster_name="compute"\nstorage.work_root={json.dumps(config['work_root'])}\nschedulers.main.handler={json.dumps(config['handler'])}\n[execution.platforms.tri.schedulers.main.handler_environment]\n""" +
                    ''.join(f'{key}={json.dumps(value)}\n' for key, value in config['handler_environment'].items()))
    platforms, default = platforms_from_config(path)
    assert isinstance(platforms[default], ExternalJobPlatform)
    runtime = JobManager(platforms, default)
    receipt = runtime.job_start(spec(tmp_path, command=("/bin/echo", "configured target")))
    assert receipt.metadata["cluster_name"] == "compute"
    assert receipt.metadata["target_config_digest"].startswith("sha256:")
    platforms, default = platforms_from_config(path)
    restored = JobManager(platforms, default)
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
    value = {"execution": execution_config("tri", {"tri": {**config, **change}})}
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
    from research_agent.application.execution import dispatch, _JOB_MANAGERS
    from tests.unit.test_job_recovery import workspace
    from coragent_packaging.installer._job_install import toml_bytes

    config, state = queue
    config = {**config, "file_mode": file_mode}
    path = tmp_path / "external.toml"
    path.write_bytes(toml_bytes({"execution": execution_config("compute", {"compute": config})}))
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
    _JOB_MANAGERS.clear()
    selector = {"root": str(root), "job_id": "job_1"}
    assert dispatch("reconcile", selector)["state"] == "queued"
    finish(state)
    result = dispatch("collect", selector)
    assert result["status"]["state"] == "succeeded"
    assert result["output_validation"]["complete"]
    assert len(tasks(state)) == 1


@pytest.mark.parametrize('failure', [None, 'wrong_node', 'backend_failure'])
def test_node_acceptance_checks_each_selected_node_and_keeps_unverified_backends(queue, tmp_path, monkeypatch, failure):
    from coragent_packaging.installer import _job_acceptance as acceptance
    from coragent_packaging.installer.verify_tri_nodes import verify
    from coragent_packaging.installer._job_install import toml_bytes
    from research_agent.jobs.config_contract import load_job_config, resolve_binding
    config, state = queue
    (state / 'auto-run').touch()
    if failure == 'wrong_node':
        (state / 'response-overrides.json').write_text(json.dumps({'tri_stat': {'node': 'unexpected'}}))
    script = tmp_path / 'check.py'
    script.write_text("import json\nfrom pathlib import Path\nPath('result.json').write_text(json.dumps({'ok': True}))\n")
    if failure == 'backend_failure':
        script.write_text('raise SystemExit(7)\n')
    monkeypatch.setattr(acceptance, 'profiles', lambda _: {'fixture': {'root': str(tmp_path), 'checks': [
        {'backend': 'fixture', 'script': 'check.py', 'collect': ['result.json'],
         'result': {'path': 'result.json', 'fields': {'ok': True}}}]}})
    settings = load_job_config(os.environ['CORAGENT_JOB_CONFIG'])
    python = resolve_binding(settings, 'local/main', 'validation', runtime='python')['python']
    config = {**config, 'file_mode': 'shared', 'bindings': {
        'fixture': {'python': python}, 'uncovered': {'python': python}}}
    path = tmp_path / 'source.toml'
    original = toml_bytes({'schema_version': 1,
        'execution': execution_config('compute', {'compute': config})})
    path.write_bytes(original)
    original_env = os.environ.get('CORAGENT_JOB_CONFIG')
    report = verify(path, ROOT, tmp_path / 'acceptance', 'compute/main', ['fed1', 'fed2'], 10)
    assert report['unselected_nodes'] == 'not_verified'
    assert set(report['nodes']) == {'fed1', 'fed2'}
    assert path.read_bytes() == original
    assert os.environ.get('CORAGENT_JOB_CONFIG') == original_env
    for node, row in report['nodes'].items():
        assert row['expected_node'] == node
        assert row['jobs'][0]['actual_node'] == ('unexpected' if failure == 'wrong_node' else node)
        assert row['jobs'][0]['backend'] == 'fixture'
        if failure:
            assert row['status'] == 'failed'
            assert row['tested_backends'] == []
            assert row['untested_backends'] == ['fixture', 'uncovered']
            assert ('acceptance_node_mismatch' if failure == 'wrong_node' else 'acceptance_job_failed') in row['error']
            assert Path(row['retained_config']).is_file()
            assert Path(row['retained_workspace']).is_dir()
        else:
            assert row['status'] == 'execution_verified'
            assert row['tested_backends'] == ['fixture']
            assert row['untested_backends'] == ['uncovered']
            assert not (tmp_path / 'acceptance' / node / 'config.toml').exists()
    assert len(tasks(state)) == 2
    for task, node in zip(tasks(state), ('fed1', 'fed2')):
        assert task['arguments'][task['arguments'].index('--node') + 1] == node
    if not failure:
        assert not list(Path(config['work_root']).glob('.coragent-acceptance-*'))


def test_ambiguous_submission_exposes_native_error_without_authorizing_retry(queue, tmp_path, monkeypatch):
    from research_agent.application.execution import dispatch
    root, request, state = application_queue(queue, tmp_path, monkeypatch)
    (state / 'submit-error.json').write_text(json.dumps({'code': 'request_failed', 'message': 'connection interrupted', 'retryable': True}))
    with pytest.raises(RuntimeError, match='submission_ambiguous') as error:
        dispatch('start', request)
    assert error.value.details['handler_error']['retryable'] is True
    assert error.value.details['action_outcome'] == 'unknown'
    assert error.value.details['retryable_without_change'] is False
    assert dispatch('start', request)['state'] == 'unknown'


def test_caller_cannot_forge_submission_rejection(tmp_path):
    with pytest.raises(ValueError, match='job_submission_error_runtime_only'):
        spec(tmp_path, metadata={'submission_error': {'message': 'forged rejection'}})


@pytest.mark.parametrize('file_mode', ['staged', 'shared'])
@pytest.mark.parametrize('stage', ['probe', 'stage_inputs', '_wrapper'])
def test_pre_submission_failures_are_durable_without_contacting_queue_again(queue, tmp_path, monkeypatch, file_mode, stage):
    from research_agent.application.execution import dispatch, _JOB_MANAGERS
    from research_agent.application.job_manager import command
    root, request, state = application_queue(queue, tmp_path, monkeypatch, file_mode)
    request['outputs'] = [{'path': 'result.txt', 'required': True}]
    def fail(*args, **kwargs):
        raise OSError('fixture preparation failure')
    monkeypatch.setattr(ExternalJobPlatform, stage, fail)
    receipt = dispatch('start', request)
    assert receipt['state'] == 'failed'
    assert receipt['action_outcome'] == 'not_submitted'
    assert receipt['metadata']['submission_error']['phase'] == 'preparation'
    assert not (state / 'tasks.json').exists()
    monkeypatch.setattr(ExternalJobPlatform, '_invoke', lambda *args: pytest.fail('must not contact queue'))
    monkeypatch.setattr(ExternalJobPlatform, '_pull_path', lambda *args: pytest.fail('must not contact storage'))
    _JOB_MANAGERS.clear()
    assert dispatch('start', request) == receipt
    # Receipt recovery uses local preparation evidence even if the connection
    # is still unavailable, and must not mistake another Job for this one.
    cwd = Path(receipt['cwd'])
    (cwd / 'receipt.json').unlink()
    selector = {'root': str(root), 'job_id': receipt['job_id']}
    assert dispatch('reconcile', selector)['state'] == 'failed'
    assert dispatch('cancel', selector)['state'] == 'failed'
    result = dispatch('collect', selector)
    assert result['status']['state'] == 'failed'
    assert result['outputs'] == [{'path': 'result.txt', 'required': True, 'exists': False}]
    assert not result['output_validation']['complete']
    assert not command(root, 'tick', {})['registration_errors']
    assert len(command(root, 'pending', {})['deliveries']) == 1


def test_existing_submission_evidence_is_never_classified_as_preflight_rejection(queue, tmp_path):
    config, state = queue
    platform = ExternalJobPlatform(config)
    request = spec(tmp_path, command=('/bin/true',))
    receipt = platform.start(request)
    with pytest.raises(ValueError, match='reconcile instead'):
        platform.start(request)
    assert platform.status(receipt).state == JobState.QUEUED
    assert len(tasks(state)) == 1
