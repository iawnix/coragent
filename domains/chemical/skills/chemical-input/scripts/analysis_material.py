"""Read validated material/order contracts in their current atom order."""
import json
from pathlib import Path

import numpy as np
from rdkit import Chem

from material import digest, graph_material, object_fields, permutation


def read_json(path):
    raw = Path(path).read_bytes()
    if len(raw) > 32 * 1024 * 1024:
        raise ValueError('analysis input exceeds 32 MiB')
    return json.loads(raw), digest(raw)


def numeric_array(value, shape, name):
    def has_bool(item):
        return isinstance(item, (bool, np.bool_)) or isinstance(item, (list, tuple)) and any(has_bool(v) for v in item)
    if has_bool(value):
        raise ValueError(f'{name} cannot contain booleans')
    raw = np.asarray(value)
    if raw.dtype.kind not in 'fiu' or raw.shape != shape:
        raise ValueError(f'{name} requires numeric shape {shape}')
    result = raw.astype(float)
    if not np.isfinite(result).all():
        raise ValueError(f'{name} must contain finite numbers')
    return result


def read_order(value):
    if not isinstance(value, dict) or value.get('schema_version') != 'chemical-material-order/1' or value.get('index_base') != 0:
        raise ValueError('chemical-material-order/1 with index_base=0 required')
    ids = value.get('input_atom_ids')
    if (not isinstance(ids, list) or any(not isinstance(v, str) or not v for v in ids)
            or len(set(ids)) != len(ids)):
        raise ValueError('order requires unique input atom IDs')
    order = permutation(value.get('new_to_old'), len(ids), 'new_to_old')
    inverse = permutation(value.get('old_to_new'), len(ids), 'old_to_new')
    if [inverse[i] for i in order] != list(range(len(ids))) or value.get('output_atom_ids') != [ids[i] for i in order]:
        raise ValueError('order inverse or output atom IDs disagree')
    return ids, order, inverse


def make_order(ids, order):
    order = permutation(order, len(ids), 'new_to_old')
    inverse = [0] * len(order)
    for new, old in enumerate(order):
        inverse[old] = new
    return {'schema_version': 'chemical-material-order/1', 'index_base': 0,
            'input_atom_ids': ids, 'output_atom_ids': [ids[i] for i in order],
            'new_to_old': order, 'old_to_new': inverse,
            'source': 'mapping_candidate', 'scope': 'Candidate correspondence, not a verified reaction trajectory'}


def read_material(path):
    value, sha = read_json(path)
    return validate_material(value, sha)


def validate_material(value, sha):
    """Validate an embedded material as well as a standalone imported file."""
    if not isinstance(value, dict) or value.get('schema_version') != 'chemical-material/1':
        raise ValueError('chemical-material/1 required')
    ids, order, inverse = read_order(value.get('atom_order'))
    atoms = value.get('atoms')
    if not isinstance(atoms, list) or len(atoms) != len(ids):
        raise ValueError('material atoms and order differ')
    if any(not isinstance(a, dict) or a.get('atom_id') != ids[order[i]] or a.get('input_index') != order[i]
           for i, a in enumerate(atoms)):
        raise ValueError('material atom IDs/indexes and order disagree')
    coords = None
    if value.get('geometry') is not None:
        if not isinstance(value['geometry'], dict) or value['geometry'].get('unit') != 'angstrom':
            raise ValueError('comparison requires angstrom geometry')
        coords = numeric_array([a.get('coordinates') for a in atoms], (len(ids), 3), 'coordinates')
    mol = None
    graph = value.get('graph')
    if graph is not None:
        if not isinstance(graph, dict):
            raise ValueError('graph must be an object')
        _, full, rows = graph_material(graph.get('smiles'))
        graph_to_input = permutation(graph.get('graph_to_input'), len(ids), 'graph_to_input')
        if len(rows) != len(ids):
            raise ValueError('graph atom count differs from material')
        output_to_graph = [0] * len(ids)
        for g, old in enumerate(graph_to_input):
            new = inverse[old]
            output_to_graph[new] = g
            if any(atoms[new].get(k) != rows[g][k] for k in ('element', 'isotope', 'atom_map')):
                raise ValueError('material graph/element/isotope/map correspondence differs')
        mol = Chem.RenumberAtoms(full, output_to_graph)
        if value.get('charge') != Chem.GetFormalCharge(mol):
            raise ValueError('material charge differs from its graph')
    return {'value': value, 'sha256': sha, 'ids': [a['atom_id'] for a in atoms],
            'atoms': atoms, 'mol': mol, 'coordinates': coords}
