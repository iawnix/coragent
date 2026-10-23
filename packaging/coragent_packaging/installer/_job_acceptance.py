"""Run bounded offline installation Jobs through the ordinary runtime APIs."""
from __future__ import annotations

import sys
from pathlib import Path

if __name__ == "__main__":
    package_root = Path(__file__).resolve().parents[3]
    sys.path[:0] = [str(package_root / "packaging"), str(package_root / "backend/src"), str(package_root)]

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import time
import shlex
import shutil
import tempfile

from coragent_packaging.installer._job_install import profiles, resource, write_private
from research_agent.application.api import execute
from research_agent.application.environment_check import check_environments
from research_agent.application.executors import prepare, prepare_script
from research_agent.jobs.config_contract import binding_digest, configured_targets, load_job_config, target_identity, target_key
from research_agent.jobs.staged import staged_directory
from research_agent.research.workspace import initialize_workspace, admit_research_workspace


TERMINAL = {'succeeded', 'failed', 'cancelled', 'timed_out', 'collected'}


class AcceptanceJobError(RuntimeError):
    def __init__(self, message, receipt, status):
        super().__init__(message)
        diagnostics = status.get('diagnostics') or {}
        self.job = {'job_id': receipt['job_id'], 'status': 'failed',
                    'actual_node': diagnostics.get('node'), 'diagnostics': diagnostics,
                    'error': message}


def run_job(root, request, timeout):
    path = root / (request['request_id'] + '.json')
    raw = (json.dumps(request) + '\n').encode()
    write_private(path, raw)
    receipt = execute('job_start', root, {'request_file': str(path), 'request_sha256': hashlib.sha256(raw).hexdigest()})
    deadline = time.monotonic() + timeout
    terminal, collected_outputs = False, False
    try:
        while time.monotonic() < deadline:
            status = execute('job_status', root, {'job_id': receipt['job_id']})
            if status['state'] in TERMINAL:
                terminal = True
                if status['state'] != 'succeeded':
                    raise AcceptanceJobError('acceptance_job_' + status['state'], receipt, status)
                collected = execute('job_collect', root, {'job_id': receipt['job_id']})
                collected_outputs = True
                if not collected['output_validation']['complete']:
                    raise AcceptanceJobError('acceptance_outputs_incomplete', receipt, status)
                diagnostics = status.get('diagnostics') or {}
                return {'job_id': receipt['job_id'], 'status': 'execution_verified', 'cwd': receipt['cwd'],
                        'actual_node': diagnostics.get('node'),
                        'diagnostics': diagnostics}
            time.sleep(.2)
        raise RuntimeError('acceptance_queue_or_execution_timeout')
    finally:
        if not terminal:
            execute('job_cancel', root, {'job_id': receipt['job_id']})
            cleanup = time.monotonic() + min(30, timeout)
            while time.monotonic() < cleanup:
                if execute('job_status', root, {'job_id': receipt['job_id']})['state'] in TERMINAL:
                    terminal = True
                    break
                time.sleep(.2)
            if not terminal:
                raise RuntimeError('acceptance_cancellation_pending:' + receipt['job_id'])
        if (terminal and receipt.get('metadata', {}).get('remote_dir')
                and receipt['metadata'].get('file_mode', 'staged') != 'shared'):
            if not collected_outputs:
                execute('job_collect', root, {'job_id': receipt['job_id']})
            from research_agent.jobs import platforms_from_config
            settings = load_job_config(os.environ['CORAGENT_JOB_CONFIG'])
            target = configured_targets(settings)[target_key(request['execution_target'])]
            remote = receipt['metadata']['remote_dir']
            expected = staged_directory(target['work_root'], receipt['cwd'], receipt['job_id'], receipt['workspace_id'])
            if remote != expected:
                raise RuntimeError('acceptance_cleanup_path_mismatch')
            platform = platforms_from_config(Path(os.environ['CORAGENT_JOB_CONFIG']))[0][target_key(request['execution_target'])]
            platform.run_command('rm -rf -- ' + shlex.quote(remote))


def accept(config, package, directory, targets, timeout, *, bindings_only=False, expected_node=None):
    os.environ['CORAGENT_JOB_CONFIG'] = str(config)
    os.environ['CORAGENT_PACKAGE_ROOT'] = str(package)
    settings = load_job_config(config)
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    available = profiles(package)
    report = {'schema_version': 'coragent-job-readiness/1', 'checked_at': datetime.now(timezone.utc).isoformat(),
              'configuration_sha256': binding_digest(settings), 'external_services': 'not_checked', 'targets': {}}
    for name, target in configured_targets(settings).items():
        if name not in targets:
            report['targets'][name] = {'status': 'not_verified'}
            continue
        row = report['targets'][name] = {'status': 'configuration_validated', 'jobs': [],
            'tested_backends': [], 'untested_backends': sorted(target.get('backends', {})),
            'expected_node': expected_node, 'node_coverage': 'selected_node' if expected_node else 'observed_only'}
        shared_workspace = None
        accepted = False
        try:
            row['environments'] = check_environments(settings, targets=[name])[name]
            row['status'] = 'environment_verified'
            if target.get('file_mode', 'staged') == 'shared':
                # Acceptance must exercise the same filesystem as real Jobs.
                # Own only this freshly-created directory, never work_root.
                shared_workspace = Path(tempfile.mkdtemp(prefix='.coragent-acceptance-',
                                                        dir=Path(target['work_root']).resolve()))
                root = shared_workspace
            else:
                root = directory / name
                root.mkdir(mode=0o700, parents=True)
            initialize_workspace(root, 'installation_' + name.replace('/', '_'), 'research')
            admit_research_workspace(root)
            expected_checks = Counter(check['backend'] for profile in available.values()
                for check in profile.get('checks', []) if not bindings_only or check.get('script'))
            completed_checks = Counter()
            for profile in available.values():
                for check in profile.get('checks', []):
                    if bindings_only and not check.get('script'):
                        continue
                    backend = check['backend']
                    if backend not in target.get('backends', {}):
                        continue
                    if check.get('script'):
                        script = resource(Path(profile['root']), check['script'])
                        request = prepare_script(config, target_identity(name), backend, script, check.get('arguments', []),
                                                 collect=check.get('collect', []))
                    else:
                        inputs = {}
                        for role, value in check.get('inputs', {}).items():
                            source = root / (check['executor'] + '-' + role)
                            write_private(source, value.encode())
                            inputs[role] = source
                        request = prepare(config, target_identity(name), check['executor'], '1', inputs, check.get('arguments', []))
                    # The bound walltime and cancellation cover both process
                    # execution and queue waits; no live research workspace is used.
                    request['timeout_seconds'] = timeout
                    try:
                        result = run_job(root, request, timeout)
                    except AcceptanceJobError as error:
                        row['jobs'].append({**error.job, 'backend': backend})
                        raise
                    job = {**{k: v for k, v in result.items() if k != 'cwd'}, 'backend': backend}
                    row['jobs'].append(job)
                    if expected_node is not None and result.get('actual_node') != expected_node:
                        job['status'] = 'failed'
                        raise RuntimeError('acceptance_node_mismatch: expected ' + expected_node
                                           + ', observed ' + str(result.get('actual_node')))
                    expected = check.get('result')
                    if expected:
                        value = json.loads((Path(result['cwd']) / expected['path']).read_text())
                        for key, wanted in expected.get('fields', {}).items():
                            if value.get(key) != wanted:
                                job['status'] = 'failed'
                                raise RuntimeError('acceptance_result_mismatch')
                    completed_checks[backend] += 1
                    row['tested_backends'] = sorted(key for key, count in completed_checks.items()
                                                   if count == expected_checks[key])
                    row['untested_backends'] = sorted(target.get('backends', {}).keys() - set(row['tested_backends']))
            row['status'] = 'execution_verified' if row['tested_backends'] else 'environment_verified'
            accepted = True
        except (OSError, RuntimeError, ValueError) as error:
            row['status'] = 'failed'
            row['error'] = str(error)
        finally:
            if shared_workspace is not None:
                if accepted:
                    shutil.rmtree(shared_workspace)
                else:
                    # Keep evidence and any unresolved execution for recovery.
                    row['retained_workspace'] = str(shared_workspace)
    return report


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--config', type=Path, required=True)
    p.add_argument('--package-root', type=Path, required=True)
    p.add_argument('--directory', type=Path, required=True)
    p.add_argument('--report', type=Path, required=True)
    p.add_argument('--targets', type=json.loads, required=True)
    p.add_argument('--timeout', type=int, default=180)
    p.add_argument('--bindings-only', action='store_true')
    args = p.parse_args()
    report = accept(args.config, args.package_root, args.directory, args.targets, args.timeout, bindings_only=args.bindings_only)
    write_private(args.report, (json.dumps(report, indent=2) + '\n').encode())
    return int(any(row['status'] == 'failed' for row in report['targets'].values()))


if __name__ == '__main__':
    raise SystemExit(main())
