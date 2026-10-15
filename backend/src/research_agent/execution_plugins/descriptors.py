"""Built-in scheduler plugin descriptors.

The descriptors are kept beside the adapters so ``jobs.config`` does not
contain scheduler-specific construction logic.  A distribution can provide a
descriptor with the same ``(scope, driver)`` key through the registry entry
point and replace one of these defaults.
"""
from __future__ import annotations

from typing import Any, Callable

from research_agent.jobs.registry import ExecutionPluginRegistry, PluginDescriptor
from research_agent.jobs.remote import RemoteSSHPlatform

from .schedulers import (
    PBSRemoteScheduler,
    SlurmRemoteScheduler,
    TorqueRemoteScheduler,
    TriRemoteScheduler,
)


def _factory(scheduler_type: type) -> Callable[[dict[str, Any]], RemoteSSHPlatform]:
    def create(target: dict[str, Any]) -> RemoteSSHPlatform:
        config = {**target, **target.get("options", {})}
        return RemoteSSHPlatform(
            config,
            platform_name=str(target["target_name"]),
            scheduler=scheduler_type(config),
        )
    return create


def register_builtin_scheduler_plugins(registry: ExecutionPluginRegistry) -> None:
    for driver, scheduler_type in (
        ("pbs", PBSRemoteScheduler),
        ("torque", TorqueRemoteScheduler),
        ("slurm", SlurmRemoteScheduler),
        ("tri", TriRemoteScheduler),
    ):
        registry.register(PluginDescriptor(
            driver=driver, scope="remote", factory=_factory(scheduler_type),
        ))
