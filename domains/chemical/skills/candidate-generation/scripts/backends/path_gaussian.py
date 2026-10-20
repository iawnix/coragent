"""Per-point Gaussian ModRedundant constrained optimization, retaining convergence evidence."""
from pathlib import Path
import shutil
import re
import subprocess
import numpy as np

from conformers import internal_value
from gaussian_io import parse_log, require_supported_energy, write_xyz
from path_contract import gaussian_header, gaussian_geometry, geometry, settings as validate_settings
from path_process import invoke, write_json


def constrained_start(xyz, axes, targets):
    """Project a scan point onto its requested internal coordinates."""
    coords = np.asarray(xyz, dtype=float).copy()
    scale = np.array([1. if a['kind'] == 'distance' else np.pi / 180. for a in axes])

    def residual(points):
        values = [internal_value(points[a['indexes']]) for a in axes]
        if any(v is None for v in values):
            raise ValueError('scan seed has an undefined internal coordinate')
        delta = np.asarray(values, dtype=float) - np.asarray(targets, dtype=float)
        for i, axis in enumerate(axes):
            if axis['kind'] == 'dihedral':
                delta[i] = (delta[i] + 180.) % 360. - 180.
        return delta * scale

    for _ in range(100):
        error = residual(coords)
        if np.max(np.abs(error)) < 1e-8:
            return coords
        jac = np.empty((len(axes), coords.size))
        for j in range(coords.size):
            plus, minus = coords.copy(), coords.copy()
            plus.flat[j] += 1e-5; minus.flat[j] -= 1e-5
            delta = residual(plus) - residual(minus)
            for i, axis in enumerate(axes):
                if axis['kind'] == 'dihedral': delta[i] = (delta[i] + np.pi) % (2 * np.pi) - np.pi
            jac[:, j] = delta / 2e-5
        step = np.linalg.lstsq(jac, -error, rcond=1e-10)[0].reshape(coords.shape)
        norm = max(float(np.max(np.linalg.norm(step, axis=1))), 1e-12)
        step *= min(1., .2 / norm)
        old = np.linalg.norm(error)
        for factor in (1., .5, .25, .125, .0625):
            candidate = coords + factor * step
            if np.linalg.norm(residual(candidate)) < old:
                coords = candidate
                break
        else:
            break
    raise ValueError('scan seed cannot satisfy all target coordinates; change the pose or scan axes')


class GaussianOptimizer:
    def __init__(self, m, settings, executable):
        self.material, self.settings = m, validate_settings(settings, 'gaussian')
        self.executable = shutil.which(executable)
        if not self.executable: raise ValueError('configured Gaussian executable unavailable')

    def optimize(self, xyz, axes, targets, directory):
        directory = Path(directory); directory.mkdir(parents=True, exist_ok=False)
        s = self.settings
        header = gaussian_header(s, f'Opt=(ModRedundant,CalcFC,MaxCycles={s.get("max_cycles", 200)})')
        seed = constrained_start(xyz, axes, targets)
        text = header + gaussian_geometry(self.material, geometry(seed, elements=[a['element'] for a in self.material['atoms']]), 'Constrained scan point; candidate only')
        for axis in axes:
            kind = {'distance': 'B', 'angle': 'A', 'dihedral': 'D'}[axis['kind']]
            text += kind + ' ' + ' '.join(str(i+1) for i in axis['indexes']) + ' F\n'
        text += '\n'; inp = directory/'input.gjf'; inp.write_text(text)
        execution_error = None
        try:
            invoke([self.executable], directory, s['timeout_seconds'], s['threads'], stdin=inp)
        except (RuntimeError, OSError, subprocess.TimeoutExpired) as exc:
            execution_error = exc
        route = next(l for l in header.splitlines() if l.startswith('#'))
        log = directory/'program.out'
        if not log.exists() and execution_error is not None:
            raise execution_error
        if log.stat().st_size > 64*1024*1024: raise ValueError('Gaussian log exceeds 64 MiB')
        parsed = parse_log(log, expected_route=route)
        write_json(directory/'parsed.json', parsed); summary = parsed['summary']
        if parsed['atoms']:
            write_xyz(directory/'last_geometry.xyz', parsed['atoms'], 'Last Gaussian scan geometry; see parsed.json for completion')
        if execution_error is not None:
            raise execution_error
        declared = re.findall(r'Charge\s*=\s*(-?\d+)\s+Multiplicity\s*=\s*(\d+)', log.read_text(errors='replace'))
        expected = (str(self.material['value']['charge']), str(self.material['value']['multiplicity']))
        if not declared or any(pair != expected for pair in declared): raise ValueError('Gaussian output charge/multiplicity missing or inconsistent')
        if (not summary['normal_termination'] or summary['error_termination'] or not summary['route_expectation']['matched']
                or not summary['optimization_completed']):
            raise ValueError('Gaussian constrained optimization/route evidence incomplete')
        energy = require_supported_energy(summary)
        atoms = parsed['atoms']
        if [a[0] for a in atoms] != [a['element'] for a in self.material['atoms']]: raise ValueError('Gaussian output atom order differs')
        return geometry([a[1:] for a in atoms], elements=[a[0] for a in atoms]), energy, {'optimization': summary,
            'constraint_model': 'Gaussian ModRedundant freezes projected starting coordinates; scan engine checks final targets',
            'start_coordinates': seed.tolist()}
