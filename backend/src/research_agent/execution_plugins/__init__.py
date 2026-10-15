"""Compatibility imports for execution plugin interfaces."""

from .schedulers import (
    DirectRemoteScheduler,
    adapter_for,
)
from research_agent.jobs.scheduler import RemoteScheduler

__all__ = [
    "RemoteScheduler", "DirectRemoteScheduler", "adapter_for",
]
