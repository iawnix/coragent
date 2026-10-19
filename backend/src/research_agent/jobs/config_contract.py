"""Public, standard-library-only contract for installation execution bindings."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import tomllib

NAME_PATTERN = r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}"
QUEUE_PATTERN = r"[A-Za-z0-9][A-Za-z0-9_.@-]{0,127}"
TIMEOUT_LIMITS = {"connect_timeout_seconds": 300, "command_timeout_seconds": 3600,
                  "transfer_timeout_seconds": 86400}
TARGET_FIELDS = {"kind", "supervisor", "python", "backends", "submission"}
BACKEND_FIELDS = {"command", "python", "activation_script", "environment", "submission", "allowed_queues", "scratch_root"}


def _keys(value, allowed, label):
    if not isinstance(value, dict) or set(value) - allowed:
        raise ValueError(f"{label} contains unsupported fields; use the current job.toml contract")


def _absolute(value, label):
    if (not isinstance(value, str) or not value.startswith('/') or value == '/'
            or any(char in value for char in '\n\r\0') or '..' in Path(value).parts):
        raise ValueError(f"{label} must be an absolute target path without traversal")


def _queues(value, label):
    if (not isinstance(value, list) or len(value) != len(set(value))
            or any(not isinstance(q, str) or not re.fullmatch(QUEUE_PATTERN, q) for q in value)):
        raise ValueError(f"{label} must be an array of unique queue names")


def validate_python(binding, label="python"):
    if not isinstance(binding, dict) or set(binding) != {"manager", "conda_executable", "prefix", "lock_ref"}:
        raise ValueError(f"{label} requires manager, conda_executable, prefix and lock_ref; migrate legacy Python strings")
    if binding["manager"] != "conda":
        raise ValueError(f"{label}.manager must be conda")
    for field in ("conda_executable", "prefix", "lock_ref"):
        _absolute(binding[field], f"{label}.{field}")
    if not isinstance(binding["lock_ref"], str) or not binding["lock_ref"].strip():
        raise ValueError(f"{label}.lock_ref must identify the installed dependency lock")
    return binding


def _validate_execution_config(value):
    """Validate the target-oriented schema and expose its binding view."""
    if set(value) != {"execution"}:
        raise ValueError("job config must contain only the execution table")
    execution = value.get("execution")
    if not isinstance(execution, dict) or set(execution) - {"default_target", "targets"}:
        raise ValueError("execution contains unsupported fields")
    default = execution.get("default_target")
    targets = execution.get("targets")
    if not isinstance(default, str) or not re.fullmatch(NAME_PATTERN, default):
        raise ValueError("execution.default_target is invalid")
    if not isinstance(targets, dict) or not targets or default not in targets:
        raise ValueError("execution.targets must define the default target")
    local_count = 0
    environments = {}
    for name, raw in targets.items():
        if not isinstance(name, str) or not re.fullmatch(NAME_PATTERN, name):
            raise ValueError(f"invalid execution target name: {name!r}")
        if not isinstance(raw, dict):
            raise ValueError(f"execution.targets.{name} must be a table")
        target = dict(raw)
        driver = target.get("driver")
        external = driver == "external"
        if driver not in {"external", "local", "process", "systemd"} or (not external and target.get("type") != "local"):
            raise ValueError("execution plugin drivers were removed; use driver=external with transport and handler")
        if not external:
            _keys(target, {"type", "driver", "supervisor", "python", "bindings", "submission"}, f"execution.targets.{name}")
        transport = target.get("transport", "ssh" if target.get("type") == "remote" else "local")
        if external and transport not in {"local", "ssh"}:
            raise ValueError("external transport must be local or ssh")
        scope = target.get("type", "remote" if transport == "ssh" else "local") if external else target.get("type")
        if external:
            _keys(target, {"type", "driver", "transport", "file_mode", "work_root", "handler", "handler_environment",
                           "cluster_name", "ssh_host", "ssh_config", "submission", "bindings", "python",
                           "allowed_queues", *TIMEOUT_LIMITS}, f"execution.targets.{name}")
            if "transport" not in target:
                raise ValueError("external target requires transport=local or transport=ssh")
            if scope != ("remote" if transport == "ssh" else "local"):
                raise ValueError("external type must match its command transport")
            for field, limit in TIMEOUT_LIMITS.items():
                if field in target and (type(target[field]) is not int or not 1 <= target[field] <= limit):
                    raise ValueError(f"external target {field} must be between 1 and {limit}")
            if "ssh_config" in target:
                _absolute(target["ssh_config"], f"execution.targets.{name}.ssh_config")
            if "allowed_queues" in target:
                _queues(target["allowed_queues"], f"execution.targets.{name}.allowed_queues")
            if transport == "local" and {"ssh_host", "ssh_config"} & target.keys():
                raise ValueError("local transport does not use SSH settings")
            if transport == "ssh" and (not isinstance(target.get("ssh_host"), str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.@:-]*", target["ssh_host"])):
                raise ValueError("external ssh_host is invalid")
            if "cluster_name" in target and (not isinstance(target["cluster_name"], str) or not re.fullmatch(NAME_PATTERN, target["cluster_name"])):
                raise ValueError("external cluster_name is invalid")
            target.update(type=scope, transport=transport)
            root = target.get("work_root")
            _absolute(root, f"execution.targets.{name}.work_root")
            if target.get('file_mode', 'staged') not in ('staged', 'shared'):
                raise ValueError('external file_mode must be staged or shared')
            handler = target.get("handler")
            if not isinstance(handler, list) or not handler or any(not isinstance(arg, str) or not arg or "\0" in arg for arg in handler):
                raise ValueError("external target requires a handler argv")
            variables = target.get("handler_environment", {})
            if not isinstance(variables, dict):
                raise ValueError("handler_environment must be a table")
            if any(not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', key) or
                   not isinstance(item, str) or '\0' in item for key, item in variables.items()):
                raise ValueError("handler_environment contains invalid variables")
        if not external:
            local_count += 1
        bindings = target.get("bindings", {})
        if not isinstance(bindings, dict):
            raise ValueError(f"execution.targets.{name}.bindings must be a table")
        normalized = dict(target)
        normalized.update({"kind": scope, "backends": bindings, "driver": driver})
        if not external:
            normalized.setdefault("supervisor", "process" if driver == "process" else "systemd")
            if normalized["supervisor"] not in {"process", "systemd"}:
                raise ValueError("local supervisor must be process or systemd")
        environments[name] = normalized
    if local_count > 1:
        raise ValueError("execution configuration may define at most one local target")
    normalized_config = {
        "default_environment": default,
        "environments": environments,
        "execution": value["execution"],
    }
    for name, target in environments.items():
        _validate_bindings(normalized_config, name, target)
    return normalized_config


def _validate_bindings(value, name, target):
    if 'allowed_queues' in target:
        _queues(target['allowed_queues'], f"environments.{name}.allowed_queues")
    if "python" in target:
        validate_python(target["python"], f"environments.{name}.python")
    backends = target.get("backends", {})
    if not isinstance(backends, dict):
        raise ValueError(f"environments.{name}.backends must be a table")
    for backend, binding in backends.items():
        if not re.fullmatch(NAME_PATTERN, backend):
            raise ValueError(f"invalid backend name: {backend}")
        if not isinstance(binding, dict):
            raise ValueError(f"invalid backend binding: {backend}")
        _keys(binding, BACKEND_FIELDS, f"backend {backend}")
        if 'allowed_queues' in binding:
            _queues(binding['allowed_queues'], f"backend {backend}.allowed_queues")
            if target.get('allowed_queues') and set(binding['allowed_queues']) - set(target['allowed_queues']):
                raise ValueError(f"backend {backend} queues exceed target allowed_queues")
        env = binding.get('environment', {})
        if not isinstance(env, dict) or any(not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', key)
                or not isinstance(item, str) or '\0' in item for key, item in env.items()):
            raise ValueError(f"backend {backend}.environment is invalid")
        if "python" in binding:
            validate_python(binding["python"], f"environments.{name}.backends.{backend}.python")
        command = binding.get("command")
        if command is not None:
            argv = [command] if isinstance(command, str) else command
            if not isinstance(argv, list) or not argv or any(not isinstance(x, str) or not x.strip() for x in argv):
                raise ValueError(f"backend {backend}.command must be a nonempty string or argv")
        elif "python" not in binding and "python" not in target:
            raise ValueError(f"backend {backend} requires command or an explicit python binding")
        for field in ('activation_script', 'scratch_root'):
            if field in binding:
                _absolute(binding[field], f"backend {backend}.{field}")
    if "submission" in target:
        resolve_submission(value, name)
    for backend, binding in backends.items():
        if "submission" in binding:
            resolve_submission(value, name, backend)


def configuration_document(settings):
    """Convert the internal binding view to installation TOML fields."""
    if "execution" not in settings:
        return settings
    targets = {}
    for name, target in settings["environments"].items():
        targets[name] = {key: value for key, value in target.items() if key not in {"kind", "backends", "bindings"}}
        targets[name]["bindings"] = target.get("backends", {})
    return {"execution": {"default_target": settings["default_environment"], "targets": targets}}


def validate_job_config(value):
    if isinstance(value, dict) and "execution" in value:
        return _validate_execution_config(configuration_document(value) if "environments" in value else value)
    _keys(value, {"default_environment", "environments"}, "job config")
    environments = value.get("environments")
    if not isinstance(environments, dict) or not environments or value.get("default_environment") not in environments:
        raise ValueError("job config must define default_environment and at least one environment")
    for name, target in environments.items():
        if not re.fullmatch(NAME_PATTERN, name):
            raise ValueError(f"invalid job environment name: {name!r}")
        if not isinstance(target, dict) or target.get("kind") not in {"local", "remote"}:
            raise ValueError(f"job environment {name!r} must declare kind=local or kind=remote")
        if 'supervisor' in target and (target['kind'] != 'local' or target['supervisor'] not in {'process', 'systemd'}):
            raise ValueError('local supervisor must be process or systemd')
        if target['kind'] == 'remote':
            raise ValueError("remote scheduler plugins were removed; use execution.targets with driver=external, transport and handler")
        _keys(target, TARGET_FIELDS, f"environments.{name}")
        _validate_bindings(value, name, target)
    return value


def load_job_config(path):
    with Path(path).expanduser().open("rb") as handle:
        return validate_job_config(tomllib.load(handle))


def validate_catalog_bindings(settings, catalogs):
    """Bootstrap binding checks without importing runtime dependencies."""
    settings = validate_job_config(settings)
    results = {}
    for name, target in settings['environments'].items():
        results[name] = {}
        for catalog in catalogs:
            for kind in ('executors', 'validators'):
                for entry in catalog.get(kind, []):
                    backend = entry['backend']
                    key = kind + ':' + entry['id'] + '@' + entry['version']
                    if backend not in target.get('backends', {}):
                        results[name][key] = {'status': 'not_configured', 'backend': backend}
                        continue
                    selected = resolve_binding(settings, name, backend,
                        runtime='python' if kind == 'validators' else entry['runtime'])
                    needs_command = any(token in entry.get('argv', []) for token in ('{command}', '{executable}'))
                    if bool(selected['binding'].get('command')) != needs_command:
                        raise ValueError('execution_binding_command_mismatch: ' + name + '/' + key)
                    results[name][key] = {'status': 'configuration_validated', 'backend': backend,
                                          'environment_evidence': None}
    return results


def resolve_python(config, environment, backend):
    target = config["environments"][environment]
    binding = target.get("backends", {}).get(backend, {}).get("python", target.get("python"))
    if binding is None:
        raise ValueError(f"python_binding_missing: configure environments.{environment}.python or backends.{backend}.python as a Conda environment")
    return validate_python(binding)


def python_command(binding):
    validate_python(binding)
    # env -u applies before Conda itself; inherited host PYTHONPATH must not
    # contaminate either Conda or the selected target interpreter.
    return ["env", "-u", "PYTHONHOME", "-u", "PYTHONPATH", "PYTHONNOUSERSITE=1",
            binding["conda_executable"], "run", "--no-capture-output", "-p", binding["prefix"], "python"]


def binding_digest(value):
    return "sha256:" + hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def resolve_binding(config, environment, backend, *, runtime, requested=None):
    """Select only the configuration that can affect this execution."""
    if runtime not in {"python", "native"}:
        raise ValueError("execution_runtime_invalid")
    if environment not in config["environments"]:
        raise ValueError("execution_environment_not_configured")
    target = config["environments"][environment]
    binding = target.get("backends", {}).get(backend)
    if binding is None:
        raise ValueError("executor_binding_missing: configure the selected environment backend " + str(backend))
    python = resolve_python(config, environment, backend) if runtime == "python" else None
    return {"environment": environment, "kind": target["kind"], "backend": backend,
            "runtime": runtime, "binding": binding, "python": python,
            "submission": resolve_submission(config, environment, backend, requested=requested),
            **({"supervisor": target.get("supervisor", "systemd")} if target["kind"] == "local" and target.get("driver") != "external" else {}),
            **{key: target[key] for key in ("ssh_host", "work_root") if key in target}}


SUBMISSION_FIELDS = {"queue", "resources", "queue_wait_seconds"}


def resolve_submission(config, environment, backend=None, *, requested=None):
    """Merge installation resource defaults; queue allowlists are permissions, not defaults."""
    target = config["environments"][environment]
    binding = target.get("backends", {}).get(backend, {})
    base = target.get("submission", {})
    override = binding.get("submission", {})
    result = {"resources": {}}
    for settings in (base, override, {} if requested is None else requested):
        validate_submission(settings, kind=target['kind'], driver=target.get('driver', 'local'))
        result = {**result, **settings, "resources": {**result['resources'], **settings.get('resources', {})}}
    return validate_submission(result, kind=target['kind'], driver=target.get('driver', 'local'),
                               allowed_queues=(target.get('allowed_queues', []), binding.get('allowed_queues', [])))


def validate_submission(result, *, kind, driver='local', allowed_queues=()):
    """Validate resolved resources; platform adapters never merge defaults."""
    _keys(result, SUBMISSION_FIELDS, "submission")
    if "queue_wait_seconds" in result and (type(result["queue_wait_seconds"]) is not int or result["queue_wait_seconds"] < 1):
        raise ValueError("queue_wait_seconds must be positive")
    queue = result.get("queue")
    if "queue" in result and (not isinstance(queue, str) or not re.fullmatch(QUEUE_PATTERN, queue)):
        raise ValueError("submission.queue is invalid")
    if kind == 'local' and driver != "external" and {'queue', 'queue_wait_seconds'} & result.keys():
        raise ValueError('local submission does not support a scheduler queue')
    for allowed in allowed_queues:
        if queue and allowed and queue not in allowed:
            raise ValueError("submission queue is not allowed")
    resources = result.get("resources", {})
    if not isinstance(resources, dict):
        raise ValueError("submission.resources must be a table")
    if set(resources) - {"cpus", "memory_mb", "gpus", "walltime", "select"}:
        raise ValueError("unsupported submission resource")
    if "gpus" in resources and driver != "external":
        raise ValueError("submission.resources.gpus requires an external target")
    if "select" in resources and (not isinstance(resources['select'], str)
            or not re.fullmatch(r'[A-Za-z0-9_=:+.-]+', resources['select'])):
        raise ValueError("submission.resources.select is invalid")
    if 'select' in resources:
        if driver != "external":
            raise ValueError('submission.resources.select requires an external target')
        if {'cpus', 'memory_mb'} & resources.keys():
            raise ValueError('use PBS select or cpus/memory_mb, not both')
    for field in ("cpus", "memory_mb", "gpus"):
        if field in resources and (type(resources[field]) is not int or resources[field] < 1):
            raise ValueError("submission.resources." + field + " must be positive")
    if "walltime" in resources:
        walltime_seconds(resources["walltime"])
    return result


def walltime_seconds(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]+:[0-5][0-9]:[0-5][0-9]", value):
        raise ValueError("submission.resources.walltime must be HH:MM:SS")
    hours, minutes, seconds = map(int, value.split(':'))
    total = hours * 3600 + minutes * 60 + seconds
    if not total:
        raise ValueError("submission.resources.walltime must be positive")
    return total


def execution_timeout(timeout, resources):
    """One effective process limit, whether the target is local or remote."""
    if 'walltime' not in resources:
        return timeout
    walltime = walltime_seconds(resources['walltime'])
    return min(timeout, walltime) if timeout is not None else walltime


def job_config_schema():
    """Generate the public editor schema from the runtime's field vocabulary."""
    def record(properties, required=()):
        return {'type': 'object', 'properties': properties, 'required': list(required), 'additionalProperties': False}
    def text(pattern=None):
        return {'type': 'string', 'minLength': 1, **({'pattern': pattern} if pattern else {})}
    def integer(maximum=None):
        return {'type': 'integer', 'minimum': 1, **({'maximum': maximum} if maximum else {})}
    absolute = text(r'^/(?!$)(?!.*(?:^|/)\.\.(?:/|$))[^\n\r\u0000]+$')
    queues = {'type': 'array', 'uniqueItems': True, 'items': text('^' + QUEUE_PATTERN + '$')}
    python = record({'manager': {'const': 'conda'}, **{key: absolute for key in ('conda_executable', 'prefix', 'lock_ref')}},
                    ('manager', 'conda_executable', 'prefix', 'lock_ref'))
    resources = record({'cpus': integer(), 'memory_mb': integer(), 'gpus': integer(),
                        'walltime': text(r'^(?!0+:00:00$)[0-9]+:[0-5][0-9]:[0-5][0-9]$'), 'select': text(r'^[A-Za-z0-9_=:+.-]+$')})
    resources['not'] = {'anyOf': [{'required': ['select', name]} for name in ('cpus', 'memory_mb')]}
    submission = record({'queue': text('^' + QUEUE_PATTERN + '$'), 'queue_wait_seconds': integer(), 'resources': resources})
    backend = record({'command': {'oneOf': [text(), {'type': 'array', 'minItems': 1, 'items': text()}]},
                      'python': python, 'activation_script': absolute, 'scratch_root': absolute,
                      'allowed_queues': queues, 'submission': submission,
                      'environment': {'type': 'object', 'propertyNames': {'pattern': r'^[A-Za-z_][A-Za-z0-9_]*$'},
                                      'additionalProperties': {'type': 'string', 'pattern': r'^[^\u0000]*$'}}})
    local_submission = {"not": {"anyOf": [{"required": [key]} for key in ("queue", "queue_wait_seconds")]},
                        "properties": {"resources": {"not": {"anyOf": [{"required": [key]} for key in ("select", "gpus")]}}}}
    target = record({"kind": {"const": "local"}, "supervisor": {"enum": ["process", "systemd"]},
                     "python": python, "submission": submission,
                     "backends": {"type": "object", "propertyNames": text("^" + NAME_PATTERN + "$"), "additionalProperties": backend}}, ("kind",))
    target["allOf"] = [{"properties": {"submission": local_submission,
        "backends": {"additionalProperties": {"properties": {"submission": local_submission}}}}}]
    legacy = record({'default_environment': text('^' + NAME_PATTERN + '$'),
                     'environments': {'type': 'object', 'minProperties': 1,
                                      'propertyNames': text('^' + NAME_PATTERN + '$'), 'additionalProperties': target}},
                    ('default_environment', 'environments'))
    execution_target = record({
        "type": {"const": "local"}, "driver": {"enum": ["local", "process", "systemd"]},
        "supervisor": {"enum": ["process", "systemd"]}, "python": python, "submission": submission,
        "bindings": {"type": "object", "propertyNames": text("^" + NAME_PATTERN + "$"), "additionalProperties": backend},
    }, ("type", "driver"))
    local_submission = {"not": {"anyOf": [{"required": [key]} for key in ("queue", "queue_wait_seconds")]},
                        "properties": {"resources": {"not": {"anyOf": [{"required": [key]} for key in ("select", "gpus")]}}}}
    execution_target["allOf"] = [{"properties": {"submission": local_submission,
        "bindings": {"additionalProperties": {"properties": {"submission": local_submission}}}}}]
    external_target = record({
        'type': {'enum': ['local', 'remote']}, 'driver': {'const': 'external'},
        'transport': {'enum': ['local', 'ssh']}, 'work_root': absolute,
        'file_mode': {'enum': ['staged', 'shared'], 'default': 'staged'},
        'handler': {'type': 'array', 'minItems': 1, 'items': text()},
        'handler_environment': backend['properties']['environment'],
        'cluster_name': text('^' + NAME_PATTERN + '$'),
        'ssh_host': text(r'^[A-Za-z0-9][A-Za-z0-9_.@:-]*$'), 'ssh_config': absolute,
        'python': python, 'submission': submission, 'bindings': execution_target['properties']['bindings'],
        'allowed_queues': queues,
        **{name: integer(limit) for name, limit in TIMEOUT_LIMITS.items()},
    }, ('driver', 'transport', 'work_root', 'handler'))
    external_target['allOf'] = [
        {'if': {'properties': {'transport': {'const': 'ssh'}}},
         'then': {'required': ['ssh_host'], 'properties': {'type': {'const': 'remote'}}},
         'else': {'properties': {'type': {'const': 'local'}}, 'not': {'anyOf': [{'required': [key]} for key in ('ssh_host', 'ssh_config')]}}},
    ]
    for schema, key in ((target, 'backends'), (execution_target, 'bindings'), (external_target, 'bindings')):
        schema.setdefault('allOf', []).append({
            'if': {'not': {'required': ['python']}},
            'then': {'properties': {key: {'additionalProperties': {
                'anyOf': [{'required': ['command']}, {'required': ['python']}]}}}},
        })
    execution = record({'default_target': text('^' + NAME_PATTERN + '$'),
                        'targets': {'type': 'object', 'minProperties': 1,
                                    'propertyNames': text('^' + NAME_PATTERN + '$'),
                                    'additionalProperties': {'oneOf': [execution_target, external_target]}}},
                       ('default_target', 'targets'))
    return {'$schema': 'https://json-schema.org/draft/2020-12/schema', 'title': 'Job installation configuration',
            'oneOf': [legacy, record({'execution': execution}, ('execution',))]}
