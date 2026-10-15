"""Execution target registry.

The registry keeps target selection separate from the implementation of a
local supervisor or a remote scheduler.  It intentionally loads only the
driver requested by the installation configuration.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from importlib import metadata
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
        self._discovered = False

    def register(self, descriptor: PluginDescriptor) -> None:
        if descriptor.scope not in {"local", "remote"}:
            raise ValueError(f"invalid execution plugin scope: {descriptor.scope}")
        key = (descriptor.scope, descriptor.driver)
        if key in self._plugins:
            raise ValueError(f"execution plugin already registered: {descriptor.scope}/{descriptor.driver}")
        self._plugins[key] = descriptor

    def descriptor(self, *, scope: str, driver: str) -> PluginDescriptor:
        self.discover()
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

    def discover(self) -> None:
        """Load separately maintained execution plugins on first lookup.

        Plugins are ordinary Python distributions exposing the
        ``tspi.execution_plugins`` entry point. The entry point may return a
        descriptor, an iterable of descriptors, or a registration callable;
        importing is delayed until a target is actually constructed.
        """
        if self._discovered:
            return
        self._discovered = True
        try:
            entries = metadata.entry_points()
            entries = entries.select(group="tspi.execution_plugins") if hasattr(entries, "select") else entries.get("tspi.execution_plugins", ())
        except Exception:
            entries = ()
        for entry in entries:
            loaded = entry.load()
            values = loaded() if callable(loaded) and not isinstance(loaded, PluginDescriptor) else loaded
            if isinstance(values, PluginDescriptor):
                values = (values,)
            for descriptor in values or ():
                if not isinstance(descriptor, PluginDescriptor):
                    raise TypeError(f"execution plugin {entry.name!r} did not return PluginDescriptor")
                # Distribution plugins are the installation-level override
                # point. This lets PBS/tri packages evolve independently of
                # the fallback adapters shipped with the core runtime.
                self._plugins[(descriptor.scope, descriptor.driver)] = descriptor

    def drivers(self, scope: str | None = None) -> tuple[str, ...]:
        values = [driver for (registered_scope, driver) in self._plugins
                  if scope is None or registered_scope == scope]
        return tuple(sorted(values))
