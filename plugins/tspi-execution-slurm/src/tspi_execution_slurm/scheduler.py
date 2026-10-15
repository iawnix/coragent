"""Slurm scheduler adapter for the generic SSH platform."""
from __future__ import annotations

from datetime import datetime, timezone
import math
import shlex
from typing import Any, TYPE_CHECKING

from research_agent.jobs.config_contract import execution_timeout
from research_agent.jobs.scheduler import RemoteScheduler

if TYPE_CHECKING:
    from research_agent.jobs.models import JobReceipt, JobSpec


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class SlurmRemoteScheduler(RemoteScheduler):
    name = "slurm"

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)
        commands = config.get("commands", {})
        self.commands = {
            "submit": str(commands.get("submit", "sbatch")),
            "status": str(commands.get("status", "squeue")),
            "cancel": str(commands.get("cancel", "scancel")),
            "sacct": str(commands.get("sacct", "sacct")),
        }

    def probe_commands(self):
        return tuple(value for value in self.commands.values() if value)

    def submit_arguments(self, spec: "JobSpec") -> list[str]:
        resources = spec.metadata.get("resources", {})
        args = [self.commands["submit"], "--parsable", "--job-name=" + spec.job_id,
                "--output=logs/scheduler.stdout", "--error=logs/scheduler.stderr"]
        if spec.metadata.get("queue"):
            args += ["--partition=" + str(spec.metadata["queue"])]
        if resources.get("cpus"):
            args += ["--cpus-per-task=" + str(resources["cpus"])]
        if resources.get("memory_mb"):
            args += ["--mem=" + str(resources["memory_mb"])]
        timeout = execution_timeout(spec.timeout_seconds, resources)
        if timeout is not None:
            args += ["--time=" + str(math.ceil(timeout / 60))]
        return args

    def details(self, platform: Any, receipt: "JobReceipt"):
        scheduler_id = str(receipt.metadata["scheduler_id"])
        result = platform._run_ssh(
            f"{shlex.quote(self.commands['status'])} -j {shlex.quote(scheduler_id)} -h -o '%T|%R'", check=False)
        details = {"scheduler_id": scheduler_id, "observed_at": _now(), "source": "squeue"}
        if result.returncode == 0 and result.stdout.strip():
            state, _, reason = result.stdout.strip().partition("|")
            details.update(scheduler_state=state, scheduler_comment=reason)
            return state, details
        accounting = platform._run_ssh(
            f"{shlex.quote(self.commands['sacct'])} -X -n -P -j {shlex.quote(scheduler_id)} -o State,ExitCode", check=False)
        if accounting.returncode == 0 and accounting.stdout.strip():
            fields = accounting.stdout.strip().splitlines()[0].split("|")
            state = fields[0].split("+", 1)[0]
            details["scheduler_state"] = state
            if len(fields) > 1 and fields[1].split(":", 1)[0].isdigit():
                details["exit_status"] = int(fields[1].split(":", 1)[0])
            return state, details
        details["record_missing"] = True
        return None, details

    def cancel(self, platform: Any, scheduler_id: str):
        return platform._run_ssh(f"{shlex.quote(self.commands['cancel'])} {shlex.quote(scheduler_id)}", check=False)

    def map_state(self, state):
        from research_agent.jobs.models import JobState
        return {"PENDING": JobState.QUEUED, "CONFIGURING": JobState.SUBMITTED,
                "RUNNING": JobState.RUNNING, "COMPLETING": JobState.RUNNING}.get(state, JobState.UNKNOWN)
