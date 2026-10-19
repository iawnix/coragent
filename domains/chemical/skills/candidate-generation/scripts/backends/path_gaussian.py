"""Per-point Gaussian ModRedundant constrained optimization, retaining convergence evidence."""
from pathlib import Path
import shutil
import re
import subprocess

from gaussian_io import parse_log, require_supported_energy, write_xyz
from path_contract import gaussian_header, gaussian_geometry, geometry, settings as validate_settings
from path_process import invoke, write_json


class GaussianOptimizer:
    def __init__(self, m, settings, executable):
        self.material, self.settings = m, validate_settings(settings, 'gaussian')
        self.executable = shutil.which(executable)
        if not self.executable: raise ValueError('configured Gaussian executable unavailable')

    def optimize(self, xyz, axes, targets, directory):
        directory = Path(directory); directory.mkdir(parents=True, exist_ok=False)
        s = self.settings
        header = gaussian_header(s, f'Opt=(ModRedundant,CalcFC,MaxCycles={s.get("max_cycles", 200)})')
        text = header + gaussian_geometry(self.material, geometry(xyz, elements=[a['element'] for a in self.material['atoms']]), 'Constrained scan point; candidate only')
        for axis, target in zip(axes, targets):
            kind = {'distance': 'B', 'angle': 'A', 'dihedral': 'D'}[axis['kind']]
            text += kind + ' ' + ' '.join(str(i+1) for i in axis['indexes']) + f' {target:.12g} F\n'
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
        return geometry([a[1:] for a in atoms], elements=[a[0] for a in atoms]), energy, {'optimization': summary, 'constraint_model': 'Gaussian ModRedundant frozen internal coordinates'}
