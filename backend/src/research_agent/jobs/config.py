"""Load the installation job.toml into Job Runtime platforms."""
from __future__ import annotations

from pathlib import Path
import os
import re
import tomllib
from typing import Any

from .local import LocalProcessPlatform
from .remote import RemoteSSHPlatform
from .platform import ExecutionPlatform
from .registry import ExecutionPluginRegistry, PluginDescriptor
from .process_scheduler import ProcessRemoteScheduler


from .config_contract import load_job_config


def _builtin_registry() -> ExecutionPluginRegistry:
    registry = ExecutionPluginRegistry()
    registry.register(PluginDescriptor(
        driver="local",
        scope="local",
        factory=lambda target: LocalProcessPlatform(
            supervisor=target.get("supervisor", "systemd"),
            platform_name=str(target["target_name"]),
        ),
    ))
    registry.register(PluginDescriptor(
        driver="process",
        scope="local",
        factory=lambda target: LocalProcessPlatform(
            supervisor="process", platform_name=str(target["target_name"]),
        ),
    ))
    registry.register(PluginDescriptor(
        driver="systemd",
        scope="local",
        factory=lambda target: LocalProcessPlatform(
            supervisor="systemd", platform_name=str(target["target_name"]),
        ),
    ))
    registry.register(PluginDescriptor(
        driver="process", scope="remote",
        factory=lambda target: RemoteSSHPlatform(
            {**target, **target.get("options", {}), "scheduler": "process", "driver": "process"},
            platform_name=str(target["target_name"]),
            scheduler=ProcessRemoteScheduler({**target, **target.get("options", {})}),
        ),
    ))
    return registry


def _execution_targets(path: str | Path) -> tuple[dict[str, dict[str, Any]], str] | None:
    """Read the new execution.targets configuration, if present.

    This is intentionally separate from the scientific environment bindings;
    target names are routing identities and driver options remain private to a
    registered execution plugin.
    """
    with Path(path).expanduser().open("rb") as handle:
        value = tomllib.load(handle)
    execution = value.get("execution")
    if execution is None:
        return None
    if not isinstance(execution, dict):
        raise ValueError("execution must be a table")
    targets = execution.get("targets")
    default = execution.get("default_target")
    if not isinstance(targets, dict) or not targets:
        raise ValueError("execution.targets must define at least one target")
    if not isinstance(default, str) or default not in targets:
        raise ValueError("execution.default_target must name a configured target")
    local = 0
    normalized: dict[str, dict[str, Any]] = {}
    for name, raw in targets.items():
        if not isinstance(name, str) or not name or not isinstance(raw, dict):
            raise ValueError("execution target names and values must be tables")
        target = dict(raw)
        scope = target.get("type")
        driver = target.get("driver")
        if scope not in {"local", "remote"}:
            raise ValueError(f"execution target {name!r} must declare type=local or type=remote")
        if not isinstance(driver, str) or not driver:
            raise ValueError(f"execution target {name!r} must declare a driver")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", driver):
            raise ValueError(f"execution target {name!r} has an invalid driver")
        if scope == "local":
            local += 1
            if "cluster_name" in target:
                raise ValueError(f"local target {name!r} cannot declare cluster_name")
        else:
            if not isinstance(target.get("cluster_name"), str) or not target["cluster_name"].strip():
                raise ValueError(f"remote target {name!r} must declare cluster_name")
            if not isinstance(target.get("ssh_host"), str) or not target["ssh_host"].strip():
                raise ValueError(f"remote target {name!r} must declare ssh_host")
            if not isinstance(target.get("remote_root"), str) or not target["remote_root"].startswith("/"):
                raise ValueError(f"remote target {name!r} must declare an absolute remote_root")
        options = target.get("options", {})
        if not isinstance(options, dict):
            raise ValueError(f"execution target {name!r}.options must be a table")
        target["target_name"] = name
        normalized[name] = target
    if local > 1:
        raise ValueError("execution configuration may define at most one local target")
    return normalized, default


def platforms_from_config(path: str | Path | None = None) -> tuple[dict[str, ExecutionPlatform], str]:
    configured = path or os.environ.get("CORAGENT_JOB_CONFIG")
    if not configured:
        raise ValueError("job_config_required: configure the installation job.toml explicitly")
    execution = _execution_targets(configured)
    if execution is not None:
        # Validate bindings and target invariants through the public contract
        # before constructing any plugin.
        load_job_config(configured)
        targets, default = execution
        registry = _builtin_registry()
        return {name: registry.create(name, target) for name, target in targets.items()}, default
    value = load_job_config(configured)
    registry = _builtin_registry()
    platforms: dict[str, ExecutionPlatform] = {}
    for name, environment in value["environments"].items():
        kind = environment["kind"]
        if kind == "local":
            platforms[name] = LocalProcessPlatform(supervisor=environment.get("supervisor", "systemd"), platform_name=name)
        else:
            target = {**environment, "target_name": name, "type": "remote",
                      "driver": environment.get("scheduler", "torque"),
                      "cluster_name": environment.get("cluster_name", name)}
            platforms[name] = registry.create(name, target)
    default = str(value["default_environment"])
    return platforms, default
