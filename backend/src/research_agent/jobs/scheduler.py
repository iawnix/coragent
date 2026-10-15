"""Stable scheduler adapter interface for SSH execution plugins."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from .models import JobReceipt, JobSpec


class RemoteScheduler(ABC):
    """Scheduler behavior injected into the generic SSH Job lifecycle."""

    name: str
    requires_queue = True

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = dict(config)

    def probe_commands(self) -> tuple[str, ...]:
        return ()

    @abstractmethod
    def submit_arguments(self, spec: "JobSpec") -> list[str]: ...

    @abstractmethod
    def details(self, platform: Any, receipt: "JobReceipt") -> tuple[str | None, dict[str, Any]]: ...

    @abstractmethod
    def cancel(self, platform: Any, scheduler_id: str): ...

    @abstractmethod
    def map_state(self, state: str | None): ...

    def completed_with_exit(self, state: str | None, details: dict[str, Any]) -> bool:
        return state in {"C", "F", "COMPLETED", "SUCCEEDED", "FAILED", "CANCELLED"} and "exit_status" in details

    def cancellation_terminal(self, state: str | None, details: dict[str, Any]) -> bool:
        return state in {"C", "F", "COMPLETED", "SUCCEEDED", "FAILED", "CANCELLED"}
