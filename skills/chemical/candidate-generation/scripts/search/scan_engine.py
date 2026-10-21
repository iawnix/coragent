"""Bounded independent-point internal-coordinate scans with terminal-result continuation."""
import copy
import hashlib
import itertools
import math
from pathlib import Path
import subprocess

import numpy as np

from conformers import internal_value
from ensemble_material import canonical, checked, xyz_text
from material import object_fields
from path_contract import candidate_material, integer, material, positive, settings
from path_process import write_json


def axes_for(value, m):
    if not isinstance(value, list) or not 1 <= len(value) <= 2: raise ValueError('one or two scan axes required')
    axes = []; keys = set()
    for axis in value:
        object_fields(axis, ('kind', 'atoms', 'values', 'unit', 'tolerance'), 'scan axis')
        kind = axis.get('kind'); n = {'distance': 2, 'angle': 3, 'dihedral': 4}.get(kind)
        ids = axis.get('atoms')
        if not n or not isinstance(ids, list) or len(ids) != n or len(set(ids)) != n or any(i not in m['ids'] for i in ids): raise ValueError('axis needs distinct existing atom IDs')
        indexes = [m['ids'].index(i) for i in ids]; key = min(tuple(indexes), tuple(reversed(indexes)))
        if key in keys: raise ValueError('duplicate scan axis')
        keys.add(key)
        if axis.get('unit') != ('angstrom' if n == 2 else 'degree'): raise ValueError('axis unit must be angstrom or degree')
        positive(axis.get('tolerance'), 'axis tolerance')
        values = axis.get('values')
        if not isinstance(values, list) or not 1 <= len(values) <= 256 or any(type(v) not in (int,float) or not math.isfinite(v) for v in values): raise ValueError('finite bounded axis values required')
        if any((n == 2 and v <= .1) or (n == 3 and not 0 < v < 180) or (n == 4 and not -180 <= v <= 180) for v in values): raise ValueError('axis values outside supported ranges')
        if len(set(values)) != len(values): raise ValueError('duplicate scan values')
        if internal_value(m['coordinates'][indexes]) is None: raise ValueError('undefined initial internal coordinate')
        axes.append({**axis, 'indexes': indexes})
    if math.prod(len(a['values']) for a in axes) > 256: raise ValueError('scan grid exceeds 256 points')
    return axes


def measure(axes, xyz, targets):
    actual = [internal_value(np.asarray(xyz)[a['indexes']]) for a in axes]
    delta = [None if v is None else abs(v-t) for v,t in zip(actual, targets)]
    delta = [min(d, 360-d) if d is not None and a['kind'] == 'dihedral' else d for a,d in zip(axes, delta)]
    return actual, delta, all(d is not None and d <= a['tolerance'] for a,d in zip(axes, delta))


def seal(row):
    return canonical({k:v for k,v in row.items() if k != 'record_sha256'})


def scan(spec, output, backend, optimizer_factory, *, max_points=256):
    object_fields(spec, ('schema_version', 'material', 'settings', 'axes', 'previous', 'retry_failed'), 'scan input')
    if spec.get('schema_version') != 'chemical-scan-input/1': raise ValueError('chemical-scan-input/1 required')
    integer(max_points, 1, 256, 'max_points')
    if type(spec.get('retry_failed', False)) is not bool: raise ValueError('retry_failed must be boolean')
    m = material(spec['material']); s = settings(spec['settings'], backend); axes = axes_for(spec['axes'], m)
    plan = {k:v for k,v in spec.items() if k not in ('previous','retry_failed')}
    plan_sha = canonical({'backend': backend, 'plan': plan})
    targets = list(itertools.product(*(a['values'] for a in axes)))
    rows = [{'index': i, 'targets': list(t), 'status': 'pending'} for i,t in enumerate(targets)]
    previous = spec.get('previous')
    if previous is not None:
        if (not isinstance(previous, dict) or previous.get('schema_version') != 'chemical-scan-result/1' or previous.get('plan_sha256') != plan_sha
                or previous.get('status') not in ('completed', 'partial', 'failed') or len(previous.get('points', [])) != len(rows)):
            raise ValueError('continuation requires a matching terminal collected scan result; running/unknown dispatch is not retryable')
        for i, old in enumerate(previous['points']):
            if old.get('index') != i or old.get('targets') != list(targets[i]) or old.get('record_sha256') != seal(old): raise ValueError('previous point binding differs')
            if old.get('status') not in ('succeeded','failed','pending'): raise ValueError('unknown point dispatch state cannot be replayed')
            if old['status'] == 'succeeded':
                reused = checked(old['material'])
                if reused['ids'] != m['ids'] or not measure(axes, reused['coordinates'], targets[i])[2]: raise ValueError('previous successful point geometry/constraints differ')
                if type(old.get('energy_hartree')) not in (int,float) or not math.isfinite(old['energy_hartree']) or not old.get('evidence') or not old.get('primary_sha256'): raise ValueError('previous successful point evidence missing')
                rows[i] = copy.deepcopy(old); rows[i]['reused_from_sha256'] = canonical(previous)
            elif old['status'] == 'failed' and not spec.get('retry_failed', False): rows[i] = copy.deepcopy(old)
    out = Path(output)
    if out.exists(): raise ValueError('new output directory required')
    optimizer = optimizer_factory(m, s)
    out.mkdir(parents=True)
    result = {'schema_version':'chemical-scan-result/1', 'plan_sha256':plan_sha, 'backend':backend, 'settings':s,
              'axes':axes, 'points':rows, 'status':'running', 'seed_policy':'each_point_uses_original_geometry',
              'source_material_sha256':m['sha256'], 'previous_sha256':canonical(previous) if previous else None,
              'scope':'Constrained candidate geometries and physical electronic energies; not saddle evidence or a free-energy surface'}
    def save():
        for r in rows: r['record_sha256'] = seal(r)
        write_json(out/'result.json', result)
    save(); executed = 0
    for row in rows:
        if row['status'] != 'pending' or executed >= max_points: continue
        row['status'] = 'running'; save(); executed += 1
        directory = out / f'points/{row["index"]:04d}'
        try:
            coords, energy, evidence = optimizer.optimize(m['coordinates'].copy(), axes, row['targets'], directory)
            actual, deviation, satisfied = measure(axes, coords, row['targets'])
            derived = candidate_material(m, coords, {'operation':'relaxed_scan', 'plan_sha256':plan_sha, 'point_index':row['index'], 'targets':row['targets']})
            row.update(actual=actual, deviations=deviation, material=derived, energy_hartree=energy, evidence=evidence)
            if type(energy) not in (int,float) or not math.isfinite(energy): raise ValueError('physical electronic energy missing')
            if not satisfied: raise ValueError('optimized coordinates outside declared target tolerances')
            row['status'] = 'succeeded'
        except (ValueError, RuntimeError, OSError, subprocess.TimeoutExpired) as exc:
            row.update(status='failed', error={'type':type(exc).__name__, 'reason':str(exc)})
            if isinstance(exc, InterruptedError): break
        finally:
            row['primary_sha256'] = {str(p.relative_to(out)):'sha256:'+hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(directory.rglob('*')) if p.is_file()}
            save()
    result['status'] = 'completed' if all(r['status']=='succeeded' for r in rows) else 'partial' if any(r['status']=='pending' for r in rows) else 'failed'
    passed = [r for r in rows if r['status']=='succeeded']
    if passed:
        best = max(passed, key=lambda r:r['energy_hartree']); candidate = checked(best['material'])
        (out/'candidate.xyz').write_text(xyz_text(candidate['atoms'],candidate['coordinates']))
        write_json(out/'candidate.material.json', candidate['value'])
        result['candidate'] = {'point_index':best['index'], 'kind':'highest_successful_sampled_point', 'validated_ts':False}
    result['executed_points'] = executed; save()
    return result
