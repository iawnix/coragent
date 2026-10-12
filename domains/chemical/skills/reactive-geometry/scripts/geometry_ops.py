"""Explicit local frames and proper rigid motions; no reaction-name templates."""
import math
import numpy as np
from analysis_material import numeric_array
from conformers import internal_value
from material import object_fields


def number(value, name, low=-1e6, high=1e6):
    if type(value) not in (int, float) or not math.isfinite(value) or not low <= value <= high:
        raise ValueError(f'{name} must be finite in [{low}, {high}]')
    return float(value)


def atom_indices(value, ids, name, lengths=None):
    if (not isinstance(value, list) or not value or (lengths is not None and len(value) not in lengths)
            or any(not isinstance(v, str) or v not in ids for v in value) or len(set(value)) != len(value)):
        raise ValueError(f'{name} requires distinct known atom IDs')
    return [ids.index(v) for v in value]


def unit(value):
    norm = np.linalg.norm(value)
    if norm < 1e-10: raise ValueError('degenerate local frame or zero direction')
    return value / norm


def rotation(axis, degrees):
    x, y, z = unit(np.asarray(axis, float)); a = math.radians(degrees)
    skew = np.array([[0., -z, y], [z, 0., -x], [-y, x, 0.]])
    return np.eye(3) + math.sin(a)*skew + (1-math.cos(a))*(skew@skew)


def align_rotation(source, target):
    source, target = unit(source), unit(target)
    cross = np.cross(source, target); cosine = np.clip(source@target, -1., 1.)
    if np.linalg.norm(cross) < 1e-10:
        if cosine > 0: return np.eye(3)
        basis = np.eye(3)[np.argmin(np.abs(source))]
        return rotation(np.cross(source, basis), 180.)
    return rotation(cross, np.degrees(np.arccos(cosine)))


def frame(spec, xyz, ids):
    object_fields(spec, ('kind', 'atoms', 'vector', 'sign'), 'direction')
    kind = spec.get('kind')
    if kind == 'vector':
        if set(spec) != {'kind', 'vector'}: raise ValueError('vector direction needs only kind/vector')
        return unit(numeric_array(spec['vector'], (3,), 'direction'))
    if kind not in ('away', 'normal'): raise ValueError('direction.kind must be vector/away/normal')
    if 'vector' in spec: raise ValueError('vector is not a local-frame field')
    indexes = atom_indices(spec.get('atoms'), ids, 'direction atoms', (3,) if kind == 'normal' else None)
    if len(indexes) < 2: raise ValueError('away direction needs center and neighbors')
    sign = number(spec.get('sign', 1), 'direction sign', -1, 1)
    if sign not in (-1, 1): raise ValueError('direction sign must be -1 or 1')
    points = xyz[indexes]
    vector = points[0] - points[1:].mean(axis=0) if kind == 'away' else np.cross(points[1]-points[0], points[2]-points[0])
    return sign * unit(vector)


def apply(op, xyz, ids, groups, choice, rng):
    """Apply one operation to a fresh coordinate array, returning the actual transform."""
    kind = op['kind']
    if kind == 'displace':
        vectors = np.asarray(op['vectors'], float)
        delta = vectors * choice
        xyz += delta
        return {'kind': kind, 'amplitude_angstrom': choice, 'max_atom_displacement_angstrom': float(np.linalg.norm(delta, axis=1).max()),
                'source_ref': op['source_ref'], 'vectors': op['vectors']}
    atoms = atom_indices(op['atoms'], ids, 'operation atoms')
    mobile = atom_indices(op['mobile_atoms'], ids, 'mobile atoms')
    if kind == 'place':
        a, b = atoms
        direction = frame(op['direction'], xyz, ids)
        cone = op.get('cone_degrees', 0.)
        if cone:
            basis = unit(np.cross(direction, np.eye(3)[np.argmin(np.abs(direction))]))
            basis = rotation(direction, rng.uniform(-180, 180)) @ basis
            direction = rotation(basis, rng.uniform(0, cone)) @ direction
        pivot = xyz[b].copy()
        matrix = np.eye(3)
        if 'mobile_direction' in op:
            matrix = align_rotation(frame(op['mobile_direction'], xyz, ids), -direction)
        matrix = rotation(direction, choice[1]) @ matrix
        shift = xyz[a] + choice[0]*direction - pivot
        xyz[mobile] = (xyz[mobile]-pivot) @ matrix.T + pivot + shift
        return {'kind': kind, 'atoms': op['atoms'], 'mobile_atoms': op['mobile_atoms'], 'distance': choice[0],
                'twist_degrees': choice[1], 'direction': direction.tolist(), 'rotation': matrix.tolist(),
                'pivot': pivot.tolist(), 'translation': shift.tolist()}
    current = internal_value(xyz[atoms])
    if current is None: raise ValueError('undefined internal coordinate')
    if kind == 'distance':
        a, b = atoms; shift = unit(xyz[b]-xyz[a])*(choice-current)
        xyz[mobile] += shift
        return {'kind': kind, 'atoms': op['atoms'], 'mobile_atoms': op['mobile_atoms'], 'target': choice, 'translation': shift.tolist()}
    if kind == 'angle':
        a, b, c = atoms; axis = np.cross(xyz[a]-xyz[b], xyz[c]-xyz[b]); pivot = xyz[b].copy()
        delta = choice-current
    else:
        a, b, c, d = atoms; axis = xyz[c]-xyz[b]; pivot = xyz[c].copy()
        delta = (choice-current+180)%360-180
    matrix = rotation(axis, delta)
    xyz[mobile] = (xyz[mobile]-pivot) @ matrix.T + pivot
    return {'kind': kind, 'atoms': op['atoms'], 'mobile_atoms': op['mobile_atoms'], 'target': choice,
            'rotation': matrix.tolist(), 'pivot': pivot.tolist()}
