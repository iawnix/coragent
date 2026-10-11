"""RRHO result reuse, explicit composite energies and entropy-only frequency floor."""
import math
import numpy as np

from energy_common import (CM_K, HARTREE_J_MOL, R, canonical, fields, finite_result,
    integer, material, model, number, same_geometry, schema, source, standard, standard_correction)


def thermal_data(thermal):
    """Normalize corrections relative to E; never interpret missing fields as zero."""
    data = thermal['data']
    if not isinstance(data, dict):
        raise ValueError('thermal data must be an object')
    fmt = thermal['format']
    if fmt == 'corrections':
        fields(data, ('E_hartree', 'ZPE_hartree', 'H_correction_hartree', 'G_correction_hartree'), 'corrections')
        mapping = {'E': 'E_hartree', 'ZPE': 'ZPE_hartree', 'H': 'H_correction_hartree', 'G': 'G_correction_hartree'}
        totals = {}
    elif fmt == 'gaussian':
        if data.get('energy_evidence', {}).get('status') != 'supported':
            raise ValueError('Gaussian target electronic energy is not supported')
        mapping = {'E': 'electronic_energy_hartree', 'ZPE': 'zero_point_correction_hartree',
                   'H': 'thermal_enthalpy_correction_hartree', 'G': 'thermal_gibbs_correction_hartree'}
        totals = {'ZPE': 'electronic_plus_zpe_hartree', 'H': 'electronic_plus_thermal_enthalpy_hartree', 'G': 'electronic_plus_thermal_free_energy_hartree'}
        if data.get('temperature_k') != thermal['temperature_k']:
            raise ValueError('Gaussian temperature disagrees with declared thermal temperature')
        pressure = number(data.get('pressure_atm'), 'Gaussian pressure', True) * 101325.
        if thermal['standard_state'] != {'kind': 'pressure_pa', 'value': pressure}:
            raise ValueError('Gaussian source standard state disagrees with log')
    elif fmt == 'cf22d':
        if data.get('schema_version') != 'pyscf-thermo/1':
            raise ValueError('pyscf-thermo/1 required')
        mapping = {'E': 'electronic_energy_hartree', 'ZPE': 'zpe_hartree', 'H': 'enthalpy_correction_hartree', 'G': 'gibbs_correction_hartree'}
        totals = {'ZPE': 'energy_0k_hartree', 'H': 'enthalpy_hartree', 'G': 'gibbs_hartree'}
        if data.get('temperature_K') != thermal['temperature_k'] or thermal['standard_state'] != {'kind': 'pressure_pa', 'value': data.get('pressure_Pa')}:
            raise ValueError('CF22D source temperature/standard state disagrees')
    else:
        raise ValueError('thermal format must be corrections, gaussian or cf22d')
    values = {key: None if data.get(field) is None else number(data[field], field) for key, field in mapping.items()}
    for key, field in totals.items():
        total = data.get(field)
        if total is not None:
            number(total, field)
            if values['E'] is None or values[key] is None or abs(total - values['E'] - values[key]) > 2e-6:
                raise ValueError('thermal total/correction inconsistency: ' + key)
    if values['ZPE'] is not None and values['ZPE'] < 0:
        raise ValueError('ZPE cannot be negative')
    return values


def rrho_check(thermal, m):
    rrho = thermal['rrho']
    fields(rrho, ('frequencies_cm1', 'stationary_type', 'geometry_class', 'symmetry_number', 'frequency_scale'), 'rrho')
    integer(rrho.get('symmetry_number'), 'symmetry_number')
    scale = number(rrho.get('frequency_scale'), 'frequency_scale', True)
    frequencies = rrho.get('frequencies_cm1')
    if not isinstance(frequencies, list) or len(frequencies) > 1536:
        raise ValueError('complete vibrational frequencies required')
    frequencies = [number(number(v, 'frequency') * scale, 'scaled frequency') for v in frequencies]
    if m['coordinates'] is None:
        raise ValueError('RRHO requires geometry')
    n = len(m['atoms'])
    singular = np.linalg.svd(m['coordinates'] - m['coordinates'].mean(axis=0), compute_uv=False)
    linear = n > 1 and (n == 2 or singular[1] < max(singular[0], 1.) * 1e-7)
    geometry = 'atom' if n == 1 else 'linear' if linear else 'nonlinear'
    if rrho.get('geometry_class') != geometry:
        raise ValueError('RRHO geometry_class disagrees with coordinates')
    count = 0 if n == 1 else 3*n - (5 if linear else 6)
    if len(frequencies) != count or any(v == 0 for v in frequencies):
        raise ValueError('RRHO requires complete nonzero vibrational modes, excluding translation/rotation')
    negative = [v for v in frequencies if v < 0]
    kind = rrho.get('stationary_type')
    if kind not in ('minimum', 'transition_state') or len(negative) != (1 if kind == 'transition_state' else 0):
        raise ValueError('unstable-mode count disagrees with stationary_type')
    return [v for v in frequencies if v > 0], negative


def oscillator_entropy(frequency, temperature):
    """Molar harmonic oscillator entropy in J mol^-1 K^-1, stable at large x."""
    x = CM_K * frequency / temperature
    if x > 700:
        return 0.
    return R * (x / math.expm1(x) - math.log(-math.expm1(-x)))


def thermochemistry(spec):
    schema(spec, 'chemical-thermochemistry-input/1', ('electronic', 'thermal', 'conditions', 'composite', 'low_frequency_cutoff_cm1'))
    electronic = fields(spec.get('electronic'), ('material', 'energy_hartree', 'model', 'source_sha256'), 'electronic')
    m = material(electronic['material']); emodel = model(electronic['model']); source(electronic['source_sha256'])
    e = number(electronic.get('energy_hartree'), 'electronic energy')
    cond = fields(spec.get('conditions'), ('temperature_k', 'phase', 'standard_state'), 'conditions')
    temperature = number(cond.get('temperature_k'), 'temperature_k', True)
    standard(cond.get('standard_state'))
    if cond.get('phase') not in ('gas', 'solution') or (cond['phase'] == 'gas') != (emodel['solvent'] is None):
        raise ValueError('phase must agree with electronic solvent model')
    if type(spec.get('composite', False)) is not bool:
        raise ValueError('composite must be boolean')
    quantities = {'E': e, 'ZPE': None, 'E+ZPE': None, 'H': None, 'G': None}
    thermal = spec.get('thermal'); correction = None; compatibility = None; thermal_model = None; treatment = None
    if thermal is not None:
        fields(thermal, ('material', 'model', 'source_sha256', 'format', 'data', 'temperature_k', 'standard_state', 'rrho'), 'thermal')
        tm = material(thermal['material']); thermal_model = model(thermal['model']); source(thermal['source_sha256'])
        compatibility = same_geometry(m, tm)
        if thermal['temperature_k'] != temperature:
            raise ValueError('temperature change requires new RRHO thermochemistry; one-temperature totals cannot be extrapolated')
        standard(thermal['standard_state'])
        if (emodel != thermal_model or electronic['source_sha256'] != thermal['source_sha256']) and not spec.get('composite', False):
            raise ValueError('separate electronic/thermal sources require explicit composite=true')
        stable, unstable = rrho_check(thermal, tm)
        data = thermal_data(thermal)
        if electronic['source_sha256'] == thermal['source_sha256'] and (emodel != thermal_model or data['E'] is not None and abs(e - data['E']) > 2e-6):
            raise ValueError('same source electronic energy/model disagrees')
        quantities['ZPE'] = data['ZPE']
        for key in ('ZPE', 'H', 'G'):
            quantities['E+ZPE' if key == 'ZPE' else key] = None if data[key] is None else e + data[key]
        delta_std = standard_correction(thermal['standard_state'], cond['standard_state'], temperature)
        delta_low = 0.
        cutoff = spec.get('low_frequency_cutoff_cm1')
        if cutoff is not None:
            number(cutoff, 'low_frequency_cutoff_cm1', True)
            if quantities['G'] is None:
                raise ValueError('low-frequency correction requires an existing RRHO G correction')
            delta_low = temperature / HARTREE_J_MOL * math.fsum(oscillator_entropy(v, temperature) - oscillator_entropy(max(v, cutoff), temperature) for v in stable)
        if quantities['G'] is not None:
            quantities['G'] += delta_std + delta_low
        correction = {'standard_state_G_hartree': delta_std, 'low_frequency_G_hartree': delta_low,
                      'applied_to_G': quantities['G'] is not None, 'source_corrections_hartree': data}
        treatment = {k: v for k, v in thermal['rrho'].items() if k not in ('frequencies_cm1', 'symmetry_number', 'geometry_class', 'stationary_type')}
        treatment.update(low_frequency_method='entropy_floor' if cutoff is not None else 'none', cutoff_cm1=cutoff)
        compatibility['excluded_unstable_frequencies_cm1'] = unstable
    elif spec.get('low_frequency_cutoff_cm1') is not None or spec.get('composite', False):
        raise ValueError('thermal source required for composite/low-frequency processing')
    return finite_result({'schema_version': 'chemical-thermochemistry-result/1', 'request': spec, 'request_sha256': canonical(spec),
        'material': electronic['material'], 'unit': 'hartree', 'quantities': quantities, 'conditions': cond,
        'model_signature': {'electronic': emodel, 'thermal': thermal_model, 'treatment': treatment},
        'corrections': correction, 'compatibility': compatibility,
        'missing_quantities': [k for k, v in quantities.items() if v is None],
        'scope': 'Declared source bindings and RRHO data; no wavefunction, convergence, stationary-point or path certification. No additional solvation correction is added.'})
