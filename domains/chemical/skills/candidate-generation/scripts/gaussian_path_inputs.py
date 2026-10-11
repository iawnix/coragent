"""Gaussian input serialization and file provenance, independent of reaction class."""
import hashlib
import json
from pathlib import Path
import shutil


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


def write_irc(spec_file, spec, checkpoint, output, max_points):
    checkpoint = Path(checkpoint).resolve()
    if not checkpoint.is_file() or checkpoint.stat().st_size == 0:
        raise ValueError('nonempty collected TS checkpoint required')
    if type(max_points) is not int or not 2 <= max_points <= 500:
        raise ValueError('max_points must be between 2 and 500')
    output = directory(output)
    shutil.copyfile(checkpoint, output/'ts.chk')
    rows = []
    for direction in ('forward','reverse'):
        name = direction+'.gjf'
        route = f'IRC=({direction.capitalize()},ReadFC,MaxPoints={max_points},StepSize=5) Geom=AllCheck Guess=Read SCF=Tight Int=UltraFine NoSymm'
        (output/name).write_text(header(spec, direction+'.chk', route, old='ts.chk')+'\n')
        rows.append({'direction':direction,'path':str(output/name),'sha256':digest(output/name)})
    result = {'schema_version':'chemical-irc-inputs/1', 'spec_sha256':digest(spec_file),
              'checkpoint':{'path':str(output/'ts.chk'),'sha256':digest(output/'ts.chk')},'inputs':rows,
              'limitations':['Checkpoint bytes are retained, not parsed: verify its method, atom order, charge/spin and Hessian against the collected TS evidence.',
                             'Assess saddle evidence and record unresolved checks before interpreting IRC.']}
    write_json(output/'irc_inputs.json', result)
    return result
