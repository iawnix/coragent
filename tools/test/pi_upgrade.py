#!/usr/bin/env python3
"""Offline upgrade/rollback rehearsal using two real, pinned product checkouts."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.test import environment, runner
from tools.test.supervisor import Supervisor, write_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--legacy-source', type=Path, required=True)
    parser.add_argument('--legacy-pi', type=Path, required=True)
    parser.add_argument('--candidate-source', type=Path, required=True)
    parser.add_argument('--env-root', type=Path, default=ROOT / 'local_debug')
    args = parser.parse_args()
    private = args.env_root.resolve()
    environment.configure_paths(private)
    sources = {'legacy': args.legacy_source.resolve(), 'candidate': args.candidate_source.resolve()}
    dependencies = {}
    identities = {}
    for label, source in sources.items():
        if not source.is_relative_to(private):
            raise ValueError('Rehearsal checkouts must be inside the private test root')
        if subprocess.check_output(['git', 'status', '--porcelain'], cwd=source):
            raise ValueError('Rehearsal requires clean, fixed product checkouts')
        pin = json.loads((source / 'packaging/coragent_packaging/pi/source.json').read_text())
        if pin['tag'] != ('v1.1.0' if label == 'legacy' else 'v1.4.0'):
            raise ValueError('Unexpected Pi version for rehearsal')
        paths = environment.dependency_paths(source, private)
        if label == 'legacy':
            paths['pi'] = args.legacy_pi.resolve()
        for component in ('python', 'node', 'pi'):
            if not paths[component].is_relative_to(private) or not (paths[component] / '.prepared.json').is_file():
                raise ValueError('Required private dependency is not prepared')
        subprocess.run([sys.executable, str(source / 'packaging/coragent_packaging/pi/prepare.py'),
                        '--verify', str(paths['pi'])], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        link = source / 'node_modules'
        if not link.exists():
            link.symlink_to(paths['node'] / 'node_modules', target_is_directory=True)
        if link.resolve() != (paths['node'] / 'node_modules').resolve():
            raise ValueError('Product checkout has unexpected Node dependencies')
        dependencies[label] = paths
        identities[label] = {'commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=source, text=True).strip(),
                             'pi_commit': pin['commit'], 'source_sha256': runner.digest_source(source, runner.source_files(source))}
    run, record = runner.create_run(private, ['pi-upgrade'], [{'reason': 'explicit offline cross-version rehearsal'}])
    record['products'] = identities
    record['dependencies'] = {f'{label}_{key}': str(value) for label, paths in dependencies.items() for key, value in paths.items()}
    write_json(run / 'run.json', record)
    env = runner.child_environment(private, run, dependencies['candidate'])
    env.update({'CORAGENT_TEST_LEGACY_SOURCE': str(sources['legacy']),
                'CORAGENT_TEST_CANDIDATE_SOURCE': str(sources['candidate']),
                'CORAGENT_TEST_LEGACY_PI': str(dependencies['legacy']['pi']),
                'CORAGENT_TEST_DEPENDENCIES': json.dumps([str(path) for paths in dependencies.values()
                                                        for path in paths.values() if (path / '.prepared.json').is_file()])})
    write_json(private / 'registry' / f'lease-{run.name}.json', {'run': str(run), 'dependencies': record['dependencies']})
    supervisor = Supervisor(run)
    try:
        command = ['unshare', '--user', '--map-root-user', '--net', '--pid', '--fork', '--kill-child=KILL', '--mount-proc',
                   sys.executable, str(run / 'source/tools/test/offline.py'), 'node', '--test', '--test-concurrency=1',
                   '--test-reporter=tap', str(run / 'source/tools/test/probes/pi-upgrade.mjs')]
        result = supervisor.execute(command, cwd=run / 'source', env=env, name='pi-upgrade', timeout=600)
        log = (run / 'logs/pi-upgrade.log').read_text(errors='replace')
        counts = {name: int(match[1]) for name in ('tests', 'pass', 'fail', 'skipped')
                  if (match := re.search(r'^# ' + name + r' (\d+)$', log, re.M))}
        result.update(counts)
        if counts.get('tests') != 4 or counts.get('skipped'):
            result['status'] = 'failed'
        record['results'] = [result]
    finally:
        record['cleanup'] = supervisor.close()
        if record['cleanup']['status'] == 'passed':
            shutil.rmtree(Path(record['socket_root']))
        record['status'] = 'passed' if record.get('results') and all(r['status'] == 'passed' for r in record['results']) and record['cleanup']['status'] == 'passed' else 'failed'
        record['finished'] = time.time()
        record['source_current'] = runner.digest_source(ROOT, runner.source_files(ROOT)) == record['source_sha256']
        record['products_current'] = all(runner.digest_source(source, runner.source_files(source)) == identities[label]['source_sha256']
                                         for label, source in sources.items())
        if record['status'] == 'passed' and not (record['source_current'] and record['products_current']):
            record['status'] = 'stale'
        write_json(run / 'run.json', record)
        write_json(run / 'report/result.json', record)
        (private / 'registry' / f'lease-{run.name}.json').unlink()
    print(json.dumps({'run': run.name, 'status': record['status'], 'cleanup': record['cleanup']['status'],
                      'results': [{k: v for k, v in r.items() if k != 'returncode'} for r in record.get('results', [])]}))
    return 0 if record['status'] == 'passed' else 1


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print(json.dumps({'status': 'blocked', 'error_type': type(error).__name__}))
        raise SystemExit(2)
