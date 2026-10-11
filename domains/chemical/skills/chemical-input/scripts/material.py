"""Import chemical materials without guessing geometry, state or atom trajectories."""
import hashlib
import json
import math
from pathlib import Path
import re
import sys

from rdkit import Chem, rdBase

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / '_shared'))
from chemical_identity import identity
from xyz import PERIODIC_TABLE, validate_electronic_state


def digest(content):
    return 'sha256:' + hashlib.sha256(content).hexdigest()


def object_fields(value, allowed, name):
    if not isinstance(value, dict) or set(value) - set(allowed):
        raise ValueError(f'{name} must be an object with only: {", ".join(allowed)}')


def permutation(value, count, name):
    if (not isinstance(value, list) or len(value) != count
            or any(type(i) is not int for i in value) or sorted(value) != list(range(count))):
        raise ValueError(f'{name} must be a zero-based permutation of all {count} atom indexes')
    return value


def xyz_text(text):
    """Read exactly one plain XYZ frame; retain text separately without round-tripping."""
    lines = text.splitlines()
    try:
        count = int(lines[0])
    except (IndexError, ValueError) as exc:
        raise ValueError('XYZ requires an atom count and one complete frame') from exc
    if count < 1 or len(lines) < count + 2 or any(line.strip() for line in lines[count + 2:]):
        raise ValueError('XYZ requires exactly one complete frame; select trajectory frames explicitly')
    rows = []
    for line in lines[2:count + 2]:
        fields = line.split()
        if len(fields) != 4 or fields[0] not in PERIODIC_TABLE[1:]:
            raise ValueError('XYZ requires an element symbol and three coordinates; extended properties are unsupported')
        coords = [float(v.replace('D', 'E').replace('d', 'e')) for v in fields[1:]]
        if not all(math.isfinite(v) for v in coords):
            raise ValueError('XYZ coordinates must be finite')
        rows.append({'element': fields[0], 'coordinates': coords, 'isotope': None,
                     'atom_map': None, 'origin': 'xyz_row'})
    return rows


def graph_material(smiles):
    if not isinstance(smiles, str) or not smiles.strip():
        raise ValueError('graph requires nonempty SMILES')
    if any(character.isspace() for character in smiles.strip()):
        raise ValueError('supply one plain molecular SMILES; separate names, extra records and CXSMILES explicitly')
    params = Chem.SmilesParserParams()
    params.removeHs = False
    mol = Chem.MolFromSmiles(smiles, params)
    if mol is None or not mol.GetNumAtoms():
        raise ValueError('invalid molecular SMILES')
    if any(a.GetAtomicNum() == 0 for a in mol.GetAtoms()):
        raise ValueError('material requires explicit chemical elements, not wildcard atoms')
    maps = [a.GetAtomMapNum() for a in mol.GetAtoms() if a.GetAtomMapNum()]
    if len(set(maps)) != len(maps):
        raise ValueError('explicit atom-map labels must be unique within a material')
    full = Chem.AddHs(mol)
    rows = [{'element': a.GetSymbol(), 'isotope': a.GetIsotope() or None,
             'atom_map': a.GetAtomMapNum() or None,
             'origin': 'smiles_atom' if a.GetIdx() < mol.GetNumAtoms() else 'added_hydrogen'}
            for a in full.GetAtoms()]
    return mol, full, rows


def electronic_state(value):
    if value is None:
        return {'kind': 'unspecified', 'source': 'unknown', 'verification': 'not_assessed'}
    object_fields(value, ('kind', 'label', 'root', 'method', 'note'), 'electronic_state')
    if value.get('kind') not in {'unspecified', 'ground', 'excited', 'broken_symmetry'}:
        raise ValueError('electronic_state.kind must be unspecified, ground, excited or broken_symmetry')
    for key in ('label', 'method', 'note'):
        if key in value and (not isinstance(value[key], str) or not value[key].strip()):
            raise ValueError(f'electronic_state.{key} must be nonempty text')
    if 'root' in value:
        if (type(value['root']) is not int or value['root'] < 1
                or value['kind'] != 'excited' or not value.get('method')):
            raise ValueError('an excited root requires a positive integer and explicit method; root identity is method-local')
    return {**value, 'source': 'declared', 'verification': 'not_assessed'}


def build_material(spec, source_digest):
    object_fields(spec, ('schema_version', 'format', 'text', 'charge', 'multiplicity', 'electronic_state',
                         'arrangement', 'fragments', 'atom_ids', 'new_to_old', 'graph', 'graph_to_input',
                         'coordinate_unit'), 'material input')
    if spec.get('schema_version') != 'chemical-material-input/1':
        raise ValueError('chemical-material-input/1 required')
    fmt, text = spec.get('format'), spec.get('text')
    if fmt not in {'smiles', 'name', 'xyz'} or not isinstance(text, str) or not text.strip():
        raise ValueError('format must be smiles/name/xyz with nonempty text')
    if '\x00' in text:
        raise ValueError('input text cannot contain NUL')
    if 'coordinate_unit' in spec and (fmt != 'xyz' or spec['coordinate_unit'] != 'angstrom'):
        raise ValueError('this importer accepts XYZ angstrom only; preserve and explicitly convert other units first')
    arrangement = spec.get('arrangement', 'unspecified')
    if arrangement not in {'unspecified', 'isolated_species', 'separate_reactants', 'complex'}:
        raise ValueError('invalid arrangement; fragment count alone does not establish association')
    state = electronic_state(spec.get('electronic_state'))
    charge, multiplicity = spec.get('charge'), spec.get('multiplicity')
    if charge is not None and type(charge) is not int:
        raise ValueError('charge must be an integer or null')
    if multiplicity is not None and (type(multiplicity) is not int or multiplicity < 1):
        raise ValueError('multiplicity must be a positive integer or null')

    mol = full = None
    rows = xyz_text(text) if fmt == 'xyz' else []
    graph = spec.get('graph')
    if graph is not None:
        if fmt == 'smiles':
            raise ValueError('SMILES input already supplies its graph')
        object_fields(graph, ('smiles', 'source', 'note'), 'graph')
        if graph.get('source') not in {'user', 'lookup', 'agent'} or not isinstance(graph.get('note'), str) or not graph['note'].strip():
            raise ValueError('selected graph requires source=user/lookup/agent and a provenance note')
    graph_input = {'smiles': text, 'source': 'user', 'note': 'supplied SMILES'} if fmt == 'smiles' else graph
    graph_order = None
    graph_metadata = None
    if graph_input is not None:
        mol, full, graph_rows = graph_material(graph_input.get('smiles'))
        graph_charge = Chem.GetFormalCharge(mol)
        if charge is not None and charge != graph_charge:
            raise ValueError('declared charge differs from the supplied molecular graph')
        charge = graph_charge
        if fmt == 'xyz':
            graph_order = permutation(spec.get('graph_to_input'), len(rows), 'graph_to_input')
            if len(graph_rows) != len(rows):
                raise ValueError('graph and XYZ must contain the same atoms including all H')
            for graph_index, input_index in enumerate(graph_order):
                if graph_rows[graph_index]['element'] != rows[input_index]['element']:
                    raise ValueError('graph_to_input element correspondence differs')
                rows[input_index].update({key: graph_rows[graph_index][key] for key in ('isotope', 'atom_map')})
        else:
            rows = graph_rows
            graph_order = list(range(len(rows)))
        graph_metadata = {**graph_input, 'identity': identity(mol),
                          'atom_order': 'RDKit parsed explicit atoms followed by added H',
                          'graph_to_input': graph_order, 'rdkit_version': rdBase.rdkitVersion,
                          'geometry_identity': 'not_assessed'}
    if 'graph_to_input' in spec and (fmt != 'xyz' or graph_input is None):
        raise ValueError('graph_to_input requires XYZ and a supplied graph')

    count = len(rows)
    if not count and any(key in spec for key in ('atom_ids', 'new_to_old', 'fragments')):
        raise ValueError('atom-level metadata requires a structure; resolve the name first')
    ids = spec.get('atom_ids', [f'atom_{i + 1}' for i in range(count)])
    if (not isinstance(ids, list) or len(ids) != count
            or any(not isinstance(v, str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_.:-]{0,127}', v) for v in ids)
            or len(set(ids)) != count):
        raise ValueError('atom_ids must be unique local identifiers for every input atom')
    order = permutation(spec.get('new_to_old', list(range(count))), count, 'new_to_old')
    inverse = [0] * count
    for new, old in enumerate(order):
        inverse[old] = new
    for i, row in enumerate(rows):
        row.update(atom_id=ids[i], input_index=i)

    fragments, fragment_source = None, 'unknown'
    if full is not None:
        fragments = [[graph_order[i] for i in indexes] for indexes in Chem.GetMolFrags(full)]
        fragment_source = 'supplied_graph'
    if 'fragments' in spec:
        supplied = spec['fragments']
        if (not isinstance(supplied, list) or not supplied
                or any(not isinstance(group, list) or not group for group in supplied)):
            raise ValueError('fragments must partition all input atom indexes into nonempty groups')
        permutation([i for group in supplied for i in group], count, 'fragments')
        if fragments is not None and {frozenset(g) for g in fragments} != {frozenset(g) for g in supplied}:
            raise ValueError('declared fragments disagree with graph connected components')
        fragments, fragment_source = supplied, 'declared'

    electrons = sum(Chem.GetPeriodicTable().GetAtomicNumber(row['element']) for row in rows) - charge if count and charge is not None else None
    if electrons is not None and electrons < 0:
        raise ValueError('charge exceeds the total nuclear charge')
    parity = 'not_assessed'
    if count and charge is not None and multiplicity is not None:
        validate_electronic_state([(row['element'], 0., 0., 0.) for row in rows], charge, multiplicity)
        parity = 'compatible'
    atom_order = {'schema_version': 'chemical-material-order/1', 'index_base': 0,
                  'input_atom_ids': ids, 'output_atom_ids': [ids[i] for i in order],
                  'new_to_old': order, 'old_to_new': inverse,
                  'source': 'declared_permutation' if 'new_to_old' in spec else 'input_order',
                  'scope': 'Local correspondence only; does not establish a reaction atom mapping'}
    unknown = []
    for key, missing in [('graph', mol is None), ('geometry', fmt != 'xyz'), ('charge', charge is None),
                         ('multiplicity', multiplicity is None), ('electronic_state', state['kind'] == 'unspecified'),
                         ('fragments', fragments is None), ('arrangement', arrangement == 'unspecified')]:
        if missing:
            unknown.append(key)
    material = {'schema_version': 'chemical-material/1',
                'source': {'format': fmt, 'text': text, 'text_sha256': digest(text.encode('utf-8')),
                           'input_sha256': source_digest},
                'graph': graph_metadata, 'identity': identity(mol) if mol is not None else None,
                'charge': charge, 'charge_source': 'declared' if spec.get('charge') is not None else 'supplied_graph' if mol is not None else 'unknown',
                'multiplicity': multiplicity, 'multiplicity_source': 'declared' if multiplicity is not None else 'unknown',
                'electronic_state': state, 'electron_count': electrons, 'electron_count_parity': parity,
                'arrangement': arrangement,
                'fragments': {'source': fragment_source, 'groups': [[ids[i] for i in group] for group in fragments] if fragments is not None else None},
                'atoms': [rows[i] for i in order], 'atom_order': atom_order,
                'geometry': {'unit': 'angstrom', 'unit_source': 'declared' if 'coordinate_unit' in spec else 'XYZ_convention',
                             'status': 'supplied_not_assessed', 'file': 'geometry.xyz',
                             'transform': 'atom_permutation' if order != list(range(count)) else 'none'} if fmt == 'xyz' else None,
                'unknown_fields': unknown,
                'limitations': ['Import does not optimize, embed, infer XYZ bonds or certify a selected name/graph correspondence.',
                                'Declared electronic state and parity compatibility do not verify a wavefunction or backend capability.',
                                'Atom identifiers are scoped to this material lineage; they do not infer reaction mapping.',
                                'A supplied graph/XYZ correspondence checks elements, not geometric or stereochemical identity.']}
    geometry = None
    if fmt == 'xyz':
        geometry = text
        if order != list(range(count)):
            lines = text.splitlines()
            newline = '\r\n' if '\r\n' in text else '\n'
            geometry = newline.join(lines[:2] + [lines[i + 2] for i in order]) + newline
        material['geometry']['sha256'] = digest(geometry.encode('utf-8'))
    return material, geometry


def import_material(source, output):
    raw = Path(source).read_bytes()
    if len(raw) > 4 * 1024 * 1024:
        raise ValueError('material input exceeds 4 MiB')
    material, geometry = build_material(json.loads(raw), digest(raw))
    output = Path(output)
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise ValueError('material output directory must be new or empty')
    output.mkdir(parents=True, exist_ok=True)
    (output / 'source.txt').write_bytes(material['source']['text'].encode('utf-8'))
    if geometry is not None:
        (output / 'geometry.xyz').write_bytes(geometry.encode('utf-8'))
    for name, value in [('material.json', material), ('atom_order.json', material['atom_order'])]:
        (output / name).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
    return material


def main():
    from material_cli import parse_arguments
    args = parse_arguments()
    try:
        result = import_material(args.input, args.output_dir)
        print(json.dumps({'output': str(args.output_dir / 'material.json'), 'unknown_fields': result['unknown_fields']}))
        return 0
    except (ValueError, TypeError, OSError) as exc:
        print(f'{type(exc).__name__}: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
