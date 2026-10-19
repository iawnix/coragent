import sys
from pathlib import Path

_SKILLS = next(parent for parent in Path(__file__).resolve().parents if (parent / "_shared").is_dir())
_SCRIPTS = _SKILLS / "material-preparation" / "scripts"
for _part in ("materials", "reaction", "geometry", "diagnostics", "tensor", "_shared"):
    sys.path.insert(0, str(_SCRIPTS / _part if _part != "_shared" else _SKILLS / _part))

"""Compare supplied geometries under graph-preserving, proper rotations."""
import math

import numpy as np

from correspondence import mappings


def internal_value(points):
    if len(points) == 2:
        return float(np.linalg.norm(points[1] - points[0]))
    if len(points) == 3:
        a, b = points[0] - points[1], points[2] - points[1]
        norm = np.linalg.norm(a) * np.linalg.norm(b)
        return None if norm < 1e-12 else float(np.degrees(np.arccos(np.clip(np.dot(a, b) / norm, -1, 1))))
    b0, b1, b2 = points[0] - points[1], points[2] - points[1], points[3] - points[2]
    norm = np.linalg.norm(b1)
    if norm < 1e-12:
        return None
    axis = b1 / norm
    v, w = b0 - np.dot(b0, axis) * axis, b2 - np.dot(b2, axis) * axis
    if np.linalg.norm(v) < 1e-12 or np.linalg.norm(w) < 1e-12:
        return None
    return float(np.degrees(np.arctan2(np.dot(np.cross(axis, v), w), np.dot(v, w))))


def state_comparison(left, right):
    conflicts, unknown = [], []
    for key in ('charge', 'multiplicity'):
        a, b = left.get(key), right.get(key)
        if a is None or b is None:
            unknown.append(key)
        elif a != b:
            conflicts.append(key)
    a, b = left.get('electronic_state', {}), right.get('electronic_state', {})
    if a.get('kind', 'unspecified') == 'unspecified' or b.get('kind', 'unspecified') == 'unspecified':
        unknown.append('electronic_state.kind')
    elif a['kind'] != b['kind']:
        conflicts.append('electronic_state.kind')
    for key in ('method', 'root', 'label'):
        if a.get(key) is not None and b.get(key) is not None and a[key] != b[key]:
            conflicts.append('electronic_state.' + key)
        elif (a.get(key) is None) != (b.get(key) is None):
            unknown.append('electronic_state.' + key)
    return {'status': 'conflicting_declarations' if conflicts else 'incomplete_declarations' if unknown else 'compatible_declarations',
            'conflicts': conflicts, 'unknown': unknown, 'wavefunction_identity': 'not_assessed',
            'scope': 'Equal labels or method-local roots do not prove identical electronic states'}


def compare_conformers(left, right, *, fixed_pairs=(), max_candidates=64, max_search=20000,
                       rmsd_threshold=.1, internal_coordinates=(), distance_tolerance=.1, angle_tolerance=10.):
    for name, value in [('rmsd_threshold', rmsd_threshold), ('distance_tolerance', distance_tolerance), ('angle_tolerance', angle_tolerance)]:
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
            raise ValueError(f'{name} requires a finite positive number')
    if not isinstance(internal_coordinates, (tuple, list)):
        raise ValueError('internal_coordinates requires groups of left atom IDs')
    groups = []
    for group in internal_coordinates:
        if (not isinstance(group, list) or len(group) not in (2, 3, 4)
                or any(not isinstance(i, str) or i not in left['ids'] for i in group) or len(set(group)) != len(group)):
            raise ValueError('internal coordinate requires 2, 3 or 4 distinct left atom IDs')
        groups.append([left['ids'].index(i) for i in group])
    correspondence = mappings(left, right, mode='identity', fixed_pairs=fixed_pairs,
                              max_candidates=max_candidates, max_search=max_search)
    state = state_comparison(left['value'], right['value'])
    result = {'schema_version': 'chemical-conformer-comparison/1', 'status': 'not_assessed',
              'geometry_status': 'not_assessed', 'state_comparison': state, 'correspondence': correspondence,
              'thresholds': {'rmsd_angstrom': rmsd_threshold, 'distance_angstrom': distance_tolerance, 'angle_degrees': angle_tolerance},
              'best': None, 'matching_candidate': None,
              'scope': 'All-atom unweighted RMSD with one proper rotation for the entire material; no optimization, automatic merge or electronic-state verification'}
    if correspondence['status'] == 'incompatible':
        result.update(status='incompatible_graph', geometry_status='not_assessed')
    elif left['coordinates'] is None or right['coordinates'] is None:
        result['reason'] = 'supplied_geometries_required'
    elif correspondence['status'] == 'not_assessed':
        result['reason'] = correspondence['reason']
    else:
        x = left['coordinates']
        evaluations = []
        for index, candidate in enumerate(correspondence['candidates']):
            y = right['coordinates'][candidate['left_to_right']]
            xc, yc = x - x.mean(axis=0), y - y.mean(axis=0)
            u, _, vt = np.linalg.svd(yc.T @ xc)
            rotation = u @ np.diag([1., 1., 1. if np.linalg.det(u @ vt) >= 0 else -1.]) @ vt
            rmsd = float(np.sqrt(np.mean(np.sum((yc @ rotation - xc) ** 2, axis=1))))
            checks = []
            for ids, group in zip(internal_coordinates, groups):
                a, b = internal_value(x[group]), internal_value(y[group])
                delta = None if a is None or b is None else abs(a - b)
                if delta is not None and len(group) == 4:
                    delta = min(delta, 360. - delta)
                tolerance = distance_tolerance if len(group) == 2 else angle_tolerance
                checks.append({'atoms': ids, 'kind': {2: 'distance', 3: 'angle', 4: 'dihedral'}[len(group)],
                               'unit': 'angstrom' if len(group) == 2 else 'degree', 'left': a, 'right': b,
                               'difference': delta, 'status': 'not_assessed' if delta is None else 'match' if delta <= tolerance else 'different'})
            failed = rmsd > rmsd_threshold or any(c['status'] == 'different' for c in checks)
            status = 'different' if failed else 'not_assessed' if any(c['status'] == 'not_assessed' for c in checks) else 'match'
            evaluations.append({'candidate_index': index, 'rmsd_angstrom': rmsd, 'rotation': rotation.tolist(),
                                'translation': (x.mean(axis=0) - y.mean(axis=0) @ rotation).tolist(),
                                'rotation_determinant': float(np.linalg.det(rotation)), 'internal_coordinates': checks, 'status': status})
        if evaluations:
            result['best'] = min(evaluations, key=lambda e: e['rmsd_angstrom'])
            matches = [e for e in evaluations if e['status'] == 'match']
            if matches:
                result['matching_candidate'] = min(matches, key=lambda e: e['rmsd_angstrom'])
        complete = correspondence['search_complete'] and not correspondence['candidate_limit_reached']
        geometry = 'match' if result['matching_candidate'] else 'different' if complete and evaluations and all(e['status'] == 'different' for e in evaluations) else 'inconclusive'
        result.update(geometry_status=geometry, status='geometry_match' if geometry == 'match' else geometry,
                      evaluated_candidates=len(evaluations), coverage_complete=complete)
    if state['conflicts']:
        result['status'] = 'state_conflict'
    return result
