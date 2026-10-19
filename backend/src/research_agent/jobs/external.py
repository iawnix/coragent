"""Durable external tasks observed through an installation-selected JSON command."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shlex
import subprocess
import tempfile

from .config_contract import SUBMISSION_FIELDS, validate_submission
from .models import JobReceipt, JobState, JobStatus
from .process_environment import validate_environment
from .staged import StagedJobPlatform, _now


PROTOCOL = "coragent-external-job/1"
TERMINAL = {JobState.SUCCEEDED, JobState.FAILED, JobState.CANCELLED, JobState.TIMED_OUT}


class ExternalJobPlatform(StagedJobPlatform):
    """The handler owns native CLI syntax; this platform owns Job lifecycle."""

    def __init__(self, config, *, platform_name="external"):
        config = {**config, **config.get("options", {})}
        handler = config.get("handler")
        if (not isinstance(handler, list) or not handler or
                any(not isinstance(arg, str) or not arg or "\0" in arg for arg in handler)):
            raise ValueError("external target requires a handler argv")
        self.handler = handler
        self.handler_environment = config.get("handler_environment", {})
        if not isinstance(self.handler_environment, dict):
            raise ValueError("handler_environment must be a table")
        validate_environment(self.handler_environment)
        transport = config.get("transport", "ssh" if config.get("type") == "remote" else "local")
        if transport not in {"local", "ssh"}:
            raise ValueError("external transport must be local or ssh")
        root = config.get("work_root")
        if not isinstance(root, str) or not Path(root).is_absolute():
            raise ValueError("external target requires an absolute work_root")
        super().__init__({**config, "transport": transport}, platform_name=platform_name)

    def _invoke(self, request):
        variables = [f"{key}={value}" for key, value in self.handler_environment.items()]
        argv = ["env", *variables, *self.handler]
        script = "printf '%s' " + shlex.quote(json.dumps(request)) + " | " + shlex.join(argv)
        result = self.run_command(script, check=False)
        if result.returncode:
            raise RuntimeError("external handler failed: " + result.stderr.strip()[:2000])
        value = json.loads(result.stdout)
        if not isinstance(value, dict) or value.get("schema_version") != PROTOCOL:
            raise ValueError("invalid external handler response")
        return value

    def probe(self, spec):
        missing = [str(path) for path in spec.inputs if not path.exists()]
        try:
            result = self.run_command(f"test -d {shlex.quote(self.remote_root)} && test -w {shlex.quote(self.remote_root)}", check=False)
            observation = self._invoke({"schema_version": PROTOCOL, "action": "probe"})
            available = result.returncode == 0 and observation.get("available") is True
            error = None if available else observation.get("error", "execution root or handler unavailable")
        except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
            available, error = False, str(exc)
        return {"platform": self.name, "available": available, "transport": self.transport.name,
                "work_root": self.remote_root, "cwd_exists": spec.cwd.is_dir(),
                "inputs_present": not missing, "missing_inputs": missing, "error": error}

    @staticmethod
    def _identity(value):
        identity = value.get("scheduler_id")
        if not isinstance(identity, str) or not identity or len(identity) > 256 or "\0" in identity:
            raise ValueError("external handler returned no valid scheduler_id; reconcile before retrying")
        return identity

    def start(self, spec):
        validate_submission({key: value for key, value in spec.metadata.items() if key in SUBMISSION_FIELDS},
                            kind="local", driver="external",
                            allowed_queues=(self.allowed_queues,))
        if any((spec.cwd / name).exists() for name in ("receipt.json", "spec.json")):
            raise ValueError("job directory already contains an execution; reconcile instead of resubmitting")
        probe = self.probe(spec)
        if not all(probe[key] for key in ("available", "cwd_exists", "inputs_present")):
            raise ValueError(f"external execution probe failed: {probe}")
        directory = self._remote_dir(spec)
        wrapper, scratch, timeout = self._wrapper(spec, directory,
            inherit_environment=("CUDA_VISIBLE_DEVICES", "NVIDIA_VISIBLE_DEVICES"))
        identity = hashlib.sha256(json.dumps([self.name, spec.workspace_id, str(spec.cwd.resolve()), spec.job_id]).encode()).hexdigest()
        request = {"schema_version": PROTOCOL, "action": "submit", "job_id": spec.job_id,
                   "request_id": "coragent-" + identity, "cwd": directory,
                   "script": directory + "/.coragent/run.sh", "resources": spec.metadata.get("resources", {}),
                   "queue": spec.metadata.get("queue"), "timeout_seconds": timeout}
        metadata = {**spec.metadata, "remote_dir": directory, "scratch_path": scratch,
                    "execution_timeout_seconds": timeout, "external_request": request,
                    "transport": self.transport.name, "driver": "external", "target_name": self.name,
                    "scope": getattr(self, "scope", "local"), "cluster_name": getattr(self, "cluster_name", None),
                    "target_config_digest": getattr(self, "target_config_digest", None)}
        self._write(spec.cwd / "spec.json", {"command": list(spec.command), "cwd": str(spec.cwd),
                    "outputs": [output.__dict__ for output in spec.outputs], "metadata": metadata,
                    "workspace_id": spec.workspace_id, "remote_dir": directory})
        self.stage_inputs(spec)
        with tempfile.NamedTemporaryFile("w", dir=spec.cwd, delete=False) as stream:
            path = Path(stream.name)
            stream.write(wrapper)
        try:
            self.transport.copy(path, request["script"])
        finally:
            path.unlink(missing_ok=True)
        self.run_command("chmod 700 " + shlex.quote(request["script"]))
        value = self._invoke(request)
        return self._receipt(spec.job_id, spec.cwd, self._identity(value), metadata, spec.command, spec.workspace_id)

    def _receipt(self, job_id, cwd, scheduler_id, metadata, command, workspace_id):
        receipt = JobReceipt(job_id, self.name, _now(), tuple(command), str(cwd), None,
                             {**metadata, "scheduler_id": scheduler_id}, workspace_id)
        self._write(Path(cwd) / "receipt.json", receipt.__dict__)
        return receipt

    def _check_target(self, metadata):
        recorded = metadata.get("target_config_digest")
        if recorded != getattr(self, "target_config_digest", None):
            raise ValueError("external target configuration changed; restore the original target to reconcile")

    def recover_receipt(self, job_id, cwd):
        spec = json.loads((cwd / "spec.json").read_text())
        metadata = spec["metadata"]
        self._check_target(metadata)
        request = metadata["external_request"]
        if request["job_id"] != job_id:
            raise ValueError("external recovery identity mismatch")
        value = self._invoke({**request, "action": "recover"})
        if value.get("found") is False:
            return None
        return self._receipt(job_id, cwd, self._identity(value), {**metadata, "recovered": True},
                             spec["command"], spec.get("workspace_id"))

    def _request(self, receipt, action):
        self._check_target(receipt.metadata)
        return {**receipt.metadata["external_request"], "action": action,
                "scheduler_id": receipt.metadata["scheduler_id"]}

    def status(self, receipt):
        try:
            self._check_target(receipt.metadata)
            path = Path(receipt.cwd) / "status.json"
            if path.exists():
                saved = json.loads(path.read_text())
                if saved.get("job_id") == receipt.job_id and JobState(saved["state"]) in TERMINAL:
                    return JobStatus(**{**saved, "state": JobState(saved["state"])})
            value = self._invoke(self._request(receipt, "status"))
            if self._identity(value) != receipt.metadata["scheduler_id"]:
                raise ValueError("external status identity mismatch")
            state = JobState(value["state"])
            if state == JobState.COLLECTED:
                raise ValueError("collection is owned by the Job runtime")
            if state == JobState.CREATED:
                raise ValueError("external task has not been submitted")
            if not isinstance(value.get("diagnostics", {}), dict):
                raise ValueError("external diagnostics must be an object")
            code = value.get("exit_code")
            if code is not None and type(code) is not int:
                raise ValueError("external exit_code must be an integer")
            if state in TERMINAL and value.get("execution_finished") is not True:
                raise ValueError("external terminal state lacks execution_finished confirmation")
            if state == JobState.SUCCEEDED and code != 0:
                raise ValueError("external success requires exit code zero")
            status = JobStatus(receipt.job_id, state, self.name, exit_code=code,
                               started_at=value.get("started_at"), finished_at=value.get("finished_at"),
                               error=value.get("error"), diagnostics=value.get("diagnostics", {}))
            if state in TERMINAL:
                self._persist(receipt, status)
            return status
        except (OSError, ValueError, KeyError, TypeError, RuntimeError, subprocess.SubprocessError) as exc:
            return JobStatus(receipt.job_id, JobState.UNKNOWN, self.name, error=str(exc))

    def cancel(self, receipt):
        current = self.status(receipt)
        if current.state in TERMINAL:
            return current
        if not self._cancellation_acknowledged(receipt):
            try:
                value = self._invoke(self._request(receipt, "cancel"))
                if self._identity(value) != receipt.metadata["scheduler_id"] or value.get("accepted") is not True:
                    raise ValueError("external cancellation was not acknowledged")
                self._write(Path(receipt.cwd) / "cancel.request", {"schema_version": "external-cancellation/1",
                            "scheduler_id": receipt.metadata["scheduler_id"], "acknowledged_at": _now()})
            except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
                return JobStatus(receipt.job_id, JobState.UNKNOWN, self.name, error=str(exc))
        return self.status(receipt)

    def collect(self, receipt):
        # Even a cached terminal status must collect from its original target.
        self._check_target(receipt.metadata)
        return super().collect(receipt)
