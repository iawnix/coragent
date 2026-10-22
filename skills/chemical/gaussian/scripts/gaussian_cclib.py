"""cclib numerical adapter. Solver events and chemical verdicts stay separate.

Parse only the selected calculation section, never a concatenated file. Partial
or unsupported logs retain the bounded text parser's observations with an
explicit fallback status. Disagreement is reviewable, not a reason to rerun a
calculation automatically. No cclib success/optdone flag is a scientific gate.
"""
import io
import logging


def reconcile_numerics(lines, parsed):
    # Do not leave partially replaced values behind if an upstream parser returns
    # malformed arrays. The bounded text observations remain inspectable.
    import copy
    original = copy.deepcopy(parsed)
    try:
        return _reconcile_numerics(lines, parsed)
    except (ValueError, TypeError, IndexError, KeyError, AttributeError, ArithmeticError) as exc:
        original["summary"]["numerical_parser"] = {
            "backend": "cclib", "status": "conflict", "fields": [],
            "conflicts": ["malformed_numerical_evidence"], "exception_type": type(exc).__name__,
            "fallback": "gaussian_text", "next_action": "review_source_and_parser; do_not_automatically_recalculate"}
        return original


def _reconcile_numerics(lines, parsed):
    summary = parsed['summary']
    record = {'backend': 'cclib', 'status': 'unavailable', 'fields': [], 'conflicts': [],
              'fallback': 'gaussian_text', 'scope': 'Numerical extraction only; phase and connectivity checks are independent'}
    summary['numerical_parser'] = record
    try:
        import cclib
        import numpy as np
        from cclib.parser import Gaussian
        from cclib.parser.utils import convertor
    except ImportError:
        return parsed
    record['version'] = cclib.__version__
    try:
        data = Gaussian(io.StringIO('\n'.join(lines)), loglevel=logging.CRITICAL,
                        logstream=io.StringIO()).parse()
    except Exception as exc:
        record.update(status='fallback', reason='cclib_could_not_parse_selected_section', exception_type=type(exc).__name__)
        return parsed
    record['status'] = 'completed'

    def scalar(attribute, field, unit=None):
        value = getattr(data, attribute, None)
        if value is None:
            return
        if attribute == 'scfenergies':
            value = value[-1] if len(value) else None
        if value is None:
            return
        value = float(convertor(value, unit, 'hartree') if unit else value)
        reference = summary.get(field)
        # Never restore an invalid/missing final record or an unsupported target.
        if reference is None:
            return
        if not np.isfinite(value) or abs(value - reference) > 2e-6:
            record['conflicts'].append(field)
            return
        summary[field] = value
        record['fields'].append(field)

    scalar('scfenergies', 'reference_scf_energy_hartree', 'eV')
    if summary['energy_evidence']['status'] == 'supported':
        scalar('scfenergies', 'electronic_energy_hartree', 'eV')
        scalar('freeenergy', 'electronic_plus_thermal_free_energy_hartree')
        scalar('enthalpy', 'electronic_plus_thermal_enthalpy_hartree')
    frequencies = np.asarray(getattr(data, 'vibfreqs', []), dtype=float)
    expected = np.asarray(parsed['frequencies'], dtype=float)
    matching_freqs = (bool(len(expected)) and frequencies.shape == expected.shape
                      and np.isfinite(frequencies).all() and np.allclose(frequencies, expected, atol=.001, rtol=0))
    if len(expected) and len(frequencies) and not matching_freqs:
        record['conflicts'].append('frequencies')
    if matching_freqs:
        parsed['frequencies'] = frequencies.tolist()
        record['fields'].append('frequencies')
    # Keep the original atom order/frame and rotate cclib's Cartesian modes
    # into it. Reflections and same-element permutations are never allowed.
    atoms = parsed['atoms']
    coords = np.asarray(getattr(data, 'atomcoords', []), dtype=float)
    numbers = getattr(data, 'atomnos', [])
    if atoms and coords.size:
        from xyz import PERIODIC_TABLE
        expected_numbers = [PERIODIC_TABLE.index(a[0]) if isinstance(PERIODIC_TABLE, list)
                            else next(k for k, v in PERIODIC_TABLE.items() if v == a[0]) for a in atoms]
        if list(numbers) != expected_numbers or coords[-1].shape != (len(atoms), 3) or not np.isfinite(coords[-1]).all():
            record['conflicts'].append('atom_identity')
        else:
            target = np.asarray([a[1:] for a in atoms], dtype=float)
            x, y = coords[-1] - coords[-1].mean(0), target - target.mean(0)
            u, _, vt = np.linalg.svd(x.T @ y)
            rotation = u @ np.diag([1., 1., np.linalg.det(u @ vt)]) @ vt
            if np.max(np.abs(x @ rotation - y)) > 1e-5:
                record['conflicts'].append('final_geometry')
            else:
                record['fields'].append('coordinates_verified')
                modes = np.asarray(getattr(data, 'vibdisps', []), dtype=float)
                if matching_freqs and modes.shape == (len(expected), len(atoms), 3) and np.isfinite(modes).all():
                    parsed['normal_modes'] = [{'frequency_cm-1': float(f), 'atomic_numbers': list(map(int, numbers)),
                        'displacements': (v @ rotation).tolist()} for f, v in zip(frequencies, modes)]
                    record['fields'].append('normal_modes_cartesian')
    if record['conflicts']:
        record['status'] = 'conflict'
        record['next_action'] = 'review_source_and_parser; do_not_automatically_recalculate'
    record['fallback'] = 'gaussian_text_for_remaining_fields'
    return parsed
