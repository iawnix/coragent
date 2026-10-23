"""Public installation uses independently prepared environments and preserves them."""

from tests.support.platforms import execution_config

from research_agent.bootstrap.layout import paths as app_paths
import base64
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tomllib
import pytest

from coragent_packaging.build.build_package import build_package
from coragent_packaging.installer import _job_install as jobs
from research_agent.bootstrap.layout import paths
from tests.unit.conftest import execution_target_fixture

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize('with_execution', [False, True])
def test_public_package_install_preserves_optional_execution(tmp_path, execution_target_fixture, with_execution):
    if importlib.util.find_spec('setuptools') is None:
        pytest.skip('local test environment lacks setuptools build backend')
    built = build_package(output_dir=tmp_path/'package', agent_manifest_path=None, allow_dirty=True, include_web=False)
    root = tmp_path/'installation'
    paths(root).initialize()
    acceptance = tmp_path/'acceptance'
    acceptance.mkdir()
    cache = app_paths(root).cache / 'job-install'
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.symlink_to(acceptance, target_is_directory=True)
    pin = json.loads((ROOT/'packaging/coragent_packaging/pi/source.json').read_text())
    pi_root = root/'runtimes/pi'/pin['commit']
    pi_root.mkdir(parents=True)
    subprocess.run(['cp','--reflink=auto','-a',os.environ['CORAGENT_TEST_PI_RUNTIME_ROOT']+'/.',str(pi_root)],check=True)
    config = tmp_path/'job.toml'
    if with_execution:
        settings = tomllib.loads(Path(os.environ['CORAGENT_JOB_CONFIG']).read_text())
        local = settings['execution']['platforms']['local']
        local['bindings'] = {'structure': local['bindings']['structure']}
        from research_agent.jobs import platforms_from_config
        route = platforms_from_config(Path(os.environ['CORAGENT_JOB_CONFIG']))[0]['local/main'].config
        local['storage'] = {key: route[key] for key in ('work_root', 'file_mode')}
        local['schedulers']['main'].update({key: route[key] for key in ('handler', 'handler_environment')})
        config.write_bytes(jobs.toml_bytes(settings))
        prefix = Path(local['bindings']['structure']['python']['prefix'])
        stamp = (prefix/'bin/python').stat().st_ino
    conda = os.environ.get('CORAGENT_TEST_CONDA') or shutil.which('conda')
    assert conda, 'Prepare with CORAGENT_TEST_CONDA set'
    environment = dict(os.environ, CONDA_OFFLINE='true')
    for key in ('CORAGENT_JOB_CONFIG', 'CORAGENT_INSTALL_ROOT', 'CORAGENT_RUNTIME_MANIFEST'):
        environment.pop(key, None)
    agent_config = tmp_path/'model-config'
    agent_config.mkdir()
    command = [sys.executable,'-S','-B',str(ROOT/'packaging/coragent_packaging/installer/installer.py'),'install','--source','package',
               '--package-manifest',built['manifest'],'--install-root',str(root),'--conda-root',str(Path(conda).parent.parent),
               '--job-offline','--service-scope','none','--without-web',
               '--agent-config-dir',str(agent_config),
               '--phone-access','disabled','--non-interactive','--yes','--allow-dirty','--json']
    subprocess.run([*command, *(['--job-config',str(config)] if with_execution else [])],env=environment,check=True)
    if with_execution:
        record = json.loads((paths(root).state/jobs.RECORD).read_text())
        assert record['readiness']['targets']['local/main']['status'] == 'execution_verified'
        assert len(record['readiness']['targets']['local/main']['jobs']) == 2
        assert record['publication']['targets']['local/main']['status'] == 'execution_verified'
        assert record['environments'] == []
    else:
        assert 'execution' not in paths(root).configuration.read()
        assert 'name_resolver' not in paths(root).configuration.read()
        assert not paths(root).job_config.exists() and not paths(root).resolver_config.exists()
        assert not (paths(root).state / jobs.RECORD).exists()
        assert not (paths(root).state / 'installation/qrun-pools.json').exists()
    runtime = json.loads((paths(root).runtime_home/'env.json').read_text())
    python = runtime['python_executable']
    clean = jobs.acceptance_environment(root/'current/agent', python)
    clean.pop('CORAGENT_JOB_CONFIG', None)
    clean.pop('CORAGENT_NAME_RESOLVER_CONFIG', None)
    subprocess.run([python,'-c','import research_agent,pathlib,sys; '
                    'assert pathlib.Path(research_agent.__file__).is_relative_to(sys.prefix)'],env=clean,check=True)
    subprocess.run([str(root / 'coragent'), '--help'], env=environment, stdout=subprocess.DEVNULL, check=True)
    research = tmp_path / 'ordinary-research'
    core_check = ('import sys;from pathlib import Path; '
                  'from research_agent.research.workspace import initialize_workspace,admit_research_workspace; '
                  'from research_agent.application.api import execute; '
                  'root=Path(sys.argv[1]);initialize_workspace(root,"ordinary","research"); '
                  'admit_research_workspace(root); '
                  'execute("research_create",root,{"goal":"Review the literature"}); '
                  'assert execute("research_read",root,{})["nodes"]')
    subprocess.run([python, '-B', '-c', core_check, str(research)], env=clean, check=True)
    subprocess.run(command,env=environment,check=True)
    if with_execution:
        assert (prefix/'bin/python').stat().st_ino == stamp
        repeated = json.loads((paths(root).state/jobs.RECORD).read_text())
        assert repeated['environments'] == []
    else:
        assert 'execution' not in paths(root).configuration.read()
        assert not paths(root).job_config.exists()
    assert not (root/'etc').exists()
    assert not (root/'var').exists()
    subprocess.run([str(root/'uninstall.sh'),'--config',str(paths(root).config_file),
                    '--service-scope','none','--purge-all','--non-interactive','--yes','--json'],env=environment,check=True)
    assert not root.exists()
    if with_execution:
        assert (prefix/'bin/python').stat().st_ino == stamp


def test_remote_provisioning_transports_and_executes_real_helper_offline(tmp_path, monkeypatch):
    # Replace only SSH transport with a local shell in the runner's network
    # namespace. The bundle, target helper, Conda install and probe are real.
    conda = os.environ.get('CORAGENT_TEST_CONDA') or shutil.which('conda')
    assert conda
    if not os.environ.get('CONDA_PKGS_DIRS'):
        pytest.skip('offline remote provisioning needs an explicit local Conda package cache')
    profile = jobs.profiles(ROOT)['wrapper']
    content = jobs.resource(Path(profile['root']), profile['lock']).read_bytes()
    checksum = jobs.digest(content+b'\0')
    store = tmp_path/'target-store'
    request = {'store':str(store),'owner':'transport-fixture','offline':True,
               'binding':{'manager':'conda','conda_executable':conda,'prefix':str(store/('wrapper-'+checksum[:16])),
                          'lock_ref':str(store/'locks'/checksum/'wrapper.lock')},
               'files':{'wrapper.lock':base64.b64encode(content).decode()},
               'profile':{key:profile[key] for key in ('lock','platform')}}
    original = subprocess.run
    def ssh(command, **kwargs):
        assert command[0] == 'ssh'
        kwargs['env']['CONDA_PKGS_DIRS'] = os.environ['CONDA_PKGS_DIRS']
        return original(['/bin/sh','-c',command[-1]], **kwargs)
    monkeypatch.setattr(subprocess, 'run', ssh)
    for _ in range(2):
        result = jobs.invoke_target({'kind':'remote','ssh_host':'fixture'}, request, ROOT)
        assert result['status'] == 'environment_verified'
    assert not list(store.glob('.installer-*'))
