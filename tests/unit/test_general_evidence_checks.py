"""Deterministic evidence and geometry tests, not physical transition-state benchmarks."""
import copy
import json
import os
from pathlib import Path
import sys
import time

import pytest
np = pytest.importorskip('numpy')

SKILLS = Path(__file__).resolve().parents[2] / 'skills/chemical'
from tests.unit.chemical_paths import configure
configure()
import evidence_check
from analysis_material import read_material, validate_material
from check_common import content_digest, stationary
from gaussian_evidence import gaussian_evidence
from irc_check import irc_check
from mode_check import mode_check
from material import build_material


XYZ = np.array([[0., 0., 0.], [2., 0., 0.], [4., 0., 0.]])


def material(coords=XYZ, graph=None, multiplicity=2, electronic_state=None):
    spec = {'schema_version': 'chemical-material-input/1', 'format': 'xyz', 'text': f'{len(coords)}\nSynthetic test\n' + ''.join(
        'H ' + ' '.join(str(float(x)) for x in row) + '\n' for row in coords), 'charge': 0,
        'multiplicity': multiplicity, 'electronic_state': electronic_state or {'kind': 'ground'}}
    if graph:
        spec.update(graph={'smiles': graph, 'source': 'user', 'note': 'Synthetic mapped graph'}, graph_to_input=list(range(len(coords))))
    value, _ = build_material(spec, 'sha256:' + 'a' * 64)
    return validate_material(value, content_digest(value))


def evidence(m, minimum=False):
    xyz = m['coordinates']; n = len(xyz)
    linear = np.linalg.matrix_rank(xyz - xyz.mean(axis=0)) < 2
    dof = max(0, 3 * n - (5 if linear else 6))
    frequencies = [float(100 + i * 50) for i in range(dof)]
    if frequencies and not minimum: frequencies[0] = -400.
    modes = np.zeros((dof, n, 3))
    if dof: modes[0, 1, 0] = 1.
    return {'schema_version': 'chemical-stationary-evidence/1', 'material_sha256': m['sha256'], 'atom_ids': m['ids'],
            'calculation': {'method': 'hf', 'basis': 'sto-3g', 'charge': 0, 'multiplicity': m['value']['multiplicity'],
                            'electronic_state': {'kind': 'ground'}, 'constraints': [], 'surface': 'single_surface'},
            'sources': [{'kind': 'synthetic_fixture', 'sha256': 'sha256:' + 'b' * 64}],
            'coordinates': xyz.tolist(), 'coordinate_unit': 'angstrom', 'termination': 'normal',
            'optimization': {'converged': True, 'criteria': [
                {'name': 'max_gradient', 'value': .00001, 'threshold': .00045, 'unit': 'hartree/bohr'},
                {'name': 'rms_gradient', 'value': .00001, 'threshold': .0003, 'unit': 'hartree/bohr'}]},
            'frequencies_cm-1': frequencies, 'mode_representation': 'cartesian', 'normal_modes': modes.tolist()}


def coordinates():
    return {'schema_version': 'chemical-mode-coordinates/1', 'coordinates': [
        {'name': 'cleavage', 'direction': 1, 'terms': [{'atoms': ['atom_1', 'atom_2']}]},
        {'name': 'formation', 'direction': -1, 'terms': [{'atoms': ['atom_2', 'atom_3']}]}]}


def path(m, endpoint, direction):
    e = evidence(m)
    return {'schema_version': 'chemical-irc-evidence/1', 'material_sha256': m['sha256'], 'atom_ids': m['ids'],
            'calculation': e['calculation'], 'sources': e['sources'], 'coordinate_unit': 'angstrom',
            'termination': 'normal', 'direction': direction, 'complete': True, 'max_points_reached': False,
            'origin_coordinates': m['coordinates'].tolist(),
            'points': [{'index': 1, 'energy_hartree': -1.0, 'coordinates': ((m['coordinates'] + endpoint['coordinates']) / 2).tolist()},
                       {'index': 2, 'energy_hartree': -1.1, 'coordinates': endpoint['coordinates'].tolist()}],
            'endpoint': {'material': endpoint['value'], 'minimum_evidence': evidence(endpoint, minimum=True)}}


def study():
    saddle = material()
    reactant = material([[0, 0, 0], [.74, 0, 0], [4, 0, 0]], '[H:1][H:2].[H:3]')
    product = material([[0, 0, 0], [3.26, 0, 0], [4, 0, 0]], '[H:1].[H:2][H:3]')
    return saddle, evidence(saddle), [path(saddle, product, 'forward'), path(saddle, reactant, 'reverse')], [reactant, product]


def test_linear_and_nonlinear_freedom_counts_are_geometry_dependent():
    m = material(); e = evidence(m)
    assert stationary(m, e)['verdict'] == 'pass'
    assert stationary(m, e)['checks']['vibrational_degrees']['details']['expected'] == 4
    bent = material([[0, 0, 0], [1, 1, 0], [2, 0, 0]])
    result = stationary(bent, evidence(bent))
    assert result['verdict'] == 'pass' and result['checks']['vibrational_degrees']['details']['expected'] == 3
    e['frequencies_cm-1'] = e['frequencies_cm-1'][:3]; e['normal_modes'] = e['normal_modes'][:3]
    assert stationary(m, e)['verdict'] == 'fail'


@pytest.mark.parametrize('mutation', ['missing_mode', 'multiple_negative', 'small_negative', 'flat', 'termination', 'convergence', 'lying_flag', 'binding', 'geometry', 'state', 'unknown_state', 'mass_weighted'])
def test_incomplete_or_conflicting_stationary_evidence_never_passes(mutation):
    m = material(); e = evidence(m)
    if mutation == 'missing_mode': e['normal_modes'] = None
    if mutation == 'multiple_negative': e['frequencies_cm-1'][1] = -100.
    if mutation == 'small_negative': e['frequencies_cm-1'][1] = -5.
    if mutation == 'flat': e['frequencies_cm-1'][1] = 0.
    if mutation == 'termination': e['termination'] = 'error'
    if mutation == 'convergence': e['optimization']['criteria'] = []
    if mutation == 'lying_flag': e['optimization']['criteria'][0]['value'] = 1.
    if mutation == 'binding': e['material_sha256'] = 'sha256:' + 'c' * 64
    if mutation == 'geometry': e['coordinates'][1][0] += .1
    if mutation == 'state': e['calculation']['multiplicity'] = 4
    if mutation == 'unknown_state': e['calculation']['multiplicity'] = None
    if mutation == 'mass_weighted': e['mode_representation'] = 'mass-weighted'
    assert stationary(m, e)['verdict'] != 'pass'


@pytest.mark.parametrize('field,value', [('constraints', ['frozen bond']), ('constraints', None), ('surface', 'crossing'), ('surface', 'barrierless'), ('electronic_state', {'kind': 'excited'})])
def test_outside_classical_scope_is_not_chemical_failure(field, value):
    m = material(); e = evidence(m); e['calculation'][field] = value
    result = stationary(m, e)
    assert result['verdict'] == 'inconclusive' and result['scientific_verdict'] == 'not_assessed'


def test_near_linear_geometry_does_not_force_a_mode_count():
    m = material([[0, 0, 0], [2, .00001, 0], [4, 0, 0]])
    result = stationary(m, evidence(m))
    assert result['checks']['vibrational_degrees']['verdict'] == 'inconclusive'
    assert result['checks']['vibrational_degrees']['details']['geometry_class'] == 'near_linear'


def test_diatomic_and_atomic_minima_use_one_and_zero_vibrations():
    pair = material([[0, 0, 0], [.74, 0, 0]], multiplicity=1)
    assert stationary(pair, evidence(pair, minimum=True), kind='minimum')['verdict'] == 'pass'
    atom = material([[0, 0, 0]])
    single = evidence(atom, minimum=True)
    assert stationary(atom, single, kind='minimum')['verdict'] == 'pass'
    assert stationary(atom, single, kind='saddle')['verdict'] != 'pass'


@pytest.mark.parametrize('mutation', ['bool_frequency', 'nan_mode', 'bad_units', 'bool_converged', 'negative_threshold'])
def test_malformed_stationary_numbers_are_rejected(mutation):
    m = material(); e = evidence(m); args = {}
    if mutation == 'bool_frequency': e['frequencies_cm-1'][0] = True
    if mutation == 'nan_mode': e['normal_modes'][0][0][0] = float('nan')
    if mutation == 'bad_units': e['optimization']['criteria'][0]['unit'] = 'eV/angstrom'
    if mutation == 'bool_converged': e['optimization']['converged'] = 'true'
    if mutation == 'negative_threshold': args['negative_threshold'] = -1
    with pytest.raises(ValueError): stationary(m, e, **args)


def test_proton_transfer_mode_sign_and_scale_do_not_change_conclusion():
    m = material(); e = evidence(m); spec = coordinates()
    original = mode_check(m, e, spec)
    assert original['verdict'] == 'pass'
    e['normal_modes'] = (-7 * np.array(e['normal_modes'])).tolist()
    reversed_ = mode_check(m, e, spec)
    assert reversed_['verdict'] == 'pass'
    assert original['checks']['mode_character']['details']['common_sign'] == -reversed_['checks']['mode_character']['details']['common_sign']
    assert np.allclose(original['displaced_geometries']['plus'], reversed_['displaced_geometries']['minus'])


def test_irrelevant_mode_or_incoherent_directions_does_not_pass():
    m = material(); e = evidence(m); spec = coordinates()
    e['normal_modes'][0][1] = [0., 1., 0.]
    assert mode_check(m, e, spec)['verdict'] == 'fail'
    e = evidence(m); spec['coordinates'][1]['direction'] = 1
    assert mode_check(m, e, spec)['verdict'] == 'fail'


def test_combination_coordinate_reports_projections_without_equal_amplitude_requirement():
    m = material(); e = evidence(m)
    spec = {'schema_version': 'chemical-mode-coordinates/1', 'coordinates': [
        {'name': 'transfer', 'direction': 1, 'terms': [{'atoms': ['atom_1', 'atom_2'], 'weight': 2., 'scale': 1.},
                                                     {'atoms': ['atom_2', 'atom_3'], 'weight': -1., 'scale': .5}]}]}
    result = mode_check(m, e, spec)
    row = result['checks']['mode_character']['details']['coordinates'][0]
    assert result['verdict'] == 'pass' and row['response_per_angstrom'] == pytest.approx(4.)
    assert 0 < row['projection_cosine'] <= 1


def test_angle_and_torsion_mode_coordinates_and_degenerate_torsion():
    xyz = np.array([[1., 0., 0.], [0., 0., 0.], [0., 0., 1.], [1., 1., 1.]])
    m = material(xyz, multiplicity=1); e = evidence(m)
    e['normal_modes'][0] = [[0, .4, 0], [0, 0, 0], [0, 0, 0], [0, 1.2, .5]]
    spec = {'schema_version': 'chemical-mode-coordinates/1', 'coordinates': [
        {'name': 'torsion', 'direction': 1, 'terms': [{'atoms': m['ids'], 'scale': 180.}], 'minimum_response': .001, 'minimum_projection': .001}]}
    result = mode_check(m, e, spec)
    assert result['verdict'] == 'pass'
    spec['coordinates'][0]['terms'][0]['atoms'] = ['atom_2', 'atom_3', 'atom_4']
    assert mode_check(m, e, spec)['verdict'] == 'pass'
    linear = material([[0, 0, 0], [1, 0, 0], [2, 0, 0], [3, 0, 0]], multiplicity=1)
    spec['coordinates'][0]['terms'][0]['atoms'] = linear['ids']
    assert mode_check(linear, evidence(linear), spec)['verdict'] == 'inconclusive'


def test_irc_accepts_direction_swap_and_records_actual_assignments():
    m, e, paths, targets = study()
    result = irc_check(m, e, paths, targets)
    assert result['verdict'] == 'pass'
    assert result['checks']['opposite_target_basins']['details']['assignments'] == [1, 0]
    assert irc_check(m, e, paths[::-1], targets)['verdict'] == 'pass'


@pytest.mark.parametrize('mutation', ['truncated', 'no_completion', 'error', 'wrong_origin', 'wrong_source', 'wrong_state', 'wrong_method', 'same_direction', 'missing_endpoint', 'missing_minimum', 'unbound_endpoint', 'same_basin', 'unexpected_basin', 'one_point', 'unknown_target_state'])
def test_incomplete_or_wrong_irc_evidence_never_passes(mutation):
    m, e, paths, targets = study(); p = paths[0]
    if mutation == 'truncated': p['max_points_reached'] = True
    if mutation == 'no_completion': p['complete'] = None
    if mutation == 'error': p['termination'] = 'error'
    if mutation == 'wrong_origin': p['origin_coordinates'][1][0] += .5
    if mutation == 'wrong_source': p['material_sha256'] = 'sha256:' + 'c' * 64
    if mutation == 'wrong_state': p['calculation']['multiplicity'] = 4
    if mutation == 'wrong_method': p['calculation']['method'] = 'b3lyp'
    if mutation == 'same_direction': p['direction'] = 'reverse'
    if mutation == 'missing_endpoint': p['endpoint'] = None
    if mutation == 'missing_minimum': p['endpoint']['minimum_evidence'] = None
    if mutation == 'unbound_endpoint': p['points'][-1]['coordinates'][1][0] += .1
    if mutation == 'same_basin': paths[0] = path(m, targets[0], 'forward')
    if mutation == 'unexpected_basin':
        unexpected = material([[0, 0, 0], [1.5, 0, 0], [4, 0, 0]], '[H:1].[H:2][H:3]')
        paths[0] = path(m, unexpected, 'forward')
    if mutation == 'one_point': p['points'] = p['points'][:1]
    if mutation == 'unknown_target_state': targets[1]['value']['electronic_state'] = {'kind': 'unspecified'}
    assert irc_check(m, e, paths, targets)['verdict'] != 'pass'


def test_endpoint_relaxation_must_start_from_the_recorded_last_point():
    m, e, paths, targets = study(); p = paths[0]
    p['points'][-1]['coordinates'][1][0] -= .1
    p['endpoint']['minimum_evidence']['optimization']['start_coordinates'] = copy.deepcopy(p['points'][-1]['coordinates'])
    assert irc_check(m, e, paths, targets)['verdict'] == 'pass'
    p['endpoint']['minimum_evidence']['optimization']['start_coordinates'][1][0] -= .1
    assert irc_check(m, e, paths, targets)['verdict'] == 'fail'


def test_fragment_translation_changes_conformer_but_not_endpoint_species():
    m, e, paths, targets = study()
    endpoint = material([[0, 5, 0], [3.26, 0, 0], [4, 0, 0]], '[H:1].[H:2][H:3]')
    minimum = evidence(endpoint, minimum=True)
    minimum['optimization']['start_coordinates'] = paths[0]['points'][-1]['coordinates']
    paths[0]['endpoint'] = {'material': endpoint['value'], 'minimum_evidence': minimum}
    result = irc_check(m, e, paths, targets)
    assert result['verdict'] == 'pass'
    identity = result['checks']['path_1_endpoint_identity']['details']
    assert identity['target_index'] == 1
    assert identity['conformer_reference']['geometry_status'] == 'different'


@pytest.mark.parametrize('change', ['missing_energy', 'uphill', 'jump', 'graph_geometry_conflict'])
def test_path_or_actual_endpoint_counterevidence_is_not_hidden_by_graph_match(change):
    m, e, paths, targets = study()
    if change == 'missing_energy': paths[0]['points'][0].pop('energy_hartree')
    if change == 'uphill': paths[0]['points'][-1]['energy_hartree'] = -.9
    if change == 'jump': paths[0]['points'][0]['coordinates'][0][1] += 10
    if change == 'graph_geometry_conflict':
        endpoint = material([[0, 0, 0], [1.5, 0, 0], [4, 0, 0]], '[H:1].[H:2][H:3]')
        paths[0]['endpoint'] = {'material': endpoint['value'], 'minimum_evidence': evidence(endpoint, minimum=True)}
        paths[0]['endpoint']['minimum_evidence']['optimization']['start_coordinates'] = paths[0]['points'][-1]['coordinates']
    assert irc_check(m, e, paths, targets)['verdict'] != 'pass'


def test_endpoint_optimization_start_allows_only_rigid_frame_changes():
    m, e, paths, targets = study()
    paths[0]['points'][-1]['coordinates'][1][0] -= .1
    start = np.asarray(paths[0]['points'][-1]['coordinates'])
    paths[0]['endpoint']['minimum_evidence']['optimization']['start_coordinates'] = (start[:, [1, 0, 2]] + 3).tolist()
    assert irc_check(m, e, paths, targets)['verdict'] == 'pass'
    paths[0]['endpoint']['minimum_evidence']['optimization']['start_coordinates'][1][0] += .3
    assert irc_check(m, e, paths, targets)['verdict'] == 'fail'


def test_endpoint_state_cannot_change_just_because_target_has_the_new_state():
    m, e, paths, targets = study()
    excited_spin = material(targets[1]['coordinates'], '[H:1].[H:2][H:3]', multiplicity=4)
    paths[0] = path(m, excited_spin, 'forward'); targets[1] = excited_spin
    result = irc_check(m, e, paths, targets)
    assert result['verdict'] == 'fail'
    assert result['checks']['path_1_endpoint_source_state']['verdict'] == 'fail'


def test_unknown_competing_target_does_not_make_an_assignment_unique():
    m, e, paths, targets = study()
    targets[0] = copy.deepcopy(targets[1])
    targets[0]['coordinates'] = None
    result = irc_check(m, e, paths, targets)
    assert result['verdict'] != 'pass'
    assert result['checks']['path_1_endpoint_identity']['verdict'] == 'inconclusive'


def test_embedded_original_material_bytes_keep_existing_evidence_binding(tmp_path):
    m, e, paths, targets = study()
    file = tmp_path / 'endpoint.json'
    file.write_text(json.dumps(targets[1]['value'], indent=2) + '\n')
    endpoint = read_material(file)
    paths[0]['endpoint'] = {'material_json': file.read_bytes().decode('utf-8'), 'minimum_evidence': evidence(endpoint, minimum=True)}
    assert irc_check(m, e, paths, targets)['verdict'] == 'pass'
    paths[0]['endpoint']['material_json'] += '\n'
    assert irc_check(m, e, paths, targets)['verdict'] == 'fail'


def gaussian_log():
    text = '#p HF/STO-3G Opt=(TS,CalcFC) Freq\n ----------------\n Charge = 0 Multiplicity = 2\n'
    text += ' Standard orientation:\n ---------------------------------------------------------------------\n Center Atomic Atomic Coordinates (Angstroms)\n Number Number Type X Y Z\n ---------------------------------------------------------------------\n'
    for i, row in enumerate(XYZ, 1): text += f' {i} 1 0 ' + ' '.join(str(x) for x in row) + '\n'
    text += ' ---------------------------------------------------------------------\n SCF Done: E(UHF) = -1.0 A.U.\n'
    text += ' Maximum Force 0.00001 0.00045 YES\n RMS     Force 0.00001 0.00030 YES\n Maximum Displacement 0.00001 0.0018 YES\n RMS     Displacement 0.00001 0.0012 YES\n Stationary point found.\n Harmonic frequencies\n'
    for fs in [[-400., 100., 150.], [200.]]:
        text += ' Frequencies -- ' + ' '.join(str(f) for f in fs) + '\n Atom AN X Y Z\n'
        for i in range(3):
            vectors = ([1., 0., 0.] if i == 1 and fs[0] < 0 else [0., 0., 0.]) + [0.] * (3 * (len(fs) - 1))
            text += f' {i + 1} 1 ' + ' '.join(str(v) for v in vectors) + '\n'
    return text + ' Thermochemistry\n Normal termination of Gaussian\n'


def test_gaussian_adapter_produces_bound_reusable_evidence(tmp_path):
    m = material(); log = tmp_path / 'calculation.log'; log.write_text(gaussian_log())
    e = gaussian_evidence(m, log, constraints='none')
    assert e['calculation']['method'] == 'hf'
    assert stationary(m, e)['verdict'] == 'pass'
    assert mode_check(m, e, coordinates())['verdict'] == 'pass'
    unknown = gaussian_evidence(m, log)
    assert stationary(m, unknown)['scientific_verdict'] == 'not_assessed'


def test_gaussian_negligible_forces_survive_adapter_and_stationary_check(tmp_path):
    text = gaussian_log().replace('0.00001 0.0018 YES', '0.002 0.0018 NO').replace(
        ' Stationary point found.', ' Optimization completed on the basis of negligible forces.\n Stationary point found.')
    m = material(); log = tmp_path / 'calculation.log'; log.write_text(text)
    e = gaussian_evidence(m, log, constraints='none')
    assert e['optimization']['completion_reason'] == 'gaussian_negligible_forces'
    checked = stationary(m, e)
    assert checked['verdict'] == 'pass'
    assert any(not row['satisfied'] for row in checked['checks']['optimization']['details'])
    e['optimization'].pop('completion_reason')
    assert stationary(m, e)['checks']['optimization']['verdict'] == 'fail'


@pytest.mark.parametrize('change', ['constraint', 'excited', 'late_incomplete', 'missing_vector'])
def test_gaussian_adapter_does_not_promote_unsupported_or_incomplete_logs(tmp_path, change):
    m = material(); text = gaussian_log()
    if change == 'constraint': text = text.replace('CalcFC)', 'CalcFC,ModRedundant)')
    if change == 'excited': text = text.replace(' Freq', ' TD=(Root=1) Freq')
    if change == 'late_incomplete': text += '\n Step number 42\n Maximum Force 0.1 0.00045 NO\n'
    if change == 'missing_vector': text = text.replace(' 2 1 1.0 0.0 0.0', ' 2 1 0.0 0.0 0.0')
    log = tmp_path / 'calc.log'; log.write_text(text)
    assert stationary(m, gaussian_evidence(m, log, constraints='none'))['verdict'] != 'pass'


def test_gaussian_irc_adapter_retains_coordinate_points_and_missing_basin_evidence(tmp_path):
    m, e, paths, targets = study()
    text = gaussian_log().split(' SCF Done:')[0].replace('Opt=(TS,CalcFC) Freq', 'IRC=(Forward,CalcFC,MaxPoints=5)')
    text += ' Point Number 1 in FORWARD path direction\n'
    for i, point in enumerate(paths[0]['points'], 1):
        text += f' SCF Done: E(UHF) = -1.1 A.U.\n Point Number: {i} Path Number: 1\n CURRENT STRUCTURE\n'
        for j, coords in enumerate(point['coordinates'], 1): text += f' {j} 1 ' + ' '.join(str(v) for v in coords) + '\n'
        text += f' NET REACTION COORDINATE UP TO THIS POINT = {i}.0\n'
    text += ' Calculation of FORWARD path complete.\n Normal termination of Gaussian\n'
    log = tmp_path / 'irc.log'; log.write_text(text)
    parsed = gaussian_evidence(m, log, kind='irc', constraints='none')
    assert parsed['complete'] and not parsed['max_points_reached']
    assert len(parsed['points']) == 2 and parsed['endpoint'] is None
    assert parsed['origin_coordinates'] == XYZ.tolist()
    result = irc_check(m, e, [parsed, paths[1]], targets)
    assert result['verdict'] == 'inconclusive'
    parsed['endpoint'] = paths[0]['endpoint']
    assert irc_check(m, e, [parsed, paths[1]], targets)['verdict'] == 'pass'


@pytest.mark.parametrize('executor', ['chemical.stationary-check', 'chemical.mode-check', 'chemical.irc-check', 'chemical.gaussian-evidence', 'chemical.ts-connectivity-inputs', 'chemical.displacement-check'])
def test_independent_checks_execute_and_collect_through_real_jobs(tmp_path, executor):
    from research_agent.application.api import execute
    from research_agent.application.executors import prepare
    from tests.unit.test_job_recovery import workspace
    root = tmp_path / 'workspace'; workspace(root)
    node = execute('research_create', root, {'goal': 'Reaction-independent evidence checks'})['node']
    m, e, paths, targets = study()
    source = root / 'material.json'; source.write_text(json.dumps(m['value']))
    disk = read_material(source)
    # Standalone material binding is the exact file digest; embedded endpoint
    # binding is the canonical JSON digest documented by the nested contract.
    e['material_sha256'] = disk['sha256']
    for p in paths: p['material_sha256'] = disk['sha256']
    payloads = {'evidence': e}
    if executor in {'chemical.mode-check', 'chemical.ts-connectivity-inputs', 'chemical.displacement-check'}: payloads['coordinates'] = coordinates()
    if executor == 'chemical.displacement-check':
        payloads.update(study=displacement_study(disk, e, paths), reactant=targets[0]['value'], product=targets[1]['value'])
    if executor == 'chemical.ts-connectivity-inputs':
        payloads.pop('evidence'); payloads['log'] = None
    if executor == 'chemical.irc-check': payloads.update(forward=paths[0], reverse=paths[1], reactant=targets[0]['value'], product=targets[1]['value'])
    inputs = {'material': source}
    for role, value in payloads.items():
        inputs[role] = root / (role + '.json'); inputs[role].write_text(json.dumps(value))
    args = []
    if executor == 'chemical.gaussian-evidence':
        inputs['evidence'].write_text(gaussian_log()); args = ['--constraints', 'none']
    if executor == 'chemical.ts-connectivity-inputs': inputs['log'].write_text(gaussian_log())
    prepared = prepare(Path(os.environ['CORAGENT_JOB_CONFIG']), 'local', executor, '1', inputs, args)
    job = execute('job_start', root, {**prepared, 'node_id': node['id']})
    try:
        for _ in range(300):
            status = execute('job_status', root, {'job_id': job['job_id']})
            if status['state'] in {'succeeded', 'failed'}: break
            time.sleep(.01)
        assert status['state'] == 'succeeded'
        assert execute('job_collect', root, {'job_id': job['job_id']})['output_validation']['complete']
        output = 'connectivity_inputs.json' if executor == 'chemical.ts-connectivity-inputs' else 'result.json'
        result = json.loads((Path(job['cwd']) / 'results' / output).read_text())
        if executor == 'chemical.ts-connectivity-inputs': assert len(result['inputs']) == 6
        elif executor == 'chemical.gaussian-evidence': assert result['schema_version'] == 'chemical-stationary-evidence/1'
        else: assert result['verdict'] == 'pass'
    finally:
        execute('job_cancel', root, {'job_id': job['job_id']})


def test_short_irc_requires_endpoint_optimization_and_keeps_strict_policy():
    m, e, paths, targets = study()
    for p in paths:
        p['max_points_reached'] = True
        p['points'][-1]['coordinates'][1][0] += .03
        p['endpoint']['minimum_evidence']['optimization']['start_coordinates'] = copy.deepcopy(p['points'][-1]['coordinates'])
    result = irc_check(m, e, paths, targets, policy='endpoint_relaxation')
    assert result['verdict'] == 'pass'
    assert result['evidence_level'] == 'short_irc_with_endpoint_optimization'
    assert not result['full_irc_complete']
    assert irc_check(m, e, paths, targets)['verdict'] == 'fail'
    paths[0]['endpoint']['minimum_evidence']['optimization']['start_coordinates'][1][0] += .05
    assert irc_check(m, e, paths, targets, policy='endpoint_relaxation')['verdict'] == 'fail'
    paths[0]['endpoint']['minimum_evidence']['optimization'].pop('start_coordinates')
    assert irc_check(m, e, paths, targets, policy='endpoint_relaxation')['verdict'] != 'pass'


def test_standalone_restart_cannot_certify_origin():
    m, e, paths, targets = study()
    paths[0]['restart_segment'] = True
    assert irc_check(m, e, paths, targets)['verdict'] == 'fail'


def displacement_study(m, e, paths):
    from connectivity import probe_geometries
    branches = []
    for a in [.05, .1]:
        geometries, _ = probe_geometries(m, e, coordinates(), a)
        for i, sign in enumerate(['plus', 'minus']):
            endpoint = copy.deepcopy(paths[i]['endpoint'])
            endpoint['minimum_evidence']['optimization']['start_coordinates'] = geometries[sign].tolist()
            branches.append({'direction': sign, 'amplitude_angstrom': a, 'endpoint': endpoint})
    return {'schema_version': 'chemical-displacement-study/1', 'branches': branches}


def test_displacement_basin_support_requires_bound_consistent_both_sides():
    from connectivity import displacement_check
    m, e, paths, targets = study()
    doc = displacement_study(m, e, paths)
    result = displacement_check(m, e, coordinates(), doc, targets)
    assert result['verdict'] == 'pass'
    assert result['evidence_level'] == 'mode_displacement_endpoint_support'
    assert result['amplitude_sensitivity_assessed'] and not result['full_irc_complete']
    wrong = copy.deepcopy(doc)
    wrong['branches'][0]['endpoint']['minimum_evidence']['optimization']['start_coordinates'][1][0] += .01
    assert displacement_check(m, e, coordinates(), wrong, targets)['verdict'] == 'fail'
    for branch in doc['branches']:
        start = branch['endpoint']['minimum_evidence']['optimization']['start_coordinates']
        branch['endpoint'] = copy.deepcopy(paths[0]['endpoint'])
        branch['endpoint']['minimum_evidence']['optimization']['start_coordinates'] = start
    assert displacement_check(m, e, coordinates(), doc, targets)['verdict'] == 'inconclusive'


def test_prepared_connectivity_inputs_bind_source_mode_and_checkpoint(tmp_path):
    from connectivity import prepare_inputs
    from gaussian_binding import inspect_binding
    from input_job import inspect_input
    m, e, _, _ = study()
    result = prepare_inputs(m, e, coordinates(), tmp_path / 'prepared')
    assert len(result['inputs']) == 6
    for row in result['inputs']:
        file = tmp_path / 'prepared' / row['path']
        checked = inspect_input(file, 'hf', 'sto-3g', 0, 2, 1, 2000)
        assert checked['checkpoints'] == [row['checkpoint']]
        assert row['collect'] == ['results/' + row['checkpoint']]
        assert inspect_binding(file, 'hf', 'sto-3g', 0, 2)['input'] == row
        if row['kind'] == 'mode_displacement':
            assert np.max(np.linalg.norm(np.array(row['start_coordinates']) - m['coordinates'], axis=1)) == pytest.approx(row['amplitude_angstrom'])
        else:
            assert 'MaxPoints=20' in file.read_text()
            assert row['start_coordinates'] == m['coordinates'].tolist()
    file.write_text(file.read_text().replace('StepSize=5', 'StepSize=10'))
    with pytest.raises(ValueError, match='differs from the source-bound'):
        inspect_binding(file, 'hf', 'sto-3g', 0, 2)
    e['coordinates'][1][0] += .1
    with pytest.raises(ValueError, match='Source must pass'):
        prepare_inputs(m, e, coordinates(), tmp_path / 'seed')


def test_later_geometry_cannot_reuse_old_normal_modes(tmp_path):
    m = material(); log = tmp_path / 'calc.log'
    text = gaussian_log() + ' SCF Done: E(UHF) = -1.1 A.U.\n'
    log.write_text(text)
    e = gaussian_evidence(m, log, constraints='none')
    assert e['normal_modes'] is None
    assert mode_check(m, e, coordinates())['verdict'] != 'pass'


def test_free_text_constraints_removed_title_does_not_claim_active_constraints(tmp_path):
    m = material(); log = tmp_path / 'calc.log'
    log.write_text(gaussian_log().replace(' Charge =', ' All constraints removed after preoptimization\n Charge ='))
    assert stationary(m, gaussian_evidence(m, log, constraints='none'))['verdict'] == 'pass'
    log.write_text(gaussian_log() + ' ! R1 R(1,2) 2.0 Frozen !\n')
    assert stationary(m, gaussian_evidence(m, log, constraints='none'))['scientific_verdict'] == 'not_assessed'


def test_source_binding_rejects_modified_bundle_and_wrong_output_origin(tmp_path):
    from connectivity import prepare_inputs
    from gaussian_binding import inspect_binding, check_output_origin
    from tests.unit.test_chemical_path_execution import orientation
    m, e, _, _ = study()
    root = tmp_path / 'prepared'
    result = prepare_inputs(m, e, coordinates(), root)
    file = root / next(r['path'] for r in result['inputs'] if r['kind'] == 'irc')
    bound = inspect_binding(file, 'hf', 'sto-3g', 0, 2)
    log = tmp_path / 'output.log'
    # Proper rigid rotation and translation do not change atom identity.
    xyz = m['coordinates'][:, [1, 0, 2]] + 2
    log.write_text(orientation([('H', *v) for v in xyz]))
    assert check_output_origin(bound, log)['status'] == 'verified'
    xyz[1, 0] += .1
    log.write_text(orientation([('H', *v) for v in xyz]))
    assert check_output_origin(bound, log)['status'] == 'mismatch'
    source = root / 'ts_source.json'
    bundle = json.loads(source.read_text()); bundle['source_kind'] = 'initial_guess'
    source.write_text(json.dumps(bundle))
    with pytest.raises(ValueError, match='digest mismatch'):
        inspect_binding(file, 'hf', 'sto-3g', 0, 2)


def test_amplitude_dependent_assignment_stays_inconclusive():
    from connectivity import displacement_check
    m, e, paths, targets = study()
    doc = displacement_study(m, e, paths)
    for i in [2, 3]:
        start = doc['branches'][i]['endpoint']['minimum_evidence']['optimization']['start_coordinates']
        doc['branches'][i]['endpoint'] = copy.deepcopy(paths[1-(i % 2)]['endpoint'])
        doc['branches'][i]['endpoint']['minimum_evidence']['optimization']['start_coordinates'] = start
    result = displacement_check(m, e, coordinates(), doc, targets)
    assert result['checks']['opposite_basins']['verdict'] == 'pass'
    assert result['checks']['amplitude_consistency']['verdict'] == 'inconclusive'
    assert result['verdict'] == 'inconclusive'
