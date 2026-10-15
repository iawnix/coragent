#!/usr/bin/env python3
"""Verify that the operation/backend registry covers execution.json exactly once."""
from __future__ import annotations
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / 'domains/chemical/execution.json'
REGISTRY = ROOT / 'domains/chemical/skills/method-selection/references/operation_backend_registry.md'

def main() -> None:
    catalog = json.loads(CATALOG.read_text())
    expected = [*((entry['id'], 'executor') for entry in catalog['executors']),
                *((entry['id'], 'validator') for entry in catalog['validators']),
                *((entry['id'], 'profile') for entry in catalog.get('acceptance_profiles', []))]
    rows = [line for line in REGISTRY.read_text().splitlines() if line.startswith('| `')]
    found = []
    for row in rows:
        match = re.match(r'^\| `([^`]+)` \| `([^`]+)` \|', row)
        if not match:
            raise SystemExit(f'invalid operation/backend registry row: {row}')
        found.append((match.group(1), match.group(2)))
    if len(found) != len(set(found)):
        raise SystemExit('operation/backend registry contains duplicate ID/type records')
    if sorted(found) != sorted(expected):
        raise SystemExit(f'operation/backend registry mismatch: missing={sorted(set(expected)-set(found))}, extra={sorted(set(found)-set(expected))}')
    print(f'operation/backend registry covers {len(found)} registered records')

if __name__ == '__main__':
    main()
