"""tri scheduler adapter for the generic SSH platform."""
from __future__ import annotations

from datetime import datetime, timezone
import shlex
from typing import Any, TYPE_CHECKING

from research_agent.jobs.scheduler import RemoteScheduler

if TYPE_CHECKING:
    from research_agent.jobs.models import JobReceipt, JobSpec


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class TriRemoteScheduler(RemoteScheduler):
    name = "tri"

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)
        commands = config.get("commands", {})
        self.commands = {
            "submit": str(commands.get("submit", "tri-submit")),
            "status": str(commands.get("status", "tri-status")),
            "cancel": str(commands.get("cancel", "tri-cancel")),
        }

    def probe_commands(self):
        return tuple(value for value in self.commands.values() if value)

    def submit_arguments(self, spec: "JobSpec") -> list[str]:
        args = [self.commands["submit"]]
        if spec.metadata.get("queue"):
            args += ["--queue", str(spec.metadata["queue"])]
        return args

    def details(self, platform: Any, receipt: "JobReceipt"):
        scheduler_id = str(receipt.metadata["scheduler_id"])
        result = platform._run_ssh(f"{shlex.quote(self.commands['status'])} {shlex.quote(scheduler_id)}", check=False)
        details = {"scheduler_id": scheduler_id, "observed_at": _now(), "source": "tri-status"}
        state = result.stdout.strip().splitlines()[0] if result.returncode == 0 and result.stdout.strip() else None
        details.update(scheduler_state=state, record_missing=state is None)
        return state, details

    def cancel(self, platform: Any, scheduler_id: str):
        return platform._run_ssh(f"{shlex.quote(self.commands['cancel'])} {shlex.quote(scheduler_id)}", check=False)

    def map_state(self, state):
        from research_agent.jobs.models import JobState
        return {"queued": JobState.QUEUED, "running": JobState.RUNNING,
                "submitted": JobState.SUBMITTED, "held": JobState.HELD}.get(str(state).lower(), JobState.UNKNOWN)
