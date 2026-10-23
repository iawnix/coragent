"""Bootstrap the packaged Python kernel without importing it from source first."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from types import ModuleType


def load_runtime_environment(package_root: str | Path) -> ModuleType:
    root = Path(package_root).expanduser().resolve()
    source_root = str(root / "backend/src")
    sys.path.insert(0, source_root)
    try:
        from research_agent.bootstrap import env
        return env
    finally:
        sys.path.remove(source_root)



def bootstrap_python_package(
    package_root: str | Path,
    *,
    required: bool = False,
    workspace_from_argv: bool = False,
    entrypoint: str | Path | None = None,
    install_root: str | Path | None = None,
) -> ModuleType:
    """Select the managed interpreter, then import installed or source code."""

    root = Path(package_root).expanduser().resolve()
    runtime = load_runtime_environment(root)
    os.environ[runtime.PACKAGE_ROOT_OVERRIDE] = str(root)
    if workspace_from_argv:
        runtime.seed_workspace_root_from_argv()
    if entrypoint is not None:
        runtime.seed_installation_runtime_from_entrypoint(entrypoint)
    if install_root is not None:
        runtime.seed_installation_runtime(install_root, authoritative=True)
    python = runtime.ensure_runtime_python(root, required=required)
    if (root / ".coragent-release.json").is_file() or install_root is not None:
        if python is None:
            raise runtime.RuntimeEnvironmentError("installed commands require the managed Python wheel")
        source = root / "backend/src"
        sys.path[:] = [item for item in sys.path if Path(item).resolve() != source]
        for name, module in list(sys.modules.items()):
            origin = getattr(module, "__file__", None)
            if origin and name.split(".")[0] == "research_agent" and Path(origin).resolve().is_relative_to(source):
                del sys.modules[name]
        import research_agent
        if not Path(research_agent.__file__).resolve().is_relative_to(Path(sys.prefix).resolve()):
            raise runtime.RuntimeEnvironmentError("installed commands must import the managed Python wheel")
    else:
        activate_source_package(root)
    return runtime


def activate_source_package(package_root: str | Path) -> None:
    """Expose the authored package only for installer and runtime-control code."""

    root = Path(package_root).expanduser().resolve()
    runtime = load_runtime_environment(root)
    os.environ[runtime.PACKAGE_ROOT_OVERRIDE] = str(root)
    for source_root in runtime.source_python_paths(root):
        value = str(source_root)
        if value not in sys.path: sys.path.insert(0, value)
