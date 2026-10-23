"""Installation-owned Qrun pools, using the same lifecycle locally and over SSH."""
from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess

try:
    from .app_layout import paths as app_paths
    from ._job_install import write_private
except ImportError:
    from app_layout import paths as app_paths
    from _job_install import write_private

REGISTRY = 'installation/qrun-pools.json'
SOURCE = 'backend/src/research_agent/jobs/qrun.py'


def options(parser):
    parser.add_argument('--manage-qrun', action='append', metavar='PLATFORM/ENTRY',
                        help='Manage this Qrun target, including SSH deployment. Local default handlers are managed automatically.')
    parser.add_argument('--qrun-state-dir', action='append', metavar='PLATFORM/ENTRY=PATH',
                        help='Dedicated queue state directory on the execution host; required for new managed SSH pools.')
    parser.add_argument('--qrun-cpus', action='append', metavar='PLATFORM/ENTRY=N', help='CPU capacity of a managed Qrun pool.')
    parser.add_argument('--qrun-memory-mb', action='append', metavar='PLATFORM/ENTRY=N', help='Memory capacity of a managed Qrun pool in MiB.')
    parser.add_argument('--qrun-runtime', action='append', metavar='PLATFORM/ENTRY=MODE',
                        help='Qrun internal runtime: auto, systemd or portable (CentOS 7).')
    parser.add_argument('--without-managed-qrun', action='store_true', help='Use separately managed Qrun pools; do not provision them.')


def owner(root):
    return 'coragent-' + hashlib.sha256(os.fsencode(Path(root).resolve())).hexdigest()


def registry(root):
    path = app_paths(root).state / REGISTRY
    if path.is_symlink():
        raise ValueError('Qrun ownership registry cannot be a symlink')
    if not path.exists():
        return {'schema_version': 'coragent-qrun-install/1', 'owner': owner(root), 'pools': []}
    value = json.loads(path.read_text())
    if value.get('schema_version') != 'coragent-qrun-install/1' or value.get('owner') != owner(root):
        raise ValueError('Qrun ownership registry does not match this installation')
    if not isinstance(value.get('pools'), list):
        raise ValueError('invalid Qrun pool registry')
    return value


def save(root, value):
    write_private(app_paths(root).state / REGISTRY, (json.dumps(value, indent=2) + '\n').encode())


def route_identity(route):
    return {key: route[key] for key in ('transport', 'ssh_host', 'ssh_config') if key in route}


def assignments(values, targets, *, numeric=False):
    result = {}
    for value in values or []:
        name, separator, item = value.partition('=')
        if not separator or name not in targets or name in result:
            raise ValueError('Qrun options require unique configured PLATFORM/ENTRY=value assignments')
        if numeric:
            if not item.isdecimal() or int(item) < 1:
                raise ValueError('Qrun pool capacity must be positive')
            item = int(item)
        elif not item.startswith('/') or item == '/' or '..' in Path(item).parts or any(c in item for c in '\n\r\0'):
            raise ValueError('Qrun state directory must be a dedicated absolute path')
        result[name] = item
    return result


def plan(args, settings):
    root = Path(args.install_root).expanduser().resolve()
    previous = registry(root)
    targets = settings['targets']
    selected = set(getattr(args, 'manage_qrun', None) or [])
    states = assignments(getattr(args, 'qrun_state_dir', None), targets)
    cpus = assignments(getattr(args, 'qrun_cpus', None), targets, numeric=True)
    memory = assignments(getattr(args, 'qrun_memory_mb', None), targets, numeric=True)
    modes = {}
    for value in getattr(args, 'qrun_runtime', None) or []:
        name, separator, mode = value.partition('=')
        if not separator or name not in targets or name in modes or mode not in {'auto', 'systemd', 'portable'}:
            raise ValueError('--qrun-runtime requires unique PLATFORM/ENTRY=auto|systemd|portable assignments')
        modes[name] = mode
    if selected - targets.keys():
        raise ValueError('managed Qrun target is not configured')
    if getattr(args, 'without_managed_qrun', False):
        if selected or states or cpus or memory or modes:
            raise ValueError('--without-managed-qrun conflicts with Qrun provisioning options')
        return []
    pools = {}
    for name, target in targets.items():
        prior = next((p for p in previous['pools'] if name in p['targets']), None)
        default_handler = target.get('handler') == ['qrun', 'handler']
        managed_handler = prior and target.get('handler') == prior.get('handler')
        requested = name in selected or name in states or name in cpus or name in memory or name in modes
        if target['executor'] != 'qrun':
            if requested:
                raise ValueError('Qrun provisioning requires executor=qrun: ' + name)
            continue
        if not requested and not (prior and prior.get('pending')) and not managed_handler and not (target['transport'] == 'local' and default_handler):
            continue
        if not default_handler and not managed_handler and not (prior and prior.get('pending')):
            raise ValueError('refusing to replace a separately managed Qrun handler: ' + name)
        route = {key: target[key] for key in ('transport', 'ssh_host', 'ssh_config', 'connect_timeout_seconds') if key in target}
        if prior and route_identity(prior['route']) != route_identity(route):
            raise ValueError('managed Qrun route changed; remove the old pool before changing its host')
        local = target['transport'] == 'local'
        if not local and not prior and not (name in states and name in cpus and name in memory):
            raise ValueError('new managed SSH Qrun requires --qrun-state-dir, --qrun-cpus and --qrun-memory-mb')
        state = states.get(name, prior['state_dir'] if prior else str(app_paths(root).state / 'qrun'))
        if prior and state != prior['state_dir']:
            raise ValueError('managed Qrun state directory cannot change during upgrade')
        key = json.dumps(route_identity(route), sort_keys=True)
        if key in pools and pools[key]['state_dir'] != state:
            raise ValueError('one managed Qrun pool per host; use the same state directory for its targets')
        available = len(os.sched_getaffinity(0)) if hasattr(os, 'sched_getaffinity') else (os.cpu_count() or 1)
        ram = os.sysconf('SC_PHYS_PAGES') * os.sysconf('SC_PAGE_SIZE') // (1024 * 1024)
        row = pools.setdefault(key, {'route': route, 'state_dir': state, 'targets': [], 'work_roots': [],
            'cpus': prior['cpus'] if prior else max(1, available - 1),
            'runtime': prior.get('runtime', 'auto') if prior else 'auto',
            'memory_mb': prior['memory_mb'] if prior else max(1, ram * 3 // 4)})
        row['targets'].append(name)
        row['work_roots'].append(target['work_root'])
        for field, values in (('cpus', cpus), ('memory_mb', memory), ('runtime', modes)):
            if name in values:
                if field + '_explicit' in row and row[field] != values[name]:
                    raise ValueError('targets sharing a Qrun pool must use the same capacity')
                row[field] = values[name]
                row[field + '_explicit'] = True
    for row in pools.values():
        row['capacity_overrides'] = [key for key in ('cpus', 'memory_mb') if row.get(key + '_explicit')]
        row.pop('cpus_explicit', None)
        row.pop('memory_mb_explicit', None)
        row.pop('runtime_explicit', None)
        row['work_roots'] = sorted(set(row['work_roots']))
        row['targets'].sort()
        if row['route']['transport'] == 'local' and getattr(args, 'service_scope', None) == 'system':
            import pwd
            if getattr(args, 'service_user', None) != pwd.getpwuid(os.getuid()).pw_name:
                raise ValueError('manage local Qrun as the execution account, or configure a separately managed handler')
    return list(pools.values())


def program(package):
    path = Path(package) / SOURCE
    if path.is_file():
        return path
    recovery = Path(__file__).with_name('qrun.py')
    return recovery if recovery.is_file() else Path(__file__).resolve().parents[1] / SOURCE


def invoke(pool, operation, installation, package, **fields):
    request = {'operation': operation, 'owner': owner(installation), **fields}
    route = pool['route']
    if route['transport'] == 'local':
        # The queue must not depend on the application's replaceable Conda runtime.
        command = ['/usr/bin/python3', '-B', str(program(package)), '--state-dir', pool['state_dir'], 'maintenance']
        payload = request
    else:
        # Send only the standalone queue program and this explicit pool request.
        # No installation config, credentials or controller environment is sent.
        bootstrap = ("import sys,json,base64,tempfile,pathlib,subprocess; p=json.load(sys.stdin); "
            "d=tempfile.TemporaryDirectory(prefix='coragent-qrun-'); f=pathlib.Path(d.name)/'qrun.py'; "
            "f.write_bytes(base64.b64decode(p['program'])); "
            "r=subprocess.run([sys.executable,'-B',str(f),'--state-dir',p['state_dir'],'maintenance'],"
            "input=json.dumps(p['request']).encode()); d.cleanup(); sys.exit(r.returncode)")
        command = ['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=' + str(route.get('connect_timeout_seconds', 15))]
        if route.get('ssh_config'):
            command += ['-F', route['ssh_config']]
        command += [route['ssh_host'], 'python3 -B -c ' + shlex.quote(bootstrap)]
        payload = {'program': base64.b64encode(program(package).read_bytes()).decode(),
                   'state_dir': pool['state_dir'], 'request': request}
    try:
        result = subprocess.run(command, input=json.dumps(payload), text=True, capture_output=True, timeout=90)
    except subprocess.TimeoutExpired as error:
        raise RuntimeError('Qrun ' + operation + ' timed out; remote outcome may be unknown') from error
    if result.returncode:
        raise RuntimeError('Qrun ' + operation + ' failed: ' + result.stderr.strip()[:1000])
    return json.loads(result.stdout)


def prepare(value, args, package):
    root = Path(value['install_root'])
    state = registry(root)
    changes = []
    try:
        for pool in value.get('qrun', []):
            index = next((i for i, row in enumerate(state['pools']) if route_identity(row['route']) == route_identity(pool['route'])
                          and row['state_dir'] == pool['state_dir']), None)
            previous = state['pools'][index] if index is not None else None
            if previous and previous.get('pending'):
                operation = 'commit' if previous.get('published') else 'restore'
                invoke(pool, operation, root, package, cancel_jobs=True)
                previous = {**previous, 'pending': False} if operation == 'commit' else previous.get('previous')
            record = {**pool, 'pending': True, 'previous': previous}
            if index is None:
                state['pools'].append(record)
                index = len(state['pools']) - 1
            else:
                state['pools'][index] = record
            # Register before remote effects: a lost SSH response remains recoverable.
            save(root, state)
            changes.append({'pool': pool, 'previous': previous, 'index': index})
            result = invoke(pool, 'install', root, package, cpus=pool['cpus'], memory_mb=pool['memory_mb'],
                            work_roots=pool['work_roots'], runtime=pool.get('runtime', 'auto'),
                            capacity_overrides=pool.get('capacity_overrides', ['cpus', 'memory_mb']),
                            start=getattr(args, 'service_scope', None) != 'none')
            record.update(handler=result['handler'], unit=result['unit'])
            record.update(result.get('capacity', {}))
            pool.update(result.get('capacity', {}))
            record['runtime'] = result.get('runtime', pool.get('runtime', 'auto'))
            pool['runtime'] = record['runtime']
            save(root, state)
            for name in pool['targets']:
                value['settings']['targets'][name]['handler'] = result['handler']
        return {'root': root, 'package': package, 'changes': changes}
    except BaseException as error:
        try:
            rollback({'root': root, 'package': package, 'changes': changes})
        except Exception as recovery_error:
            raise RuntimeError(str(error) + '; Qrun recovery incomplete; ownership record retained: ' + str(recovery_error)) from error
        raise


def rollback(transaction):
    root, package = transaction['root'], transaction['package']
    state = registry(root)
    for change in reversed(transaction['changes']):
        if state['pools'][change['index']].get('published'):
            continue
        invoke(change['pool'], 'restore', root, package, cancel_jobs=True)
        row = change['previous'] or {**change['pool'], 'removed': True}
        state['pools'][change['index']] = row
        save(root, state)


def commit(transaction):
    state = registry(transaction['root'])
    for change in transaction['changes']:
        state['pools'][change['index']]['published'] = True
    save(transaction['root'], state)
    for change in transaction['changes']:
        invoke(change['pool'], 'commit', transaction['root'], transaction['package'])
        state['pools'][change['index']]['pending'] = False
        state['pools'][change['index']].pop('previous', None)
        save(transaction['root'], state)


def remove(root, args, package):
    state = registry(root)
    if getattr(args, 'remove_root', False) and not getattr(args, 'purge_qrun_state', False):
        if any(pool['route']['transport'] == 'local' and Path(pool['state_dir']).is_relative_to(root)
               for pool in state['pools']):
            raise ValueError('--remove-root requires --purge-qrun-state for queue history inside the installation')
    results = []
    for pool in state['pools']:
        if pool.get('removed') and not getattr(args, 'purge_qrun_state', False):
            continue
        result = invoke(pool, 'remove', root, package, cancel_jobs=bool(getattr(args, 'cancel_qrun_jobs', False)),
                        purge=bool(getattr(args, 'purge_qrun_state', False)))
        pool.update(removed=True, pending=False)
        save(root, state)
        results.append({'targets': pool['targets'], **result})
    return results
