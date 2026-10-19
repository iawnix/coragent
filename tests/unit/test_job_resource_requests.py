"""Per-job allocation travels from preparation to the scheduler and program."""
import hashlib
import json
import os
from pathlib import Path
import tomllib
import subprocess
import sys

import pytest

from research_agent.application.api import execute
from research_agent.application.executors import prepare, prepare_script
from research_agent.application.execution_environment import check_binding, check_configuration
from research_agent.jobs.config_contract import load_job_config
from scripts.install_wizard import _job_config_bytes
from tests.unit.test_external_jobs import queue, tasks, finish
from tests.unit.test_job_recovery import workspace


def configured(tmp_path, *, external=None):
    path = Path(os.environ['CORAGENT_JOB_CONFIG'])
    source = tomllib.loads(path.read_text())['environments']['local']
    python = source['backends']['validation']['python']
    program = tmp_path / 'g16'
    program.write_text('#!/bin/sh\ncat > observed.gjf\nprintf "%s" "$OMP_NUM_THREADS" > observed.threads\n'
                       "printf '%s\\n' ' #p M062X/6-31G** SP SCF=Tight Int=UltraFine' ' ----------------' "
                       "' SCF Done: E(RM062X) = -76.0 A.U.' ' Normal termination of Gaussian'\n")
    program.chmod(0o700)
    target = {**(external or {'driver': 'process', 'type': 'local'}),
              'python': python, 'submission': {'resources': {'cpus': 4, 'memory_mb': 4096}},
              'bindings': {key: {'command': str(program)} for key in ('gaussian', 'xtb', 'crest', 'path_gaussian', 'path_xtb')},
              }
    target['bindings'].update(pyscf={}, validation={})
    path.write_bytes(_job_config_bytes({'execution': {'default_target': 'local', 'targets': {'local': target}}}))
    return path


def geometry(tmp_path):
    path = tmp_path / 'water.xyz'
    path.write_text('3\nwater\nO 0.0 0.0 0.0\nH 0.0 0.0 1.0\nH 0.0 1.0 0.0\n')
    return path


def gaussian(config, tmp_path, **kw):
    return prepare(config, 'local', 'chemical.gaussian', '1', {'geometry': geometry(tmp_path)}, ['--task', 'sp'], **kw)


def test_explicit_allocation_reaches_tri_and_gaussian_without_changing_defaults(tmp_path, queue):
    target, state = queue
    config = configured(tmp_path, external=target)
    root = tmp_path / 'work'
    workspace(root)
    prepared = gaussian(config, root, submission={'resources': {'cpus': 12, 'memory_mb': 16384, 'walltime': '00:10:00'}})
    path = root / 'request.json'
    path.write_text(json.dumps(prepared))
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    receipt = execute('job.start', root, {'request_file': str(path), 'request_sha256': digest})
    try:
        arguments = tasks(state)[0]['arguments']
        assert arguments[arguments.index('--cpu') + 1] == '12'
        assert arguments[arguments.index('--mem') + 1] == '16384M'
        assert arguments[arguments.index('--timeout') + 1] == '600'
        finish(state)
        result = execute('job.collect', root, {'job_id': receipt['job_id']})
        assert result['status']['state'] == 'succeeded'
        output = Path(receipt['cwd']) / 'results/sp'
        assert (output / 'observed.threads').read_text() == '12'
        assert '%nprocshared=12' in (output / 'observed.gjf').read_text().lower()
        assert '%mem=14745MB' in (output / 'observed.gjf').read_text()
        spec = json.loads((Path(receipt['cwd']) / 'spec.json').read_text())
        assert spec['metadata']['resources']['cpus'] == 12
        assert load_job_config(config)['environments']['local']['submission']['resources']['cpus'] == 4
        # Neither changing an existing file nor attaching an override can reuse its digest.
        prepared['metadata']['resources']['cpus'] = 16
        path.write_text(json.dumps(prepared))
        with pytest.raises(ValueError, match='prepared_request_changed'):
            execute('job.start', root, {'request_file': str(path), 'request_sha256': digest})
        with pytest.raises(ValueError, match='prepared_override_forbidden'):
            execute('job.start', root, {'request_file': str(path), 'request_sha256': digest,
                                       'submission': {'resources': {'cpus': 16}}})
    finally:
        execute('job.cancel', root, {'job_id': receipt['job_id']})


def test_default_backend_and_partial_job_resources_share_one_resolver(tmp_path, mock_environment_probe):
    config = configured(tmp_path)
    with config.open('a') as stream:
        stream.write('\n[execution.targets.local.bindings.gaussian.submission.resources]\ncpus=6\n')
    normal = gaussian(config, tmp_path)
    override = gaussian(config, tmp_path, submission={'resources': {'cpus': 12}})
    assert normal['metadata']['resources'] == {'cpus': 6, 'memory_mb': 4096}
    assert override['metadata']['resources'] == {'cpus': 12, 'memory_mb': 4096}
    assert normal['work_id'] != override['work_id']
    assert normal['request_id'] != override['request_id']
    check_binding(override, probe=False)
    # Default changes still invalidate prepared configuration evidence.
    config.write_text(config.read_text().replace('cpus=6', 'cpus=8'))
    with pytest.raises(ValueError, match='execution_binding_changed'):
        check_configuration(override)


def test_script_resources_are_pinned_without_claiming_internal_parallelism(tmp_path):
    config = configured(tmp_path)
    script = tmp_path / 'analysis.py'
    script.write_text('print("analysis")\n')
    prepared = prepare_script(config, 'local', 'validation', script, submission={'resources': {'cpus': 12}})
    assert prepared['metadata']['resources'] == {'cpus': 12, 'memory_mb': 4096}
    assert prepared['metadata']['program_resources']['status'] == 'unverified'
    check_binding(prepared, probe=False)
    prepared = json.loads(json.dumps(prepared))  # Match a reviewed request read back from disk.
    prepared['metadata']['resources']['cpus'] = 16
    with pytest.raises(ValueError, match='execution_binding_submission_mismatch'):
        check_configuration(prepared)


def test_target_activation_cannot_restore_stale_thread_defaults(tmp_path):
    from tests.unit.test_execution_environment import stage, run_guard
    config = configured(tmp_path)
    conda = Path(load_job_config(config)['environments']['local']['python']['conda_executable'])
    conda.write_text(conda.read_text().replace('else shift 5;',
        'else export OMP_NUM_THREADS=2 CORAGENT_JOB_CPUS=2 CORAGENT_JOB_MEMORY_MB=256; shift 5;'))
    script = tmp_path / 'analysis.py'
    variables = ('OMP_NUM_THREADS', 'MKL_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'CORAGENT_JOB_CPUS', 'CORAGENT_JOB_MEMORY_MB')
    script.write_text('import os, json\nprint(json.dumps([os.environ.get(k) for k in ' + repr(variables) + ']))\n')
    prepared = prepare_script(config, 'local', 'validation', script, submission={'resources': {'cpus': 12, 'memory_mb': 16384}})
    result = run_guard(stage(tmp_path, prepared), prepared['command'])
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == ['12', '12', '12', '12', '16384']


@pytest.mark.parametrize('executor', ['chemical.gaussian', 'chemical.cf22d', 'chemical.crest', 'chemical.xtb'])
def test_shortcut_program_threads_follow_job_allocation(tmp_path, mock_environment_probe, executor):
    config = configured(tmp_path)
    inputs = {'material': geometry(tmp_path)} if executor == 'chemical.crest' else {'geometry': geometry(tmp_path)}
    arguments = [] if executor == 'chemical.crest' else ['--task', 'sp']
    prepared = prepare(config, 'local', executor, '1', inputs, arguments, submission={'resources': {'cpus': 12}})
    check_binding(prepared, probe=False)
    assert prepared['metadata']['program_resources']['threads'] == 12
    if executor != 'chemical.xtb':
        argv = prepared['metadata']['execution_argv']
        assert argv[argv.index('--threads') + 1] == '12'


def test_explicit_gaussian_input_drives_allocation_and_is_not_rewritten(tmp_path, mock_environment_probe):
    config = configured(tmp_path)
    source = tmp_path / 'input.gjf'
    source.write_text('%nprocshared=12\n%mem=8GB\n#p HF/sto-3g SP\n\nwater\n\n0 1\n\n')
    before = source.read_bytes()
    def build(**kw):
        return prepare(config, 'local', 'chemical.gaussian-input', '1', {'input': source}, **kw)
    request = build()
    assert request['metadata']['resources'] == {'cpus': 12, 'memory_mb': 9103}
    assert request['metadata']['program_resources']['program_memory_mb'] == 8192
    check_binding(request, probe=False)
    with pytest.raises(ValueError, match='job_resource_conflict'):
        build(submission={'resources': {'cpus': 4}})
    with pytest.raises(ValueError, match='including overhead'):
        build(submission={'resources': {'memory_mb': 8192}})
    assert source.read_bytes() == before


@pytest.mark.parametrize('arguments,submission', [
    (['--threads', '8'], {'resources': {'cpus': 12}}),
    (['--memory-mb', '8192'], {'resources': {'memory_mb': 8192}}),
])
def test_conflicting_scientific_flags_fail_before_probe(tmp_path, monkeypatch, arguments, submission):
    config = configured(tmp_path)
    monkeypatch.setattr('research_agent.application.executors.probe_binding', lambda *a: pytest.fail('conflict must fail before probe'))
    with pytest.raises(ValueError, match='job_resource_conflict'):
        prepare(config, 'local', 'chemical.gaussian', '1', {'geometry': geometry(tmp_path)},
                ['--task', 'sp', *arguments], submission=submission)


@pytest.mark.parametrize('operation,version', [('scan-xtb', '1'), ('neb-gaussian', '2'), ('electronic-gaussian', '1'), ('mecp-gaussian', '1')])
def test_serial_path_resources_use_per_process_settings_not_image_count(tmp_path, mock_environment_probe, operation, version):
    config = configured(tmp_path)
    source = tmp_path / 'input.json'
    source.write_text(json.dumps({'settings': {'threads': 12, **({'memory_mb': 8000} if 'gaussian' in operation else {})},
                                 'image_count': 9}))
    prepared = prepare(config, 'local', 'chemical.' + operation, version, {'input': source})
    assert prepared['metadata']['resources']['cpus'] == 12
    assert prepared['metadata']['program_resources']['concurrent_processes'] == 1
    check_binding(prepared, probe=False)
    with pytest.raises(ValueError, match='job_resource_conflict'):
        prepare(config, 'local', 'chemical.' + operation, version, {'input': source}, submission={'resources': {'cpus': 4}})


def test_binding_thread_override_cannot_hide_allocation_mismatch(tmp_path):
    config = configured(tmp_path)
    with config.open('a') as stream:
        stream.write('\n[execution.targets.local.bindings.gaussian.environment]\nOMP_NUM_THREADS="4"\n')
    with pytest.raises(ValueError, match='job_resource_conflict: OMP_NUM_THREADS'):
        gaussian(config, tmp_path, submission={'resources': {'cpus': 12}})


def test_input_changes_and_program_argument_tampering_are_rechecked(tmp_path, mock_environment_probe):
    from research_agent.jobs.environment import guarded_command
    config = configured(tmp_path)
    prepared = gaussian(config, tmp_path, submission={'resources': {'cpus': 12}})
    metadata = prepared['metadata']
    argv = metadata['execution_argv']
    argv[argv.index('--threads') + 1] = '4'
    prepared['command'], _ = guarded_command(metadata['execution_binding'], argv, metadata['execution_environment'],
                                            module_paths=metadata['module_paths'])
    with pytest.raises(ValueError, match='job_resource_conflict'):
        check_binding(prepared, probe=False)
    geometry(tmp_path).write_text('edited input')
    with pytest.raises(ValueError, match='prepared_input_changed'):
        check_binding(prepared, probe=False)


def test_preparer_cli_has_a_single_job_resource_entry_point(tmp_path):
    config = configured(tmp_path)
    path = tmp_path / 'request.json'
    result = subprocess.run([sys.executable, '-m', 'research_agent.application.executors',
        '--config', str(config), '--environment', 'local', '--executor', 'chemical.gaussian', '--version', '1',
        '--input', 'geometry=' + str(geometry(tmp_path)), '--cpus', '12', '--job-memory-mb', '16384',
        '--walltime', '01:00:00', '--output', str(path), '--', '--task', 'sp'], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    prepared = json.loads(path.read_text())
    assert prepared['metadata']['resources'] == {'cpus': 12, 'memory_mb': 16384, 'walltime': '01:00:00'}
    assert prepared['metadata']['program_resources']['threads'] == 12
    assert json.loads(result.stdout)['request_sha256'] == hashlib.sha256(path.read_bytes()).hexdigest()


def test_raw_job_uses_the_same_public_submission_field(tmp_path, queue):
    target, state = queue
    configured(tmp_path, external=target)
    root = tmp_path / 'work'
    workspace(root)
    receipt = execute('job.start', root, {'request_id': 'resource-test', 'command': ['/bin/true'],
        'submission': {'resources': {'cpus': 12, 'memory_mb': 8192}}})
    try:
        args = tasks(state)[0]['arguments']
        assert args[args.index('--cpu') + 1] == '12'
        finish(state)
        assert execute('job.status', root, {'job_id': receipt['job_id']})['state'] == 'succeeded'
    finally:
        execute('job.cancel', root, {'job_id': receipt['job_id']})


@pytest.mark.parametrize('resource', [{'cpus': 0}, {'cpus': True}, {'memory_mb': -1}, {'gpus': 1}, {'walltime': '00:00:00'}])
def test_invalid_or_unsupported_job_resources_fail_during_preparation(tmp_path, resource):
    config = configured(tmp_path)
    with pytest.raises(ValueError):
        gaussian(config, tmp_path, submission={'resources': resource})
