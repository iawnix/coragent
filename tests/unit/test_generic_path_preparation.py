"""Generic input preparation with deterministic geometry; no real Gaussian calculation."""
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path

import pytest

from tests.unit.test_chemical_path_execution import helper
from reaction_checks import molecules, ordered_molecule
from path_specification import preparation_spec
from input_job import inspect_input
from gaussian_io import read_xyz

irc_spec = importlib.util.spec_from_file_location(
    'chemical_irc_preparation',
    Path(__file__).resolve().parents[2] / 'skills/chemical/validation/scripts/irc_preparation.py',
)
irc_helper = importlib.util.module_from_spec(irc_spec)
irc_spec.loader.exec_module(irc_helper)


RING_OPENING = {
    'schema_version': 'chemical-path-spec/1',
    'mapped_smiles': '[CH2:1]1[CH:2]=[CH:3][CH2:4]1>>[CH2:1]=[CH:2][CH:3]=[CH2:4]',
    'transformation': {'kind': 'explicit', 'bond_changes': [
        {'atoms': [1, 2], 'before': 1, 'after': 2},
        {'atoms': [1, 4], 'before': 1, 'after': 0},
        {'atoms': [2, 3], 'before': 2, 'after': 1},
        {'atoms': [3, 4], 'before': 1, 'after': 2}]},
    'method': 'M062X', 'basis': '6-31G**', 'charge': 0,
    'multiplicity': 1, 'threads': 2, 'memory_mb': 1000,
}


def prepare(tmp_path, spec, **options):
    source = tmp_path / 'spec.json'
    source.write_text(json.dumps(spec))
    return helper.prepare_candidates(source, tmp_path / 'result', **options)


def supplied_substitution():
    spec = {**copy.deepcopy(RING_OPENING), 'charge': -1, 'candidate_strategy': 'provided_endpoints',
            'mapped_smiles': '[Cl-:1].[CH3:2][Br:3]>>[Cl:1][CH3:2].[Br-:3]',
            'transformation': {'kind': 'explicit', 'bond_changes': [
                {'atoms': [1, 2], 'before': 0, 'after': 1},
                {'atoms': [2, 3], 'before': 1, 'after': 0}]}}
    mol, order = ordered_molecule(molecules(spec['mapped_smiles'])[0])
    xyz = [[-4., 0., 0.], [0., 0., 0.], [1.9, 0., 0.],
           [-.3, 1., 0.], [-.3, -.5, .86], [-.3, -.5, -.86]]
    rows = [{'atom': key, 'element': atom.GetSymbol(), 'xyz': pos}
            for key, atom, pos in zip(order, mol.GetAtoms(), xyz)]
    products = copy.deepcopy(rows)
    products[0]['xyz'], products[2]['xyz'] = [1.8, 0., 0.], [-4., 0., 0.]
    spec['endpoints'] = {'reactants': list(reversed(rows)), 'product': products}
    return spec


def test_unimolecular_ring_opening_generates_reproducible_generic_qst2(tmp_path):
    first = tmp_path / 'first'; first.mkdir()
    second = tmp_path / 'second'; second.mkdir()
    result = prepare(first, RING_OPENING, conformers=2)
    repeated = prepare(second, RING_OPENING, conformers=2)
    assert result['strategy'] == 'mapped_endpoints'
    assert len(result['candidates']) == 2
    for row, again in zip(result['candidates'], repeated['candidates']):
        assert row['status'] == 'prepared'
        assert row['files']['ts.gjf']['sha256'] == again['files']['ts.gjf']['sha256']
        path = Path(row['files']['ts.gjf']['path'])
        parsed = inspect_input(path, 'M062X', '6-31G**', 0, 1, 2, 1000)
        assert 'QST2' in parsed['routes'][0]
        assert row['atom_count'] == 10
        branch_spec = Path(row['files']['spec.json']['path'])
        assert hashlib.sha256(branch_spec.read_bytes()).hexdigest() in path.read_text()
    assert 'da_geometry.py' not in result['implementation_sha256']


@pytest.mark.parametrize('bonded', [True, False])
def test_qst_preparer_retains_graph_aware_hydrogen_contact_diagnosis(tmp_path, bonded):
    from rdkit import Chem
    from gaussian_path_inputs import write_qst2
    mol = Chem.MolFromSmiles('[H:1][H:2]' if bonded else '[H:1].[H:2]')
    xyz = [[0., 0., 0.], [.758, 0., 0.]]
    settings = {'charge': 0, 'multiplicity': 1, 'method': 'HF', 'basis': 'STO-3G', 'threads': 1, 'memory_mb': 256}
    folder = tmp_path / 'candidate'; folder.mkdir()
    if bonded:
        files = write_qst2(folder, settings, mol, mol, xyz, xyz, [1, 2], 'fixture')
        assert 'geometry_preflight.json' in files
        assert (folder / 'ts.gjf').is_file()
    else:
        with pytest.raises(ValueError, match='nonreaction_short_contact'):
            write_qst2(folder, settings, mol, mol, xyz, xyz, [1, 2], 'fixture')
        assert not (folder / 'ts.gjf').exists()
    report = json.loads((folder / 'geometry_preflight.json').read_text())
    assert report['reactant']['verdict'] == ('safe' if bonded else 'unsafe')


def test_supplied_multifragment_coordinates_preserve_mapping_and_produce_irc(tmp_path):
    assert not hasattr(helper, 'prepare_irc')
    assert hasattr(irc_helper, 'prepare_irc')
    spec = supplied_substitution()
    result = prepare(tmp_path, spec)
    assert result['strategy'] == 'provided_endpoints'
    row = result['candidates'][0]
    assert row['status'] == 'prepared' and row['seed'] is None
    _, _, atoms = read_xyz(Path(row['files']['reactants.xyz']['path']))
    assert [a[0] for a in atoms] == ['Cl', 'C', 'Br', 'H', 'H', 'H']
    assert list(atoms[0][1:]) == [-4., 0., 0.]
    branch = Path(row['files']['spec.json']['path'])
    inspect_input(Path(row['files']['ts.gjf']['path']), 'M062X', '6-31G**', -1, 1, 2, 1000)
    checkpoint = tmp_path / 'fixture.chk'; checkpoint.write_bytes(b'synthetic checkpoint')
    irc = irc_helper.prepare_irc(branch, checkpoint, tmp_path / 'irc', max_points=12)
    assert Path(irc['checkpoint']['path']).read_bytes() == checkpoint.read_bytes()
    assert irc['spec_sha256'] == row['files']['spec.json']['sha256']
    for item in irc['inputs']:
        text = Path(item['path']).read_text()
        assert item['direction'].capitalize() in text and 'MaxPoints=12' in text
        assert 'Geom=AllCheck' in text and '%oldchk=ts.chk' in text
    # Generic preparation must not silently broaden the specialized DA contract.


def test_explicit_mapped_hydrogen_transfer_retains_the_same_atom_identity(tmp_path):
    spec = {**copy.deepcopy(RING_OPENING), 'candidate_strategy': 'provided_endpoints',
        'mapped_smiles': '[O:1]([H:3])[H:4].[N:2]([H:5])([H:6])[H:7]>>[O-:1][H:4].[N+:2]([H:3])([H:5])([H:6])[H:7]',
        'transformation': {'kind': 'explicit', 'bond_changes': [
            {'atoms': [1, 3], 'before': 1, 'after': 0}, {'atoms': [2, 3], 'before': 0, 'after': 1}]}}
    checks, sides = preparation_spec(spec)
    mol, order = ordered_molecule(sides[0])
    assert order == [[0, i, 0] for i in range(1, 8)]
    assert checks['mapping_valid']
    xyz = [[0.,0.,0.], [3.,0.,0.], [.96,0.,0.], [-.24,.93,0.], [3.,1.,0.], [3.,-.5,.86], [3.,-.5,-.86]]
    rows = [{'atom': key, 'element': a.GetSymbol(), 'xyz': pos} for key,a,pos in zip(order,mol.GetAtoms(),xyz)]
    product = copy.deepcopy(rows); product[2]['xyz'] = [2.,0.,0.]
    spec['endpoints'] = {'reactants': rows, 'product': product}
    row = prepare(tmp_path, spec)['candidates'][0]
    assert row['status'] == 'prepared' and row['atom_count'] == 7
    _, _, reactants = read_xyz(Path(row['files']['reactants.xyz']['path']))
    _, _, products = read_xyz(Path(row['files']['product.xyz']['path']))
    assert reactants[2][0] == products[2][0] == 'H'
    assert reactants[2][1] == .96 and products[2][1] == 2.


@pytest.mark.parametrize('fault, message', [
    ('nonfinite', 'finite'), ('duplicate', 'duplicates'), ('wrong_element', 'elements'),
    ('missing_atom', 'one row per atom'), ('coincident', 'coincident'),
    ('ignored_endpoints', 'must not be ignored'), ('missing_change', 'declared bond changes'),
    ('duplicate_change', 'duplicate bond_changes'), ('wrong_spin', 'electron count'),
])
def test_invalid_specifications_fail_before_writing_candidates(tmp_path, fault, message):
    spec = supplied_substitution()
    if fault == 'nonfinite': spec['endpoints']['product'][0]['xyz'][0] = float('nan')
    if fault == 'duplicate': spec['endpoints']['product'][1]['atom'] = [0, 1, 0]
    if fault == 'wrong_element': spec['endpoints']['product'][0]['element'] = 'C'
    if fault == 'missing_atom': spec['endpoints']['product'].pop()
    if fault == 'coincident': spec['endpoints']['product'][0]['xyz'] = spec['endpoints']['product'][1]['xyz']
    if fault == 'ignored_endpoints': spec['candidate_strategy'] = 'mapped_endpoints'
    if fault == 'missing_change': spec['transformation']['bond_changes'].pop()
    if fault == 'duplicate_change': spec['transformation']['bond_changes'] *= 2
    if fault == 'wrong_spin': spec['multiplicity'] = 2
    with pytest.raises(ValueError, match=message):
        prepare(tmp_path, spec)
    assert not (tmp_path/'result').exists()


def test_multifragment_auto_and_implicit_h_transfer_request_explicit_correspondence(tmp_path):
    spec = supplied_substitution(); del spec['endpoints']; del spec['candidate_strategy']
    with pytest.raises(ValueError, match='fragment placement'):
        prepare(tmp_path, spec)
    spec = {**copy.deepcopy(RING_OPENING), 'mapped_smiles': '[OH2:1].[NH3:2]>>[OH-:1].[NH4+:2]',
            'transformation': {'kind': 'explicit', 'bond_changes': []}}
    with pytest.raises(ValueError, match='explicitly map transferred H'):
        prepare(tmp_path, spec)
    assert not (tmp_path/'result').exists()


def test_generic_settings_allow_a_doublet_but_reject_unsupported_mass_and_invalid_smiles():
    # Identity mapping exercises state validation, not a proposed reaction mechanism.
    spec = {**copy.deepcopy(RING_OPENING), 'mapped_smiles': '[CH3:1]>>[CH3:1]',
            'multiplicity': 2, 'transformation': {'kind': 'explicit', 'bond_changes': []}}
    _, sides = preparation_spec(spec)
    assert sides[0].GetAtomWithIdx(0).GetNumRadicalElectrons() == 1
    for smiles, message in [(None, 'SMILES string'), ('>>', 'invalid reaction SMILES'),
                            ('[13CH3:1]>>[13CH3:1]', 'isotope-specific')]:
        with pytest.raises(ValueError, match=message):
            preparation_spec({**spec, 'mapped_smiles': smiles})


@pytest.mark.parametrize('options', [{'conformers': 2}, {'enumerate_stereo': True}])
def test_supplied_endpoints_are_not_silently_repeated_or_stereo_enumerated(tmp_path, options):
    with pytest.raises(ValueError, match='provided_endpoints requires conformers=1'):
        prepare(tmp_path, supplied_substitution(), **options)
    assert not (tmp_path/'result').exists()


def test_failed_embedding_retains_branch_failures(tmp_path, monkeypatch):
    def fail(*args):
        raise ValueError('synthetic embedding failure')
    monkeypatch.setattr(helper, 'embed', fail)
    result = prepare(tmp_path, RING_OPENING, conformers=2)
    assert [row['status'] for row in result['candidates']] == ['failed', 'failed']
    assert all('synthetic embedding failure' in row['error'] for row in result['candidates'])
    assert (tmp_path/'result/candidates.json').is_file()


def test_generic_irc_preparer_runs_from_declared_staged_resources(tmp_path):
    from research_agent.application.executors import prepare as prepare_job
    from tests.unit.test_job_recovery import workspace
    from tests.unit.test_chemical_path_execution import run_job
    workspace(tmp_path)
    source = tmp_path/'spec.json'; source.write_text(json.dumps(RING_OPENING))
    checkpoint = tmp_path/'fixture.chk'; checkpoint.write_bytes(b'synthetic checkpoint')
    request = prepare_job(os.environ['CORAGENT_JOB_CONFIG'], 'local', 'chemical.path-irc', '1',
                          {'spec': source, 'checkpoint': checkpoint}, ['--max-points', '12'])
    request_file = tmp_path/'request.json'; request_file.write_text(json.dumps(request))
    collected = run_job(tmp_path, {'request_file':str(request_file),
                        'request_sha256':hashlib.sha256(request_file.read_bytes()).hexdigest()})
    assert collected['output_validation']['complete']
    forward = next(a for a in collected['artifacts'] if a['provenance']['source_path'].endswith('results/forward.gjf'))
    assert 'MaxPoints=12' in Path(forward['location']).read_text()
