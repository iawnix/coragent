"""Entry point descriptor for tri."""
from __future__ import annotations

from typing import Any

from research_agent.jobs.remote import RemoteSSHPlatform
from research_agent.jobs.registry import PluginDescriptor

from .scheduler import TriRemoteScheduler


def descriptor() -> PluginDescriptor:
    def factory(target: dict[str, Any]) -> RemoteSSHPlatform:
        config = {**target, **target.get("options", {}), "driver": "tri", "scheduler": "tri"}
        return RemoteSSHPlatform(config, platform_name=str(target["target_name"]),
                                 scheduler=TriRemoteScheduler(config))
    return PluginDescriptor(driver="tri", scope="remote", factory=factory)
