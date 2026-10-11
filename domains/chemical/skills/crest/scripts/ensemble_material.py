"""Derived geometries retain atom lineage; graph checks remain explicit in scope."""
import json

import numpy as np
from rdkit import Chem
from rdkit.Chem import rdDetermineBonds

from analysis_material import numeric_array, validate_material
from correspondence import edges, stereo_corresponds
from material import build_material, digest


def canonical(value):
    return digest(json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode())


def xyz_text(atoms, coordinates, comment='Derived candidate, not an optimized minimum'):
    return f'{len(atoms)}\n{comment}\n' + ''.join(a['element'] + ' ' + ' '.join(format(float(v), '.17g') for v in row) + '\n' for a, row in zip(atoms, coordinates))


def derive_material(template, coordinates, source):
    value = template['value']; graph = value.get('graph')
    spec = {'schema_version': 'chemical-material-input/1', 'format': 'xyz',
            'text': xyz_text(template['atoms'], coordinates), 'coordinate_unit': 'angstrom',
            'atom_ids': template['ids'], 'charge': value.get('charge'), 'multiplicity': value.get('multiplicity'),
            'electronic_state': {k: v for k, v in value['electronic_state'].items() if k in {'kind', 'label', 'method', 'root', 'note'}},
            'arrangement': value['arrangement']}
    groups = value['fragments']['groups']
    if groups is not None: spec['fragments'] = [[template['ids'].index(i) for i in group] for group in groups]
    if graph:
        spec['graph'] = {k: graph[k] for k in ('smiles', 'source', 'note')}
        spec['graph_to_input'] = [value['atom_order']['old_to_new'][i] for i in graph['graph_to_input']]
    derived, _ = build_material(spec, canonical(source))
    derived['derivation'] = {'template_sha256': template['sha256'], **source}
    return derived


def identity_check(member):
    mol, xyz = member['mol'], member['coordinates']
    scope = 'RDKit coordinate-derived connectivity, charges/radicals and specified stereo in fixed atom order; inferred, not electronic or trajectory proof'
    if mol is None or xyz is None or member['value']['charge'] is None:
        return {'status': 'not_assessed', 'reason': 'explicit_graph_coordinates_and_charge_required', 'scope': scope}
    allowed = {'H', 'B', 'C', 'N', 'O', 'F', 'Si', 'P', 'S', 'Cl', 'Br', 'I'}
    if any(a.GetSymbol() not in allowed for a in mol.GetAtoms()):
        return {'status': 'not_assessed', 'reason': 'coordinate_bond_inference_outside_supported_elements', 'scope': scope}
    try:
        probe = Chem.MolFromXYZBlock(xyz_text(member['atoms'], xyz))
        for a, b in zip(mol.GetAtoms(), probe.GetAtoms()): b.SetIsotope(a.GetIsotope())
        rdDetermineBonds.DetermineBonds(probe, charge=member['value']['charge'], allowChargedFragments=True, embedChiral=True)
        local_states = lambda m: [(a.GetFormalCharge(), a.GetNumRadicalElectrons()) for a in m.GetAtoms()]
        same = edges(mol) == edges(probe) and local_states(mol) == local_states(probe) and stereo_corresponds(mol, probe, list(range(len(xyz))))
        return {'status': 'match' if same else 'different', 'scope': scope}
    except (ValueError, RuntimeError):
        return {'status': 'not_assessed', 'reason': 'bond_or_stereo_inference_unresolved', 'scope': scope}


def checked(value):
    return validate_material(value, canonical(value))


def import_crest(template, run, run_sha):
    if not isinstance(run, dict) or run.get('schema_version') != 'chemical-crest-run/1' or run.get('material_sha256') != template['sha256']:
        raise ValueError('CREST run must bind the exact source material')
    primary = run.get('primary'); settings = run.get('settings')
    if not isinstance(primary, dict) or primary.get('schema_version') != 'chemical-crest-primary/1' or not isinstance(settings, dict):
        raise ValueError('parsed CREST primary evidence and settings required')
    if (settings.get('charge'), settings.get('multiplicity')) != (template['value']['charge'], template['value']['multiplicity']):
        raise ValueError('CREST settings and material state disagree')
    if settings.get('method') not in ('gfn1', 'gfn2') or template['value']['electronic_state']['kind'] != 'ground':
        raise ValueError('supported CREST method and ground-state material required')
    if any(a.get('isotope') is not None for a in template['atoms']):
        raise ValueError('CREST isotope mass support is not established by this profile')
    if not {'solvent', 'solvent_model', 'constraints'} <= settings.keys():
        raise ValueError('explicit solvent and constraints required')
    if settings['constraints'] != [] or settings['solvent_model'] != ('ALPB' if settings['solvent'] else 'gas'):
        raise ValueError('unsupported solvent/constraint settings')
    rows = primary.get('members')
    if not isinstance(rows, list) or len(rows) > 1024 or any(not isinstance(r, dict) for r in rows):
        raise ValueError('at most 1024 member objects required')
    energy_model = {k: settings[k] for k in ('method', 'charge', 'multiplicity', 'solvent', 'solvent_model', 'constraints')}
    energy_model['quantity'] = 'electronic_energy'; energy_model['program_version'] = primary.get('version')
    members = []
    for i, row in enumerate(rows, 1):
        if row.get('index') != i: raise ValueError('member indexes must be consecutive')
        atoms = row.get('atoms')
        if not isinstance(atoms, list) or any(not isinstance(a, list) or len(a) != 4 for a in atoms) or [a[0] for a in atoms] != [a['element'] for a in template['atoms']]:
            members.append({'id': f'member_{i:04d}', 'material': None, 'energy': None, 'issues': ['element_order_differs'], 'original': row})
            continue
        coords = numeric_array([a[1:] for a in atoms], (len(template['atoms']), 3), 'member coordinates')
        derived = derive_material(template, coords, {'operation': 'crest_member', 'run_sha256': run_sha,
                                                   'primary_sha256': primary.get('primary_sha256', {}), 'frame_index': i})
        identity = identity_check(checked(derived))
        energy = row.get('energy_hartree')
        if type(energy) not in (int, float) or not np.isfinite(energy): raise ValueError('finite member energy required')
        issues = row.get('issues', [])
        if not isinstance(issues, list) or any(not isinstance(s, str) for s in issues): raise ValueError('member issues must be a string list')
        if primary.get('version') != '3.0.2': issues = [*issues, 'unsupported_or_missing_version']
        members.append({'id': f'member_{i:04d}', 'material': derived, 'identity': identity, 'issues': issues,
                        'energy': {'value': energy, 'unit': 'hartree', 'model': energy_model} if not issues else None,
                        'reported_energy_hartree': energy, 'reported_relative_kcal_mol': row.get('relative_energy_kcal_mol')})
    return {'schema_version': 'chemical-ensemble/1', 'origin': 'crest', 'source_sha256': run_sha,
            'reference_material': template['value'], 'members': members, 'sampling': settings,
            'complete': run.get('status') == 'completed' and primary.get('complete') is True,
            'issues': primary.get('issues', []), 'run_status': run.get('status'),
            'scope': 'Preserved sampled members; graph identity is inferred per geometry. No exhaustive conformer coverage or thermochemical ranking'}
