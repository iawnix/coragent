"""Compatibility loading for the generic direct remote scheduler.

PBS, Slurm, Torque, and tri implementations live in their separately
installed distributions. This module contains no scheduler-specific command
syntax; it only keeps direct process execution available and provides a
source compatibility loader for direct ``RemoteSSHPlatform`` callers.
"""
from __future__ import annotations

from datetime import datetime, timezone
from importlib import metadata
import shlex
from typing import Any

from research_agent.jobs.scheduler import RemoteScheduler
from research_agent.jobs.registry import PluginDescriptor


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class DirectRemoteScheduler(RemoteScheduler):
    """Run the wrapper directly on the SSH host without a queue."""

    name = "process"
    requires_queue = False

    def submit_arguments(self, spec):
        return []

    def details(self, platform, receipt):
        remote_dir = str(receipt.metadata.get("remote_dir", ""))
        result = platform._run_ssh(f"test -f {shlex.quote(remote_dir + '/status.exit')}", check=False)
        return ("C" if result.returncode == 0 else "R"), {
            "scheduler_id": str(receipt.metadata.get("scheduler_id", "")),
            "observed_at": _now(), "source": "status.exit",
        }

    def cancel(self, platform, scheduler_id):
        return platform._run_ssh(f"kill {shlex.quote(scheduler_id)}", check=False)

    def map_state(self, state):
        from research_agent.jobs.models import JobState
        return {"C": JobState.SUCCEEDED, "R": JobState.RUNNING}.get(state, JobState.UNKNOWN)


def _entry_points():
    try:
        entries = metadata.entry_points()
        return entries.select(group="tspi.execution_plugins") if hasattr(entries, "select") else entries.get("tspi.execution_plugins", ())
    except Exception:
        return ()


def adapter_for(config: dict[str, Any]) -> RemoteScheduler:
    """Load an installed scheduler adapter for direct platform construction.

    Normal configuration goes through :class:`ExecutionPluginRegistry`; this
    path exists only for callers that instantiate ``RemoteSSHPlatform``
    directly. The adapter itself is supplied by an external wheel.
    """
    name = str(config.get("scheduler", config.get("driver", "torque"))).lower()
    if name == "process":
        return DirectRemoteScheduler(config)
    target = {**config, "target_name": str(config.get("target_name", "remote")),
              "type": "remote", "driver": name}
    for entry in _entry_points():
        if entry.name.lower() != name:
            continue
        loaded = entry.load()
        descriptor = loaded() if callable(loaded) and not isinstance(loaded, PluginDescriptor) else loaded
        if not isinstance(descriptor, PluginDescriptor):
            raise TypeError(f"execution plugin {entry.name!r} did not return PluginDescriptor")
        platform = descriptor.factory(target)
        return platform.scheduler_adapter
    raise ValueError(f"unsupported remote scheduler or plugin is not installed: {name}")
