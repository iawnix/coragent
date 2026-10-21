#!/usr/bin/env python3
"""Check every registered executor/validator/profile closure against the source tree."""
from __future__ import annotations
import hashlib, json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOMAIN = ROOT / 'skills/chemical'
CATALOG = json.loads((DOMAIN / 'execution.json').read_text())

def digest(path: Path) -> str:
    return 'sha256:' + hashlib.sha256(path.read_bytes()).hexdigest()

def source(rel: str) -> Path:
    path = DOMAIN / rel
    if not path.is_file() or path.is_symlink():
        raise SystemExit(f'missing or symlinked execution resource: {rel}')
    return path

def main() -> None:
    count = 0
    for entry in [*CATALOG['executors'], *CATALOG['validators']]:
        source(entry['entry'])
        for rel, expected in (entry.get('resources') or {}).items():
            if isinstance(expected, dict):
                rel, expected = expected['path'], expected['sha256']
            if digest(source(rel)) != expected:
                raise SystemExit(f'changed resource: {entry["id"]}: {rel}')
        count += 1
    for profile in CATALOG.get('acceptance_profiles', []):
        for check in profile.get('checks', []):
            if not any(v['id'] == check['validator_id'] and str(v['version']) == str(check['validator_version']) for v in CATALOG['validators']):
                raise SystemExit(f'unresolved validator: {profile["id"]}: {check["validator_id"]}')
    print(f'execution closure covers {count} executors and validators; acceptance profiles resolve')

if __name__ == '__main__':
    main()
