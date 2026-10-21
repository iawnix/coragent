"""Pure allocation contract; no science imports, probes, writes or ambient inference.

Current scan, NEB image and MECP surface evaluations are sequential: concurrency
is one. A parallel implementation must update this contract along with its runner.
Gaussian/PySCF memory reserves at least 256 MiB and 10% of the job total for overhead.
This is a conservative default budget, not a prediction of actual peak RSS.
"""
import json
import os
from pathlib import Path
import re


def positive(value, name):
    if type(value) is not int or value < 1:
        raise ValueError('job_resource_invalid: ' + name + ' must be a positive integer')
    return value


def program_memory(total):
    total = positive(total, 'memory_mb')
    usable = total - max(256, (total + 9) // 10)
    if usable < 1:
        raise ValueError('job_resource_conflict: job memory must leave at least 256 MiB for process overhead')
    return usable


def job_memory(program):
    program = positive(program, 'program memory_mb')
    return max(program + 256, (program * 10 + 8) // 9)


def runtime_settings(value, *, memory=True):
    """Fill omitted JSON program settings from the pinned execution environment."""
    result = dict(value)
    if 'threads' not in result:
        result['threads'] = int(os.environ.get('CORAGENT_JOB_CPUS', '1'))
    if memory and 'memory_mb' not in result:
        total = os.environ.get('CORAGENT_JOB_MEMORY_MB')
        result['memory_mb'] = program_memory(int(total)) if total else 2000
    return result


def _option(arguments, flag):
    found = []
    for index, arg in enumerate(arguments):
        if arg == flag:
            if index + 1 == len(arguments):
                raise ValueError('job_resource_invalid: missing value for ' + flag)
            found.append(arguments[index + 1])
        elif arg.startswith(flag + '='):
            found.append(arg.split('=', 1)[1])
    if len(found) > 1:
        raise ValueError('job_resource_invalid: duplicate ' + flag)
    if not found:
        return None
    if not re.fullmatch(r'[0-9]+', found[0]):
        raise ValueError('job_resource_invalid: ' + flag + ' must be a positive integer')
    return positive(int(found[0]), flag)


def _gjf(path):
    values = []
    for section in re.split(r'(?im)^\s*--Link1--\s*$', Path(path).read_text()):
        cpus = re.findall(r'(?im)^\s*%nproc(?:shared)?\s*=\s*(\d+)\s*$', section)
        memory = re.findall(r'(?im)^\s*%mem\s*=\s*(\d+)\s*(MB|GB)\s*$', section)
        if len(cpus) != 1 or len(memory) != 1:
            raise ValueError('job_resource_invalid: every Gaussian link needs %nprocshared and %mem in MB/GB')
        values.append((positive(int(cpus[0]), 'GJF threads'),
                       positive(int(memory[0][0]) * (1024 if memory[0][1].upper() == 'GB' else 1), 'GJF memory')))
    if len(set(values)) != 1:
        raise ValueError('job_resource_conflict: this Gaussian runner requires the same resources in every link')
    return values[0]


def _declared(descriptor, arguments, inputs):
    name = descriptor['id']
    cpus, memory = _option(arguments, '--threads'), _option(arguments, '--memory-mb')
    if name == 'chemical.gaussian-input':
        file_cpus, file_memory = _gjf(inputs['input'])
        if cpus is not None and cpus != file_cpus or memory is not None and memory != file_memory:
            raise ValueError('job_resource_conflict: runner arguments disagree with the explicit Gaussian input')
        return file_cpus, file_memory
    if descriptor['backend'] in ('path_xtb', 'path_gaussian'):
        value = json.loads(Path(inputs['input']).read_text())
        settings = value.get('settings') if isinstance(value, dict) else None
        if not isinstance(settings, dict):
            raise ValueError('job_resource_invalid: calculation input requires a settings object')
        if any(key in obj for obj in (value, settings) for key in ('parallel', 'workers', 'concurrency')):
            raise ValueError('job_resource_invalid: these path runners evaluate one process at a time; parallel settings are unsupported')
        cpus, memory = settings.get('threads'), settings.get('memory_mb')
    return (positive(cpus, 'threads') if cpus is not None else None,
            positive(memory, 'program memory_mb') if memory is not None else None)


def defaults(descriptor):
    result = {'cpus': 1}
    if descriptor['backend'] in ('gaussian', 'path_gaussian', 'pyscf'):
        result['memory_mb'] = job_memory(4000 if descriptor['backend'] == 'pyscf' else 2000)
    return result


def requirements(descriptor, arguments, inputs):
    cpus, memory = _declared(descriptor, arguments, inputs)
    return {**({'cpus': cpus} if cpus is not None else {}),
            **({'memory_mb': job_memory(memory)} if memory is not None else {})}


def prepare(descriptor, arguments, inputs, resources):
    cpus, memory = _declared(descriptor, arguments, inputs)
    total_cpus = resources.get('cpus')
    if total_cpus is None:
        raise ValueError('job_resource_invalid: this runner requires numeric cpus, not an opaque scheduler select expression')
    if cpus is not None and cpus != total_cpus:
        raise ValueError(f'job_resource_conflict: program threads={cpus}, job cpus={total_cpus}; update the input or re-prepare with matching --cpus')
    has_memory = descriptor['backend'] in ('gaussian', 'path_gaussian', 'pyscf')
    if has_memory:
        if 'memory_mb' not in resources:
            raise ValueError('job_resource_invalid: numeric job memory_mb is required for this runner')
        usable = program_memory(resources['memory_mb'])
        if memory is not None and memory > usable:
            raise ValueError(f'job_resource_conflict: program memory={memory} MiB needs at least {job_memory(memory)} MiB total job memory including overhead')
        memory = usable if memory is None else memory
    if descriptor['backend'] not in ('path_xtb', 'path_gaussian') and descriptor['id'] != 'chemical.xtb':
        if _option(arguments, '--threads') is None:
            arguments += ['--threads', str(total_cpus)]
        if has_memory and _option(arguments, '--memory-mb') is None:
            arguments += ['--memory-mb', str(memory)]
    return arguments, {'status': 'checked', 'scope': 'declared program settings, not measured peak usage',
                       'threads': total_cpus, 'concurrent_processes': 1,
                       **({'program_memory_mb': memory} if has_memory else {})}
