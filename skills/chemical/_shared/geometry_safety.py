"""Small, reaction-aware geometry safety checks shared by chemical runners.

This module deliberately checks only catastrophic input failures.  It does not
require reaction-center distances or angles to look like a minimum: those are
allowed to be non-equilibrium for a transition-state candidate.
"""
from __future__ import annotations

import re
from pathlib import Path

import numpy as np


# Cordero/Slater-style covalent radii (angstrom) for the elements commonly
# encountered by the bundled molecular workflows.  The fallback keeps the
# safety check conservative for less common elements without importing RDKit in
# Gaussian-only environments.
COVALENT_RADII = {
    "H": 0.31, "He": 0.28, "Li": 1.28, "Be": 0.96, "B": 0.84,
    "C": 0.76, "N": 0.71, "O": 0.66, "F": 0.57, "Ne": 0.58,
    "Na": 1.66, "Mg": 1.41, "Al": 1.21, "Si": 1.11, "P": 1.07,
    "S": 1.05, "Cl": 1.02, "Ar": 1.06, "K": 2.03, "Ca": 1.76,
    "Sc": 1.70, "Ti": 1.60, "V": 1.53, "Cr": 1.39, "Mn": 1.39,
    "Fe": 1.32, "Co": 1.26, "Ni": 1.24, "Cu": 1.32, "Zn": 1.22,
    "Ga": 1.22, "Ge": 1.20, "As": 1.19, "Se": 1.20, "Br": 1.20,
    "Kr": 1.16, "Rb": 2.20, "Sr": 1.95, "Y": 1.90, "Zr": 1.75,
    "Nb": 1.64, "Mo": 1.54, "Tc": 1.47, "Ru": 1.46, "Rh": 1.42,
    "Pd": 1.39, "Ag": 1.45, "Cd": 1.44, "In": 1.42, "Sn": 1.39,
    "Sb": 1.39, "Te": 1.38, "I": 1.39, "Xe": 1.40, "Cs": 2.44,
    "Ba": 2.15, "La": 2.07, "Ce": 2.04, "Pr": 2.03, "Nd": 2.01,
    "Sm": 1.98, "Eu": 1.98, "Gd": 1.96, "Tb": 1.94, "Dy": 1.92,
    "Ho": 1.92, "Er": 1.89, "Tm": 1.90, "Yb": 1.87, "Lu": 1.87,
    "Hf": 1.75, "Ta": 1.70, "W": 1.62, "Re": 1.51, "Os": 1.44,
    "Ir": 1.41, "Pt": 1.36, "Au": 1.36, "Hg": 1.32, "Tl": 1.45,
    "Pb": 1.46, "Bi": 1.48,
}

_ATOMIC_NUMBER_TO_SYMBOL = {
    index + 1: symbol for index, symbol in enumerate(
        "H He Li Be B C N O F Ne Na Mg Al Si P S Cl Ar K Ca Sc Ti V Cr Mn Fe Co Ni Cu Zn "
        "Ga Ge As Se Br Kr Rb Sr Y Zr Nb Mo Tc Ru Rh Pd Ag Cd In Sn Sb Te I Xe Cs Ba La Ce Pr Nd "
        "Pm Sm Eu Gd Tb Dy Ho Er Tm Yb Lu Hf Ta W Re Os Ir Pt Au Hg Tl Pb Bi Po At Rn Fr Ra Ac Th "
        "Pa U Np Pu Am Cm Bk Cf Es Fm Md No Lr Rf Db Sg Bh Hs Mt Ds Rg Cn Nh Fl Mc Lv Ts Og".split()
    )
}
_ELEMENT = re.compile(r"^[A-Z][a-z]?$")
_FLOAT = r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[EeDd][-+]?\d+)?"


def _symbol(value):
    if isinstance(value, str) and value.isdigit():
        return _ATOMIC_NUMBER_TO_SYMBOL.get(int(value))
    if isinstance(value, str) and _ELEMENT.fullmatch(value):
        return value[0].upper() + value[1:].lower()
    return None


def _radii(elements):
    values = []
    unknown = []
    for index, element in enumerate(elements):
        symbol = _symbol(element)
        if symbol is None:
            unknown.append({'index': index, 'element': element})
            values.append(1.0)
        else:
            values.append(COVALENT_RADII.get(symbol, 1.0))
    return np.asarray(values, dtype=float), unknown


def _pair_set(pairs, atom_count):
    result = set()
    for pair in pairs or ():
        if not isinstance(pair, (list, tuple)) or len(pair) != 2:
            raise ValueError('atom pairs must contain two zero-based indexes')
        a, b = pair
        if (isinstance(a, (bool, np.bool_)) or isinstance(b, (bool, np.bool_))
                or not isinstance(a, (int, np.integer)) or not isinstance(b, (int, np.integer))
                or not 0 <= a < atom_count or not 0 <= b < atom_count or a == b):
            raise ValueError('atom pair indexes must be distinct and within the geometry')
        result.add(tuple(sorted((int(a), int(b)))))
    return result


def assess(elements, coordinates, *, bonded_pairs=None, reaction_pairs=(), profile='general',
           clash_scale=None, max_coordinate=1e4, fragment_groups=None, reference_coordinates=None):
    """Return a machine-readable safety assessment for one geometry.

    ``bonded_pairs`` and ``reaction_pairs`` use zero-based atom indexes.  The
    latter are exempt from non-bonded short-contact checks, but never from the
    absolute collapse check.  This is the distinction that permits an
    elongated/forming TS bond while rejecting the 0.15 angstrom overlap seen in
    T001.
    """
    elements = list(elements) if isinstance(elements, (list, tuple)) else []
    hard = []
    warnings = []
    checks = {
        'finite_coordinates': 'fail',
        'atom_identity': 'fail',
        'catastrophic_overlap': 'not_assessed',
        'nonreaction_contacts': 'not_assessed',
        'reaction_center': 'not_assessed',
        'bond_lengths': 'not_assessed',
    }
    array = np.asarray(coordinates, dtype=float) if coordinates is not None else np.empty((0, 3))
    if array.ndim != 2 or array.shape != (len(elements), 3):
        hard.append({'kind': 'atom_coordinate_shape', 'expected': [len(elements), 3], 'actual': list(array.shape)})
        return _result('unsafe', checks, hard, warnings, array, None)
    if not np.isfinite(array).all():
        hard.append({'kind': 'nonfinite_coordinates'})
    elif np.abs(array).max(initial=0.0) > max_coordinate:
        hard.append({'kind': 'coordinates_out_of_bounds', 'maximum_abs_coordinate': float(np.abs(array).max())})
    else:
        checks['finite_coordinates'] = 'pass'
    radii, unknown = _radii(elements)
    if unknown:
        warnings.append({'kind': 'unknown_element_radius', 'atoms': unknown})
    checks['atom_identity'] = 'pass' if elements and not any(_symbol(e) is None for e in elements) else 'warning'
    if hard or len(elements) < 2:
        return _result('unsafe' if hard else 'safe', checks, hard, warnings, array, None)

    bonded = _pair_set(bonded_pairs, len(elements))
    reaction = _pair_set(reaction_pairs, len(elements))
    owners = {}
    if fragment_groups is not None:
        for group_index, group in enumerate(fragment_groups):
            for atom in group:
                if type(atom) is not int or not 0 <= atom < len(elements) or atom in owners:
                    raise ValueError('fragment groups must partition the atom indexes')
                owners[atom] = group_index
        if len(owners) != len(elements):
            raise ValueError('fragment groups must partition the atom indexes')
    reference = None
    if reference_coordinates is not None:
        reference = np.asarray(reference_coordinates, dtype=float)
        if reference.shape != array.shape or not np.isfinite(reference).all():
            raise ValueError('reference coordinates must be finite and match the atom order/shape')
    if bonded_pairs is None:
        warnings.append({'kind': 'bond_connectivity_not_supplied',
                         'detail': 'Supply bonded_pairs to distinguish bonded and nonbonded close contacts.'})
    if clash_scale is None:
        clash_scale = {'general': .75, 'reaction_seed': .72, 'ts_candidate': .70,
                       'path_image': .72}.get(profile, .75)
    if not isinstance(clash_scale, (int, float)) or not 0.1 <= clash_scale <= 1.5:
        raise ValueError('clash_scale must be between 0.1 and 1.5')
    distances = np.linalg.norm(array[:, None, :] - array[None, :, :], axis=2)
    short_contacts = []
    collapse_pairs = []
    bond_outliers = []
    for i in range(len(elements)):
        for j in range(i):
            pair = (j, i)
            distance = float(distances[i, j])
            radius_sum = float(radii[i] + radii[j])
            hydrogen_pair = _symbol(elements[i]) == _symbol(elements[j]) == 'H'
            known_nonbonded = bonded_pairs is not None or (owners and owners[i] != owners[j])
            contact_limit = 1.20 if known_nonbonded else .70
            # A reaction pair may be elongated or unformed, but no chemistry
            # makes two nuclei occupying the same point a valid TS guess.
            if distance < max(.35, .50 * radius_sum):
                collapse_pairs.append({'atoms': [j, i], 'distance_angstrom': distance,
                                       'reaction_pair': pair in reaction})
            elif pair not in bonded and pair not in reaction and hydrogen_pair and distance < contact_limit:
                short_contacts.append({'atoms': [j, i], 'distance_angstrom': distance,
                                       'threshold_angstrom': contact_limit,
                                       'context': 'declared_nonbonded' if known_nonbonded else 'connectivity_unknown',
                                       'radius_sum_angstrom': radius_sum, 'kind': 'short_hydrogen_contact'})
            elif pair not in bonded and pair not in reaction and distance < clash_scale * radius_sum:
                short_contacts.append({'atoms': [j, i], 'distance_angstrom': distance,
                                         'radius_sum_angstrom': radius_sum})
            elif hydrogen_pair and pair not in bonded and pair not in reaction and distance < 1.20:
                warnings.append({'kind': 'hydrogen_contact_needs_connectivity', 'atoms': [j, i],
                                 'distance_angstrom': distance})
            if pair in bonded and pair not in reaction:
                observed = {'atoms': [j, i], 'distance_angstrom': distance}
                if reference is not None:
                    before = float(np.linalg.norm(reference[i] - reference[j]))
                    observed.update(reference_distance_angstrom=before, delta_angstrom=distance-before)
                    unusual = abs(distance-before) > max(.20, .20 * before)
                else:
                    unusual = distance < .65 * radius_sum or distance > 1.6 * radius_sum
                if unusual:
                    bond_outliers.append(observed)
    if bonded_pairs is not None:
        checks['bond_lengths'] = 'warning' if bond_outliers else 'pass'
    if bond_outliers:
        warnings.append({'kind': 'nonreaction_bond_length_change', 'pairs': bond_outliers})
    if collapse_pairs:
        hard.append({'kind': 'catastrophic_overlap', 'pairs': collapse_pairs})
        checks['catastrophic_overlap'] = 'fail'
    else:
        checks['catastrophic_overlap'] = 'pass'
    if short_contacts:
        hard.append({'kind': 'nonreaction_short_contact', 'pairs': short_contacts})
        checks['nonreaction_contacts'] = 'fail'
    else:
        checks['nonreaction_contacts'] = 'pass'
    if reaction:
        checks['reaction_center'] = 'warning'
        warnings.append({'kind': 'reaction_center_not_normality_checked',
                         'pairs': [list(pair) for pair in sorted(reaction)]})
    else:
        checks['reaction_center'] = 'not_assessed'
    return _result('unsafe' if hard else 'safe', checks, hard, warnings, array, distances)


def _result(verdict, checks, hard, warnings, array, distances):
    minimum = None
    if distances is not None and len(array) > 1:
        minimum = float(distances[np.triu_indices(len(array), 1)].min())
    return {'verdict': verdict, 'hard_failures': hard, 'warnings': warnings,
            'checks': checks, 'minimum_pair_distance_angstrom': minimum,
            'atom_count': int(len(array)), 'scope':
            'Catastrophic input geometry only; reaction-center non-equilibrium is not a TS validation.'}


def require_safe(result):
    if result.get('verdict') != 'safe':
        kinds = ', '.join(row.get('kind', 'geometry_error') for row in result.get('hard_failures', []))
        detail = ': ' + kinds if kinds else ''
        # Keep the long-standing path-contract diagnostic recognizable while
        # exposing the machine-readable safety category in the report.
        if any(row.get('kind') == 'catastrophic_overlap' for row in result.get('hard_failures', [])):
            detail += ' (coincident or near-coincident atoms)'
        raise ValueError('geometry safety failed' + detail)
    return result


def parse_gaussian_coordinate_blocks(text):
    """Extract explicit Cartesian blocks from a Gaussian input.

    ``Geom=AllCheck`` inputs intentionally return no blocks: the checkpoint
    geometry is outside this text-level parser and must be assessed separately.
    """
    lines = str(text).splitlines()
    blocks = []
    header = re.compile(r'^\s*-?\d+\s+\d+\s*$')
    number = re.compile(r'^' + _FLOAT + r'$')
    for index, line in enumerate(lines):
        if not header.fullmatch(line):
            continue
        rows = []
        for candidate in lines[index + 1:]:
            if not candidate.strip():
                break
            fields = candidate.split()
            if len(fields) != 4 or not all(number.fullmatch(value) for value in fields[1:]):
                break
            symbol = _symbol(fields[0])
            if symbol is None:
                break
            rows.append((symbol, *[float(value.replace('D', 'E').replace('d', 'e')) for value in fields[1:]]))
        if rows:
            blocks.append(rows)
    return blocks


def assess_gaussian_input(text, *, profile='general'):
    blocks = parse_gaussian_coordinate_blocks(text)
    assessments = []
    for rows in blocks:
        assessments.append(assess([row[0] for row in rows], [row[1:] for row in rows], profile=profile))
    return assessments

