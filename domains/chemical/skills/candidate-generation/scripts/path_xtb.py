"""xTB 6.7.1 CLI adapter: physical gradients and restrained optimization are separate."""
import hashlib
import importlib.util
import math
from pathlib import Path
import re
import shutil

import numpy as np

from ensemble_material import canonical, xyz_text
from gradient_contract import calculation
from path_contract import BOHR_ANGSTROM, geometry, settings as validate_settings
from path_process import invoke, write_json
from xyz import read_xyz

_base = Path(__file__).resolve().parents[2] / 'xtb/scripts/parser.py'
_spec = importlib.util.spec_from_file_location('path_xtb_parser', _base)
_parser = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(_parser)


def number(s):
    x = float(s.replace('D', 'E').replace('d', 'e'))
    if not math.isfinite(x): raise ValueError('nonfinite gradient record')
    return x


def gradient_file(text, m, xyz, energy):
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    n = len(m['ids'])
    if len(lines) != 2*n + 3 or lines[0] != '$grad' or lines[-1] != '$end': raise ValueError('single complete Turbomole gradient block required')
    match = re.search(r'SCF energy\s*=\s*(\S+)', lines[1], re.I)
    if not match or abs(number(match[1]) - energy) > 1e-7: raise ValueError('gradient and log energy differ')
    positions = []; gradients = []
    for i, line in enumerate(lines[2:2+n]):
        fields = line.split()
        if len(fields) != 4 or fields[3].capitalize() != m['atoms'][i]['element']: raise ValueError('gradient element order differs')
        positions.append([number(s) for s in fields[:3]])
    if not np.allclose(np.array(positions)*BOHR_ANGSTROM, xyz, atol=1e-7, rtol=0): raise ValueError('gradient coordinates differ from requested geometry')
    for line in lines[2+n:-1]:
        fields = line.split()
        if len(fields) != 3: raise ValueError('three gradient components required')
        gradients.append([number(s) for s in fields])
    return np.array(gradients)


def read_output(directory, method, task, state):
    log = directory / 'program.out'
    if log.stat().st_size > 64*1024*1024: raise ValueError('native log exceeds 64 MiB')
    files = {'xtb.out': log}
    if task == 'opt': files['xtbopt.xyz'] = directory / 'xtbopt.xyz'
    summary = _parser.parse_xtb_artifacts(task, files)['summary']
    if summary['program_version'] != '6.7.1' or (summary['method'] or '').lower().replace('-', '') != method + 'xtb':
        raise ValueError('this adapter requires xTB 6.7.1 and requested GFN method')
    if not summary['execution_completed'] or not summary['scc_converged'] or summary['missing_artifacts']:
        raise ValueError('normal termination and complete converged SCC evidence required')
    if task == 'opt' and not summary['optimization_converged']: raise ValueError('restrained optimization did not converge')
    for key, expected in [('charge',state['charge']),('unpaired_electrons',state['multiplicity']-1)]:
        if summary[key] is not None and summary[key] != expected: raise ValueError('xTB output state differs from request')
    e = summary['total_energy_hartree']
    if type(e) not in (int, float) or not math.isfinite(e): raise ValueError('finite native energy required')
    return summary


class XtbCalculator:
    def __init__(self, m, settings, executable):
        self.material, self.settings = m, validate_settings(settings, 'xtb')
        self.executable = shutil.which(executable)
        if not self.executable: raise ValueError('configured xTB executable unavailable')
        self.model = {'backend': 'xtb', 'version': '6.7.1', 'method': settings['method'],
                      'charge': m['value']['charge'], 'multiplicity': m['value']['multiplicity'],
                      'electronic_state': m['value']['electronic_state'], 'solvent': settings['solvent'],
                      'solvent_model': settings['solvent_model'], 'constraints': [], 'accuracy':1., 'electronic_temperature_K':300.}

    def command(self):
        s, m = self.settings, self.material['value']
        command = [self.executable, 'input.xyz', '--gfn', s['method'][-1], '--chrg', str(m['charge']), '--uhf', str(m['multiplicity']-1), '--parallel', str(s['threads']), '--acc', '1.0', '--etemp', '300']
        if s['solvent_model'] != 'gas': command += ['--alpb', s['solvent']]
        return command

    def evaluate(self, xyz, directory):
        directory = Path(directory); directory.mkdir(parents=True, exist_ok=False)
        xyz = geometry(xyz, elements=[a['element'] for a in self.material['atoms']]); (directory / 'input.xyz').write_text(xyz_text(self.material['atoms'], xyz))
        invoke(self.command() + ['--grad'], directory, self.settings['timeout_seconds'], self.settings['threads'])
        summary = read_output(directory, self.settings['method'], 'sp', self.material['value'])
        gradient = directory / 'gradient'
        if gradient.stat().st_size > 8*1024*1024: raise ValueError('gradient exceeds size bound')
        g = gradient_file(gradient.read_text(), self.material, xyz, summary['total_energy_hartree'])
        sources = {p.name: 'sha256:' + hashlib.sha256(p.read_bytes()).hexdigest() for p in [gradient, directory/'program.out', directory/'input.xyz', directory/'command.json']}
        result = calculation(self.material, xyz, self.model, summary['total_energy_hartree'], g, sources)
        write_json(directory/'evaluation.json', result)
        return result

    def optimize(self, xyz, axes, targets, directory):
        directory = Path(directory); directory.mkdir(parents=True, exist_ok=False)
        (directory / 'input.xyz').write_text(xyz_text(self.material['atoms'], geometry(xyz, elements=[a['element'] for a in self.material['atoms']])))
        force = self.settings.get('force_constant', 1.)
        text = '$constrain\n force constant=' + str(force) + '\n'
        for axis, target in zip(axes, targets):
            text += ' ' + axis['kind'] + ': ' + ', '.join(str(i+1) for i in axis['indexes']) + ', ' + str(target) + '\n'
        text += '$end\n'; (directory / 'constraints.inp').write_text(text)
        invoke(self.command() + ['--opt', self.settings.get('opt_level', 'tight'), '--input', 'constraints.inp'], directory, self.settings['timeout_seconds'], self.settings['threads'])
        summary = read_output(directory, self.settings['method'], 'opt', self.material['value'])
        atoms = read_xyz(directory/'xtbopt.xyz')
        if [a[0] for a in atoms] != [a['element'] for a in self.material['atoms']]: raise ValueError('optimized atom order differs')
        coords = geometry([a[1:] for a in atoms], elements=[a[0] for a in atoms])
        # xTB TOTAL ENERGY during restrained optimization may include the added
        # potential. A fresh unrestrained evaluation supplies physical energy.
        value = self.evaluate(coords, directory/'unrestrained')
        return coords, value['energy']['value'], {'optimization': summary, 'physical_evaluation': value,
            'constraint_model': 'xTB added restraint potential; actual coordinate tolerance checked independently',
            'force_constant_native': force, 'restraint_input_sha256': 'sha256:'+hashlib.sha256(text.encode()).hexdigest()}
