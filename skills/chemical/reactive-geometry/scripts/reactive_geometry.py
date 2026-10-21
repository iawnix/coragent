"""Evidence-directed reactive geometry editing, with final-geometry rejection gates."""
from pathlib import Path
import itertools
import json
import sys

SKILLS = Path(__file__).resolve().parents[2]
for part in ('_shared', 'material-preparation/scripts/materials', 'material-preparation/scripts/reaction',
             'crest/scripts', 'candidate-generation/scripts/path'):
    sys.path.insert(0, str(SKILLS / part))

import numpy as np
from rdkit import Chem
from analysis_material import read_json
from conformers import internal_value
from ensemble_material import canonical, xyz_text
from material import digest
from path_contract import candidate_material
from geometry_contract import validate
from geometry_ops import apply, frame, unit


def diagnostics(xyz, original, reference, edges, changes, center, sampling, targets, checks):
    ids = reference['ids']; reasons = []; residuals = []; measured = []
    distances = np.linalg.norm(xyz[:, None]-xyz[None, :], axis=2)
    radii = np.array([Chem.GetPeriodicTable().GetRcovalent(a['element']) for a in reference['atoms']])
    if not np.isfinite(xyz).all(): return {'reasons': ['nonfinite_geometry']}
    clashes = []
    # 1-3 contacts are not nonbonded clashes, but no pair is exempt from collapse.
    bonded = [set() for _ in ids]
    for a, b in edges: bonded[a].add(b); bonded[b].add(a)
    for a in range(len(ids)):
        for b in range(a):
            pair = (b, a); d = distances[a, b]; radius_sum = radii[a]+radii[b]
            collapse = d < max(.1, .5*radius_sum)
            exempt = pair in edges or pair in changes or bool(bonded[a] & bonded[b])
            if collapse or (not exempt and d < sampling['clash_scale']*radius_sum):
                clashes.append({'atoms': [ids[b], ids[a]], 'distance': float(d), 'kind': 'collapse' if collapse else 'short_contact'})
    if clashes: reasons.append('atomic_clash')
    distorted = []
    for a, b in edges:
        if (a, b) in changes: continue
        before = np.linalg.norm(original[a]-original[b]); delta = abs(distances[a, b]-before)
        if delta > sampling['protected_bond_tolerance']:
            distorted.append({'atoms': [ids[a], ids[b]], 'change_angstrom': float(delta)})
    if distorted: reasons.append('protected_bond_distortion')
    stereo = []
    for a in reference['mol'].GetAtoms():
        index = a.GetIdx()
        if index in center or a.GetChiralTag() == Chem.ChiralType.CHI_UNSPECIFIED: continue
        neighbors = [n.GetIdx() for n in a.GetNeighbors()]
        if len(neighbors) != 4: continue
        # Preserve the source geometry's handedness outside the declared reaction center.
        def volume(coords):
            p = coords[neighbors]; return np.linalg.det(p[:3]-p[3])
        old, new = volume(original), volume(xyz)
        if abs(old) > 1e-5 and (old*new <= 0 or abs(new) < 1e-5): stereo.append(ids[index])
    if stereo: reasons.append('protected_stereocenter_changed')
    for atoms, target, tolerance in targets:
        actual = internal_value(xyz[[ids.index(a) for a in atoms]])
        error = None if actual is None else abs((actual-target+180)%360-180) if len(atoms) == 4 else abs(actual-target)
        measured.append({'atoms': atoms, 'target': target, 'actual': actual, 'tolerance': tolerance})
        if error is None or error > tolerance: reasons.append('final_target_not_met')
        if error is not None: residuals.append(error/tolerance)
    for check in checks:
        actual = internal_value(xyz[[ids.index(a) for a in check['atoms']]])
        measured.append({**check, 'actual': actual})
        if actual is None or not check['minimum'] <= actual <= check['maximum']: reasons.append('final_check_not_met')
    return {'reasons': sorted(set(reasons)), 'coordinates': measured, 'clashes': clashes,
            'protected_bond_distortions': distorted, 'protected_stereocenters_changed': stereo,
            'target_error_score': float(np.mean(np.square(residuals))) if residuals else None,
            'coordinate_rms_change_angstrom': float(np.sqrt(np.mean(np.sum((xyz-original)**2, axis=1)))),
            'minimum_pair_distance_angstrom': float(distances[np.triu_indices(len(ids), 1)].min())}


def generate(spec):
    source, reference, groups, edges, changes, center, sampling, hypotheses = validate(spec)
    original = source['coordinates']; ids = source['ids']; rng = np.random.default_rng(sampling['seed'])
    candidates = []; rejected = []; pending = []
    for hypothesis, options in hypotheses:
        choices = itertools.product(*options)
        # With a cone, repeat the bounded combination cycle with fresh directions.
        if any(op.get('cone_degrees', 0) > 0 for op in hypothesis['operations']):
            choices = itertools.chain.from_iterable(itertools.product(*options) for _ in range(sampling['count']))
        pending.append((hypothesis, iter(choices)))
    attempts = 0
    while pending and attempts < sampling['count']:
        next_round = []
        for hypothesis, choices in pending:
            if attempts >= sampling['count']: next_round.append((hypothesis, choices)); continue
            choice = next(choices, None)
            if choice is None: continue
            next_round.append((hypothesis, choices)); attempts += 1
            xyz = original.copy(); operations = []; targets = []
            record = {'id': f'candidate-{attempts:04d}', 'hypothesis_id': hypothesis['id'],
                      'note': hypothesis['note'], 'source_refs': hypothesis['source_refs'], 'operations': operations,
                      'validated_ts': False, 'preoptimization': 'not_run'}
            failure = None; local_delta = np.zeros_like(xyz)
            try:
                for op, selected in zip(hypothesis['operations'], choice):
                    before = xyz.copy()
                    operations.append(apply(op, xyz, ids, groups, selected, rng))
                    if op['kind'] != 'place': local_delta += xyz-before
                    if op['kind'] != 'displace':
                        targets.append((op['atoms'], selected[0] if op['kind'] == 'place' else selected,
                                        op.get('tolerance', .03 if len(op['atoms']) == 2 else 3.)))
                if np.linalg.norm(local_delta, axis=1).max() > sampling['max_local_displacement']:
                    failure = 'excessive_local_displacement'
            except ValueError as exc:
                failure = str(exc)
            report = diagnostics(xyz, original, reference, edges, changes, center, sampling, targets, hypothesis.get('checks', []))
            report['approach_angles'] = []
            for op, trace in zip(hypothesis['operations'], operations):
                if op['kind'] != 'place': continue
                a, b = [ids.index(i) for i in op['atoms']]
                try:
                    expected = np.asarray(trace['direction'])
                    angle = float(np.degrees(np.arccos(np.clip(unit(xyz[b]-xyz[a]) @ expected, -1, 1))))
                    mobile_angle = None
                    if 'mobile_direction' in op:
                        mobile_angle = float(np.degrees(np.arccos(np.clip(frame(op['mobile_direction'], xyz, ids) @ -expected, -1, 1))))
                    tolerance = op.get('direction_tolerance_degrees', 3.)
                    report['approach_angles'].append({'atoms': op['atoms'], 'error_degrees': angle,
                        'mobile_error_degrees': mobile_angle, 'tolerance_degrees': tolerance})
                    if angle > tolerance or (mobile_angle is not None and mobile_angle > tolerance):
                        report['reasons'].append('final_approach_direction_not_met')
                except ValueError:
                    report['reasons'].append('undefined_final_approach_direction')
            if failure: report['reasons'].append(failure)
            record.update(coordinates=xyz.tolist(), atom_ids=ids, diagnostics=report)
            if not report['reasons']:
                # Fixed correspondence preserves evidence binding; no symmetry remapping here.
                for previous in candidates:
                    if np.max(np.abs(np.array(previous['coordinates'])-xyz)) < 1e-6:
                        report['reasons'].append('duplicate_geometry'); record['duplicate_of'] = previous['id']; break
            (rejected if report['reasons'] else candidates).append(record)
        pending = next_round
    # Geometry residual is not energy or a success probability. Keep ties in generation order.
    candidates.sort(key=lambda r: (r['diagnostics']['target_error_score'] is None, r['diagnostics']['target_error_score'] or 0))
    for rank, row in enumerate(candidates, 1):
        row['geometry_rank'] = rank
        row['material'] = candidate_material(reference, np.asarray(row['coordinates']), {
            'operation': 'reactive_geometry_edit', 'input_sha256': canonical(spec), 'hypothesis_id': row['hypothesis_id'],
            'source_material_sha256': source['sha256'],
            'source_refs': row['source_refs'], 'note': row['note'], 'operations': row['operations'],
            'reference_material_sha256': reference['sha256']})
    unvisited = [hyp['id'] for hyp, choices in pending if next(choices, None) is not None]
    return {'schema_version': 'chemical-reactive-geometry-result/1', 'input_sha256': canonical(spec),
            'material_sha256': source['sha256'], 'reference_material_sha256': reference['sha256'],
            'source_material': source['value'], 'reference_material': reference['value'],
            'bond_changes': spec['bond_changes'], 'edit_hypotheses': spec['edit_hypotheses'], 'sampling': sampling,
            'candidates': candidates, 'rejected': rejected,
            'status': 'candidates_generated' if candidates else 'no_candidates',
            'summary': {'attempted': attempts, 'accepted': len(candidates), 'rejected': len(rejected),
                        'enumeration_complete': not unvisited, 'unexplored_hypotheses': unvisited},
            'scope': 'Explicit local frames and coordinate edits, not automatic mechanisms or electronic-structure analysis. '
                     'Geometric checks are relative to source/reference, not absolute identity or minimum certification. '
                     'No physical optimization or energy ranking. Candidates need solver refinement, frequencies and IRC.'}


def run(input_path, output_dir):
    spec, sha = read_json(input_path)
    result = generate(spec)  # Invalid inputs produce no output directory.
    output = Path(output_dir)
    if output.exists() and (not output.is_dir() or any(output.iterdir())): raise ValueError('output directory must be new or empty')
    output.mkdir(parents=True, exist_ok=True)
    def write(path, value): path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+'\n')
    write(output/'input.json', spec)
    for collection in ('candidates', 'rejected'):
        for row in result[collection]:
            folder = output/collection/row['id']; folder.mkdir(parents=True)
            xyz = xyz_text(result['source_material']['atoms'], row['coordinates'], 'Reactive geometry seed; validated_ts=false')
            (folder/'geometry.xyz').write_text(xyz)
            row['xyz'] = {'path': f'{collection}/{row["id"]}/geometry.xyz', 'sha256': digest(xyz.encode())}
            if 'material' in row: write(folder/'material.json', row['material'])
    result['input_file_sha256'] = sha
    write(output/'result.json', result)
    return result


if __name__ == '__main__':
    from reactive_cli import parse_arguments
    args = parse_arguments()
    result = run(args.input, args.output_dir)
    raise SystemExit(0 if result['candidates'] else 1)
