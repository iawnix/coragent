"""Bounded rigid-fragment sampling; coordinates are seeds, never optimized complexes."""
import json
import math

import numpy as np
from rdkit import Chem

from ensemble_material import canonical, checked, derive_material, xyz_text
from material import build_material, object_fields


def combine(spec):
    object_fields(spec, ('schema_version', 'materials', 'multiplicity', 'electronic_state', 'fixed_fragments', 'distance_constraints'), 'complex input')
    if spec.get('schema_version') != 'chemical-complex-input/1' or not isinstance(spec.get('materials'), list) or not spec['materials']:
        raise ValueError('chemical-complex-input/1 with a nonempty materials list required')
    if len(spec['materials']) > 16: raise ValueError('at most 16 input materials supported')
    materials = [checked(v) for v in spec['materials']]
    if any(m['coordinates'] is None for m in materials): raise ValueError('all source materials need supplied coordinates')
    if len(materials) == 1:
        if 'multiplicity' in spec or 'electronic_state' in spec:
            raise ValueError('single-material state comes from that material; create a new material to change it')
        return materials[0], [{'material_index': 0, 'source_id': i, 'combined_id': i} for i in materials[0]['ids']]
    rows = []; coords = []; ids = []; lineage = []; fragments = []; combined = None; all_graphs = True
    for index, m in enumerate(materials):
        offset = len(ids)
        for i, atom in enumerate(m['atoms']):
            name = f'part{index + 1}_atom{i + 1}'
            rows.append(atom); coords.append(atom['coordinates']); ids.append(name)
            lineage.append({'material_index': index, 'source_id': m['ids'][i], 'combined_id': name})
        groups = m['value']['fragments']['groups']
        if groups is None: raise ValueError('explicit fragments are required for each input')
        fragments.extend([[offset + m['ids'].index(i) for i in group] for group in groups])
        if m['mol'] is None: all_graphs = False
        elif combined is None: combined = Chem.Mol(m['mol'])
        else: combined = Chem.CombineMols(combined, m['mol'])
    charges = [m['value']['charge'] for m in materials]
    request = {'schema_version': 'chemical-material-input/1', 'format': 'xyz', 'text': xyz_text(rows, coords),
               'coordinate_unit': 'angstrom', 'atom_ids': ids, 'fragments': fragments, 'arrangement': 'separate_reactants',
               'charge': sum(charges) if all(v is not None for v in charges) else None,
               'multiplicity': spec.get('multiplicity'), 'electronic_state': spec.get('electronic_state')}
    if all_graphs:
        labels = [a.GetAtomMapNum() for a in combined.GetAtoms() if a.GetAtomMapNum()]
        if len(labels) != len(set(labels)): raise ValueError('conflicting explicit atom-map labels between materials; resolve them explicitly')
        smiles = Chem.MolToSmiles(combined, canonical=False, allHsExplicit=True)
        order = json.loads(combined.GetProp('_smilesAtomOutputOrder'))
        request.update(graph={'smiles': smiles, 'source': 'agent', 'note': 'Disjoint union of supplied graphs; no association or spin coupling inferred'}, graph_to_input=order)
    elif any(a.get('isotope') is not None for a in rows):
        raise ValueError('combining isotopic material requires explicit graphs for all fragments')
    result, _ = build_material(request, canonical(spec))
    result['derivation'] = {'operation': 'disjoint_material_union', 'source_sha256': [m['sha256'] for m in materials], 'atom_lineage': lineage}
    return checked(result), lineage


def rotation(rng, maximum_degrees=None):
    if maximum_degrees is None:
        q = rng.normal(size=4); q /= np.linalg.norm(q)
        w, x, y, z = q
    else:
        axis = rng.normal(size=3); axis /= np.linalg.norm(axis)
        angle = rng.uniform(-maximum_degrees, maximum_degrees) * math.pi / 180.
        w = math.cos(angle / 2); x, y, z = axis * math.sin(angle / 2)
    return np.array([[1 - 2*(y*y+z*z), 2*(x*y-z*w), 2*(x*z+y*w)],
                     [2*(x*y+z*w), 1-2*(x*x+z*z), 2*(y*z-x*w)],
                     [2*(x*z-y*w), 2*(y*z+x*w), 1-2*(x*x+y*y)]])


def sample_complex(spec, *, mode='assemble', samples=16, max_attempts=256, seed=0,
                   min_separation=3., max_separation=6., translation=.5, rotation_degrees=30., clash_scale=1.2):
    if mode not in {'assemble', 'perturb'}: raise ValueError('mode must be assemble or perturb')
    if type(samples) is not int or not 1 <= samples <= 256 or type(max_attempts) is not int or not 1 <= max_attempts <= 10000:
        raise ValueError('samples must be 1..256 and max-attempts 1..10000')
    if type(seed) is not int or not 0 <= seed < 2**32: raise ValueError('seed must be a uint32')
    for v in (min_separation, max_separation, translation, rotation_degrees, clash_scale):
        if type(v) not in (int, float) or not math.isfinite(v) or v <= 0: raise ValueError('sampling ranges must be finite positive numbers')
    if min_separation > max_separation or rotation_degrees > 180: raise ValueError('invalid separation/rotation range')
    source, lineage = combine(spec)
    groups = source['value']['fragments']['groups']
    if groups is None or not 2 <= len(groups) <= 16 or len(source['atoms']) > 256:
        raise ValueError('2..16 declared fragments and at most 256 atoms required')
    groups = [[source['ids'].index(i) for i in group] for group in groups]
    fixed = spec.get('fixed_fragments', [0])
    if not isinstance(fixed, list) or any(type(i) is not int or not 0 <= i < len(groups) for i in fixed) or len(set(fixed)) != len(fixed):
        raise ValueError('fixed_fragments requires unique zero-based fragment indexes')
    fixed = sorted(set(fixed) | {0})
    if len(fixed) == len(groups): raise ValueError('at least one mobile fragment required')
    constraints = spec.get('distance_constraints', [])
    if not isinstance(constraints, list): raise ValueError('distance_constraints must be a list')
    parsed_constraints = []
    for c in constraints:
        object_fields(c, ('atoms', 'minimum', 'maximum'), 'distance constraint')
        pair = c.get('atoms')
        if not isinstance(pair, list) or len(pair) != 2 or any(i not in source['ids'] for i in pair) or pair[0] == pair[1]:
            raise ValueError('distance constraint requires two combined atom IDs')
        bounds = [c.get('minimum'), c.get('maximum')]
        if any(type(v) not in (int, float) or not math.isfinite(v) or v < 0 for v in bounds) or bounds[0] > bounds[1]:
            raise ValueError('constraint requires ordered nonnegative angstrom bounds')
        parsed_constraints.append(([source['ids'].index(i) for i in pair], *bounds))
    xyz = source['coordinates']; centers = [xyz[g].mean(axis=0) for g in groups]
    radii = np.array([Chem.GetPeriodicTable().GetRcovalent(a['element']) for a in source['atoms']])
    rng = np.random.default_rng(seed); members = []; rejected = {'collision': 0, 'distance_constraint': 0}; attempted = 0
    def accept(candidate, transformations, original=False):
        for i, group in enumerate(groups):
            for other in groups[i + 1:]:
                distances = np.linalg.norm(candidate[group, None, :] - candidate[None, other, :], axis=2)
                if np.any(distances < clash_scale * (radii[group, None] + radii[None, other])):
                    rejected['collision'] += 1; return
        for pair, lower, upper in parsed_constraints:
            if not lower <= np.linalg.norm(candidate[pair[0]] - candidate[pair[1]]) <= upper:
                rejected['distance_constraint'] += 1; return
        derived = derive_material(source, candidate, {'operation': 'rigid_fragment_sampling', 'attempt': attempted,
                                                     'seed': seed, 'original': original, 'transformations': transformations})
        derived['arrangement'] = 'complex'
        derived['unknown_fields'] = [f for f in derived['unknown_fields'] if f != 'arrangement']
        members.append({'id': f'member_{len(members) + 1:04d}', 'material': derived, 'energy': None,
                        'identity': {'status': 'rigid_fragments_preserved', 'scope': 'Interfragment association and electronic state unassessed'}, 'issues': []})
    if mode == 'perturb': accept(xyz.copy(), [], original=True)
    while len(members) < samples and attempted < max_attempts:
        attempted += 1; candidate = xyz.copy(); transforms = []
        for i, group in enumerate(groups):
            if i in fixed: continue
            rot = rotation(rng, rotation_degrees if mode == 'perturb' else None)
            direction = rng.normal(size=3); direction /= np.linalg.norm(direction)
            center = centers[i] + direction * rng.uniform(0, translation) if mode == 'perturb' else centers[0] + direction * rng.uniform(min_separation, max_separation)
            candidate[group] = (xyz[group] - centers[i]) @ rot + center
            transforms.append({'fragment_index': i, 'rotation': rot.tolist(), 'center_before': centers[i].tolist(), 'center_after': center.tolist()})
        accept(candidate, transforms)
    return {'schema_version': 'chemical-ensemble/1', 'origin': 'complex_sampling', 'reference_material': source['value'],
            'source_sha256': canonical(spec), 'members': members, 'atom_lineage': lineage, 'complete': len(members) == samples,
            'sampling': {'mode': mode, 'requested': samples, 'attempted': attempted, 'max_attempts': max_attempts, 'seed': seed,
                         'rng': 'numpy.default_rng/PCG64', 'fixed_fragments': fixed, 'min_centroid_separation_angstrom': min_separation,
                         'max_centroid_separation_angstrom': max_separation, 'translation_angstrom': translation, 'rotation_degrees': rotation_degrees,
                         'clash_covalent_radius_factor': clash_scale, 'distance_constraints': constraints, 'rejected': rejected},
            'issues': [] if len(members) == samples else ['sampling_budget_exhausted'],
            'scope': 'Bounded rigid-fragment seeds; first fragment fixed, only proper rotations, no intrafragment conformer search, optimization, energies or exhaustive coverage. Sampling distance constraints do not constrain later optimization'}
