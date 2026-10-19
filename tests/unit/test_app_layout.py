import json
from pathlib import Path
import pytest
from research_agent.foundation.layout import paths, inspect_installation
from research_agent.foundation.configuration import Configuration, toml_text


@pytest.fixture
def layout(tmp_path, monkeypatch):
    config = Configuration(tmp_path / 'configuration/config.toml')
    config.write({'schema_version': 1, 'paths': {
        'software_root': str(tmp_path / 'software'), 'state_root': str(tmp_path / 'state'),
        'workspace_root': str(tmp_path / 'research')}})
    monkeypatch.setenv('CORAGENT_CONFIG', str(config.path))
    return paths(config_file=config.path)


def test_layout_initialization_and_configuration_are_shared(layout):
    layout.initialize()
    recovered = paths(layout.root)
    assert recovered.config_file == layout.config_file
    assert recovered.state == layout.state
    assert recovered.read_config()['workspace_root'] == str(layout.workspace_root)
    assert layout.marker.stat().st_mode & 0o077 == 0
    assert layout.credentials.stat().st_mode & 0o077 == 0
    assert not (layout.root / 'etc').exists()
    assert not (layout.root / 'var').exists()
    assert layout.env_root.is_absolute()


@pytest.mark.parametrize('old', ['.pi', '.agents', 'etc', 'var'])
def test_old_installation_requires_fresh_install(layout, old):
    (layout.root / old).mkdir(parents=True)
    with pytest.raises(ValueError, match='old installation'):
        layout.initialize()


def test_doctor_requires_matching_release_receipt(layout):
    layout.initialize()
    release = layout.releases / 'release-a'; release.mkdir(parents=True)
    layout.current.symlink_to('releases/release-a')
    layout.install_state.write_text(json.dumps({'current_release_id':'release-a', 'package_root':str(release)}))
    assert inspect_installation(layout.root)['ok']
    layout.install_state.write_text(json.dumps({'current_release_id':'release-b', 'package_root':str(release)}))
    assert not inspect_installation(layout.root)['ok']


def test_generated_inputs_refresh_but_credentials_are_not_overwritten(layout):
    layout.initialize()
    config = layout.configuration
    config.update(models={'providers': {'test': {'apiKey': 'credential:provider_key'}}},
                  execution={'default_target':'local', 'targets': {'local': {'type':'local', 'driver':'systemd'}}},
                  notifications={'email': {'enabled':True, 'provider':'smtp', 'preset':'custom', 'host':'smtp.example.test',
                      'username':'sender@example.test', 'recipient':'recipient@example.test', 'password':'credential:smtp'}})
    original = {'models': {'test': {'type':'oauth', 'access':'refreshed-fake-token'}},
                'secrets': {'provider_key':'fake-key', 'smtp':'fake-password'}}
    layout.credentials.write_text(json.dumps(original))
    layout.materialize()
    assert json.loads((layout.pi_config/'models.json').read_text())['providers']['test']['apiKey'] == 'fake-key'
    assert not (layout.pi_config/'auth.json').exists()
    assert json.loads(layout.credentials.read_text()) == original
    assert 'fake-password' not in layout.email_config.read_text()
    assert (layout.generated/'secrets/smtp-password').read_text().strip() == 'fake-password'
    config.update(models={'providers': {}})
    layout.materialize()
    assert json.loads((layout.pi_config/'models.json').read_text()) == {'providers': {}}
    assert json.loads(layout.credentials.read_text()) == original


def test_changed_state_root_cannot_redirect_uninstall(layout):
    layout.initialize()
    document = layout.configuration.read()
    document['paths']['state_root'] = str(layout.state.parent/'other-state')
    layout.configuration.write(document)
    with pytest.raises(ValueError, match='ownership record'):
        paths(layout.root)


def test_configuration_cannot_select_another_installation(layout):
    layout.initialize()
    with pytest.raises(ValueError, match='ownership record'):
        paths(layout.root, config_file=layout.config/'other.toml')


def test_configured_data_alias_is_normalized(layout):
    alias = layout.workspace_root.parent/'DATA'
    target = layout.workspace_root.parent/'shared'; target.mkdir()
    alias.symlink_to(target, target_is_directory=True)
    document = layout.configuration.read()
    document['paths']['workspace_root'] = str(alias/'workspaces')
    layout.configuration.write(document)
    assert paths(layout.root).workspace_root == target/'workspaces'


@pytest.mark.parametrize('store', ['/', 'relative'])
def test_environment_store_cannot_be_a_broad_or_relative_path(layout, monkeypatch, store):
    monkeypatch.setenv('CORAGENT_HOST_ENV_ROOT', store)
    with pytest.raises(ValueError, match='Host environment store'):
        layout.initialize()


def test_root_overlap_is_rejected(layout):
    document = layout.configuration.read()
    document['paths']['state_root'] = str(layout.root/'state')
    layout.configuration.write(document)
    with pytest.raises(ValueError, match='separate'):
        paths(layout.root)


def test_toml_encoder_handles_model_arrays_and_quoted_provider_names():
    import tomllib
    value = {'models': {'providers': {'test.provider': {'models': [
        {'id':'test', 'input':['text'], 'cost': {'input': 0.1, 'output':0}}]}}}}
    assert tomllib.loads(toml_text(value)) == value


def test_unsupported_model_thinking_levels_survive_configuration_and_projection(layout):
    import copy
    import tomllib
    models = {'providers': {'test': {'models': [{
        'id': 'test', 'reasoning': True,
        'thinkingLevelMap': {'off': None, 'minimal': None, 'high': 'high'},
        'compat': {'supportsDeveloperRole': False}}]}}}
    original = copy.deepcopy(models)
    layout.configuration.update(models=models)
    stored = tomllib.loads(layout.config_file.read_text())
    assert stored['models']['providers']['test']['models'][0]['thinkingLevelMap']['off'] is False
    assert layout.configuration.read()['models'] == original
    assert models == original
    layout.initialize().materialize()
    assert json.loads((layout.pi_config / 'models.json').read_text()) == original


def test_install_preview_uses_one_config_without_writing_runtime_files(layout, capsys):
    from scripts.install_wizard import parse_args, show_dry_run
    layout.configuration.update(execution={'default_target': 'local', 'targets': {
        'local': {'type':'local', 'driver':'process', 'bindings':{}}}},
        web={'enabled':False}, notifications={'email':{'enabled':False}})
    args = parse_args(['--config', str(layout.config_file), '--dry-run', '--service-scope', 'none'])
    show_dry_run(args)
    result = json.loads(capsys.readouterr().out)['plan']
    assert result['config'] == str(layout.config_file)
    assert result['install_root'] == str(layout.root)
    assert result['scientific_execution']['environments'] == []
    assert not layout.root.exists()
    assert not layout.state.exists()


def test_generated_state_cannot_escape_through_internal_symlink(layout):
    outside = layout.state.parent/'outside'; outside.mkdir()
    layout.state.mkdir()
    (layout.state/'pi').symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match='symlink'):
        layout.initialize()
    assert not list(outside.iterdir())


def test_core_config_purge_preserves_sibling_files_and_cluster_software(layout):
    from scripts.uninstall import parse_args, uninstall
    layout.initialize()
    sibling = layout.config/'unrelated.txt'; sibling.write_text('keep')
    cluster = layout.root.parent/'cluster-software'; cluster.mkdir()
    evidence = cluster/'owned-by-cluster'; evidence.write_text('keep')
    args = parse_args(['--config', str(layout.config_file), '--service-scope', 'none',
                      '--purge-config', '--purge-runtime', '--non-interactive', '--yes'])
    uninstall(args)
    assert not layout.config_file.exists()
    assert not layout.credentials.exists()
    assert sibling.read_text() == 'keep'
    assert evidence.read_text() == 'keep'


def test_explicit_service_options_override_unified_config(layout):
    from scripts.install_wizard import parse_args
    layout.configuration.update(web={'enabled':True, 'host':'127.0.0.2', 'port':8767}, service={'scope':'user'})
    args = parse_args(['--config',str(layout.config_file),'--without-web','--web-host','127.0.0.3', '--service-scope','none'])
    assert args.with_web is False
    assert args.web_host == '127.0.0.3'
    assert args.web_port is None
    assert args.service_scope == 'none'


def test_disabled_notification_needs_no_recipient_or_credentials(layout, monkeypatch):
    from types import SimpleNamespace
    from research_agent.bootstrap.launcher import configure_notifications
    layout.initialize()
    layout.configuration.update(notifications={'email':{'enabled':False}})
    layout.materialize()
    monkeypatch.delenv('CORAGENT_NOTIFICATION_CONFIG', raising=False)
    configure_notifications(SimpleNamespace(notification_config_default=layout.email_config))
    import os
    assert os.environ['CORAGENT_NOTIFICATION_DISPLAY_TARGET'] == 'disabled'


def test_invalid_notification_configuration_is_rejected_before_install(layout):
    from scripts.install_wizard import parse_args
    layout.configuration.update(notifications={'email':{'enabled':'true'}})
    with pytest.raises(ValueError, match='boolean'):
        parse_args(['--config', str(layout.config_file), '--dry-run'])
    assert not layout.state.exists()


def test_install_prepare_preserves_live_component_inputs_until_cutover(layout):
    from types import SimpleNamespace
    from scripts._configuration import prepare
    layout.initialize()
    layout.job_config.write_text('live configuration')
    layout.configuration.update(execution={'default_target':'local', 'targets':{
        'local':{'type':'local', 'driver':'process'}}})
    prepare(SimpleNamespace(install_root=str(layout.root)))
    assert layout.job_config.read_text() == 'live configuration'


def test_uninstall_can_purge_configuration_with_missing_credentials(layout):
    from scripts.uninstall import parse_args, uninstall
    layout.initialize()
    layout.configuration.update(models={'providers':{'test':{'apiKey':'credential:missing'}}})
    args = parse_args(['--config',str(layout.config_file),'--service-scope','none',
                      '--purge-config','--non-interactive','--yes'])
    uninstall(args)
    assert not layout.config_file.exists()


@pytest.mark.parametrize('name', ['config', 'state', 'workspace_root'])
def test_runtime_store_cannot_overlap_operator_data(layout, monkeypatch, name):
    monkeypatch.setenv('CORAGENT_HOST_ENV_ROOT', str(getattr(layout, name)))
    with pytest.raises(ValueError, match='separate'):
        _ = layout.env_root


def test_installer_reads_email_from_main_config_without_generated_files(layout):
    from scripts.install_wizard import parse_args, _load_existing_email_defaults, validate_email_options
    layout.configuration.update(notifications={'email':{'provider':'smtp', 'preset':'custom',
        'host':'smtp.example.test', 'username':'sender@example.test', 'recipient':'recipient@example.test',
        'password':'credential:smtp'}})
    from research_agent.foundation.configuration import atomic_write
    atomic_write(layout.credentials, json.dumps({'models':{},'secrets':{'smtp':'fake-password'}}))
    args = parse_args(['--config',str(layout.config_file)])
    _load_existing_email_defaults(args, layout.root)
    validate_email_options(args)
    assert args.email_recipient == 'recipient@example.test'
    assert not layout.state.exists()
    layout.initialize().materialize()
    import tomllib
    assert tomllib.loads(layout.email_config.read_text())['notifications']['email']['enabled'] is True


def test_execution_import_preserves_unchanged_secret_references_and_accepts_replacements(layout):
    from scripts._configuration import publish
    from scripts.install_wizard import parse_args
    layout.initialize()
    layout.credentials.write_text(json.dumps({'models':{},'secrets':{'tri':'fake-original'}}))
    execution = {'default_target':'cluster', 'targets':{'cluster':{
        'driver':'external', 'transport':'local', 'handler_environment':{'TRI_AUTH_TOKEN':'credential:tri'}}}}
    layout.configuration.update(execution=execution)
    args = parse_args(['--config',str(layout.config_file),'--without-web','--service-scope','none'])
    layout.materialize()
    publish(args)
    value = layout.configuration.read()['execution']['targets']['cluster']['handler_environment']
    assert value['TRI_AUTH_TOKEN'] == 'credential:tri'
    execution['targets']['cluster']['handler_environment']['TRI_AUTH_TOKEN'] = 'fake-replacement'
    layout.job_config.write_text(toml_text({'execution':execution}))
    publish(args)
    value = layout.configuration.read()['execution']['targets']['cluster']['handler_environment']
    assert layout.configuration.resolve_credentials(value)['TRI_AUTH_TOKEN'] == 'fake-replacement'
