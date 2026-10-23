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


# This module also runs standalone during installation. Keep the built-in
# scheduler definitions here so normalization, validation and editor schemas
# share one source without importing a scheduler or its runtime dependencies.
SCHEDULERS = {
    "qrun": {"default_handler": ("qrun", "handler"),
             "unsupported_submission": ("queue",), "unsupported_resources": ("gpus", "select")},
    "pbs": {},
    "torque": {},
    "slurm": {},
    "tri": {},
    "external": {},
}
EXECUTORS = frozenset(SCHEDULERS)
CONNECTION_FIELDS = {"transport", "ssh_host", "ssh_config", *TIMEOUT_LIMITS}
SHARED_FIELDS = {"python", "bindings", "submission", "allowed_queues", "storage"}
ENTRY_FIELDS = {"executor", "handler", "handler_environment", "cluster_name", "limits", *SHARED_FIELDS}
PLATFORM_FIELDS = {"display_name", "aliases", "enabled", "default_scheduler", "schedulers", *CONNECTION_FIELDS, *SHARED_FIELDS}
STORAGE_FIELDS = {"work_root", "scratch_root", "file_mode"}


class ExecutionConfig(dict):
    """Validated configuration and its derived adapter index, never a wire format."""


def target_identity(name):
    platform, entry = name.split("/")
    return {"platform": platform, "scheduler_entry": entry}


def target_key(identity):
    _keys(identity, {"platform", "scheduler_entry"}, "execution target")
    for field in ("platform", "scheduler_entry"):
        if not isinstance(identity.get(field), str) or not re.fullmatch(NAME_PATTERN, identity[field]):
            raise ValueError("execution_target_invalid: requires platform and scheduler_entry")
    return identity["platform"] + "/" + identity["scheduler_entry"]


def _merge(platform, entry):
    from copy import deepcopy
    platform, entry = deepcopy(platform), deepcopy(entry)
    result = {key: value for key, value in platform.items() if key in CONNECTION_FIELDS | SHARED_FIELDS}
    result.update(entry)
    if platform.get("allowed_queues") and entry.get("allowed_queues") and set(entry["allowed_queues"]) - set(platform["allowed_queues"]):
        raise ValueError("scheduler queues exceed platform permissions")
    for field in ("bindings", "storage"):
        result[field] = {**platform.get(field, {}), **entry.get(field, {})}
    if "submission" in platform or "submission" in entry:
        base, override = platform.get("submission", {}), entry.get("submission", {})
        result["submission"] = {**base, **override, "resources": {**base.get("resources", {}), **override.get("resources", {})}}
    result.update(result.pop("storage", {}))
    return result


def _validate_effective_target(name, target):
    executor = target.get('executor')
    if not isinstance(executor, str) or executor not in SCHEDULERS:
        raise ValueError('executor must be one of: ' + ', '.join(SCHEDULERS))
    _keys(target, {"executor", "transport", "file_mode", "work_root", "handler", "handler_environment",
                   "cluster_name", "ssh_host", "ssh_config", "submission", "bindings", "python",
                   "allowed_queues", "scratch_root", "platform", "scheduler_entry", "limits", *TIMEOUT_LIMITS}, f"execution.platforms.{name}")
    transport = target.get('transport')
    if transport not in {'local', 'ssh'}:
        raise ValueError('executor requires transport=local or transport=ssh')
    scope = 'remote' if transport == 'ssh' else 'local'
    if 'default_handler' in SCHEDULERS[executor]:
        target.setdefault('handler', list(SCHEDULERS[executor]['default_handler']))
    for field, limit in TIMEOUT_LIMITS.items():
        if field in target and (type(target[field]) is not int or not 1 <= target[field] <= limit):
            raise ValueError(f"external target {field} must be between 1 and {limit}")
    if "ssh_config" in target:
        _absolute(target["ssh_config"], f"execution.platforms.{name}.ssh_config")
    if "allowed_queues" in target:
        _queues(target["allowed_queues"], f"execution.platforms.{name}.allowed_queues")
    if transport == "local" and {"ssh_host", "ssh_config"} & target.keys():
        raise ValueError("local transport does not use SSH settings")
    if transport == "ssh" and (not isinstance(target.get("ssh_host"), str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.@:-]*", target["ssh_host"])):
        raise ValueError("external ssh_host is invalid")
    if "cluster_name" in target and (not isinstance(target["cluster_name"], str) or not re.fullmatch(NAME_PATTERN, target["cluster_name"])):
        raise ValueError("external cluster_name is invalid")
    root = target.get("work_root")
    _absolute(root, f"execution.platforms.{name}.work_root")
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
    bindings = target.get("bindings", {})
    if not isinstance(bindings, dict):
        raise ValueError(f"execution.platforms.{name}.bindings must be a table")
    normalized = dict(target)
    normalized.update({"kind": scope, "backends": bindings})
    if "scratch_root" in normalized:
        _absolute(normalized["scratch_root"], "storage.scratch_root")
    limits = normalized.get("limits", {})
    _keys(limits, {"max_in_flight", "cpus", "memory_mb", "gpus", "walltime"}, "scheduler limits")
    for key, limit in limits.items():
        if key == "walltime":
            walltime_seconds(limit)
        elif type(limit) is not int or limit < 1:
            raise ValueError("scheduler limits must be positive")
    return normalized


def _validate_execution_config(value):
    _keys(value, {"execution"}, "job config")
    execution = value.get("execution")
    _keys(execution, {"schema_version", "default_platform", "platforms"}, "execution")
    if execution.get("schema_version") != 2:
        raise ValueError("execution.schema_version must be 2; flat targets are not supported")
    platforms = execution.get("platforms")
    if not isinstance(platforms, dict) or not platforms:
        raise ValueError("execution.platforms must define named platforms")
    default = execution.get("default_platform")
    if default not in platforms:
        raise ValueError("execution.default_platform must name a configured platform")
    targets, names = {}, {}
    for name, platform in platforms.items():
        if not re.fullmatch(NAME_PATTERN, name):
            raise ValueError("invalid platform ID: " + name)
        _keys(platform, PLATFORM_FIELDS, "platform " + name)
        aliases = platform.get("aliases", [])
        if not isinstance(aliases, list):
            raise ValueError("platform aliases must be an array")
        for alias in [name, *aliases]:
            if not isinstance(alias, str) or not re.fullmatch(NAME_PATTERN, alias):
                raise ValueError("invalid platform alias")
            folded = alias.casefold()
            if folded in names and names[folded] != name:
                raise ValueError("platform_alias_ambiguous: " + alias)
            names[folded] = name
        if "display_name" in platform and (not isinstance(platform["display_name"], str) or not platform["display_name"].strip()):
            raise ValueError("platform display_name must be nonempty")
        if type(platform.get("enabled", True)) is not bool:
            raise ValueError("platform enabled must be boolean")
        if platform.get("transport") not in {"local", "ssh"}:
            raise ValueError("platform requires local or ssh transport")
        if platform["transport"] == "ssh":
            host = platform.get("ssh_host")
            if not isinstance(host, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.@:-]*", host):
                raise ValueError("platform ssh_host is invalid")
        elif {"ssh_host", "ssh_config"} & platform.keys():
            raise ValueError("local platform does not use SSH settings")
        _keys(platform.get("storage", {}), STORAGE_FIELDS, "platform storage")
        entries = platform.get("schedulers", {})
        if not isinstance(entries, dict):
            raise ValueError("platform schedulers must be a table")
        if platform.get("enabled", True) and platform.get("default_scheduler") not in entries:
            raise ValueError("enabled platform requires a configured default_scheduler")
        for entry, raw in entries.items():
            if not re.fullmatch(NAME_PATTERN, entry):
                raise ValueError("invalid scheduler entry ID")
            _keys(raw, ENTRY_FIELDS, "scheduler " + entry)
            _keys(raw.get("storage", {}), STORAGE_FIELDS, "scheduler storage")
            key = name + "/" + entry
            effective = _merge(platform, raw)
            effective.update(platform=name, scheduler_entry=entry)
            target = _validate_effective_target(key, effective)
            if platform.get("enabled", True):
                targets[key] = target
    if not platforms[default].get("enabled", True):
        raise ValueError("default platform must be enabled")
    settings = ExecutionConfig(execution=execution, targets=targets,
        default_target=default + "/" + platforms[default]["default_scheduler"])
    for name, target in targets.items():
        _validate_bindings(settings, name, target)
    return settings


def resolve_target(settings, requested=None, *, scheduler=None):
    """Resolve one structured platform/entry selection to an internal adapter key."""
    if requested is None:
        requested = {}
    _keys(requested, {"platform", "scheduler_entry"}, "execution target")
    platforms = settings["execution"]["platforms"]
    requested_platform = requested.get("platform", settings["execution"]["default_platform"])
    matches = [name for name, platform in platforms.items()
               if requested_platform.casefold() in {name.casefold(), *(alias.casefold() for alias in platform.get("aliases", []))}]
    if len(matches) != 1 or not platforms[matches[0]].get("enabled", True):
        raise ValueError("execution_platform_unavailable: " + requested_platform)
    name = matches[0]
    entries = platforms[name]["schedulers"]
    candidates = [entry for entry in entries
                  if (not requested.get("scheduler_entry") or entry == requested["scheduler_entry"])
                  and (not scheduler or entries[entry]["executor"].casefold() == scheduler.casefold())]
    preferred = platforms[name]["default_scheduler"]
    if len(candidates) > 1 and preferred in candidates:
        candidates = [preferred]
    if len(candidates) != 1:
        raise ValueError("execution_scheduler_ambiguous_or_missing: " + name)
    return name + "/" + candidates[0]


def target_route_digest(settings, name):
    target = settings["targets"][name]
    keys = ("executor", "transport", "ssh_host", "ssh_config", "cluster_name", "work_root", "file_mode", "handler", "handler_environment")
    return binding_digest({"target": target_identity(name), **{key: target.get(key) for key in keys}})


def resolve_selection(settings, requested=None, *, scheduler=None, source_text=None):
    if source_text:
        mentioned = {executor for executor in EXECUTORS - {"external"}
                     if re.search(r"(?<![A-Za-z0-9_])" + re.escape(executor) + r"(?![A-Za-z0-9_])", source_text, re.I)}
        if len(mentioned) > 1:
            raise ValueError("execution_intent_ambiguous: quote one affirmative placement instruction")
        if mentioned:
            explicit = next(iter(mentioned))
            if scheduler and scheduler.casefold() != explicit:
                raise ValueError("execution_intent_conflict: scheduler differs from cited instruction")
            scheduler = explicit
    name = resolve_target(settings, requested, scheduler=scheduler)
    return {"target": target_identity(name), "executor": settings["targets"][name]["executor"],
            "route_digest": target_route_digest(settings, name),
            "selection_mode": "explicit" if requested or scheduler else "default"}


def bound_target(settings, requested=None, context=None):
    if not context:
        return resolve_target(settings, requested)
    if context.get("unselected"):
        raise ValueError("execution_item_required: bind the task with task_update bind_execution or select its execution plan item before preparation")
    selection = context["selection"]
    required = target_key(selection["target"])
    actual = resolve_target(settings, requested) if requested else required
    if actual != required:
        raise ValueError("execution_target_mismatch: request differs from the bound work item")
    if selection["route_digest"] != target_route_digest(settings, required):
        raise ValueError("execution_target_changed: rebind before preparing new work")
    return required


def configured_targets(settings):
    return settings["targets"]


def platform_catalog(settings):
    platforms = {}
    for name, platform in settings["execution"]["platforms"].items():
        entries = {}
        for entry, raw in platform.get("schedulers", {}).items():
            key = name + "/" + entry
            if key not in settings["targets"]:
                continue
            target = settings["targets"][key]
            entries[entry] = {"executor": target["executor"], "software": sorted(target["backends"]),
                "storage": {field: target[field] for field in STORAGE_FIELDS if field in target},
                "submission": target.get("submission", {}), "limits": target.get("limits", {}),
                "sources": {"bindings": {backend: "scheduler_entry" if backend in raw.get("bindings", {}) else "platform"
                                         for backend in target["backends"]},
                            "storage": {field: "scheduler_entry" if field in raw.get("storage", {}) else "platform"
                                        for field in STORAGE_FIELDS if field in target}}}
        platforms[name] = {"display_name": platform.get("display_name", name),
            "aliases": platform.get("aliases", []), "transport": platform["transport"],
            "enabled": platform.get("enabled", True), "default_scheduler": platform.get("default_scheduler"),
            "schedulers": entries}
    return {"default_platform": settings["execution"]["default_platform"], "platforms": platforms}


def default_target(settings):
    return settings["default_target"]


def _validate_bindings(value, name, target):
    if 'allowed_queues' in target:
        _queues(target['allowed_queues'], f"targets.{name}.allowed_queues")
    if "python" in target:
        validate_python(target["python"], f"targets.{name}.python")
    backends = target.get("backends", {})
    if not isinstance(backends, dict):
        raise ValueError(f"targets.{name}.backends must be a table")
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
            validate_python(binding["python"], f"targets.{name}.backends.{backend}.python")
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
    """Publish installer changes into the single platform configuration document."""
    import copy
    document = {"execution": copy.deepcopy(settings["execution"])}
    for name, target in settings["targets"].items():
        identity = target_identity(name)
        platform = document["execution"]["platforms"][identity["platform"]]
        entry = platform["schedulers"][identity["scheduler_entry"]]
        baseline = _merge(platform, entry)
        for field in ENTRY_FIELDS - {"storage", "bindings"}:
            if field in target and target[field] != baseline.get(field):
                entry[field] = copy.deepcopy(target[field])
        for backend, binding in target.get("backends", {}).items():
            if binding != baseline.get("bindings", {}).get(backend):
                entry.setdefault("bindings", {})[backend] = copy.deepcopy(binding)
        for field in STORAGE_FIELDS:
            if field in target and target[field] != baseline.get(field):
                entry.setdefault("storage", {})[field] = target[field]
    return document


def validate_job_config(value):
    if isinstance(value, ExecutionConfig):
        return value
    return _validate_execution_config(value)


def load_job_config(path):
    with Path(path).expanduser().open("rb") as handle:
        return validate_job_config(tomllib.load(handle))


def validate_catalog_bindings(settings, catalogs):
    """Bootstrap binding checks without importing runtime dependencies."""
    settings = validate_job_config(settings)
    results = {}
    for name, target in settings['targets'].items():
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
    target = config["targets"][environment]
    binding = target.get("backends", {}).get(backend, {}).get("python", target.get("python"))
    if binding is None:
        raise ValueError(f"python_binding_missing: configure targets.{environment}.python or backends.{backend}.python as a Conda environment")
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
    if environment not in config["targets"]:
        raise ValueError("execution_environment_not_configured")
    target = config["targets"][environment]
    binding = target.get("backends", {}).get(backend)
    if binding is None:
        raise ValueError("executor_binding_missing: configure the selected environment backend " + str(backend))
    binding = {**({"scratch_root": target["scratch_root"]} if "scratch_root" in target else {}), **binding}
    python = resolve_python(config, environment, backend) if runtime == "python" else None
    return {"environment": environment, "kind": target["kind"], "backend": backend,
            "runtime": runtime, "binding": binding, "python": python,
            "submission": resolve_submission(config, environment, backend, requested=requested),
            "executor": target["executor"], "transport": target["transport"],
            **{key: target[key] for key in ("ssh_host", "work_root") if key in target}}


SUBMISSION_FIELDS = {"queue", "resources", "queue_wait_seconds"}


def resolve_submission(config, environment, backend=None, *, requested=None):
    """Merge installation resource defaults; queue allowlists are permissions, not defaults."""
    target = config["targets"][environment]
    binding = target.get("backends", {}).get(backend, {})
    base = target.get("submission", {})
    override = binding.get("submission", {})
    result = {"resources": {}}
    for settings in (base, override, {} if requested is None else requested):
        validate_submission(settings, executor=target['executor'])
        result = {**result, **settings, "resources": {**result['resources'], **settings.get('resources', {})}}
    result = validate_submission(result,
                               allowed_queues=(target.get('allowed_queues', []), binding.get('allowed_queues', [])),
                               executor=target['executor'])
    if 'select' in result['resources'] and {'cpus', 'memory_mb', 'gpus'} & target.get('limits', {}).keys():
        raise ValueError('submission_resource_limit_unverifiable: use explicit resources with entry allocation limits')
    for key, limit in target.get('limits', {}).items():
        amount = result['resources'].get(key)
        if amount is not None and (walltime_seconds(amount) > walltime_seconds(limit) if key == 'walltime' else amount > limit):
            raise ValueError('submission_resource_limit_exceeded: ' + key)
    return result


def validate_submission(result, *, allowed_queues=(), executor=None):
    """Validate resolved resources; platform adapters never merge defaults."""
    _keys(result, SUBMISSION_FIELDS, "submission")
    if "queue_wait_seconds" in result and (type(result["queue_wait_seconds"]) is not int or result["queue_wait_seconds"] < 1):
        raise ValueError("queue_wait_seconds must be positive")
    queue = result.get("queue")
    if "queue" in result and (not isinstance(queue, str) or not re.fullmatch(QUEUE_PATTERN, queue)):
        raise ValueError("submission.queue is invalid")
    for allowed in allowed_queues:
        if queue and allowed and queue not in allowed:
            raise ValueError("submission queue is not allowed")
    resources = result.get("resources", {})
    if not isinstance(resources, dict):
        raise ValueError("submission.resources must be a table")
    if executor is not None:
        definition = SCHEDULERS[executor]
        unsupported = (set(definition.get('unsupported_submission', ())) & result.keys()
                       | set(definition.get('unsupported_resources', ())) & resources.keys())
        if unsupported:
            raise ValueError(executor.title() + ' does not support: ' + ', '.join(sorted(unsupported)))
    if set(resources) - {"cpus", "memory_mb", "gpus", "walltime", "select"}:
        raise ValueError("unsupported submission resource")
    if "select" in resources and (not isinstance(resources['select'], str)
            or not re.fullmatch(r'[A-Za-z0-9_=:+.-]+', resources['select'])):
        raise ValueError("submission.resources.select is invalid")
    if 'select' in resources:
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
    storage = record({'work_root': absolute, 'scratch_root': absolute,
                      'file_mode': {'enum': ['staged', 'shared']}})
    bindings = {'type': 'object', 'propertyNames': {'pattern': '^' + NAME_PATTERN + '$'}, 'additionalProperties': backend}
    shared = {'python': python, 'bindings': bindings, 'storage': storage,
              'submission': submission, 'allowed_queues': queues}
    limits = record({'max_in_flight': integer(), 'cpus': integer(), 'memory_mb': integer(),
                     'gpus': integer(), 'walltime': resources['properties']['walltime']})
    entry = record({**shared, 'executor': {'enum': sorted(EXECUTORS)},
                    'handler': {'type': 'array', 'minItems': 1, 'items': text()},
                    'handler_environment': backend['properties']['environment'],
                    'cluster_name': text('^' + NAME_PATTERN + '$'), 'limits': limits}, ('executor',))
    entry['allOf'] = []
    for name, definition in SCHEDULERS.items():
        scheduler_submission = {}
        if definition.get('unsupported_submission'):
            scheduler_submission['not'] = {'anyOf': [
                {'required': [key]} for key in definition['unsupported_submission']]}
        if definition.get('unsupported_resources'):
            scheduler_submission['properties'] = {'resources': {'not': {'anyOf': [
                {'required': [key]} for key in definition['unsupported_resources']]}}}
        if scheduler_submission:
            entry['allOf'].append({'if': {'properties': {'executor': {'const': name}}},
                'then': {'properties': {'submission': scheduler_submission,
                    'bindings': {'additionalProperties': {'properties': {'submission': scheduler_submission}}}}}})
    entry['allOf'].append({'if': {'properties': {'executor': {'enum': [
        name for name, definition in SCHEDULERS.items() if 'default_handler' in definition]}}},
        'else': {'required': ['handler']}})
    platform = record({**shared, 'display_name': text(), 'enabled': {'type': 'boolean'},
        'aliases': {'type': 'array', 'uniqueItems': True, 'items': text('^' + NAME_PATTERN + '$')},
        'transport': {'enum': ['local', 'ssh']},
        'ssh_host': text(r'^[A-Za-z0-9][A-Za-z0-9_.@:-]*$'), 'ssh_config': absolute,
        'default_scheduler': text('^' + NAME_PATTERN + '$'),
        'schedulers': {'type': 'object', 'propertyNames': {'pattern': '^' + NAME_PATTERN + '$'}, 'additionalProperties': entry},
        **{name: integer(limit) for name, limit in TIMEOUT_LIMITS.items()}}, ('transport',))
    platform['allOf'] = [
        {'if': {'properties': {'transport': {'const': 'ssh'}}}, 'then': {'required': ['ssh_host']},
         'else': {'not': {'anyOf': [{'required': [key]} for key in ('ssh_host', 'ssh_config')]}}},
        {'if': {'properties': {'enabled': {'const': False}}, 'required': ['enabled']},
         'else': {'required': ['schedulers', 'default_scheduler'],
                  'properties': {'schedulers': {'minProperties': 1}}}}]
    execution = record({'schema_version': {'const': 2}, 'default_platform': text('^' + NAME_PATTERN + '$'),
                        'platforms': {'type': 'object', 'minProperties': 1,
                                      'propertyNames': {'pattern': '^' + NAME_PATTERN + '$'},
                                      'additionalProperties': platform}},
                       ('schema_version', 'default_platform', 'platforms'))
    return {'$schema': 'https://json-schema.org/draft/2020-12/schema', 'title': 'Execution platforms',
            **record({'execution': execution}, ('execution',))}
