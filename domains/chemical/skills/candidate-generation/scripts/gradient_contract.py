"""Calculator evidence and explicit gradient-to-force conversion, in atomic energy units."""
import copy
import math

import numpy as np

from analysis_material import numeric_array
from ensemble_material import canonical
from path_contract import BOHR_ANGSTROM


def calculation(m, xyz, model, energy, gradient, sources):
    return {'schema_version': 'chemical-calculation/1', 'atom_ids': list(m['ids']), 'coordinates': np.asarray(xyz).tolist(),
            'coordinate_unit': 'angstrom', 'model': copy.deepcopy(model), 'geometry_sha256': canonical(np.asarray(xyz).tolist()),
            'energy': {'value': energy, 'unit': 'hartree', 'quantity': 'electronic_energy'},
            'gradient': {'values': np.asarray(gradient).tolist(), 'unit': 'hartree/bohr', 'representation': 'cartesian', 'quantity': 'dE/dR'},
            'converged': True, 'sources': sources}


def evaluate_evidence(value, m, xyz, model):
    if not isinstance(value, dict) or value.get('schema_version') != 'chemical-calculation/1': raise ValueError('calculator evidence contract required')
    if value.get('atom_ids') != m['ids'] or value.get('model') != model: raise ValueError('calculator atom order/model differs')
    if value.get('converged') is not True or not value.get('sources'): raise ValueError('converged calculator evidence with sources required')
    xyz = np.asarray(xyz)
    coordinates = numeric_array(value.get('coordinates'), xyz.shape, 'calculator geometry')
    if value.get('coordinate_unit') != 'angstrom' or not np.allclose(coordinates, xyz, atol=1e-9, rtol=0) or value.get('geometry_sha256') != canonical(xyz.tolist()):
        raise ValueError('calculator geometry binding differs')
    e, g = value.get('energy'), value.get('gradient')
    if not isinstance(e, dict) or e.get('unit') != 'hartree' or e.get('quantity') != 'electronic_energy' or type(e.get('value')) not in (int, float) or not math.isfinite(e['value']):
        raise ValueError('finite electronic energy in hartree required')
    if not isinstance(g, dict) or g.get('quantity') != 'dE/dR' or g.get('representation') != 'cartesian' or g.get('unit') not in ('hartree/bohr', 'hartree/angstrom'):
        raise ValueError('Cartesian dE/dR gradient required; an energy-only calculator cannot run NEB')
    gradient = numeric_array(g.get('values'), xyz.shape, 'gradient')
    if g['unit'] == 'hartree/bohr': gradient = gradient / BOHR_ANGSTROM
    return float(e['value']), -gradient
