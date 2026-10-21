"""Durable external tasks observed through an installation-selected JSON command."""
from __future__ import annotations

import hashlib
import json
import os
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


class ExternalHandlerError(RuntimeError):
    def __init__(self, error):
        self.details = error
        super().__init__(error['code'] + ': ' + error['message'])


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
        if isinstance(value.get('error'), dict):
            error = value['error']
            if (not isinstance(error.get('code'), str) or not isinstance(error.get('message'), str)
                    or type(error.get('retryable')) is not bool
                    or error.get('action_outcome') not in {'unknown', 'not_submitted'}):
                raise ValueError('invalid external handler error')
            raise ExternalHandlerError(error)
        return value

    def probe(self, spec):
        missing = [str(path) for path in spec.inputs if not path.exists()]
        try:
            result = self.run_command(f"test -d {shlex.quote(self.remote_root)} && test -w {shlex.quote(self.remote_root)}", check=False)
            if self.shared:
                self.shared.probe(spec.cwd)
            observation = self._invoke({"schema_version": PROTOCOL, "action": "probe"})
            available = result.returncode == 0 and observation.get("available") is True
            error = None if available else observation.get("error", "execution root or handler unavailable")
        except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
            available, error = False, str(exc)
        return {"platform": self.name, "available": available, "transport": self.transport.name,
                "work_root": self.remote_root, "file_mode": self.file_mode, "cwd_exists": spec.cwd.is_dir(),
                "inputs_present": not missing, "missing_inputs": missing, "error": error}

    @staticmethod
    def _identity(value):
        identity = value.get("scheduler_id")
        if not isinstance(identity, str) or not identity or len(identity) > 256 or "\0" in identity:
            raise ValueError("external handler returned no valid scheduler_id; reconcile before retrying")
        return identity

    def start(self, spec):
        # Existing execution evidence never proves that a submission is new.
        if any((spec.cwd / name).exists() for name in ("receipt.json", "spec.json")):
            raise ValueError("job directory already contains an execution; reconcile instead of resubmitting")
        try:
            request, metadata = self._prepare_submission(spec)
        except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
            # No submit action has been invoked. A probe/copy failure cannot
            # hide acceptance by the scheduler, even if its transport failed.
            return self._not_submitted(spec, {
                'code': 'submission_preparation_failed', 'message': str(exc),
                'retryable': False, 'action_outcome': 'not_submitted', 'phase': 'preparation'})
        try:
            value = self._invoke(request)
        except ExternalHandlerError as exc:
            if exc.details['action_outcome'] != 'not_submitted':
                raise
            return self._not_submitted(spec, exc.details)
        return self._receipt(spec.job_id, spec.cwd, self._identity(value), metadata, spec.command, spec.workspace_id)

    def _prepare_submission(self, spec):
        validate_submission({key: value for key, value in spec.metadata.items() if key in SUBMISSION_FIELDS},
                            kind="local", driver="external",
                            allowed_queues=(self.allowed_queues,))
        probe = self.probe(spec)
        if not all(probe[key] for key in ("available", "cwd_exists", "inputs_present")):
            raise ValueError(f"external execution probe failed: {probe}")
        directory = self._remote_dir(spec)
        wrapper, scratch, timeout = self._wrapper(spec, directory,
            inherit_environment=("CUDA_VISIBLE_DEVICES", "NVIDIA_VISIBLE_DEVICES"))
        # In shared mode prepare only private execution controls; the ordinary
        # Job API has already placed immutable inputs in this directory.
        storage = self.stage_inputs(spec) if self.shared else {}
        if self.shared:
            wrapper = '#!/bin/sh\n' + self.shared.guard(directory, storage['shared_token']) + wrapper.removeprefix('#!/bin/sh\n')
        identity = hashlib.sha256(json.dumps([self.name, spec.workspace_id, str(spec.cwd.resolve()), spec.job_id]).encode()).hexdigest()
        request = {"schema_version": PROTOCOL, "action": "submit", "job_id": spec.job_id,
                   "request_id": "coragent-" + identity, "cwd": directory,
                   "script": directory + "/.coragent/run.sh", "resources": spec.metadata.get("resources", {}),
                   "queue": spec.metadata.get("queue"), "timeout_seconds": timeout}
        metadata = {**spec.metadata, **storage, "file_mode": self.file_mode, "remote_dir": directory, "scratch_path": scratch,
                    "execution_timeout_seconds": timeout, "external_request": request,
                    "transport": self.transport.name, "driver": "external", "target_name": self.name,
                    "scope": getattr(self, "scope", "local"), "cluster_name": getattr(self, "cluster_name", None),
                    "target_config_digest": getattr(self, "target_config_digest", None)}
        self._write(spec.cwd / "spec.json", {"command": list(spec.command), "cwd": str(spec.cwd),
                    "outputs": [output.__dict__ for output in spec.outputs], "metadata": metadata,
                    "workspace_id": spec.workspace_id, "remote_dir": directory})
        if not self.shared:
            self.stage_inputs(spec)
        with tempfile.NamedTemporaryFile("w", dir=spec.cwd, delete=False) as stream:
            path = Path(stream.name)
            stream.write(wrapper)
        try:
            if self.shared:
                os.replace(path, request['script'])
                os.chmod(request['script'], 0o700)
            else:
                self.transport.copy(path, request["script"])
        finally:
            path.unlink(missing_ok=True)
        if not self.shared:
            self.run_command("chmod 700 " + shlex.quote(request["script"]))
        return request, metadata

    def _not_submitted(self, spec, error):
        path = spec.cwd / 'spec.json'
        saved = json.loads(path.read_text()) if path.exists() else {
            'job_id': spec.job_id, 'command': list(spec.command), 'cwd': str(spec.cwd),
            'outputs': [output.__dict__ for output in spec.outputs],
            'workspace_id': spec.workspace_id, 'metadata': {
                **spec.metadata, 'file_mode': self.file_mode, 'driver': 'external',
                'target_name': self.name, 'transport': self.transport.name,
                'target_config_digest': getattr(self, 'target_config_digest', None)}}
        metadata = {**saved['metadata'], 'submission_error': error}
        # Save evidence before the receipt so an interrupted receipt write can
        # recover locally, without contacting an unavailable submission host.
        self._write(path, {**saved, 'metadata': metadata})
        receipt = self._receipt(spec.job_id, spec.cwd, None, metadata, spec.command, spec.workspace_id)
        self._persist(receipt, self.status(receipt))
        return receipt

    def _receipt(self, job_id, cwd, scheduler_id, metadata, command, workspace_id):
        receipt = JobReceipt(job_id, self.name, _now(), tuple(command), str(cwd), None,
                             {**metadata, "scheduler_id": scheduler_id}, workspace_id)
        self._write(Path(cwd) / "receipt.json", receipt.__dict__)
        return receipt

    def _check_target(self, metadata):
        if metadata.get('file_mode', 'staged') != self.file_mode:
            raise ValueError('external file_mode changed; restore the original target to reconcile')
        recorded = metadata.get("target_config_digest")
        if recorded != getattr(self, "target_config_digest", None):
            raise ValueError("external target configuration changed; restore the original target to reconcile")

    def recover_receipt(self, job_id, cwd):
        spec = json.loads((cwd / "spec.json").read_text())
        metadata = spec["metadata"]
        self._check_target(metadata)
        recorded_id = spec.get('job_id') or metadata.get('external_request', {}).get('job_id')
        if recorded_id != job_id:
            raise ValueError("external recovery identity mismatch")
        if metadata.get('submission_error'):
            return self._receipt(job_id, cwd, None, metadata, spec['command'], spec.get('workspace_id'))
        request = metadata["external_request"]
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
            rejected = receipt.metadata.get('submission_error')
            if rejected:
                return JobStatus(receipt.job_id, JobState.FAILED, self.name, finished_at=receipt.submitted_at,
                                 error=rejected['message'], diagnostics={'submission_error': rejected})
            path = Path(receipt.cwd) / "status.json"
            if path.exists():
                saved = json.loads(path.read_text())
                if saved.get("job_id") == receipt.job_id and JobState(saved["state"]) in TERMINAL:
                    if self.shared and JobState(saved['state']) == JobState.SUCCEEDED:
                        self.shared.check_receipt(receipt, success=True)
                    return JobStatus(**{**saved, "state": JobState(saved["state"])})
            value = self._invoke(self._request(receipt, "status"))
            if self._identity(value) != receipt.metadata["scheduler_id"]:
                raise ValueError("external status identity mismatch")
            state = JobState(value["state"])
            if state == JobState.COLLECTED:
                raise ValueError("collection is owned by the Job manager")
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
            if self.shared and state == JobState.SUCCEEDED:
                self.shared.check_receipt(receipt, success=True)
            status = JobStatus(receipt.job_id, state, self.name, exit_code=code,
                               started_at=value.get("started_at"), finished_at=value.get("finished_at"),
                               error=value.get("error"), diagnostics=value.get("diagnostics", {}))
            if state in TERMINAL:
                self._persist(receipt, status)
            return status
        except ExternalHandlerError as exc:
            return JobStatus(receipt.job_id, JobState.UNKNOWN, self.name, error=str(exc),
                             diagnostics={'handler_error': exc.details})
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
            except ExternalHandlerError as exc:
                return JobStatus(receipt.job_id, JobState.UNKNOWN, self.name, error=str(exc),
                                 diagnostics={'handler_error': exc.details})
            except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
                return JobStatus(receipt.job_id, JobState.UNKNOWN, self.name, error=str(exc))
        return self.status(receipt)

    def collect(self, receipt):
        # Even a cached terminal status must collect from its original target.
        self._check_target(receipt.metadata)
        if receipt.metadata.get('submission_error'):
            # Nothing executed, so no staged input is a produced output. Do not
            # contact storage/SSH or require a successfully prepared shared token.
            declared = json.loads((Path(receipt.cwd) / 'spec.json').read_text()).get('outputs', [])
            outputs = [{'path': item['path'], 'required': item.get('required', False), 'exists': False}
                       for item in declared]
            errors = [{'path': item['path'], 'error': 'not_submitted'} for item in outputs if item['required']]
            return {'job_id': receipt.job_id, 'status': self.status(receipt).__dict__, 'outputs': outputs,
                    'output_validation': {'complete': not errors, 'errors': errors},
                    'stdout': str(Path(receipt.cwd) / 'logs/stdout.log'),
                    'stderr': str(Path(receipt.cwd) / 'logs/stderr.log')}
        return super().collect(receipt)
