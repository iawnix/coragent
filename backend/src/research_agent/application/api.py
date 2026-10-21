"""Small canonical command service shared by CLI and host adapters.

The command names in this module are the public application boundary.  Pi
tools, slash commands, and CoRAgent Web are transports; they should not invent a
second research vocabulary of their own.
"""

from __future__ import annotations

import json
import re
from importlib.resources import files
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator



def _load_command_catalog() -> dict[str, Any]:
    value = json.loads(files("research_agent.application").joinpath("command_catalog.json").read_text(encoding="utf-8"))
    if value.get("schema_version") != "coragent-command-catalog/2" or not isinstance(value.get("commands"), list):
        raise RuntimeError("invalid CoRAgent command catalog")
    identities = [item.get("id") if isinstance(item, dict) else None for item in value["commands"]]
    if any(not isinstance(name, str) or not re.fullmatch(r"[a-z][a-z0-9_]*", name) for name in identities):
        raise RuntimeError("invalid command identity")
    if len(set(identities)) != len(identities):
        raise RuntimeError("duplicate command identity")
    return value


COMMAND_CATALOG = _load_command_catalog()
COMMAND_DEFINITIONS = {
    str(item["id"]): item
    for item in COMMAND_CATALOG["commands"]
    if isinstance(item, dict) and isinstance(item.get("id"), str)
}
RESEARCH_COMMANDS = frozenset(
    command for command, definition in COMMAND_DEFINITIONS.items() if definition.get("domain") == "research"
)
COMMANDS = frozenset(COMMAND_DEFINITIONS)
COMMAND_VALIDATORS = {command: Draft202012Validator(definition["schema"])
                      for command, definition in COMMAND_DEFINITIONS.items()}

class CommandError(ValueError):
    """A canonical command request is invalid or cannot be served."""


def _string(value: dict[str, Any], field: str) -> str:
    item = value.get(field)
    if not isinstance(item, str) or not item.strip():
        raise CommandError(f"{field} must be a non-empty string")
    return item.strip()


def _json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def validate_command_params(command: str, value: dict[str, Any], *, transport_fields: tuple[str, ...] = ()) -> None:
    """Reject retired/unknown fields using the catalog shared with JS transports."""
    if not isinstance(command, str) or command not in COMMANDS:
        raise CommandError(f"unsupported command: {command}")
    if not isinstance(value, dict):
        raise CommandError("command params must be an object")
    if any(any(c.isupper() for c in key) for key in value):
        raise CommandError("schema_field_invalid: command fields use snake_case")
    unsupported = sorted(set(value) - set(COMMAND_DEFINITIONS[command]["allowed"]) - set(transport_fields))
    if unsupported:
        raise CommandError(f"schema_field_invalid: {command} unsupported fields: {', '.join(unsupported)}")
    required = COMMAND_DEFINITIONS[command].get("required", [])
    missing = [key for key in required if value.get(key) is None or value.get(key) == ""]
    if missing:
        raise CommandError(f"{command} requires {', '.join(missing)}")
    parameters = {key: item for key, item in value.items() if key not in transport_fields}
    error = next(COMMAND_VALIDATORS[command].iter_errors(parameters), None)
    if error is not None:
        location = ".".join(map(str, error.absolute_path)) or "parameters"
        raise CommandError(f"schema_field_invalid: {command} {location} violates {error.validator}")


def _research_read(root, value):
    from .memory_context import read
    return read(root, **value)


def _research_search(root, value):
    from research_agent.research.retrieval import search
    return search(root, **value)


def _research_source(root, value):
    from research_agent.research.records import record_source
    return record_source(root, value)


def _research_observe(root, value):
    from research_agent.research.basis import observe
    return observe(root, value)


def _research_allocate_task(root, value):
    from research_agent.research.operational_ids import allocate_id
    return {"identifier": allocate_id(root, "task", [value["session_id"], value["request_id"]])}


def _mutation(operation):
    def invoke(root, value):
        from research_agent.research import nodes, results, views
        from research_agent.foundation.transactions import TransactionCoordinator
        from . import memory_context
        handlers = {"research_create": nodes.create, "research_update": nodes.update, "research_result": results.publish}
        with TransactionCoordinator(root).locked():
            request = dict(value)
            if operation == "research_create" and request.get("source_submission_ids"):
                resolved = memory_context.resolve_source_submission_ids(
                    root, request["source_submission_ids"], request.get("session_id"))
                request["source_refs"] = list(dict.fromkeys([*(request.get("source_refs") or []), *resolved]))
            reply = handlers[operation](root, {**request, "_reference_details": memory_context.reference_details(root, request)})
            try:
                views.render(root)
            except (OSError, ValueError) as exc:
                reply = {**reply, "view_error": str(exc)}
            return reply
    return invoke


def _job(operation):
    def invoke(root, value):
        from .execution import dispatch
        return dispatch(operation, {**value, "workspace_root": str(root)})
    return invoke


def _artifact(operation):
    def invoke(root, value):
        from .evidence import dispatch
        return dispatch(operation, {**value, "workspace_root": str(root)})
    return invoke


def _job_prepare(root, value):
    from .references import prepare_job
    return prepare_job(root, value)


def _job_resolve_prepared(root, value):
    from .references import resolve_prepared_job
    return resolve_prepared_job(root, value)


def _job_manager_assess(root, value):
    from .job_manager import assess
    return assess(root, **value)


# Command identity is shared by tools, transports and this dispatch table.
# Local handler operations are implementation details, never accepted aliases.
COMMAND_HANDLERS = {
    "research_read": _research_read,
    "research_search": _research_search,
    "research_create": _mutation("research_create"),
    "research_update": _mutation("research_update"),
    "research_result": _mutation("research_result"),
    "research_source": _research_source,
    "research_observe": _research_observe,
    "research_allocate_task": _research_allocate_task,
    "job_start": _job("start"),
    "job_status": _job("status"),
    "job_collect": _job("collect"),
    "job_cancel": _job("cancel"),
    "job_probe": _job("probe"),
    "job_reconcile": _job("reconcile"),
    "job_targets": _job("targets"),
    "job_resolve_target": _job("resolve_target"),
    "job_list": _job("list"),
    "job_prepare": _job_prepare,
    "job_resolve_prepared": _job_resolve_prepared,
    "job_manager_assess": _job_manager_assess,
    "artifact_create": _artifact("create"),
    "artifact_register": _artifact("register"),
    "artifact_read": _artifact("read"),
}
if COMMAND_HANDLERS.keys() != COMMAND_DEFINITIONS.keys():
    raise RuntimeError("command handlers do not match the installed command catalog")


def execute(command: str, root: str | Path, params: dict[str, Any] | None = None) -> dict[str, Any]:
    """Execute one canonical command. Retired dotted names are not aliases."""
    value = params if params is not None else {}
    validate_command_params(command, value)
    return COMMAND_HANDLERS[command](root, value)
