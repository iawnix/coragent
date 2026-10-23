"""Pure process settings shared by local supervisors and remote wrappers."""
from __future__ import annotations

import hashlib
import os
import pwd
from pathlib import PurePosixPath
import re

THREAD_VARIABLES = ('OMP_NUM_THREADS', 'MKL_NUM_THREADS', 'OPENBLAS_NUM_THREADS')


def resource_environment(resources):
    """Allocation-derived defaults, also reasserted after software activation."""
    cpus = resources.get('cpus')
    return {**({name: str(cpus) for name in (*THREAD_VARIABLES, 'CORAGENT_JOB_CPUS')} if cpus else {}),
            **({'CORAGENT_JOB_MEMORY_MB': str(resources['memory_mb'])} if resources.get('memory_mb') else {})}


def validate_resource_environment(resources, variables):
    for name, expected in resource_environment(resources).items():
        if name in variables and variables[name] != expected:
            raise ValueError('job_resource_conflict: ' + name + ' differs from the job allocation; update the binding environment')


def minimum_environment(home=None):
    return {"PATH": os.defpath, "LANG": "C.UTF-8", "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONNOUSERSITE": "1", **({"HOME": home} if home is not None else {})}


def validate_environment(variables):
    if any(not isinstance(key, str) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', key)
           or not isinstance(value, str) or '\0' in value for key, value in variables.items()):
        raise ValueError('invalid Job environment variable')


def job_process_environment(root, metadata, variables, *, home=None):
    validate_environment(variables)
    scratch_root = metadata.get('execution_binding', {}).get('binding', {}).get('scratch_root')
    scratch = str(PurePosixPath(scratch_root) / ('job-' + hashlib.sha256(str(root).encode()).hexdigest()[:32])
                  if scratch_root else PurePosixPath(root) / '.scratch')
    env = {**minimum_environment(home), 'TMPDIR': scratch}
    resources = metadata.get('resources', {})
    validate_resource_environment(resources, variables)
    env.update(resource_environment(resources))
    env.update({key: value.replace('{scratch}', scratch) for key, value in variables.items()})
    return env, scratch


def supervisor_environment():
    """Clean environment for target probes; never forwards controller credentials."""
    return minimum_environment(pwd.getpwuid(os.getuid()).pw_dir)
