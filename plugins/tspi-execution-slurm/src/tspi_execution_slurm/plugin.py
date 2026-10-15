"""Entry point descriptor for Slurm."""
from __future__ import annotations

from typing import Any

from research_agent.jobs.remote import RemoteSSHPlatform
from research_agent.jobs.registry import PluginDescriptor

from .scheduler import SlurmRemoteScheduler


def descriptor() -> PluginDescriptor:
    def factory(target: dict[str, Any]) -> RemoteSSHPlatform:
        config = {**target, **target.get("options", {}), "driver": "slurm", "scheduler": "slurm"}
        return RemoteSSHPlatform(config, platform_name=str(target["target_name"]),
                                 scheduler=SlurmRemoteScheduler(config))
    return PluginDescriptor(driver="slurm", scope="remote", factory=factory)
