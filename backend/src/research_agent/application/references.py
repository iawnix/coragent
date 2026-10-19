"""Immutable prepared requests, addressed by their canonical workspace IDs."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import re

from research_agent.foundation.transactions import TransactionCoordinator, _safe_path, read_json, workspace_transaction, write_json

from research_agent.research.operational_ids import allocate_id

_REFERENCE = re.compile(r"^prepared_[1-9][0-9]*$")
_REQUEST_FIELDS = {"request_id", "work_id", "command", "platform", "execution_target", "environment", "inputs", "outputs", "metadata", "timeout_seconds", "input_artifact_ids", "submission"}


class ReferenceError(ValueError):
    def __init__(self, code, message, candidates=()):
        self.code = code
        self.candidates = list(candidates)
        suffix = f"; available references: {', '.join(self.candidates)}" if self.candidates else ""
        super().__init__(f"{code}: {message}{suffix}")


def _digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _record_path(root, ref):
    if not isinstance(ref, str) or not _REFERENCE.fullmatch(ref):
        raise ReferenceError("reference_invalid", "use an exact prepared_ref (prepared_N)")
    return _safe_path(root, f"operations/references/records/{ref}.json")


def _record(root, ref, kind):
    try:
        value = read_json(_record_path(root, ref))
    except FileNotFoundError as exc:
        raise ReferenceError("reference_not_found", f"unknown exact reference {ref}") from exc
    reservation = f"operations/identifiers/prepared/{_digest(value.get('identity'))}.json"
    try:
        allocated = read_json(_safe_path(root, reservation))['identifier']
    except FileNotFoundError as exc:
        raise ReferenceError("reference_registry_invalid", f"unregistered reference {ref}") from exc
    if (value.get("schema_version") != "research-reference/1" or value.get("ref") != ref
            or value.get("kind") != kind or allocated != ref):
        raise ReferenceError("reference_registry_invalid", f"invalid reference {ref}")
    return value


def _register(root, kind, identity, payload):
    ref = allocate_id(root, 'prepared', identity)
    path = _record_path(root, ref)
    try:
        previous = _record(root, ref, kind)
    except ReferenceError as exc:
        if exc.code != 'reference_not_found':
            raise
    else:
        if previous['payload'] != payload:
            raise ReferenceError('reference_rebinding_forbidden', f'immutable reference {ref} has different content')
        return ref
    write_json(path, {"schema_version": "research-reference/1", "ref": ref, "kind": kind,
                      "identity": identity, "payload": payload})
    return ref


def _workspace(root):
    # Reuse canonical workspace validation and the read-your-writes context.
    from research_agent.research.workspace import validate_workspace_manifest
    path = TransactionCoordinator(root).root
    validate_workspace_manifest(read_json(path / "workspace_manifest.json"), path, require_ready=True, validate_documents=False)
    return path


def read_prepared_file(root, params=None):
    """Read and pin a file once, without registering or executing anything."""
    params = params or {}
    root = _workspace(root)
    request_file = params.get("request_file")
    if not isinstance(request_file, str) or not request_file:
        raise ReferenceError("prepared_request_required", "request_file is required")
    path = Path(request_file).expanduser()
    path = (path if path.is_absolute() else root / path).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise ReferenceError("prepared_request_invalid", "request_file must be a file inside the workspace")
    encoded = path.read_bytes()
    if len(encoded) > 1_000_000:
        raise ReferenceError("prepared_request_invalid", "request_file exceeds 1 MB")
    expected = params.get("request_sha256")
    if expected is not None and hashlib.sha256(encoded).hexdigest() != expected:
        raise ReferenceError("prepared_request_changed", "prepared Job digest mismatch; inspect the current request")
    request = json.loads(encoded)
    if (not isinstance(request, dict) or set(request) - _REQUEST_FIELDS
            or not isinstance(request.get("request_id"), str) or not request["request_id"]
            or not isinstance(request.get("command"), list) or not request["command"]
            or any(not isinstance(arg, str) or not arg for arg in request["command"])):
        raise ReferenceError("prepared_request_invalid", "request must have a stable request_id and argv command")
    request.setdefault("work_id", request["request_id"])
    if not isinstance(request["work_id"], str) or not request["work_id"]:
        raise ReferenceError("prepared_request_invalid", "work_id must be a nonempty string")
    from research_agent.jobs.inputs import content_digest
    inputs = request.get("inputs", [])
    if not isinstance(inputs, list):
        raise ReferenceError("prepared_request_invalid", "inputs must be an array")
    pinned = []
    for item in inputs:
        item = {"source": item} if isinstance(item, str) else copy.deepcopy(item)
        if not isinstance(item, dict) or not isinstance(item.get("source"), str):
            raise ReferenceError("prepared_request_invalid", "each input needs a source path")
        source = Path(item["source"]).expanduser()
        source = (source if source.is_absolute() else root / source).resolve()
        if not source.exists():
            raise ReferenceError("prepared_input_missing", str(source))
        digest = content_digest(source)
        if item.get("sha256") not in {None, digest}:
            raise ReferenceError("prepared_input_changed", "an input changed; re-prepare its request")
        item.update(source=str(source), sha256=digest)
        pinned.append(item)
    request["inputs"] = pinned
    payload = {"source_path": str(path.relative_to(root)), "source_sha256": hashlib.sha256(encoded).hexdigest(),
               "request_sha256": _digest(request), "request": request}
    return payload


def register_prepared_payload(root, payload):
    """Register the resolved bytes within the caller's State transaction."""
    request = payload["request"]
    ref = _register(root, "prepared_job", _digest(payload), payload)
    return {"prepared_ref": ref, "request_id": request["request_id"], "work_id": request["work_id"],
            "request_sha256": payload["request_sha256"]}


@workspace_transaction("job.prepare")
def prepare_job(root, params=None):
    return register_prepared_payload(_workspace(root), read_prepared_file(root, params))


def resolve_prepared_job(root, params):
    """Resolve the immutable snapshot; mutable input content must still match."""
    allowed = {"prepared_ref", "timeout_seconds", "repeat", "root", "workspace_root"}
    if set(params) - allowed:
        raise ReferenceError("prepared_override_forbidden", "edit and re-prepare to change a captured request")
    with TransactionCoordinator(root).locked():
        root = _workspace(root)
        record = _record(root, params.get("prepared_ref"), "prepared_job")
        payload = record["payload"]
        request = copy.deepcopy(payload["request"])
        if _digest(payload) != record["identity"] or _digest(request) != payload["request_sha256"]:
            raise ReferenceError("prepared_snapshot_changed", "the registered request snapshot is corrupt")
        from research_agent.jobs.inputs import content_digest
        for item in request.get("inputs", []):
            source = Path(item["source"])
            if not source.exists() or content_digest(source) != item["sha256"]:
                raise ReferenceError("prepared_input_changed", "an input changed; prepare a new reference before submission")
        for key in ("timeout_seconds", "repeat"):
            if key in params:
                request[key] = copy.deepcopy(params[key])
        return request
