"""Scientific invariants of bounded mapping, geometry comparison and tensor order."""
import json
import os
from pathlib import Path
import sys
import time

import pytest
np = pytest.importorskip('numpy')

SCRIPTS = Path(__file__).resolve().parents[2] / 'skills/chemical/material-preparation/scripts/materials'
from tests.unit.chemical_paths import configure
configure()
from material import build_material, graph_material
from analysis_material import make_order, read_material
from correspondence import mappings
from conformers import compare_conformers, internal_value
from tensor_order import reorder_tensors
from analysis import run
from analysis_cli import parse_arguments


def material(tmp_path, name, smiles, coords=None, **extra):
    request = {'schema_version': 'chemical-material-input/1', 'format': 'smiles', 'text': smiles, **extra}
    if coords is not None:
        _, _, atoms = graph_material(smiles)
        request.update(format='xyz', text=f'{len(atoms)}\nsynthetic geometry\n' + ''.join(
            a['element'] + ' ' + ' '.join(str(float(v)) for v in row) + '\n' for a, row in zip(atoms, coords)),
            graph={'smiles': smiles, 'source': 'user', 'note': 'Synthetic numerical fixture'}, graph_to_input=list(range(len(atoms))))
    value, _ = build_material(request, 'sha256:synthetic')
    path = tmp_path / (name + '.json')
    path.write_text(json.dumps(value))
    return read_material(path)


def test_mapping_preserves_symmetry_and_declared_constraints(tmp_path):
    a = material(tmp_path, 'a', 'O')
    b = material(tmp_path, 'b', 'O', new_to_old=[2, 0, 1])
    result = mappings(a, b, mode='identity')
    assert result['ambiguity'] == 'multiple' and result['best_count_observed'] == 2
    assert result['search_complete']
    fixed = mappings(a, b, mode='identity', fixed_pairs=[['atom_2', 'atom_2']])
    assert fixed['ambiguity'] == 'unique'
    candidate = fixed['candidates'][0]
    assert candidate['left_to_right'] == [1, 2, 0]
    assert candidate['right_order']['output_atom_ids'] == a['ids']
    limited = mappings(a, b, mode='identity', max_candidates=1)
    assert limited['candidate_limit_reached'] and limited['ambiguity'] == 'multiple'
    exhausted = mappings(a, b, max_search=1)
    assert exhausted['status'] == 'inconclusive' and not exhausted['search_complete']
    assert exhausted['ambiguity'] == 'unknown'


def test_reaction_mapping_handles_proton_transfer_without_da_assumptions(tmp_path):
    a = material(tmp_path, 'a', '[O:1]([H:3])[H:4].[NH3:2]')
    b = material(tmp_path, 'b', '[O-:1][H:4].[NH3+:2][H:3]')
    result = mappings(a, b)
    assert result['status'] == 'candidates' and result['best_cost'] == 2
    changes = result['candidates'][0]['bond_changes']
    assert len(changes) == 2
    assert {(c['before'], c['after']) for c in changes} == {(1., 0.), (0., 1.)}
    with pytest.raises(ValueError, match='conflicts'):
        mappings(a, b, fixed_pairs=[['atom_1', 'atom_3']])


@pytest.mark.parametrize('left,right', [('O', '[2H]O'), ('[NH4+]', 'N.[H]'), ('F[C@](Cl)(Br)I', 'F[C@@](Cl)(Br)I')])
def test_incompatible_composition_charge_or_stereochemistry(tmp_path, left, right):
    result = mappings(material(tmp_path, 'a', left), material(tmp_path, 'b', right), mode='identity')
    assert result['status'] == 'incompatible'


def test_missing_graph_is_unassessed_including_unresolved_name(tmp_path):
    value, _ = build_material({'schema_version': 'chemical-material-input/1', 'format': 'name', 'text': 'unknown'}, 'sha256:fixture')
    path = tmp_path / 'unknown.json'
    path.write_text(json.dumps(value))
    a = read_material(path)
    assert mappings(a, a)['status'] == 'not_assessed'


def test_isotopes_remove_false_symmetry_and_local_ids_are_not_maps(tmp_path):
    a = material(tmp_path, 'a', '[2H]O', atom_ids=['left-D', 'left-O', 'left-H'])
    b = material(tmp_path, 'b', '[2H]O', atom_ids=['right-D', 'right-O', 'right-H'], new_to_old=[2, 1, 0])
    result = mappings(a, b, mode='identity')
    assert result['ambiguity'] == 'unique'
    candidate = result['candidates'][0]
    assert candidate['left_to_right'] == [2, 1, 0]
    assert candidate['right_order']['output_atom_ids'] == ['right-D', 'right-O', 'right-H']
    assert candidate['pairs'][0] == ['left-D', 'right-D']


@pytest.mark.parametrize('option', [{'max_candidates': 0}, {'max_search': True}, {'max_search': 1000001}, {'fixed_pairs': [['missing', 'atom_1']]}])
def test_mapping_rejects_invalid_bounds_and_constraints(tmp_path, option):
    a = material(tmp_path, 'a', 'O')
    with pytest.raises(ValueError): mappings(a, a, **option)


TETRA = np.array([[1., 1., 1.], [0., 0., 0.], [-1., -1., 1.], [-1., 1., -1.], [1., -1., -1.]])


def test_proper_alignment_handles_rotation_translation_and_atom_order(tmp_path):
    rot = np.array([[0., -1., 0.], [1., 0., 0.], [0., 0., 1.]])
    a = material(tmp_path, 'a', 'FC(Cl)(Br)I', TETRA)
    b = material(tmp_path, 'b', 'FC(Cl)(Br)I', TETRA @ rot + [4., -2., 7.], new_to_old=[4, 2, 0, 3, 1])
    result = compare_conformers(a, b, internal_coordinates=[['atom_1', 'atom_2'], ['atom_1', 'atom_2', 'atom_3'], ['atom_1', 'atom_2', 'atom_3', 'atom_4']])
    assert result['geometry_status'] == 'match'
    assert result['best']['rmsd_angstrom'] < 1e-12
    assert result['best']['rotation_determinant'] == pytest.approx(1.)
    assert all(c['status'] == 'match' for c in result['best']['internal_coordinates'])
    assert result['state_comparison']['wavefunction_identity'] == 'not_assessed'


def test_reflection_is_not_a_rotation_even_when_graph_stereo_is_unspecified(tmp_path):
    a = material(tmp_path, 'a', 'FC(Cl)(Br)I', TETRA)
    b = material(tmp_path, 'b', 'FC(Cl)(Br)I', TETRA * [-1., 1., 1.])
    result = compare_conformers(a, b)
    assert result['geometry_status'] == 'different'
    assert result['best']['rotation_determinant'] == pytest.approx(1.)


def test_specified_chirality_survives_atom_permutations(tmp_path):
    a = material(tmp_path, 'a', 'F[C@](Cl)(Br)I', TETRA)
    b = material(tmp_path, 'b', 'F[C@](Cl)(Br)I', TETRA, new_to_old=[4, 3, 2, 1, 0])
    assert compare_conformers(a, b)['geometry_status'] == 'match'


def test_double_bond_stereochemistry_is_preserved_by_exact_correspondence(tmp_path):
    a = material(tmp_path, 'a', 'F/C=C/Cl')
    b = material(tmp_path, 'b', 'F/C=C/Cl', new_to_old=list(reversed(range(6))))
    c = material(tmp_path, 'c', 'F/C=C\\Cl')
    assert mappings(a, b, mode='identity')['status'] == 'candidates'
    assert mappings(a, c, mode='identity')['status'] == 'incompatible'


def test_internal_torsion_and_degenerate_coordinates_are_not_hidden_by_rmsd(tmp_path):
    a = material(tmp_path, 'a', 'FC(Cl)(Br)I', TETRA)
    altered = TETRA.copy(); altered[3] = [-1., -1., -1.]
    b = material(tmp_path, 'b', 'FC(Cl)(Br)I', altered)
    ids = [['atom_1', 'atom_2', 'atom_3', 'atom_4']]
    result = compare_conformers(a, b, rmsd_threshold=10., internal_coordinates=ids, angle_tolerance=1.)
    assert result['geometry_status'] == 'different'
    linear = material(tmp_path, 'linear', 'FC(Cl)(Br)I', [[i, 0, 0] for i in range(5)])
    assert compare_conformers(linear, linear, internal_coordinates=ids)['geometry_status'] == 'inconclusive'
    assert internal_value(np.array([[0, 0, 0], [0, 0, 0], [1, 0, 0]])) is None


def test_dihedral_wrap_uses_short_periodic_difference(tmp_path):
    points = np.array([[1., 0., 0.], [0., 0., 0.], [0., 0., 1.], [-1., .01, 1.], [2., 2., 2.]])
    other = points.copy(); other[3, 1] = -.01
    a = material(tmp_path, 'a', 'FC(Cl)(Br)I', points)
    b = material(tmp_path, 'b', 'FC(Cl)(Br)I', other)
    result = compare_conformers(a, b, internal_coordinates=[['atom_1', 'atom_2', 'atom_3', 'atom_4']])
    check = result['matching_candidate']['internal_coordinates'][0]
    assert abs(check['left'] - check['right']) > 350
    assert check['difference'] < 2 and check['status'] == 'match'


def test_complex_alignment_does_not_independently_move_fragments(tmp_path):
    coords = np.array([[0, 0, 0], [5, 0, 0], [0, 0, 1], [0, 1, 0], [5, 0, 1], [5, 1, 0]], dtype=float)
    changed = coords.copy(); changed[[1, 4, 5]] += [3, 0, 0]
    a = material(tmp_path, 'a', 'O.O', coords)
    b = material(tmp_path, 'b', 'O.O', changed)
    assert compare_conformers(a, b)['geometry_status'] == 'different'


def test_candidate_limit_prevents_false_negative_but_allows_a_witness(tmp_path):
    a = material(tmp_path, 'a', 'O', [[0, 0, 0], [0, 0, 1], [0, 2, 0]])
    b = material(tmp_path, 'b', 'O', [[0, 0, 0], [0, 0, 1], [0, 2, 0]], new_to_old=[0, 2, 1])
    limited = compare_conformers(a, b, max_candidates=1)
    assert limited['geometry_status'] == 'inconclusive'
    assert not limited['coverage_complete']
    assert compare_conformers(a, b)['geometry_status'] == 'match'
    assert compare_conformers(a, a, max_candidates=1)['geometry_status'] == 'match'


def test_electronic_state_conflicts_are_kept_separate_from_geometry(tmp_path):
    a = material(tmp_path, 'a', 'FC(Cl)(Br)I', TETRA, multiplicity=1, electronic_state={'kind': 'ground'})
    b = material(tmp_path, 'b', 'FC(Cl)(Br)I', TETRA, multiplicity=3, electronic_state={'kind': 'excited', 'root': 1, 'method': 'TDDFT'})
    result = compare_conformers(a, b)
    assert result['status'] == 'state_conflict' and result['geometry_status'] == 'match'
    assert 'multiplicity' in result['state_comparison']['conflicts']
    same_root = compare_conformers(b, b)
    assert same_root['state_comparison']['status'] == 'compatible_declarations'
    assert same_root['state_comparison']['wavefunction_identity'] == 'not_assessed'


def tensors():
    rng = np.random.default_rng(41)
    matrix = rng.normal(size=(9, 9))
    return {'schema_version': 'chemical-tensors/1', 'atom_ids': ['O', 'H1', 'H2'],
            'axis_order': 'atom-major-xyz', 'representation': 'cartesian',
            'units': {'coordinates': 'angstrom', 'gradient': 'hartree/bohr', 'hessian': 'hartree/bohr^2', 'modes': 'dimensionless'},
            'coordinates': rng.normal(size=(3, 3)).tolist(), 'gradient': rng.normal(size=(3, 3)).tolist(),
            'hessian': (matrix.T @ matrix).tolist(), 'modes': rng.normal(size=(2, 3, 3)).tolist(),
            'masses': [16., 1., 2.], 'elements': ['O', 'H', 'H'], 'frequencies_cm-1': [-100., 250.]}


def test_tensor_permutation_preserves_spectrum_quadratic_form_and_mode_axes():
    before = tensors(); order = make_order(before['atom_ids'], [2, 0, 1])
    after = reorder_tensors(before, order)
    inverse = make_order(after['atom_ids'], order['old_to_new'])
    restored = reorder_tensors(after, inverse)
    for key in before:
        assert restored[key] == before[key]
    h, hp = np.array(before['hessian']), np.array(after['hessian'])
    assert np.allclose(np.linalg.eigvalsh(h), np.linalg.eigvalsh(hp))
    dx = np.arange(9).reshape(3, 3) / 10.
    px = dx[[2, 0, 1]].flatten(); x = dx.flatten()
    assert x @ h @ x == pytest.approx(px @ hp @ px)
    assert np.array(before['gradient']).flatten() @ x == pytest.approx(np.array(after['gradient']).flatten() @ px)
    assert np.allclose(np.array(after['modes'])[:, 0], np.array(before['modes'])[:, 2])
    assert after['frequencies_cm-1'] == before['frequencies_cm-1']


@pytest.mark.parametrize('mutation', ['ids', 'shape', 'bool', 'nonfinite', 'asymmetric', 'units', 'representation', 'inverse', 'masses', 'frequencies'])
def test_invalid_tensor_contract_rejected(mutation):
    value = tensors(); order = make_order(value['atom_ids'], [2, 0, 1])
    if mutation == 'ids': value['atom_ids'] = ['H1', 'O', 'H2']
    if mutation == 'shape': value['gradient'] = [[1, 2, 3]]
    if mutation == 'bool': value['gradient'][0][0] = True
    if mutation == 'nonfinite': value['modes'][0][0][0] = float('nan')
    if mutation == 'asymmetric': value['hessian'][0][4] += 1
    if mutation == 'units': del value['units']['hessian']
    if mutation == 'representation': value['representation'] = 'mass-weighted'
    if mutation == 'inverse': order['old_to_new'] = [0, 1, 2]
    if mutation == 'masses': value['masses'][0] = 0
    if mutation == 'frequencies': value['frequencies_cm-1'] = [1]
    with pytest.raises(ValueError): reorder_tensors(value, order)


def test_cli_does_not_overwrite_input_or_create_invalid_result(tmp_path):
    value = tensors(); source = tmp_path / 'tensors.json'; source.write_text(json.dumps(value))
    order = tmp_path / 'order.json'; order.write_text(json.dumps(make_order(value['atom_ids'], [2, 0, 1])))
    with pytest.raises(FileExistsError):
        run(parse_arguments(['--output', str(source), 'reorder', '--tensors', str(source), '--order', str(order)]))
    assert json.loads(source.read_text()) == value
    value['gradient'][0][0] = True; source.write_text(json.dumps(value))
    output = tmp_path / 'new' / 'result.json'
    with pytest.raises(ValueError):
        run(parse_arguments(['--output', str(output), 'reorder', '--tensors', str(source), '--order', str(order)]))
    assert not output.exists()


@pytest.mark.parametrize('executor,expected', [('chemical.map-candidates', 'chemical-correspondence/1'),
                                             ('chemical.conformer-compare', 'chemical-conformer-comparison/1'),
                                             ('chemical.reorder-tensors', 'chemical-tensors/1')])
def test_analysis_jobs_execute_staged_dependencies_and_collect(tmp_path, executor, expected):
    from research_agent.application.api import execute
    from research_agent.application.executors import prepare
    from tests.unit.test_job_recovery import workspace
    root = tmp_path / 'workspace'; workspace(root)
    node = execute('research_create', root, {'goal': 'Independent deterministic structure analysis'})['node']
    if executor == 'chemical.reorder-tensors':
        value = tensors()
        inputs = {'tensors': root / 'tensors.json', 'order': root / 'order.json'}
        inputs['tensors'].write_text(json.dumps(value))
        inputs['order'].write_text(json.dumps(make_order(value['atom_ids'], [2, 0, 1])))
    else:
        material(root, 'left', 'O', [[0, 0, 0], [0, 0, 1], [0, 1, 0]])
        material(root, 'right', 'O', [[0, 0, 0], [0, 0, 1], [0, 1, 0]], new_to_old=[2, 0, 1])
        inputs = {'left': root / 'left.json', 'right': root / 'right.json'}
    arguments = ['--mode', 'identity', '--max-candidates', '1'] if executor == 'chemical.map-candidates' else ['--rmsd-threshold', '0.05'] if executor == 'chemical.conformer-compare' else []
    prepared = prepare(Path(os.environ['CORAGENT_JOB_CONFIG']), 'local', executor, '1', inputs, arguments)
    job = execute('job_start', root, {**prepared, 'node_id': node['id']})
    try:
        for _ in range(300):
            status = execute('job_status', root, {'job_id': job['job_id']})
            if status['state'] in {'succeeded', 'failed'}: break
            time.sleep(.01)
        assert status['state'] == 'succeeded'
        collected = execute('job_collect', root, {'job_id': job['job_id']})
        assert collected['output_validation']['complete']
        result = json.loads((Path(job['cwd']) / 'results/result.json').read_text())
        assert result['schema_version'] == expected
    finally:
        execute('job_cancel', root, {'job_id': job['job_id']})
