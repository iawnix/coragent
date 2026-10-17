"""TRI scheduler adapter for the generic SSH platform."""
from __future__ import annotations

from datetime import datetime, timezone
import json
import math
import shlex
from typing import Any, TYPE_CHECKING

from research_agent.jobs.config_contract import execution_timeout
from research_agent.jobs.scheduler import RemoteScheduler

if TYPE_CHECKING:
    from research_agent.jobs.models import JobReceipt, JobSpec


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class TriRemoteScheduler(RemoteScheduler):
    """Submit and observe jobs through the native TRI command line."""

    name = "tri"
    # TRI has no queue selector, but it is still a scheduler-backed target.
    requires_queue = False
    uses_scheduler = True

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)
        commands = config.get("commands", {})
        self.commands = {
            "submit": str(commands.get("submit", "tri_sub")),
            "status": str(commands.get("status", "tri_stat")),
            "cancel": str(commands.get("cancel", "tri_del")),
        }

    def probe_commands(self):
        return tuple(value for value in self.commands.values() if value)

    @staticmethod
    def _memory(value: object) -> str:
        return f"{int(value)}M"

    def submit_arguments(self, spec: "JobSpec") -> list[str]:
        metadata = spec.metadata
        if metadata.get("queue") or metadata.get("queue_wait_seconds"):
            raise ValueError("TRI does not support scheduler queues; remove queue settings")
        resources = metadata.get("resources", {})
        if not isinstance(resources, dict):
            resources = {}

        # Keep the durable Job identity in TRI as both its human-readable name
        # and idempotency key.  RemoteSSHPlatform appends the wrapper path.
        job_id = str(spec.job_id or "tri-job")
        args = [self.commands["submit"], "--name", job_id, "--request-id", job_id]
        if resources.get("cpus") is not None:
            args += ["--cpu", str(resources["cpus"])]
        if resources.get("memory_mb") is not None:
            args += ["--mem", self._memory(resources["memory_mb"])]
        if resources.get("gpus") is not None:
            args += ["--gpu", str(resources["gpus"])]
        node = metadata.get("node")
        if node:
            args += ["--node", str(node)]
        external_id = metadata.get("external_id")
        if external_id:
            args += ["--external-id", str(external_id)]
        timeout = execution_timeout(spec.timeout_seconds, resources)
        if timeout is not None:
            args += ["--timeout", str(math.ceil(timeout))]
        return args

    def details(self, platform: Any, receipt: "JobReceipt"):
        scheduler_id = str(receipt.metadata["scheduler_id"])
        command = f"{shlex.quote(self.commands['status'])} --json {shlex.quote(scheduler_id)}"
        result = platform._run_ssh(command, check=False)
        details = {"scheduler_id": scheduler_id, "observed_at": _now(), "source": "tri_stat --json"}
        if result.returncode:
            details["query_error"] = result.stderr.strip()[:2000] or "scheduler record unavailable"
            details["record_missing"] = True
            return None, details
        try:
            payload = json.loads(result.stdout)
        except (TypeError, ValueError, json.JSONDecodeError):
            details["query_error"] = "TRI returned invalid JSON"
            details["record_missing"] = False
            return None, details
        if not isinstance(payload, dict):
            details["query_error"] = "TRI returned an invalid task record"
            details["record_missing"] = False
            return None, details
        state = payload.get("state")
        details.update(
            scheduler_state=state,
            node=payload.get("node"),
            exit_status=payload.get("exit_code"),
            scheduler_error=payload.get("error"),
            started_at=payload.get("started_at"),
            finished_at=payload.get("finished_at"),
            record_missing=state is None,
        )
        return (str(state) if state is not None else None), details

    def cancel(self, platform: Any, scheduler_id: str):
        return platform._run_ssh(
            f"{shlex.quote(self.commands['cancel'])} --json {shlex.quote(scheduler_id)}", check=False
        )

    def map_state(self, state):
        from research_agent.jobs.models import JobState
        return {
            "wait": JobState.QUEUED, "queued": JobState.QUEUED,
            "run": JobState.RUNNING, "running": JobState.RUNNING,
            "blocked": JobState.HELD, "submitted": JobState.SUBMITTED,
            "done": JobState.SUCCEEDED, "success": JobState.SUCCEEDED,
            "succeeded": JobState.SUCCEEDED, "fail": JobState.FAILED,
            "failed": JobState.FAILED, "cancel": JobState.CANCELLED,
            "cancelled": JobState.CANCELLED, "timed_out": JobState.TIMED_OUT,
        }.get(str(state).lower(), JobState.UNKNOWN)

    def completed_with_exit(self, state: str | None, details: dict[str, Any]) -> bool:
        from research_agent.jobs.models import JobState
        return self.map_state(state) in {JobState.SUCCEEDED, JobState.FAILED, JobState.CANCELLED} and details.get("exit_status") is not None

    def cancellation_terminal(self, state: str | None, details: dict[str, Any]) -> bool:
        from research_agent.jobs.models import JobState
        return self.map_state(state) in {JobState.SUCCEEDED, JobState.FAILED, JobState.CANCELLED, JobState.TIMED_OUT}
