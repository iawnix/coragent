"""Synthetic Gaussian records test evidence selection, not computed chemistry."""
import importlib.util
import json
from pathlib import Path
import shlex
import subprocess
import sys

import pytest
pytest.importorskip('numpy')

SKILLS = Path(__file__).resolve().parents[2] / 'domains/chemical/skills'
sys.path[:0] = [str(SKILLS / 'gaussian/scripts'), str(SKILLS / '_shared')]
from gaussian_io import parse_log

spec = importlib.util.spec_from_file_location('frequency_regression_validator',
    SKILLS / 'validation/scripts/gaussian_frequency.py')
frequency_validator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(frequency_validator)

CONVERGED = ''' Maximum Force 0.00001 0.00045 YES
 RMS     Force 0.00001 0.00030 YES
 Maximum Displacement 0.00001 0.00180 YES
 RMS     Displacement 0.00001 0.00120 YES
 Stationary point found.
'''

NEGLIGIBLE = CONVERGED.replace('0.00001 0.00180 YES', '0.00200 0.00180 NO').replace(
    ' Stationary point found.', ' Optimization completed on the basis of negligible forces.\n Stationary point found.')


def test_negligible_force_completion_retains_failed_displacement_row(tmp_path):
    summary = parse(tmp_path, NEGLIGIBLE + ' Normal termination of Gaussian\n')['summary']
    assert summary['optimization_completed']
    assert summary['optimization_completion_reason'] == 'gaussian_negligible_forces'
    assert not summary['final_convergence_satisfied']
    assert summary['force_convergence']['Maximum Displacement']['converged'] == 'NO'


@pytest.mark.parametrize('case', ['truncated', 'error', 'later_step', 'later_rows', 'missing_marker', 'bad_force', 'stopped'])
def test_negligible_force_completion_does_not_mask_failed_or_missing_evidence(tmp_path, case):
    text = NEGLIGIBLE
    if case == 'error': text += ' Error termination via Lnk1e\n'
    if case == 'later_step': text += ' Step number 2 out of a maximum of 20\n'
    if case == 'later_rows': text += CONVERGED.replace(' Stationary point found.\n', '')
    if case == 'missing_marker': text = text.replace(' Optimization completed on the basis of negligible forces.\n', '')
    if case == 'bad_force': text = text.replace('0.00001 0.00045 YES', '0.1 0.00045 YES')
    if case == 'stopped': text += ' Optimization stopped.\n'
    if case != 'truncated': text += ' Normal termination of Gaussian\n'
    assert not parse(tmp_path, text)['summary']['optimization_completed']


@pytest.mark.parametrize('mode', ['xyz', 'explicit'])
@pytest.mark.parametrize('status', ['negligible', 'limit', 'nonzero'])
def test_runners_preserve_last_geometry_and_use_solver_completion(tmp_path, mode, status):
    from tests.unit.test_gaussian_explicit_input import gjf
    route = '#p M062X/6-31G** Opt=Tight SCF=Tight Int=UltraFine'
    orientation = (' Standard orientation:\n ----\n Center Atomic Atomic Coordinates (Angstroms)\n'
                   ' Number Number Type X Y Z\n ----\n 1 8 0 0.0 0.0 0.0\n'
                   ' 2 1 0 0.0 0.0 1.0\n 3 1 0 0.0 1.0 0.0\n ----\n')
    text = route + '\n ----\n' + orientation + ' SCF Done: E(RM062X) = -76.0 A.U.\n'
    text += (NEGLIGIBLE + ' Normal termination of Gaussian\n' if status == 'negligible' else
             ' Maximum Force 0.1 0.00045 NO\n Optimization stopped.\n Error termination via Lnk1e\n')
    log = tmp_path / 'fixture.out'; log.write_text(text)
    program = tmp_path / 'fixture-gaussian'
    program.write_text('#!/bin/sh\ncat >/dev/null\ncat ' + shlex.quote(str(log)) +
                       ('\nexit 1\n' if status == 'nonzero' else '\n'))
    program.chmod(0o755)
    if mode == 'explicit':
        source = gjf(tmp_path / 'input.gjf', 'Opt=Tight SCF=Tight Int=UltraFine')
        inputs = ['--input-gjf', str(source), '--validation', 'opt']
    else:
        source = tmp_path / 'input.xyz'; source.write_text('3\nfixture\nO 0 0 0\nH 0 0 1\nH 0 1 0\n')
        inputs = ['--xyz', str(source), '--task', 'opt']
    out = tmp_path / 'out'
    completed = subprocess.run([sys.executable, str(SKILLS / 'gaussian/scripts/run.py'), *inputs,
        '--executable', str(program), '--output-dir', str(out), '--threads', '12', '--memory-mb', '4000'],
        capture_output=True, text=True, timeout=30)
    assert completed.returncode == (0 if status == 'negligible' else 1), completed.stderr
    result = json.loads((out / 'result.json').read_text())
    assert (out / result['last_attempt']['geometry']).read_text().startswith('3\n')
    assert result['last_attempt']['summary']['optimization_completed'] == (status == 'negligible')
    assert result['checks_passed'] == (status == 'negligible')
    assert result['scientific_validation'] == 'not_assessed'
    if status != 'negligible': assert not (out / 'geometry.xyz').exists()


def parse(tmp_path, text):
    path = tmp_path / 'gaussian.out'
    path.write_text(text)
    return parse_log(path)


def test_repaired_calculation_does_not_inherit_previous_process_failure(tmp_path):
    failed = (' Entering Link 1 = /fixture/l1.exe\n #p HF/STO-3G Opt\n ----\n'
              ' Convergence failure -- run terminated.\n Error termination via Lnk1e\n')
    repaired = (' Entering Link 1 = /fixture/l1.exe\n #p HF/STO-3G Opt\n ----\n'
                ' SCF Done: E(RHF) = -75.1 A.U.\n' + CONVERGED + ' Normal termination of Gaussian\n')
    result = parse(tmp_path, failed + repaired)
    assert result['summary']['section_count'] == 2
    assert result['summary']['selected_section_index'] == 1
    assert result['summary']['normal_termination']
    assert not result['summary']['error_termination']
    assert result['summary']['primary_failure'] is None
    assert result['summary']['final_convergence_satisfied']
    old = parse_log(tmp_path / 'gaussian.out', section_index=0)
    assert old['summary']['primary_failure']['kind'] == 'scf_convergence'


@pytest.mark.parametrize('later', [
    ' Maximum Force 0.1 0.00045 NO\n',
    ' Maximum Force 0.00001 0.00045 YES\n',
    CONVERGED.replace(' Stationary point found.\n', '').replace('0.00001 0.00045 YES', '0.1 0.00045 NO'),
])
def test_later_incomplete_or_failed_convergence_cannot_reuse_old_stationary_point(tmp_path, later):
    result = parse(tmp_path, CONVERGED + ' Step number 2 out of a maximum of 20\n' + later)
    assert not result['summary']['final_convergence_satisfied']
    assert result['summary']['force_convergence_source'] == 'last_section_rows'
    assert not result['summary']['stationary_point_found']


@pytest.mark.parametrize('later', [' Step number 2 out of a maximum of 20\n', ' Maximum Force\n'])
def test_truncated_new_optimization_evidence_clears_previous_convergence(tmp_path, later):
    result = parse(tmp_path, CONVERGED + later)
    assert not result['summary']['final_convergence_evidence_present']
    assert not result['summary']['stationary_point_found']


def test_empty_final_harmonic_section_does_not_reuse_previous_negative_mode(tmp_path):
    result = parse(tmp_path, ' Harmonic frequencies\n Frequencies -- -200.0 100.0 150.0\n'
        ' Thermochemistry\n Harmonic frequencies\n Normal termination of Gaussian\n')
    assert result['summary']['raw_imaginary_frequency_count'] == 1
    assert result['frequencies'] == []
    assert result['summary']['frequency_count'] == 0
    assert result['normal_modes'] == []


def test_fortran_exponents_in_frequency_records_are_read_without_losing_sign(tmp_path):
    result = parse(tmp_path, ' Harmonic frequencies\n Frequencies -- -2.0D+02 1.0d+02 1.5E+02\n')
    assert result['frequencies'] == [-200.0, 100.0, 150.0]
    assert result['summary']['imaginary_frequency_count'] == 1


def test_final_geometry_follows_record_order_across_orientation_types(tmp_path):
    def orientation(kind, x):
        return (f' {kind} orientation:\n ----\n Center Atomic Atomic Coordinates (Angstroms)\n'
                ' Number Number Type X Y Z\n ----\n'
                f' 1 8 0 {x} 0.0 0.0\n ----\n')
    result = parse(tmp_path, orientation('Standard', 0.0) + orientation('Input', 1.0))
    assert result['atoms'] == [('O', 1.0, 0.0, 0.0)]


@pytest.mark.parametrize('frequencies,error_termination', [
    ([-200.0, float('nan'), 100.0], False),
    ([-200.0, float('inf'), 100.0], False),
    ([-200.0, 'unparsed', 100.0], False),
    ([-200.0, True, 100.0], False),
    ([-200.0, 100.0, 150.0], True),
])
def test_unusable_frequency_evidence_is_inconclusive_not_a_scientific_pass(tmp_path, frequencies, error_termination):
    path = tmp_path / 'parsed.json'
    path.write_text(json.dumps({'summary': {'normal_termination': True, 'error_termination': error_termination},
                               'frequencies': frequencies}))
    assert frequency_validator.validate([path])['verdict'] == 'inconclusive'


@pytest.mark.parametrize('frequencies,verdict', [
    ([-200.0, 100.0, 150.0], 'pass'), ([20.0, 100.0, 150.0], 'fail'),
    ([-200.0, -100.0, 150.0], 'fail'),
])
def test_finite_frequency_table_reports_only_its_declared_scope(tmp_path, frequencies, verdict):
    path = tmp_path / 'parsed.json'
    path.write_text(json.dumps({'summary': {'normal_termination': True, 'error_termination': False},
                               'frequencies': frequencies}))
    result = frequency_validator.validate([path])
    assert result['verdict'] == verdict
    assert 'excludes IRC and mode character' in result['scope']


@pytest.mark.parametrize('evidence,passes', [
    (CONVERGED + ' Harmonic frequencies\n Frequencies -- -200.0 100.0 150.0\n', True),
    (CONVERGED + ' Harmonic frequencies\n Frequencies -- -200.0 100.0 150.0\n'
        ' Thermochemistry\n Harmonic frequencies\n', False),
    (CONVERGED + ' Maximum Force 0.00001 0.00045 YES\n'
        ' Harmonic frequencies\n Frequencies -- -200.0 100.0 150.0\n', False),
])
def test_actual_runner_keeps_program_success_separate_from_final_evidence(tmp_path, evidence, passes):
    from tests.unit.test_gaussian_explicit_input import gjf
    source = gjf(tmp_path / 'input.gjf')
    log = tmp_path / 'synthetic.out'
    log.write_text(' #p M062X/6-31G** Opt=(TS,CalcFC) Freq\n ----------------\n'
                   ' SCF Done: E(RM062X) = -76.0 A.U.\n' + evidence + ' Normal termination of Gaussian\n')
    program = tmp_path / 'fixture-gaussian'
    program.write_text('#!/bin/sh\ncat >/dev/null\ncat ' + shlex.quote(str(log)) + '\n')
    program.chmod(0o755)
    out = tmp_path / 'out'
    run = subprocess.run([sys.executable, str(SKILLS / 'gaussian/scripts/run.py'),
        '--input-gjf', str(source), '--executable', str(program), '--output-dir', str(out),
        '--threads', '12', '--memory-mb', '4000', '--validation', 'saddle'],
        capture_output=True, text=True, timeout=30)
    result = json.loads((out / 'result.json').read_text())
    assert run.returncode == (0 if passes else 1)
    assert result['program_returncode'] == 0
    assert result['execution_status'] == 'succeeded'
    assert result['parsing']['status'] == 'completed'
    assert result['check_status'] == ('satisfied' if passes else 'not_satisfied')
    assert result['checks_passed'] is passes
    assert result['scientific_validation'] == 'not_assessed'


@pytest.mark.parametrize('message,kind', [
    ('Maximum number of corrector steps exceded.', 'irc_corrector_limit'),
    ('Maximum number of corrector steps exceeded.', 'irc_corrector_limit'),
    ('You must use ReadCartesianFC, FCCards, or CalcFC with IRC.', 'irc_hessian_missing'),
    ('RedCar/ORedCr failed for GTrans.', 'coordinate_transform'),
])
def test_specific_failure_precedes_secondary_termination_signals(tmp_path, message, kind):
    result = parse(tmp_path, message + '\n Error termination via Lnk1e\n segmentation violation\n')
    summary = result['summary']
    assert summary['primary_failure']['kind'] == kind
    assert {event['kind'] for event in summary['diagnostics']} >= {kind, 'signal', 'execution_error'}


@pytest.mark.parametrize('method,label', [
    ('HF', 'RHF'), ('HF', 'UHF'), ('ROHF', 'ROHF'), ('B3LYP', 'RB3LYP'),
    ('M062X', 'RM062X'), ('wB97X-D', 'RwB97XD'),
])
def test_matching_scf_energy_preserves_method_and_fortran_exponent(tmp_path, method, label):
    summary = parse(tmp_path, f' #p {method}/6-31G* SP\n ----\n'
                    f' SCF Done: E({label}) = -7.5123D+01 A.U.\n')['summary']
    assert summary['electronic_energy_hartree'] == pytest.approx(-75.123)
    assert summary['reference_scf_energy_hartree'] == summary['electronic_energy_hartree']
    assert summary['energy_evidence']['status'] == 'supported'
    assert summary['energy_evidence']['scf_method'] == label


@pytest.mark.parametrize('route,label,extra', [
    ('B3LYP/6-31G* TD=(Root=2,NStates=4)', 'RB3LYP', ' Excited State 2: Singlet-A 4.1 eV\n'),
    ('B3LYP/6-31G* TDA', 'RB3LYP', ''),
    ('CIS/6-31G*', 'RHF', ''),
    ('MP2/6-31G*', 'RHF', ' EUMP2 = -7.60D+01\n'),
    ('CCSD(T)/6-31G*', 'RHF', ' CCSD(T)= -7.61D+01\n'),
    ('B2PLYP/6-31G*', 'RB2PLYP', ''),
    ('B3LYP/6-31G* Counterpoise=2', 'RB3LYP', ''),
    ('B3LYP/6-31G* IOp(3/76=1000005000)', 'RB3LYP', ''),
    ('B3LYP/6-31G*', 'RB3LYP', ' Total Energy, E(TD-HF/TD-KS) = -75.0\n'),
    ('B3LYP/6-31G*', 'RHF', ''),
])
def test_reference_scf_is_not_promoted_to_unsupported_target_energy(tmp_path, route, label, extra):
    summary = parse(tmp_path, f' #p {route}\n ----\n SCF Done: E({label}) = -75.1 A.U.\n'
                    + extra + ' Zero-point correction= 0.01\n'
                    ' Sum of electronic and zero-point Energies= -75.09\n'
                    ' Sum of electronic and thermal Free Energies= -75.12\n'
                    ' Normal termination of Gaussian\n')['summary']
    assert summary['normal_termination']
    assert summary['reference_scf_energy_hartree'] == -75.1
    assert summary['electronic_energy_hartree'] is None
    assert summary['energy_evidence']['status'] == 'unsupported'
    assert summary['electronic_plus_zpe_hartree'] is None
    assert summary['electronic_plus_thermal_free_energy_hartree'] is None
    assert summary['reported_thermochemical_totals']['electronic_plus_zpe_hartree'] == -75.09
    assert summary['zero_point_correction_hartree'] == .01


def test_missing_route_or_invalid_final_energy_never_reuses_an_earlier_value(tmp_path):
    missing = parse(tmp_path, ' SCF Done: E(RHF) = -75.1 A.U.\n')['summary']
    assert missing['electronic_energy_hartree'] is None
    assert missing['reference_scf_energy_hartree'] == -75.1
    for value in ['********', 'NaN', '-Infinity']:
        summary = parse(tmp_path, ' #p HF/STO-3G SP\n ----\n SCF Done: E(RHF) = -75.1 A.U.\n'
                        f' SCF Done: E(RHF) = {value} A.U.\n')['summary']
        assert summary['reference_scf_energy_hartree'] is None
        assert summary['electronic_energy_hartree'] is None
        assert summary['energy_evidence']['reason'] == 'invalid_final_scf_energy'


@pytest.mark.parametrize('mode', ['xyz', 'explicit'])
def test_runners_retain_output_but_reject_mp2_reference_energy(tmp_path, mode):
    from tests.unit.test_gaussian_explicit_input import gjf
    log = tmp_path / 'synthetic.out'
    log.write_text(' #p MP2/6-31G** SP SCF=Tight Int=UltraFine\n ----\n'
                   ' SCF Done: E(RHF) = -76.0 A.U.\n EUMP2 = -7.62D+01\n'
                   ' Normal termination of Gaussian\n')
    program = tmp_path / 'fixture-gaussian'
    program.write_text('#!/bin/sh\ncat >/dev/null\ncat ' + shlex.quote(str(log)) + '\n')
    program.chmod(0o755)
    if mode == 'explicit':
        source = gjf(tmp_path / 'input.gjf', 'SP SCF=Tight Int=UltraFine')
        source.write_text(source.read_text().replace('M062X/', 'MP2/'))
        inputs = ['--input-gjf', str(source), '--validation', 'none']
    else:
        source = tmp_path / 'input.xyz'
        source.write_text('3\nsynthetic\nO 0 0 0\nH 0 0 1\nH 0 1 0\n')
        inputs = ['--xyz', str(source), '--task', 'sp']
    out = tmp_path / 'out'
    run = subprocess.run([sys.executable, str(SKILLS / 'gaussian/scripts/run.py'), *inputs,
        '--method', 'MP2', '--executable', str(program), '--output-dir', str(out),
        '--threads', '12', '--memory-mb', '4000'], capture_output=True, text=True, timeout=30)
    assert run.returncode == 1
    result = json.loads((out / 'result.json').read_text())
    assert result['checks_passed'] is False
    assert result['steps'] == []
    assert 'target energy not assessed' in result['error']['message']
    folder = out if mode == 'explicit' else out / 'sp'
    assert (folder / 'gaussian.out').read_text() == log.read_text()
    parsed = json.loads((folder / 'parsed.json').read_text())
    assert parsed['summary']['reference_scf_energy_hartree'] == -76.0
    assert parsed['summary']['electronic_energy_hartree'] is None
    if mode == 'explicit':
        assert result['execution_status'] == 'succeeded'
        assert result['parsing']['status'] == 'completed'
        assert result['check_status'] == 'not_satisfied'


def test_unsupported_scan_keeps_reference_points_without_target_energies(tmp_path):
    from gaussian_io import parse_scan_log
    path = tmp_path / 'scan.out'
    path.write_text(' #p MP2/6-31G* Opt=Scan\n ----\n'
                    ' SCF Done: E(RHF) = -75.0 A.U.\n SCF Done: E(RHF) = -75.1 A.U.\n'
                    ' Normal termination of Gaussian\n')
    parsed = parse_scan_log(path)
    assert not parsed['summary']['scan_energies_complete']
    assert parsed['summary']['electronic_energy_hartree'] is None
    assert [p['reference_scf_energy_hartree'] for p in parsed['profile']['points']] == [-75., -75.1]
    assert all(p['energy_hartree'] is None for p in parsed['profile']['points'])
