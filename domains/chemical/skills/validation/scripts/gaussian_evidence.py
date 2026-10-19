"""Adapt a selected Gaussian log section without importing specialized validators."""
import re
from pathlib import Path

from rdkit import Chem

from gaussian_io import electronic_energy_evidence, final_geometry, parse_irc_log, parse_log, select_job_section
from material import digest


def gaussian_evidence(material, path, *, kind='stationary', section_index=None, constraints='unknown'):
    if constraints not in {'none', 'unknown'} or kind not in {'stationary', 'irc'}:
        raise ValueError('unsupported Gaussian evidence options')
    raw = Path(path).read_bytes()
    if len(raw) > 64 * 1024 * 1024:
        raise ValueError('Gaussian log exceeds 64 MiB')
    section = select_job_section(raw.decode(errors='replace').splitlines(), section_index)
    lines = section['lines']; text = '\n'.join(lines)
    parsed = parse_log(Path(path), section_index=section_index) if kind == 'stationary' else parse_irc_log(Path(path), section_index=section_index)
    summary = parsed['summary']; route = summary.get('gaussian_route') or ''
    energy = electronic_energy_evidence(lines, route)['energy_evidence']
    method = energy.get('requested_method')
    pairs = re.findall(r'(?:^|\s)([a-zA-Z][^\s/]*)\s*/\s*([^\s]+)', route)
    basis = pairs[0][1].lower() if len(pairs) == 1 else None
    states = {(int(c), int(m)) for c, m in re.findall(r'Charge\s*=\s*(-?\d+)\s+Multiplicity\s*=\s*(\d+)', text, re.I)}
    charge, multiplicity = next(iter(states)) if len(states) == 1 else (None, None)
    # Known restriction markers veto a declaration of no constraints. Absence of
    # markers alone never proves an unconstrained input.
    restricted = bool(re.search(r'\b(?:modredundant|readfreeze|readopt|addredundant|freeze|frozen|constraints?)\b', text, re.I))
    calc = {'method': method, 'basis': basis, 'charge': charge, 'multiplicity': multiplicity,
            'electronic_state': material['value']['electronic_state'],
            'surface': 'single_surface' if energy['status'] == 'supported' else 'unassessed',
            'constraints': ['restriction_marker_in_log'] if restricted else [] if constraints == 'none' else None}
    elements = [a['element'] for a in material['atoms']]
    atoms = parsed['atoms']
    common = {'material_sha256': material['sha256'], 'atom_ids': material['ids'] if [a[0] for a in atoms] == elements else [],
              'calculation': calc, 'coordinate_unit': 'angstrom',
              'termination': 'error' if summary['error_termination'] else 'normal' if summary['normal_termination'] else 'unknown',
              'sources': [{'kind': 'gaussian_log', 'sha256': digest(raw), 'section_index': section['index']}],
              'adapter': {'name': 'gaussian_evidence/1', 'energy_scope': energy,
                          'state_scope': 'State kind and atom IDs come from the supplied material declaration; charge/multiplicity come from the log. No state tracking or same-element trajectory identity is certified',
                          'constraints_declaration': constraints}}
    # Isotope masses are not checked by this parser. Do not silently certify a
    # frequency signature calculated with different masses.
    if any(a.get('isotope') is not None for a in material['atoms']):
        calc['surface'] = 'unassessed'
        common['adapter']['isotope_scope'] = 'Explicit isotope masses require a method-specific evidence adapter'
    if kind == 'irc':
        first = next((i for i, line in enumerate(lines) if re.search(r'Point Number:\s*\d+', line)), len(lines))
        origin = final_geometry(lines[:first])
        if origin and [a[0] for a in origin] != elements:
            common['atom_ids'] = []
        for point in parsed['points']:
            if [a[0] for a in point['atoms']] != elements:
                common['atom_ids'] = []
        return {**common, 'schema_version': 'chemical-irc-evidence/1', 'direction': summary['direction'],
                'origin_coordinates': [list(a[1:]) for a in origin] if origin else None,
                'complete': summary['path_complete_marker'], 'max_points_reached': summary['max_points_reached'],
                'points': [{'index': point['point_number'], 'coordinates': [list(a[1:]) for a in point['atoms']],
                            'energy_hartree': point['electronic_energy_hartree']} for point in parsed['points']],
                'endpoint': None}
    aliases = {'Maximum Force': 'max_gradient', 'RMS Force': 'rms_gradient',
               'Maximum Displacement': 'max_displacement', 'RMS Displacement': 'rms_displacement'}
    criteria = []
    for name, row in summary['force_convergence'].items():
        if name in aliases and type(row['value']) in (int, float) and type(row['threshold']) in (int, float):
            criteria.append({'name': aliases[name], 'value': row['value'], 'threshold': row['threshold'],
                             'unit': 'hartree/bohr' if 'Force' in name else 'bohr'})
    complete = len(criteria) == 4
    mode_rows = parsed['normal_modes']
    numbers = [Chem.GetPeriodicTable().GetAtomicNumber(e) for e in elements]
    matching = (len(mode_rows) == len(parsed['frequencies']) and all(row['atomic_numbers'] == numbers for row in mode_rows)
                and [row['frequency_cm-1'] for row in mode_rows] == parsed['frequencies'])
    return {**common, 'schema_version': 'chemical-stationary-evidence/1',
            'coordinates': [list(a[1:]) for a in atoms] if atoms else None,
            'optimization': {'converged': summary['optimization_completed'] if complete else None,
                             'completion_reason': summary['optimization_completion_reason'],
                             'criteria': criteria},
            'frequencies_cm-1': parsed['frequencies'] or None, 'mode_representation': 'cartesian',
            'normal_modes': [row['displacements'] for row in mode_rows] if matching and mode_rows else None}
