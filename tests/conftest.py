"""Per-case isolation and local failure evidence retention."""
from __future__ import annotations
import os
import hashlib
import shutil
from pathlib import Path
import pytest


@pytest.fixture
def tmp_path(request, tmp_path_factory):
    # Long test names must not consume the Unix-domain socket path budget.
    case='c'+hashlib.sha256(request.node.nodeid.encode()).hexdigest()[:10]
    return tmp_path_factory.mktemp(case)


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    result = yield
    setattr(item, 'report_' + result.get_result().when, result.get_result())


@pytest.fixture(autouse=True)
def restore_tmp_path_permissions(tmp_path: Path, request):
    yield
    for current, directories, files in os.walk(tmp_path, topdown=False):
        for name in files:
            path = Path(current) / name
            if not path.is_symlink(): path.chmod(0o600)
        for name in directories:
            path = Path(current) / name
            if not path.is_symlink(): path.chmod(0o700)
    if tmp_path.exists() and not tmp_path.is_symlink():
        tmp_path.chmod(0o700)
        reports = [getattr(request.node, 'report_' + phase, None) for phase in ('setup','call')]
        if all(report is not None and report.passed for report in reports):
            shutil.rmtree(tmp_path)


@pytest.fixture(autouse=True)
def isolate_installation_environment_paths(tmp_path, monkeypatch):
    monkeypatch.setenv('HOME', str(tmp_path.parent / ('home-' + tmp_path.name)))
    monkeypatch.delenv('CORAGENT_CONFIG', raising=False)
    monkeypatch.setenv('CORAGENT_HOST_ENV_ROOT', str(tmp_path / 'host-envs'))
    monkeypatch.setenv('XDG_RUNTIME_DIR', str(tmp_path / 'xdg'))
    previous = dict(os.environ)
    yield
    os.environ.clear()
    os.environ.update(previous)


@pytest.fixture(autouse=True)
def qrun_execution_fixture(tmp_path, tmp_path_factory, monkeypatch, isolate_installation_environment_paths,
                           restore_tmp_path_permissions):
    """Explicit /fixture targets use a real Qrun daemon with a test runtime."""
    import json
    import subprocess
    import sys
    import time
    import threading
    from research_agent.jobs import qrun
    from research_agent.jobs.external import ExternalJobPlatform

    original = ExternalJobPlatform.__init__
    process = None
    root = None
    startup = threading.Lock()

    def configure(self, config, **kwargs):
        nonlocal process, root
        if config.get('executor') == 'qrun' and config.get('work_root') == '/fixture/qrun/jobs':
            with startup:
                if process is None:
                    root = tmp_path_factory.mktemp('qrun-pool')
                    root.chmod(0o700)
                    monkeypatch.setenv('XDG_RUNTIME_DIR', os.environ['CORAGENT_TEST_SOCKET_ROOT'])
                    program = ('import sys; sys.path[:0]=' + repr(sys.path) + '; '
                               'from pathlib import Path; from tests.support.qrun_runtime import serve; '
                               'serve(Path(' + repr(str(root)) + '), Path(' + repr(str(tmp_path)) + '))')
                    process = subprocess.Popen([sys.executable, '-B', '-c', program])
                    deadline = time.monotonic() + 5
                    while not qrun.socket_path(root).exists() and time.monotonic() < deadline:
                        assert process.poll() is None, 'fixture queue stopped before readiness'
                        time.sleep(.01)
                    assert qrun.socket_path(root).exists()
            config = {**config, 'work_root': str(tmp_path), 'file_mode': 'shared',
                      'handler': [sys.executable, '-B', qrun.__file__, '--state-dir', str(root), 'handler'],
                      'handler_environment': {'XDG_RUNTIME_DIR': os.environ['CORAGENT_TEST_SOCKET_ROOT']}}
        original(self, config, **kwargs)

    monkeypatch.setattr(ExternalJobPlatform, '__init__', configure)
    try:
        yield
    finally:
        if process is not None:
            try:
                for path in (root / 'jobs').glob('*/run.json'):
                    request = json.loads(path.read_text())
                    qrun.client(root, {**request, 'action': 'cancel'})
                deadline = time.monotonic() + 10
                while time.monotonic() < deadline:
                    requests = [json.loads(path.read_text()) for path in (root / 'jobs').glob('*/run.json')]
                    if all(qrun.client(root, {**req, 'action': 'status'})['state'] in qrun.TERMINAL for req in requests):
                        break
                    time.sleep(.02)
                else:
                    raise AssertionError('fixture queue jobs did not stop')
            finally:
                process.terminate()
                process.wait(timeout=5)
                assert not qrun.socket_path(root).exists()
