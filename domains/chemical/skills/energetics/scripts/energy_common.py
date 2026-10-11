"""Explicit quantities and shared validation for bounded energy analyses."""
from collections import Counter
import hashlib
import json
import math

import numpy as np
from analysis_material import validate_material
from conformers import compare_conformers, state_comparison
from material import object_fields
from xyz import validate_electronic_state

# CODATA molar constants; all internal energies are Eh per molecule.
R = 8.31446261815324  # J mol^-1 K^-1
HARTREE_J_MOL = 2625499.6394799
CM_K = 1.4387768775039338  # h c / k_B in K cm
UNITS = {'hartree': 1., 'kJ/mol': HARTREE_J_MOL / 1000., 'kcal/mol': HARTREE_J_MOL / 4184.}
QUANTITIES = ('E', 'ZPE', 'E+ZPE', 'H', 'G')


def canonical(value):
    return 'sha256:' + hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def fields(value, allowed, name):
    object_fields(value, allowed, name)
    return value


def number(value, name, positive=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or positive and value <= 0:
        raise ValueError(name + ' requires a finite ' + ('positive ' if positive else '') + 'number')
    return float(value)


def integer(value, name, maximum=1000000):
    if type(value) is not int or not 1 <= value <= maximum:
        raise ValueError(name + ' requires a bounded positive integer')
    return value


def label(value, name):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(name + ' requires nonempty text')
    return value


def source(value):
    if not isinstance(value, str) or len(value) != 71 or not value.startswith('sha256:') or any(c not in '0123456789abcdef' for c in value[7:]):
        raise ValueError('source_sha256 requires a SHA-256 digest')
    return value


def material(value):
    result = validate_material(value, canonical(value))
    if not result['atoms'] or len(result['atoms']) > 512:
        raise ValueError('energy analysis requires 1..512 atoms')
    if type(value.get('charge')) is not int:
        raise ValueError('declared charge required')
    integer(value.get('multiplicity'), 'multiplicity', 100)
    if value.get('electronic_state', {}).get('kind') != 'ground':
        raise ValueError('this energy analysis supports declared ground states; excited-state identity needs a dedicated adapter')
    for atom in result['atoms']:
        label(atom.get('element'), 'element')
        if atom.get('isotope') is not None:
            integer(atom['isotope'], 'isotope', 300)
    validate_electronic_state([(a['element'], 0., 0., 0.) for a in result['atoms']], value['charge'], value['multiplicity'])
    return result


def model(value):
    fields(value, ('method', 'basis', 'solvent'), 'model')
    label(value.get('method'), 'method')
    if 'basis' not in value or 'solvent' not in value:
        raise ValueError('model must explicitly specify basis and solvent (null if absent)')
    if value['basis'] is not None:
        label(value['basis'], 'basis')
    if value['solvent'] is not None:
        fields(value['solvent'], ('name', 'model'), 'solvent')
        label(value['solvent'].get('name'), 'solvent name')
        label(value['solvent'].get('model'), 'solvent model')
    return value


def standard(value):
    fields(value, ('kind', 'value'), 'standard state')
    if value.get('kind') not in ('pressure_pa', 'concentration_mol_l'):
        raise ValueError('standard state kind must be pressure_pa or concentration_mol_l')
    number(value.get('value'), 'standard state value', True)
    return value


def concentration(state, temperature):
    standard(state)
    return state['value'] if state['kind'] == 'concentration_mol_l' else state['value'] / (R * temperature * 1000.)


def standard_correction(old, new, temperature):
    number(temperature, 'temperature_k', True)
    return R * temperature / HARTREE_J_MOL * (math.log(concentration(new, temperature)) - math.log(concentration(old, temperature)))


def composition(m):
    return Counter((a['element'], a.get('isotope')) for a in m['atoms'])


def same_geometry(left, right):
    state = state_comparison(left['value'], right['value'])
    if state['status'] != 'compatible_declarations':
        raise ValueError('incompatible or incomplete electronic state declarations')
    if left['coordinates'] is None or right['coordinates'] is None:
        raise ValueError('electronic/thermal combination requires both geometries')
    if left['mol'] is not None and right['mol'] is not None:
        check = compare_conformers(left, right, rmsd_threshold=.01)
        if check['geometry_status'] != 'match':
            raise ValueError('electronic/thermal geometry compatibility not established')
        return {'method': 'graph_mapping_proper_rotation', 'rmsd_angstrom': check['matching_candidate']['rmsd_angstrom']}
    # Graphless TS materials: only exact ordered geometry bindings are accepted.
    if (left['ids'] != right['ids'] or [(a['element'], a.get('isotope')) for a in left['atoms']] !=
            [(a['element'], a.get('isotope')) for a in right['atoms']] or
            not np.allclose(left['coordinates'], right['coordinates'], rtol=0, atol=1e-8)):
        raise ValueError('graphless materials require identical ordered geometries')
    return {'method': 'exact_ordered_geometry', 'rmsd_angstrom': 0.}


def schema(spec, name, allowed):
    fields(spec, ('schema_version', *allowed), name)
    if spec.get('schema_version') != name:
        raise ValueError(name + ' required')


def finite_result(value):
    json.dumps(value, allow_nan=False)
    return value
