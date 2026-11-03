#!/usr/bin/env python3
"""Qrun: a host-local durable FIFO queue for modern and older Linux hosts.

This stdlib-only file can be installed on an execution host without CoRAgent.
The same JSON handler is called directly or over SSH. Only the single queue
daemon writes the SQLite ledger; calculation processes never access it.
"""
from __future__ import annotations

import argparse
import ctypes
from collections import Counter
from contextlib import contextmanager, nullcontext
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import pwd
import re
import resource
import signal
import shutil
import shlex
import socket
import socketserver
import sqlite3
import stat
import struct
import subprocess
import sys
import time

PROTOCOL = "coragent-external-job/1"
VIEW_VERSION = 'qrun-view/1'
CLI_VERSION = 'qrun-cli/1'
TERMINAL = {"succeeded", "failed", "cancelled", "timed_out"}
ACTIVE = {"starting", "running", "stopping", "unknown"}
MAX_MESSAGE = 1024 * 1024
DAEMON_CHILDREN = {}
READ_ACTIONS = {'overview', 'resources', 'jobs', 'show', 'logs'}


def now():
    return datetime.now(timezone.utc).isoformat()


def boot_id():
    return Path('/proc/sys/kernel/random/boot_id').read_text().strip()


def clean_environment():
    uid = os.getuid()
    return {"HOME": pwd.getpwuid(uid).pw_dir, "PATH": os.defpath, "LANG": "C.UTF-8",
            "PYTHONDONTWRITEBYTECODE": "1", "PYTHONNOUSERSITE": "1",
            "XDG_RUNTIME_DIR": f"/run/user/{uid}",
            "DBUS_SESSION_BUS_ADDRESS": f"unix:path=/run/user/{uid}/bus"}


def atomic_json(path, value):
    path = Path(path)
    temporary = path.with_name('.' + path.name + '.' + str(os.getpid()))
    try:
        with temporary.open('x', encoding='utf-8') as stream:
            os.chmod(temporary, 0o600)
            json.dump(value, stream, sort_keys=True)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    finally:
        temporary.unlink(missing_ok=True)


@contextmanager
def lock(path, *, nonblocking=False):
    with Path(path).open('a') as stream:
        fcntl.flock(stream, fcntl.LOCK_EX | (fcntl.LOCK_NB if nonblocking else 0))
        yield


def private_root(path):
    path = Path(path).expanduser()
    if not path.is_absolute() or '..' in path.parts or path == Path('/'):
        raise ValueError('state directory must be an absolute dedicated path')
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError('state directory must not contain symlinks')
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    st = path.stat()
    if st.st_uid != os.getuid() or st.st_mode & 0o077:
        raise ValueError('state directory must be owned by this user with mode 0700')
    return path


class RequestError(ValueError):
    def __init__(self, message, *, outcome='unknown', code='qrun_error'):
        super().__init__(message)
        self.outcome = outcome
        self.code = code


class QueryError(RuntimeError):
    """Keep a daemon/transport error intact for the operator CLI."""
    def __init__(self, error):
        super().__init__(error['message'])
        self.error = error


class Systemd:
    """One implementation for all Qrun hosts; no SSH logic belongs here."""

    def __init__(self, root):
        self.root = root

    def command(self, argv):
        return subprocess.run(argv, env=clean_environment(), capture_output=True,
                              text=True, timeout=15)

    def probe(self):
        controllers = Path('/sys/fs/cgroup/cgroup.controllers')
        if not controllers.is_file() or not {'cpu', 'memory'} <= set(controllers.read_text().split()):
            raise RuntimeError('Qrun requires cgroup v2 CPU and memory controllers')
        result = self.command(['systemctl', '--user', 'show-environment'])
        if result.returncode:
            raise RuntimeError('user systemd manager unavailable')

    def inspect(self, job):
        result = self.command(['systemctl', '--user', 'show', job['unit'],
            '--property=LoadState,ActiveState,SubState,Result,ExecMainCode,ExecMainStatus,Description,ControlGroup'])
        values = dict(line.split('=', 1) for line in result.stdout.splitlines() if '=' in line)
        if values.get('LoadState') == 'not-found':
            path = self.root / 'jobs' / job['id'] / 'unit.json'
            if path.exists():
                saved = json.loads(path.read_text())
                if saved.get('unit') != job['unit'] or saved.get('boot') != boot_id():
                    raise RuntimeError('stored systemd identity mismatch')
                if self.group_empty(saved['group']):
                    return {'state': 'finished', 'result': 'unit-removed', 'exit_code': None}
            return {'state': 'missing'}
        if result.returncode or values.get('LoadState') != 'loaded':
            raise RuntimeError('cannot observe systemd unit')
        if values.get('Description') != 'Qrun ' + job['id']:
            raise RuntimeError('systemd unit identity mismatch')
        group = values.get('ControlGroup')
        if group:
            atomic_json(self.root / 'jobs' / job['id'] / 'unit.json', {
                'unit': job['unit'], 'boot': boot_id(), 'group': group})
        active, substate = values.get('ActiveState'), values.get('SubState')
        if active in {'activating', 'deactivating'} or substate == 'running':
            return {'state': 'running'}
        if active not in {'inactive', 'failed'} and not (active == 'active' and substate == 'exited'):
            raise RuntimeError('unrecognized systemd unit state')
        # A stopped main PID alone does not prove its descendants have exited.
        if group and not self.group_empty(group):
            return {'state': 'running'}
        return {'state': 'finished', 'result': values.get('Result'),
                'exit_code': int(values.get('ExecMainStatus', '0')),
                'exit_kind': int(values.get('ExecMainCode', '0'))}

    @staticmethod
    def group_empty(group):
        relative = Path(group.lstrip('/'))
        if not group.startswith('/') or '..' in relative.parts or not relative.parts:
            raise RuntimeError('invalid systemd control group')
        directory = Path('/sys/fs/cgroup') / relative
        if not directory.exists():
            return True
        return 'populated 0' in (directory / 'cgroup.events').read_text().splitlines()

    def start(self, job):
        # Retain units until the durable terminal record has been committed.
        timeout = json.loads(job['request']).get('timeout_seconds')
        limits = ['--property=RuntimeMaxSec=' + str(timeout + 5) + 's'] if timeout else []
        args = ['systemd-run', '--user', '--quiet', '--unit=' + job['unit'],
                '--property=Description=Qrun ' + job['id'], '--property=Type=exec',
                '--property=RemainAfterExit=yes', '--property=KillMode=control-group',
                '--property=TimeoutStopSec=5s', '--property=SendSIGKILL=yes',
                '--property=CPUAccounting=yes', '--property=MemoryAccounting=yes',
                '--property=CPUQuota=' + str(job['cpus'] * 100) + '%',
                '--property=MemoryMax=' + str(job['memory_mb'] * 1024 * 1024),
                '--property=UMask=0077', '--property=StandardOutput=null',
                '--property=StandardError=null', *limits, '--', '/usr/bin/env', '-i',
                *[key + '=' + value for key, value in clean_environment().items()],
                sys.executable, '-B', str(Path(__file__).resolve()), '--state-dir', str(self.root),
                '_run', job['id']]
        result = self.command(args)
        if result.returncode:
            # Even a nonzero response can follow acceptance. Reconcile by unit.
            raise RuntimeError('systemd launch not acknowledged: ' + result.stderr[:500])

    def stop(self, job):
        result = self.command(['systemctl', '--user', 'stop', job['unit']])
        if result.returncode:
            raise RuntimeError('systemd stop not acknowledged')

    def cleanup(self, job):
        observed = self.inspect(job)  # Verify ownership before stopping any unit.
        if observed['state'] == 'missing':
            return False
        if observed.get('result') == 'unit-removed':
            return True
        self.stop(job)
        result = self.command(['systemctl', '--user', 'reset-failed', job['unit']])
        after = self.inspect(job)
        if after['state'] == 'missing' or after.get('result') == 'unit-removed':
            return True
        if result.returncode:
            raise RuntimeError('systemd cleanup not acknowledged')
        return False


def process_info(pid):
    try:
        fields = Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()
        return {'pid': int(pid), 'state': fields[0], 'ppid': int(fields[1]),
                'start': fields[19], 'rss': int(fields[21]) * os.sysconf('SC_PAGE_SIZE'),
                'cpu_seconds': sum(int(fields[i]) for i in (11, 12, 13, 14)) / os.sysconf('SC_CLK_TCK')}
    except (FileNotFoundError, ProcessLookupError):
        return None


def descendants(parent):
    processes = {}
    for path in Path('/proc').iterdir():
        if path.name.isdecimal():
            try:
                if path.stat().st_uid == os.getuid():
                    row = process_info(int(path.name))
                    if row:
                        processes[row['pid']] = row
            except (FileNotFoundError, ProcessLookupError):
                pass
    selected = {parent}
    while True:
        added = {pid for pid, row in processes.items() if row['ppid'] in selected} - selected
        if not added:
            return [row for pid, row in processes.items() if pid in selected and pid != parent]
        selected.update(added)


def subreaper():
    library = ctypes.CDLL(None, use_errno=True)
    if library.prctl(36, 1, 0, 0, 0) != 0:  # PR_SET_CHILD_SUBREAPER, Linux >= 3.4
        raise OSError(ctypes.get_errno(), 'Qrun requires Linux child subreapers')


def spawn_script(directory, request):
    streams = []
    try:
        for name in ('stdout', 'stderr'):
            descriptor = os.open(directory / (name + '.log'), os.O_WRONLY | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW, 0o600)
            streams.append(os.fdopen(descriptor, 'ab'))
        return subprocess.Popen(['/bin/sh', request['script']], cwd=request['cwd'], env=clean_environment(),
            stdin=subprocess.DEVNULL, stdout=streams[0], stderr=streams[1], start_new_session=True)
    finally:
        for stream in streams:
            stream.close()


class JobSampler:
    """Bounded rate samples survive worker/daemon exit; never used as reservations."""
    def __init__(self, directory, mode):
        self.directory, self.mode = directory, mode
        self.previous_time = time.monotonic()
        self.previous_cpu = self.peak = 0
        self.group = None
        if mode == 'systemd':
            for line in Path('/proc/self/cgroup').read_text().splitlines():
                if line.startswith('0::/'):
                    self.group = Path('/sys/fs/cgroup') / line[4:]

    def sample(self, rows=None, *, force=False, final=False):
        current = time.monotonic()
        elapsed = current - self.previous_time
        if not force and elapsed < .5:
            return
        try:
            if self.mode == 'systemd' and self.group:
                fields = dict(line.split() for line in (self.group / 'cpu.stat').read_text().splitlines())
                cpu = int(fields['usage_usec']) / 1_000_000
                memory = int((self.group / 'memory.current').read_text())
                count = len((self.group / 'cgroup.procs').read_text().split())
                source = 'cgroup-v2'
            else:
                rows = descendants(os.getpid()) if rows is None else rows
                reaped = resource.getrusage(resource.RUSAGE_CHILDREN)
                cpu = sum(row['cpu_seconds'] for row in rows) + reaped.ru_utime + reaped.ru_stime
                memory = sum(row['rss'] for row in rows)
                count, source = len(rows), 'proc-tree-sampled'
            cpu = max(cpu, self.previous_cpu)
            self.peak = max(self.peak, memory)
            atomic_json(self.directory / 'usage.json', {'sampled_at': now(), 'source': source, 'final': final,
                'cpu_seconds': round(cpu, 3), 'cpu_cores': round((cpu - self.previous_cpu) / max(elapsed, .001), 3),
                'memory_mb': round(memory / 1048576, 3), 'peak_memory_mb': round(self.peak / 1048576, 3),
                'processes': count, 'sample_interval_seconds': round(elapsed, 3)})
            self.previous_cpu, self.previous_time = cpu, current
        except (OSError, ValueError, KeyError):
            pass  # Missing samples are shown as stale, never as zero usage.


class HostSampler:
    def __init__(self):
        self.previous = None
        self.value = None
        self.when = 0

    def sample(self):
        if self.value is not None and time.monotonic() - self.when < .5:
            return self.value
        fields = [int(v) for v in Path('/proc/stat').read_text().splitlines()[0].split()[1:9]]
        total, idle = sum(fields), fields[3] + fields[4]
        percent = None
        if self.previous and total > self.previous[0]:
            percent = round(100 * (1 - (idle - self.previous[1]) / (total - self.previous[0])), 1)
        memory = {line.split(':', 1)[0]: int(line.split()[1]) / 1024
                  for line in Path('/proc/meminfo').read_text().splitlines() if line.startswith(('MemTotal:', 'MemAvailable:'))}
        self.value = {'sampled_at': now(), 'logical_cpus': os.cpu_count(),
            'allowed_cpus': len(os.sched_getaffinity(0)), 'cpu_busy_percent': percent,
            'memory_total_mb': memory['MemTotal'], 'memory_available_mb': memory.get('MemAvailable'),
            'load_average': list(os.getloadavg())}
        self.previous, self.when = (total, idle), time.monotonic()
        return self.value


def read_json(path, default=None):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return default


def age(timestamp, end=None):
    if not timestamp:
        return None
    return max(0, ((datetime.fromisoformat(end) if end else datetime.now(timezone.utc)) -
                   datetime.fromisoformat(timestamp)).total_seconds())


def resolve_job(rows, identifier):
    key = str(identifier)
    matches = [row for row in rows if str(row['seq']) == key]
    if len(matches) != 1:
        raise RequestError('ambiguous job ID' if matches else 'unknown job ID', code='job_not_found')
    return matches[0]


class QueueView:
    """One ledger snapshot for CLI, SSH handler and offline inspection."""
    def __init__(self, root, config, rows, *, online, host=None):
        self.root, self.config, self.rows, self.online = root, config, rows, online
        self.control = read_json(root / 'control.json', {'paused': False})
        self.heartbeat = read_json(root / 'heartbeat.json', {})
        self.host = host if online else self.heartbeat.get('host')
        self.reserved = {key: sum(row[key] for row in rows if row['state'] in ACTIVE)
                         for key in ('cpus', 'memory_mb')}
        self.waiting = {}
        remaining = {key: config[key] - self.reserved[key] for key in self.reserved}
        predecessor = None
        for row in rows:
            if row['state'] != 'queued':
                continue
            if not online:
                reason = {'code': 'daemon_offline'}
            elif self.control['paused']:
                reason = {'code': 'paused'}
            elif predecessor:
                reason = {'code': 'fifo', 'blocked_by': predecessor}
            elif any(row[key] > config[key] for key in remaining):
                reason = {'code': 'exceeds_capacity'}
            elif any(row[key] > remaining[key] for key in remaining):
                reason = {'code': 'insufficient_resources', 'shortfall': {
                    key: max(0, row[key] - remaining[key]) for key in remaining}}
            else:
                reason = {'code': 'ready'}
                for key in remaining:
                    remaining[key] -= row[key]
            self.waiting[row['id']] = reason
            if reason['code'] != 'ready' and predecessor is None:
                predecessor = str(row['seq'])

    def usage(self, row):
        value = read_json(self.root / 'jobs' / row['id'] / 'usage.json')
        if not value:
            return {'available': False, 'stale': True, 'sampled_at': None,
                    'cpu_cores': None, 'memory_mb': None, 'cpu_seconds': None, 'peak_memory_mb': None}
        return {**value, 'available': True, 'stale': (not self.online or
            (row['state'] in ACTIVE and (age(value['sampled_at']) > 3 or value.get('final', False)))),
            'age_seconds': round(age(value['sampled_at']), 1)}

    def job(self, row, *, detail=False):
        value = {key: row[key] for key in ('seq', 'id', 'request_id', 'state', 'cpus', 'memory_mb',
                  'created_at', 'started_at', 'finished_at', 'exit_code', 'error')}
        value.update(id=str(row['seq']), cancel_requested=bool(row['cancel']), cleaned=bool(row['cleaned']),
            execution_finished=row['state'] in TERMINAL,
            wait_reason=self.waiting.get(row['id']), usage=self.usage(row),
            wait_seconds=age(row['created_at'], row['started_at'] or row['finished_at']),
            elapsed_seconds=age(row['started_at'], row['finished_at']))
        if detail:
            request = json.loads(row['request'])
            value.update(cwd=request['cwd'], script=request['script'], timeout_seconds=request.get('timeout_seconds'),
                         unit=row['unit'])
        return value

    def overview(self):
        capacity = {key: self.config[key] for key in self.reserved}
        usage = [self.usage(row) for row in self.rows if row['state'] in ACTIVE]
        fresh = [item for item in usage if item['available'] and not item['stale']]
        complete = self.online and len(fresh) == len(usage)
        cpu = round(sum(item['cpu_cores'] for item in fresh), 3)
        memory = round(sum(item['memory_mb'] for item in fresh), 3)
        return {'runtime': self.config.get('runtime', 'systemd'),
            'memory_enforcement': 'sampled-rss' if self.config.get('runtime') == 'portable' else 'cgroup',
            'paused': self.control['paused'], 'capacity': capacity, 'reserved': self.reserved,
            'free': {key: max(0, capacity[key] - self.reserved[key]) for key in capacity},
            'overcommitted': {key: max(0, self.reserved[key] - capacity[key]) for key in capacity},
            'states': dict(Counter(row['state'] for row in self.rows)), 'host': self.host,
            'job_usage': {'cpu_cores': cpu, 'memory_mb': memory, 'complete': complete,
                'total_cpu_cores': cpu if complete else None, 'total_memory_mb': memory if complete else None,
                'fresh_jobs': len(fresh), 'missing_or_stale_jobs': len(usage) - len(fresh)}}

    def query(self, request):
        result = {'view_version': VIEW_VERSION, 'online': self.online, 'stale': not self.online,
                  'source': 'daemon' if self.online else 'ledger', 'state_basis': 'ledger',
                  'observed_at': now(), 'last_heartbeat': self.heartbeat.get('sampled_at')}
        action = request['action']
        if action in {'overview', 'resources'}:
            return {**result, **self.overview()}
        if action == 'jobs':
            if 'all' in request and type(request['all']) is not bool:
                raise RequestError('all must be a boolean', code='invalid_arguments')
            states = request.get('states')
            if states is None or states == []:
                states = ACTIVE | {'queued'} if not request.get('all') else ACTIVE | TERMINAL | {'queued'}
            if (not isinstance(states, (list, set)) or any(not isinstance(state, str) for state in states)
                    or set(states) - ACTIVE - TERMINAL - {'queued'}):
                raise RequestError('invalid state filter', code='invalid_arguments')
            limit, offset = request.get('limit', 50), request.get('offset', 0)
            if type(limit) is not int or not 1 <= limit <= 100 or type(offset) is not int or offset < 0:
                raise RequestError('limit must be 1..100 and offset must be nonnegative', code='invalid_arguments')
            selected = [row for row in self.rows if row['state'] in states]
            # History is newest first, while the live queue follows FIFO order.
            if request.get('all') or set(states) <= TERMINAL:
                selected.reverse()
            return {**result, 'total': len(selected), 'limit': limit, 'offset': offset,
                    'has_more': offset + limit < len(selected),
                    'next_offset': offset + limit if offset + limit < len(selected) else None,
                    'order': 'newest_first' if request.get('all') or set(states) <= TERMINAL else 'fifo',
                    'jobs': [self.job(row) for row in selected[offset:offset + limit]]}
        row = resolve_job(self.rows, request.get('identifier', ''))
        if action == 'show':
            return {**result, 'job': self.job(row, detail=True)}
        if action == 'logs':
            return {**result, **job_logs(self.root, row, request)}
        raise ValueError('unsupported query')


def job_logs(root, row, request):
    stream = request.get('stream', 'stdout')
    limit = request.get('bytes', 16384)
    offset = request.get('offset')
    if stream not in {'stdout', 'stderr'} or type(limit) is not int or not 1 <= limit <= 65536:
        raise RequestError('stream must be stdout/stderr and bytes must be 1..65536', code='invalid_arguments')
    if offset is not None and (type(offset) is not int or offset < 0):
        raise RequestError('invalid log offset', code='invalid_arguments')
    cwd = Path(json.loads(row['request'])['cwd'])
    candidates = [cwd / 'logs' / (stream + '.log'), root / 'jobs' / row['id'] / (stream + '.log')]
    for path in candidates:
        try:
            fd = open_log(path)
        except FileNotFoundError:
            continue
        with os.fdopen(fd, 'rb') as file:
            info = os.fstat(file.fileno())
            if not stat.S_ISREG(info.st_mode):
                raise ValueError('log is not a regular file')
            identity = str(info.st_dev) + ':' + str(info.st_ino)
            reset = offset is not None and (offset > info.st_size or request.get('identity') != identity)
            start = max(0, info.st_size - limit) if offset is None else (0 if reset else offset)
            file.seek(start)
            data = file.read(limit)
            end = file.tell()
            return {'id': str(row['seq']), 'stream': stream, 'available': True, 'text': data.decode('utf-8', errors='replace'),
                    'offset': end, 'identity': identity, 'reset': reset, 'truncated': start > 0,
                    'eof': end >= info.st_size, 'finished': row['state'] in TERMINAL}
    return {'id': str(row['seq']), 'stream': stream, 'available': False, 'text': '', 'offset': 0,
            'identity': None, 'eof': True, 'finished': row['state'] in TERMINAL}


def open_log(path):
    # Walk with directory descriptors: renames/symlinks cannot redirect a read
    # between validation and opening. Log requests never accept arbitrary paths.
    parent = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in path.parts[1:-1]:
            next_fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
            os.close(parent)
            parent = next_fd
        return os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
    except FileNotFoundError:
        raise
    except OSError as exc:
        raise ValueError('unsafe log path (symlink or inaccessible directory)') from exc
    finally:
        os.close(parent)


def query(root, request):
    """Only reads may fall back to the ledger when the daemon is unavailable."""
    try:
        answer = client(root, {'schema_version': PROTOCOL, **request}, timeout=5)
    except (OSError, ValueError):
        if request['action'] not in READ_ACTIONS:
            raise QueryError({'code': 'qrun_unavailable',
                'message': 'Qrun daemon unavailable or response lost; operation outcome is unknown',
                'retryable': True, 'action_outcome': 'unknown'}) from None
        config = json.loads((root / 'config.json').read_text())
        connection = sqlite3.connect((root / 'queue.sqlite3').as_uri() + '?mode=ro', uri=True)
        connection.row_factory = sqlite3.Row
        try:
            rows = [dict(row) for row in connection.execute('SELECT * FROM jobs ORDER BY seq')]
            answer = QueueView(root, config, rows, online=False).query(request)
        finally:
            connection.close()
    if isinstance(answer.get('error'), dict):
        raise QueryError(answer['error'])
    return answer


class Portable:
    """Unprivileged Linux runtime. Reservations and sampled RSS, not cgroup isolation."""
    def __init__(self, root):
        self.root = root
        self.children = []

    def probe(self):
        if not hasattr(os, 'sched_setaffinity') or not Path('/proc/self/task').is_dir():
            raise RuntimeError('portable Qrun requires Linux /proc and CPU affinity')
        value = ctypes.c_int()
        if ctypes.CDLL(None, use_errno=True).prctl(37, ctypes.byref(value), 0, 0, 0) != 0:
            raise RuntimeError('portable Qrun requires Linux child subreapers')

    def inspect(self, job):
        self.children = [child for child in self.children if child.poll() is None]
        directory = self.root / 'jobs' / job['id']
        result = directory / 'result.json'
        if result.exists() and json.loads(result.read_text()).get('descendants_reaped'):
            return {'state': 'finished', 'result': 'portable-exit'}
        identity = directory / 'worker.json'
        if identity.exists():
            saved = json.loads(identity.read_text())
            observed = process_info(saved['pid'])
            if (saved['boot'] == boot_id() and observed and observed['state'] != 'Z'
                    and observed['start'] == saved['start']):
                return {'state': 'running'}
        return {'state': 'missing'}

    def start(self, job):
        used = set()
        for path in (self.root / 'jobs').glob('*/allocation.json'):
            row = json.loads(path.read_text())
            result = path.with_name('result.json')
            complete = result.exists() and json.loads(result.read_text()).get('descendants_reaped')
            complete = complete or (path.with_name('cancel.json').exists() and not path.with_name('started.json').exists())
            if row['boot'] == boot_id() and not complete:
                used.update(row['affinity'])
        available = sorted(os.sched_getaffinity(0) - used)
        if len(available) < job['cpus']:
            raise RuntimeError('portable CPU affinity allocation unavailable')
        directory = self.root / 'jobs' / job['id']
        atomic_json(directory / 'allocation.json', {'affinity': available[:job['cpus']], 'boot': boot_id()})
        child = subprocess.Popen([sys.executable, '-B', str(Path(__file__).resolve()),
            '--state-dir', str(self.root), '_portable-run', job['id']],
            env=clean_environment(), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, start_new_session=True)
        self.children.append(child)
        # Serialize launch acknowledgments so subsequent Jobs cannot reuse its CPUs.
        deadline = time.monotonic() + 5
        while self.inspect(job)['state'] == 'missing':
            if child.poll() is not None or time.monotonic() >= deadline:
                raise RuntimeError('portable worker launch was not acknowledged')
            time.sleep(.02)

    def stop(self, job):
        directory = self.root / 'jobs' / job['id']
        with lock(directory / 'launch.lock'):
            atomic_json(directory / 'cancel.json', {'requested_at': now()})

    def cleanup(self, job):
        if self.inspect(job)['state'] == 'finished':
            return True
        directory = self.root / 'jobs' / job['id']
        with lock(directory / 'launch.lock'):
            return (directory / 'cancel.json').exists() and not (directory / 'started.json').exists()


def runtime_for(root, config):
    return Portable(root) if config.get('runtime', 'systemd') == 'portable' else Systemd(root)


def select_runtime(value='auto'):
    if value == 'auto':
        return 'systemd' if Path('/sys/fs/cgroup/cgroup.controllers').is_file() else 'portable'
    if value not in {'systemd', 'portable'}:
        raise ValueError('Qrun runtime must be auto, systemd or portable')
    return value


def portable_run(root, identifier):
    if not re.fullmatch(r'qr-[a-f0-9]{64}', identifier):
        raise ValueError('invalid job identity')
    directory = root / 'jobs' / identifier
    with lock(directory / 'worker.lock', nonblocking=True):
        if (directory / 'result.json').exists():
            return 0
        subreaper()
        affinity = json.loads((directory / 'allocation.json').read_text())['affinity']
        os.sched_setaffinity(0, affinity)
        atomic_json(directory / 'worker.json', {**process_info(os.getpid()), 'boot': boot_id(), 'affinity': affinity})
        request = json.loads((directory / 'run.json').read_text())
        stopping = False
        def stop(*_args):
            nonlocal stopping
            stopping = True
        signal.signal(signal.SIGTERM, stop)
        signal.signal(signal.SIGINT, stop)
        process = None
        sampler = JobSampler(directory, 'portable')
        state, code, error = 'failed', None, None
        try:
            with lock(directory / 'launch.lock'):
                if stopping or (directory / 'cancel.json').exists():
                    state = 'cancelled'
                else:
                    atomic_json(directory / 'started.json', {'boot': boot_id(), 'started_at': now()})
                    process = spawn_script(directory, request)
            deadline = time.monotonic() + request['timeout_seconds'] if request.get('timeout_seconds') else None
            while process is not None:
                observed = os.waitid(os.P_PID, process.pid, os.WEXITED | os.WNOHANG | os.WNOWAIT)
                if observed:
                    code = observed.si_status if observed.si_code == os.CLD_EXITED else -observed.si_status
                    state = 'succeeded' if code == 0 else 'failed'
                    marker = Path(request['cwd']) / 'status.state'
                    if marker.is_file() and marker.read_text().strip() == 'timed_out':
                        state = 'timed_out'
                    break
                if stopping or (directory / 'cancel.json').exists():
                    state = 'cancelled'
                    break
                if deadline and time.monotonic() >= deadline:
                    state = 'timed_out'
                    break
                children = descendants(os.getpid())
                sampler.sample(children)
                if sum(row['rss'] for row in children) > request['resources']['memory_mb'] * 1048576:
                    error = 'sampled process-tree RSS exceeded memory reservation'
                    break
                time.sleep(.1)
        except (OSError, ValueError, subprocess.SubprocessError) as exc:
            error = str(exc)
        finally:
            sampler.sample(force=True)
            # Kill only our unreaped direct children: their PIDs cannot be reused.
            # Detached/double-forked descendants become direct children as their
            # parents exit because this worker is a Linux child subreaper.
            while True:
                for row in descendants(os.getpid()):
                    if row['ppid'] != os.getpid():
                        continue
                    try:
                        observed = os.waitid(os.P_PID, row['pid'], os.WEXITED | os.WNOHANG | os.WNOWAIT)
                        if observed is None:
                            os.kill(row['pid'], signal.SIGKILL)
                        else:
                            os.waitpid(row['pid'], 0)
                    except ChildProcessError:
                        pass
                try:
                    observed = os.waitid(os.P_ALL, 0, os.WEXITED | os.WNOHANG | os.WNOWAIT)
                except ChildProcessError:
                    break
                if observed:
                    os.waitpid(observed.si_pid, 0)
                time.sleep(.02)
            if process is not None:
                process.returncode = code if code is not None else -signal.SIGKILL
            sampler.sample(force=True, final=True)
            atomic_json(directory / 'result.json', {'state': state, 'exit_code': code, 'error': error,
                        'finished_at': now(), 'descendants_reaped': True})
        return 0 if state == 'succeeded' else 1


class Queue:
    def __init__(self, root, *, runtime=None):
        self.root = private_root(root)
        self.config = json.loads((self.root / 'config.json').read_text())
        validate_pool(self.config)
        self.runtime = runtime or runtime_for(self.root, self.config)
        self.host_sampler = HostSampler()
        self.heartbeat_time = 0
        self.connection = sqlite3.connect(self.root / 'queue.sqlite3')
        self.connection.row_factory = sqlite3.Row
        self.connection.execute('PRAGMA journal_mode=WAL')
        self.connection.execute('PRAGMA synchronous=FULL')
        self.connection.execute('''CREATE TABLE IF NOT EXISTS jobs (
            seq INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT NOT NULL UNIQUE,
            request_id TEXT NOT NULL UNIQUE, fingerprint TEXT NOT NULL,
            request TEXT NOT NULL, state TEXT NOT NULL, cpus INTEGER NOT NULL,
            memory_mb INTEGER NOT NULL, unit TEXT NOT NULL UNIQUE, boot TEXT,
            cancel INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL,
            started_at TEXT, finished_at TEXT, exit_code INTEGER, error TEXT,
            cleaned INTEGER NOT NULL DEFAULT 0)''')
        self.connection.commit()
        (self.root / 'jobs').mkdir(exist_ok=True, mode=0o700)

    def close(self):
        self.connection.close()

    def rows(self):
        return [dict(row) for row in self.connection.execute('SELECT * FROM jobs ORDER BY seq')]

    def update(self, job, **values):
        with self.connection:
            self.connection.execute('UPDATE jobs SET ' + ','.join(key + '=?' for key in values) + ' WHERE id=?',
                                    [*values.values(), job['id']])
        job.update(values)

    def directory(self, job):
        return self.root / 'jobs' / job['id']

    def terminal(self, job, state, code=None, error=None):
        self.update(job, state=state, exit_code=code, error=error, finished_at=now())

    def validate_request(self, request):
        if request.get('queue') is not None:
            raise RequestError('Qrun has one FIFO queue; queue names are unsupported', outcome='not_submitted')
        resources = request.get('resources', {})
        if not isinstance(resources, dict) or set(resources) - {'cpus', 'memory_mb', 'walltime'}:
            raise RequestError('Qrun supports CPU, memory and walltime only', outcome='not_submitted')
        for name in ('cpus', 'memory_mb'):
            if type(resources.get(name)) is not int or not 1 <= resources[name] <= self.config[name]:
                raise RequestError(name + ' must be explicit and within pool capacity', outcome='not_submitted')
        timeout = request.get('timeout_seconds')
        if timeout is not None and (type(timeout) not in (int, float) or not 0 < timeout <= 31536000):
            raise RequestError('invalid timeout_seconds', outcome='not_submitted')
        cwd, script = Path(request.get('cwd', '')), Path(request.get('script', ''))
        roots = [Path(value).resolve() for value in self.config['work_roots']]
        if (not cwd.is_absolute() or not cwd.is_dir() or not script.is_absolute() or not script.is_file()
                or not any(cwd.resolve().is_relative_to(root) for root in roots)
                or not script.resolve().is_relative_to(cwd.resolve())
                or cwd.resolve().is_relative_to(self.root) or self.root.is_relative_to(cwd.resolve())):
            raise RequestError('job paths must be inside an allowed work root, outside queue state', outcome='not_submitted')
        return resources

    @staticmethod
    def fingerprint(request):
        fields = {key: request.get(key) for key in ('request_id', 'job_id', 'cwd', 'script', 'resources', 'queue', 'timeout_seconds')}
        return hashlib.sha256(json.dumps(fields, sort_keys=True, allow_nan=False).encode()).hexdigest()

    def lookup(self, request):
        row = self.connection.execute('SELECT * FROM jobs WHERE request_id=?', (request.get('request_id'),)).fetchone()
        if row is None:
            return None
        job = dict(row)
        if job['fingerprint'] != self.fingerprint(request):
            raise RequestError('request identity reused with different content')
        if request.get('scheduler_id', str(job['seq'])) not in (str(job['seq']), job['id']):
            raise RequestError('execution identity mismatch')
        return job

    def handle(self, request):
        if request.get('schema_version') != PROTOCOL:
            raise RequestError('unsupported protocol')
        action = request.get('action')
        if not isinstance(action, str):
            raise RequestError('action must be a string', code='invalid_arguments')
        if action in READ_ACTIONS:
            return self.view().query(request)
        if action in {'pause', 'resume'}:
            atomic_json(self.root / 'control.json', {'paused': action == 'pause', 'changed_at': now()})
            return self.view().query({'action': 'overview'})
        if action == 'configure':
            config = {**self.config, **{key: request[key] for key in ('cpus', 'memory_mb') if key in request}}
            validate_pool(config)
            if config.get('runtime') == 'portable' and config['cpus'] > len(os.sched_getaffinity(0)):
                raise ValueError('CPU capacity exceeds available CPU affinity')
            if config['memory_mb'] > self.host_sampler.sample()['memory_total_mb']:
                raise ValueError('memory capacity exceeds host physical memory')
            atomic_json(self.root / 'config.json', config)
            self.config = config
            return self.view().query({'action': 'overview'})
        if action == 'cancel_job':
            job = resolve_job(self.rows(), request.get('identifier', ''))
            return self.handle({**json.loads(job['request']), 'action': 'cancel', 'scheduler_id': str(job['seq'])})
        if action == 'probe':
            self.runtime.probe()
            return {'available': True, 'executor': 'qrun',
                    'runtime': self.config.get('runtime', 'systemd'),
                    'memory_enforcement': 'sampled-rss' if self.config.get('runtime') == 'portable' else 'cgroup',
                    'capacity': {key: self.config[key] for key in ('cpus', 'memory_mb')},
                    'queue': self.view().query({'action': 'overview'})}
        if not isinstance(request.get('request_id'), str) or not re.fullmatch(r'[A-Za-z0-9_.-]{1,200}', request['request_id']):
            raise RequestError('invalid request identity', outcome='not_submitted')
        job = self.lookup(request)
        if action == 'submit':
            if job:
                return {'scheduler_id': str(job['seq'])}
            resources = self.validate_request(request)
            identifier = 'qr-' + hashlib.sha256((str(self.root) + '\0' + request['request_id']).encode()).hexdigest()
            with self.connection:
                inserted = self.connection.execute('''INSERT INTO jobs
                    (id,request_id,fingerprint,request,state,cpus,memory_mb,unit,created_at)
                    VALUES (?,?,?,?,?,?,?,?,?)''', (identifier, request['request_id'], self.fingerprint(request),
                    json.dumps(request), 'queued', resources['cpus'], resources['memory_mb'],
                    'coragent-qrun-' + identifier[3:] + '.service', now()))
            return {'scheduler_id': str(inserted.lastrowid)}
        if action == 'recover':
            return {'found': job is not None, **({'scheduler_id': str(job['seq'])} if job else {})}
        if job is None:
            raise RequestError('job not found; execution outcome is unknown')
        if action == 'cancel':
            if job['state'] not in TERMINAL:
                # Persist intent before acknowledging it, including queued work.
                self.update(job, cancel=1)
                if job['state'] == 'queued':
                    self.terminal(job, 'cancelled')
            return {'scheduler_id': request.get('scheduler_id', str(job['seq'])), 'accepted': True}
        if action != 'status':
            raise RequestError('unsupported action')
        return {'scheduler_id': request.get('scheduler_id', str(job['seq'])), 'state': 'submitted' if job['state'] == 'starting' else
                'running' if job['state'] == 'stopping' else job['state'],
                'execution_finished': job['state'] in TERMINAL, 'exit_code': job['exit_code'],
                'started_at': job['started_at'], 'finished_at': job['finished_at'], 'error': job['error'],
                'diagnostics': {'executor': 'qrun', 'unit': job['unit'], 'cancel_requested': bool(job['cancel']),
                                'resources': {'cpus': job['cpus'], 'memory_mb': job['memory_mb']},
                                'usage': self.view().usage(job),
                                'wait_reason': self.view().waiting.get(job['id'])}}

    def view(self):
        return QueueView(self.root, self.config, self.rows(), online=True, host=self.host_sampler.sample())

    def reconcile(self, job):
        directory = self.directory(job)
        if not job['started_at']:
            started = read_json(directory / 'started.json', {})
            if started.get('boot') == job['boot'] and started.get('started_at'):
                self.update(job, started_at=started['started_at'])
        result_path = directory / 'result.json'
        # System reboot proves the previous boot's units cannot still consume resources.
        if job['boot'] != boot_id():
            result = json.loads(result_path.read_text()) if result_path.exists() else None
            if result:
                self.terminal(job, result['state'], result['exit_code'], result.get('error'))
            else:
                self.terminal(job, 'failed', error='execution host restarted; job was not rerun')
            return
        native = self.runtime.inspect(job)
        # Inspection can observe a result published while it runs. Read it afterwards
        # so a finished worker cannot be failed using an earlier absence of evidence.
        result = json.loads(result_path.read_text()) if result_path.exists() else None
        if native['state'] == 'finished':
            if result:
                self.terminal(job, result['state'], result['exit_code'], result.get('error'))
            elif native.get('result') == 'timeout':
                self.terminal(job, 'timed_out', native.get('exit_code'))
            elif job['cancel']:
                self.terminal(job, 'cancelled', native.get('exit_code'))
            else:
                self.terminal(job, 'failed', native.get('exit_code'), 'execution ended without a durable result: ' + str(native.get('result')))
            return
        if native['state'] == 'missing':
            # Never infer success or free an uncertain allocation from a missing unit.
            self.update(job, state='unknown', error='unit unavailable; allocation retained')
        else:
            self.update(job, state='running', error=None, started_at=job['started_at'] or now())
            if result is not None:
                # The wrapper exited but a descendant escaped its process group.
                # Stop the entire cgroup before freeing the allocation.
                self.runtime.stop(job)
                return
        if job['cancel']:
            with lock(directory / 'launch.lock'):
                atomic_json(directory / 'cancel.json', {'requested_at': now()})
                never_started = not (directory / 'started.json').exists()
            if native['state'] == 'missing' and never_started:
                # A late systemd launch must check this fence under the same lock.
                self.terminal(job, 'cancelled')
            else:
                self.runtime.stop(job)
                self.update(job, state='stopping')

    def tick(self):
        for job in self.rows():
            if job['state'] in ACTIVE:
                try:
                    self.reconcile(job)
                except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
                    self.update(job, state='unknown', error=str(exc))
            if job['state'] in TERMINAL and not job['cleaned']:
                try:
                    if job['boot'] is None or job['boot'] != boot_id() or self.runtime.cleanup(job):
                        self.update(job, cleaned=1)
                except (OSError, ValueError, RuntimeError, subprocess.SubprocessError):
                    pass  # Terminal evidence is already durable; retry cleanup next tick.
        rows = self.rows()
        if time.monotonic() - self.heartbeat_time >= 1:
            atomic_json(self.root / 'heartbeat.json', {'sampled_at': now(), 'host': self.host_sampler.sample()})
            self.heartbeat_time = time.monotonic()
        if read_json(self.root / 'control.json', {}).get('paused'):
            return
        used_cpu = sum(job['cpus'] for job in rows if job['state'] in ACTIVE)
        used_memory = sum(job['memory_mb'] for job in rows if job['state'] in ACTIVE)
        for job in rows:
            if job['state'] != 'queued':
                continue
            if job['cpus'] + used_cpu > self.config['cpus'] or job['memory_mb'] + used_memory > self.config['memory_mb']:
                break  # Strict FIFO; no starvation caused by repeated small backfills.
            directory = self.directory(job)
            directory.mkdir(mode=0o700, exist_ok=True)
            atomic_json(directory / 'run.json', json.loads(job['request']))
            self.update(job, state='starting', boot=boot_id())
            used_cpu += job['cpus']
            used_memory += job['memory_mb']
            try:
                self.runtime.start(job)
            except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
                self.update(job, state='unknown', error=str(exc))


def validate_pool(config):
    if config.get('schema_version') != 'qrun-pool/1':
        raise ValueError('unsupported Qrun pool configuration')
    select_runtime(config.get('runtime', 'systemd'))
    for key in ('cpus', 'memory_mb'):
        if type(config.get(key)) is not int or config[key] < 1:
            raise ValueError(key + ' must be a positive integer')
    roots = config.get('work_roots')
    if not isinstance(roots, list) or not roots or any(not isinstance(p, str) or not p.startswith('/') or p == '/' or '..' in Path(p).parts for p in roots):
        raise ValueError('work_roots must contain dedicated absolute directories')


def socket_path(root):
    # Hash the canonical store, so path aliases share one daemon and short socket.
    config = root / 'config.json'
    if config.is_file() and json.loads(config.read_text()).get('runtime') == 'portable':
        return '\0qrun-' + str(os.getuid()) + '-' + hashlib.sha256(str(root.resolve()).encode()).hexdigest()
    runtime = Path(os.environ.get('XDG_RUNTIME_DIR', f'/run/user/{os.getuid()}'))
    return runtime / ('qrun-' + hashlib.sha256(str(root.resolve()).encode()).hexdigest()[:20] + '.sock')


def response(queue, request):
    try:
        return {'schema_version': PROTOCOL, **queue.handle(request)}
    except (RequestError, OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        return {'schema_version': PROTOCOL, 'error': {'code': getattr(exc, 'code', 'qrun_error'), 'message': str(exc),
            'retryable': False, 'action_outcome': getattr(exc, 'outcome', 'unknown')}}


def serve(root):
    root = private_root(root)
    with lock(root / 'daemon.lock', nonblocking=True):
        queue = Queue(root)
        address = socket_path(root)
        class Handler(socketserver.StreamRequestHandler):
            def handle(self):
                nonlocal stopped
                if struct.unpack('3i', self.request.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))[1] != os.getuid():
                    return
                self.request.settimeout(5)
                raw = self.rfile.readline(MAX_MESSAGE + 1)
                if len(raw) > MAX_MESSAGE:
                    return
                try:
                    request = json.loads(raw)
                    if not isinstance(request, dict):
                        return
                    if request.get('action') == '_shutdown' and request.get('schema_version') == PROTOCOL:
                        stopped = True
                        answer = {'stopped': True}
                    else:
                        answer = response(queue, request)
                    encoded = json.dumps(answer).encode() + b'\n'
                    if len(encoded) > MAX_MESSAGE:
                        encoded = json.dumps({'schema_version': PROTOCOL, 'error': {
                            'code': 'response_too_large', 'message': 'response too large; use a smaller page',
                            'retryable': False, 'action_outcome': 'unknown'}}).encode() + b'\n'
                    self.wfile.write(encoded)
                except (ValueError, OSError):
                    return
        stopped = False
        def stop(*_):
            nonlocal stopped
            stopped = True
        previous = {sig: signal.signal(sig, stop) for sig in (signal.SIGTERM, signal.SIGINT)}
        try:
            queue.runtime.probe()
            if isinstance(address, Path):
                address.unlink(missing_ok=True)
            with socketserver.UnixStreamServer(str(address), Handler) as server:
                if isinstance(address, Path):
                    os.chmod(address, 0o600)
                server.timeout = 0.25
                while not stopped:
                    queue.tick()
                    server.handle_request()
        finally:
            if isinstance(address, Path):
                address.unlink(missing_ok=True)
            queue.close()
            for sig, handler in previous.items():
                signal.signal(sig, handler)


def client(root, request, *, timeout=60):
    with socket.socket(socket.AF_UNIX) as connection:
        connection.settimeout(timeout)
        connection.connect(str(socket_path(root)))
        connection.sendall(json.dumps(request).encode() + b'\n')
        with connection.makefile('rb') as stream:
            raw = stream.readline(MAX_MESSAGE + 1)
        if len(raw) > MAX_MESSAGE:
            raise ValueError('Qrun response too large')
        answer = json.loads(raw)
        if not isinstance(answer, dict):
            raise ValueError('Qrun response must be an object')
        return answer


def run_job(root, identifier):
    if not re.fullmatch(r'qr-[a-f0-9]{64}', identifier):
        raise ValueError('invalid job identity')
    directory = root / 'jobs' / identifier
    request = json.loads((directory / 'run.json').read_text())
    stopping = False
    def stop(*_):
        nonlocal stopping
        stopping = True
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    process = None
    sampler = JobSampler(directory, 'systemd')
    state, code, error = 'failed', None, None
    try:
        with lock(directory / 'launch.lock'):
            if (directory / 'cancel.json').exists() or stopping:
                state = 'cancelled'
            else:
                # Record before spawning: absence plus a cancellation fence proves no execution.
                atomic_json(directory / 'started.json', {'boot': boot_id(), 'started_at': now()})
                process = spawn_script(directory, request)
        if process is not None:
            timeout = request.get('timeout_seconds')
            deadline = time.monotonic() + timeout if timeout else None
            kill_at = None
            while True:
                sampler.sample()
                # Keep the group leader unreaped until descendants are killed;
                # otherwise a reused PID/PGID could target an unrelated process.
                observed = os.waitid(os.P_PID, process.pid, os.WEXITED | os.WNOHANG | os.WNOWAIT)
                if observed is not None:
                    code = observed.si_status if observed.si_code == os.CLD_EXITED else -observed.si_status
                    if stopping and state != 'timed_out':
                        state = 'cancelled'
                    break
                if kill_at is not None and time.monotonic() >= kill_at:
                    os.killpg(process.pid, signal.SIGKILL)
                elif kill_at is None and (stopping or (deadline and time.monotonic() >= deadline)):
                    state = 'cancelled' if stopping else 'timed_out'
                    os.killpg(process.pid, signal.SIGTERM)
                    kill_at = time.monotonic() + 2
                time.sleep(0.05)
            if state not in {'cancelled', 'timed_out'}:
                state = 'succeeded' if code == 0 else 'failed'
                marker = Path(request['cwd']) / 'status.state'
                if marker.is_file() and marker.read_text().strip() == 'timed_out':
                    state = 'timed_out'
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        error = str(exc)
    finally:
        sampler.sample(force=True)
        if process is not None:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait()
        sampler.sample(force=True, final=True)
        atomic_json(directory / 'result.json', {'state': state, 'exit_code': code, 'error': error, 'finished_at': now()})
    return 0 if state == 'succeeded' else 1


def initialize(root, cpus, memory_mb, work_roots, *, locked=False, runtime=None):
    root = private_root(root)
    config = {'schema_version': 'qrun-pool/1', 'cpus': cpus, 'memory_mb': memory_mb, 'work_roots': work_roots}
    if runtime is not None:
        config['runtime'] = select_runtime(runtime)
    validate_pool(config)
    with (nullcontext() if locked else lock(root / 'daemon.lock', nonblocking=True)):
        path = root / 'config.json'
        if path.exists() and json.loads(path.read_text()) != config:
            raise ValueError('pool already configured; stop and drain it before explicit capacity maintenance')
        for work in work_roots:
            directory = Path(work)
            if directory.resolve().is_relative_to(root) or root.is_relative_to(directory.resolve()):
                raise ValueError('work roots and queue state must not overlap')
            directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        atomic_json(path, config)
    return config


def unit_text(root, executable):
    def quote(value):
        # systemd ExecStart syntax is not shell syntax.
        return '"' + str(value).replace('\\', '\\\\').replace('"', '\\"').replace('%', '%%').replace('$', '$$') + '"'
    command = ' '.join(quote(value) for value in ('/usr/bin/env', '-i',
        *[key + '=' + value for key, value in clean_environment().items()],
        sys.executable, '-B', executable, '--state-dir', root, 'serve'))
    return ('[Unit]\nDescription=Qrun durable job queue\n\n[Service]\nType=exec\n'
            'ExecStart=' + command + '\nRestart=on-failure\nRestartSec=2\nUMask=0077\n'
            'Environment=PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1\n'
            '\n[Install]\nWantedBy=default.target\n')


def install(root, cpus, memory_mb, work_roots, *, start=True, runtime=None):
    root = private_root(root)
    mode = select_runtime(runtime) if runtime is not None else 'systemd'
    with lock(root / 'daemon.lock', nonblocking=True):
        if start:
            check_service_manager(root, mode) if mode == 'portable' else check_service_manager(root)
        record = _install_locked(root, cpus, memory_mb, work_roots, start=False, runtime=runtime)
    if start:
        activate(root, record)
    return record


def _install_locked(root, cpus, memory_mb, work_roots, *, start=True, owner=None, runtime=None):
    """Explicit target-side installation. Never invoked implicitly by a Job."""
    root = private_root(root)
    manifest = root / 'installation.json'
    previous = json.loads(manifest.read_text()) if manifest.exists() else {}
    if previous.get('owner') and previous['owner'] != owner:
        raise ValueError('managed Qrun must be updated through its owning installer')
    config = initialize(root, cpus, memory_mb, work_roots, locked=True, runtime=runtime)
    mode = config.get('runtime', 'systemd')
    content = Path(__file__).read_bytes()
    binary = root / ('qrun-' + hashlib.sha256(content).hexdigest()[:20] + '.py')
    if binary.exists():
        if binary.is_symlink() or binary.read_bytes() != content:
            raise ValueError('installed Qrun code identity mismatch')
    else:
        with binary.open('xb') as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        binary.chmod(0o700)
    unit = 'coragent-qrun-queue-' + hashlib.sha256(str(root).encode()).hexdigest()[:20] + '.service'
    config_home = Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config'))
    directory = root if mode == 'portable' else config_home / 'systemd/user'
    directory.mkdir(parents=True, exist_ok=True)
    destination = root / 'service.json' if mode == 'portable' else directory / unit
    if destination.is_symlink() or (destination.exists() and previous.get('unit_path') != str(destination)):
        raise ValueError('refusing to overwrite an unowned systemd unit')
    destination.write_text(json.dumps({'runtime': mode, 'program': str(binary)}) if mode == 'portable' else unit_text(root, binary))
    record = {'unit': unit, 'unit_path': str(destination), 'program': str(binary),
              'handler': [sys.executable, '-B', str(binary), '--state-dir', str(root), 'handler'], 'runtime': mode}
    if owner:
        record.update(owner=owner, registered=start,
                      unit_sha256=hashlib.sha256(destination.read_bytes()).hexdigest())
    atomic_json(manifest, record)
    return record


def service_command(root, *arguments):
    config = root / 'config.json'
    if config.exists() and json.loads(config.read_text()).get('runtime') == 'portable':
        return portable_service(root, *arguments)
    result = Systemd(root).command(['systemctl', '--user', *arguments])
    if result.returncode:
        raise RuntimeError('Qrun service operation failed: ' + ' '.join(arguments[:1]))
    return result.stdout


def check_service_manager(root, mode='systemd'):
    if mode == 'portable':
        Portable(root).probe()
        result = cron_command(['-l'])
        if result.returncode and 'no crontab for' not in result.stderr.lower():
            raise RuntimeError('portable Qrun requires an accessible user crontab')
        return
    runtime = Systemd(root)
    runtime.probe()
    linger = runtime.command(['loginctl', 'show-user', str(os.getuid()), '--property=Linger', '--value'])
    if linger.returncode or linger.stdout.strip() != 'yes':
        raise ValueError('enable user lingering before installing Qrun: loginctl enable-linger ' + pwd.getpwuid(os.getuid()).pw_name)


def activate(root, record):
    service_command(root, 'daemon-reload')
    service_command(root, 'enable', '--now', record['unit'])
    deadline = time.monotonic() + 10
    while True:
        try:
            if client(root, {'schema_version': PROTOCOL, 'action': 'probe'}, timeout=1).get('available'):
                return
        except (OSError, ValueError):
            pass
        if time.monotonic() >= deadline:
            raise RuntimeError('Qrun service did not become ready')
        time.sleep(.05)


def cron_command(arguments, *, content=None):
    return subprocess.run(['crontab', *arguments], input=content, env={**clean_environment(), 'LC_ALL': 'C'},
                          capture_output=True, text=True, timeout=15)


def portable_enabled(root, enabled=None):
    """Change only this pool's cron lines; retain other user entries."""
    marker = '# coragent-qrun-' + hashlib.sha256(str(root).encode()).hexdigest()[:20]
    old = cron_command(['-l'])
    if old.returncode and 'no crontab for' not in old.stderr.lower():
        raise RuntimeError('cannot read user crontab')
    lines = old.stdout.splitlines() if old.returncode == 0 else []
    selected = [line for line in lines if line.endswith(marker)]
    if enabled is None:
        return bool(selected)
    retained = [line for line in lines if not line.endswith(marker)]
    if enabled:
        record = json.loads((root / 'installation.json').read_text())
        argv = [record['handler'][0], '-B', record['program'], '--state-dir', str(root), 'service', 'ensure']
        command = shlex.join(argv).replace('%', '\\%')
        if '\n' in command or '\r' in command:
            raise ValueError('invalid cron command path')
        retained.extend(prefix + ' ' + command + ' >/dev/null 2>&1 ' + marker for prefix in ('@reboot', '* * * * *'))
    content = '\n'.join(retained) + ('\n' if retained else '')
    if content != old.stdout:
        result = cron_command(['-'], content=content)
        if result.returncode:
            raise RuntimeError('cannot update Qrun user crontab')
    return enabled


def daemon_locked(root):
    try:
        with lock(root / 'daemon.lock', nonblocking=True):
            return False
    except BlockingIOError:
        return True


def portable_service(root, *arguments):
    operation = arguments[0]
    if operation == 'daemon-reload':
        return ''
    if operation == 'show':
        return ('ActiveState=' + ('active' if daemon_locked(root) else 'inactive') +
                '\nUnitFileState=' + ('enabled' if portable_enabled(root) else 'disabled'))
    if operation in {'enable', 'disable'}:
        portable_enabled(root, operation == 'enable')
        if '--now' not in arguments:
            return ''
        operation = 'start' if operation == 'enable' else 'stop'
    if operation == 'start':
        if not daemon_locked(root):
            record = json.loads((root / 'installation.json').read_text())
            if record.get('removed'):
                raise RuntimeError('Qrun installation was removed')
            with (root / 'daemon.log').open('ab') as output:
                child = subprocess.Popen([record['handler'][0], '-B', record['program'], '--state-dir', str(root), 'serve'],
                    env=clean_environment(), stdin=subprocess.DEVNULL, stdout=output, stderr=output, start_new_session=True)
            DAEMON_CHILDREN[str(root)] = child
            deadline = time.monotonic() + 10
            while not daemon_locked(root):
                if child.poll() is not None or time.monotonic() >= deadline:
                    raise RuntimeError('portable Qrun daemon did not start')
                time.sleep(.05)
        return ''
    if operation == 'stop':
        if daemon_locked(root):
            client(root, {'schema_version': PROTOCOL, 'action': '_shutdown'}, timeout=5)
            deadline = time.monotonic() + 10
            while daemon_locked(root):
                if time.monotonic() >= deadline:
                    raise RuntimeError('portable Qrun daemon did not stop')
                time.sleep(.05)
        child = DAEMON_CHILDREN.pop(str(root), None)
        if child:
            child.wait(timeout=5)
        return ''
    raise ValueError('unsupported portable service operation')


def owned_record(root, owner):
    """Validate ownership and the unit file before any service or data mutation."""
    manifest = root / 'installation.json'
    if manifest.is_symlink():
        raise ValueError('Qrun installation record cannot be a symlink')
    if not manifest.exists():
        unit = 'coragent-qrun-queue-' + hashlib.sha256(str(root).encode()).hexdigest()[:20] + '.service'
        destination = Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config')) / 'systemd/user' / unit
        if destination.exists() or destination.is_symlink():
            raise ValueError('Qrun unit exists without this installation ownership')
        if (root / 'config.json').exists():
            raise ValueError('Qrun pool already exists without this installation ownership')
        if any(path.name not in {'maintenance.lock', 'daemon.lock'} for path in root.iterdir()):
            raise ValueError('new managed Qrun state directory must be empty')
        return None
    record = json.loads(manifest.read_text())
    unit = 'coragent-qrun-queue-' + hashlib.sha256(str(root).encode()).hexdigest()[:20] + '.service'
    expected = (root / 'service.json' if record.get('runtime') == 'portable' else
                Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config')) / 'systemd/user' / unit)
    if record.get('owner') != owner or record.get('unit') != unit or record.get('unit_path') != str(expected):
        raise ValueError('Qrun pool is not owned by this installation and account')
    if expected.is_symlink() or (expected.exists() and hashlib.sha256(expected.read_bytes()).hexdigest() != record.get('unit_sha256')):
        raise ValueError('Qrun service definition changed outside the installer')
    if not expected.exists() and not record.get('removed'):
        raise ValueError('owned Qrun service definition is missing')
    return record


def _restore_files(root, snapshot):
    record = snapshot['record']
    if record:
        if record.get('removed'):
            Path(record['unit_path']).unlink(missing_ok=True)
        else:
            Path(record['unit_path']).write_text(snapshot['unit_text'])
        atomic_json(root / 'config.json', snapshot['config'])
        atomic_json(root / 'installation.json', record)
    else:
        if snapshot.get('unit_path'):
            Path(snapshot['unit_path']).unlink(missing_ok=True)
        manifest = root / 'installation.json'
        if not manifest.exists():
            (root / 'config.json').unlink(missing_ok=True)
            return
        record = json.loads(manifest.read_text())
        Path(record['unit_path']).unlink(missing_ok=True)
        record['removed'] = True
        atomic_json(root / 'installation.json', record)


def maintain(root, request):
    """Owned installation, drained upgrade, rollback and bounded uninstallation.

    The daemon is stopped before taking its writer lock. No ledger mutation is
    performed concurrently with serve(). Work roots are never deleted here.
    """
    owner = request.get('owner')
    if not isinstance(owner, str) or not re.fullmatch(r'coragent-[a-f0-9]{64}', owner):
        raise ValueError('invalid Qrun installation owner')
    operation = request.get('operation')
    if operation not in {'install', 'remove', 'restore', 'commit'}:
        raise ValueError('unsupported Qrun maintenance operation')
    if operation != 'install' and not Path(root).exists():
        return {'removed': True, 'restored': False}
    root = private_root(root)
    if root == Path.home() or root in Path.home().parents:
        raise ValueError('Qrun requires a dedicated state directory')
    with lock(root / 'maintenance.lock', nonblocking=True):
        old = owned_record(root, owner)
        if operation != 'install' and old is None:
            return {'removed': True}
        if operation == 'restore' and not (root / 'maintenance-snapshot.json').exists():
            return {'restored': False}
        if operation == 'commit':
            (root / 'maintenance-snapshot.json').unlink(missing_ok=True)
            return {'committed': True}
        previous_config = json.loads((root / 'config.json').read_text()) if old else None
        mode = select_runtime(request.get('runtime', previous_config.get('runtime', 'systemd') if old else 'auto'))
        if old and mode != previous_config.get('runtime', 'systemd'):
            raise ValueError('Qrun runtime cannot change for an existing pool')
        if operation == 'install' and request.get('start'):
            check_service_manager(root, mode) if mode == 'portable' else check_service_manager(root)
        registered = bool(old and old.get('registered') and not old.get('removed'))
        active = enabled = False
        if registered:
            observation = service_command(root, 'show', old['unit'], '--property=ActiveState,UnitFileState')
            values = dict(line.split('=', 1) for line in observation.splitlines() if '=' in line)
            active = values.get('ActiveState') in {'active', 'activating', 'reloading'}
            enabled = values.get('UnitFileState') in {'enabled', 'enabled-runtime'}
        snapshot = {'record': old, 'active': active, 'enabled': enabled,
                    'unit_text': Path(old['unit_path']).read_text() if old and not old.get('removed') else '',
                    'config': previous_config}
        unit = 'coragent-qrun-queue-' + hashlib.sha256(str(root).encode()).hexdigest()[:20] + '.service'
        snapshot['unit_path'] = str(root / 'service.json' if mode == 'portable' else
            Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config')) / 'systemd/user' / unit)
        # Durable recovery information exists even if the installer loses SSH.
        pending = root / 'maintenance-snapshot.json'
        if operation == 'install' and pending.exists():
            raise ValueError('unfinished Qrun installation; restore or commit the recorded operation first')
        mutated = activation_attempted = False
        try:
            if registered:
                service_command(root, 'stop', old['unit'])
            with lock(root / 'daemon.lock', nonblocking=True):
                queue = Queue(root) if (root / 'queue.sqlite3').exists() else None
                try:
                    jobs = queue.rows() if queue else []
                    unfinished = [job for job in jobs if job['state'] not in TERMINAL]
                    if unfinished and (operation == 'install' or not request.get('cancel_jobs')):
                        raise ValueError('Qrun has unfinished jobs; drain before upgrade or use --cancel-qrun-jobs for removal')
                    if unfinished:
                        for job in unfinished:
                            queue.handle({**json.loads(job['request']), 'action': 'cancel'})
                        deadline = time.monotonic() + 30
                        while any(job['state'] not in TERMINAL for job in queue.rows()):
                            queue.tick()
                            if time.monotonic() >= deadline:
                                raise RuntimeError('Qrun cancellation is unresolved; service and evidence retained')
                            time.sleep(.05)
                    if queue:
                        queue.tick()  # Remove terminal calculation units before releasing ownership.
                        if any(not job['cleaned'] for job in queue.rows()):
                            raise RuntimeError('Qrun calculation cleanup is unresolved')
                finally:
                    if queue:
                        queue.close()
                if operation == 'install':
                    config = {'schema_version': 'qrun-pool/1', 'cpus': request['cpus'],
                              'memory_mb': request['memory_mb'], 'work_roots': request['work_roots'], 'runtime': mode}
                    if previous_config:
                        for key in ('cpus', 'memory_mb'):
                            if key not in request.get('capacity_overrides', ['cpus', 'memory_mb']):
                                config[key] = previous_config[key]
                    validate_pool(config)
                    if mode == 'portable' and config['cpus'] > len(os.sched_getaffinity(0)):
                        raise ValueError('portable pool CPU capacity exceeds available CPU affinity')
                    atomic_json(pending, snapshot)
                    mutated = True
                    # Code upgrades still drain; online budget changes use configure.
                    atomic_json(root / 'config.json', config)
                    record = _install_locked(root, config['cpus'], config['memory_mb'], config['work_roots'], start=False, owner=owner, runtime=mode)
                    record.update(owner=owner, registered=bool(request.get('start')),
                                  unit_sha256=hashlib.sha256(Path(record['unit_path']).read_bytes()).hexdigest())
                    atomic_json(root / 'installation.json', record)
                    launcher = root / 'handler.py'
                    source = ('import json,os,sys\nfrom pathlib import Path\n'
                              'p=Path(__file__).resolve().parent\n'
                              'r=json.loads((p/"installation.json").read_text())\n'
                              'os.execv(sys.executable,[sys.executable,"-B",r["program"],*sys.argv[1:]])\n')
                    if launcher.is_symlink() or (launcher.exists() and launcher.read_text() != source):
                        raise ValueError('Qrun handler launcher changed outside the installer')
                    launcher.write_text(source)
                    launcher.chmod(0o700)
                    record.update(owner=owner, registered=bool(request.get('start')),
                                  handler=[sys.executable, '-B', str(launcher), '--state-dir', str(root), 'handler'],
                                  unit_sha256=hashlib.sha256(Path(record['unit_path']).read_bytes()).hexdigest())
                    atomic_json(root / 'installation.json', record)
                elif operation == 'restore':
                    if registered:
                        service_command(root, 'disable', old['unit'])
                    mutated = True
                    saved = json.loads(pending.read_text()) if pending.exists() else snapshot
                    _restore_files(root, saved)
                    record = saved['record']
                else:
                    if registered:
                        service_command(root, 'disable', old['unit'])
                    mutated = True
                    Path(old['unit_path']).unlink(missing_ok=True)
                    record = {**old, 'removed': True}
                    atomic_json(root / 'installation.json', record)
            if operation == 'install':
                if request.get('start'):
                    activation_attempted = True
                    activate(root, record)
                elif registered:
                    service_command(root, 'disable', old['unit'])
                    service_command(root, 'daemon-reload')
                return {**record, 'capacity': {key: config[key] for key in ('cpus', 'memory_mb')}, 'snapshot': True}
            if registered:
                service_command(root, 'daemon-reload')
            if operation == 'restore' and record and not record.get('removed'):
                if saved['enabled']:
                    service_command(root, 'enable', record['unit'])
                if saved['active']:
                    service_command(root, 'start', record['unit'])
            pending.unlink(missing_ok=True)
            if operation == 'remove' and request.get('purge'):
                shutil.rmtree(root)
            return {'removed': operation == 'remove', 'restored': operation == 'restore', 'state_retained': not request.get('purge')}
        except BaseException:
            if mutated:
                # Activation can fail after systemd accepted the start request.
                # Stop that daemon before restoring files it may be using.
                if activation_attempted:
                    service_command(root, 'stop', record['unit'])
                    service_command(root, 'disable', record['unit'])
                _restore_files(root, snapshot)
                if registered or activation_attempted:
                    service_command(root, 'daemon-reload')
            if enabled:
                service_command(root, 'enable', old['unit'])
            if active:
                service_command(root, 'start', old['unit'])
            if mutated and operation == 'install':
                pending.unlink(missing_ok=True)
            raise


def printable(value):
    return ''.join(char if char in '\n\t' or char.isprintable() else '?' for char in str(value))


ANSI_RESET = '\033[0m'
ANSI_BOLD = '\033[1m'
ANSI_DIM = '\033[2m'
ANSI_RED = '\033[31m'
ANSI_GREEN = '\033[32m'
ANSI_YELLOW = '\033[33m'
ANSI_CYAN = '\033[36m'


def color_enabled(stream=None):
    """Return whether human-readable output should use ANSI emphasis."""
    stream = sys.stdout if stream is None else stream
    if os.environ.get('NO_COLOR') is not None or os.environ.get('TERM') == 'dumb':
        return False
    try:
        return bool(stream.isatty())
    except (AttributeError, OSError):
        return False


def paint(value, color, *, enabled):
    text = str(value)
    return color + text + ANSI_RESET if enabled else text


def state_color(state):
    return {
        'succeeded': ANSI_GREEN,
        'running': ANSI_CYAN,
        'starting': ANSI_CYAN,
        'stopping': ANSI_YELLOW,
        'queued': ANSI_YELLOW,
        'cancelled': ANSI_YELLOW,
        'timed_out': ANSI_RED,
        'failed': ANSI_RED,
        'unknown': ANSI_RED,
    }.get(state, ANSI_DIM)


def cli_result(value, command):
    """Add CLI metadata without moving or renaming existing response fields."""
    return {**value, 'cli_version': CLI_VERSION, 'ok': True, 'command': command}


def cli_error(exc, command, *, code=None):
    if isinstance(exc, QueryError):
        error = dict(exc.error)
    else:
        error = {'code': code or getattr(exc, 'code', None) or (
            'state_unavailable' if isinstance(exc, (OSError, sqlite3.Error, json.JSONDecodeError)) else
            'invalid_arguments' if isinstance(exc, ValueError) else 'qrun_error'),
            'message': str(exc), 'retryable': False,
            'action_outcome': getattr(exc, 'outcome', 'unknown')}
    error.setdefault('code', 'qrun_error')
    error.setdefault('retryable', False)
    error.setdefault('action_outcome', 'unknown')
    error['recovery'] = {
        'invalid_arguments': 'Check qrun COMMAND --help and correct the arguments.',
        'job_not_found': 'Check the execution host, state directory and numeric job ID with jobs --json.',
        'state_unavailable': 'Check the state directory, installation and file permissions.',
        'response_too_large': 'Reduce jobs --limit or logs --bytes and query again.',
    }.get(error['code'], 'Read status/config/show before retrying a mutation; an unacknowledged operation may have applied.')
    return {'cli_version': CLI_VERSION, 'ok': False, 'command': command, 'error': error}


class CLIUsageError(ValueError):
    outcome = 'not_submitted'


class CLIParser(argparse.ArgumentParser):
    def error(self, message):
        raise CLIUsageError(message)


def display(value, *, as_json=False, color=None):
    if color is None:
        color = not as_json and color_enabled()
    if as_json:
        print(json.dumps(value, ensure_ascii=True), flush=True)
        return
    if not value.get('online', True):
        print(paint('OFFLINE — saved state only; last heartbeat: ' + str(value.get('last_heartbeat')),
                    ANSI_RED + ANSI_BOLD, enabled=color))
    if 'capacity' in value:
        mode = 'OFFLINE' if not value.get('online', True) else ('PAUSED' if value['paused'] else 'dispatching')
        mode_color = ANSI_RED if mode == 'OFFLINE' else (ANSI_YELLOW if value['paused'] else ANSI_GREEN)
        print('Qrun ' + paint(value['runtime'], ANSI_CYAN, enabled=color) + ' | ' +
              paint(mode, mode_color + (ANSI_BOLD if value['paused'] else ''), enabled=color))
        print(f"{'Resource':<12} {'Budget':>12} {'Reserved':>12} {'Free':>12} {'Over budget':>12}")
        for key, label in (('cpus', 'CPU'), ('memory_mb', 'Memory MiB')):
            columns = []
            for name in ('capacity', 'reserved', 'free', 'overcommitted'):
                text = f"{value[name][key]:>13}"
                if name == 'overcommitted' and value[name][key]:
                    text = paint(text, ANSI_RED + ANSI_BOLD, enabled=color)
                elif name == 'free' and value[name][key]:
                    text = paint(text, ANSI_GREEN, enabled=color)
                columns.append(text)
            print(f"{label:<12}" + ''.join(columns))
        usage = value['job_usage']
        # Old daemons may not yet provide completeness-aware totals.
        complete = usage.get('complete', value.get('online', True) and not usage['missing_or_stale_jobs'])
        cpu = usage['cpu_cores'] if complete else '-'
        memory = usage['memory_mb'] if complete else '-'
        print(f"Job usage: {cpu} CPU cores, {memory} MiB RSS/current; " +
              paint(f"{usage['missing_or_stale_jobs']} missing/stale", ANSI_YELLOW,
                    enabled=color and bool(usage['missing_or_stale_jobs'])))
        host = value.get('host')
        if host:
            print(f"Host: {host['logical_cpus']} logical CPUs ({host['allowed_cpus']} allowed), "
                  f"busy {host['cpu_busy_percent']}%; available memory {host['memory_available_mb']} MiB")
        states = []
        for key, number in sorted(value['states'].items()):
            states.append(paint(f'{key}={number}', state_color(key), enabled=color))
        print('Jobs: ' + (', '.join(states) or 'none'))
        print('Memory enforcement: ' + value['memory_enforcement'])
    elif 'jobs' in value:
        print(f"{'ID':>6} {'STATE':<10} {'CPU':>4} {'MEM MiB':>8} {'CPU used':>8} {'RSS MiB':>9}  WAIT")
        for row in value['jobs']:
            usage = row['usage']
            measured = usage['available'] and not usage['stale']
            reason = row['wait_reason']
            wait = '' if reason is None else reason['code'] + (
                ' ' + reason['blocked_by'] if 'blocked_by' in reason else '')
            state = paint(f"{row['state']:<10}", state_color(row['state']), enabled=color)
            wait = paint(wait, ANSI_YELLOW, enabled=color) if wait else wait
            print(f"{row['id']:>6} {state} {row['cpus']:>4} {row['memory_mb']:>8} "
                  f"{usage.get('cpu_cores') if measured else '-':>8} {usage.get('memory_mb') if measured else '-':>9}  "
                  + wait)
        print(f"{len(value['jobs'])} shown / {value['total']} matching (offset {value['offset']})")
    elif 'job' in value:
        for key, item in value['job'].items():
            if key in {'seq', 'request_id', 'unit'}:
                continue
            rendered = printable(json.dumps(item, ensure_ascii=True) if isinstance(item, (dict, list)) else item)
            if key == 'state':
                rendered = paint(rendered, state_color(str(item)), enabled=color)
            elif key == 'error' and item:
                rendered = paint(rendered, ANSI_RED, enabled=color)
            elif key == 'wait_reason' and item:
                rendered = paint(rendered, ANSI_YELLOW, enabled=color)
            print(f'{key}: ' + rendered)
    elif value.get('accepted') is True and 'scheduler_id' in value:
        print(paint('Cancellation accepted for job ' + str(value['scheduler_id']) + '.', ANSI_YELLOW, enabled=color))
        print('This does not confirm termination. Check: qrun show ' + str(value['scheduler_id']))
    else:
        print(json.dumps(value, ensure_ascii=True))


def operator_command(root, args):
    action = args.action
    if action == 'logs':
        request = {'action': 'logs', 'identifier': args.identifier, 'stream': args.stream, 'bytes': args.bytes}
        if args.offset is not None:
            request.update(offset=args.offset, identity=args.identity)
        while True:
            value = query(root, request)
            if not value['online'] and not args.json:
                print(paint('OFFLINE — retained log only.', ANSI_RED + ANSI_BOLD,
                            enabled=color_enabled(sys.stderr)), file=sys.stderr)
            if args.json:
                display(cli_result(value, action), as_json=True)
            else:
                print(printable(value['text']), end='', flush=True)
                if not value['available'] and (not args.follow or value['finished']):
                    print('No retained log for this job.', file=sys.stderr)
            if not args.follow or not value['online'] or (value['finished'] and value['eof']):
                break
            request.update(offset=value['offset'], identity=value['identity'])
            if value['eof']:
                time.sleep(args.interval)
        return
    if action == 'watch':
        count = 0
        while args.count is None or count < args.count:
            overview = query(root, {'action': 'overview'})
            jobs = query(root, {'action': 'jobs'})
            if args.json:
                display(cli_result({'overview': overview, 'jobs': jobs}, action), as_json=True)
            else:
                if sys.stdout.isatty() and os.environ.get('TERM') != 'dumb':
                    print('\033[2J\033[H', end='')
                display(overview)
                display(jobs)
            count += 1
            if args.count is None or count < args.count:
                time.sleep(args.interval)
        return
    request = {'action': {'status': 'overview', 'config': 'configure', 'cancel': 'cancel_job'}.get(action, action)}
    if action == 'config':
        request.update({key: getattr(args, key) for key in ('cpus', 'memory_mb') if getattr(args, key) is not None})
        if len(request) == 1:
            request['action'] = 'overview'
    if action in {'show', 'cancel'}:
        request['identifier'] = args.identifier
    if action == 'jobs':
        request.update(states=args.state, all=args.all, limit=args.limit, offset=args.offset)
    value = query(root, request)
    display(cli_result(value, action) if args.json else value, as_json=args.json)


CLI_COMMANDS = (
    ('Inspect jobs', (
        ('status', 'queue overview'),
        ('jobs', 'unfinished jobs; --all includes history'),
        ('list', 'legacy full ledger JSON export; use jobs for tables'),
        ('show', 'job details by numeric ID'),
        ('logs', 'tail retained output'),
        ('resources', 'budget, reservations and actual host/job usage'),
        ('watch', 'refresh resources and live jobs'),
    )),
    ('Control the queue', (
        ('pause', 'pause new dispatch; keep running jobs'),
        ('resume', 'resume dispatch'),
        ('cancel', 'request cancellation by numeric job ID'),
        ('config', 'show or resize budget without stopping jobs'),
    )),
    ('Installation and service', (
        ('install', 'install Qrun and its queue service on this host'),
        ('service', 'manage the installed queue daemon'),
        ('init', 'create a pool without starting services'),
        ('unit', 'print the systemd service definition'),
    )),
)


def cli_help(*, full=False):
    sections = []
    for title, entries in CLI_COMMANDS:
        sections.append(title + ':\n' + '\n'.join(f'  {name:<12} {description}' for name, description in entries))
    sections.append('Examples:\n  qrun jobs\n  qrun jobs --all --limit 20\n  qrun show 4\n  qrun watch')
    sections.append('Use qrun COMMAND --help for options. Query commands support --json.')
    sections.append('Use qrun --help-all for automation, protocol and internal entrypoints.')
    if full:
        sections.append('Automation:\n'
            '  qrun jobs --all --limit 20 --json\n'
            '  qrun show 4 --json\n'
            '  qrun watch --count 1 --json\n'
            '  qrun --state-dir /absolute/pool handler < request.json\n\n'
            'Operator JSON: qrun-cli/1 metadata; existing view fields stay at the top level.\n'
            'Exit codes: 0 success (including stale reads), 1 operation error, 2 usage error,\n'
            '130 interrupted JSON command. watch and logs --follow emit flushed JSON Lines.\n'
            'Read ok, online, stale and job_usage.complete; accepted cancellation is not termination.\n'
            'Follow next_offset until null; pages are live and may change between calls.\n'
            'list is the legacy unbounded array exception, with no freshness guarantee.')
        sections.append('Machine protocol:\n'
            '  handler       one coragent-external-job/1 JSON request on stdin\n'
            '                actions: probe, submit, recover, status, cancel; queue views/controls\n'
            '                unchanged protocol envelope; errors are JSON, exit status is 0\n'
            '                preserve request_id and request fields; recover after response loss\n\n'
            'Internal lifecycle (not job submission interfaces):\n'
            '  maintenance   installer-owned lifecycle request on stdin\n'
            '  serve         run the queue daemon in the foreground\n'
            '  _run          systemd worker entrypoint\n'
            '  _portable-run portable worker entrypoint\n\n'
            'See docs/QRUN.md or docs/QRUN.zh-CN.md for the machine contract.')
    return '\n\n'.join(sections)


def main(argv=None):
    if sys.version_info < (3, 11):
        print('Qrun requires Python 3.11 or newer', file=sys.stderr)
        return 1
    os.umask(0o077)
    argv = list(sys.argv[1:] if argv is None else argv)
    json_requested = '--json' in argv
    parser = CLIParser(prog='qrun', description='Qrun: a durable CPU/memory job queue for this host.',
        formatter_class=argparse.RawDescriptionHelpFormatter, epilog=cli_help(full='--help-all' in argv),
        usage='%(prog)s [-h] [--state-dir STATE_DIR] COMMAND ...')
    parser.add_argument('--help-all', action='help', help='show automation and internal entrypoint help')
    parser.add_argument('--state-dir', type=Path, default=Path.home() / '.local/state/coragent/qrun')
    commands = parser.add_subparsers(prog='qrun', dest='action', required=True, metavar='COMMAND', help=argparse.SUPPRESS)
    descriptions = dict(entry for _, entries in CLI_COMMANDS for entry in entries)

    def command_parser(name):
        return commands.add_parser(name, description=descriptions[name])

    init = command_parser('init')
    init.add_argument('--cpus', type=int, required=True)
    init.add_argument('--memory-mb', type=int, required=True)
    init.add_argument('--work-root', action='append', required=True)
    init.add_argument('--runtime', choices=('auto', 'systemd', 'portable'), default='auto')
    installer = command_parser('install')
    installer.add_argument('--cpus', type=int, required=True)
    installer.add_argument('--memory-mb', type=int, required=True)
    installer.add_argument('--work-root', action='append', required=True)
    installer.add_argument('--no-start', action='store_true', help='write installation without contacting the service manager')
    installer.add_argument('--runtime', choices=('auto', 'systemd', 'portable'), default='auto')
    service = command_parser('service')
    service.add_argument('operation', choices=('start', 'stop', 'status', 'ensure'))
    commands.add_parser('maintenance', help='installation-owned lifecycle request on stdin')
    commands.add_parser('handler', description='Read one coragent-external-job/1 JSON request from stdin; '
        'write one protocol response. See --help-all and the Qrun machine contract.')
    commands.add_parser('serve', help='run the persistent queue daemon')
    command_parser('unit')
    listing = command_parser('list')
    listing.add_argument('--json', action='store_true', help='explicit legacy JSON export (also the default)')
    for name in ('status', 'resources', 'pause', 'resume', 'config', 'jobs', 'show', 'logs', 'watch'):
        command = command_parser(name)
        command.add_argument('--json', action='store_true')
        if name in {'show', 'logs'}:
            command.add_argument('identifier')
        if name == 'config':
            command.add_argument('--cpus', type=int)
            command.add_argument('--memory-mb', type=int)
        if name == 'jobs':
            command.add_argument('--all', action='store_true', help='include history, newest first')
            command.add_argument('--state', action='append', choices=sorted(ACTIVE | TERMINAL | {'queued'}))
            command.add_argument('--limit', type=int, default=50)
            command.add_argument('--offset', type=int, default=0)
        if name == 'logs':
            command.add_argument('--stream', choices=('stdout', 'stderr'), default='stdout')
            command.add_argument('--bytes', type=int, default=16384, help='tail/chunk bytes, at most 65536')
            command.add_argument('--follow', '-f', action='store_true')
            command.add_argument('--offset', type=int, help='resume from a returned byte offset; pair with --identity')
            command.add_argument('--identity', help='file identity returned by an earlier logs --json response')
        if name in {'watch', 'logs'}:
            command.add_argument('--interval', type=float, default=2)
        if name == 'watch':
            command.add_argument('--count', type=int)
    cancel = command_parser('cancel')
    cancel.add_argument('identifier')
    cancel.add_argument('--json', action='store_true')
    worker = commands.add_parser('_run', help=argparse.SUPPRESS)
    worker.add_argument('identifier')
    portable_worker = commands.add_parser('_portable-run', help=argparse.SUPPRESS)
    portable_worker.add_argument('identifier')
    try:
        args = parser.parse_args(argv)
    except CLIUsageError as exc:
        if json_requested:
            display(cli_error(exc, None, code='invalid_arguments'), as_json=True)
        else:
            parser.print_usage(sys.stderr)
            print('qrun: error: ' + str(exc), file=sys.stderr)
        return 2
    json_requested = getattr(args, 'json', False)
    try:
        root = args.state_dir.expanduser().resolve()
        if hasattr(args, 'interval') and not .2 <= args.interval <= 3600:
            raise ValueError('interval must be between 0.2 and 3600 seconds')
        if args.action == 'watch' and args.count is not None and args.count < 1:
            raise ValueError('count must be positive')
        if args.action in {'status', 'resources', 'jobs', 'show', 'logs', 'watch', 'pause', 'resume', 'config', 'cancel'}:
            operator_command(root, args)
        elif args.action == 'maintenance':
            print(json.dumps(maintain(args.state_dir, json.load(sys.stdin))))
        elif args.action == 'init':
            print(json.dumps(initialize(args.state_dir, args.cpus, args.memory_mb, args.work_root, runtime=args.runtime)))
        elif args.action == 'install':
            print(json.dumps(install(args.state_dir, args.cpus, args.memory_mb, args.work_root, start=not args.no_start, runtime=args.runtime)))
        elif args.action == 'service':
            with lock(root / 'maintenance.lock', nonblocking=True):
                record = json.loads((root / 'installation.json').read_text())
                if args.operation == 'ensure':
                    if record.get('runtime') != 'portable' or record.get('removed') or not portable_enabled(root):
                        return 0
                    print(service_command(root, 'start', record['unit']))
                else:
                    print(service_command(root, 'show' if args.operation == 'status' else args.operation, record['unit']))
        elif args.action == 'unit':
            if json.loads((root / 'config.json').read_text()).get('runtime') == 'portable':
                raise ValueError('portable Qrun uses user cron; manage it with the service command')
            print(unit_text(root, Path(__file__).resolve()), end='')
        elif args.action == 'serve':
            serve(args.state_dir)
        elif args.action == '_run':
            return run_job(root, args.identifier)
        elif args.action == '_portable-run':
            return portable_run(root, args.identifier)
        elif args.action == 'list':
            connection = sqlite3.connect((root / 'queue.sqlite3').as_uri() + '?mode=ro', uri=True)
            connection.row_factory = sqlite3.Row
            try:
                print(json.dumps([dict(row) for row in connection.execute(
                    'SELECT CAST(seq AS TEXT) AS id,state,cpus,memory_mb,created_at,started_at,finished_at,error FROM jobs ORDER BY seq')]))
            finally:
                connection.close()
        else:
            raw = sys.stdin.buffer.read(MAX_MESSAGE + 1)
            if len(raw) > MAX_MESSAGE:
                raise ValueError('Qrun request too large')
            request = json.loads(raw)
            if not isinstance(request, dict):
                raise ValueError('Qrun request must be an object')
            print(json.dumps(client(root, request)))
    except KeyboardInterrupt:
        if json_requested:
            display(cli_error(RuntimeError('Command interrupted; query state to determine whether an in-flight operation applied'),
                              args.action, code='interrupted'), as_json=True)
            return 130
        return 0
    except (OSError, ValueError, RuntimeError, sqlite3.Error, subprocess.SubprocessError) as exc:
        if args.action == 'handler':
            print(json.dumps({'schema_version': PROTOCOL, 'error': {'code': 'qrun_unavailable',
                'message': str(exc), 'retryable': True, 'action_outcome': 'unknown'}}))
            return 0
        if json_requested:
            display(cli_error(exc, args.action), as_json=True)
            return 1
        print(paint(str(exc), ANSI_RED, enabled=color_enabled(sys.stderr)), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
