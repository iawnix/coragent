"""Shared execution uses ordinary queue lifecycle without copying Job files."""

from tests.support.platforms import execution_config
from dataclasses import replace
import json
from pathlib import Path
import shlex
import subprocess

import pytest
from jsonschema import Draft202012Validator

from research_agent.jobs import JobOutput, JobState
from research_agent.jobs.config_contract import job_config_schema, validate_job_config
from research_agent.jobs.external import ExternalJobPlatform
from research_agent.jobs.transport import LocalTransport
from tests.unit.test_external_jobs import queue, spec, finish, tasks, update_task
from tests.unit.test_batch_schedulers import batch


def shared_platform(config, monkeypatch, transport='local'):
    config = {**config, 'file_mode':'shared', 'transport':transport}
    if transport == 'ssh':
        config['ssh_host'] = 'fixture'
    platform = ExternalJobPlatform(config)
    if transport == 'ssh':
        local = LocalTransport(config)
        def run(argv, *, timeout):
            assert argv[0] == 'ssh'
            return local.run(shlex.split(argv[-1])[2], check=False)
        monkeypatch.setattr(platform.transport, 'capture', run)
    def no_transfer(*args, **kwargs):
        pytest.fail('shared execution must not transfer files')
    monkeypatch.setattr(platform.transport, 'copy', no_transfer)
    monkeypatch.setattr(platform.transport, 'pull', no_transfer)
    return platform


@pytest.mark.parametrize('transport', ['local', 'ssh'])
def test_shared_lifecycle_restarts_and_collects_in_place(queue, monkeypatch, transport):
    config, state = queue
    request = spec(Path(config['work_root']), outputs=(JobOutput('result.txt', required=True),))
    source = request.cwd / 'input.txt'
    source.write_text('shared input')
    request = replace(request, inputs=(source,))
    receipt = shared_platform(config, monkeypatch, transport).start(request)
    assert tasks(state)[0]['cwd'] == str(request.cwd.resolve())
    assert receipt.metadata['file_mode'] == 'shared'
    assert not list(Path(config['work_root']).glob('job_1-*'))
    platform = shared_platform(config, monkeypatch, transport)
    assert platform.status(receipt).state == JobState.QUEUED
    with pytest.raises(RuntimeError, match='not complete'):
        platform.collect(receipt)
    finish(state)
    inode = (request.cwd / 'result.txt').stat().st_ino
    before = (request.cwd / 'receipt.json').read_bytes()
    for _ in range(2):
        result = platform.collect(receipt)
        assert result['output_validation']['complete']
        assert result['status']['state'] == JobState.SUCCEEDED
        assert (request.cwd / 'result.txt').stat().st_ino == inode
        assert (request.cwd / 'receipt.json').read_bytes() == before
    assert len(tasks(state)) == 1
    assert not list(request.cwd.glob('.coragent-storage-*'))


def test_shared_recovery_and_pending_cancellation(queue, monkeypatch):
    config, state = queue
    request = spec(Path(config['work_root']), command=('/bin/true',))
    (state / 'lose-submit-response').touch()
    with pytest.raises(RuntimeError):
        shared_platform(config, monkeypatch).start(request)
    platform = shared_platform(config, monkeypatch)
    receipt = platform.recover_receipt('job_1', request.cwd)
    assert len(tasks(state)) == 1
    update_task(state, state='run', started_at='earlier', lease_id='lease')
    assert platform.cancel(receipt).state == JobState.RUNNING
    update_task(state, finished_at='now', lease_id=None, exit_code=-15)
    assert shared_platform(config, monkeypatch).collect(receipt)['status']['state'] == JobState.CANCELLED
    assert request.cwd.is_dir()


def test_storage_mode_change_cannot_redirect_old_jobs(queue, monkeypatch):
    config, _ = queue
    request = spec(Path(config['work_root']), command=('/bin/true',))
    receipt = shared_platform(config, monkeypatch).start(request)
    changed = ExternalJobPlatform(config)
    assert changed.status(receipt).state == JobState.UNKNOWN
    with pytest.raises(ValueError, match='file_mode changed'):
        changed.recover_receipt('job_1', request.cwd)
    with pytest.raises(ValueError, match='file_mode changed'):
        changed.collect(receipt)


def test_shared_storage_probe_rejects_same_path_without_round_trip(queue, monkeypatch):
    config, state = queue
    request = spec(Path(config['work_root']), command=('/bin/true',))
    platform = shared_platform(config, monkeypatch)
    # A successful command alone cannot prove that its write reached this host.
    monkeypatch.setattr(platform.transport, 'run', lambda *args, **kw: subprocess.CompletedProcess([], 0, '', ''))
    receipt = platform.start(request)
    assert platform.status(receipt).state == JobState.FAILED
    assert 'round-trip failed' in receipt.metadata['submission_error']['message']
    assert receipt.metadata['submission_error']['action_outcome'] == 'not_submitted'
    assert not (state / 'tasks.json').exists()
    assert (request.cwd / 'spec.json').exists()  # Durable non-submission evidence.
    assert not list(request.cwd.glob('.coragent-storage-*'))


@pytest.mark.parametrize('case', ['cwd', 'external', 'traversal'])
def test_shared_mode_rejects_cwd_outside_root_and_external_inputs(queue, tmp_path, monkeypatch, case):
    config, state = queue
    platform = shared_platform(config, monkeypatch)
    if case == 'cwd':
        request = spec(tmp_path, command=('/bin/true',))
        expected = 'below work_root'
    else:
        source = tmp_path / 'external' if case == 'external' else Path(config['work_root']) / 'sibling'
        source.write_text('outside job')
        if case == 'traversal':
            source = Path(config['work_root']) / 'controller' / '..' / 'sibling'
        request = spec(Path(config['work_root']), command=('/bin/true',), inputs=(source,))
        expected = 'escapes Job directory'
    receipt = platform.start(request)
    assert platform.status(receipt).state == JobState.FAILED
    assert expected in receipt.metadata['submission_error']['message']
    assert receipt.metadata['submission_error']['action_outcome'] == 'not_submitted'
    assert not (state / 'tasks.json').exists()


def test_compute_node_guard_rejects_wrong_directory_before_calculation(queue, monkeypatch):
    config, state = queue
    request = spec(Path(config['work_root']), command=('/bin/sh','-c','touch calculation-started'))
    receipt = shared_platform(config, monkeypatch).start(request)
    (request.cwd / '.coragent/shared-token').write_text('wrong-filesystem')
    finish(state)
    assert not (request.cwd / 'calculation-started').exists()
    assert tasks(state)[0]['exit_code'] == 125
    assert shared_platform(config, monkeypatch).status(receipt).state == JobState.FAILED


def test_shared_success_requires_compute_evidence_visible_to_controller(queue, monkeypatch):
    config, state = queue
    request = spec(Path(config['work_root']), command=('/bin/true',))
    platform = shared_platform(config, monkeypatch)
    receipt = platform.start(request)
    update_task(state, state='done', exit_code=0, finished_at='now', lease_id=None)
    assert platform.status(receipt).state == JobState.UNKNOWN
    assert not (request.cwd / 'status.json').exists()
    finish(state)
    assert platform.status(receipt).state == JobState.SUCCEEDED


@pytest.mark.parametrize('output', ['receipt.json', 'result', 'directory'])
def test_shared_collection_rejects_control_files_and_symlinks(queue, tmp_path, monkeypatch, output):
    config, state = queue
    request = spec(Path(config['work_root']), command=('/bin/true',),
                   outputs=(JobOutput(output, recursive=output == 'directory'),))
    platform = shared_platform(config, monkeypatch)
    receipt = platform.start(request)
    external = tmp_path / 'private'; external.write_text('keep')
    if output == 'result':
        (request.cwd / output).symlink_to(external)
    if output == 'directory':
        (request.cwd / output).mkdir()
        (request.cwd / output / 'link').symlink_to(external)
    finish(state)
    with pytest.raises(ValueError, match='control files|escapes job cwd|symlink'):
        platform.collect(receipt)
    assert external.read_text() == 'keep'


def test_shared_collection_reports_missing_and_empty_outputs(queue, monkeypatch):
    config, state = queue
    request = spec(Path(config['work_root']), command=('/bin/sh','-c','touch empty'),
        outputs=(JobOutput('empty', required=True, min_bytes=1), JobOutput('missing', required=True)))
    platform = shared_platform(config, monkeypatch)
    receipt = platform.start(request)
    finish(state)
    result = platform.collect(receipt)
    assert result['status']['state'] == JobState.SUCCEEDED
    assert {e['error'] for e in result['output_validation']['errors']} == {'too_small','missing'}


def test_shared_mount_alias_stdin_and_node_local_scratch(queue, tmp_path, monkeypatch):
    config, state = queue
    request = spec(Path(config['work_root']), command=('/bin/sh','-c',
        'cat > result.txt; printf %s "$TMPDIR" > scratch.txt; printf %s "$LOCATION" > location.txt'),
        env={'LOCATION':'{scratch}'}, outputs=(JobOutput('result.txt', required=True),),
        metadata={'execution_binding':{'binding':{'scratch_root':str(tmp_path / 'node scratch')}}})
    source = request.cwd / 'input'; source.write_text('stdin in shared storage')
    request = replace(request, inputs=(source,), stdin=source)
    alias = tmp_path / 'DATA'; alias.symlink_to(config['work_root'], target_is_directory=True)
    platform = shared_platform({**config, 'work_root':str(alias)}, monkeypatch)
    receipt = platform.start(request)
    finish(state)
    assert platform.collect(receipt)['output_validation']['complete']
    assert (request.cwd / 'result.txt').read_text() == 'stdin in shared storage'
    scratch = Path((request.cwd / 'scratch.txt').read_text())
    assert scratch.is_relative_to(tmp_path / 'node scratch') and scratch.is_dir()
    assert (request.cwd / 'location.txt').read_text() == str(scratch)


@pytest.mark.parametrize('command,timeout,expected', [
    (('/bin/sh','-c','exit 7'), None, JobState.FAILED),
    (('/bin/sleep','5'), .05, JobState.TIMED_OUT),
])
def test_shared_failure_and_timeout_are_collectable(queue, monkeypatch, command, timeout, expected):
    config, state = queue
    platform = shared_platform(config, monkeypatch)
    request = spec(Path(config['work_root']), command=command, timeout_seconds=timeout)
    receipt = platform.start(request)
    finish(state)
    assert platform.collect(receipt)['status']['state'] == expected


def test_batch_schedulers_execute_shared_jobs_without_copy(batch, monkeypatch):
    original, state, request = batch
    cwd = Path(original.config['work_root']) / 'job'; cwd.mkdir()
    request = replace(request, cwd=cwd, command=('/bin/sh','-c','echo result > result.txt'),
                      outputs=(JobOutput('result.txt', required=True),))
    (state / 'defer').unlink()
    platform = shared_platform(original.config, monkeypatch)
    receipt = platform.start(request)
    assert platform.collect(receipt)['output_validation']['complete']
    assert json.loads((state / 'tasks.json').read_text())[0]['cwd'] == str(cwd)


@pytest.mark.parametrize('mode', ['staged', 'shared', 'auto', False])
def test_shared_config_schema_and_runtime_agree(queue, mode):
    config, _ = queue
    document = {'execution':execution_config('compute', {'compute':{**config,'file_mode':mode}})}
    errors = list(Draft202012Validator(job_config_schema()).iter_errors(document))
    if mode in ('staged','shared'):
        assert not errors
        assert validate_job_config(document)['targets']['compute/main']['file_mode'] == mode
    else:
        assert errors
        with pytest.raises(ValueError, match='file_mode'):
            validate_job_config(document)


@pytest.mark.parametrize('interrupted', [False, True])
def test_shared_acceptance_retains_failed_or_interrupted_workspace(queue, tmp_path, monkeypatch, interrupted):
    from scripts import _job_acceptance as acceptance
    from scripts._job_install import toml_bytes
    config, _ = queue
    target = {**config, 'file_mode':'shared', 'bindings':{'shell':{'command':'/bin/true'}}}
    path = tmp_path / 'job.toml'
    path.write_bytes(toml_bytes({'execution':execution_config('compute', {'compute':target})}))
    monkeypatch.setattr(acceptance, 'check_environments', lambda _: {'compute/main':{}})
    monkeypatch.setattr(acceptance, 'profiles', lambda _: {'check':{'root':str(tmp_path),
        'checks':[{'backend':'shell','script':'example.py'}]}})
    monkeypatch.setattr(acceptance, 'resource', lambda *args: Path('/bin/true'))
    monkeypatch.setattr(acceptance, 'prepare_script', lambda *args, **kwargs: {})
    def pending(root, request, timeout):
        (root / 'pending-job').write_text('retain for recovery')
        if interrupted:
            raise KeyboardInterrupt()
        raise RuntimeError('acceptance_cancellation_pending:job_1')
    monkeypatch.setattr(acceptance, 'run_job', pending)
    if interrupted:
        with pytest.raises(KeyboardInterrupt):
            acceptance.accept(path, tmp_path, tmp_path / 'acceptance', ['compute/main'], 1)
    else:
        result = acceptance.accept(path, tmp_path, tmp_path / 'acceptance', ['compute/main'], 1)
        assert result['targets']['compute/main']['status'] == 'failed'
        assert Path(result['targets']['compute/main']['retained_workspace']).is_dir()
    retained = list(Path(config['work_root']).glob('.coragent-acceptance-*/pending-job'))
    assert len(retained) == 1
    assert retained[0].read_text() == 'retain for recovery'
