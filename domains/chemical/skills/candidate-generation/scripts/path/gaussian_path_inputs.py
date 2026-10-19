"""Gaussian input serialization and file provenance, independent of reaction class."""
import hashlib
import json
from pathlib import Path
from gaussian_input import serialize_structures, inspect_qst_structures
from geometry_safety import assess, require_safe


def digest(path):
    return 'sha256:' + hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')


def directory(path):
    path = Path(path).resolve()
    path.mkdir(parents=True, exist_ok=True)
    if any(path.iterdir()):
        raise ValueError('output directory must be empty')
    return path


def render(mol, xyz):
    return '\n'.join(f'{atom.GetSymbol():2s} {row[0]: .10f} {row[1]: .10f} {row[2]: .10f}'
                     for atom, row in zip(mol.GetAtoms(), xyz))


def header(spec, checkpoint, route, old=None):
    return ((f'%oldchk={old}\n' if old else '') +
            f'%chk={checkpoint}\n%nprocshared={spec["threads"]}\n%mem={spec["memory_mb"]}MB\n'
            f'#p {spec["method"]}/{spec["basis"]} {route}\n\n')


def write_qst2(folder, spec, reactant, product, rxyz, pxyz, atom_order, branch):
    structures = []
    geometry_reports = []
    for mol, xyz, title in ((reactant, rxyz, f'{branch} reactants'), (product, pxyz, f'{branch} product')):
        if mol.GetNumAtoms() != len(xyz):
            raise ValueError('coordinate count differs from molecular graph')
        structures.append({'title': title, 'charge': spec['charge'], 'multiplicity': spec['multiplicity'],
                           'atoms': [(a.GetSymbol(), *row) for a, row in zip(mol.GetAtoms(), xyz)]})
        geometry_reports.append(assess([a.GetSymbol() for a in mol.GetAtoms()], xyz,
                                      bonded_pairs=[(b.GetBeginAtomIdx(), b.GetEndAtomIdx()) for b in mol.GetBonds()]))
    # Check all blocks before writing the candidate's files.
    inspect_qst_structures(serialize_structures(structures), 'Opt=QST2')
    write_json(folder/'geometry_preflight.json', {'reactant': geometry_reports[0], 'product': geometry_reports[1]})
    for report in geometry_reports:
        require_safe(report)
    rtext, ptext = render(reactant, rxyz), render(product, pxyz)
    (folder/'reactants.xyz').write_text(f'{len(rxyz)}\n{branch} reactant seed\n{rtext}\n')
    (folder/'product.xyz').write_text(f'{len(pxyz)}\n{branch} product seed\n{ptext}\n')
    write_json(folder/'spec.json', spec)
    marker = 'CoRAgentSpec '+digest(folder/'spec.json').removeprefix('sha256:')
    route = 'Opt=(QST2,CalcFC,MaxCycles=200) Freq SCF=Tight Int=UltraFine NoSymm'
    for structure in structures:
        structure['title'] = marker + '\n' + structure['title']
    (folder/'ts.gjf').write_text(header(spec, 'ts.chk', route) + serialize_structures(structures))
    write_json(folder/'atom_order.json', {'schema_version':'chemical-atom-order/1', 'atoms':atom_order})
    return {name:{'path':str(folder/name), 'sha256':digest(folder/name)} for name in
            ('ts.gjf','reactants.xyz','product.xyz','spec.json','atom_order.json','geometry_preflight.json')}


