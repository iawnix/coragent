"""Scheduler adapters used by the SSH execution plugin.

This module is the replaceable part of remote execution.  It knows scheduler
CLI syntax and state vocabulary; it does not stage files, write receipts, or
decide how a Job is collected.  A separately maintained distribution can
implement :class:`RemoteScheduler` and register its descriptor through the
``tspi.execution_plugins`` entry point group.
"""
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
                              if key in {"checkjob", "sacct"}})
        self.diagnostic_command = commands.get("checkjob")

    def probe_commands(self):
        return tuple(value for value in self.commands.values() if value)


class DirectRemoteScheduler(_CommandScheduler):
    name = "process"
    requires_queue = False

    @classmethod
    def default_commands(cls) -> dict[str, str]:
        return {}

    def submit_arguments(self, spec: "JobSpec") -> list[str]:
        return []

    def details(self, platform: Any, receipt: "JobReceipt"):
        remote_dir = str(receipt.metadata.get("remote_dir", ""))
        result = platform._run_ssh(f"test -f {shlex.quote(remote_dir + '/status.exit')}", check=False)
        return ("C" if result.returncode == 0 else "R"), {
            "scheduler_id": str(receipt.metadata.get("scheduler_id", "")),
            "observed_at": _now(), "source": "status.exit",
        }

    def cancel(self, platform: Any, scheduler_id: str):
        return platform._run_ssh(f"kill {shlex.quote(scheduler_id)}", check=False)

    def map_state(self, state):
        from research_agent.jobs.models import JobState
        return {"C": JobState.SUCCEEDED, "R": JobState.RUNNING}.get(state, JobState.UNKNOWN)


class PBSRemoteScheduler(_CommandScheduler):
    name = "pbs"

    @classmethod
    def default_commands(cls):
        return {"submit": "qsub", "status": "qstat", "cancel": "qdel"}

    def submit_arguments(self, spec):
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

    def details(self, platform, receipt):
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
                # Optional diagnosis must not erase authoritative queue state.
                details["diagnosis_error"] = str(error)[:2000]
        return state, details

    def cancel(self, platform, scheduler_id):
        return platform._run_ssh(f"{shlex.quote(self.commands['cancel'])} {shlex.quote(scheduler_id)}", check=False)

    def map_state(self, state):
        from research_agent.jobs.models import JobState
        return {"Q": JobState.QUEUED, "W": JobState.QUEUED, "H": JobState.HELD,
                "R": JobState.RUNNING, "E": JobState.RUNNING, "T": JobState.SUBMITTED}.get(state, JobState.UNKNOWN)


class TorqueRemoteScheduler(PBSRemoteScheduler):
    name = "torque"

    def submit_arguments(self, spec):
        resources = spec.metadata.get("resources", {})
        args = [self.commands["submit"], "-q", str(spec.metadata["queue"]), "-m", "n", "-r", "n",
                "-o", "logs/scheduler.stdout", "-e", "logs/scheduler.stderr"]
        if "cpus" in resources:
            args += ["-l", "nodes=1:ppn=" + str(resources["cpus"])]
        if "memory_mb" in resources:
            args += ["-l", "mem=" + str(resources["memory_mb"]) + "mb"]
        return self._walltime(args, spec)


class SlurmRemoteScheduler(_CommandScheduler):
    name = "slurm"

    @classmethod
    def default_commands(cls):
        return {"submit": "sbatch", "status": "squeue", "cancel": "scancel", "sacct": "sacct"}

    def submit_arguments(self, spec):
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

    def details(self, platform, receipt):
        scheduler_id = str(receipt.metadata["scheduler_id"])
        result = platform._run_ssh(
            f"{shlex.quote(self.commands['status'])} -j {shlex.quote(scheduler_id)} -h -o '%T|%R'", check=False)
        details = {"scheduler_id": scheduler_id, "observed_at": _now(), "source": "squeue"}
        if result.returncode == 0 and result.stdout.strip():
            state, _, reason = result.stdout.strip().partition("|")
            details.update(scheduler_state=state, scheduler_comment=reason)
            return state, details
        sacct = self.commands.get("sacct")
        if sacct:
            accounting = platform._run_ssh(
                f"{shlex.quote(sacct)} -X -n -P -j {shlex.quote(scheduler_id)} -o State,ExitCode", check=False)
            if accounting.returncode == 0 and accounting.stdout.strip():
                fields = accounting.stdout.strip().splitlines()[0].split("|")
                state = fields[0].split("+", 1)[0]
                details["scheduler_state"] = state
                if len(fields) > 1 and fields[1].split(":", 1)[0].isdigit():
                    details["exit_status"] = int(fields[1].split(":", 1)[0])
                return state, details
        details["record_missing"] = True
        return None, details

    def cancel(self, platform, scheduler_id):
        return platform._run_ssh(f"{shlex.quote(self.commands['cancel'])} {shlex.quote(scheduler_id)}", check=False)

    def map_state(self, state):
        from research_agent.jobs.models import JobState
        return {"PENDING": JobState.QUEUED, "CONFIGURING": JobState.SUBMITTED,
                "RUNNING": JobState.RUNNING, "COMPLETING": JobState.RUNNING}.get(state, JobState.UNKNOWN)


class TriRemoteScheduler(_CommandScheduler):
    name = "tri"

    @classmethod
    def default_commands(cls):
        return {"submit": "tri-submit", "status": "tri-status", "cancel": "tri-cancel"}

    def submit_arguments(self, spec):
        args = [self.commands["submit"]]
        if spec.metadata.get("queue"):
            args += ["--queue", str(spec.metadata["queue"])]
        return args

    def details(self, platform, receipt):
        scheduler_id = str(receipt.metadata["scheduler_id"])
        result = platform._run_ssh(f"{shlex.quote(self.commands['status'])} {shlex.quote(scheduler_id)}", check=False)
        details = {"scheduler_id": scheduler_id, "observed_at": _now(), "source": "tri-status"}
        state = result.stdout.strip().splitlines()[0] if result.returncode == 0 and result.stdout.strip() else None
        details.update(scheduler_state=state, record_missing=state is None)
        return state, details

    def cancel(self, platform, scheduler_id):
        return platform._run_ssh(f"{shlex.quote(self.commands['cancel'])} {shlex.quote(scheduler_id)}", check=False)

    def map_state(self, state):
        from research_agent.jobs.models import JobState
        return {"queued": JobState.QUEUED, "running": JobState.RUNNING,
                "submitted": JobState.SUBMITTED, "held": JobState.HELD}.get(str(state).lower(), JobState.UNKNOWN)


def adapter_for(config: dict[str, Any]) -> RemoteScheduler:
    name = str(config.get("scheduler", config.get("driver", "torque"))).lower()
    adapters = {"pbs": PBSRemoteScheduler, "torque": TorqueRemoteScheduler,
                "slurm": SlurmRemoteScheduler, "tri": TriRemoteScheduler,
                "process": DirectRemoteScheduler}
    try:
        return adapters[name](config)
    except KeyError as exc:
        raise ValueError(f"unsupported remote scheduler: {name}") from exc
