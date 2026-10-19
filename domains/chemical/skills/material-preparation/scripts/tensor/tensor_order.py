import sys
from pathlib import Path

_SKILLS = next(parent for parent in Path(__file__).resolve().parents if (parent / "_shared").is_dir())
_SCRIPTS = _SKILLS / "material-preparation" / "scripts"
for _part in ("materials", "reaction", "geometry", "diagnostics", "tensor", "_shared"):
    sys.path.insert(0, str(_SCRIPTS / _part if _part != "_shared" else _SKILLS / _part))

"""Permute Cartesian tensors consistently without rotating or changing units."""
import numpy as np

from analysis_material import numeric_array, read_order
from material import object_fields


def reorder_tensors(value, order):
    object_fields(value, ('schema_version', 'atom_ids', 'axis_order', 'representation', 'units',
                         'coordinates', 'gradient', 'hessian', 'modes', 'masses', 'elements',
                         'frequencies_cm-1', 'provenance'), 'tensors')
    if value.get('schema_version') != 'chemical-tensors/1' or value.get('axis_order') != 'atom-major-xyz':
        raise ValueError('chemical-tensors/1 with axis_order=atom-major-xyz required')
    if value.get('representation') != 'cartesian':
        raise ValueError('only Cartesian, non-mass-weighted tensors are supported')
    ids, permutation, _ = read_order(order)
    n = len(ids)
    if not n or value.get('atom_ids') != ids:
        raise ValueError('tensor atom_ids must exactly match the nonempty input order')
    units = value.get('units')
    fields = [k for k in ('coordinates', 'gradient', 'hessian', 'modes') if k in value]
    if not fields:
        raise ValueError('at least one tensor required')
    if not isinstance(units, dict) or set(units) != set(fields) or any(not isinstance(u, str) or not u.strip() for u in units.values()):
        raise ValueError('explicit units required for each supplied tensor only')
    result = {**value, 'atom_ids': order['output_atom_ids']}
    cartesian = [3 * i + axis for i in permutation for axis in range(3)]
    for key in fields:
        shape = (3 * n, 3 * n) if key == 'hessian' else (n, 3)
        if key == 'modes':
            if not isinstance(value[key], list) or not value[key]:
                raise ValueError('modes must be a nonempty K x N x 3 array')
            shape = (len(value[key]), n, 3)
        array = numeric_array(value[key], shape, key)
        if key == 'hessian':
            if not np.allclose(array, array.T, rtol=1e-8, atol=1e-10):
                raise ValueError('Hessian must be symmetric')
            array = array[np.ix_(cartesian, cartesian)]
        elif key == 'modes':
            array = array[:, permutation, :]
        else:
            array = array[permutation]
        result[key] = array.tolist()
    if 'masses' in value:
        masses = numeric_array(value['masses'], (n,), 'masses')
        if np.any(masses <= 0):
            raise ValueError('masses must be positive atomic mass units')
        result['masses'] = masses[permutation].tolist()
    if 'elements' in value:
        from xyz import PERIODIC_TABLE
        if not isinstance(value['elements'], list) or len(value['elements']) != n or any(e not in PERIODIC_TABLE[1:] for e in value['elements']):
            raise ValueError('elements must identify all atoms')
        result['elements'] = [value['elements'][i] for i in permutation]
    if 'frequencies_cm-1' in value:
        if 'modes' not in value:
            raise ValueError('frequencies_cm-1 requires modes in the same order')
        result['frequencies_cm-1'] = numeric_array(value['frequencies_cm-1'], (len(value['modes']),), 'frequencies_cm-1').tolist()
    result['provenance'] = {'operation': 'atom_permutation_only', 'order': order,
                            'previous': value.get('provenance'),
                            'scope': 'No spatial rotation, mass weighting, normalization, unit conversion or atom-ID renaming'}
    return result
