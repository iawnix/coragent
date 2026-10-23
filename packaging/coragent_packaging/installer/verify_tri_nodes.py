#!/usr/bin/env python3
"""Explicit TRI node/backend acceptance using ordinary, bounded CoRAgent Jobs."""
from __future__ import annotations

import sys
from pathlib import Path

if __name__ == "__main__":
    package_root = Path(__file__).resolve().parents[3]
    sys.path[:0] = [str(package_root / "packaging"), str(package_root / "backend/src"), str(package_root)]


import argparse
import copy
import json
import os
from pathlib import Path
import re
import tomllib

from coragent_packaging.installer._job_acceptance import accept
from coragent_packaging.installer._job_install import toml_bytes, write_private
from research_agent.jobs.config_contract import validate_job_config, configuration_document, binding_digest


def settings_from_config(config):
    document = tomllib.loads(config.read_text())
    if 'schema_version' in document:
        from research_agent.configuration.configuration import Configuration
        operator = Configuration(config)
        document = {'execution': operator.resolve_credentials(operator.read()['execution'])}
    return validate_job_config(document)


def verify(config, package, directory, target, nodes, timeout):
    settings = settings_from_config(config)
    selected = settings['targets'].get(target)
    if not selected or selected.get('executor') != 'tri':
        raise ValueError('TRI acceptance requires executor=tri')
    if (not isinstance(nodes, list) or not nodes
            or any(not isinstance(node, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', node) for node in nodes)
            or len(set(nodes)) != len(nodes)):
        raise ValueError('nodes must be a nonempty list of unique node names')
    if timeout <= 0:
        raise ValueError('timeout must be positive')
    # Never edit the active installation or mix acceptance with a research run.
    directory.mkdir(parents=True, mode=0o700, exist_ok=False)
    report = {'schema_version': 'coragent-tri-node-readiness/1', 'target': target,
              'configuration_sha256': binding_digest(settings), 'coverage': 'selected_nodes_only',
              'unselected_nodes': 'not_verified', 'nodes': {}}
    previous = {key: os.environ.get(key) for key in ('CORAGENT_JOB_CONFIG', 'CORAGENT_PACKAGE_ROOT')}
    try:
        for node in nodes:
            node_dir = directory / node
            pinned = copy.deepcopy(selected)
            pinned['handler_environment'] = {**pinned.get('handler_environment', {}), 'CORAGENT_TRI_NODE': node}
            candidate_settings = copy.deepcopy(settings)
            candidate_settings['targets'][target] = pinned
            document = configuration_document(candidate_settings)
            candidate = node_dir / 'config.toml'
            write_private(candidate, toml_bytes(document))
            # Retain the pinned configuration on failure for reconciliation.
            # Its digest is part of each Job's identity, including pending cancels.
            result = accept(candidate, package, node_dir / 'jobs', [target], timeout, expected_node=node)
            row = report['nodes'][node] = result['targets'][target]
            row['configuration_sha256'] = result['configuration_sha256']
            if row['status'] == 'failed':
                row['retained_config'] = str(candidate)
            else:
                candidate.unlink()
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
    write_private(directory / 'report.json', (json.dumps(report, indent=2) + '\n').encode())
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--package-root', type=Path, required=True)
    parser.add_argument('--directory', type=Path, required=True, help='New private acceptance directory')
    parser.add_argument('--platform', required=True)
    parser.add_argument('--scheduler-entry', help='TRI scheduler entry in the selected platform')
    parser.add_argument('--nodes', type=json.loads, required=True, help='JSON array of exact TRI node names')
    parser.add_argument('--timeout', type=int, default=180)
    args = parser.parse_args()
    from research_agent.jobs.config_contract import resolve_target
    selected = resolve_target(settings_from_config(args.config), {"platform": args.platform,
        **({"scheduler_entry": args.scheduler_entry} if args.scheduler_entry else {})}, scheduler="tri")
    report = verify(args.config.resolve(), args.package_root.resolve(), args.directory.resolve(),
                    selected, args.nodes, args.timeout)
    # Incomplete backend coverage is not a successful cluster acceptance.
    return int(any(row['status'] != 'execution_verified' or row['untested_backends']
                   for row in report['nodes'].values()))


if __name__ == '__main__':
    raise SystemExit(main())
