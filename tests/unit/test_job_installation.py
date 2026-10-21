"""Installation plans and ordinary Job acceptance use deterministic local inputs."""

from research_agent.foundation.layout import paths as app_paths
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tomllib

import pytest

from scripts import _job_install as jobs
from scripts import install_wizard as wizard
from tests.unit.test_remote_job_execution import cluster

ROOT = Path(__file__).resolve().parents[2]


def options(tmp_path, *extra):
    # These tests exercise the independent environment maintenance helper.
    profiles, remaining = [], []
    iterator = iter(extra)
    for value in iterator:
        if value == '--job-profile': profiles.append(next(iterator))
        else: remaining.append(value)
    args = wizard.parse_args(['--install-root', str(tmp_path/'install'), '--conda-root', str(tmp_path/'conda'),
                              '--job-software-root', 'local=' + str(tmp_path/'software'), *remaining], use_environment=False)
    args.job_profile = profiles
    return args


def test_fresh_plan_only_references_execution_and_creates_no_environments(tmp_path):
    args = options(tmp_path)
    plan = jobs.plan(args)
    assert plan['settings']['targets']['local']['backends'] == {}
    assert plan['environments'] == []
    assert plan['targets'] == ['local']
    assert not (tmp_path/'install').exists()
    assert not (tmp_path/'software').exists()


def test_profile_completes_partial_native_binding_and_rejects_unknown_target(tmp_path):
    config = tmp_path/'job.toml'
    config.write_text('[execution]\ndefault_target="local"\n[execution.targets.local]\ntype="local"\ndriver="process"\n'
                      '[execution.targets.local.bindings.xtb]\ncommand="/native/xtb"\n')
    value = jobs.plan(options(tmp_path, '--job-config',str(config),'--job-profile','local:wrapper'))
    wizard._validate_job_config(value['settings'])
    assert value['settings']['targets']['local']['backends']['xtb']['command'] == '/native/xtb'
    with pytest.raises(ValueError, match='target is not configured'):
        jobs.plan(options(tmp_path, '--job-conda', 'typo=/bin/conda'))


def test_core_installer_rejects_cluster_provisioning_options(tmp_path, monkeypatch):
    with pytest.raises(ValueError, match='separately'):
        wizard.parse_args(['--job-profile','local:structure'])
    monkeypatch.setenv('CORAGENT_JOB_PROFILE','local:render')
    with pytest.raises(ValueError, match='separately'):
        wizard.parse_args([])


def test_existing_bindings_are_preserved_and_remote_is_not_contacted(tmp_path, monkeypatch):
    config = tmp_path/'job.toml'
    config.write_text('[execution]\ndefault_target="local"\n[execution.targets.local]\ntype="local"\ndriver="process"\n'
                      '[execution.targets.local.bindings.shell]\ncommand="/bin/sh"\n'
                      '[execution.targets.cluster]\ndriver="external"\ntransport="ssh"\nssh_host="fixture"\nwork_root="/jobs"\n'
                      'handler=["/bin/true"]\n[execution.targets.cluster.submission]\nqueue="batch"\n')
    monkeypatch.setattr(subprocess, 'run', lambda *_a, **_k: pytest.fail('planning must not run commands'))
    value = jobs.plan(options(tmp_path, '--job-config', str(config)))
    assert jobs.contract().configuration_document(value['settings'])['execution']['targets']['cluster']['work_root'] == '/jobs'
    assert value['targets'] == ['local']
    assert value['environments'] == []
    with pytest.raises(ValueError, match='job-software-root'):
        jobs.plan(options(tmp_path, '--job-config', str(config), '--job-profile', 'cluster:pyscf'))
    remote = jobs.plan(options(tmp_path, '--job-config', str(config), '--job-profile', 'cluster:pyscf',
                              '--job-software-root', 'cluster=/remote/envs', '--job-conda', 'cluster=/remote/conda/bin/conda'))
    row = remote['environments'][0]
    assert row['binding']['prefix'].startswith('/remote/envs/pyscf-')
    assert remote['targets'] == ['cluster', 'local']


def test_managed_upgrade_reuses_identity_and_detects_concurrent_config_change(tmp_path):
    args = options(tmp_path, '--job-profile', 'local:structure')
    app_paths(args.install_root).initialize()
    first = jobs.plan(args)
    first['readiness'] = {'targets': {}}
    jobs.publish(first)
    second = jobs.plan(args)
    assert second['environments'][0]['binding'] == first['environments'][0]['binding']
    config = app_paths(Path(args.install_root)).config_file
    config.write_text(config.read_text() + '\n# operator edit\n')
    with pytest.raises(ValueError, match='input changed'):
        jobs.publish(second)


def test_bootstrap_validation_works_without_site_packages(tmp_path):
    config = tmp_path/'job.toml'
    config.write_text('[execution]\ndefault_target="local"\n[execution.targets.local]\ntype="local"\ndriver="process"\n'
                      '[execution.targets.local.bindings.shell]\ncommand="/bin/sh"\n')
    result = subprocess.run([sys.executable, '-S', '-B', str(ROOT/'scripts/installer.py'), 'install',
                             '--source', 'local', '--dry-run', '--job-config', str(config),
                             '--install-root', str(tmp_path/'install')], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)['plan']['scientific_execution']['verify_targets'] == ['local']
    assert not (tmp_path/'install').exists()


@pytest.mark.skipif(importlib.util.find_spec('numpy') is None, reason='fixture environment lacks NumPy for structure acceptance')
def test_candidate_and_published_config_work_inside_real_jobs(tmp_path):
    config = tomllib.loads(Path(os.environ['CORAGENT_JOB_CONFIG']).read_text())
    local = config['execution']['targets']['local']
    local['bindings'] = {'structure': local['bindings']['structure']}
    local['bindings']['structure'].pop('environment', None)
    source = tmp_path/'job.toml'
    source.write_bytes(jobs.toml_bytes({'execution': {'default_target':'local','targets':{'local':local}}}))
    args = options(tmp_path, '--job-config', str(source))
    plan = jobs.prepare(jobs.plan(args), args, ROOT, sys.executable)
    report = plan['readiness']
    assert report['targets']['local']['status'] == 'execution_verified', report
    assert len(report['targets']['local']['jobs']) == 2
    assert report['external_services'] == 'not_checked'
    jobs.publish(plan)
    jobs.verify_publication(plan, sys.executable)
    record = json.loads((app_paths(Path(args.install_root)).state/jobs.RECORD).read_text())
    result = record['publication']
    assert result['targets']['local']['status'] == 'execution_verified', result


def test_ssh_payload_contains_only_selected_target_resources(tmp_path, monkeypatch):
    request = {'store':'/remote/envs','binding':{'prefix':'/remote/envs/structure'},'files':{},'owner':'fixture'}
    target = {'kind':'remote','ssh_host':'cluster','ssh_config':'/fixture/ssh-config'}
    def run(command, **kwargs):
        assert command[0] == 'ssh' and command[-2] == 'cluster'
        payload = json.loads(kwargs['input'])
        assert payload['request'] == request
        assert set(payload['bundle']) == {'scripts/_job_target.py','scripts/install_job_environment.py',
            'backend/src/research_agent/jobs/config_contract.py','backend/src/research_agent/jobs/environment_probe.py'}
        assert 'models.json' not in kwargs['input'] and 'auth.json' not in kwargs['input']
        return subprocess.CompletedProcess(command, 0, 'CORAGENT_PROVISION={"status":"environment_verified"}\n', '')
    monkeypatch.setattr(subprocess, 'run', run)
    assert jobs.invoke_target(target, request, ROOT)['status'] == 'environment_verified'


@pytest.mark.parametrize('scheduler', ['pbs', 'torque', 'slurm'])
@pytest.mark.parametrize('file_mode', ['staged', 'shared'])
@pytest.mark.skipif(importlib.util.find_spec('numpy') is None, reason='fixture environment lacks NumPy for structure acceptance')
def test_remote_acceptance_uses_scheduler_collects_results_and_removes_test_jobs(cluster, tmp_path, monkeypatch, scheduler, file_mode):
    from scripts._job_acceptance import accept
    from research_agent.jobs import environment
    platform, calls, remote_root = cluster
    local = tomllib.loads(Path(os.environ['CORAGENT_JOB_CONFIG']).read_text())['execution']['targets']['local']
    resolver = tmp_path/'remote-resolver.toml'
    resolver.write_text('default_resolver="auto"\n')
    structure = {**local['bindings']['structure'],
                 'environment': {'CORAGENT_NAME_RESOLVER_CONFIG': str(resolver)}}
    target = {**platform.config, 'file_mode': file_mode, 'handler': [*platform.handler[:-1], scheduler],
              'submission':{'queue':'batch','resources':{'cpus':1,'walltime':'00:00:20'}},
              'bindings':{'structure':structure}}
    config = tmp_path/'remote-job.toml'
    config.write_bytes(jobs.toml_bytes({'execution':{'default_target':'cluster','targets':{'cluster':target}}}))
    original_capture = environment._capture
    def transport(command, **kwargs):
        assert command[0] == 'ssh'
        return original_capture(['/bin/sh','-c',command[-1]], **kwargs)
    monkeypatch.setattr(environment, '_capture', transport)
    result = accept(config, ROOT, tmp_path/'acceptance', ['cluster'], 20)
    assert result['targets']['cluster']['status'] == 'execution_verified', result
    assert len(result['targets']['cluster']['jobs']) == 2
    assert any(command[0] == 'rsync' for command, _ in calls) == (file_mode == 'staged')
    assert not list(remote_root.glob('job_*'))
    assert not list(remote_root.glob('.coragent-acceptance-*'))


def test_acceptance_waits_for_cancellation_and_reports_pending_jobs(tmp_path, monkeypatch):
    from scripts import _job_acceptance as acceptance
    calls = []
    def execute(operation, *args):
        calls.append(operation)
        if operation == 'job_start':
            return {'job_id':'job_fixture'}
        if operation == 'job_status':
            return {'state':'queued'}
        return {}
    ticks = iter(range(100))
    monkeypatch.setattr(acceptance, 'execute', execute)
    monkeypatch.setattr(acceptance.time, 'monotonic', lambda: next(ticks))
    monkeypatch.setattr(acceptance.time, 'sleep', lambda _:None)
    with pytest.raises(RuntimeError, match='cancellation_pending'):
        acceptance.run_job(tmp_path, {'request_id':'request'}, 3)
    assert calls.count('job_cancel') == 1
    assert calls[-1] == 'job_status'


def test_target_provisioning_reuses_verified_environment_and_recovers_interrupted_prefix(tmp_path, monkeypatch):
    from scripts import _job_target as target
    import base64
    store = tmp_path/'managed'
    raw = b'@EXPLICIT\nhttps://fixture.invalid/python.conda\n'
    digest = jobs.digest(raw + b'\0')
    prefix = store/('structure-' + digest[:16])
    request = {'store':str(store),'owner':'fixture','offline':True,
               'binding':{'manager':'conda','conda_executable':'/fixture/conda','prefix':str(prefix),
                          'lock_ref':str(store/'locks'/digest/'structure.lock')},
               'profile':{'lock':'structure.lock','platform':{'system':'Linux','machines':['x86_64'],'glibc':'2.28'}},
               'files':{'structure.lock':base64.b64encode(raw).decode()}}
    monkeypatch.setattr(target.platform, 'libc_ver', lambda:('glibc','2.35'))
    monkeypatch.setattr(target.platform, 'machine', lambda:'x86_64')
    calls=[]
    def install(binding, **kwargs):
        assert kwargs['offline']
        calls.append(prefix.exists())
        prefix.mkdir(exist_ok=True)
        (prefix/'coragent-environment.json').write_text('{}')
        return {'lock_sha256':digest,'inventory_sha256':'fixture'}
    monkeypatch.setattr(target, 'install', install)
    assert target.provision(request)['status'] == 'environment_verified'
    assert target.provision(request)['status'] == 'environment_verified'
    assert calls == [False,True]
    (prefix/'coragent-environment.json').unlink()
    (prefix/'partial').write_text('interrupted')
    (store/('.'+prefix.name+'.pending')).write_text(json.dumps({'installation_id':'fixture'},sort_keys=True)+'\n')
    target.provision(request)
    assert not (prefix/'partial').exists()
    with pytest.raises(ValueError, match='immutable_file_changed'):
        target.provision({**request,'owner':'different'})


def test_purge_selects_only_owned_unreferenced_local_environments(tmp_path):
    from contextlib import ExitStack
    root, store, workspace = tmp_path/'install', tmp_path/'software', tmp_path/'research'
    store.mkdir()
    (store/'installation-owner.json').write_text(json.dumps({'installation_id':jobs.digest(os.fsencode(root))[:16]}))
    record = {'environments':[{'kind':'local','managed':True,'store':str(store)}]}
    jobs.write_private(app_paths(root).state/jobs.RECORD,json.dumps(record).encode())
    with ExitStack() as guards:
        removed, retained = jobs.cleanup_stores(root, workspace, guards)
        assert removed == [store] and retained == []
    jobs.write_private(workspace/'t001/operations/executions/job_fixture.json',b'{"state":"running"}')
    with ExitStack() as guards:
        removed, retained = jobs.cleanup_stores(root, workspace, guards)
        assert removed == [] and retained == [str(store)]


def test_failed_preparation_store_is_kept_while_acceptance_job_is_unfinished(tmp_path):
    from contextlib import ExitStack
    root, store = tmp_path/'install', tmp_path/'software'
    store.mkdir()
    (store/'installation-owner.json').write_text(json.dumps({'installation_id':jobs.digest(os.fsencode(root))[:16]}))
    jobs.write_private(app_paths(root).state/jobs.STORES,json.dumps([{'kind':'local','store':str(store)}]).encode())
    job = app_paths(root).cache / 'job-install/candidate/jobs/local/operations/executions/job_fixture.json'
    jobs.write_private(job,b'{"state":"running"}')
    with ExitStack() as guards:
        assert jobs.cleanup_stores(root,tmp_path/'research',guards) == ([],[str(store)])
    jobs.write_private(job,b'{"state":"cancelled"}')
    with ExitStack() as guards:
        assert jobs.cleanup_stores(root,tmp_path/'research',guards) == ([store],[])
