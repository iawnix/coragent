"""Evidence contracts shared by checks; no reaction topology is imported."""
import hashlib
import json
import math
import re

import numpy as np

from analysis_material import numeric_array
from conformers import state_comparison
from material import object_fields


def content_digest(value):
    return 'sha256:' + hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def positive(value, name):
    if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
        raise ValueError(f'{name} must be finite and positive')
    return float(value)


def check(value, details=None):
    return {'verdict': 'inconclusive' if value is None else 'pass' if value else 'fail', 'details': details}


def report(kind, checks, **extra):
    verdicts = [v['verdict'] for v in checks.values()]
    return {'schema_version': 'chemical-evidence-check/1', 'kind': kind,
            'verdict': 'fail' if 'fail' in verdicts else 'inconclusive' if not verdicts or 'inconclusive' in verdicts else 'pass',
            'checks': checks, 'parsing': {'status': 'completed'}, **extra}


def common_checks(material, evidence, schema):
    if not isinstance(evidence, dict) or evidence.get('schema_version') != schema:
        raise ValueError(f'{schema} required')
    sources = evidence.get('sources')
    valid_sources = isinstance(sources, list) and bool(sources) and all(
        isinstance(s, dict) and isinstance(s.get('sha256'), str) and re.fullmatch(r'sha256:[0-9a-f]{64}', s['sha256'])
        and isinstance(s.get('kind'), str) and bool(s['kind']) for s in sources)
    calc = evidence.get('calculation')
    if not isinstance(calc, dict):
        raise ValueError('calculation object required')
    object_fields(calc, ('method', 'basis', 'charge', 'multiplicity', 'electronic_state', 'constraints', 'surface'), 'calculation')
    for key in ('method', 'basis'):
        if calc.get(key) is not None and (not isinstance(calc[key], str) or not calc[key].strip()):
            raise ValueError(f'{key} must be nonempty text or null')
    for key in ('charge', 'multiplicity'):
        if calc.get(key) is not None and (type(calc[key]) is not int or key == 'multiplicity' and calc[key] < 1):
            raise ValueError(f'invalid calculation {key}')
    state = calc.get('electronic_state', {'kind': 'unspecified'})
    if not isinstance(state, dict) or state.get('kind') not in {'ground', 'unspecified', 'excited', 'broken_symmetry'}:
        raise ValueError('invalid calculation electronic_state')
    compared = state_comparison(material['value'], {**calc, 'electronic_state': state})
    constraints = calc.get('constraints')
    if constraints is not None and not isinstance(constraints, list):
        raise ValueError('constraints must be an explicit list or null for unknown')
    checks = {
        'source_attribution': check(bool(valid_sources), 'Source hashes attribute supplied evidence; use Job/Artifact provenance to verify the derivation'),
        'material_binding': check(evidence.get('material_sha256') == material['sha256']),
        'atom_order': check(evidence.get('atom_ids') == material['ids']),
        'declared_state': check(False if compared['conflicts'] else None if compared['unknown'] else True, compared),
        'method_basis': check(True if calc.get('method') and calc.get('basis') else None),
    }
    scope = calc.get('surface') == 'single_surface' and state['kind'] == 'ground' and constraints == []
    return checks, scope


def unsupported(kind, checks):
    # A known unsupported surface or constraint does not refute its chemistry.
    return {'schema_version': 'chemical-evidence-check/1', 'kind': kind, 'verdict': 'inconclusive',
            'scientific_verdict': 'not_assessed', 'checks': checks, 'parsing': {'status': 'completed'},
            'scope': 'Only explicitly unconstrained, ground-state single-surface stationary/IRC evidence is assessed; unknown constraints, excited/crossing/barrierless studies need other criteria'}


def geometry_class(coordinates):
    n = len(coordinates)
    if n == 1:
        return 'atom', 0
    singular = np.linalg.svd(coordinates - coordinates.mean(axis=0), compute_uv=False)
    if singular[0] < 1e-8:
        return 'degenerate', None
    ratio = singular[1] / singular[0]
    if ratio < 1e-7:
        return 'linear', 3 * n - 5
    if ratio < 1e-4:
        return 'near_linear', None
    return 'nonlinear', 3 * n - 6


def stationary(material, evidence, *, kind='saddle', negative_threshold=20., near_zero=10.):
    if kind not in {'minimum', 'saddle'}:
        raise ValueError('kind must be minimum or saddle')
    positive(negative_threshold, 'negative_threshold'); positive(near_zero, 'near_zero')
    if near_zero > negative_threshold:
        raise ValueError('near_zero cannot exceed negative_threshold')
    checks, scope = common_checks(material, evidence, 'chemical-stationary-evidence/1')
    if not scope:
        return unsupported('stationary', checks)
    xyz = material['coordinates']
    if xyz is None or not len(xyz):
        checks['geometry'] = check(None, 'Supplied angstrom geometry required')
        return report('stationary', checks)
    supplied = evidence.get('coordinates')
    checks['geometry_binding'] = check(None if supplied is None else bool(np.max(np.abs(numeric_array(supplied, xyz.shape, 'coordinates') - xyz)) <= 1e-5))
    checks['coordinate_unit'] = check(evidence.get('coordinate_unit') == 'angstrom')
    termination = evidence.get('termination')
    checks['termination'] = check(True if termination == 'normal' else False if termination == 'error' else None)
    optimization = evidence.get('optimization') or {}
    if not isinstance(optimization, dict):
        raise ValueError('optimization must be an object')
    converged = optimization.get('converged')
    if converged is not None and type(converged) is not bool:
        raise ValueError('optimization.converged must be boolean or null')
    criteria = optimization.get('criteria', [])
    if not isinstance(criteria, list):
        raise ValueError('optimization.criteria must be a list')
    evaluated, seen = [], set()
    for row in criteria:
        object_fields(row, ('name', 'value', 'threshold', 'unit'), 'convergence criterion')
        name = row.get('name')
        if name not in {'max_gradient', 'rms_gradient', 'max_displacement', 'rms_displacement'} or name in seen:
            raise ValueError('unique supported convergence criterion names required')
        seen.add(name)
        threshold = positive(row.get('threshold'), 'convergence threshold')
        expected_unit = 'hartree/bohr' if name.endswith('gradient') else 'bohr'
        value = row.get('value')
        if type(value) not in (int, float) or not math.isfinite(value) or value < 0 or row.get('unit') != expected_unit:
            raise ValueError('convergence values require nonnegative numbers with declared atomic units')
        evaluated.append({**row, 'satisfied': value <= threshold})
    enough = {'max_gradient', 'rms_gradient'} <= seen
    checks['optimization'] = check(False if converged is False or any(not v['satisfied'] for v in evaluated)
                                   else True if converged is True and enough else None, evaluated)
    category, dof = geometry_class(xyz)
    frequencies = evidence.get('frequencies_cm-1')
    f = None
    if frequencies is not None:
        if not isinstance(frequencies, list):
            raise ValueError('frequencies_cm-1 must be a list or null')
        f = numeric_array(frequencies, (len(frequencies),), 'frequencies')
    checks['vibrational_degrees'] = check(None if dof is None or f is None else len(f) == dof,
                                        {'geometry_class': category, 'expected': dof, 'actual': None if f is None else len(f),
                                         'spectrum': 'Vibrational modes only, with overall translations/rotations projected out'})
    negative = [] if f is None else np.flatnonzero(f < -negative_threshold).tolist()
    small_negative = [] if f is None else np.flatnonzero((f < 0) & (f >= -negative_threshold)).tolist()
    flat = [] if f is None else np.flatnonzero(np.abs(f) <= near_zero).tolist()
    checks['frequency_signature'] = check(None if f is None else len(negative) == (1 if kind == 'saddle' else 0),
        {'all_cm-1': frequencies, 'significant_negative_indexes': negative, 'small_negative_indexes': small_negative,
         'near_zero_indexes': flat, 'negative_threshold_cm-1': negative_threshold, 'near_zero_cm-1': near_zero})
    checks['unresolved_small_modes'] = check(None if f is None or small_negative or flat else True,
                                            'Small negative and flat modes require follow-up; none are silently discarded')
    if kind == 'saddle':
        modes = evidence.get('normal_modes')
        usable = None
        if modes is not None and f is not None:
            if len(f) == 0 and modes == []:
                usable = False
            else:
                vectors = numeric_array(modes, (len(f), len(xyz), 3), 'normal_modes')
                usable = (evidence.get('mode_representation') == 'cartesian' and len(negative) == 1
                          and np.linalg.norm(vectors[negative[0]]) > 1e-12)
        checks['imaginary_vector_available'] = check(usable)
    return report('stationary', checks, requested_kind=kind,
                  scope='Stationarity and harmonic signature under supplied evidence; excludes intended mode character, IRC connection, wavefunction stability and global mechanism completeness')
