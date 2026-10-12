"""Bound edits to explicit materials, reaction changes and calculation provenance."""
import itertools
import numpy as np
from rdkit import Chem
from analysis_material import numeric_array
from ensemble_material import canonical, checked
from material import object_fields
from geometry_ops import atom_indices, number


def text(value, name):
    if not isinstance(value, str) or not value.strip() or len(value) > 4096:
        raise ValueError(name+' requires nonempty text (at most 4096 characters)')
    return value


def rows(value, name, low=1, high=64):
    if not isinstance(value, list) or not low <= len(value) <= high:
        raise ValueError(f'{name} requires {low}..{high} entries')
    return value


def targets(value, kind):
    bounds = (.1, 30.) if kind in ('place', 'distance') else (.01, 179.99) if kind == 'angle' else (-180., 180.) if kind == 'dihedral' else (-2., 2.)
    result = [number(v, kind+' value', *bounds) for v in rows(value, 'values', high=32)]
    if len(set(result)) != len(result): raise ValueError('duplicate operation values')
    return result


def validate(spec):
    object_fields(spec, ('schema_version', 'material', 'reference_material', 'bond_changes', 'edit_hypotheses', 'sampling'), 'reactive geometry input')
    if spec.get('schema_version') != 'chemical-reactive-geometry/1': raise ValueError('chemical-reactive-geometry/1 required')
    source = checked(spec.get('material')); ids = source['ids']; xyz = source['coordinates']
    if xyz is None or not 2 <= len(ids) <= 256: raise ValueError('2..256 atoms with angstrom coordinates required')
    if np.abs(xyz).max() > 1e6: raise ValueError('coordinates outside bounded molecular geometry range; recenter first')
    reference = checked(spec['reference_material']) if 'reference_material' in spec else source
    if reference['ids'] != ids or any((a['element'], a.get('isotope')) != (b['element'], b.get('isotope')) for a, b in zip(source['atoms'], reference['atoms'])):
        raise ValueError('reference must use the same atom IDs, order, elements and isotopes; explicitly reorder first')
    if reference['mol'] is None: raise ValueError('a reference graph is required for protected-bond checks')
    for key in ('charge', 'multiplicity', 'electronic_state'):
        if source['value'].get(key) != reference['value'].get(key): raise ValueError('reference state declaration differs')
    mol = reference['mol']
    groups = [list(group) for group in Chem.GetMolFrags(mol)]
    # Coordinates can already be TS-like; graph is a protected-skeleton reference, not their identity.
    edges = {tuple(sorted((b.GetBeginAtomIdx(), b.GetEndAtomIdx()))): b.GetBondTypeAsDouble() for b in mol.GetBonds()}
    changes = {}; center = set()
    for row in rows(spec.get('bond_changes'), 'bond_changes'):
        object_fields(row, ('atoms', 'before', 'after'), 'bond change')
        pair = tuple(sorted(atom_indices(row.get('atoms'), ids, 'bond change', (2,))))
        before = number(row.get('before'), 'before bond order', 0, 3)
        after = number(row.get('after'), 'after bond order', 0, 3)
        if before == after or pair in changes: raise ValueError('bond changes must be unique and change bond order')
        if before != edges.get(pair, 0): raise ValueError('before bond order differs from reference graph')
        changes[pair] = row; center.update(pair)
    sampling = spec.get('sampling', {})
    object_fields(sampling, ('count', 'seed', 'clash_scale', 'protected_bond_tolerance', 'max_local_displacement'), 'sampling')
    count, seed = sampling.get('count', 16), sampling.get('seed', 0)
    if type(count) is not int or not 1 <= count <= 256: raise ValueError('count must be 1..256')
    if type(seed) is not int or not 0 <= seed < 2**32: raise ValueError('seed must be a uint32')
    sampling = {'count': count, 'seed': seed, 'clash_scale': number(sampling.get('clash_scale', .85), 'clash_scale', .5, 1.5),
                'protected_bond_tolerance': number(sampling.get('protected_bond_tolerance', .15), 'protected bond tolerance', .001, .5),
                'max_local_displacement': number(sampling.get('max_local_displacement', .75), 'local displacement', .001, 2.)}
    hypotheses = rows(spec.get('edit_hypotheses'), 'edit_hypotheses', high=32)
    seen = set(); parsed = []
    for hypothesis in hypotheses:
        object_fields(hypothesis, ('id', 'note', 'source_refs', 'operations', 'checks'), 'edit hypothesis')
        name = text(hypothesis.get('id'), 'hypothesis id')
        if name in seen: raise ValueError('duplicate hypothesis id')
        seen.add(name); text(hypothesis.get('note'), 'hypothesis note')
        refs = rows(hypothesis.get('source_refs'), 'source_refs', low=0)
        for ref in refs: text(ref, 'source ref')
        options = []
        for op in rows(hypothesis.get('operations'), 'operations', high=16):
            kind = op.get('kind') if isinstance(op, dict) else None
            common = ('kind', 'atoms', 'mobile_atoms', 'values', 'tolerance')
            if kind == 'displace':
                object_fields(op, ('kind', 'vectors', 'values', 'atom_ids', 'material_sha256', 'source_ref', 'representation'), 'displacement')
                if op.get('representation') != 'cartesian_direction': raise ValueError('convert mass-weighted modes/gradients to Cartesian directions explicitly')
                if op.get('atom_ids') != ids or op.get('material_sha256') != source['sha256']:
                    raise ValueError('displacement must bind the exact source material and full atom order')
                if op.get('source_ref') not in refs: raise ValueError('displacement source_ref must be in hypothesis source_refs')
                v = numeric_array(op.get('vectors'), xyz.shape, 'displacement vectors')
                if not 1e-12 < np.linalg.norm(v, axis=1).max() <= 1.+1e-12:
                    raise ValueError('vectors require nonzero direction with maximum atom norm <= 1; normalize the whole mode, never each atom')
                options.append(targets(op.get('values'), kind)); continue
            if kind not in ('place', 'distance', 'angle', 'dihedral'): raise ValueError('unsupported edit kind')
            object_fields(op, (*common, 'direction', 'mobile_direction', 'twists', 'cone_degrees', 'direction_tolerance_degrees') if kind == 'place' else common, 'geometry operation')
            n = {'place': 2, 'distance': 2, 'angle': 3, 'dihedral': 4}[kind]
            atoms = atom_indices(op.get('atoms'), ids, 'operation atoms', (n,))
            mobile = set(atom_indices(op.get('mobile_atoms'), ids, 'mobile_atoms'))
            if atoms[-1] not in mobile or set(atoms[:-1]) & mobile: raise ValueError('move the last coordinate atom and its group; earlier anchors must be fixed')
            values = targets(op.get('values'), kind)
            number(op.get('tolerance', .03 if n == 2 else 3.), 'tolerance', .0001, .5 if n == 2 else 30.)
            if kind == 'place':
                if tuple(sorted(atoms)) not in changes or changes[tuple(sorted(atoms))]['before'] != 0:
                    raise ValueError('placement requires an explicitly forming interfragment bond')
                if sorted(mobile) not in [sorted(g) for g in groups] or any(atoms[0] in g and atoms[1] in g for g in groups):
                    raise ValueError('placement must move one whole separate reference fragment')
                # Validate frame contracts now. Degeneracy is a per-candidate failure below.
                for key in ('direction', 'mobile_direction'):
                    if key not in op and key != 'direction': continue
                    f = op.get(key)
                    object_fields(f, ('kind', 'atoms', 'vector', 'sign'), 'direction')
                    if f.get('kind') == 'vector':
                        if set(f) != {'kind', 'vector'}: raise ValueError('vector frame requires only kind/vector')
                        vec = numeric_array(f['vector'], (3,), 'frame vector')
                        if np.linalg.norm(vec) < 1e-10: raise ValueError('zero direction')
                    else:
                        if f.get('kind') not in ('normal', 'away') or 'vector' in f: raise ValueError('direction kind must be vector/away/normal')
                        ix = atom_indices(f.get('atoms'), ids, 'frame atoms', (3,) if f['kind'] == 'normal' else None)
                        if len(ix) < 2 or ix[0] != atoms[0 if key == 'direction' else 1]: raise ValueError('local frame starts at its reactive anchor')
                        wrong_group = bool(set(ix) & mobile) if key == 'direction' else not set(ix) <= mobile
                        if wrong_group:
                            raise ValueError('local frame must stay in its fixed/mobile group')
                        if number(f.get('sign', 1), 'frame sign', -1, 1) not in (-1, 1): raise ValueError('frame sign must be +/-1')
                number(op.get('cone_degrees', 0), 'cone degrees', 0, 90)
                number(op.get('direction_tolerance_degrees', 3.), 'direction tolerance', .0001, 30.)
                twists = targets(op.get('twists', [0.]), 'dihedral')
                options.append(list(itertools.product(values, twists)))
            else: options.append(values)
        checks = hypothesis.get('checks', [])
        rows(checks, 'checks', low=0)
        for check in checks:
            object_fields(check, ('atoms', 'minimum', 'maximum'), 'final check')
            ix = atom_indices(check.get('atoms'), ids, 'check atoms', (2, 3, 4))
            low, high = (.1, 30) if len(ix) == 2 else (0, 180) if len(ix) == 3 else (-180, 180)
            if number(check.get('minimum'), 'minimum', low, high) > number(check.get('maximum'), 'maximum', low, high):
                raise ValueError('check bounds must be ordered; use separate hypotheses for wrapped dihedrals')
        parsed.append((hypothesis, options))
    return source, reference, groups, edges, changes, center, sampling, parsed
