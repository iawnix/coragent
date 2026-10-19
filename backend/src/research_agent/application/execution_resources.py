"""Resolve job requirements without importing scientific libraries or scheduling work."""
import copy
import importlib.util

from research_agent.jobs.config_contract import binding_digest, resolve_binding
from research_agent.jobs.process_environment import validate_resource_environment


def contract(base, descriptor):
    path = descriptor.get('resource_contract')
    if path is None:
        return None
    # registered_entry has already checked ownership, staging and content hashes.
    spec = importlib.util.spec_from_file_location('coragent_resource_contract', base / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def resolve(settings, environment, backend, runtime, *, submission=None, requirements=None, defaults=None):
    requested = copy.deepcopy({} if submission is None else submission)
    # Validate the caller's unmerged object too: do not hide malformed requests.
    resolve_binding(settings, environment, backend, runtime=runtime, requested=requested)
    configured = resolve_binding(settings, environment, backend, runtime=runtime)
    fallback = {key: value for key, value in (defaults or {}).items() if key not in configured['submission']['resources']}
    requested['resources'] = {**fallback, **(requirements or {}), **requested.get('resources', {})}
    selected = resolve_binding(settings, environment, backend, runtime=runtime, requested=requested)
    validate_resource_environment(selected['submission']['resources'], selected['binding'].get('environment', {}))
    return selected, {'configuration_sha256': binding_digest(configured), 'submission_request': requested}


def check_program(base, descriptor, arguments, inputs, resources):
    module = contract(base, descriptor)
    if module is None:
        return list(arguments), {'status': 'unverified', 'scope': 'program internal resource use'}
    normalized, report = module.prepare(descriptor, list(arguments), inputs, resources)
    if not isinstance(normalized, list) or any(not isinstance(arg, str) or '\0' in arg for arg in normalized):
        raise ValueError('resource_contract_arguments_invalid')
    return normalized, report
