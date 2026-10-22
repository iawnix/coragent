"""Bidirectional path evidence with explicit origin and endpoint assignments."""
import json

import numpy as np

from analysis_material import numeric_array, validate_material
from check_common import check, common_checks, content_digest, positive, report, stationary, unsupported
from conformers import compare_conformers, state_comparison
from material import digest
from endpoint_identity import compare_identity, geometry_identity


def aligned_rmsd(left, right):
    x, y = left - left.mean(axis=0), right - right.mean(axis=0)
    u, _, vt = np.linalg.svd(y.T @ x)
    rotation = u @ np.diag([1., 1., 1. if np.linalg.det(u @ vt) >= 0 else -1.]) @ vt
    return float(np.sqrt(np.mean(np.sum((y @ rotation - x) ** 2, axis=1))))


def irc_check(material, reference, paths, targets, *, negative_threshold=20., near_zero=10.,
              endpoint_rmsd=.2, origin_rmsd=.01, max_search=20000, max_candidates=64,
              energy_tolerance=1e-6, max_step_rmsd=1., policy='strict'):
    if policy not in {'strict', 'endpoint_relaxation'}:
        raise ValueError('IRC policy must be strict or endpoint_relaxation')
    positive(endpoint_rmsd, 'endpoint_rmsd'); positive(origin_rmsd, 'origin_rmsd')
    positive(energy_tolerance, 'energy_tolerance'); positive(max_step_rmsd, 'max_step_rmsd')
    base = stationary(material, reference, kind='saddle', negative_threshold=negative_threshold, near_zero=near_zero)
    if base.get('scientific_verdict') == 'not_assessed':
        return {**base, 'kind': 'irc', 'stationary': base}
    checks = {'source_stationary_evidence': {'verdict': base['verdict'], 'details': 'Mode character is assessed separately'}}
    directions, assignments, details = [], [], []
    xyz = material['coordinates']
    if xyz is None or not len(xyz):
        checks['origin'] = check(None, 'Source saddle coordinates required')
        return report('irc', checks, stationary=base)
    for ordinal, path in enumerate(paths):
        prefix = f'path_{ordinal + 1}_'
        current, scope = common_checks(material, path, 'chemical-irc-evidence/1')
        if not scope:
            current['method_scope'] = check(None, unsupported('irc', current)['scope'])
        direction = path.get('direction')
        directions.append(direction)
        current['direction'] = check(direction in ('forward', 'reverse'))
        current['source_segment'] = check(path.get('restart_segment') is not True,
            'Standalone restart segments require a stitched path back to the verified saddle')
        current['termination'] = check(True if path.get('termination') == 'normal' else False if path.get('termination') == 'error' else None)
        for key in ('complete', 'max_points_reached'):
            if path.get(key) is not None and type(path[key]) is not bool:
                raise ValueError(f'{key} must be boolean or null')
        current['path_complete'] = check(False if path.get('max_points_reached') is True or path.get('complete') is False
                                        else True if path.get('complete') is True and path.get('max_points_reached') is False else None,
                                        'Path completeness is separate from endpoint-relaxed connectivity')
        if policy == 'endpoint_relaxation':
            # A normally stopped, bounded path can support connectivity when its
            # exact last point is linked to a validated endpoint optimization.
            complete = current.pop('path_complete')
            current['path_stop_evidence'] = check(path.get('complete') is True and path.get('max_points_reached') in (True, False),
                                                {'strict_path_completeness': complete})
        calc = path['calculation']
        current['same_method_basis'] = check(all(calc.get(k) == reference['calculation'].get(k) and calc.get(k) is not None for k in ('method', 'basis')))
        origin = path.get('origin_coordinates')
        rmsd = None if origin is None else aligned_rmsd(xyz, numeric_array(origin, xyz.shape, 'origin_coordinates'))
        current['saddle_origin'] = check(None if rmsd is None else rmsd <= origin_rmsd,
                                         {'rmsd_angstrom': rmsd, 'maximum': origin_rmsd, 'atom_correspondence': 'fixed supplied IDs; proper rotation only'})
        current['coordinate_unit'] = check(path.get('coordinate_unit') == 'angstrom')
        points = path.get('points')
        last = None
        if not isinstance(points, list):
            raise ValueError('IRC points must be a list')
        for i, point in enumerate(points):
            if not isinstance(point, dict) or type(point.get('index')) is not int or point['index'] != i + 1:
                raise ValueError('IRC point indexes must be contiguous from 1')
            last = numeric_array(point.get('coordinates'), xyz.shape, 'IRC point coordinates')
            if point.get('energy_hartree') is not None:
                numeric_array([point['energy_hartree']], (1,), 'point energy')
        current['coordinate_path'] = check(True if len(points) >= 2 else None, {'point_count': len(points), 'minimum': 2})
        energies = [p.get('energy_hartree') for p in points]
        if energies and all(e is not None for e in energies):
            # IRC energies should descend away from the saddle.  Permit small
            # numerical noise, but reject a path whose endpoint is uphill.
            scale = energy_tolerance
            uphill = sum(1 for a, b in zip(energies, energies[1:]) if b > a + scale)
            current['energy_descent'] = check(uphill == 0 and energies[-1] <= energies[0] + scale,
                                              {'uphill_steps': uphill, 'first_hartree': energies[0], 'last_hartree': energies[-1],
                                               'tolerance_hartree': scale})
        else:
            current['energy_descent'] = check(None, 'Every path point needs energy evidence to assess descent')
        frames = ([numeric_array(origin, xyz.shape, 'origin_coordinates')] if origin is not None else []) + [
            numeric_array(p['coordinates'], xyz.shape, 'point coordinates') for p in points]
        steps = [aligned_rmsd(a, b) for a, b in zip(frames, frames[1:])]
        current['path_continuity'] = check(None if not steps else all(v <= max_step_rmsd for v in steps),
            {'step_rmsd_angstrom': steps, 'maximum': max_step_rmsd,
             'scope': 'Fixed-atom proper-alignment jump screen; inspect reaction coordinates and solver step evidence'})
        endpoint = path.get('endpoint')
        endpoint_checks_, assignment, endpoint_details = endpoint_checks(material, reference, endpoint, last, targets,
            negative_threshold=negative_threshold, near_zero=near_zero, endpoint_rmsd=endpoint_rmsd,
            max_search=max_search, max_candidates=max_candidates)
        current.update(endpoint_checks_)
        if policy == 'endpoint_relaxation':
            evidence = (endpoint or {}).get('minimum_evidence') or {}
            start = (evidence.get('optimization') or {}).get('start_coordinates')
            current['endpoint_optimization_origin'] = check(None if start is None or last is None else
                aligned_rmsd(last, numeric_array(start, xyz.shape, 'optimization start_coordinates')) <= 1e-5,
                'The endpoint relaxation must start at the final accepted IRC point')
        assignments.append(assignment)
        details.append({'direction': direction, 'endpoint': endpoint_details})
        checks.update({prefix + k: v for k, v in current.items()})
    checks['both_directions'] = check(len(directions) == 2 and set(directions) == {'forward', 'reverse'})
    checks['opposite_target_basins'] = check(None if any(a is None for a in assignments) else sorted(assignments) == [0, 1],
                                            {'assignments': assignments, 'target_order': ['reactant', 'product'], 'direction_swap_allowed': True})
    return report('irc', checks, stationary=base, paths=details, policy=policy,
                  evidence_level='complete_irc' if policy == 'strict' else 'short_irc_with_endpoint_optimization',
                  full_irc_complete=len(paths) == 2 and all(p.get('complete') is True and p.get('max_points_reached') is False for p in paths),
                  scope='Bound single-surface paths and mapped chemical endpoint assignments; reference conformers are diagnostics; includes supplied graph/state declarations but does not prove wavefunction continuity, intended mode character or mechanism uniqueness')


def endpoint_checks(material, reference, endpoint, last, targets, *, negative_threshold=20., near_zero=10.,
                    endpoint_rmsd=.2, max_search=20000, max_candidates=64):
    current = {}
    xyz = material["coordinates"]
    assignment = None
    endpoint_details = {'status': 'unassigned', 'next_step': 'Continue the path or optimize its endpoint, then supply a bound minimum and reference materials'}
    if endpoint is not None:
        if not isinstance(endpoint, dict) or ('material' in endpoint) == ('material_json' in endpoint):
            raise ValueError('endpoint requires exactly one of material or material_json')
        if 'material_json' in endpoint:
            raw = endpoint['material_json']
            if not isinstance(raw, str):
                raise ValueError('material_json requires the exact original UTF-8 file text')
            endpoint_material = validate_material(json.loads(raw), digest(raw.encode('utf-8')))
        else:
            endpoint_material = validate_material(endpoint['material'], content_digest(endpoint['material']))
        end_xyz = endpoint_material['coordinates']
        same_order = endpoint_material['ids'] == material['ids'] and [a['element'] for a in endpoint_material['atoms']] == [a['element'] for a in material['atoms']] and [a.get('isotope') for a in endpoint_material['atoms']] == [a.get('isotope') for a in material['atoms']]
        current['endpoint_atom_identity'] = check(same_order)
        endpoint_state = state_comparison(material['value'], endpoint_material['value'])
        current['endpoint_source_state'] = check(False if endpoint_state['conflicts'] else None if endpoint_state['unknown'] else True, endpoint_state)
        evidence = endpoint.get('minimum_evidence')
        if evidence is not None:
            minimum = stationary(endpoint_material, evidence, kind='minimum', negative_threshold=negative_threshold, near_zero=near_zero)
            current['endpoint_minimum'] = {'verdict': minimum['verdict'], 'details': minimum}
            current['endpoint_method_basis'] = check(all(evidence['calculation'].get(k) == reference['calculation'].get(k) for k in ('method', 'basis')))
        else:
            current['endpoint_minimum'] = check(None, 'A complete minimum assessment is required for basin assignment')
        start = None if evidence is None else (evidence.get('optimization') or {}).get('start_coordinates')
        if same_order and end_xyz is not None and last is not None:
            linked = aligned_rmsd(last, end_xyz) <= 1e-5
            if not linked and start is not None:
                linked = aligned_rmsd(last, numeric_array(start, xyz.shape, 'optimization start_coordinates')) <= 1e-5
            current['endpoint_path_binding'] = check(linked, 'Endpoint must be the final point or a minimum optimized from that exact point, allowing proper rigid rotation/translation with fixed atom IDs')
        else:
            current['endpoint_path_binding'] = check(None)
        # Species/basin identity is graph/state based.  Conformer RMSD is
        # retained as a separate diagnostic and must not reject a valid
        # endpoint that relaxed into another conformer or separated pose.
        comparisons = [compare_conformers(endpoint_material, target, rmsd_threshold=endpoint_rmsd,
                                          max_search=max_search, max_candidates=max_candidates) for target in targets]
        current['endpoint_geometry_identity'] = geometry_identity(endpoint_material)
        identity_comparisons = [compare_identity(endpoint_material, target,
            max_search=max_search, max_candidates=max_candidates) for target in targets]
        matched = [i for i, comp in enumerate(identity_comparisons) if comp['status'] == 'match']
        excluded = [comp['status'] == 'mismatch' for comp in identity_comparisons]
        if len(matched) == 1 and all(i == matched[0] or excluded[i] for i in range(len(comparisons))):
            assignment = matched[0]
        endpoint_details = {'status': 'assigned' if assignment is not None else 'ambiguous_or_unexpected',
                            'target_index': assignment, 'comparisons': comparisons,
                            'identity_comparisons': identity_comparisons,
                            'conformer_reference': None if assignment is None else {
                                'geometry_status': comparisons[assignment]['geometry_status'],
                                'rmsd_is_diagnostic_only': True, 'threshold_angstrom': endpoint_rmsd},
                            'actual_material_sha256': endpoint_material['sha256']}
        current['endpoint_identity'] = check(True if assignment is not None else None, endpoint_details)
    else:
        current['endpoint_identity'] = check(None, endpoint_details)
    return current, assignment, endpoint_details
