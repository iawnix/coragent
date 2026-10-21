from __future__ import annotations

from typing import Any, Mapping

from .models import JobReceipt, JobSpec, JobStatus
from .platform import ExecutionPlatform


class JobManager:
    """Job execution operations; platform adapters own process and scheduler details."""

    def __init__(self, platforms: Mapping[str, ExecutionPlatform], default: str = "local") -> None:
        if default not in platforms:
            raise ValueError(f"unknown default execution platform: {default}")
        self.platforms = dict(platforms)
        self.default = default

    def _platform(self, name: str | None) -> ExecutionPlatform:
        key = name or self.default
        try:
            return self.platforms[key]
        except KeyError as exc:
            raise ValueError(f"unknown execution platform: {key}") from exc

    def job_probe(self, spec: JobSpec, *, platform: str | None = None) -> dict[str, Any]:
        return self._platform(platform).probe(spec)

    def job_start(self, spec: JobSpec, *, platform: str | None = None) -> JobReceipt:
        return self._platform(platform).start(spec)

    def job_status(self, receipt: JobReceipt) -> JobStatus:
        return self._platform(receipt.platform).status(receipt)

    def job_collect(self, receipt: JobReceipt) -> dict[str, Any]:
        return self._platform(receipt.platform).collect(receipt)

    def job_cancel(self, receipt: JobReceipt) -> JobStatus:
        return self._platform(receipt.platform).cancel(receipt)

    def job_reconcile(self, receipt: JobReceipt) -> JobStatus:
        return self._platform(receipt.platform).reconcile(receipt)

    def receipt_from_disk(self, path: str) -> JobReceipt:
        """Load a durable receipt and reconcile it through its platform."""
        # Receipt loading is platform-specific because remote adapters carry
        # scheduler metadata alongside the same durable receipt envelope.
        import json
        with open(path, encoding="utf-8") as handle:
            platform_name = json.load(handle).get("platform", "local")
        platform = self._platform(str(platform_name))
        loader = getattr(platform, "receipt_from_disk", None)
        if not callable(loader):
            raise TypeError(f"configured platform cannot load durable receipts: {platform_name}")
        return loader(path)
