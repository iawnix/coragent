"""Construct transport-independent Job platforms from installation settings."""
from __future__ import annotations

import os
from pathlib import Path

from .config_contract import binding_digest, configured_targets, default_target, load_job_config
from .external import ExternalJobPlatform
from .platform import ExecutionPlatform


def platforms_from_config(path: str | Path | None = None) -> tuple[dict[str, ExecutionPlatform], str]:
    configured = path or os.environ.get("CORAGENT_JOB_CONFIG")
    if not configured:
        raise ValueError("job_config_required: configure the installation job.toml explicitly")
    settings = load_job_config(configured)
    platforms = {}
    for name, target in configured_targets(settings).items():
        platform = ExternalJobPlatform(target, platform_name=name)
        platform.scope = target["kind"]
        platform.driver = "external"
        platform.cluster_name = target.get("cluster_name")
        platform.target_config_digest = binding_digest(target)
        platforms[name] = platform
    return platforms, default_target(settings)
