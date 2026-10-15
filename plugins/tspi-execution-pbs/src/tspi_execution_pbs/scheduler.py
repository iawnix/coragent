"""PBS and Torque scheduler adapters for the generic SSH platform."""
from __future__ import annotations

from datetime import datetime, timezone
import math
import re
import shlex
from typing import Any, TYPE_CHECKING

from research_agent.jobs.config_contract import execution_timeout
from research_agent.jobs.scheduler import RemoteScheduler

if TYPE_CHECKING:
    from research_agent.jobs.models import JobReceipt, JobSpec


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class _CommandScheduler(RemoteScheduler):
    @classmethod
    def default_commands(cls) -> dict[str, str]:
        return {}

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)
        commands = config.get("commands", {})
        defaults = self.default_commands()
        self.commands = {
            key: str(commands.get(key, commands.get(alias, defaults.get(key, ""))))
            for key, alias in (("submit", "qsub"), ("status", "qstat"), ("cancel", "qdel"))
        }
        self.commands.update({key: str(value) for key, value in commands.items()
                              if key in {"checkjob"}})
        self.diagnostic_command = commands.get("checkjob")

    def probe_commands(self):
        return tuple(value for value in self.commands.values() if value)


class PBSRemoteScheduler(_CommandScheduler):
    name = "pbs"

    @classmethod
    def default_commands(cls):
        return {"submit": "qsub", "status": "qstat", "cancel": "qdel"}

    def submit_arguments(self, spec: "JobSpec") -> list[str]:
        resources = spec.metadata.get("resources", {})
        args = [self.commands["submit"], "-q", str(spec.metadata["queue"]), "-m", "n", "-r", "n",
                "-o", "logs/scheduler.stdout", "-e", "logs/scheduler.stderr"]
        select = resources.get("select")
        if not select and ("cpus" in resources or "memory_mb" in resources):
            select = "1"
            if "cpus" in resources:
                select += ":ncpus=" + str(resources["cpus"])
            if "memory_mb" in resources:
                select += ":mem=" + str(resources["memory_mb"]) + "mb"
        if select:
            args += ["-l", "select=" + select]
        return self._walltime(args, spec)

    @staticmethod
    def _walltime(args, spec):
        timeout = execution_timeout(spec.timeout_seconds, spec.metadata.get("resources", {}))
        if timeout is not None:
            seconds = math.ceil(timeout)
            args += ["-l", f"walltime={seconds//3600:02}:{seconds//60%60:02}:{seconds%60:02}"]
        return args

    def details(self, platform: Any, receipt: "JobReceipt"):
        scheduler_id = str(receipt.metadata["scheduler_id"])
        result = platform._run_ssh(f"{shlex.quote(self.commands['status'])} -f {shlex.quote(scheduler_id)}", check=False)
        details = {"scheduler_id": scheduler_id, "observed_at": _now(), "source": "qstat -f"}
        if result.returncode:
            details["query_error"] = result.stderr.strip()[:2000] or "scheduler record unavailable"
            details["record_missing"] = result.returncode != 255 and bool(
                re.search(r"\bUnknown Job Id\b", result.stderr, re.IGNORECASE))
            return None, details
        fields = dict(re.findall(r"(?m)^\s*([A-Za-z_.]+)\s*=\s*(.*?)\s*$", result.stdout))
        state = fields.get("job_state")
        details.update(scheduler_state=state, queue=fields.get("queue"), scheduler_comment=fields.get("comment"))
        if fields.get("exit_status") is not None:
            details["exit_status"] = int(fields["exit_status"])
        if state in {"Q", "W", "H"} and self.diagnostic_command:
            try:
                diagnosis = platform._run_ssh(
                    f"{shlex.quote(self.diagnostic_command)} {shlex.quote(scheduler_id.split('.')[0])}", check=False)
                details["queue_diagnosis"] = (diagnosis.stdout if diagnosis.returncode == 0 else diagnosis.stderr).strip()[:8000]
                details["diagnosis_source"] = "checkjob"
            except Exception as error:
                details["diagnosis_error"] = str(error)[:2000]
        return state, details

    def cancel(self, platform: Any, scheduler_id: str):
        return platform._run_ssh(f"{shlex.quote(self.commands['cancel'])} {shlex.quote(scheduler_id)}", check=False)

    def map_state(self, state):
        from research_agent.jobs.models import JobState
        return {"Q": JobState.QUEUED, "W": JobState.QUEUED, "H": JobState.HELD,
                "R": JobState.RUNNING, "E": JobState.RUNNING, "T": JobState.SUBMITTED}.get(state, JobState.UNKNOWN)


class TorqueRemoteScheduler(PBSRemoteScheduler):
    name = "torque"

    def submit_arguments(self, spec: "JobSpec") -> list[str]:
        resources = spec.metadata.get("resources", {})
        args = [self.commands["submit"], "-q", str(spec.metadata["queue"]), "-m", "n", "-r", "n",
                "-o", "logs/scheduler.stdout", "-e", "logs/scheduler.stderr"]
        if "cpus" in resources:
            args += ["-l", "nodes=1:ppn=" + str(resources["cpus"])]
        if "memory_mb" in resources:
            args += ["-l", "mem=" + str(resources["memory_mb"]) + "mb"]
        return self._walltime(args, spec)
