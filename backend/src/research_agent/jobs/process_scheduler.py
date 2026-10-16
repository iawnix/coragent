"""Scheduler adapter for the explicit remote process execution target."""
from __future__ import annotations

from datetime import datetime, timezone
import shlex
from typing import Any

from .scheduler import RemoteScheduler


class ProcessRemoteScheduler(RemoteScheduler):
    """Run a remote wrapper directly without a queue manager."""

    name = "process"
    requires_queue = False

    def submit_arguments(self, spec):
        return []

    def details(self, platform, receipt):
        remote_dir = str(receipt.metadata.get("remote_dir", ""))
        result = platform._run_ssh(f"test -f {shlex.quote(remote_dir + '/status.exit')}", check=False)
        return ("C" if result.returncode == 0 else "R"), {
            "scheduler_id": str(receipt.metadata.get("scheduler_id", "")),
            "observed_at": datetime.now(timezone.utc).isoformat(),
            "source": "status.exit",
        }

    def cancel(self, platform, scheduler_id):
        return platform._run_ssh(f"kill {shlex.quote(scheduler_id)}", check=False)

    def map_state(self, state):
        from .models import JobState
        return {"C": JobState.SUCCEEDED, "R": JobState.RUNNING}.get(state, JobState.UNKNOWN)
