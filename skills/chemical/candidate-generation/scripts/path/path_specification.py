"""Validate mapped path inputs without selecting a reaction by name."""
import math

import numpy as np
from rdkit import Chem

from reaction_checks import calculation_spec, molecules, ordered_molecule, reaction
from xyz import validate_electronic_state


def preparation_spec(spec):
    calculation_spec(spec)
    transformation = spec.get('transformation')
    if not isinstance(transformation, dict):
        raise ValueError('transformation requires kind=explicit and the complete bond_changes list')
    if transformation.get('kind') != 'explicit':
        raise ValueError('use kind=explicit with bond_changes; new reaction names do not need new kinds')
    sides = molecules(spec.get('mapped_smiles', ''))
    ids = {a.GetAtomMapNum() for a in sides[0].GetAtoms()}
    changes = transformation.get('bond_changes')
    if not isinstance(changes, list):
        raise ValueError('explicit transformation requires the complete bond_changes list')
    seen = set()
    for row in changes:
        pair = row.get('atoms') if isinstance(row, dict) else None
        if (not isinstance(pair, list) or len(pair) != 2 or any(type(n) is not int or n not in ids for n in pair)
                or pair[0] == pair[1]):
            raise ValueError('bond_changes atoms must be two distinct existing map IDs')
        key = tuple(sorted(pair))
        if key in seen:
            raise ValueError('duplicate bond_changes pair')
        seen.add(key)
        if any(type(row.get(k)) not in (int, float) or not math.isfinite(row[k]) or row[k] < 0 for k in ('before', 'after')):
            raise ValueError('bond_changes before/after must be finite nonnegative bond orders')
    if 'hydrogen_changes' in transformation:
        hydrogen = transformation['hydrogen_changes']
        if not isinstance(hydrogen, list):
            raise ValueError('hydrogen_changes must be a list')
        seen = set()
        for row in hydrogen:
            if (not isinstance(row, dict) or type(row.get('atom')) is not int or row['atom'] not in ids
                    or row['atom'] in seen or any(type(row.get(k)) is not int or row[k] < 0 for k in ('before', 'after'))):
                raise ValueError('hydrogen_changes requires unique existing atom IDs and nonnegative counts')
            seen.add(row['atom'])
    checks = reaction(spec['mapped_smiles'], transformation)
    if any(checks['checks'][key]['verdict'] != 'pass' for key in
           ('element_charge_balance', 'map_identity', 'declared_transformation')):
        raise ValueError('mapped reaction does not match declared bond changes, atom identities or balance')
    if checks['checks']['atom_hydrogen_changes']['verdict'] == 'fail':
        raise ValueError('mapped reaction does not match declared hydrogen changes')
    ordered = [ordered_molecule(m) for m in sides]
    if ordered[0][1] != ordered[1][1]:
        raise ValueError('endpoint atom correspondence differs; explicitly map transferred H atoms')
    for mol, _ in ordered:
        if Chem.GetFormalCharge(mol) != spec['charge']:
            raise ValueError('requested charge differs from the molecular graphs')
        if any(a.GetIsotope() for a in mol.GetAtoms()):
            raise ValueError('isotope-specific masses require explicit Gaussian inputs; this writer emits element symbols only')
        validate_electronic_state([(a.GetSymbol(), 0, 0, 0) for a in mol.GetAtoms()], spec['charge'], spec['multiplicity'])
    return checks, sides


def select_strategy(spec):
    default = 'provided_endpoints' if 'endpoints' in spec else 'mapped_endpoints'
    strategy = spec.get('candidate_strategy', default)
    if strategy not in ('mapped_endpoints', 'provided_endpoints'):
        raise ValueError('candidate_strategy must be mapped_endpoints or provided_endpoints')
    if 'endpoints' in spec and strategy != 'provided_endpoints':
        raise ValueError('endpoints requires candidate_strategy=provided_endpoints; supplied geometry must not be ignored')
    return strategy


def provided_coordinates(rows, mol, atom_order):
    """Each coordinate carries its atom key; input rows may be in any order."""
    if not isinstance(rows, list) or len(rows) != len(atom_order):
        raise ValueError('each endpoint must supply exactly one row per atom, including H')
    expected = {tuple(key): a.GetSymbol() for key, a in zip(atom_order, mol.GetAtoms())}
    mapped = {}
    for row in rows:
        key = row.get('atom') if isinstance(row, dict) else None
        if not isinstance(key, list) or len(key) != 3 or any(type(n) is not int for n in key):
            raise ValueError('endpoint atom must be [0, map_id, 0] or [1, parent_map_id, H_ordinal]')
        key = tuple(key)
        if key not in expected or key in mapped or row.get('element') != expected[key]:
            raise ValueError('endpoint atom keys/elements must match the mapped graph exactly without duplicates')
        xyz = row.get('xyz')
        if (not isinstance(xyz, list) or len(xyz) != 3
                or any(type(v) not in (int, float) or not math.isfinite(v) for v in xyz)):
            raise ValueError('endpoint xyz requires three finite numeric coordinates in angstrom')
        mapped[key] = xyz
    coordinates = np.asarray([mapped[tuple(key)] for key in atom_order], dtype=float)
    for i in range(len(coordinates)):
        if any(np.linalg.norm(coordinates[i]-coordinates[j]) < 0.1 for j in range(i)):
            raise ValueError('endpoint contains coincident atoms')
    return coordinates
