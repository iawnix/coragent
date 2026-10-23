"""Deterministic ensemble contracts; fake native output is not a chemistry benchmark."""
import copy
import json
import os
from pathlib import Path
import re
import sys
import time
import tomllib

import pytest
np = pytest.importorskip('numpy')

SKILLS = Path(__file__).resolve().parents[2] / 'skills/chemical'
from tests.unit.chemical_paths import configure
configure()
import ensemble
from analysis_material import read_material
from complex_sample import combine, sample_complex
from crest_cli import parse_arguments
from crest_io import HARTREE_TO_KCAL, frames, parse_primary
from crest_run import input_geometry, run
from ensemble_material import checked, derive_material, identity_check, import_crest, xyz_text
from ensemble_select import select_ensemble
from material import build_material


def water(shift=0., graph=True):
    coords = np.array([[0., 0., 0.], [.958, 0., 0.], [-.24, .927, 0.]]) + shift
    spec = {'schema_version': 'chemical-material-input/1', 'format': 'xyz',
            'text': xyz_text([{'element': e} for e in ('O', 'H', 'H')], coords),
            'charge': 0, 'multiplicity': 1, 'electronic_state': {'kind': 'ground'}, 'fragments': [[0, 1, 2]]}
    if graph: spec.update(graph={'smiles': '[O]([H])[H]', 'source': 'user', 'note': 'fixture'}, graph_to_input=[0, 1, 2])
    return checked(build_material(spec, 'sha256:' + 'a'*64)[0])


def frame(m, energy=-5.):
    return xyz_text(m['atoms'], m['coordinates'], str(energy))


def primary(tmp_path, m=None):
    m = m or water()
    texts = {'crest.out': 'Version 3.0.2\nCREST terminated normally.\n',
             'crest_conformers.xyz': frame(m) + frame(m, -4.99), 'crest_best.xyz': frame(m),
             'crest.energies': f'1 0.000\n2 {.01*HARTREE_TO_KCAL:.3f}\n'}
    for name, text in texts.items(): (tmp_path / name).write_text(text)
    return texts


def collection(m=None, energies=(-5., -4.99)):
    m = m or water()
    model = {'method': 'gfn2', 'charge': 0, 'multiplicity': 1, 'solvent': None,
             'solvent_model': 'gas', 'constraints': [], 'quantity': 'electronic_energy'}
    return {'schema_version': 'chemical-ensemble/1', 'reference_material': m['value'], 'complete': True,
            'members': [{'id': str(i), 'material': copy.deepcopy(m['value']),
                         'energy': None if e is None else {'value': e, 'unit': 'hartree', 'model': copy.deepcopy(model)}}
                        for i, e in enumerate(energies)]}


def test_primary_units_and_best_binding(tmp_path):
    primary(tmp_path)
    result = parse_primary(tmp_path, ['O', 'H', 'H'])
    assert result['complete'] and result['best_member_indexes'] == [1]
    assert result['members'][1]['relative_energy_kcal_mol'] == 6.275


@pytest.mark.parametrize('mutation', ['energy_unit', 'count', 'index', 'nan', 'order', 'best', 'version', 'termination', 'truncated', 'limit'])
def test_primary_inconsistency_never_completes(tmp_path, mutation):
    texts = primary(tmp_path)
    if mutation == 'energy_unit': texts['crest.energies'] = '1 -5\n2 -4.99\n'
    if mutation == 'count': texts['crest.energies'] = '1 0\n'
    if mutation == 'index': texts['crest.energies'] = '1 0\n3 6.275\n'
    if mutation == 'nan': texts['crest_conformers.xyz'] += '1\nnan\nH 0 0 0\n'
    if mutation == 'order': texts['crest_conformers.xyz'] = texts['crest_conformers.xyz'].replace('O ', 'N ')
    if mutation == 'best': texts['crest_best.xyz'] = frame(water(1))
    if mutation == 'version': texts['crest.out'] = texts['crest.out'].replace('3.0.2', '3.0.1')
    if mutation == 'termination': texts['crest.out'] = 'Version 3.0.2\n'
    if mutation == 'truncated': texts['crest_conformers.xyz'] += '3\n-4.0\nO 0 0 0\n'
    for name, text in texts.items(): (tmp_path / name).write_text(text)
    result = parse_primary(tmp_path, ['O', 'H', 'H'], 1 if mutation == 'limit' else 256)
    assert not result['complete'] and result['issues']
    assert len(result['members']) == (1 if mutation == 'limit' else 2)


def test_identity_and_selection_preserve_uncertainty():
    m = water(); assert identity_check(m)['status'] == 'match'
    c = collection(); result = select_ensemble(c)
    assert [d['decision'] for d in result['decisions']] == ['selected', 'outside_energy_window']
    c = collection(energies=(-5., -4.999)); result = select_ensemble(c)
    assert result['decisions'][1]['decision'] == 'duplicate'
    c['members'][0]['material'] = derive_material(m, m['coordinates'] * 4, {'operation': 'fixture'})
    damaged = select_ensemble(c)['decisions'][0]
    assert damaged['identity']['status'] != 'match' and damaged['relative_kcal_mol'] is None
    c = collection(water(graph=False))
    result = select_ensemble(c)
    assert len(result['selected_ids']) == 2 and result['energy_ranking'].startswith('unranked')
    assert all(d['needs_identity_review'] for d in result['decisions'])


@pytest.mark.parametrize('change', ['method', 'solvent', 'missing', 'unknown_spin'])
def test_incomparable_or_missing_energies_are_not_window_filtered(change):
    c = collection()
    if change == 'method': c['members'][1]['energy']['model']['method'] = 'gfn1'
    if change == 'solvent': c['members'][1]['energy']['model'].update(solvent='water', solvent_model='ALPB')
    if change == 'missing': c['members'][1]['energy'] = None
    if change == 'unknown_spin':
        for m in [c['reference_material'], *[r['material'] for r in c['members']]]: m['multiplicity'] = None
        for r in c['members']: r['energy']['model']['multiplicity'] = None
    result = select_ensemble(c)
    assert not any(d['decision'] == 'outside_energy_window' for d in result['decisions'])
    assert result['decisions'][1]['relative_kcal_mol'] is None


def test_selection_and_pair_budgets_are_distinct():
    c = collection(water(graph=False), energies=(None, None, None))
    result = select_ensemble(c, max_selected=1)
    assert result['selection_limit_reached'] and not result['comparison_budget_exhausted']
    result = select_ensemble(c, max_pairs=1)
    assert result['comparison_budget_exhausted'] and len(result['selected_ids']) == 3
    for kw in ({'max_search': 0}, {'max_candidates': True}):
        with pytest.raises(ValueError): select_ensemble(c, **kw)


def spec():
    return {'schema_version': 'chemical-complex-input/1', 'materials': [water()['value'], water(5)['value']]}


def test_rigid_sampling_reproducible_geometry_lineage_and_unknown_spin():
    s = spec(); original = copy.deepcopy(s)
    result = sample_complex(s, samples=4, seed=42)
    assert result == sample_complex(s, samples=4, seed=42) and s == original and result['complete']
    ref = checked(result['reference_material'])
    assert ref['value']['multiplicity'] is None and ref['value']['electronic_state']['kind'] == 'unspecified'
    assert ref['mol'] is not None and len(result['atom_lineage']) == 6
    for member in result['members']:
        m = checked(member['material'])
        assert np.allclose(m['coordinates'][:3], ref['coordinates'][:3])
        assert np.allclose(np.linalg.norm(m['coordinates'][3:, None] - m['coordinates'][None, 3:], axis=2),
                           np.linalg.norm(ref['coordinates'][3:, None] - ref['coordinates'][None, 3:], axis=2))
        assert np.linalg.det(member['material']['derivation']['transformations'][0]['rotation']) == pytest.approx(1.)
        assert member['energy'] is None


def test_perturb_preserves_supplied_complex_and_rejects_impossible_constraints():
    s = spec(); ref, _ = combine(s)
    one = {'schema_version': 'chemical-complex-input/1', 'materials': [ref['value']]}
    result = sample_complex(one, mode='perturb', samples=2)
    assert checked(result['members'][0]['material'])['coordinates'].tolist() == ref['coordinates'].tolist()
    one['distance_constraints'] = [{'atoms': [ref['ids'][0], ref['ids'][3]], 'minimum': 100., 'maximum': 101.}]
    result = sample_complex(one, samples=2, max_attempts=3)
    assert not result['complete'] and not result['members'] and result['sampling']['attempted'] == 3
    one['fixed_fragments'] = [0, 1]
    with pytest.raises(ValueError, match='mobile'): sample_complex(one)


def fake_crest(path, mode='success'):
    texts = {'crest_conformers.xyz': frame(water()), 'crest_best.xyz': frame(water()), 'crest.energies': '1 0.000\n'}
    path.write_text(f'''#!{sys.executable}
import json, os, subprocess, sys, time
from pathlib import Path
if '--version' in sys.argv:
    print('Version {"9.0.0" if mode == "version" else "3.0.2"}'); sys.exit(0)
Path('args.json').write_text(json.dumps(sys.argv[1:]))
for name, text in {texts!r}.items(): Path(name).write_text(text)
print('Version 3.0.2', flush=True)
if {mode!r} == 'timeout':
    child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])
    Path('child.pid').write_text(str(child.pid))
    time.sleep(60)
print('CREST terminated normally.', flush=True)
sys.exit({7 if mode == 'nonzero' else 0})
''')
    path.chmod(0o755); return path


@pytest.mark.parametrize('mode', ['success', 'timeout', 'nonzero', 'version'])
def test_native_runner_retains_receipt_and_kills_descendants(tmp_path, mode):
    source = tmp_path / 'material.json'; source.write_text(json.dumps(water()['value']))
    out = tmp_path / 'out'; fake = fake_crest(tmp_path / 'crest', mode)
    args = parse_arguments(['--material', str(source), '--output-dir', str(out), '--executable', str(fake),
                            '--timeout', '.5', '--search-level', 'quick', '--solvent', 'water'])
    result = run(args)
    assert result['status'] == ('completed' if mode == 'success' else 'failed')
    assert json.loads((out / 'result.json').read_text()) == result
    if mode != 'version':
        command = json.loads((out / 'args.json').read_text())
        assert '--quick' in command and command[-2:] == ['--alpb', 'water']
    if mode == 'timeout':
        from tests.support.processes import assert_stopped
        assert_stopped(int((out / 'child.pid').read_text()))
        assert result['primary']['members'] and not result['primary']['complete']
    imported = import_crest(read_material(source), result, 'sha256:'+'b'*64)
    assert imported['complete'] == (mode == 'success')


@pytest.mark.parametrize('change', ['charge', 'excited', 'isotope'])
def test_runner_rejects_unsupported_state_before_execution(change):
    m = water()['value']
    if change == 'charge': m['charge'] = None
    if change == 'excited': m['electronic_state']['kind'] = 'excited'
    if change == 'isotope': m['atoms'][0]['isotope'] = 18
    with pytest.raises(ValueError): input_geometry(json.dumps(m))


def test_registered_pipeline_stages_collects_and_exports_refinement(tmp_path, monkeypatch):
    from research_agent.application.api import execute
    from research_agent.application.executors import prepare
    from tests.unit.test_job_recovery import workspace
    root = tmp_path / 'workspace'; workspace(root)
    config = Path(os.environ['CORAGENT_JOB_CONFIG'])
    text = config.read_text(); data = tomllib.loads(text)
    # Extend only this test's native binding; all environments stay runner-managed.
    native = fake_crest(tmp_path / 'crest')
    binding = data['execution']['platforms']['local']['bindings']['structure']['python']
    text = re.sub(r'(?ms)^\[execution\.platforms\.local\.bindings\.crest\]\n.*?(?=^\[|\Z)', '', text)
    text += '\n[execution.platforms.local.bindings.crest]\ncommand = '+json.dumps(str(native))+'\n'
    text += '[execution.platforms.local.bindings.crest.python]\n' + ''.join(k+' = '+json.dumps(v)+'\n' for k,v in binding.items())
    text = text.replace('command = \"xtb\"', 'command = '+json.dumps(str(native)))
    text += '[execution.platforms.local.bindings.xtb.python]\n' + ''.join(k+' = '+json.dumps(v)+'\n' for k,v in binding.items())
    config = tmp_path / 'job.toml'; config.write_text(text); monkeypatch.setenv('CORAGENT_JOB_CONFIG', str(config))
    node = execute('research_create', root, {'goal': 'Independent conformer and complex preparation'})['node']
    source = root / 'material.json'; source.write_text(json.dumps(water()['value']))
    def job(executor, inputs, args=()):
        prepared = prepare(config, {'platform': 'local', 'scheduler_entry': 'main'}, executor, '1', inputs, list(args))
        receipt = execute('job_start', root, {**prepared, 'node_id': node['id']})
        try:
            for _ in range(500):
                status = execute('job_status', root, {'job_id': receipt['job_id']})
                if status['state'] in {'succeeded', 'failed'}: break
                time.sleep(.01)
            assert status['state'] == 'succeeded'
            assert execute('job_collect', root, {'job_id': receipt['job_id']})['output_validation']['complete']
            return Path(receipt['cwd']) / 'results'
        finally: execute('job_cancel', root, {'job_id': receipt['job_id']})
    native_out = job('chemical.crest', {'material': source}, ['--timeout', '2'])
    imported = job('chemical.crest-ensemble', {'material': source, 'run': native_out / 'result.json'})
    selected = job('chemical.ensemble-select', {'ensemble': imported / 'result.json'})
    refined = json.loads((selected / 'refinement.json').read_text())['members'][0]
    assert (selected / refined['geometry']).is_file() and refined['multiplicity'] == 1
    # Existing SP/optimization preparation consumes exported XYZ independently.
    for task in ('sp', 'opt'):
        request = prepare(config, {'platform': 'local', 'scheduler_entry': 'main'}, 'chemical.xtb', '1', {'geometry': selected / refined['geometry']}, ['--task', task])
        assert request['command']
    sampling = root / 'sampling.json'; sampling.write_text(json.dumps(spec()))
    sampled = job('chemical.complex-sample', {'input': sampling}, ['--mode', 'assemble', '--samples', '2'])
    assert len(json.loads((sampled / 'refinement.json').read_text())['members']) == 2


def test_mirror_geometry_is_never_merged():
    from rdkit import Chem
    from rdkit.Chem import AllChem
    mol = Chem.AddHs(Chem.MolFromSmiles('FC(Cl)(Br)I'))
    assert AllChem.EmbedMolecule(mol, randomSeed=42) == 0
    coords = mol.GetConformer().GetPositions()
    spec = {'schema_version': 'chemical-material-input/1', 'format': 'xyz',
            'text': xyz_text([{'element': a.GetSymbol()} for a in mol.GetAtoms()], coords),
            'graph': {'smiles': 'FC(Cl)(Br)I', 'source': 'user', 'note': 'Unspecified stereo'},
            'graph_to_input': list(range(len(coords))), 'charge': 0, 'multiplicity': 1, 'electronic_state': {'kind': 'ground'}}
    m = checked(build_material(spec, 'sha256:'+'a'*64)[0])
    c = collection(m, energies=(None, None))
    mirror = coords.copy(); mirror[:, 0] *= -1
    c['members'][1]['material'] = derive_material(m, mirror, {'operation': 'reflection_fixture'})
    result = select_ensemble(c)
    assert len(result['selected_ids']) == 2
    assert result['comparisons'][0]['geometry_status'] == 'different'


def test_derived_material_retains_permuted_graph_and_isotopes():
    spec = {'schema_version': 'chemical-material-input/1', 'format': 'xyz',
            'text': '3\nfixture\nO 0 0 0\nH .958 0 0\nH -.24 .927 0\n',
            'graph': {'smiles': '[18O]([H])[H]', 'source': 'user', 'note': 'fixture'},
            'graph_to_input': [0, 1, 2], 'new_to_old': [2, 0, 1],
            'charge': 0, 'multiplicity': 1, 'electronic_state': {'kind': 'ground'}}
    m = checked(build_material(spec, 'sha256:'+'a'*64)[0])
    derived = checked(derive_material(m, m['coordinates'] + 1, {'operation': 'test_translation'}))
    assert derived['ids'] == m['ids'] and derived['atoms'][1]['isotope'] == 18
    assert identity_check(derived)['status'] == 'match'


def test_interspecies_energy_is_excluded_even_when_more_negative():
    from rdkit import Chem
    from rdkit.Chem import AllChem
    mol = Chem.AddHs(Chem.MolFromSmiles('N')); AllChem.EmbedMolecule(mol, randomSeed=4)
    s = {'schema_version': 'chemical-material-input/1', 'format': 'xyz', 'text': Chem.MolToXYZBlock(mol),
         'graph': {'smiles': 'N', 'source': 'user', 'note': 'fixture'}, 'graph_to_input': list(range(4)),
         'charge': 0, 'multiplicity': 1, 'electronic_state': {'kind': 'ground'}}
    c = collection(); c['members'][1]['material'] = build_material(s, 'sha256:'+'a'*64)[0]
    c['members'][1]['energy']['value'] = -100.
    result = select_ensemble(c)
    assert result['decisions'][0]['decision'] == 'selected'
    assert result['decisions'][1]['decision'] == 'excluded'
    assert result['decisions'][0]['relative_kcal_mol'] == 0.


def test_collision_rejection_and_partial_export(tmp_path):
    s = spec()
    sampled = sample_complex(s, samples=2, max_attempts=3, min_separation=.01, max_separation=.02)
    assert sampled['sampling']['rejected']['collision'] == 3 and not sampled['members']
    primary(tmp_path); (tmp_path / 'crest_conformers.xyz').write_text(frame(water()) + '3\n-4\nO 0 0 0\n')
    p = parse_primary(tmp_path, ['O', 'H', 'H'])
    assert not p['complete'] and len(p['members']) == 1
    source = tmp_path / 'material.json'; source.write_text(json.dumps(water()['value']))
    m = read_material(source)
    packet = {'schema_version': 'chemical-crest-run/1', 'material_sha256': m['sha256'], 'primary': p,
              'status': 'failed', 'settings': {'method': 'gfn2', 'charge': 0, 'multiplicity': 1,
                                           'solvent': None, 'solvent_model': 'gas', 'constraints': []}}
    run_path = tmp_path / 'run.json'; run_path.write_text(json.dumps(packet))
    from ensemble_cli import parse_arguments as parse_ensemble
    result = ensemble.run(parse_ensemble(['--output-dir', str(tmp_path / 'export'), 'import', '--material', str(source), '--run', str(run_path)]))
    assert not result['complete'] and len(result['exports']) == 1
    assert (tmp_path / 'export/members/0001/geometry.xyz').is_file()
    packet['material_sha256'] = 'sha256:'+'0'*64
    with pytest.raises(ValueError, match='exact'): import_crest(m, packet, 'sha256:'+'b'*64)


@pytest.mark.parametrize('field,value', [('constraints', None), ('solvent_model', None), ('method', ['gfn2']), ('solvent', 'water')])
def test_incomplete_energy_model_cannot_enable_ranking(field, value):
    c = collection()
    for member in c['members']: member['energy']['model'][field] = value
    with pytest.raises(ValueError): select_ensemble(c)
