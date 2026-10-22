"""Prepare source-bound local probes; assess optimized endpoints without claiming IRC."""
import json
import re
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
for part in ('_shared', 'gaussian/scripts', 'material-preparation/scripts/materials',
             'material-preparation/scripts/reaction', 'material-preparation/scripts/geometry',
             'material-preparation/scripts/tensor'):
    sys.path.insert(0, str(ROOT / part))

import numpy as np
from analysis_material import read_material, read_json, numeric_array
from check_common import check, report, content_digest
from mode_check import mode_check
from irc_check import endpoint_checks, aligned_rmsd
from gaussian_evidence import gaussian_evidence
from gaussian_io import write_gjf, write_xyz
from geometry_safety import assess, require_safe
from material import digest
from connectivity_cli import parse_arguments


def probe_geometries(material, evidence, coordinates, amplitude):
    if type(amplitude) not in (int, float) or not np.isfinite(amplitude) or not 0 < amplitude <= .2:
        raise ValueError('amplitude must be finite and in (0, 0.2] angstrom')
    mode = mode_check(material, evidence, coordinates)
    if mode['verdict'] != 'pass':
        raise ValueError('Source must pass stationary, geometry binding and target-mode checks')
    vector = np.asarray(evidence['normal_modes'][mode['mode_index']], dtype=float)
    vector /= np.max(np.linalg.norm(vector, axis=1))
    return {sign: material['coordinates'] + factor * amplitude * vector
            for sign, factor in [('plus', 1), ('minus', -1)]}, mode


def prepare_inputs(material, evidence, coordinates, output, *, amplitudes=(.05, .1),
                   threads=1, memory_mb=2000, max_points=20, step_size=5):
    if type(threads) is not int or threads < 1 or type(memory_mb) is not int or memory_mb < 1:
        raise ValueError('positive integer resources required')
    if type(max_points) is not int or not 2 <= max_points <= 500:
        raise ValueError('max_points must be in 2..500')
    if type(step_size) is not int or step_size == 0:
        raise ValueError('Gaussian StepSize must be a nonzero integer')
    if not 1 <= len(amplitudes) <= 3 or len(set(amplitudes)) != len(amplitudes):
        raise ValueError('one to three distinct amplitudes required')
    probes = [probe_geometries(material, evidence, coordinates, a) for a in amplitudes]
    calc = evidence['calculation']
    route = evidence.get('adapter', {}).get('gaussian_route', '')
    if (calc.get('basis', '').lower() in {'gen', 'genecp', 'chkbasis'}
            or re.search(r'\b(?:scrf|empiricaldispersion|pseudo|iop|field|counterpoise|oniom|external)\b', route, re.I)):
        raise ValueError('Automatic probes require a self-contained method/basis; additional model settings need explicit bound input support')
    if not all(isinstance(calc.get(k), str) and re.fullmatch(r'[A-Za-z0-9+*(),._-]+', calc[k]) for k in ('method', 'basis')):
        raise ValueError('single Gaussian method/basis tokens required')
    output = Path(output)
    if output.exists() and any(output.iterdir()):
        raise ValueError('output directory must be empty')
    elements = [a['element'] for a in material['atoms']]
    jobs = []
    for amplitude, (geometries, _) in zip(amplitudes, probes):
        for sign, xyz in geometries.items():
            require_safe(assess(elements, xyz.tolist(), profile='ts_candidate'))
            jobs.append((f'probe_{amplitude:g}_{sign}', xyz, 'Opt=(Tight,MaxCycles=100) Freq',
                         {'kind': 'mode_displacement', 'direction': sign, 'amplitude_angstrom': amplitude}))
    for direction in ('forward', 'reverse'):
        jobs.append((f'irc_{direction}', material['coordinates'],
                     f'IRC=({direction.capitalize()},CalcFC,MaxPoints={max_points},StepSize={step_size})',
                     {'kind': 'irc', 'direction': direction, 'max_points': max_points}))
    output.mkdir(parents=True, exist_ok=True)
    source = {'schema_version': 'chemical-ts-source/1', 'material': material['value'],
              'material_sha256': material['sha256'], 'atom_ids': material['ids'], 'elements': elements,
              'coordinates': material['coordinates'].tolist(), 'calculation': calc,
              'stationary_evidence': evidence, 'mode_coordinates': coordinates, 'mode_check': probes[0][1],
              'source_kind': 'optimized_saddle', 'inputs': []}
    for name, xyz, task, details in jobs:
        file = output / (name + '.gjf')
        route = f"#p {calc['method']}/{calc['basis']} {task} SCF=Tight Int=UltraFine NoSymm"
        atoms = [(element, *map(float, point)) for element, point in zip(elements, xyz)]
        write_gjf(file, 'coragent-ts-binding=ts_source.json', atoms, route, calc['charge'], calc['multiplicity'],
                  threads, f'{memory_mb}MB', name + '.chk', [])
        source['inputs'].append({**details, 'path': file.name, 'sha256': digest(file.read_bytes()),
            'checkpoint': name + '.chk', 'collect': ['results/' + name + '.chk'], 'start_coordinates': xyz.tolist()})
    source['binding_sha256'] = content_digest(source)
    (output / 'ts_source.json').write_text(json.dumps(source, indent=2, allow_nan=False) + '\n')
    write_xyz(output / 'ts.xyz', [(e, *x) for e, x in zip(elements, material['coordinates'])], 'Validated source saddle')
    result = {'schema_version': 'chemical-connectivity-inputs/1', 'source': 'ts_source.json',
              'source_sha256': digest((output / 'ts_source.json').read_bytes()), 'inputs': source['inputs'],
              'evidence': 'prepared_inputs_only', 'normalization': 'maximum_atom_displacement_angstrom',
              'retry_policy': {'enforcement': 'workflow_guidance; no automatic resubmission',
                 'max_attempts_per_branch': 3, 'identical_input_retry': 'requires_external_failure_reason',
                 'syntax_error': 'correct_input', 'parser_conflict': 'review_source',
                 'max_points': 'inspect_endpoint_then_relax_before_extending',
                 'same_basin_or_amplitude_dependence': 'short_irc_then_endpoint_optimization'},
              'limitations': ['Mode displacements are not IRC points.',
                 'CalcFC uses explicit verified TS coordinates; checkpoint Hessian reuse requires separately bound checkpoint evidence.',
                 'Stage ts_source.json with each GJF. Collection names are derived from the same checkpoint declaration.']}
    (output / 'connectivity_inputs.json').write_text(json.dumps(result, indent=2, allow_nan=False) + '\n')
    return result


def displacement_check(material, evidence, coordinates, study, targets):
    if study.get('schema_version') != 'chemical-displacement-study/1':
        raise ValueError('chemical-displacement-study/1 required')
    branches = study.get('branches')
    if not isinstance(branches, list) or not 2 <= len(branches) <= 6:
        raise ValueError('two to six displacement endpoint branches required')
    checks, details, assignments = {}, [], {}
    for i, branch in enumerate(branches):
        amplitude, sign = branch.get('amplitude_angstrom'), branch.get('direction')
        if sign not in ('plus', 'minus'):
            raise ValueError('displacement direction must be plus or minus')
        key = (amplitude, sign)
        if key in assignments:
            raise ValueError('duplicate displacement branch')
        geometries, mode = probe_geometries(material, evidence, coordinates, amplitude)
        current, assignment, detail = endpoint_checks(material, evidence, branch.get('endpoint'), geometries[sign], targets)
        minimum = (branch.get('endpoint') or {}).get('minimum_evidence') or {}
        start = (minimum.get('optimization') or {}).get('start_coordinates')
        current['displacement_origin'] = check(None if start is None else
            aligned_rmsd(geometries[sign], numeric_array(start, geometries[sign].shape, 'start_coordinates')) <= 1e-5,
            'Optimization must start at the recomputed signed mode displacement')
        checks.update({f'branch_{i+1}_{k}': v for k, v in current.items()})
        assignments[key] = assignment
        details.append({'direction': sign, 'amplitude_angstrom': amplitude, 'endpoint': detail})
    amplitudes = sorted({key[0] for key in assignments})
    pairs = [[assignments.get((a, sign)) for sign in ('plus', 'minus')] for a in amplitudes]
    opposite = all(None not in pair and sorted(pair) == [0, 1] for pair in pairs)
    checks['both_sides_each_amplitude'] = check(all((a, s) in assignments for a in amplitudes for s in ('plus', 'minus')))
    # Same-basin descent is unresolved, not chemical proof that a TS is wrong.
    checks['opposite_basins'] = check(True if opposite else None, pairs)
    checks['amplitude_consistency'] = check(True if opposite and all(p == pairs[0] for p in pairs) else None, pairs)
    return report('mode_displacement_connectivity', checks, paths=details, mode=mode,
        evidence_level='mode_displacement_endpoint_support', full_irc_complete=False,
        amplitude_sensitivity_assessed=len(amplitudes) > 1,
        next_action='short_irc_for_key_path' if opposite else 'inspect_mode_amplitude_then_short_irc',
        scope='Optimized basin support only; ordinary optimization can bypass shallow intermediates and is not an IRC')


def main():
    args = parse_arguments()
    material = read_material(args.material)
    coordinates, _ = read_json(args.coordinates)
    if args.action == 'prepare':
        evidence = gaussian_evidence(material, args.log, constraints='none', section_index=args.section_index)
        result = prepare_inputs(material, evidence, coordinates, args.output_dir, amplitudes=args.amplitudes,
            threads=args.threads, memory_mb=args.memory_mb, max_points=args.max_points, step_size=args.step_size)
    else:
        evidence, _ = read_json(args.evidence)
        study, _ = read_json(args.study)
        result = displacement_check(material, evidence, coordinates, study,
                                    [read_material(args.reactant), read_material(args.product)])
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open('x') as handle:
            handle.write(json.dumps(result, indent=2, allow_nan=False) + '\n')
    print(json.dumps(result, allow_nan=False))


if __name__ == '__main__':
    main()
