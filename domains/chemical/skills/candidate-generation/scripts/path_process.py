"""Finite native attempts with durable inputs and process-group cleanup."""
import json
import os
from pathlib import Path
import signal
import subprocess


def write_json(path, value):
    path = Path(path); temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')
    temporary.replace(path)


def invoke(command, directory, timeout, threads, stdin=None, extra_env=None):
    process = None; inp = None
    def interrupt(signum, frame): raise InterruptedError(f'received signal {signum}')
    old = {s: signal.signal(s, interrupt) for s in (signal.SIGTERM, signal.SIGINT)}
    directory = Path(directory).resolve()
    write_json(directory / 'command.json', command)
    try:
        if stdin is not None: inp = Path(stdin).open('rb')
        with (directory / 'program.out').open('wb') as log:
            env = dict(os.environ, OMP_NUM_THREADS=str(threads), MKL_NUM_THREADS=str(threads), TMPDIR=str(directory))
            if extra_env is not None: env.update(extra_env)
            process = subprocess.Popen(command, cwd=directory, stdin=inp, stdout=log, stderr=subprocess.STDOUT, env=env, start_new_session=True)
            rc = process.wait(timeout=timeout)
            if rc: raise RuntimeError(f'native program exited {rc}')
    finally:
        if process is not None:
            try: os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError: pass
            process.wait()
        if inp is not None: inp.close()
        for sig, handler in old.items(): signal.signal(sig, handler)
