"""ASE NEB with evidence-bound Gaussian/xTB calculators and durable partial paths."""
from pathlib import Path
import subprocess

import ase
from ase import Atoms
from ase.calculators.calculator import Calculator, all_changes
from ase.io import write
from ase.mep import NEB
from ase.mep.neb import idpp_interpolate
from ase.optimize import BFGS, FIRE
from ase.units import Hartree
import numpy as np

from analysis_material import numeric_array
from ensemble_material import canonical, xyz_text
from gradient_contract import evaluate_evidence
from material import object_fields
from path_contract import candidate_material, endpoints, geometry, integer, positive
from path_process import write_json


class EvidenceCalculator(Calculator):
    """ASE uses eV/angstrom; the backend returns bound hartree gradient evidence."""
    implemented_properties = ['energy', 'forces']

    def __init__(self, backend, material, output, ledger, image_index):
        super().__init__()
        self.backend = backend
        self.material = material
        self.output = Path(output)
        self.ledger = ledger
        self.image_index = image_index
        self.evidence = None

    def calculate(self, atoms=None, properties=('energy', 'forces'), system_changes=all_changes):
        super().calculate(atoms, properties, system_changes)
        xyz = geometry(self.atoms.get_positions(),
                       elements=[a['element'] for a in self.material['atoms']])
        if self.ledger['attempted'] >= self.ledger['limit']:
            raise RuntimeError('calculator evaluation budget exhausted')
        attempt = self.ledger['attempted']
        self.ledger['attempted'] += 1
        entry = {'attempt': attempt, 'image_index': self.image_index,
                 'coordinates': xyz.tolist(), 'status': 'running'}
        self.ledger['evaluations'].append(entry)
        write_json(self.output / 'evaluations.json', self.ledger)
        try:
            value = self.backend.evaluate(xyz, self.output / f'evaluations/{attempt:06d}')
            energy, force = evaluate_evidence(value, self.material, xyz, self.backend.model)
            self.results = {'energy': energy * Hartree, 'forces': force * Hartree}
            self.evidence = value
            entry.update(status='completed', evidence=value)
        except Exception as exc:
            self.results = {}
            entry.update(status='failed', error={'type': type(exc).__name__, 'reason': str(exc)})
            raise
        finally:
            write_json(self.output / 'evaluations.json', self.ledger)


def neb(spec, output, calculator_factory):
    object_fields(spec, ('schema_version', 'reactant', 'product', 'mapping', 'settings',
                        'image_count', 'images', 'max_steps', 'max_evaluations',
                        'fmax_ev_per_angstrom', 'spring_ev_per_angstrom2', 'max_step_angstrom',
                        'climb_after', 'optimizer', 'interpolation', 'idpp_steps'), 'ASE NEB input')
    if spec.get('schema_version') != 'chemical-neb-input/2':
        raise ValueError('chemical-neb-input/2 required; v1 step_size is not an ASE optimizer setting')
    m, _, pxyz, order = endpoints(spec)
    count = integer(spec.get('image_count', 7), 3, 32, 'image_count')
    steps = integer(spec.get('max_steps', 200), 0, 2000, 'max_steps')
    budget = integer(spec.get('max_evaluations', 10000), 1, 100000, 'max_evaluations')
    fmax = positive(spec.get('fmax_ev_per_angstrom', .05), 'fmax_ev_per_angstrom')
    spring = positive(spec.get('spring_ev_per_angstrom2', .1), 'spring_ev_per_angstrom2')
    maxstep = positive(spec.get('max_step_angstrom', .05), 'max_step_angstrom')
    if maxstep > 1: raise ValueError('max_step_angstrom must not exceed 1')
    climb_after = spec.get('climb_after', 5)
    if climb_after is not None: integer(climb_after, 0, 2000, 'climb_after')
    optimizer_name = spec.get('optimizer', 'FIRE')
    if optimizer_name not in ('FIRE', 'BFGS'): raise ValueError('optimizer must be FIRE or BFGS')
    interpolation = spec.get('interpolation', 'linear')
    if interpolation not in ('linear', 'idpp'): raise ValueError('interpolation must be linear or idpp')
    idpp_steps = integer(spec.get('idpp_steps', 100), 1, 1000, 'idpp_steps')
    supplied = spec.get('images') is not None
    if supplied:
        if interpolation != 'linear': raise ValueError('provided images must not be silently reinterpolated')
        xyzs = numeric_array(spec['images'], (count, len(m['ids']), 3), 'images')
        if not np.allclose(xyzs[0], m['coordinates'], atol=1e-9, rtol=0) or not np.allclose(xyzs[-1], pxyz, atol=1e-9, rtol=0):
            raise ValueError('path endpoints differ from mapped materials')
    else:
        xyzs = np.array([(1-t)*m['coordinates']+t*pxyz for t in np.linspace(0, 1, count)])
    elements = [a['element'] for a in m['atoms']]
    for xyz in xyzs: geometry(xyz, elements=elements)
    if any(np.linalg.norm(a-b) < 1e-10 for a, b in zip(xyzs, xyzs[1:])):
        raise ValueError('duplicate adjacent NEB images')
    if not isinstance(spec.get('settings'), dict): raise ValueError('calculator settings required')
    backend = calculator_factory(m, spec['settings'])
    out = Path(output)
    out.mkdir(parents=True, exist_ok=False)
    images = [Atoms([a['element'] for a in m['atoms']], positions=xyz) for xyz in xyzs]
    band = NEB(images, k=spring, climb=False, method='improvedtangent',
               parallel=False, remove_rotation_and_translation=False)
    ledger = {'attempted': 0, 'limit': budget, 'evaluations': []}
    result = {'schema_version': 'chemical-neb-result/2', 'source_sha256': canonical(spec),
              'status': 'running', 'engine': {'name': 'ASE', 'version': ase.__version__, 'method': 'improvedtangent'},
              'model': backend.model, 'atom_ids': m['ids'], 'product_to_reactant_order': order,
              'settings': {'optimizer': optimizer_name, 'image_count': count, 'max_steps': steps,
                           'max_evaluations': budget, 'fmax_ev_per_angstrom': fmax,
                           'spring_ev_per_angstrom2': spring, 'max_step_angstrom': maxstep,
                           'climb_after': climb_after, 'interpolation': 'provided' if supplied else interpolation,
                           'idpp_steps': idpp_steps if interpolation == 'idpp' else None},
              'endpoint_status': 'fixed_supplied_geometries_not_certified_minima', 'iterations': [],
              'images': None, 'energies_hartree': None, 'candidate': None,
              'scope': 'Nonperiodic molecular single-surface candidate path; no endpoint optimization, TS/IRC or wavefunction-continuity certification'}
    write_json(out/'result.json', result)
    optimizer = None
    try:
        if not supplied and interpolation == 'idpp':
            idpp_interpolate(band, traj=None, log=None, steps=idpp_steps)
        for i, atoms in enumerate(images):
            geometry(atoms.positions, elements=elements)
            atoms.calc = EvidenceCalculator(backend, m, out, ledger, i)
        for step in range(steps+1):
            proposed = np.array([a.positions for a in images])
            result['pending_images'] = proposed.tolist()
            result['current_iteration'] = step
            write_json(out/'result.json', result)
            for atoms in images: geometry(atoms.positions, elements=elements)
            if any(np.linalg.norm(a-b) < 1e-10 for a,b in zip(proposed,proposed[1:])):
                raise ValueError('duplicate adjacent NEB images during optimization')
            energies = np.array([a.get_potential_energy() / Hartree for a in images])
            for atoms in images: atoms.get_forces()
            # Only complete physical evaluations can replace the candidate geometry/energy pair.
            result.update(images=proposed.tolist(), energies_hartree=energies.tolist(),
                          max_neb_force_ev_per_angstrom=None)
            result.pop('pending_images', None)
            desired_climb = band.climb or (climb_after is not None and step >= climb_after)
            if desired_climb != band.climb:
                band.climb = desired_climb
                optimizer = None
            forces = band.get_forces()
            if not np.isfinite(forces).all(): raise ValueError('nonfinite ASE NEB forces; revise path')
            maximum = float(np.linalg.norm(forces, axis=1).max())
            # If the ordinary band converges early, begin climbing now instead of moving a zero-force band.
            if maximum <= fmax and climb_after is not None and not band.climb:
                band.climb = True
                optimizer = None
                forces = band.get_forces()
                if not np.isfinite(forces).all(): raise ValueError('nonfinite ASE climbing forces')
                maximum = float(np.linalg.norm(forces, axis=1).max())
            result['max_neb_force_ev_per_angstrom'] = maximum
            high = int(np.argmax(energies[1:-1]))+1
            result['iterations'].append({'index': step, 'energies_hartree': energies.tolist(),
                'max_neb_force_ev_per_angstrom': maximum, 'climbing_image': high if band.climb else None,
                'evaluations': ledger['attempted']})
            iteration_dir = out / f'iterations/{step:04d}'
            iteration_dir.mkdir(parents=True)
            write(iteration_dir/'path.traj', images)
            (iteration_dir/'path.xyz').write_text(''.join(xyz_text(m['atoms'],a.positions,f'ASE NEB iteration {step} image {i}') for i,a in enumerate(images)))
            write_json(out/'result.json', result)
            if maximum <= fmax:
                result['status'] = 'converged'
                break
            if step == steps:
                result['status'] = 'step_limit'
                break
            if optimizer is None:
                cls = FIRE if optimizer_name == 'FIRE' else BFGS
                optimizer = cls(band, logfile=None, trajectory=None, maxstep=maxstep)
            optimizer.step()
            optimizer.nsteps += 1
    except (ValueError, RuntimeError, OSError, ArithmeticError, subprocess.TimeoutExpired) as exc:
        result.update(status='failed', error={'type': type(exc).__name__, 'reason': str(exc)})
    if result['energies_hartree'] is not None:
        high = int(np.argmax(result['energies_hartree'][1:-1]))+1
        xyz = np.array(result['images'][high])
        candidate = candidate_material(m, xyz, {'operation': 'ase_neb_image', 'source_sha256': canonical(spec), 'image_index': high})
        write_json(out/'candidate.material.json', candidate)
        (out/'candidate.xyz').write_text(xyz_text(m['atoms'],xyz))
        (out/'path.xyz').write_text(''.join(xyz_text(m['atoms'],xyz,f'Last fully evaluated ASE NEB image {i}') for i,xyz in enumerate(result['images'])))
        result['candidate'] = {'image_index': high, 'kind': 'highest_evaluated_internal_image', 'validated_ts': False}
    result['evaluation_count'] = ledger['attempted']
    write_json(out/'result.json', result)
    return result
