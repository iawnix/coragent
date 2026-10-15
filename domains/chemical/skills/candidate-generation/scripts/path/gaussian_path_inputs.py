"""Gaussian input serialization and file provenance, independent of reaction class."""
import hashlib
import json
from pathlib import Path


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
    rtext, ptext = render(reactant, rxyz), render(product, pxyz)
    (folder/'reactants.xyz').write_text(f'{len(rxyz)}\n{branch} reactant seed\n{rtext}\n')
    (folder/'product.xyz').write_text(f'{len(pxyz)}\n{branch} product seed\n{ptext}\n')
    write_json(folder/'spec.json', spec)
    marker = 'CoRAgentSpec '+digest(folder/'spec.json').removeprefix('sha256:')
    charge = f'{spec["charge"]} {spec["multiplicity"]}'
    route = 'Opt=(QST2,CalcFC,MaxCycles=200) Freq SCF=Tight Int=UltraFine NoSymm'
    (folder/'ts.gjf').write_text(header(spec, 'ts.chk', route)+f'{marker}\n{branch} reactants\n\n{charge}\n{rtext}\n\n{marker}\n{branch} product\n\n{charge}\n{ptext}\n\n')
    write_json(folder/'atom_order.json', {'schema_version':'chemical-atom-order/1', 'atoms':atom_order})
    return {name:{'path':str(folder/name), 'sha256':digest(folder/name)} for name in
            ('ts.gjf','reactants.xyz','product.xyz','spec.json','atom_order.json')}


