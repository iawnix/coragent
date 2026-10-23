"""Canonical command adapter for the generic Python job runtime."""
from __future__ import annotations
from research_agent.research.operational_ids import allocate_id

import re
import os
import json
import hashlib
import shutil
from dataclasses import replace
from pathlib import Path
from typing import Any

from research_agent.jobs.inputs import content_digest
from research_agent.jobs import JobOutput, JobManager, JobSpec, platforms_from_config
from research_agent.foundation.transactions import TransactionCoordinator, workspace_transaction, write_json

_JOB_ID = re.compile(r"^job_[1-9][0-9]*$")


_JOB_MANAGERS: dict[tuple[str, str], JobManager] = {}

def _job_config_path() -> Path:
    configured = os.environ.get("CORAGENT_JOB_CONFIG")
    if not configured:
        raise ValueError("job_config_required: configure the installation job.toml explicitly")
    config = Path(configured).expanduser()
    if not config.is_file():
        raise ValueError(f"explicit job configuration is missing: {config}")
    return config


def _job_manager(root: Path) -> JobManager:
    config = _job_config_path()
    key = (str(root), hashlib.sha256(config.read_bytes()).hexdigest())
    if key not in _JOB_MANAGERS:
        try:
            platforms, default = platforms_from_config(config)
        except (OSError, TypeError, ValueError) as exc:
            raise ValueError(f"invalid job runtime configuration: {config}: {exc}") from exc
        _JOB_MANAGERS[key] = JobManager(platforms, default=default)
    cached = _JOB_MANAGERS[key]
    return JobManager(cached.platforms, default=cached.default)


def _root(params: dict[str, Any]) -> Path:
    value = params.get("workspace_root") or params.get("root")
    if not isinstance(value, str) or not value:
        raise ValueError("workspace root is required")
    root = Path(value).expanduser().resolve()
    manifest = root / "workspace_manifest.json"
    if manifest.exists():
        from research_agent.research.workspace import validate_workspace_manifest
        from research_agent.foundation.transactions import TransactionCoordinator, read_json
        with TransactionCoordinator(root).locked():
            validate_workspace_manifest(read_json(manifest), root, require_ready=True, validate_documents=False)
    return root


class JobSelectionError(ValueError):
    def __init__(self, code, message):
        super().__init__(code + ": " + message)
        self.code = code


class JobSubmissionError(RuntimeError):
    """Dispatch was attempted; a retry must reconcile the existing identity."""

    code = "submission_ambiguous"


def _job_id(params: dict[str, Any]) -> str:
    value = params.get("job_id")
    if not isinstance(value, str) or not _JOB_ID.fullmatch(value):
        raise JobSelectionError("job_id_invalid", "use an exact job_id or event_id; query research_search")
    return value


def _resolve_selector(root, params):
    selected = []
    if params.get("job_id"):
        selected.append(_job_id(params))
    if params.get("event_id"):
        from .job_manager import validate_event
        matches = [json.loads(path.read_text()) for path in (root / "operations/monitors").glob("*/events/*.json")]
        event = next((validate_event(e) for e in matches if e["event_id"] == params["event_id"]), None)
        if not event:
            raise JobSelectionError("job_not_found", "unknown event; query monitor pending or research_read context")
        selected.append(event["job_id"])
    if not selected:
        raise JobSelectionError("job_selector_required", "supply job_id or event_id")
    if len(set(selected)) != 1:
        raise JobSelectionError("job_selector_conflict", "selectors resolve to different Jobs")
    return {**params, "job_id": selected[0]}



def _spec(root: Path, params: dict[str, Any]) -> JobSpec:
    command = params.get("command")
    if not isinstance(command, list) or not command or any(not isinstance(item, str) or not item for item in command):
        raise ValueError("job command must be a non-empty array of strings")
    job_id = _job_id(params)
    base = root / "runs" / "jobs" / job_id
    relative = Path(params.get("cwd") or ".")
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("cwd must be a relative subdirectory of the isolated Job root")
    cwd = base / relative
    cwd.mkdir(parents=True, exist_ok=True, mode=0o700)
    inputs = []
    staged_sources = {}
    destinations = set()
    for value in params.get("inputs", []):
        source = value.get("source") if isinstance(value, dict) else value
        path = Path(source)
        path = (path if path.is_absolute() else root / path).resolve()
        destination = value.get("destination", path.name) if isinstance(value, dict) else path.name
        rel = Path(destination)
        if rel.is_absolute() or ".." in rel.parts or str(rel) in {".", ""}:
            raise ValueError("input destination must stay below job cwd")
        target = (cwd / rel).resolve()
        if not target.is_relative_to(cwd.resolve()): raise ValueError("input destination escapes job cwd")
        if target in destinations or any(x in target.parents or target in x.parents for x in destinations):
            raise ValueError("input destinations overlap")
        destinations.add(target)
        if not path.exists(): raise FileNotFoundError(f"job input missing: {path}")
        before_digest = content_digest(path)
        expected_digest = value.get("sha256") if isinstance(value, dict) else None
        if expected_digest and expected_digest != before_digest:
            raise ValueError("prepared_input_changed: re-prepare the request")
        if path != target:
            if target.exists(): raise ValueError(f"input destination already exists: {destination}")
            target.parent.mkdir(parents=True, exist_ok=True)
            if path.is_dir(): shutil.copytree(path, target, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
            else: shutil.copy2(path, target)
        if content_digest(target) != before_digest:
            raise ValueError("staged_input_changed: source changed during staging")
        for original in (sorted(path.rglob('*')) if path.is_dir() else [path]):
            if original.is_file():
                staged_sources[str(original.resolve())] = content_digest(original)
        inputs.append(target)
    input_files = {str(f.relative_to(cwd)):hashlib.sha256(f.read_bytes()).hexdigest()
        for path in inputs for f in (sorted(path.rglob("*")) if path.is_dir() else [path]) if f.is_file()}
    (cwd / "input_manifest.json").write_text(json.dumps(input_files, indent=2)+"\n")
    input_basis = None
    if params.get("input_artifact_ids"):
        from research_agent.artifacts.registry import read_manifest
        artifacts = {ref: read_manifest(root, ref) for ref in params["input_artifact_ids"]}
        input_basis = {ref: row["sha256"] for ref, row in artifacts.items()}
        for ref, row in artifacts.items():
            sources = [str((root / 'artifacts' / ref / 'payload').resolve())]
            if row.get('provenance', {}).get('source_path'):
                sources.append(str((root / row['provenance']['source_path']).resolve()))
            if not any(staged_sources.get(source) == row['sha256'].removeprefix('sha256:') for source in sources):
                raise ValueError("job_input_not_staged: stage the exact declared material payload or its verified original source")
    outputs = tuple(JobOutput(
        str(row["path"]), bool(row.get("required", False)), row.get("media_type"), int(row.get("min_bytes", 0)), row.get("recursive", False)
    ) for row in params.get("outputs", []))
    process_env = params.get("environment", {})
    if not isinstance(process_env, dict):
        raise ValueError("job environment variables must be an object")
    manifest_path = root / "workspace_manifest.json"
    workspace_id = json.loads(manifest_path.read_text())["workspace_id"] if manifest_path.is_file() else params.get("workspace_id")
    if params.get("workspace_id") and params["workspace_id"] != workspace_id:
        raise ValueError("job_workspace_mismatch")
    return JobSpec(
        command=tuple(command), cwd=cwd, job_id=job_id,
        env=process_env, inputs=tuple(inputs), outputs=outputs,
        timeout_seconds=params.get("timeout_seconds"),
        metadata={**(params.get("metadata") or {}),
                  **({"input_evidence_basis": input_basis, "input_artifact_ids": params["input_artifact_ids"]} if input_basis else {}),
                  **({"work_id": params["work_id"]} if params.get("work_id") else {})}, workspace_id=workspace_id,
    )


def _receipt_path(root: Path, job_id: str) -> Path:
    intent = root / _intent_path(root, job_id)
    if intent.is_file():
        value = json.loads(intent.read_text())
        cwd = Path(value["cwd"]).resolve()
        if not cwd.is_relative_to((root / "runs" / "jobs" / job_id).resolve()):
            raise ValueError("job receipt cwd escapes job root")
        return cwd / "receipt.json"
    return root / "runs" / "jobs" / job_id / "receipt.json"


def _intent_path(root: Path, job_id: str) -> str:
    return f"operations/jobs/{job_id}.json"


def _platform_name(params: dict[str, Any]) -> str | None:
    from research_agent.jobs.config_contract import target_key
    return target_key(params["execution_target"]) if params.get("execution_target") else None


def _recorded_platform(intent):
    if intent["schema_version"] != "job_intent/4":
        raise ValueError("job_intent_version_unsupported")
    from research_agent.jobs.external import ExternalJobPlatform
    platform = ExternalJobPlatform(intent["route"], platform_name=intent["platform"])
    platform.target_config_digest = intent["target_config_digest"]
    platform.cluster_name = intent["cluster_name"]
    platform.scope = intent["target_scope"]
    platform.driver = intent["target_driver"]
    return platform


def _recorded_job_manager(root: Path, job_id: str) -> JobManager:
    """Existing Jobs use their durable route, independently of new-job settings."""
    intent = json.loads((root / _intent_path(root, job_id)).read_text())
    platform = _recorded_platform(intent)
    return JobManager({intent["platform"]: platform}, default=intent["platform"])


def _receipt(root: Path, params: dict[str, Any], *, runtime=None):
    job_id = _job_id(params)
    path = _receipt_path(root, job_id)
    if not path.is_file():
        raise FileNotFoundError(f"job receipt not found: {job_id}")
    runtime = runtime or _recorded_job_manager(root, job_id)
    return runtime.receipt_from_disk(str(path))


def dispatch(operation: str, params: dict[str, Any]) -> dict[str, Any]:
    from .api import validate_command_params
    validate_command_params("job_" + operation, params, transport_fields=("root", "workspace_root"))
    root = _root(params)
    if operation == "list":
        from .job_state import list_executions
        return list_executions(root, session_id=params.get("session_id"), user_task_id=params.get("user_task_id"),
                               limit=params.get("limit", 50), cursor=params.get("cursor"))
    preparation = None
    if operation == "start" and (params.get("prepared_ref") or params.get("request_file")):
        from research_agent.application.references import read_prepared_file, resolve_prepared_job
        transport = {key: params[key] for key in ("root", "workspace_root", "session_id", "user_task_id", "execution_context") if key in params}
        controls = {key: params[key] for key in ("timeout_seconds", "repeat", "node_id") if key in params}
        allowed = {*transport, *controls, "prepared_ref"} if params.get("prepared_ref") else {
            *transport, *controls, "request_file", "request_sha256"}
        overrides = sorted(set(params) - allowed)
        if overrides:
            raise ValueError(
                "prepared_override_forbidden: remove top-level " + ", ".join(overrides)
                + "; the prepared request already owns its execution fields and request_id/work_id. "
                "Submit request_file + request_sha256 (or prepared_ref). "
                "To change execution parameters, run the preparer again; do not strip fields from its output."
            )
        if params.get("prepared_ref"):
            request = resolve_prepared_job(root, {key: value for key, value in params.items()
                                                  if key not in {"session_id", "user_task_id", "node_id", "execution_context"}})
        else:
            if not isinstance(params.get("request_sha256"), str):
                raise ValueError("prepared_request_digest_required")
            preparation = read_prepared_file(root, params)
            request = preparation["request"]
        params = {**request, **controls, **transport}
    if operation == "resolve_target":
        from research_agent.jobs.config_contract import load_job_config, resolve_selection
        return resolve_selection(load_job_config(_job_config_path()), params.get("target"),
                                 scheduler=params.get("scheduler"),
                                 source_text=params.get("source_text"))
    if operation == "platforms":
        from research_agent.jobs.config_contract import load_job_config, platform_catalog
        return platform_catalog(load_job_config(_job_config_path()))
    if operation == "resources":
        from datetime import datetime, timezone
        from research_agent.jobs.config_contract import load_job_config, resolve_target, target_identity
        settings = load_job_config(_job_config_path())
        name = resolve_target(settings, params.get("execution_target"))
        probe = _job_manager(root).job_probe(JobSpec(command=("true",), cwd=root), platform=name)
        queue = probe.get("queue", {})
        return {"target": target_identity(name), "executor": settings["targets"][name]["executor"],
                "available": probe["available"], "observed_at": datetime.now(timezone.utc).isoformat(),
                "capacity": queue.get("capacity"), "reserved": queue.get("reserved"), "free": queue.get("free"),
                "usage": queue.get("job_usage"), "memory_enforcement": queue.get("memory_enforcement"),
                "scheduler_observation": queue or None, "error": probe.get("error")}
    if operation == "start":
        from research_agent.jobs.config_contract import bound_target, load_job_config, target_identity
        settings = load_job_config(_job_config_path())
        actual = bound_target(settings, params.get("execution_target"), params.get("execution_context"))
        params["execution_target"] = target_identity(actual)
        return _start(root, _job_manager(root), params, preparation=preparation)
    if operation == "probe":
        runtime = _job_manager(root)
        # Probe is a capability query and intentionally does not require a
        # command or a workspace job directory.
        if not params.get("command"):
            from research_agent.jobs.config_contract import load_job_config, resolve_target
            platform = resolve_target(load_job_config(_job_config_path()), params.get("execution_target"))
            if platform not in runtime.platforms:
                return {"platform": platform, "available": False, "reason": "platform adapter is not configured"}
            spec = JobSpec(command=("true",), cwd=root)
            return runtime.job_probe(spec, platform=platform)
        return runtime.job_probe(_spec(root, params), platform=_platform_name(params))
    params = _resolve_selector(root, params)
    intent_path = root / _intent_path(root, _job_id(params))
    if not intent_path.is_file():
        raise JobSelectionError("job_not_found", "unknown exact Job ID; query research_search")
    runtime = _recorded_job_manager(root, params["job_id"])
    try:
        receipt = _receipt(root, params, runtime=runtime)
    except FileNotFoundError:
        recovered = None
        if operation == "reconcile":
            intent = json.loads(intent_path.read_text())
            platform = runtime.platforms[intent["platform"]]
            recovery = getattr(platform, "recover_receipt", None)
            if recovery and (Path(intent["cwd"]) / "spec.json").is_file():
                recovered = recovery(intent["job_id"], Path(intent["cwd"]))
        if recovered is not None:
            receipt = recovered
        elif operation in {"status", "reconcile"}:
            from types import SimpleNamespace
            from .job_state import observe_execution
            intent = json.loads(intent_path.read_text())
            value = {"job_id": intent["job_id"], "state": "unknown",
                     "platform": intent["platform"], "error": "durable dispatch intent has no receipt; no automatic resubmission"}
            observe_execution(root, SimpleNamespace(**intent), value)
            return value
        else:
            raise
    value = getattr(runtime, f"job_{operation}")(receipt)
    def json_value(item):
        if hasattr(item, "value"):
            return item.value
        if hasattr(item, "__dict__"):
            return {key: json_value(val) for key, val in item.__dict__.items()}
        if isinstance(item, dict):
            return {key: json_value(val) for key, val in item.items()}
        if isinstance(item, (list, tuple)):
            return [json_value(val) for val in item]
        return item
    value = json_value(value)
    if isinstance(value, dict):
        value.setdefault("job_id", receipt.job_id)
    return _commit_result(root, {"receipt": receipt.__dict__, "value": value, "operation": operation})


@workspace_transaction("job.result_observation")
def _commit_result(root, request):
    """Publish collected evidence, its receipt and the execution view together."""
    from types import SimpleNamespace
    receipt = SimpleNamespace(**request["receipt"])
    value, operation = request["value"], request["operation"]
    if operation == "collect":
        from .evidence import dispatch as artifact_dispatch
        paths = [str(Path(receipt.cwd) / row["path"]) for row in value.get("outputs", []) if row.get("exists")]
        paths += [value[key] for key in ("stdout", "stderr") if value.get(key) and Path(value[key]).is_file()]
        value["artifacts"] = [artifact_dispatch("register", {"root":str(root), "path":path,
            "job_id":receipt.job_id}) for path in dict.fromkeys(paths)]
        value["artifacts"] = list({a["artifact_id"]: a for a in value["artifacts"]}.values())
        manifest = [{"artifact_id": a["artifact_id"], "sha256": a["sha256"]} for a in value["artifacts"]]
        output_digest = hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest()
        result_id = allocate_id(root, 'job_result', [receipt.job_id, value.get('status'), output_digest])
        from .job_state import execution_observation
        observation = execution_observation(root, receipt, value.get("status", {}))
        result_receipt = {"schema_version": "job-result/2", "receipt_id": result_id,
            "workspace_id": receipt.workspace_id, "job_id": receipt.job_id,
            **receipt.metadata.get("research_binding", {"node_id": None, "node_revision": None}),
            "execution_state": value.get("status", {}).get("state"), "execution_observation": observation,
            "execution_observation_ref": observation["observation_id"],
            "collection_state": "complete" if value.get("output_validation", {}).get("complete") else "partial",
            "artifact_refs": [a["artifact_id"] for a in value["artifacts"]], "output_manifest_digest": "sha256:" + output_digest}
        from .validators import collect_validation
        result_receipt["validator_result"] = collect_validation(receipt, value)
        write_json(root / f'operations/results/{result_id}.json', result_receipt)
        value["result_receipt"] = result_receipt
    from .job_state import observe_execution
    conflict = observe_execution(root, receipt, {**value, "_reconciled": operation == "reconcile"})
    if conflict:
        value["execution_conflict"] = conflict
    return value


def _request_digest(params):
    semantic = {k: v for k, v in params.items() if k not in {"root", "workspace_root", "session_id", "principal"}}
    return hashlib.sha256(json.dumps(semantic, sort_keys=True, default=str).encode()).hexdigest()


def _start_result(receipt, intent):
    result = {**receipt.__dict__, "command": list(receipt.command),
              **({"prepared_ref": intent["prepared_ref"]} if intent.get("prepared_ref") else {})}
    rejected = receipt.metadata.get("submission_error")
    if rejected:
        result.update(state="failed", action_outcome="not_submitted", error=rejected["message"])
    return result


def _admit_start(root, params):
    job_id = _job_id(params)
    request_id = params.get("request_id")
    if request_id:
        for path in (root / "operations/jobs").glob("*.json"):
            old = json.loads(path.read_text())
            if old.get("request_id") == request_id and old["job_id"] != job_id:
                raise ValueError("request_id_reused: existing Job " + old["job_id"])
    # A prepared/committing transaction may outlive the caller. Recover its
    # durable decision before inspecting or removing any staged input.
    # Persisted request identity is independent of the command routing name.
    intent_request_id = (request_id or f"job.start:{job_id}") + ":intent"
    coordinator = TransactionCoordinator(root)
    transaction = coordinator.get(intent_request_id)
    if transaction and transaction["state"] in {"prepared", "committing"}:
        coordinator.commit(intent_request_id)
    previous = root / _intent_path(root, job_id)
    if previous.is_file():
        old = json.loads(previous.read_text())
        fingerprint = _request_digest(params)
        if old.get("request_digest") != fingerprint: raise ValueError("job ID reused with different parameters")
        path = _receipt_path(root, job_id)
        if path.is_file(): return _start_result(_receipt(root, params), old)
        return {"job_id":job_id,"state":"unknown","error":"dispatch already attempted; reconcile before resubmitting"}


def _prepare_start(root, runtime, params, preparation=None, prepared_params=None):
    replay = _admit_start(root, params)
    if replay is not None:
        return replay
    job_id = _job_id(params)
    intent_request_id = (params.get("request_id") or f"job.start:{job_id}") + ":intent"
    coordinator = TransactionCoordinator(root)
    previous = root / _intent_path(root, job_id)
    from .execution_environment import check_configuration
    check_configuration(prepared_params)
    staging_root = root / "runs/jobs" / job_id
    marker = root / "operations/staging" / f"{job_id}.json"
    ownership = {"schema_version": "job_staging/1", "job_id": job_id,
                 "request_digest": _request_digest(params), "state": "preparing"}
    if staging_root.exists() or marker.exists():
        if marker.is_symlink() or not marker.is_file() or json.loads(marker.read_text()) != ownership:
            raise ValueError("orphan_job_directory: staging ownership is unproven; inspect before retrying")
        # Only a matching pre-dispatch marker, with no intent/receipt, proves
        # that this adapter has never launched the staged command.
        if staging_root.is_symlink() or any(staging_root.rglob("receipt.json")):
            raise ValueError("orphan_job_directory: execution evidence requires reconciliation")
        if staging_root.exists():
            shutil.rmtree(staging_root)
    write_json(marker, ownership)
    try:
        result = _stage_start(root, runtime, params, job_id, preparation, prepared_params)
    except Exception:
        transaction = coordinator.get(intent_request_id)
        if not previous.exists() and not transaction:
            if staging_root.exists():
                shutil.rmtree(staging_root)
            marker.unlink(missing_ok=True)
        raise
    marker.unlink(missing_ok=True)
    return result


def _stage_start(root, runtime, params, job_id, preparation=None, prepared_params=None):
    staging_root = root / "runs/jobs" / job_id
    if {"input_evidence_basis", "research_binding", "user_task_id", "execution_item"} & set(params.get("metadata") or {}):
        raise ValueError("job_input_basis_runtime_only: declare input_artifact_ids and stage their actual files")
    if params.get("validator_id"):
        from .validators import check_current_inputs
        check_current_inputs(root, prepared_params)
    metadata = dict(prepared_params.get('metadata') or {})
    if 'submission' in prepared_params and metadata.get('execution_binding'):
        raise ValueError('prepared_override_forbidden: resource changes require a new preparation')
    if not metadata.get('execution_binding'):
        from research_agent.jobs.config_contract import SUBMISSION_FIELDS, load_job_config, resolve_submission
        # Registered entries carry their already resolved, verified submission.
        # Raw Jobs receive the same resolver before submission fingerprint commit.
        requested = {key: value for key, value in metadata.items() if key in SUBMISSION_FIELDS}
        if 'submission' in prepared_params:
            if requested:
                raise ValueError('job_submission_ambiguous: use submission or metadata resource fields, not both')
            requested = prepared_params['submission']
        submission = resolve_submission(load_job_config(os.environ['CORAGENT_JOB_CONFIG']),
            _platform_name(prepared_params) or runtime.default,
            requested=requested)
        metadata.update(submission)
        prepared_params = {**prepared_params, 'metadata': metadata}
    context = params.get("execution_context")
    if context:
        item = context.get("item")
        if item:
            if item.get("backend") and metadata.get("execution_binding", {}).get("backend") != item["backend"]:
                raise ValueError("execution_item_backend_mismatch")
            if params.get("work_id") != item["work_id"]:
                raise ValueError("execution_work_id_mismatch")
            if not set(item["input_artifact_ids"]) <= set(params.get("input_artifact_ids", [])):
                raise ValueError("execution_dependency_inputs_missing")
            if any(metadata["resources"].get(key) != value for key, value in item["resources"].items()):
                raise ValueError("execution_item_resources_mismatch")
            metadata["execution_item"] = item
        prepared_params = {**prepared_params, "metadata": metadata}
    if params.get('node_id') is not None:
        from research_agent.research.nodes import get_node
        node = get_node(root, params['node_id'])
        metadata['research_binding'] = {'node_id': node['id'], 'node_revision': node['revision']}
        prepared_params = {**prepared_params, 'metadata': metadata}
    try:
        spec = _spec(root, prepared_params)
    except Exception:
        if staging_root.exists():
            shutil.rmtree(staging_root)
        raise
    request_id = params.get("request_id") or f"job.start:{spec.job_id}"
    input_manifest = json.loads((spec.cwd / "input_manifest.json").read_text())
    target_name = _platform_name(prepared_params) or runtime.default
    target = runtime.platforms[target_name]
    from research_agent.jobs.config_contract import load_job_config
    route = {key: value for key, value in target.config.items()
             if key in {"transport", "ssh_host", "ssh_config", "handler", "handler_environment", "work_root", "file_mode",
                        "connect_timeout_seconds", "command_timeout_seconds", "transfer_timeout_seconds"}}
    target_digest = getattr(target, "target_config_digest", None)
    target_driver = getattr(target, "driver", None)
    target_scope = getattr(target, "scope", None)
    target_cluster = getattr(target, "cluster_name", None)
    execution_content = {"command": list(spec.command), "inputs": input_manifest,
        "environment_digest": hashlib.sha256(json.dumps(dict(spec.env), sort_keys=True).encode()).hexdigest(),
        "outputs": [output.__dict__ for output in spec.outputs], "timeout_seconds": spec.timeout_seconds,
        "platform": target_name,
        "target_driver": target_driver,
        "target_scope": target_scope,
        "cluster_name": target_cluster,
        "target_config_digest": target_digest,
        "configuration": spec.metadata.get("configuration_sha256"), "resources": spec.metadata.get("resources_sha256"),
        "submission": {key: spec.metadata[key] for key in ('queue', 'queue_wait_seconds', 'resources') if key in spec.metadata},
        "execution_environment": spec.metadata.get("execution_environment", {}).get("sha256")}
    execution_fingerprint = "sha256:" + hashlib.sha256(json.dumps(execution_content, sort_keys=True).encode()).hexdigest()
    prior_intents = [json.loads(path.read_text()) for path in (root / "operations/jobs").glob("*.json")]
    from .job_state import execution as read_execution, TERMINAL
    observations = {row["job_id"]: read_execution(root, row["job_id"]) for row in prior_intents}
    def active(row):
        observation = observations[row["job_id"]]
        return observation["state"] not in TERMINAL or observation.get("execution_conflict")
    from research_agent.jobs.config_contract import load_job_config
    limit = load_job_config(os.environ["CORAGENT_JOB_CONFIG"])["targets"][target_name].get("limits", {}).get("max_in_flight")
    if limit and sum(row["platform"] == target_name and bool(active(row)) for row in prior_intents) >= limit:
        raise ValueError("execution_entry_capacity_reached")
    if context and context.get("policy"):
        owned = [row for row in prior_intents if row.get("user_task_id") == params.get("user_task_id")]
        policy = context["policy"]
        if len(owned) >= policy["max_attempts"] or sum(bool(active(row)) for row in owned) >= policy["max_in_flight"]:
            raise ValueError("execution_task_budget_reached")
        if context.get("item") and any(row.get("execution_item", {}).get("id") == context["item"]["id"] for row in owned):
            raise ValueError("execution_item_already_submitted: reconcile its existing Job")

    duplicates = [i for i in prior_intents if i.get("execution_fingerprint") == execution_fingerprint]
    repeat = params.get("repeat")
    if repeat:
        if (not isinstance(repeat, dict) or not repeat.get("reason") or not repeat.get("budget")
                or repeat.get("predecessor_job_id") not in {i["job_id"] for i in duplicates}):
            shutil.rmtree(root / "runs/jobs" / job_id)
            raise ValueError("repeat_invalid: identify an identical predecessor, reason and budget")
    elif duplicates:
        shutil.rmtree(root / "runs/jobs" / job_id)
        return {"accepted": False, "code": "duplicate_execution", "job_id": duplicates[0]["job_id"],
                "execution_fingerprint": execution_fingerprint,
                "recovery": "Reuse job_status/collect or submit repeat with predecessor_job_id, reason and budget"}

    intent = {
        "schema_version": "job_intent/4", "job_id": spec.job_id, "state": "dispatching",
        "request_id": request_id, "execution_fingerprint": execution_fingerprint,
        "fingerprint_complete": bool(spec.metadata.get("configuration_sha256") and spec.metadata.get("resources_sha256")),
        "repeat": repeat,
        "user_task_id": params.get("user_task_id"),
        **({"execution_item": context["item"]} if context and context.get("item") else {}),
        **spec.metadata.get("research_binding", {"node_id": None, "node_revision": None}),
        "request_digest": _request_digest(params),
        "command": list(spec.command), "cwd": str(spec.cwd), "workspace_id": spec.workspace_id,
        "platform": target_name,
        "target_name": target_name,
        "route": route,
        "target_driver": target_driver,
        "target_scope": target_scope,
        "cluster_name": target_cluster,
        "target_config_digest": target_digest,
    }
    # A durable dispatching intent is committed before spawning. If the
    # Agent Server dies after this point, reconcile reports unknown rather
    # than submitting the command a second time.
    prepared = _commit_dispatch(root, {"request_id": f"{request_id}:intent", "intent": intent,
        "spec": {"job_id": spec.job_id,
                 "command": list(spec.command), "metadata": dict(spec.metadata)},
        "session_id": params.get("session_id"), "preparation": preparation})
    return spec, prepared, request_id


@workspace_transaction("job.dispatch")
def _commit_dispatch(root, request):
    from types import SimpleNamespace
    from .job_state import register_execution
    from .job_manager import bind
    intent = request["intent"]
    if request.get("preparation") is not None:
        from research_agent.application.references import register_prepared_payload
        ref = register_prepared_payload(root, request["preparation"])["prepared_ref"]
        intent = {**intent, "prepared_ref": ref}
    register_execution(root, SimpleNamespace(**request["spec"]), intent["platform"])
    write_json(root / _intent_path(root, intent["job_id"]), intent)
    bind(root, intent, request.get("session_id"))
    return intent


def _start(root, runtime, params, preparation=None):
    if not params.get("request_id"):
        raise ValueError("request_id_required: supply a stable request identity")
    coordinator = TransactionCoordinator(root)
    with coordinator.locked():
        params = {**params, "job_id": allocate_id(root, "job", params["request_id"])}
        replay = _admit_start(root, params)
    if replay is not None:
        return replay
    # Target subprocesses and SSH must never hold the State transaction lock.
    if params.get("validator_id"):
        from .validators import prepare
        prepared_params = prepare(root, params)
    else:
        if (params.get("metadata") or {}).get("validator"):
            raise ValueError("validator_source_forbidden: use a registered validator_id")
        prepared_params = params
    from .execution_environment import check_binding
    # Validator expansion just observed the target; file/ref submissions carry
    # an older observation and require a new probe here.
    check_binding(prepared_params, probe=not bool(params.get("validator_id")))
    runtime = _job_manager(root)
    with coordinator.locked():
        prepared = _prepare_start(root, runtime, params, preparation, prepared_params)
    if isinstance(prepared, dict):
        return prepared
    spec, intent, request_id = prepared
    receipt = None
    try:
        receipt = runtime.job_start(spec, platform=intent["platform"])
        result = _start_result(receipt, intent)
        committed = {**intent, "state": result.get("state", "submitted"), "receipt": result}
        coordinator.commit_files(f"{request_id}:receipt", "job.receipt", result, writes={_intent_path(root, spec.job_id): committed}, result=result)
        from .job_manager import bind
        bind(root, committed, params.get("session_id"))
        return result
    except Exception as error:
        if receipt is None:
            failed = {**intent, "state": "unknown", "error": str(error)}
            try:
                coordinator.commit_files(f"{request_id}:failed", "job.dispatch_failed", params, writes={_intent_path(root, spec.job_id): failed}, result=failed)
            except Exception:
                pass  # The durable dispatch intent still prevents resubmission.
        failure = JobSubmissionError(
            f"submission_ambiguous: job {spec.job_id}: submission outcome requires reconciliation: {error}")
        failure.details = {"job_id": spec.job_id, "recovery": "job_reconcile",
                           "action_outcome": "unknown", "retryable_without_change": False}
        if isinstance(getattr(error, "details", None), dict):
            failure.details["handler_error"] = error.details
        raise failure from error
