"""Sign-invariant mode response for declared internal-coordinate combinations."""
import numpy as np

from analysis_material import numeric_array
from check_common import check, positive, report, stationary
from conformers import internal_value
from material import object_fields


def difference(a, b, size):
    if a is None or b is None:
        return None
    return (a - b + 180.) % 360. - 180. if size == 4 else a - b


def mode_check(material, evidence, specification, *, negative_threshold=20., near_zero=10., step=.05):
    positive(step, 'step')
    if step > .5:
        raise ValueError('step must be <= 0.5 angstrom for local mode probes')
    object_fields(specification, ('schema_version', 'coordinates'), 'mode specification')
    if specification.get('schema_version') != 'chemical-mode-coordinates/1':
        raise ValueError('chemical-mode-coordinates/1 required')
    coordinates = specification.get('coordinates')
    if not isinstance(coordinates, list) or not 1 <= len(coordinates) <= 64:
        raise ValueError('1..64 declared coordinates required')
    resolved = []
    for coordinate in coordinates:
        object_fields(coordinate, ('name', 'terms', 'direction', 'minimum_response', 'minimum_projection'), 'coordinate')
        if not isinstance(coordinate.get('name'), str) or not coordinate['name'].strip():
            raise ValueError('coordinate name required')
        if type(coordinate.get('direction')) is not int or coordinate['direction'] not in (-1, 1):
            raise ValueError('coordinate direction must be +1 or -1')
        response = positive(coordinate.get('minimum_response', .02), 'minimum_response')
        projection = positive(coordinate.get('minimum_projection', .05), 'minimum_projection')
        if projection > 1:
            raise ValueError('minimum_projection must be <= 1')
        terms = coordinate.get('terms')
        if not isinstance(terms, list) or not 1 <= len(terms) <= 64:
            raise ValueError('1..64 terms required per coordinate')
        parsed = []
        for term in terms:
            object_fields(term, ('atoms', 'weight', 'scale'), 'coordinate term')
            ids = term.get('atoms')
            if (not isinstance(ids, list) or len(ids) not in (2, 3, 4)
                    or any(not isinstance(i, str) or i not in material['ids'] for i in ids) or len(set(ids)) != len(ids)):
                raise ValueError('term requires 2/3/4 distinct current material atom IDs')
            weight = term.get('weight', 1.)
            if type(weight) not in (int, float) or not np.isfinite(weight) or weight == 0:
                raise ValueError('weight requires a finite nonzero number')
            scale = positive(term.get('scale', 1.), 'scale')
            parsed.append(([material['ids'].index(i) for i in ids], weight, scale))
        resolved.append((coordinate, parsed, response, projection))
    base = stationary(material, evidence, kind='saddle', negative_threshold=negative_threshold, near_zero=near_zero)
    if base.get('scientific_verdict') == 'not_assessed':
        return {**base, 'kind': 'mode', 'stationary': base}
    checks = {'stationary_evidence': {'verdict': base['verdict'], 'details': 'Independent stationary checks attached'}}
    frequencies = evidence.get('frequencies_cm-1')
    indexes = [] if frequencies is None else [i for i, f in enumerate(frequencies) if f < -negative_threshold]
    if material['coordinates'] is None or len(indexes) != 1 or evidence.get('normal_modes') is None or evidence.get('mode_representation') != 'cartesian':
        checks['mode_character'] = check(None, 'One significant imaginary Cartesian mode and bound geometry required')
        return report('mode', checks, stationary=base)
    xyz = material['coordinates']
    modes = numeric_array(evidence['normal_modes'], (len(frequencies), len(xyz), 3), 'normal_modes')
    vector = modes[indexes[0]]
    norm = np.linalg.norm(vector)
    if norm < 1e-12:
        checks['mode_character'] = check(None, 'Mode norm is zero')
        return report('mode', checks, stationary=base)
    vector = vector / norm
    plus, minus = xyz + step * vector, xyz - step * vector
    observations, signs, missing, failed = [], [], False, False
    for coordinate, terms, min_response, min_projection in resolved:
        response, gradient, samples = 0., np.zeros_like(xyz), []
        available = True
        for indexes_, weight, scale in terms:
            size = len(indexes_)
            before, after_plus, after_minus = [internal_value(points[indexes_]) for points in (xyz, plus, minus)]
            delta = difference(after_plus, after_minus, size)
            samples.append({'atoms': [material['ids'][i] for i in indexes_], 'unit': 'angstrom' if size == 2 else 'degree',
                            'weight': weight, 'scale': scale, 'before': before, 'plus': after_plus, 'minus': after_minus})
            if before is None or delta is None:
                available = False
                continue
            response += weight / scale * delta / (2 * step)
            h = 1e-5
            for atom in indexes_:
                for axis in range(3):
                    a, b = xyz.copy(), xyz.copy()
                    a[atom, axis] += h; b[atom, axis] -= h
                    d = difference(internal_value(a[indexes_]), internal_value(b[indexes_]), size)
                    if d is None:
                        available = False
                    else:
                        gradient[atom, axis] += weight / scale * d / (2 * h)
        grad_norm = np.linalg.norm(gradient)
        projection = None if not available or grad_norm < 1e-12 else float(np.clip(np.sum(gradient * vector) / grad_norm, -1., 1.))
        passed = None if projection is None else abs(response) >= min_response and abs(projection) >= min_projection
        missing |= passed is None
        failed |= passed is False
        if passed:
            signs.append(1 if response * coordinate['direction'] > 0 else -1)
        observations.append({'name': coordinate['name'], 'terms': samples, 'response_per_angstrom': float(response) if available else None,
                             'projection_cosine': projection, 'expected_direction': coordinate['direction'],
                             'minimum_response': min_response, 'minimum_projection': min_projection, **check(passed)})
    coherent = len(set(signs)) <= 1
    checks['mode_character'] = check(False if failed or not coherent else None if missing else True,
                                     {'coordinates': observations, 'common_sign': signs[0] if signs and coherent else None})
    return report('mode', checks, stationary=base, mode_index=indexes[0], step_angstrom=step,
                  displaced_geometries={'atom_ids': material['ids'], 'plus': plus.tolist(), 'minus': minus.tolist()},
                  scope='Local normalized Cartesian probes and coordinate-gradient projections; overall mode sign is arbitrary. Displaced structures are not optimized endpoints or an IRC, and this is not complete TS certification')
