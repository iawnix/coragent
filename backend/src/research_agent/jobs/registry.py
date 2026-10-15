"""Execution target registry.

The registry keeps target selection separate from the implementation of a
local supervisor or a remote scheduler.  It intentionally loads only the
driver requested by the installation configuration.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any, Callable

from .platform import ExecutionPlatform


PluginFactory = Callable[[dict[str, Any]], ExecutionPlatform]


@dataclass(frozen=True)
class PluginDescriptor:
    """Metadata used to validate a target before constructing its platform."""

    driver: str
    scope: str
    factory: PluginFactory


class ExecutionPluginRegistry:
    """Small registry for built-in and separately installed drivers."""

    def __init__(self) -> None:
        self._plugins: dict[tuple[str, str], PluginDescriptor] = {}

    def register(self, descriptor: PluginDescriptor) -> None:
        if descriptor.scope not in {"local", "remote"}:
            raise ValueError(f"invalid execution plugin scope: {descriptor.scope}")
        key = (descriptor.scope, descriptor.driver)
        if key in self._plugins:
            raise ValueError(f"execution plugin already registered: {descriptor.scope}/{descriptor.driver}")
        self._plugins[key] = descriptor

    def descriptor(self, *, scope: str, driver: str) -> PluginDescriptor:
        try:
            return self._plugins[(scope, driver)]
        except KeyError as exc:
            raise ValueError(f"execution plugin is not installed: {scope}/{driver}") from exc

    def create(self, name: str, target: dict[str, Any]) -> ExecutionPlatform:
        scope = target.get("type")
        driver = target.get("driver")
        if not isinstance(scope, str) or not isinstance(driver, str):
            raise ValueError(f"execution target {name!r} must declare type and driver")
        descriptor = self.descriptor(scope=scope, driver=driver)
        platform = descriptor.factory({**target, "target_name": name})
        platform.name = name
        setattr(platform, "scope", scope)
        setattr(platform, "driver", driver)
        setattr(platform, "cluster_name", target.get("cluster_name"))
        digest_input = {key: value for key, value in target.items() if key != "target_name"}
        setattr(platform, "target_config_digest", "sha256:" + hashlib.sha256(
            json.dumps(digest_input, sort_keys=True, separators=(",", ":"), default=str).encode()
        ).hexdigest())
        return platform

    def drivers(self, scope: str | None = None) -> tuple[str, ...]:
        values = [driver for (registered_scope, driver) in self._plugins
                  if scope is None or registered_scope == scope]
        return tuple(sorted(values))
