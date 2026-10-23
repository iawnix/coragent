"""Load the installed chemical resolver's standalone configuration contract."""
from __future__ import annotations

import importlib.util
from pathlib import Path


def parse_config(value, *, package_root=None):
    if package_root is None:
        from .env import resolve_package_root
        package_root = resolve_package_root()
    source = Path(package_root) / 'skills/chemical/material-preparation/scripts/materials/name_resolver_config.py'
    spec = importlib.util.spec_from_file_location('coragent_name_resolver_config', source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.parse_name_resolver_config(value)
