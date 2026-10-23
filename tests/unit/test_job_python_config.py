
from tests.support.platforms import execution_config
import importlib.util
from pathlib import Path
import pytest
from research_agent.jobs.config_contract import validate_job_config, resolve_python, python_command, configuration_document


def binding(prefix):
    return {"manager": "conda", "conda_executable": "/opt/conda/bin/conda", "prefix": prefix, "lock_ref": "/opt/locks/python.lock"}


def config():
    return validate_job_config({"execution": execution_config("local", {
        "local": {'executor': 'qrun', 'transport': 'local', 'work_root': '/fixture/qrun/jobs'},
        "remote": {'executor': 'external', 'transport': 'ssh', 'ssh_host': 'fixture', 'work_root': '/scratch/jobs', 'handler': ['/bin/true'], 'submission': {'queue': 'test'}, 'python': binding('/opt/runner'), 'bindings': {'xtb': {'command': ['/opt/xtb']}, 'pyscf': {'python': binding('/opt/cf22d')}}}})})


def test_conda_selection_and_host_python_isolation():
    c = validate_job_config(config())
    assert resolve_python(c, 'remote/main', "xtb")["prefix"] == "/opt/runner"
    assert resolve_python(c, 'remote/main', "pyscf")["prefix"] == "/opt/cf22d"
    command = python_command(resolve_python(c, 'remote/main', "xtb"))
    assert command[:6] == ["env", "-u", "PYTHONHOME", "-u", "PYTHONPATH", "PYTHONNOUSERSITE=1"]
    assert command[-3:] == ["-p", "/opt/runner", "python"]


def test_legacy_interpreter_is_not_a_second_configuration_protocol():
    c = {"execution": execution_config("local", {
        "local": {'executor': 'qrun', 'transport': 'local', 'work_root': '/fixture/qrun/jobs'},
        "remote": {'executor': 'external', 'transport': 'ssh', 'ssh_host': 'fixture', 'work_root': '/scratch/jobs', 'handler': ['/bin/true'], 'python': '/usr/bin/python3'}})}
    with pytest.raises(ValueError, match="migrate legacy"):
        validate_job_config(c)


def test_skill_preparation_uses_bound_conda_and_rejects_dual_pyscf_binding(tmp_path, mock_environment_probe):
    import json
    import tomllib
    from research_agent.application.executors import prepare
    path = tmp_path / "job.toml"
    text = '[execution]\nschema_version = 2\ndefault_platform = "remote"\n[execution.platforms.remote]\ndefault_scheduler = "main"\nschedulers.main.executor = "external"\ntransport = "ssh"\nschedulers.main.handler = ["/bin/true"]\nssh_host = "fixture"\nstorage.work_root = "/scratch/jobs"\n[execution.platforms.remote.schedulers.main.submission]\nqueue = "test"\n[execution.platforms.remote.python]\nmanager = "conda"\nconda_executable = "/opt/conda/bin/conda"\nprefix = "/opt/runner"\nlock_ref = "/opt/locks/runner.lock"\n[execution.platforms.remote.bindings.xtb]\ncommand = ["/opt/xtb"]\n[execution.platforms.remote.bindings.pyscf.python]\nmanager = "conda"\nconda_executable = "/opt/conda/bin/conda"\nprefix = "/opt/cf22d"\nlock_ref = "/opt/locks/cf22d.lock"\n'
    path.write_text(text)
    xyz = tmp_path / "water.xyz"; xyz.write_text("1\nH\nH 0 0 0\n")
    job = prepare(path, {'platform': 'remote', 'scheduler_entry': 'main'}, "chemical.xtb", "1", {"geometry": xyz}, ["--task", "opt-sp"])
    assert "/opt/runner" in job["command"]
    assert job["execution_target"] == {'platform': 'remote', 'scheduler_entry': 'main'}
    assert job["metadata"]["python_binding"]["lock_ref"] == "/opt/locks/runner.lock"
    with pytest.raises(ValueError, match="runner_arguments_invalid.*",):
        prepare(path, {'platform': 'remote', 'scheduler_entry': 'main'}, "chemical.xtb", "1", {"geometry": xyz}, ["--task", "opt-sp", "--method", "GFN2-xTB"])
    with pytest.raises(ValueError, match="owned by the execution descriptor"):
        prepare(path, {'platform': 'remote', 'scheduler_entry': 'main'}, "chemical.xtb", "1", {"geometry": xyz}, ["--task", "sp", "--output-dir", "/tmp/escaped"])
    path.write_text(text.replace('[execution.platforms.remote.bindings.pyscf.python]', '[execution.platforms.remote.bindings.pyscf]\ncommand = ["/old/python"]\n[execution.platforms.remote.bindings.pyscf.python]'))
    with pytest.raises(ValueError, match="executor_binding_unused_command"):
        prepare(path, {'platform': 'remote', 'scheduler_entry': 'main'}, "chemical.cf22d", "1", {"geometry": xyz}, ["--task", "opt-sp"])


def test_example_and_python_binding_share_public_schema():
    import copy
    import json
    import tomllib
    from jsonschema import Draft202012Validator
    root = Path(__file__).resolve().parents[2]
    schema = json.loads((root / 'config/job.schema.json').read_text())
    from research_agent.jobs.config_contract import job_config_schema
    assert schema == job_config_schema()
    validator = Draft202012Validator(schema)
    example = tomllib.loads((root / 'config/job.example.toml').read_text())
    validator.validate(example)
    validate_job_config(example)
    inherited = copy.deepcopy(example)
    inherited['execution']['platforms']['local']['bindings']['pyscf'] = {}
    validator.validate(inherited)
    validate_job_config(inherited)
    assert resolve_python(validate_job_config(inherited), 'local/qrun', 'pyscf') == validate_job_config(inherited)['targets']['local/qrun']['python']
    for invalid in ['/usr/bin/python3', {**binding('/opt/env'), 'manager': 'venv'},
                    {**binding('/opt/env'), 'prefix': 'relative'}, {**binding('/opt/env'), 'extra': True}]:
        c = copy.deepcopy(example)
        c['execution']['platforms']['local']['python'] = invalid
        assert list(validator.iter_errors(c))
        with pytest.raises(ValueError):
            validate_job_config(c)


def test_installer_refuses_unverified_prefix_and_does_not_publish_bad_receipt(tmp_path, monkeypatch):
    import runpy
    from types import SimpleNamespace
    root = Path(__file__).resolve().parents[2]
    installer = runpy.run_path(str(root / 'packaging/coragent_packaging/installer/install_job_environment.py'))['install']
    prefix = tmp_path / 'science'; prefix.mkdir()
    lock = tmp_path / 'science.lock'; lock.write_text('@EXPLICIT\nhttps://example.test/python.conda\n')
    b = {**binding(str(prefix)), 'lock_ref': str(lock)}
    with pytest.raises(ValueError, match='no matching environment receipt'):
        installer(b)
    monkeypatch.setattr('subprocess.run', lambda *a, **k: SimpleNamespace(stdout='@EXPLICIT\nhttps://example.test/wrong.conda\n', returncode=0))
    with pytest.raises(ValueError, match='does not match'):
        installer(b, adopt=True)
    assert not (prefix / 'coragent-environment.json').exists()


@pytest.mark.parametrize('adopt', [False, True])
def test_installer_cli_uses_selected_target(tmp_path, adopt):
    import json
    import subprocess
    import sys
    root = Path(__file__).resolve().parents[2]
    config_path = tmp_path / 'job.toml'
    config_path.write_text(config_path.read_text().replace('execution.platforms.local', 'execution.platforms.science')
                           .replace('default_platform = "local"', 'default_platform = "queue"')
                           + '\n[execution.platforms.queue]\ndefault_scheduler = "main"\nschedulers.main.executor = "external"\ntransport = "local"\n'
                           + 'storage.work_root = ' + json.dumps(str(tmp_path / 'queue')) + '\nschedulers.main.handler = ["/bin/true"]\n')
    receipt = tmp_path / 'target-python/coragent-environment.json'
    if adopt:
        receipt.unlink()
    result = subprocess.run([sys.executable, '-B', str(root / 'packaging/coragent_packaging/installer/install_job_environment.py'),
                             '--config', str(config_path), '--platform', 'science', '--backend', 'structure',
                             *(['--adopt'] if adopt else [])], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    installed = json.loads(result.stdout)
    assert installed == json.loads(receipt.read_text())
    assert installed['python']['prefix'] == str(tmp_path / 'target-python')
    assert installed['inventory_sha256'].startswith('sha256:')


def test_failed_new_install_removes_only_its_partial_prefix(tmp_path, monkeypatch):
    import runpy
    import subprocess
    root = Path(__file__).resolve().parents[2]
    installer = runpy.run_path(str(root / 'packaging/coragent_packaging/installer/install_job_environment.py'))['install']
    prefix = tmp_path/'partial'
    lock = tmp_path/'science.lock'
    lock.write_text('@EXPLICIT\nhttps://example.test/python.conda#' + 'a'*64 + '\n')
    def broken_install(argv, **kwargs):
        assert argv[1] == 'create'
        prefix.mkdir()
        (prefix/'partial-file').write_text('interrupted installation')
        raise subprocess.CalledProcessError(1, argv)
    monkeypatch.setattr('subprocess.run', broken_install)
    with pytest.raises(subprocess.CalledProcessError):
        installer({**binding(str(prefix)), 'lock_ref':str(lock)})
    assert not prefix.exists() and lock.exists()


@pytest.mark.parametrize('contents', ['package==1.0\n', 'package>=1.0 --hash=sha256:'+'a'*64+'\n'])
def test_pip_install_requires_pinned_versions_and_hashes_before_creating_prefix(tmp_path, monkeypatch, contents):
    import runpy
    root = Path(__file__).resolve().parents[2]
    installer = runpy.run_path(str(root/'packaging/coragent_packaging/installer/install_job_environment.py'))['install']
    lock = tmp_path/'science.lock'; lock.write_text('@EXPLICIT\nhttps://example.test/python.conda\n')
    lock.with_suffix('.requirements.txt').write_text(contents)
    monkeypatch.setattr('subprocess.run', lambda *a, **kw: pytest.fail('invalid lock must fail before installation'))
    with pytest.raises(ValueError, match='environment_pip_lock_invalid'):
        installer({**binding(str(tmp_path/'science')), 'lock_ref':str(lock)})
    assert not (tmp_path/'science').exists()


def test_remote_queue_selection_is_explicit_and_allowlisted():
    from research_agent.jobs.config_contract import resolve_submission
    c=config();remote=c['targets']['remote/main'];remote['allowed_queues']=['test']
    assert resolve_submission(c,'remote/main','xtb')['queue']=='test'
    remote['submission']['queue']='forbidden'
    with pytest.raises(ValueError,match='not allowed'):resolve_submission(c,'remote/main','xtb')
    del remote['submission']
    assert 'queue' not in resolve_submission(c,'remote/main','xtb')


@pytest.mark.parametrize('mutate', [
    lambda target: target.update(ssh_host='-oProxyCommand=bad'),
    lambda target: target.update(work_root='/scratch/../other'),
    lambda target: target.update(driver='unsupported'),
    lambda target: target.update(command_timeout_seconds=0),
    lambda target: target.update(max_nodes=2),
    lambda target: target.update(commands={'pbsnodes': 'pbsnodes'}),
    lambda target: target['bindings']['xtb'].update(requires_gpu=False),
    lambda target: target['bindings']['xtb'].update(allowed_queues=['bad queue']),
])
def test_runtime_and_generated_schema_reject_invalid_remote_settings(mutate):
    from jsonschema import Draft202012Validator
    from research_agent.jobs.config_contract import job_config_schema
    value = configuration_document(config())
    mutate(value['execution']['platforms']['remote'])
    with pytest.raises(ValueError): validate_job_config(value)
    assert list(Draft202012Validator(job_config_schema()).iter_errors(value))


def test_target_selection_has_no_implicit_local_or_remote_alias(tmp_path, monkeypatch):
    from research_agent.jobs.config import platforms_from_config
    monkeypatch.delenv('CORAGENT_JOB_CONFIG', raising=False)
    with pytest.raises(ValueError, match='job_config_required'): platforms_from_config()
    path = tmp_path / 'remote.toml'
    path.write_text('[execution]\nschema_version = 2\ndefault_platform="cluster_a"\n[execution.platforms.cluster_a]\ndefault_scheduler = "main"\nschedulers.main.executor = "external"\ntransport="ssh"\nschedulers.main.handler=["/bin/true"]\nssh_host="fixture"\nstorage.work_root="/scratch/jobs"\n')
    platforms, default = platforms_from_config(path)
    assert set(platforms) == {'cluster_a/main'} and default == 'cluster_a/main'


def test_executor_and_transport_are_part_of_prepared_binding():
    from research_agent.jobs.config_contract import resolve_binding, binding_digest
    settings = config()
    settings['targets']['local/main']['backends'] = {'shell': {'command': '/bin/sh'}}
    baseline = resolve_binding(settings, 'local/main', 'shell', runtime='native')
    assert baseline['executor'] == 'qrun'
    assert baseline['transport'] == 'local'
    settings['targets']['local/main'].update(executor='tri', scheduler='tri')
    selected = resolve_binding(settings, 'local/main', 'shell', runtime='native')
    assert binding_digest(selected) != binding_digest(baseline)
    document = configuration_document(settings)
    document['execution']['platforms']['local']['supervisor'] = 'process'
    with pytest.raises(ValueError, match='unsupported fields'):
        validate_job_config(document)
