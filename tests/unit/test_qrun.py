"""Deterministic Qrun lifecycle and failure-window tests; no remote systems."""

from tests.support.platforms import execution_config
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import shlex
import socket

import pytest
from jsonschema import Draft202012Validator

from research_agent.jobs import qrun
from research_agent.jobs.config_contract import (validate_job_config, job_config_schema,
    configuration_document, resolve_submission, binding_digest)
from research_agent.jobs.external import ExternalJobPlatform
from research_agent.jobs.models import JobSpec, JobOutput, JobState


class Runtime:
    def __init__(self, root):
        self.root = root
        self.units = {}
        self.starts = []
        self.stops = []
        self.fail_start = False
        self.unreachable = False

    def probe(self):
        if self.unreachable:
            raise RuntimeError('unreachable')

    def start(self, job):
        self.starts.append(job['id'])
        self.units[job['id']] = {'state': 'running'}
        if self.fail_start:
            raise RuntimeError('lost launch response')

    def inspect(self, job):
        self.probe()
        return self.units.get(job['id'], {'state': 'missing'})

    def stop(self, job):
        self.stops.append(job['id'])
        self.units[job['id']] = {'state': 'finished', 'result': 'signal', 'exit_code': 15}

    def cleanup(self, job):
        self.units.pop(job['id'], None)
        return True

    def finish(self, job, *, code=0, state=None):
        qrun.atomic_json(self.root / 'jobs' / job['id'] / 'result.json', {
            'state': state or ('failed' if code else 'succeeded'), 'exit_code': code})
        self.units[job['id']] = {'state': 'finished', 'result': 'success', 'exit_code': code}


@pytest.fixture
def pool(tmp_path):
    root, work = tmp_path / 'queue', tmp_path / 'work'
    qrun.initialize(root, 4, 4096, [str(work)])
    runtime = Runtime(root)
    queue = qrun.Queue(root, runtime=runtime)
    yield queue, runtime, work
    queue.close()


def request(work, name='first', *, cpus=2, memory=1024, script='exit 0', timeout=None):
    directory = work / name
    directory.mkdir(exist_ok=True)
    executable = directory / 'run.sh'
    executable.write_text(script + '\n')
    return {'schema_version': qrun.PROTOCOL, 'action': 'submit', 'request_id': name,
            'job_id': 'job_1', 'cwd': str(directory), 'script': str(executable),
            'resources': {'cpus': cpus, 'memory_mb': memory}, 'timeout_seconds': timeout}


def status(queue, req):
    return queue.handle({**req, 'action': 'status'})


def test_fifo_reserves_cpu_and_memory_and_releases_only_after_exit(pool):
    queue, runtime, work = pool
    requests = [request(work, 'first', memory=3072), request(work, 'second', cpus=3),
                request(work, 'third', cpus=1)]
    for req in requests:
        queue.handle(req)
    queue.tick()
    assert len(runtime.starts) == 1
    assert status(queue, requests[1])['state'] == status(queue, requests[2])['state'] == 'queued'
    runtime.finish(queue.rows()[0])
    queue.tick()
    assert len(runtime.starts) == 3
    assert status(queue, requests[0])['execution_finished'] is True


@pytest.mark.parametrize('resources', [dict(cpus=5, memory_mb=1), dict(cpus=1, memory_mb=4097),
    dict(cpus=True, memory_mb=1), dict(cpus=1), dict(cpus=1, memory_mb=1, gpus=1),
    dict(cpus=1, memory_mb=1, select='1:ncpus=1')])
def test_invalid_allocation_is_conclusively_rejected(pool, resources):
    queue, runtime, work = pool
    answer = qrun.response(queue, {**request(work), 'resources': resources})
    assert answer['error']['action_outcome'] == 'not_submitted'
    assert queue.rows() == [] and runtime.starts == []


def test_response_loss_and_daemon_restart_do_not_resubmit(pool):
    queue, runtime, work = pool
    req = request(work)
    first = queue.handle(req)
    runtime.fail_start = True
    queue.tick()
    with qrun.lock(queue.root / 'test.lock'):
        restored = qrun.Queue(queue.root, runtime=runtime)
        try:
            assert restored.handle(req) == first
            recovered = restored.handle({**req, 'action': 'recover'})
            assert recovered['found'] and recovered['scheduler_id'] == first['scheduler_id']
            restored.tick()
            assert status(restored, req)['state'] == 'running'
            assert first['scheduler_id'] == '1'
            assert runtime.starts == [queue.rows()[0]['id']]
        finally:
            restored.close()


def test_missing_or_unreachable_unit_retains_capacity(pool):
    queue, runtime, work = pool
    first, second = request(work, cpus=4), request(work, 'second')
    queue.handle(first)
    queue.handle(second)
    queue.tick()
    runtime.units.clear()
    queue.tick()
    assert status(queue, first)['state'] == 'unknown'
    assert status(queue, second)['state'] == 'queued'
    runtime.unreachable = True
    queue.tick()
    assert len(runtime.starts) == 1


def test_finished_wrapper_with_live_descendant_retains_allocation(pool):
    queue, runtime, work = pool
    first, second = request(work, cpus=4), request(work, 'second')
    queue.handle(first)
    queue.handle(second)
    queue.tick()
    job = queue.rows()[0]
    qrun.atomic_json(queue.directory(job) / 'result.json', {'state': 'succeeded', 'exit_code': 0})
    queue.tick()
    assert runtime.stops == [job['id']]
    assert status(queue, second)['state'] == 'queued'
    queue.tick()
    assert status(queue, first)['state'] == 'succeeded'
    assert len(runtime.starts) == 2


def test_queued_cancel_and_duplicate_submit_never_launch(pool):
    queue, runtime, work = pool
    req = request(work)
    receipt = queue.handle(req)
    assert queue.handle({**req, 'action': 'cancel'})['accepted']
    assert queue.handle(req) == receipt
    queue.tick()
    assert status(queue, req)['state'] == 'cancelled'
    assert runtime.starts == []


def test_cancel_is_durable_and_requires_termination(pool):
    queue, runtime, work = pool
    req = request(work)
    queue.handle(req)
    queue.tick()
    queue.handle({**req, 'action': 'cancel'})
    assert not status(queue, req)['execution_finished']
    queue.tick()
    assert not status(queue, req)['execution_finished']
    queue.tick()
    assert status(queue, req)['state'] == 'cancelled'


def test_late_launch_is_fenced_after_cancellation(pool):
    queue, runtime, work = pool
    marker = work / 'must-not-exist'
    req = request(work, script='touch ' + str(marker))
    queue.handle(req)
    queue.tick()
    runtime.units.clear()
    queue.handle({**req, 'action': 'cancel'})
    queue.tick()
    assert status(queue, req)['state'] == 'cancelled'
    job = queue.rows()[0]
    completed = subprocess.run([sys.executable, '-B', qrun.__file__, '--state-dir', str(queue.root), '_run', job['id']])
    assert completed.returncode == 1
    assert not marker.exists()


def test_completion_wins_a_cancel_race(pool):
    queue, runtime, work = pool
    req = request(work)
    queue.handle(req)
    queue.tick()
    runtime.finish(queue.rows()[0])
    queue.handle({**req, 'action': 'cancel'})
    queue.tick()
    assert status(queue, req)['state'] == 'succeeded'


def test_reboot_fails_without_rerunning_and_releases_resources(pool, monkeypatch):
    queue, runtime, work = pool
    req = request(work)
    queue.handle(req)
    queue.tick()
    monkeypatch.setattr(qrun, 'boot_id', lambda: 'another-boot')
    queue.tick()
    assert status(queue, req)['state'] == 'failed'
    assert len(runtime.starts) == 1


def test_changed_payload_or_foreign_execution_id_cannot_cancel(pool):
    queue, runtime, work = pool
    req = request(work)
    queue.handle(req)
    for changed in ({'resources': {'cpus': 1, 'memory_mb': 1}}, {'scheduler_id': 'another'}):
        answer = qrun.response(queue, {**req, **changed, 'action': 'cancel'})
        assert answer['error']['action_outcome'] == 'unknown'
    assert queue.rows()[0]['cancel'] == 0


def test_simultaneous_duplicate_submissions_have_one_identity(pool):
    queue, runtime, work = pool
    req = request(work)
    # Daemon serializes requests; SQLite UNIQUE also protects accidental duplicate writers.
    def submit():
        other = qrun.Queue(queue.root, runtime=runtime)
        try:
            try:
                return other.handle(req)['scheduler_id']
            except qrun.sqlite3.IntegrityError:
                return other.handle(req)['scheduler_id']
        finally:
            other.close()
    with ThreadPoolExecutor(max_workers=4) as workers:
        identities = list(workers.map(lambda _: submit(), range(8)))
    assert len(set(identities)) == len(queue.rows()) == 1


@pytest.mark.parametrize('code,expected', [(0, 'succeeded'), (3, 'failed'), (124, 'failed')])
def test_real_wrapper_exit_is_saved_independently_of_unit(pool, code, expected):
    queue, runtime, work = pool
    req = request(work, script='exit ' + str(code))
    queue.handle(req)
    queue.tick()
    job = queue.rows()[0]
    subprocess.run([sys.executable, '-B', qrun.__file__, '--state-dir', str(queue.root), '_run', job['id']], check=False)
    runtime.units[job['id']] = {'state': 'finished', 'result': 'success'}
    queue.tick()
    assert status(queue, req)['state'] == expected
    assert status(queue, req)['exit_code'] == code


def test_real_timeout_terminates_job(pool):
    queue, runtime, work = pool
    req = request(work, script='sleep 60', timeout=0.1)
    queue.handle(req)
    queue.tick()
    job = queue.rows()[0]
    subprocess.run([sys.executable, '-B', qrun.__file__, '--state-dir', str(queue.root), '_run', job['id']], check=False, timeout=5)
    runtime.units[job['id']] = {'state': 'finished', 'result': 'success'}
    queue.tick()
    assert status(queue, req)['state'] == 'timed_out'


@pytest.mark.parametrize('transport', ['local', 'ssh'])
def test_unified_configuration_normalizes_qrun(transport):
    target = {'executor': 'qrun', 'transport': transport, 'work_root': '/srv/jobs',
              'submission': {'resources': {'cpus': 2, 'memory_mb': 1024}}}
    if transport == 'ssh':
        target['ssh_host'] = 'agent.com30'
    document = {'execution': execution_config('compute', {'compute': target})}
    Draft202012Validator(job_config_schema()).validate(document)
    settings = validate_job_config(document)
    selected = settings['targets']['compute/main']
    assert selected['executor'] == 'qrun' and selected['scheduler_entry'] == 'main'
    assert selected['handler'] == ['qrun', 'handler']
    restored = validate_job_config(configuration_document(settings))
    assert binding_digest(restored['targets']) == binding_digest(settings['targets'])


@pytest.mark.parametrize('field', [{'queue': 'batch'}, {'resources': {'gpus': 1}}, {'resources': {'select': '1:ncpus=1'}}])
def test_qrun_resource_capabilities_match_schema(field):
    document = {'execution': execution_config('compute', {'compute': {
        'executor': 'qrun', 'transport': 'local', 'work_root': '/srv/jobs', 'submission': field}})}
    assert not Draft202012Validator(job_config_schema()).is_valid(document)
    with pytest.raises(ValueError, match='Qrun'):
        validate_job_config(document)


@pytest.mark.parametrize('fields', [
    {'driver': 'process', 'type': 'local'}, {'driver': 'systemd', 'type': 'local'},
    {'driver': 'local', 'type': 'local'}, {'driver': 'external', 'transport': 'local'},
    {'executor': 'process', 'transport': 'local'}, {'executor': 'systemd', 'transport': 'local'},
    {'executor': 'qrun', 'transport': 'local', 'supervisor': 'systemd'},
    {'executor': 'qrun', 'transport': 'local', 'scheduler': 'qrun'},
])
def test_removed_execution_configuration_is_rejected(fields):
    document = {'execution': execution_config('local', {'local': {**fields, 'work_root': '/srv/jobs'}})}
    assert not Draft202012Validator(job_config_schema()).is_valid(document)
    with pytest.raises(ValueError):
        validate_job_config(document)


def test_multiple_local_qrun_targets():
    target = {'executor': 'qrun', 'transport': 'local', 'work_root': '/srv/jobs'}
    document = {'execution': execution_config('first', {'first': target, 'second': target})}
    assert len(validate_job_config(document)['targets']) == 2


@pytest.mark.parametrize('executor', ['pbs', 'torque', 'slurm', 'tri', 'external'])
@pytest.mark.parametrize('transport', ['local', 'ssh'])
def test_executor_selection_uses_one_public_configuration(executor, transport):
    target = {'transport': transport, 'work_root': '/srv/jobs', 'handler': ['fixture', executor]}
    if transport == 'ssh':
        target['ssh_host'] = 'fixture'
    def document(fields):
        return {'execution': execution_config('target', {'target': fields})}
    new = document({**target, 'executor': executor})
    Draft202012Validator(job_config_schema()).validate(new)
    settings = validate_job_config(new)
    assert settings['targets']['target/main']['executor'] == executor
    assert validate_job_config(configuration_document(settings))['targets'] == settings['targets']


def test_example_and_installer_publication_keep_qrun_selection(tmp_path):
    import tomllib
    from scripts import _job_install
    example = Path(__file__).resolve().parents[2] / 'config/job.qrun.example.toml'
    settings = validate_job_config(tomllib.loads(example.read_text()))
    raw = _job_install.toml_bytes(configuration_document(settings))
    document = tomllib.loads(raw.decode())
    Draft202012Validator(job_config_schema()).validate(document)
    assert document['execution']['platforms']['local']['schedulers']['qrun']['executor'] == 'qrun'
    assert document['execution']['platforms']['com30']['transport'] == 'ssh'
    assert validate_job_config(document)['targets'] == settings['targets']


def test_target_installation_is_standalone_and_does_not_start_without_flag(tmp_path, monkeypatch):
    monkeypatch.setenv('XDG_CONFIG_HOME', str(tmp_path / 'config'))
    root, work = tmp_path / 'queue', tmp_path / 'jobs'
    installed = qrun.install(root, 4, 4096, [str(work)], start=False)
    assert Path(installed['program']).read_bytes() == Path(qrun.__file__).read_bytes()
    assert 'Restart=on-failure' in Path(installed['unit_path']).read_text()
    result = subprocess.run([sys.executable, '-B', installed['program'], '--help'], capture_output=True, text=True)
    assert result.returncode == 0 and 'handler' in result.stdout
    assert not (root / 'queue.sqlite3').exists()


def test_external_job_staging_collection_and_restart_use_qrun(pool, tmp_path):
    queue, runtime, work = pool
    config = {'executor': 'qrun', 'transport': 'local',
              'work_root': str(work), 'handler': ['qrun', 'handler']}
    platform = ExternalJobPlatform(config)
    platform._invoke = queue.handle
    cwd = tmp_path / 'controller'
    cwd.mkdir()
    (cwd / 'input.txt').write_text('real staged input')
    spec = JobSpec(command=('/bin/sh', '-c', 'cat input.txt > output.txt'), cwd=cwd, job_id='job_1',
        outputs=(JobOutput('output.txt', required=True),), metadata={'resources': {'cpus': 1, 'memory_mb': 256}})
    probe = platform.probe(spec)
    assert probe['queue']['capacity'] == {'cpus': 4, 'memory_mb': 4096}
    schema = json.loads((Path(__file__).resolve().parents[2] / 'contracts/commands/results.json').read_text())
    Draft202012Validator(schema['definitions']['JobExecutionProbe']).validate(probe)
    receipt = platform.start(spec)
    assert platform.status(receipt).state == JobState.QUEUED
    queue.tick()
    job = queue.rows()[0]
    subprocess.run([sys.executable, '-B', qrun.__file__, '--state-dir', str(queue.root), '_run', job['id']], check=True)
    runtime.units[job['id']] = {'state': 'finished', 'result': 'success'}
    queue.tick()
    restored = ExternalJobPlatform(config)
    restored._invoke = queue.handle
    recovered = restored.recover_receipt('job_1', cwd)
    assert recovered.metadata['scheduler_id'] == receipt.metadata['scheduler_id']
    collected = restored.collect(recovered)
    assert collected['output_validation']['complete']
    assert (cwd / 'output.txt').read_text() == 'real staged input'


def test_real_daemon_socket_handler_and_restart_preserve_accepted_jobs(tmp_path, monkeypatch):
    monkeypatch.setenv('XDG_RUNTIME_DIR', os.environ['CORAGENT_TEST_SOCKET_ROOT'])
    root, work = tmp_path / 'queue', tmp_path / 'work'
    qrun.initialize(root, 1, 512, [str(work)])
    program = ('import sys; sys.path[:0]=' + repr(sys.path) + '; '
               'from pathlib import Path; from research_agent.jobs import qrun; '
               'from tests.unit.test_qrun import Runtime; qrun.Systemd=Runtime; '
               'qrun.serve(Path(' + repr(str(root)) + '))')
    def start():
        process = subprocess.Popen([sys.executable, '-B', '-c', program])
        deadline = time.monotonic() + 5
        while not qrun.socket_path(root).exists() and time.monotonic() < deadline:
            if process.poll() is not None:
                raise AssertionError('queue daemon stopped before readiness')
            time.sleep(.02)
        assert qrun.socket_path(root).exists()
        return process
    process = start()
    try:
        req = request(work, cpus=1, memory=256)
        # Close the connection before reading the submission reply.
        with socket.socket(socket.AF_UNIX) as connection:
            connection.connect(str(qrun.socket_path(root)))
            connection.sendall(json.dumps(req).encode() + b'\n')
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            recovered = qrun.client(root, {**req, 'action': 'recover'})
            if recovered['found']:
                break
            time.sleep(.02)
        assert recovered['found']
        identifier = recovered['scheduler_id']
        process.terminate()
        process.wait(timeout=5)
        process = start()
        # Execute the actual standalone JSON handler, as the SSH transport does.
        handler = subprocess.run([sys.executable, '-B', qrun.__file__, '--state-dir', str(root), 'handler'],
            input=json.dumps(req), text=True, capture_output=True, check=True)
        assert json.loads(handler.stdout)['scheduler_id'] == identifier
        assert qrun.client(root, {**req, 'action': 'status'})['state'] == 'unknown'
        assert qrun.client(root, {**req, 'action': 'cancel'})['accepted']
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if qrun.client(root, {**req, 'action': 'status'})['state'] == 'cancelled':
                break
            time.sleep(.02)
        assert qrun.client(root, {**req, 'action': 'status'})['state'] == 'cancelled'
    finally:
        process.terminate()
        process.wait(timeout=5)
        assert not qrun.socket_path(root).exists()


def test_ssh_qrun_stages_inputs_and_uses_same_handler_contract(pool, tmp_path, monkeypatch):
    from research_agent.jobs import transport as transport_module
    queue, runtime, work = pool
    calls = []
    original = transport_module._capture
    def capture(argv, *, timeout, **kwargs):
        calls.append(argv[0])
        if argv[0] == 'ssh':
            return original(['/bin/sh', '-c', shlex.split(argv[-1])[2]], timeout=timeout, **kwargs)
        local = list(argv)
        index = local.index('-e')
        del local[index:index+2]
        return original([value.removeprefix('fixture:') for value in local], timeout=timeout, **kwargs)
    original_init = transport_module.SSHTransport.__init__
    monkeypatch.setattr(transport_module.SSHTransport, '__init__',
        lambda self, config: original_init(self, config, capture=capture))
    platform = ExternalJobPlatform({'executor': 'qrun', 'transport': 'ssh',
        'ssh_host': 'fixture', 'work_root': str(work), 'handler': ['qrun', 'handler']})
    platform._invoke = queue.handle
    cwd = tmp_path / 'controller'
    cwd.mkdir()
    (cwd / 'input').write_text('transport fixture')
    spec = JobSpec(command=('/bin/sh', '-c', 'cat input > output'), cwd=cwd, job_id='job_1',
        outputs=(JobOutput('output', required=True),), metadata={'resources': {'cpus': 1, 'memory_mb': 128}})
    receipt = platform.start(spec)
    queue.tick()
    job = queue.rows()[0]
    subprocess.run([sys.executable, '-B', qrun.__file__, '--state-dir', str(queue.root), '_run', job['id']], check=True)
    runtime.units[job['id']] = {'state': 'finished', 'result': 'success'}
    queue.tick()
    assert platform.collect(receipt)['output_validation']['complete']
    assert (cwd / 'output').read_text() == 'transport fixture'
    assert {'ssh', 'rsync'} <= set(calls)
