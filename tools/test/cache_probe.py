#!/usr/bin/env python3
"""Bounded synthetic cache probe; local by default, live only with --live."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import tomllib
import uuid

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live', action='store_true', help='Use the configured provider with synthetic data; incurs model usage.')
    parser.add_argument('--size-k', type=int, choices=[128, 256, 512], default=128, help='Approximate input size; actual tokens come from the response.')
    parser.add_argument('--installation', type=Path, default=Path('/home/iaw/soft/coragent'))
    parser.add_argument('--pi-runtime', type=Path)
    parser.add_argument('--provider', default='CPA')
    parser.add_argument('--model', default='gpt-6-astra')
    args = parser.parse_args()
    pi = args.pi_runtime
    if pi is None:
        candidates = [p for p in (args.installation / 'runtimes/pi').iterdir()
                      if (p / 'packages/coding-agent/src/experimental/source-resolver.ts').is_file()]
        if len(candidates) != 1:
            parser.error('Specify --pi-runtime when there is not exactly one installed Pi runtime.')
        pi = candidates[0]
    config = {'mode': 'live' if args.live else 'local', 'sizeK': args.size_k, 'piRoot': str(pi.resolve())}
    if args.live:
        root = args.installation / 'config'
        document = tomllib.loads((root / 'config.toml').read_text())
        provider = document['models']['providers'][args.provider]
        selected = next(model for model in provider['models'] if model['id'] == args.model)
        if selected.get('api', provider.get('api')) != 'openai-completions':
            parser.error('This probe currently targets the OpenAI-compatible Chat Completions route.')
        credentials = json.loads((root / 'credentials.json').read_text())

        def resolve(value):
            if isinstance(value, str) and value.startswith('credential:'):
                return credentials['secrets'][value.removeprefix('credential:')]
            if isinstance(value, dict):
                return {key: resolve(item) for key, item in value.items()}
            return value

        key = resolve(provider.get('apiKey'))
        if not isinstance(key, str) or not key or key.startswith('!'):
            parser.error('The probe requires a configured literal API key or credential reference; shell secrets are not executed.')
        config.update({'provider': args.provider, 'model': selected, 'baseUrl': provider['baseUrl'],
                       'apiKey': key, 'headers': resolve(provider.get('headers', {})),
                       'compat': selected.get('compat', provider.get('compat'))})
    os.umask(0o077)
    run = ROOT / 'local_debug/cache-probes' / (time.strftime('%Y%m%d-%H%M%S') + '-' + uuid.uuid4().hex[:8])
    run.mkdir(parents=True)
    for name in ('tmp', 'cache'):
        (run / name).mkdir()
    config['outputDir'] = str(run)
    source_files = ['tools/test/cache_probe.py', 'tools/test/cache-probe.mjs',
                    'apps/agent/context/cache-diagnostics.mjs', 'apps/agent/context/manager.mjs']
    manifest = {'mode': config['mode'], 'size_k': args.size_k, 'max_requests': 4, 'max_output_tokens': 512,
                'synthetic_only': True, 'pi_runtime': pi.name,
                'source_sha256': {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in source_files}}
    (run / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    env = dict(os.environ)
    env.update({'TMPDIR': str(run / 'tmp'), 'XDG_CACHE_HOME': str(run / 'cache'),
                'NODE_COMPILE_CACHE': str(run / 'cache/node'), 'PYTHONDONTWRITEBYTECODE': '1'})
    print(json.dumps({'mode': config['mode'], 'size_k': args.size_k, 'max_requests': 4, 'output_dir': str(run)}), flush=True)
    with (run / 'stderr.log').open('w') as stderr:
        result = subprocess.run(['node', '--import', str(pi / 'packages/coding-agent/src/experimental/source-resolver.ts'),
                                 str(ROOT / 'tools/test/cache-probe.mjs')], input=json.dumps(config), text=True,
                                env=env, stderr=stderr, cwd=ROOT, timeout=4 * 125 + 30)
    return result.returncode


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, KeyError, ValueError, StopIteration, subprocess.TimeoutExpired) as error:
        # Configuration or transport errors must not disclose secrets to stdout.
        print(json.dumps({'status': 'failed', 'error_type': type(error).__name__}))
        raise SystemExit(1)
