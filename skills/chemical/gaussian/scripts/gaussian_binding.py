"""Verify immutable TS preparation bundles before invoking Gaussian."""
import hashlib
import json
import re
from pathlib import Path

import numpy as np


def content_digest(value):
    return 'sha256:' + hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
        ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def rmsd(left, right):
    x, y = np.asarray(left, dtype=float), np.asarray(right, dtype=float)
    if x.shape != y.shape or x.ndim != 2 or x.shape[1] != 3 or not len(x) or not np.isfinite(x).all() or not np.isfinite(y).all():
        raise ValueError('TS binding requires finite matching Nx3 coordinates')
    x, y = x - x.mean(0), y - y.mean(0)
    u, _, vt = np.linalg.svd(x.T @ y)
    rotation = u @ np.diag([1., 1., np.linalg.det(u @ vt)]) @ vt
    return float(np.sqrt(np.mean(np.sum((x @ rotation - y) ** 2, axis=1))))


def inspect_binding(input_path, method, basis, charge, multiplicity):
    path = Path(input_path)
    names = re.findall(r'coragent-ts-binding=([^\s]+)', path.read_text())
    if not names:
        return None
    if len(names) != 1 or names[0] != 'ts_source.json':
        raise ValueError('one local ts_source.json binding is required')
    source_path = path.parent / names[0]
    source = json.loads(source_path.read_text())
    claimed = source.pop('binding_sha256', None)
    if source.get('schema_version') != 'chemical-ts-source/1' or claimed != content_digest(source):
        raise ValueError('TS source binding digest mismatch')
    if source.get('source_kind') != 'optimized_saddle' or source.get('mode_check', {}).get('verdict') != 'pass':
        raise ValueError('validated target-mode saddle required; a TS seed is not a source saddle')
    calc = source['calculation']
    if (calc['method'].lower(), calc['basis'].lower(), calc['charge'], calc['multiplicity']) != (method.lower(), basis.lower(), charge, multiplicity):
        raise ValueError('TS source method/basis or charge/multiplicity differs from requested input')
    input_sha = 'sha256:' + hashlib.sha256(path.read_bytes()).hexdigest()
    matches = [row for row in source['inputs'] if row['sha256'] == input_sha]
    if len(matches) != 1:
        raise ValueError('Gaussian input differs from the source-bound preparation; regenerate it from the verified TS')
    return {'source_sha256': 'sha256:' + hashlib.sha256(source_path.read_bytes()).hexdigest(),
            'binding_sha256': claimed, 'source': source, 'input': matches[0], 'dependency': names[0]}


def check_output_origin(binding, log_path):
    from gaussian_io import orientation_blocks
    lines = Path(log_path).read_text(errors='replace').splitlines()
    blocks = orientation_blocks(lines, 'orientation:')
    if not blocks:
        return {'status': 'not_assessed', 'reason': 'no_initial_geometry_in_output'}
    atoms = blocks[0]
    correct_order = [row[0] for row in atoms] == binding['source']['elements']
    distance = rmsd(binding['input']['start_coordinates'], [row[1:] for row in atoms]) if correct_order else None
    return {'status': 'verified' if correct_order and distance <= 1e-5 else 'mismatch',
            'origin_rmsd_angstrom': distance, 'fixed_atom_order': correct_order,
            'source_sha256': binding['source_sha256'], 'input_kind': binding['input']['kind']}
