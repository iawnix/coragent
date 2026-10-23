"""Bounded native CREST execution with a retained receipt on timeout/failure."""
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / '_shared'))
from crest_cli import parse_arguments
from crest_io import input_geometry, parse_primary, sha, version


def bounded(command, cwd, log, timeout, env):
    process = None
    def interrupt(signum, frame):
        raise InterruptedError(f'runner received signal {signum}')
    old = {s: signal.signal(s, interrupt) for s in (signal.SIGTERM, signal.SIGINT)}
    try:
        with Path(log).open('w') as handle:
            process = subprocess.Popen(command, cwd=cwd, stdout=handle, stderr=subprocess.STDOUT, env=env, start_new_session=True)
            return process.wait(timeout=timeout)
    finally:
        if process is not None:
            try: os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError: pass
            process.wait()
        for sig, handler in old.items(): signal.signal(sig, handler)


def run(args):
    if args.material.stat().st_size > 32 * 1024 * 1024: raise ValueError('material exceeds 32 MiB')
    raw = args.material.read_bytes(); material, atoms = input_geometry(raw)
    out = args.output_dir.resolve()
    if out.exists(): raise ValueError('use a new output directory for each attempt')
    executable = shutil.which(args.executable)
    if not executable: raise ValueError('configured CREST executable unavailable')
    out.mkdir(parents=True)
    xyz = str(len(atoms)) + '\nCREST input; material ' + sha(raw) + '\n' + ''.join(a[0] + ' ' + ' '.join(format(v, '.17g') for v in a[1:]) + '\n' for a in atoms)
    (out / 'input.xyz').write_text(xyz)
    settings = {'method': args.method, 'search_level': args.search_level, 'opt_level': args.opt_level,
                'charge': material['charge'], 'multiplicity': material['multiplicity'], 'uhf': material['multiplicity'] - 1,
                'threads': args.threads, 'solvent': args.solvent, 'solvent_model': 'ALPB' if args.solvent else 'gas',
                'energy_window_kcal_mol': args.energy_window, 'timeout_seconds': args.timeout,
                'max_members': args.max_members,
                'constraints': [], 'random_seed': None, 'seed_scope': 'Native CREST randomness is not controlled by this command profile'}
    command = [executable, 'input.xyz', '--' + args.method, '--chrg', str(material['charge']), '--uhf', str(material['multiplicity'] - 1),
               '--optlev', args.opt_level, '-T', str(args.threads), '--ewin', str(args.energy_window)]
    if args.search_level != 'normal': command.append('--' + args.search_level)
    if args.solvent: command += ['--alpb', args.solvent]
    result = {'schema_version': 'chemical-crest-run/1', 'material_sha256': sha(raw), 'settings': settings,
              'input_xyz_sha256': sha(xyz.encode()), 'command': command, 'status': 'failed', 'returncode': None,
              'scope': 'One bounded CREST 3.0.2 search, not exhaustive sampling or wavefunction/identity certification'}
    env = dict(os.environ, OMP_NUM_THREADS=str(args.threads), MKL_NUM_THREADS=str(args.threads), TMPDIR=str(out))
    try:
        rc = bounded([executable, '--version'], out, out / 'version.out', min(args.timeout, 30.), env)
        detected = version((out / 'version.out').read_text(errors='replace'))
        result['version'] = detected
        if rc != 0 or detected != '3.0.2': raise ValueError('this command/output profile requires CREST 3.0.2')
        result['returncode'] = bounded(command, out, out / 'crest.out', args.timeout, env)
        if result['returncode'] != 0: raise RuntimeError('CREST returned a nonzero exit status')
        result['primary'] = parse_primary(out, [a[0] for a in atoms], args.max_members)
        if result['primary']['parsing_status'] == 'invalid': raise ValueError('CREST primary outputs are incomplete or inconsistent')
        result['status'] = 'completed'
    except (ValueError, RuntimeError, OSError, subprocess.TimeoutExpired) as exc:
        result['error'] = {'type': type(exc).__name__, 'reason': str(exc)}
    finally:
        if 'primary' not in result:
            result['primary'] = parse_primary(out, [a[0] for a in atoms], args.max_members)
        (out / 'result.json').write_text(json.dumps(result, indent=2, allow_nan=False) + '\n')
    return result


if __name__ == '__main__':
    result = run(parse_arguments())
    raise SystemExit(0 if result['status'] == 'completed' else 1)
