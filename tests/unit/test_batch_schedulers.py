import importlib.util
import json
from pathlib import Path
import sys

import pytest
from jsonschema import Draft202012Validator

from research_agent.jobs import ExternalJobPlatform, JobSpec, JobState, platforms_from_config
from research_agent.jobs.config_contract import job_config_schema, validate_job_config
from tests.unit.test_remote_job_execution import cluster

ROOT = Path(__file__).resolve().parents[2]
HANDLER = ROOT / 'skills/batch-schedulers/scripts/queue.py'


@pytest.fixture(params=['pbs', 'torque', 'slurm'])
def batch(request, tmp_path, monkeypatch):
    state = tmp_path / 'queue'
    state.mkdir()
    source = Path(__file__).with_name('batch_queue_fixture.py').read_text()
    variables = {'BATCH_FIXTURE_ROOT': str(state)}
    for name in ('qsub', 'qstat', 'qdel', 'sbatch', 'squeue', 'sacct', 'scancel'):
        executable = state / name
        executable.write_text('#!' + sys.executable + '\n' + source)
        executable.chmod(0o700)
        variables['CORAGENT_' + name.upper()] = str(executable)
    (state / 'defer').touch()
    shared = tmp_path / 'shared'
    shared.mkdir()
    config = {'driver': 'external', 'transport': 'local', 'work_root': str(shared),
              'handler': [sys.executable, str(HANDLER), request.param], 'handler_environment': variables}
    cwd = tmp_path / 'controller'
    cwd.mkdir()
    spec = JobSpec(job_id='job_1', command=('/bin/true',), cwd=cwd)
    return ExternalJobPlatform(config), state, spec


def update(directory, **fields):
    path = directory / 'tasks.json'
    tasks = json.loads(path.read_text())
    tasks[0].update(fields)
    path.write_text(json.dumps(tasks))


@pytest.mark.parametrize('native,expected', [('Q', JobState.QUEUED), ('R', JobState.RUNNING),
    ('E', JobState.RUNNING), ('H', JobState.HELD), ('unexpected', JobState.UNKNOWN)])
def test_native_states(batch, native, expected):
    platform, state, spec = batch
    receipt = platform.start(spec)
    update(state, state=native)
    assert platform.status(receipt).state == expected


@pytest.mark.parametrize('code,expected', [(0, JobState.SUCCEEDED), (125, JobState.FAILED)])
def test_accounting_recovers_missing_wrapper_exit(batch, code, expected):
    platform, state, spec = batch
    receipt = platform.start(spec)
    update(state, state='F', exit=code)
    assert platform.status(receipt).state == expected
    (state / 'query-failure').touch()
    assert ExternalJobPlatform(platform.config).status(receipt).state == expected


def test_cancel_acknowledgement_waits_across_restart(batch):
    platform, state, spec = batch
    receipt = platform.start(spec)
    update(state, state='R')
    assert platform.cancel(receipt).state == JobState.RUNNING
    restarted = ExternalJobPlatform(platform.config)
    (state / 'query-failure').touch()
    assert restarted.status(receipt).state == JobState.UNKNOWN
    (state / 'query-failure').unlink()
    update(state, state='F', exit=143)
    assert restarted.status(receipt).state == JobState.CANCELLED


def test_failed_cancel_does_not_claim_termination(batch):
    platform, state, spec = batch
    receipt = platform.start(spec)
    (state / 'cancel-failure').touch()
    assert platform.cancel(receipt).state == JobState.UNKNOWN
    assert not (spec.cwd / 'cancel.request').exists()


def test_lost_submit_response_queries_identity_without_resubmission(batch):
    platform, state, spec = batch
    (state / 'lose-submit-response').touch()
    with pytest.raises(RuntimeError):
        platform.start(spec)
    receipt = ExternalJobPlatform(platform.config).recover_receipt(spec.job_id, spec.cwd)
    assert platform.status(receipt).state == JobState.QUEUED
    assert len(json.loads((state / 'tasks.json').read_text())) == 1
    # Retrying the handler itself cannot enqueue a duplicate either.
    metadata = json.loads((spec.cwd / 'spec.json').read_text())['metadata']
    assert platform._invoke(metadata['external_request'])['scheduler_id'] == receipt.metadata['scheduler_id']
    assert len(json.loads((state / 'tasks.json').read_text())) == 1


def test_disappeared_record_is_unknown_even_after_cancel(batch):
    platform, state, spec = batch
    receipt = platform.start(spec)
    platform.cancel(receipt)
    (state / 'tasks.json').write_text('[]')
    assert platform.status(receipt).state == JobState.UNKNOWN


def test_recycled_scheduler_identity_is_rejected(batch):
    platform, state, spec = batch
    receipt = platform.start(spec)
    update(state, request_id='coragent-' + '0'*64, state='F', exit=0)
    assert platform.status(receipt).state == JobState.UNKNOWN


def module():
    spec = importlib.util.spec_from_file_location('batch_handler', HANDLER)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


@pytest.mark.parametrize('scheduler', ['pbs', 'torque', 'slurm'])
def test_resources_map_to_native_flags(scheduler):
    _, args = module().submit_arguments(scheduler, {'request_id': 'coragent-'+'a'*64,
        'job_id': 'job_1', 'cwd': '/shared/jobs/job_1', 'script': '/shared/jobs/job_1/run.sh', 'queue':'batch',
        'timeout_seconds':30, 'resources': {'cpus':2,'memory_mb':128,'walltime':'00:00:20'}})
    if scheduler == 'pbs':
        assert 'select=1:ncpus=2:mem=128mb' in args and 'walltime=00:00:20' in args
    elif scheduler == 'torque':
        assert 'nodes=1:ppn=2' in args and 'mem=128mb' in args and 'walltime=00:00:20' in args
    else:
        assert '--cpus-per-task=2' in args and '--mem=128' in args and '--time=1' in args
        assert '--partition=batch' in args and '--no-requeue' in args


@pytest.mark.parametrize('driver', ['pbs','torque','slurm','tri','process','third-party'])
def test_removed_plugin_configs_are_rejected(driver):
    value = {'execution':{'default_target':'cluster','targets':{'cluster':{
        'type':'remote','driver':driver,'ssh_host':'login','remote_root':'/scratch','cluster_name':'c'}}}}
    with pytest.raises(ValueError, match='removed'):
        validate_job_config(value)
    assert list(Draft202012Validator(job_config_schema()).iter_errors(value))


def test_old_distributions_are_never_loaded(tmp_path, monkeypatch):
    from importlib import metadata
    monkeypatch.setattr(metadata, 'entry_points', lambda **kw: pytest.fail('must not discover Python execution plugins'))
    path = tmp_path / 'job.toml'
    path.write_text('[execution]\ndefault_target="local"\n[execution.targets.local]\ntype="local"\ndriver="process"\n')
    assert platforms_from_config(path)[1] == 'local'


def test_unresolved_submission_intent_prevents_duplicate(batch):
    platform, state, spec = batch
    (state / 'lose-submit-response').touch()
    with pytest.raises(RuntimeError):
        platform.start(spec)
    (state / 'tasks.json').write_text('[]')
    request = json.loads((spec.cwd / 'spec.json').read_text())['metadata']['external_request']
    assert platform.recover_receipt(spec.job_id, spec.cwd) is None
    with pytest.raises(RuntimeError, match='unresolved'):
        platform._invoke(request)
    assert json.loads((state / 'tasks.json').read_text()) == []


def test_ambiguous_native_identity_remains_unresolved(batch):
    platform, state, spec = batch
    (state / 'lose-submit-response').touch()
    with pytest.raises(RuntimeError):
        platform.start(spec)
    path = state / 'tasks.json'
    task = json.loads(path.read_text())[0]
    path.write_text(json.dumps([task, {**task, 'id': '2' if platform.handler[-1] == 'slurm' else '2.fixture'}]))
    with pytest.raises(RuntimeError, match='multiple scheduler jobs'):
        platform.recover_receipt(spec.job_id, spec.cwd)


def test_slurm_signal_exit_is_failure(monkeypatch, tmp_path):
    handler = module()
    monkeypatch.setattr(handler, 'slurm_records', lambda *a, **kw: [{
        'id':'1', 'request_id':'r', 'state':'COMPLETED', 'exit':'0:9'}])
    result = handler.status('slurm', {'scheduler_id':'1','request_id':'r','cwd':str(tmp_path)}, {})
    assert result['state'] == 'failed' and result['exit_code'] == 137
    assert result['execution_finished']


def test_startup_reads_external_target_without_scheduler_plugins(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from research_agent.bootstrap import launcher
    path = tmp_path / 'job.toml'
    path.write_text('[execution]\ndefault_target="batch"\n[execution.targets.batch]\n'
                    'driver="external"\ntransport="ssh"\nssh_host="fixture"\ncluster_name="batch"\n'
                    'work_root="/shared/jobs"\nhandler=["/bin/true"]\n')
    path.chmod(0o600)
    monkeypatch.setenv('CORAGENT_JOB_CONFIG', str(path))
    launcher.configure_remote(SimpleNamespace(job_config_default=path))
    assert launcher.os.environ[launcher.REMOTE_ENVIRONMENT_ENV] == 'batch'
    assert launcher.os.environ['CORAGENT_REMOTE_DISPLAY_TARGET'] == 'fixture · Batch'
