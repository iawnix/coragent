from __future__ import annotations

from research_agent.bootstrap.layout import paths as app_paths

import json
import subprocess
from pathlib import Path

import pytest

from coragent_packaging.installer import uninstall as uninstaller
from coragent_packaging.installer.install_from_github import install_uninstaller
from coragent_packaging.installer.uninstall import uninstall


def _args(root: Path, **overrides: object):
    from research_agent.bootstrap.layout import paths
    paths(root).initialize()
    values = {
        "install_root": str(root),
        "service_scope": "none",
        "purge_workspaces": False,
        "purge_config": False,
        "purge_runtime": False,
        "remove_root": False,
        "purge_all": False,
        "non_interactive": True,
        "yes": True,
        "json": False,
    }
    values.update(overrides)
    return type("Options", (), values)()


def test_uninstall_preserves_workspace_and_config_by_default(tmp_path: Path) -> None:
    root = tmp_path / "install"
    from research_agent.bootstrap.layout import paths
    paths(root).initialize()
    (root / "workspaces/ts_001").mkdir(parents=True)
    web_token = app_paths(root).generated / 'web/auth.token'
    web_token.parent.mkdir(parents=True, exist_ok=True)
    web_token.write_text("w" * 43)
    phone_connection = app_paths(root).state / 'host/link.json'
    phone_connection.parent.mkdir(parents=True, exist_ok=True)
    phone_connection.write_text('{"schema_version":"coragent-link/1"}\n', encoding="utf-8")
    download = root / "downloads/client.apk"
    download.parent.mkdir()
    download.write_bytes(b"apk")
    (root / "coragent").symlink_to("./current")

    result = uninstall(_args(root))

    assert result["ok"] is True
    assert (root / "workspaces/ts_001").is_dir()
    assert web_token.read_text() == "w" * 43
    assert phone_connection.is_file()
    assert download.read_bytes() == b"apk"
    assert not (root / "releases").exists()


@pytest.mark.parametrize("dangling", [False, True])
def test_uninstall_removes_owned_stable_links(tmp_path: Path, dangling: bool) -> None:
    root = tmp_path / "install"
    args = _args(root)
    if not dangling: (root / "releases/old/agent").mkdir(parents=True)
    (root / "current").symlink_to("releases/old")
    (root / "coragent").symlink_to("current/agent/coragent")
    uninstall(args)
    assert not (root / "current").is_symlink()
    assert not (root / "coragent").is_symlink()
    assert root.is_dir()


def test_uninstall_does_not_follow_external_bin_directory(tmp_path: Path) -> None:
    root = tmp_path / "install"
    root.mkdir()
    external = tmp_path / "external"
    external.mkdir()
    launcher = external / "coragent"
    launcher.symlink_to(root / "./current/agent/coragent")
    (root / "bin").symlink_to(external)

    uninstall(_args(root))

    assert launcher.is_symlink()


def test_uninstall_uses_configured_external_workspace_root(tmp_path: Path) -> None:
    root = tmp_path / "install"
    from research_agent.bootstrap.layout import paths
    paths(root).initialize()
    workspace_root = tmp_path / "research"
    (workspace_root / "reaction-a").mkdir(parents=True)
    paths(root).update_config(workspace_root=str(workspace_root))

    result = uninstall(_args(root, purge_workspaces=True))

    assert result["workspace_root"] == str(workspace_root)
    assert not workspace_root.exists()


def test_uninstall_refuses_to_purge_an_installation_ancestor(tmp_path: Path) -> None:
    root = tmp_path / "install"
    from research_agent.bootstrap.layout import paths
    paths(root).initialize()
    paths(root).update_config(workspace_root=str(tmp_path))

    with pytest.raises(ValueError, match="separate|broad workspace root"):
        uninstall(_args(root, purge_workspaces=True))

    assert root.is_dir()


def test_interactive_defaults_run_safe_uninstall_and_preserve_data(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "install"
    from research_agent.bootstrap.layout import paths
    paths(root).initialize()
    workspace = root / "workspaces/ts_001"
    workspace.mkdir(parents=True)
    config = app_paths(root).job_config
    config.write_text("[remote]\n", encoding="utf-8")
    runtime = paths(root).env_root / "base/test"
    runtime.mkdir(parents=True)
    (root / "coragent").symlink_to("./current")
    monkeypatch.setattr(uninstaller.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(uninstaller.sys.stdout, "isatty", lambda: True)
    replies = iter(["", "", "", ""])
    monkeypatch.setattr("builtins.input", lambda _: next(replies))

    result = uninstall(_args(root, non_interactive=False, yes=False))

    assert result["ok"] is True
    assert workspace.is_dir()
    assert config.is_file()
    assert runtime.is_dir()
    assert root.is_dir()
    assert not (root / "releases").exists()


def test_uninstall_removes_immutable_release_without_following_links(tmp_path: Path) -> None:
    root = tmp_path / "install"
    release = root / "./releases/release-id"
    nested = release / "agent/packages"
    nested.mkdir(parents=True)
    artifact = nested / "package.json"
    artifact.write_text("{}\n", encoding="utf-8")
    external = tmp_path / "external"
    external.mkdir()
    preserved = external / "keep.txt"
    preserved.write_text("keep\n", encoding="utf-8")
    (release / "external").symlink_to(external, target_is_directory=True)
    artifact.chmod(0o400)
    for directory in (nested, nested.parent, release):
        directory.chmod(0o500)

    result = uninstall(_args(root))

    assert result["ok"] is True
    assert not (root / "releases").exists()
    assert preserved.read_text(encoding="utf-8") == "keep\n"


def test_uninstall_purge_removes_the_dedicated_installation_root(tmp_path: Path) -> None:
    root = tmp_path / "install"
    from research_agent.bootstrap.layout import paths
    paths(root).initialize()
    (root / "workspaces/ts_001").mkdir(parents=True)
    (root / "coragent").symlink_to("./current")
    install_uninstaller(root, Path(__file__).resolve().parents[2])
    download = root / "downloads/client.apk"
    download.parent.mkdir()
    download.write_bytes(b"apk")

    result = uninstall(_args(root, purge_workspaces=True, purge_config=True, purge_runtime=True, remove_root=True))

    assert result["ok"] is True
    assert not root.exists()


@pytest.mark.parametrize("layout", ["libexec", "runtimes", "upgrade"])
def test_installed_uninstaller_runs_with_its_private_ui_module(tmp_path: Path, layout: str) -> None:
    root = tmp_path / "install"
    from research_agent.bootstrap.layout import paths
    paths(root).initialize()
    install_uninstaller(root, Path(__file__).resolve().parents[2])
    if layout != "libexec":
        (root / "libexec/maintenance").rename(root / "runtimes/maintenance")
    if layout == "upgrade":
        # An older entrypoint only knows the legacy location.
        entrypoint = root / "uninstall.sh"
        entrypoint.write_text(entrypoint.read_text().replace(
            '  "${SCRIPT_ROOT}/libexec/maintenance/packaging/coragent_packaging/installer/installer.py" \\\n', ""))
        install_uninstaller(root, Path(__file__).resolve().parents[2])
        assert not (root / "runtimes/maintenance").exists()

    completed = subprocess.run(
        [
            str(root / "uninstall.sh"),
            "--install-root",
            str(root),
            "--service-scope",
            "none",
            "--non-interactive",
            "--yes",
            "--json",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout)["ok"] is True
    bundle = "runtimes" if layout == "runtimes" else "libexec"
    assert (root / bundle / "maintenance/packaging/coragent_packaging/installer/_terminal_ui.py").is_file()


def test_failed_maintenance_migration_preserves_legacy_uninstaller(tmp_path: Path, monkeypatch) -> None:
    from coragent_packaging.installer import install_from_github

    root = tmp_path / "install"
    source = Path(__file__).resolve().parents[2]
    install_uninstaller(root, source)
    (root / "libexec/maintenance").rename(root / "runtimes/maintenance")
    entrypoint = root / "uninstall.sh"
    old_script = entrypoint.read_text().replace(
        '  "${SCRIPT_ROOT}/libexec/maintenance/packaging/coragent_packaging/installer/installer.py" \\\n', "")
    entrypoint.write_text(old_script)
    copyfile = install_from_github.shutil.copyfile

    def fail_copy(src, dst):
        if src.name == "_terminal_ui.py":
            raise OSError("simulated incomplete maintenance copy")
        return copyfile(src, dst)

    monkeypatch.setattr(install_from_github.shutil, "copyfile", fail_copy)
    with pytest.raises(OSError, match="incomplete maintenance copy"):
        install_uninstaller(root, source)
    assert entrypoint.read_text() == old_script
    completed = subprocess.run([str(entrypoint), "--help"], capture_output=True, text=True, timeout=10)
    assert completed.returncode == 0, completed.stderr
    assert "--purge-config" in completed.stdout


def test_uninstall_purge_config_removes_both_maintenance_locations(tmp_path: Path) -> None:
    root = tmp_path / "install"
    install_uninstaller(root, Path(__file__).resolve().parents[2])
    legacy = root / "runtimes/maintenance"
    legacy.mkdir()
    (legacy / "old.py").write_text("# old recovery bundle\n")
    result = uninstall(_args(root, purge_config=True))
    assert result["ok"] is True
    assert not (root / "libexec/maintenance").exists()
    assert not legacy.exists()
    assert not (root / "uninstall.sh").exists()


def test_uninstall_rejects_external_libexec_directory(tmp_path: Path) -> None:
    root = tmp_path / "install"
    args = _args(root, purge_config=True)
    external = tmp_path / "external"
    (external / "maintenance").mkdir(parents=True)
    kept = external / "maintenance/keep.py"
    kept.write_text("# external code\n")
    (root / "libexec").symlink_to(external, target_is_directory=True)
    with pytest.raises(ValueError, match="symbolic link"):
        uninstall(args)
    assert kept.is_file()


@pytest.mark.parametrize("layout", ["libexec", "runtimes"])
def test_interactive_uninstaller_infers_root_from_maintenance_bundle(tmp_path: Path, monkeypatch, layout: str) -> None:
    root = tmp_path / "custom-install"
    monkeypatch.setattr(uninstaller, "__file__", str(
        root / layout / "maintenance/packaging/coragent_packaging/installer/uninstall.py"))
    monkeypatch.setattr(uninstaller.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(uninstaller.sys.stdout, "isatty", lambda: True)
    monkeypatch.setattr(uninstaller, "ask", lambda _prompt, default: default)

    def check_root(args, **kwargs):
        assert args.install_root == str(root)
        return {"ok": True}

    monkeypatch.setattr(uninstaller, "uninstall", check_root)
    assert uninstaller.main(["--json"]) == 0


@pytest.mark.parametrize("selection", ["root", "config", "environment"])
def test_maintenance_location_does_not_override_explicit_installation(tmp_path: Path, monkeypatch, selection: str) -> None:
    bundled = tmp_path / "bundle/libexec/maintenance/packaging/coragent_packaging/installer/uninstall.py"
    monkeypatch.setattr(uninstaller, "__file__", str(bundled))
    selected = tmp_path / "selected"
    layout = app_paths(selected).initialize()
    if selection == "root":
        argv = ["--install-root", str(selected)]
    elif selection == "config":
        argv = ["--config", str(layout.config_file)]
    else:
        monkeypatch.setenv("CORAGENT_CONFIG", str(layout.config_file))
        argv = []
    assert uninstaller.parse_args(argv).install_root == str(selected)


def test_installed_uninstaller_removes_an_immutable_partial_release(tmp_path: Path) -> None:
    root = tmp_path / "install"
    install_uninstaller(root, Path(__file__).resolve().parents[2])
    release = root / "./releases/partial-release/agent"
    release.mkdir(parents=True)
    artifact = release / "package.json"
    artifact.write_text("{}\n", encoding="utf-8")
    artifact.chmod(0o400)
    for directory in (release, release.parent):
        directory.chmod(0o500)

    completed = subprocess.run(
        [
            str(root / "uninstall.sh"),
            "--install-root", str(root),
            "--service-scope", "none",
            "--purge-all",
            "--non-interactive",
            "--yes",
            "--json",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout)["ok"] is True
    assert not root.exists()


def test_uninstall_rejects_a_source_checkout_without_installation_metadata(tmp_path: Path) -> None:
    root = tmp_path / "source"
    root.mkdir()
    (root / "coragent").write_text("#!/bin/sh\n")

    with pytest.raises(ValueError, match="trusted CoRAgent installation metadata"):
        uninstaller.validate_root(root)

    assert (root / "coragent").is_file()


def test_uninstall_rejects_non_object_package_state(tmp_path: Path) -> None:
    root = tmp_path / "install"
    state = app_paths(root).install_state
    state.parent.mkdir(parents=True)
    state.write_text("[]\n")

    with pytest.raises(ValueError, match="must contain a JSON object"):
        uninstaller.validate_root(root)


def test_valid_ownership_marker_allows_cleanup_of_damaged_package_state(tmp_path: Path) -> None:
    root = tmp_path / "install"
    state = app_paths(root).install_state
    state.parent.mkdir(parents=True)
    state.write_text("[]\n")
    args = _args(root)

    result = uninstall(args)

    assert result["ok"] is True
    assert not (root / "releases").exists()
    assert (app_paths(root).marker).is_file()


def test_purge_config_removes_local_uninstaller_and_ownership_marker(tmp_path: Path) -> None:
    root = tmp_path / "install"
    from research_agent.bootstrap.layout import paths
    paths(root).initialize()
    install_uninstaller(root, Path(__file__).resolve().parents[2])
    web_token = app_paths(root).generated / 'web/auth.token'
    web_token.parent.mkdir(parents=True, exist_ok=True)
    web_token.write_text("w" * 43)
    resolver_config = app_paths(root).resolver_config
    resolver_config.write_text("default_resolver = 'pubchem'\n", encoding="utf-8")

    result = uninstall(_args(root, purge_config=True))

    assert result["ok"] is True
    assert not (root / "uninstall.sh").exists()
    assert not (app_paths(root).generated).exists()
    assert not web_token.exists()
    assert not resolver_config.exists()


def test_purge_removes_unified_host_sessions_and_credentials(tmp_path: Path) -> None:
    root = tmp_path / "install"
    from research_agent.bootstrap.layout import paths
    paths(root).initialize()
    host_session = app_paths(root).state / 'pi/sessions/workspace/session/session.sqlite'
    host_session.parent.mkdir(parents=True)
    host_session.write_text("session\n", encoding="utf-8")
    (app_paths(root).state / 'host/server-id').write_text("server\n", encoding="utf-8")
    phone_connection = app_paths(root).state / 'host/link.json'
    phone_connection.write_text("{}\n", encoding="utf-8")
    host_token = app_paths(root).state / 'host/host.token'
    host_token.write_text("secret\n", encoding="utf-8")
    (app_paths(root).pi_config / 'auth.json').parent.mkdir(parents=True, exist_ok=True)
    (app_paths(root).pi_config / 'auth.json').write_text("{}\n", encoding="utf-8")
    (app_paths(root).generated / 'secrets/smtp-password').parent.mkdir(parents=True, exist_ok=True)
    (app_paths(root).generated / 'secrets/smtp-password').write_text("secret\n", encoding="utf-8")

    result = uninstall(_args(root, purge_workspaces=True, purge_config=True))

    assert result["ok"] is True
    assert not host_session.exists()
    assert not (app_paths(root).state / 'host/server-id').exists()
    assert not phone_connection.exists()
    assert not host_token.exists()
    assert not (app_paths(root).pi_config).exists()
    assert not (app_paths(root).generated / 'secrets').exists()


def test_installed_uninstaller_removes_owned_relay_without_source_tree(tmp_path: Path) -> None:
    root = tmp_path / 'installation'
    from research_agent.bootstrap.layout import paths
    paths(root).initialize()
    install_uninstaller(root, Path(__file__).resolve().parents[2])
    relay_root = root / 'runtimes/link-relay'
    (relay_root / 'releases').mkdir(parents=True)
    state = app_paths(root).state / 'link-relay'
    state.mkdir(parents=True)
    (state / 'relay.db').write_bytes(b'preserved state')
    (app_paths(root).generated / 'link-relay.json').write_text(json.dumps({
        'schema': 'coragent-install-link-relay/1', 'owned': True, 'install_root': str(root),
        'relay_install_root': str(relay_root), 'state_dir': str(state), 'service_scope': 'none',
    }))
    completed = subprocess.run([
        str(root / 'uninstall.sh'), '--install-root', str(root), '--service-scope', 'none',
        '--non-interactive', '--yes', '--json',
    ], cwd=tmp_path, text=True, capture_output=True, check=False)
    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout)
    assert result['link_relay']['ok'] is True
    assert not relay_root.exists()
    assert (state / 'relay.db').read_bytes() == b'preserved state'


@pytest.mark.parametrize('purge', [False, True])
def test_recovery_uninstaller_removes_qrun_without_application_runtime(tmp_path, monkeypatch, purge):
    from coragent_packaging.installer import _qrun_install
    from research_agent.jobs import qrun
    root = tmp_path / 'installation'
    options = _args(root)
    monkeypatch.setenv('XDG_CONFIG_HOME', str(tmp_path / 'unit-config'))
    install_uninstaller(root, Path(__file__).resolve().parents[2])
    pool = {'route': {'transport': 'local'}, 'targets': ['local'],
            'state_dir': str(tmp_path / 'queue'), 'cpus': 2, 'memory_mb': 1024,
            'work_roots': [str(tmp_path / 'calculations')]}
    record = qrun.maintain(Path(pool['state_dir']), {'operation': 'install',
        'owner': _qrun_install.owner(root), 'start': False,
        **{k: pool[k] for k in ('cpus', 'memory_mb', 'work_roots')}})
    qrun.maintain(Path(pool['state_dir']), {'operation': 'commit', 'owner': _qrun_install.owner(root)})
    registry = _qrun_install.registry(root)
    registry['pools'] = [{**pool, 'handler': record['handler'], 'unit': record['unit']}]
    _qrun_install.save(root, registry)
    command = [str(root / 'uninstall.sh'), '--install-root', str(root), '--service-scope', 'none',
               '--non-interactive', '--yes', '--json']
    if purge:
        command.append('--purge-qrun-state')
    completed = subprocess.run(command, cwd=tmp_path, text=True, capture_output=True)
    assert completed.returncode == 0
    assert json.loads(completed.stdout)['qrun'][0]['removed']
    assert not Path(record['unit_path']).exists()
    assert Path(pool['state_dir']).exists() != purge
    assert Path(pool['work_roots'][0]).exists()


def test_qrun_removal_failure_prevents_application_deletion(tmp_path, monkeypatch):
    root = tmp_path / 'installation'
    options = _args(root)
    release = root / 'releases/fixture'
    release.mkdir(parents=True)

    def refused(*_args):
        raise ValueError('fixture unfinished jobs')

    monkeypatch.setattr(uninstaller._qrun_install, 'remove', refused)
    monkeypatch.setattr(uninstaller, 'stop_services', lambda *_a: pytest.fail('Qrun refusal must precede app changes'))
    with pytest.raises(ValueError, match='unfinished jobs'):
        uninstall(options)
    assert release.exists()
