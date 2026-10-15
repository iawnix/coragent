"""Entry point descriptors for PBS and Torque."""
from __future__ import annotations

from typing import Any

from research_agent.jobs.remote import RemoteSSHPlatform
from research_agent.jobs.registry import PluginDescriptor

from .scheduler import PBSRemoteScheduler, TorqueRemoteScheduler


def _descriptor(driver: str, scheduler_type: type) -> PluginDescriptor:
    def factory(target: dict[str, Any]) -> RemoteSSHPlatform:
        config = {**target, **target.get("options", {}), "driver": driver, "scheduler": driver}
        return RemoteSSHPlatform(config, platform_name=str(target["target_name"]),
                                 scheduler=scheduler_type(config))
    return PluginDescriptor(driver=driver, scope="remote", factory=factory)


def pbs_descriptor() -> PluginDescriptor:
    return _descriptor("pbs", PBSRemoteScheduler)


def torque_descriptor() -> PluginDescriptor:
    return _descriptor("torque", TorqueRemoteScheduler)
