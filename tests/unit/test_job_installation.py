"""Installation plans and ordinary Job acceptance use deterministic local inputs."""

from tests.support.platforms import execution_config

from research_agent.bootstrap.layout import paths as app_paths
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tomllib

import pytest

from coragent_packaging.installer import _job_install as jobs
from coragent_packaging.installer import install_wizard as wizard
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
                              *remaining], use_environment=False)
    args.job_profile = profiles
    return args


def test_fresh_installation_has_no_execution_services_or_environment_provisioning(tmp_path, monkeypatch):
    args = options(tmp_path)
    monkeypatch.setattr(subprocess, 'run', lambda *_a, **_k: pytest.fail('empty installation must not run commands'))
    plan = jobs.plan(args)
    assert plan['settings'] is None and plan['resolver'] is None
    assert plan['qrun'] == []
    assert plan['environments'] == []
    assert plan['targets'] == []
    assert not (tmp_path/'install').exists()
    assert not (tmp_path/'software').exists()
    layout = app_paths(args.install_root).initialize()
    prepared = jobs.prepare(jobs.plan(args), args, ROOT, '/unused/python')
    result = jobs.publish(prepared)
    assert result['job']['status'] == result['name_resolver']['status'] == 'not_configured'
    assert 'execution' not in layout.configuration.read()
    assert 'name_resolver' not in layout.configuration.read()
    assert not layout.job_config.exists() and not layout.resolver_config.exists()
    assert not (layout.cache / 'job-install').exists()
    assert not (layout.state / jobs.RECORD).exists()


@pytest.mark.parametrize('option,value', [
    ('--job-software-root', 'local/main=/fixture/software'),
    ('--verify-job-target', 'local/main'),
    ('--manage-qrun', 'local/main'),
])
def test_execution_options_require_an_explicit_platform_configuration(tmp_path, option, value):
    with pytest.raises(ValueError, match='execution configuration required'):
        jobs.plan(options(tmp_path, option, value))


@pytest.mark.parametrize('old_configuration', ['malformed', 'missing_credential'])
def test_explicit_execution_import_repairs_invalid_previous_configuration(tmp_path, monkeypatch, old_configuration):
    source = tmp_path/'replacement.toml'
    args = options(tmp_path, '--job-config', str(source))
    layout = app_paths(args.install_root).initialize()
    previous = execution_config('cluster', {'cluster': {
        'executor': 'tri', 'transport': 'ssh', 'ssh_host': 'old-cluster',
        'work_root': '/fixture/jobs', 'handler': ['/fixture/tri-handler']}})
    scheduler = previous['platforms']['cluster']['schedulers']['main']
    if old_configuration == 'malformed':
        scheduler['executor'] = 'unsupported'
    else:
        scheduler['handler_environment'] = {'TRI_AUTH_TOKEN': 'credential:missing_token'}
    layout.configuration.update(execution=previous)
    replacement = execution_config('cluster', {'cluster': {
        'executor': 'external', 'transport': 'ssh', 'ssh_host': 'replacement-cluster',
        'work_root': '/fixture/jobs', 'handler': ['/fixture/replacement-handler']}})
    source.write_bytes(jobs.toml_bytes({'execution': replacement}))
    monkeypatch.setattr(subprocess, 'run', lambda *_a, **_k: pytest.fail('repair planning must not contact a cluster'))

    with pytest.raises(ValueError):
        jobs.plan(options(tmp_path))
    plan = jobs.plan(args)
    plan['readiness'] = {'targets': {}}
    result = jobs.publish(plan)['job']

    assert layout.configuration.read()['execution'] == replacement
    assert tomllib.loads(layout.job_config.read_text())['execution'] == replacement
    assert result['configuration_changed'] is True
    assert result['previous_sha256'] is not None
    assert result['previous_sha256'] != result['sha256']


@pytest.mark.parametrize('source', ['configuration', 'import'])
def test_resolver_configuration_is_validated_without_execution(tmp_path, source):
    args = options(tmp_path)
    layout = app_paths(args.install_root).initialize()
    invalid = {'default_resolver': 'unsupported'}
    if source == 'configuration':
        layout.configuration.update(name_resolver=invalid)
    else:
        imported = tmp_path/'resolver.toml'
        imported.write_bytes(jobs.toml_bytes(invalid))
        args.name_resolver_config = str(imported)

    with pytest.raises(ValueError, match='default_resolver'):
        jobs.plan(args)
    assert not layout.job_config.exists() and not layout.resolver_config.exists()


def test_profile_completes_partial_native_binding_and_rejects_unknown_target(tmp_path):
    config = tmp_path/'job.toml'
    config.write_text('[execution]\nschema_version = 2\ndefault_platform="local"\n[execution.platforms.local]\ndefault_scheduler = "main"\nschedulers.main.executor = "qrun"\ntransport = "local"\nstorage.work_root = "/fixture/qrun/jobs"\nsubmission = {resources = {cpus = 1, memory_mb = 512}}\n[execution.platforms.local.bindings.xtb]\ncommand="/native/xtb"\n')
    value = jobs.plan(options(tmp_path, '--job-config',str(config),'--job-profile','local/main:wrapper'))
    wizard._validate_job_config(jobs.contract().configuration_document(value['settings']))
    assert value['settings']['targets']['local/main']['backends']['xtb']['command'] == '/native/xtb'
    with pytest.raises(ValueError, match='target is not configured'):
        jobs.plan(options(tmp_path, '--job-conda', 'typo/main=/bin/conda'))


def test_core_installer_rejects_cluster_provisioning_options(tmp_path, monkeypatch):
    with pytest.raises(ValueError, match='separately'):
        wizard.parse_args(['--job-profile','local/main:structure'])
    monkeypatch.setenv('CORAGENT_JOB_PROFILE','local/main:render')
    with pytest.raises(ValueError, match='separately'):
        wizard.parse_args([])


def test_existing_bindings_are_preserved_and_remote_is_not_contacted(tmp_path, monkeypatch):
    config = tmp_path/'job.toml'
    config.write_text('[execution]\nschema_version = 2\ndefault_platform="local"\n[execution.platforms.local]\ndefault_scheduler = "main"\nschedulers.main.executor = "qrun"\ntransport = "local"\nstorage.work_root = "/fixture/qrun/jobs"\nsubmission = {resources = {cpus = 1, memory_mb = 512}}\n[execution.platforms.local.bindings.shell]\ncommand="/bin/sh"\n[execution.platforms.cluster]\ndefault_scheduler = "main"\nschedulers.main.executor = "external"\ntransport="ssh"\nssh_host="fixture"\nstorage.work_root="/jobs"\nschedulers.main.handler=["/bin/true"]\n[execution.platforms.cluster.schedulers.main.submission]\nqueue="batch"\n')
    monkeypatch.setattr(subprocess, 'run', lambda *_a, **_k: pytest.fail('planning must not run commands'))
    value = jobs.plan(options(tmp_path, '--job-config', str(config)))
    assert jobs.contract().configuration_document(value['settings'])['execution']['platforms']['cluster']['storage']['work_root'] == '/jobs'
    assert value['targets'] == ['local/main']
    assert value['environments'] == []
    with pytest.raises(ValueError, match='job-software-root'):
        jobs.plan(options(tmp_path, '--job-config', str(config), '--job-profile', 'cluster/main:pyscf'))
    remote = jobs.plan(options(tmp_path, '--job-config', str(config), '--job-profile', 'cluster/main:pyscf',
                              '--job-software-root', 'cluster/main=/remote/envs', '--job-conda', 'cluster/main=/remote/conda/bin/conda'))
    row = remote['environments'][0]
    assert row['binding']['prefix'].startswith('/remote/envs/pyscf-')
    assert remote['targets'] == ['cluster/main', 'local/main']


def test_managed_upgrade_reuses_identity_and_detects_concurrent_config_change(tmp_path):
    args = options(tmp_path, '--job-profile', 'local/qrun:structure')
    args.job_software_root = ['local/qrun=' + str(tmp_path/'software')]
    layout = app_paths(args.install_root).initialize()
    layout.configuration.update(execution={'schema_version': 2, 'default_platform': 'local',
        'platforms': {'local': {'transport': 'local', 'default_scheduler': 'qrun',
            'storage': {'work_root': str(layout.jobs)}, 'schedulers': {'qrun': {'executor': 'qrun'}}}}})
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
    config.write_text('[execution]\nschema_version = 2\ndefault_platform="local"\n[execution.platforms.local]\ndefault_scheduler = "main"\nschedulers.main.executor = "qrun"\ntransport = "local"\nstorage.work_root = "/fixture/qrun/jobs"\nsubmission = {resources = {cpus = 1, memory_mb = 512}}\n[execution.platforms.local.bindings.shell]\ncommand="/bin/sh"\n')
    result = subprocess.run([sys.executable, '-S', '-B', str(ROOT/'packaging/coragent_packaging/installer/installer.py'), 'install',
                             '--source', 'local', '--dry-run', '--job-config', str(config),
                             '--install-root', str(tmp_path/'install')], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)['plan']['scientific_execution']['verify_targets'] == ['local/main']
    assert not (tmp_path/'install').exists()


@pytest.mark.skipif(importlib.util.find_spec('numpy') is None, reason='fixture environment lacks NumPy for structure acceptance')
def test_candidate_and_published_config_work_inside_real_jobs(tmp_path):
    config = tomllib.loads(Path(os.environ['CORAGENT_JOB_CONFIG']).read_text())
    local = config['execution']['platforms']['local']
    local['bindings'] = {'structure': local['bindings']['structure']}
    local['bindings']['structure'].pop('environment', None)
    # Child acceptance processes need the actual fixture endpoint in their config.
    from research_agent.jobs import platforms_from_config
    route = platforms_from_config(Path(os.environ['CORAGENT_JOB_CONFIG']))[0]['local/main'].config
    local['storage'] = {key: route[key] for key in ('work_root', 'file_mode')}
    local['schedulers']['main'].update({key: route[key] for key in ('handler', 'handler_environment')})
    source = tmp_path/'job.toml'
    source.write_bytes(jobs.toml_bytes(config))
    args = options(tmp_path, '--job-config', str(source))
    app_paths(args.install_root).initialize()
    plan = jobs.prepare(jobs.plan(args), args, ROOT, sys.executable)
    report = plan['readiness']
    assert report['targets']['local/main']['status'] == 'execution_verified', report
    assert len(report['targets']['local/main']['jobs']) == 2
    assert report['external_services'] == 'not_checked'
    jobs.publish(plan)
    jobs.verify_publication(plan, sys.executable, timeout=args.job_check_timeout)
    record = json.loads((app_paths(Path(args.install_root)).state/jobs.RECORD).read_text())
    result = record['publication']
    assert result['targets']['local/main']['status'] == 'execution_verified', result


@pytest.mark.parametrize('timeout', [37, 300])
def test_candidate_and_publication_acceptance_share_operator_timeout(tmp_path, monkeypatch, timeout):
    config = tmp_path / 'job.toml'
    config.write_bytes(jobs.toml_bytes({'execution': execution_config('local', {'local': {
        'transport': 'local', 'executor': 'qrun', 'work_root': str(tmp_path / 'jobs'),
        'bindings': {'shell': {'command': '/bin/sh'}}}})}))
    args = options(tmp_path, '--job-config', str(config), '--job-check-timeout', str(timeout))
    app_paths(args.install_root).initialize()
    calls = []
    def run(command, **kwargs):
        calls.append(command)
        assert Path(command[2]).name == '_job_acceptance.py'
        assert command[command.index('--timeout') + 1] == str(timeout)
        report = Path(command[command.index('--report') + 1])
        report.write_text(json.dumps({'schema_version': 'coragent-job-readiness/1',
            'targets': {'local/main': {'status': 'environment_verified'}}}))
        return subprocess.CompletedProcess(command, 0, '', '')
    monkeypatch.setattr(subprocess, 'run', run)
    args._prepared_job_plan = jobs.prepare(jobs.plan(args), args, ROOT, sys.executable)
    backend_configs = jobs.publish(args._prepared_job_plan)
    wizard.verify_job_bindings(args, {'runtime': {'python_executable': sys.executable}}, backend_configs)
    assert len(calls) == 2
    assert '--bindings-only' not in calls[0]
    assert '--bindings-only' in calls[1]


def test_execution_publication_preserves_secret_references_and_ignores_generated_edits(tmp_path, monkeypatch):
    args = options(tmp_path)
    layout = app_paths(args.install_root).initialize()
    layout.credentials.write_text(json.dumps({'models': {}, 'secrets': {'tri_token': 'fake-tri-token'}}))
    configured = execution_config('cluster', {'cluster': {
        'executor': 'tri', 'transport': 'ssh', 'ssh_host': 'fixture',
        'work_root': '/fixture/jobs', 'handler': ['/fixture/tri-handler'],
        'handler_environment': {'TRI_AUTH_TOKEN': 'credential:tri_token'}}})
    layout.configuration.update(execution=configured)
    monkeypatch.setattr(subprocess, 'run', lambda *_a, **_k: pytest.fail('publication must not contact a cluster'))
    plan = jobs.plan(args)
    plan['readiness'] = {'targets': {}}
    publication = jobs.publish(plan)['job']
    assert publication['configuration_changed'] is False
    assert publication['previous_sha256'] == publication['sha256']
    published = layout.configuration.read()['execution']
    assert published == configured
    assert 'fake-tri-token' not in layout.config_file.read_text()
    assert tomllib.loads(layout.job_config.read_text())['execution']['platforms']['cluster']['schedulers']['main']['handler_environment']['TRI_AUTH_TOKEN'] == 'fake-tri-token'
    layout.job_config.write_text('invalid derived file')
    next_plan = jobs.plan(args)
    assert next_plan['settings']['targets']['cluster/main']['handler_environment']['TRI_AUTH_TOKEN'] == 'fake-tri-token'
    next_plan['readiness'] = {'targets': {}}
    next_publication = jobs.publish(next_plan)['job']
    assert next_publication['configuration_changed'] is False
    assert next_publication['previous_sha256'] == next_publication['sha256'] == publication['sha256']
    assert layout.configuration.read()['execution'] == configured
    assert tomllib.loads(layout.job_config.read_text())['execution']['platforms']['cluster']['ssh_host'] == 'fixture'


def test_ssh_payload_contains_only_selected_target_resources(tmp_path, monkeypatch):
    request = {'store':'/remote/envs','binding':{'prefix':'/remote/envs/structure'},'files':{},'owner':'fixture'}
    target = {'kind':'remote','ssh_host':'cluster','ssh_config':'/fixture/ssh-config'}
    def run(command, **kwargs):
        assert command[0] == 'ssh' and command[-2] == 'cluster'
        payload = json.loads(kwargs['input'])
        assert payload['request'] == request
        assert set(payload['bundle']) == {'packaging/coragent_packaging/installer/_job_target.py','packaging/coragent_packaging/installer/install_job_environment.py',
            'backend/src/research_agent/jobs/config_contract.py','backend/src/research_agent/jobs/environment_probe.py'}
        assert 'models.json' not in kwargs['input'] and 'auth.json' not in kwargs['input']
        return subprocess.CompletedProcess(command, 0, 'CORAGENT_PROVISION={"status":"environment_verified"}\n', '')
    monkeypatch.setattr(subprocess, 'run', run)
    assert jobs.invoke_target(target, request, ROOT)['status'] == 'environment_verified'


@pytest.mark.parametrize('scheduler', ['pbs', 'torque', 'slurm'])
@pytest.mark.parametrize('file_mode', ['staged', 'shared'])
@pytest.mark.skipif(importlib.util.find_spec('numpy') is None, reason='fixture environment lacks NumPy for structure acceptance')
def test_remote_acceptance_uses_scheduler_collects_results_and_removes_test_jobs(cluster, tmp_path, monkeypatch, scheduler, file_mode):
    from coragent_packaging.installer._job_acceptance import accept
    from research_agent.jobs import environment
    platform, calls, remote_root = cluster
    local = tomllib.loads(Path(os.environ['CORAGENT_JOB_CONFIG']).read_text())['execution']['platforms']['local']
    resolver = tmp_path/'remote-resolver.toml'
    resolver.write_text('default_resolver="auto"\n')
    structure = {**local['bindings']['structure'],
                 'environment': {'CORAGENT_NAME_RESOLVER_CONFIG': str(resolver)}}
    target = {**platform.config, 'file_mode': file_mode, 'handler': [*platform.handler[:-1], scheduler],
              'submission':{'queue':'batch','resources':{'cpus':1,'walltime':'00:00:20'}},
              'bindings':{'structure':structure}}
    config = tmp_path/'remote-job.toml'
    config.write_bytes(jobs.toml_bytes({'execution':execution_config('cluster', {'cluster':target})}))
    original_capture = environment._capture
    def transport(command, **kwargs):
        assert command[0] == 'ssh'
        return original_capture(['/bin/sh','-c',command[-1]], **kwargs)
    monkeypatch.setattr(environment, '_capture', transport)
    result = accept(config, ROOT, tmp_path/'acceptance', ['cluster/main'], 20)
    assert result['targets']['cluster/main']['status'] == 'execution_verified', result
    assert len(result['targets']['cluster/main']['jobs']) == 2
    assert any(command[0] == 'rsync' for command, _ in calls) == (file_mode == 'staged')
    assert not list(remote_root.glob('job_*'))
    assert not list(remote_root.glob('.coragent-acceptance-*'))


def test_acceptance_waits_for_cancellation_and_reports_pending_jobs(tmp_path, monkeypatch):
    from coragent_packaging.installer import _job_acceptance as acceptance
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


@pytest.mark.parametrize('targets', [
    ['first/main'],
    ['first/main', 'offline/main', 'last/main'],
])
def test_acceptance_probes_each_selected_target_once_and_isolates_failures(tmp_path, monkeypatch, targets):
    from coragent_packaging.installer import _job_acceptance as acceptance
    from research_agent.application import environment_check
    config = tmp_path / 'job.toml'
    config.write_bytes(jobs.toml_bytes({'execution': execution_config('first', {name: {
        'transport': 'local', 'executor': 'qrun', 'work_root': '/fixture/' + name,
        'bindings': {'native': {'command': '/bin/true'}}}
        for name in ('first', 'offline', 'last')})}))
    calls = []
    def probe(settings, selected, requirements):
        name = selected['environment']
        calls.append(name)
        if name == 'offline/main':
            raise ValueError('environment_executable_missing')
        return {'target': name}
    monkeypatch.setattr(environment_check, 'probe_binding', probe)
    monkeypatch.setattr(environment_check, 'installed_catalogs', lambda: [])
    monkeypatch.setattr(acceptance, 'profiles', lambda _: {})
    monkeypatch.setattr(acceptance, 'initialize_workspace', lambda *args: None)
    monkeypatch.setattr(acceptance, 'admit_research_workspace', lambda *args: None)
    monkeypatch.setenv('CORAGENT_JOB_CONFIG', str(config))
    monkeypatch.setenv('CORAGENT_PACKAGE_ROOT', str(ROOT))
    report = acceptance.accept(config, ROOT, tmp_path / 'acceptance', targets, 1)
    assert report['schema_version'] == 'coragent-job-readiness/1'
    assert calls == targets
    for name, row in report['targets'].items():
        if name not in targets:
            assert row == {'status': 'not_verified'}
        elif name == 'offline/main':
            assert row['status'] == 'failed'
            assert row['error'] == 'environment_executable_missing'
        else:
            assert row['status'] == 'environment_verified'
            assert row['environments']['binding:native']['environment_evidence'] == {'target': name}


def test_target_provisioning_reuses_verified_environment_and_recovers_interrupted_prefix(tmp_path, monkeypatch):
    from coragent_packaging.installer import _job_target as target
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
