"""Real user units exercise Job ownership, credentials and resource limits."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid

import pytest

from research_agent.jobs import qrun


def manager_environment():
    runtime = f"/run/user/{os.getuid()}"
    return {**os.environ, "XDG_RUNTIME_DIR": runtime, "DBUS_SESSION_BUS_ADDRESS": "unix:path=" + runtime + "/bus"}


def manager(*args, check=False):
    return subprocess.run(["systemctl", "--user", *args], env=manager_environment(),
                          capture_output=True, text=True, check=check, timeout=10)


def wait_file(path):
    for _ in range(200):
        if path.is_file():
            return
        time.sleep(.02)
    raise AssertionError("missing fixture result: " + str(path))


class RegisteredQrunSystemd(qrun.Systemd):
    """Route launches through the test runner's network isolation and guardian."""
    def command(self, argv):
        if argv[0] == 'systemd-run':
            boundary = argv.index('--')
            argv = [*argv[:boundary], '--property=ReadWritePaths=' + str(self.root.parent), *argv[boundary:]]
            return subprocess.run(argv, env=manager_environment(), capture_output=True, text=True, timeout=15)
        return super().command(argv)


def test_qrun_real_systemd_queue_recovers_and_enforces_limits(tmp_path):
    root, work = tmp_path / 'qrun', tmp_path / 'work'
    qrun.initialize(root, 1, 256, [str(work)])
    runtime = RegisteredQrunSystemd(root)
    queue = qrun.Queue(root, runtime=runtime)
    requests = []
    try:
        for index, script in enumerate((
            'echo captured; echo warning >&2; touch started; while [ ! -f release ]; do sleep 0.05; done; echo first > output',
            'echo second > output')):
            directory = work / str(index)
            directory.mkdir()
            (directory / 'run.sh').write_text(script)
            req = {'schema_version': qrun.PROTOCOL, 'action': 'submit', 'request_id': uuid.uuid4().hex,
                'job_id': 'job_' + str(index + 1), 'cwd': str(directory), 'script': str(directory / 'run.sh'),
                'resources': {'cpus': 1, 'memory_mb': 128}, 'timeout_seconds': 20}
            queue.handle(req)
            requests.append(req)
        queue.tick()
        wait_file(work / '0/started')
        first = queue.rows()[0]
        wait_file(queue.directory(first) / 'usage.json')
        usage = queue.view().usage(first)
        assert usage['source'] == 'cgroup-v2' and not usage['stale']
        assert usage['memory_mb'] > 0 and usage['cpu_seconds'] > 0
        assert queue.view().query({'action': 'logs', 'identifier': 1})['text'] == 'captured\n'
        assert queue.view().query({'action': 'logs', 'identifier': 1, 'stream': 'stderr'})['text'] == 'warning\n'
        assert queue.rows()[1]['state'] == 'queued'
        assert manager('show', '-p', 'MemoryMax', '--value', first['unit'], check=True).stdout.strip() == str(128 * 1024 * 1024)
        assert manager('show', '-p', 'CPUQuotaPerSecUSec', '--value', first['unit'], check=True).stdout.strip() == '1s'
        queue.close()
        queue = qrun.Queue(root, runtime=runtime)
        queue.tick()
        assert queue.rows()[0]['state'] == 'running'
        (work / '0/release').touch()
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            queue.tick()
            if all(job['state'] in qrun.TERMINAL for job in queue.rows()):
                break
            time.sleep(.05)
        assert [job['state'] for job in queue.rows()] == ['succeeded', 'succeeded']
        assert (work / '1/output').read_text().strip() == 'second'
    finally:
        jobs = queue.rows()
        queue.close()
        for job in jobs:
            runtime.cleanup(job)
            assert manager('show', '-p', 'LoadState', '--value', job['unit']).stdout.strip() == 'not-found'


def test_qrun_real_systemd_cancel_kills_detached_descendants(tmp_path):
    root, work = tmp_path / 'qrun', tmp_path / 'work'
    qrun.initialize(root, 1, 256, [str(work)])
    runtime = RegisteredQrunSystemd(root)
    queue = qrun.Queue(root, runtime=runtime)
    script = work / 'run.sh'
    script.write_text("setsid sh -c 'touch child-started; sleep 60' &\ntouch started\nwait\n")
    request = {'schema_version': qrun.PROTOCOL, 'action': 'submit', 'request_id': uuid.uuid4().hex,
        'job_id': 'job_1', 'cwd': str(work), 'script': str(script),
        'resources': {'cpus': 1, 'memory_mb': 128}, 'timeout_seconds': 20}
    try:
        queue.handle(request)
        queue.tick()
        wait_file(work / 'child-started')
        queue.handle({**request, 'action': 'cancel'})
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            queue.tick()
            if queue.rows()[0]['state'] in qrun.TERMINAL:
                break
            time.sleep(.05)
        assert queue.rows()[0]['state'] == 'cancelled'
    finally:
        jobs = queue.rows()
        queue.close()
        for job in jobs:
            runtime.cleanup(job)
            assert manager('show', '-p', 'LoadState', '--value', job['unit']).stdout.strip() == 'not-found'


def test_qrun_job_survives_its_controller_unit_and_scrubs_credentials(tmp_path, monkeypatch):
    monkeypatch.setenv('FIXTURE_PROVIDER_CREDENTIAL', 'must-not-enter-job')
    root, work = tmp_path / 'queue', tmp_path / 'work'
    qrun.initialize(root, 1, 256, [str(work)])
    (work / 'run.sh').write_text(
        'test -z "${FIXTURE_PROVIDER_CREDENTIAL:-}" || exit 99\n'
        'touch started\nwhile [ ! -f release ]; do sleep 0.05; done\necho survived > output\n')
    request = {'schema_version': qrun.PROTOCOL, 'action': 'submit', 'request_id': uuid.uuid4().hex,
               'job_id': 'job_1', 'cwd': str(work), 'script': str(work / 'run.sh'),
               'resources': {'cpus': 1, 'memory_mb': 128}, 'timeout_seconds': 20}
    parent = 'coragent-test-host-' + uuid.uuid4().hex + '.service'
    program = tmp_path / 'controller.py'
    program.write_text('import sys,time\nfrom pathlib import Path\nsys.path[:0]=' + repr(sys.path) + '\n'
        'from research_agent.jobs import qrun\n'
        'from tests.unit.test_local_job_isolation import RegisteredQrunSystemd\n'
        'root=Path(' + repr(str(root)) + ')\n'
        'queue=qrun.Queue(root,runtime=RegisteredQrunSystemd(root))\n'
        'queue.handle(' + repr(request) + ')\nqueue.tick()\ntime.sleep(60)\n')
    queue = None
    try:
        subprocess.run(['systemd-run', '--user', '--collect', '--quiet', '--unit=' + parent,
            '--property=Type=exec', '--property=ReadWritePaths=' + str(tmp_path),
            '--', sys.executable, '-B', str(program)], env=manager_environment(),
            capture_output=True, text=True, check=True, timeout=15)
        wait_file(work / 'started')
        manager('stop', parent, check=True)
        runtime = RegisteredQrunSystemd(root)
        queue = qrun.Queue(root, runtime=runtime)
        queue.tick()
        assert queue.rows()[0]['state'] == 'running'
        (work / 'release').touch()
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            queue.tick()
            if queue.rows()[0]['state'] in qrun.TERMINAL:
                break
            time.sleep(.05)
        assert queue.rows()[0]['state'] == 'succeeded'
        assert (work / 'output').read_text().strip() == 'survived'
    finally:
        manager('stop', parent)
        if queue is None:
            queue = qrun.Queue(root, runtime=RegisteredQrunSystemd(root))
        jobs = queue.rows()
        queue.close()
        for job in jobs:
            queue.runtime.cleanup(job)
            assert manager('show', '-p', 'LoadState', '--value', job['unit']).stdout.strip() == 'not-found'
        assert manager('show', '-p', 'LoadState', '--value', parent).stdout.strip() == 'not-found'
