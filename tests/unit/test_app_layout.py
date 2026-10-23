
from tests.support.platforms import execution_config
import json
from pathlib import Path
import pytest
from research_agent.bootstrap.layout import paths, inspect_installation
from research_agent.configuration.configuration import Configuration, toml_text


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
                  execution=execution_config('local', {'local': {'executor': 'qrun', 'transport': 'local', 'work_root': '/fixture/qrun/jobs'}}),
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
    document['paths']['state_root'] = str(layout.root/'releases/state')
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
    from coragent_packaging.installer.install_wizard import parse_args, show_dry_run
    layout.configuration.update(execution=execution_config('local', {
        'local': {'executor': 'qrun', 'bindings': {}, 'transport': 'local', 'work_root': '/fixture/qrun/jobs'}}),
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
    from coragent_packaging.installer.uninstall import parse_args, uninstall
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
    from coragent_packaging.installer.install_wizard import parse_args
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
    from coragent_packaging.installer.install_wizard import parse_args, show_dry_run
    layout.configuration.update(notifications={'email':{'enabled':'true'}})
    args = parse_args(['--config', str(layout.config_file), '--dry-run'])
    with pytest.raises(ValueError, match='boolean'):
        show_dry_run(args)
    assert not layout.state.exists()


def test_install_prepare_preserves_live_component_inputs_until_cutover(layout):
    from types import SimpleNamespace
    from coragent_packaging.installer._configuration import prepare
    layout.initialize()
    layout.job_config.write_text('live configuration')
    layout.configuration.update(execution=execution_config('local', {
        'local':{'executor': 'qrun', 'transport': 'local', 'work_root': '/fixture/qrun/jobs'}}))
    prepare(SimpleNamespace(install_root=str(layout.root)))
    assert layout.job_config.read_text() == 'live configuration'


def test_uninstall_can_purge_configuration_with_missing_credentials(layout):
    from coragent_packaging.installer.uninstall import parse_args, uninstall
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
    from coragent_packaging.installer.install_wizard import parse_args, _load_existing_email_defaults, validate_email_options
    layout.configuration.update(notifications={'email':{'provider':'smtp', 'preset':'custom',
        'host':'smtp.example.test', 'username':'sender@example.test', 'recipient':'recipient@example.test',
        'password':'credential:smtp'}})
    from research_agent.configuration.configuration import atomic_write
    atomic_write(layout.credentials, json.dumps({'models':{},'secrets':{'smtp':'fake-password'}}))
    args = parse_args(['--config',str(layout.config_file)])
    _load_existing_email_defaults(args, layout.root)
    validate_email_options(args)
    assert args.email_recipient == 'recipient@example.test'
    assert not layout.state.exists()
    layout.initialize().materialize()
    import tomllib
    assert tomllib.loads(layout.email_config.read_text())['notifications']['email']['enabled'] is True


def test_generated_edits_are_not_imported_and_explicit_candidates_preserve_secret_references(layout):
    from coragent_packaging.installer._configuration import publish
    from coragent_packaging.installer.install_wizard import parse_args
    layout.initialize()
    layout.credentials.write_text(json.dumps({'models':{},'secrets':{'tri':'fake-original'}}))
    execution = execution_config('cluster', {'cluster':{'executor': 'external', 'transport': 'local',
        'work_root': '/fixture/jobs', 'handler': ['/fixture/handler'],
        'handler_environment': {'TRI_AUTH_TOKEN': 'credential:tri'}}})
    layout.configuration.update(execution=execution)
    args = parse_args(['--config',str(layout.config_file),'--without-web','--service-scope','none'])
    layout.materialize()
    publish(args)
    value = layout.configuration.read()['execution']['platforms']['cluster']['schedulers']['main']['handler_environment']
    assert value['TRI_AUTH_TOKEN'] == 'credential:tri'
    execution['platforms']['cluster']['schedulers']['main']['handler_environment']['TRI_AUTH_TOKEN'] = 'fake-replacement'
    layout.job_config.write_text(toml_text({'execution':execution}))
    publish(args)
    value = layout.configuration.read()['execution']['platforms']['cluster']['schedulers']['main']['handler_environment']
    assert layout.configuration.resolve_credentials(value)['TRI_AUTH_TOKEN'] == 'fake-original'
    from coragent_packaging.installer._configuration import commit_sections
    commit_sections(layout.root, execution=execution).materialize(strict=True)
    value = layout.configuration.read()['execution']['platforms']['cluster']['schedulers']['main']['handler_environment']
    assert value['TRI_AUTH_TOKEN'].startswith('credential:')
    assert layout.configuration.resolve_credentials(value)['TRI_AUTH_TOKEN'] == 'fake-replacement'


def test_default_layout_keeps_mutable_data_beside_releases(tmp_path, monkeypatch):
    monkeypatch.delenv('CORAGENT_CONFIG', raising=False)
    root = tmp_path / 'application'
    layout = paths(root).initialize()
    assert layout.config_file == root / 'config/config.toml'
    assert layout.state == root / 'state'
    assert layout.generated == root / 'generated'
    assert layout.jobs == root / 'jobs'
    assert layout.backups == root / 'backups'
    assert paths(root).config_file == layout.config_file
    assert all(p.is_dir() for p in (layout.state, layout.generated, layout.jobs, layout.backups))


@pytest.mark.parametrize('name', ['config', 'state', 'generated', 'jobs', 'backups'])
def test_managed_data_directories_reject_symlinks(tmp_path, monkeypatch, name):
    monkeypatch.delenv('CORAGENT_CONFIG', raising=False)
    root = tmp_path / 'application'; root.mkdir()
    outside = tmp_path / 'outside'; outside.mkdir()
    (root / name).symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match='symlink'):
        paths(root).initialize()
    assert not list(outside.iterdir())


def test_default_uninstall_preserves_nested_operator_data(tmp_path, monkeypatch):
    from coragent_packaging.installer.uninstall import parse_args, uninstall
    monkeypatch.delenv('CORAGENT_CONFIG', raising=False)
    layout = paths(tmp_path / 'application').initialize()
    release = layout.releases / 'test'; release.mkdir(parents=True)
    saved = [layout.credentials, layout.jobs / 'result', layout.backups / 'saved-config', layout.state / 'qrun/queue.sqlite3']
    for p in saved[1:]:
        p.parent.mkdir(parents=True, exist_ok=True); p.write_text('preserve')
    original = {p: p.read_bytes() for p in saved}
    args = parse_args(['--install-root', str(layout.root), '--service-scope', 'none', '--non-interactive', '--yes'])
    uninstall(args)
    assert not release.exists()
    assert all(p.read_bytes() == data for p, data in original.items())
    assert layout.config_file.is_file()


def test_root_removal_requires_explicit_backup_purge(tmp_path, monkeypatch):
    from coragent_packaging.installer.uninstall import parse_args, uninstall
    monkeypatch.delenv('CORAGENT_CONFIG', raising=False)
    layout = paths(tmp_path / 'application').initialize()
    backup = layout.backups / 'original'; backup.write_text('keep')
    args = parse_args(['--install-root', str(layout.root), '--service-scope', 'none', '--non-interactive', '--yes',
        '--remove-root', '--purge-workspaces', '--purge-runtime', '--purge-config'])
    with pytest.raises(ValueError, match='purge-backups'):
        uninstall(args)
    assert backup.read_text() == 'keep'
    assert layout.config_file.is_file()


def test_invalid_optional_projection_does_not_block_core_or_reuse_old_secret(layout):
    layout.initialize()
    layout.configuration.update(notifications={'email': {'provider': 'smtp', 'preset': 'custom',
        'host': 'smtp.example.test', 'username': 'sender@example.test', 'recipient': 'recipient@example.test',
        'password': 'credential:missing'}})
    layout.email_config.write_text('obsolete email configuration')
    (layout.generated / 'secrets/smtp-password').write_text('obsolete test secret')
    (layout.generated / 'secrets/service.env').write_text('OLD_SMTP_PASSWORD="obsolete"\n')
    layout.materialize()
    assert not layout.email_config.exists()
    assert not (layout.generated / 'secrets/smtp-password').exists()
    assert not (layout.generated / 'secrets/service.env').exists()
    status = json.loads((layout.generated / 'configuration-status.json').read_text())
    assert status['email']['state'] == 'invalid'
    assert status['execution']['state'] == 'not_configured'
    assert paths(layout.root).workspace_root == layout.workspace_root
    with pytest.raises(ValueError, match='email configuration is invalid'):
        layout.materialize(strict=True)


def test_resolver_projection_uses_domain_validation_and_recovers_after_repair(layout):
    from research_agent.bootstrap.name_resolver_config import parse_config
    layout.initialize()
    invalid = {'default_resolver': 'invalid-resolver'}
    layout.configuration.update(name_resolver=invalid)
    layout.resolver_config.write_text('obsolete resolver configuration')
    with pytest.raises(ValueError) as domain_error:
        parse_config(invalid)

    layout.materialize()

    assert not layout.resolver_config.exists()
    status_path = layout.generated / 'configuration-status.json'
    assert json.loads(status_path.read_text())['name_resolver']['state'] == 'invalid'
    with pytest.raises(ValueError, match=str(domain_error.value)):
        layout.materialize(strict=True)
    repaired = {'default_resolver': 'opsin', 'backends': {'opsin': {'cache': False}}}
    layout.configuration.update(name_resolver=repaired)
    layout.materialize(strict=True)
    import tomllib
    assert tomllib.loads(layout.resolver_config.read_text()) == repaired
    assert json.loads(status_path.read_text())['name_resolver']['state'] == 'configured'


@pytest.mark.parametrize('email', [None, {'enabled': False}, {
    'provider': 'smtp', 'preset': 'qq', 'username': 'sender@qq.com',
    'recipient': 'receiver@example.test', 'password_env': 'EXTERNAL_SMTP_PASSWORD'}])
def test_email_environment_is_external_and_never_restored_from_generated_capture(layout, email, monkeypatch):
    layout.initialize()
    if email is not None:
        layout.configuration.update(notifications={'email': email})
    obsolete = layout.generated / 'secrets/service.env'
    obsolete.write_text('EXTERNAL_SMTP_PASSWORD="obsolete"\n')
    monkeypatch.setenv('EXTERNAL_SMTP_PASSWORD', 'current-external-value')
    original = layout.credentials.read_bytes()

    layout.materialize(strict=True)

    assert not obsolete.exists()
    assert layout.credentials.read_bytes() == original
    assert not (layout.generated / 'secrets/smtp-password').exists()


def test_disposable_component_inputs_rebuild_without_changing_main_config(layout):
    layout.initialize()
    layout.configuration.update(execution=execution_config('local', {'local': {
        'executor': 'qrun', 'transport': 'local', 'work_root': '/fixture/qrun/jobs'}}))
    original = layout.config_file.read_bytes()
    layout.materialize(strict=True)
    expected = layout.job_config.read_bytes()
    layout.job_config.unlink()
    layout.materialize(strict=True)
    assert layout.job_config.read_bytes() == expected
    assert layout.config_file.read_bytes() == original
