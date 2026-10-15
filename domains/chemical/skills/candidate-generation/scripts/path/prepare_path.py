"""Prepare mapped QST2 candidates through reusable geometry strategies."""
import json
from pathlib import Path
import sys

from rdkit import Chem, rdBase
from rdkit.Chem.EnumerateStereoisomers import EnumerateStereoisomers, StereoEnumerationOptions

SCRIPTS = Path(__file__).resolve().parent
SKILLS = next(parent for parent in Path(__file__).resolve().parents if (parent / '_shared').is_dir())
SHARED = SKILLS / '_shared'
sys.path[:0] = [str(SCRIPTS), str(SHARED), str(SCRIPTS.parent / 'search'), str(SCRIPTS.parent / 'backends'), str(SCRIPTS.parent / 'neb'), str(SCRIPTS.parent / 'da')]
from reaction_checks import ordered_molecule
from path_specification import preparation_spec, provided_coordinates, select_strategy
from path_geometry import align, coordinates, embed
from gaussian_path_inputs import digest, directory, write_json, write_qst2


def prepare_candidates(spec_file, output, conformers=1, enumerate_stereo=False):
    if type(conformers) is not int or not 1 <= conformers <= 8:
        raise ValueError('conformers must be between 1 and 8')
    spec_file = Path(spec_file).resolve()
    spec = json.loads(spec_file.read_text())
    checks, sides = preparation_spec(spec)
    strategy = select_strategy(spec)
    if any(str(s.specified) == 'Unspecified' for s in Chem.FindPotentialStereo(sides[0])):
        raise ValueError('specify reactant stereochemistry before candidate generation')
    uncertain = [s for s in Chem.FindPotentialStereo(sides[1]) if str(s.specified) == 'Unspecified']
    if uncertain and not enumerate_stereo:
        raise ValueError('unspecified product stereochemistry: use --enumerate-stereo or a specified product')
    supplied = None
    if strategy == 'provided_endpoints':
        if conformers != 1 or enumerate_stereo:
            raise ValueError('provided_endpoints requires conformers=1 and no stereo enumeration; submit each explicit geometry separately')
        endpoints = spec.get('endpoints')
        if not isinstance(endpoints, dict) or set(endpoints) != {'reactants', 'product'}:
            raise ValueError('provided_endpoints requires endpoints.reactants and endpoints.product')
        supplied = [provided_coordinates(endpoints[name], *ordered_molecule(mol))
                    for name, mol in zip(('reactants', 'product'), sides)]
    elif strategy == 'mapped_endpoints' and any(len(Chem.GetMolFrags(mol)) != 1 for mol in sides):
        raise ValueError('automatic mapped_endpoints requires single-fragment endpoints; supply mapped endpoint geometries for fragment placement')
    products = list(EnumerateStereoisomers(sides[1], options=StereoEnumerationOptions(onlyUnassigned=True, maxIsomers=16))) if enumerate_stereo else [sides[1]]
    output = directory(output)
    rows = []
    for stereo_index, product in enumerate(products):
        for conformer_index in range(conformers):
            branch = f'candidate-{stereo_index+1}-{conformer_index+1}'
            folder = output/branch
            folder.mkdir()
            row = {'id': branch, 'stereo_index': stereo_index, 'conformer_index': conformer_index}
            try:
                local_spec = {**spec, 'mapped_smiles': spec['mapped_smiles'].split('>>')[0]+'>>'+Chem.MolToSmiles(product),
                              'parent_spec_sha256': digest(spec_file)}
                preparation_spec(local_spec)
                reactant, atom_order = ordered_molecule(sides[0])
                product_full, product_order = ordered_molecule(product)
                if atom_order != product_order:
                    raise ValueError('reactant/product atom correspondence differs')
                seed = 17001 + 97*stereo_index + conformer_index
                if supplied is not None:
                    rxyz, pxyz = supplied
                else:
                    reactant = embed(reactant, seed)
                    product_full = embed(product_full, seed)
                    if strategy == 'diels_alder':
                        from da_geometry import da_endpoints
                        rxyz, pxyz = da_endpoints(spec, reactant, product_full)
                    else:
                        rxyz, pxyz = coordinates(reactant), coordinates(product_full)
                        rotation, left, right = align(pxyz, rxyz)
                        pxyz = (pxyz-left) @ rotation+right
                files = write_qst2(folder, local_spec, reactant, product_full, rxyz, pxyz, atom_order, branch)
                row.update(status='prepared', atom_count=len(atom_order), seed=None if supplied is not None else seed, files=files)
            except (ValueError, RuntimeError) as exc:
                row.update(status='failed', error=str(exc))
            rows.append(row)
    module_paths = {
        'prepare_path.py': SCRIPTS / 'prepare_path.py',
        'path_specification.py': SCRIPTS / 'path_specification.py',
        'path_geometry.py': SCRIPTS / 'path_geometry.py',
        'gaussian_path_inputs.py': SCRIPTS / 'gaussian_path_inputs.py',
        'da_geometry.py': SCRIPTS.parent / 'da' / 'da_geometry.py',
    }
    modules = ['prepare_path.py', 'path_specification.py', 'path_geometry.py', 'gaussian_path_inputs.py']
    if strategy == 'diels_alder':
        modules.append('da_geometry.py')
    implementation = {name:digest(module_paths[name]) for name in modules}
    implementation.update({'_shared/'+name:digest(SHARED/name) for name in ('reaction_checks.py', 'xyz.py')})
    result = {'schema_version':'chemical-candidates/1', 'source_spec_sha256':digest(spec_file),
              'strategy':'mapped_da_qst2' if strategy == 'diels_alder' else strategy,
              'rdkit_version':rdBase.rdkitVersion, 'script_sha256':digest(__file__),
              'implementation_sha256':implementation,
              'candidates':rows, 'mapping_checks':checks,
              'stereo_enumeration_limit':16, 'stereo_limit_reached':len(products)==16,
              'limitations':['Endpoint seeds are not verified stationary points; QST2 convergence is not guaranteed.',
                             'Finite sampling does not establish exhaustive pathway coverage.',
                             'Provided geometry is checked for atom identity and finite coordinates, not graph/stereo agreement or optimization quality.',
                             'Reaction-specific validators apply only within their documented scope.']}
    write_json(output/'candidates.json', result)
    return result


def main():
    from cli import parse_arguments
    a = parse_arguments()
    result = prepare_candidates(a.spec, a.output_dir, a.conformers, a.enumerate_stereo)
    print(json.dumps(result, allow_nan=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
