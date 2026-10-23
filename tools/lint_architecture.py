#!/usr/bin/env python3
"""Enforce package ownership and the single production runtime boundary.

This check is intentionally source based.  It prevents a new implementation
from silently recreating the removed ``research_agent.application`` subpackages while the
single wheel ships one research_agent namespace.
"""

from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packaging"))
from coragent_packaging.manifests.package_inventory import RETIRED_RUNTIME_PATHS

OLD_SUBPACKAGE = re.compile(
    r"\bresearch_agent_runtime\.(?:backends|analysis|remote|platforms|structures|reaction|pyscf|workspace|providers|io|path_safety|calculation_contracts|runtime)\b"
)


def _python_files(root: Path):
    return sorted(path for path in root.rglob("*.py") if "__pycache__" not in path.parts)


def _imports(path: Path, *, backend: Path | None = None):
    """Resolve Python imports so relative imports obey the same layer rules."""
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name, node.lineno
        elif isinstance(node, ast.ImportFrom):
            package = []
            if node.level and backend is not None:
                package = ['research_agent', *path.relative_to(backend).parts[:-1]]
                package = package[:len(package) - node.level + 1]
            base = '.'.join([*package, *([node.module] if node.module else [])])
            for alias in node.names:
                yield base if alias.name == '*' else '.'.join(filter(None, (base, alias.name))), node.lineno


def _execution_resources():
    """Only catalog-staged science runs remotely; report orchestration stays on the controller."""
    metadata = json.loads((ROOT / 'package.json').read_text())
    paths = set()
    for declaration in metadata['coragent']['execution']:
        catalog_path = ROOT / declaration
        catalog = json.loads(catalog_path.read_text())
        for descriptor in catalog['executors']:
            paths.update(catalog_path.parent / resource for resource in descriptor['resources'])
        for descriptor in catalog['validators']:
            paths.add(catalog_path.parent / descriptor['entry'])
            paths.update(catalog_path.parent / resource['path'] for resource in descriptor.get('resources', {}).values())
    return sorted(path for path in paths if path.suffix == '.py')


def check_ownership() -> list[str]:
    """Check source dependencies, not runtime payloads or compatibility aliases."""
    errors = []
    backend = ROOT / "backend/src/research_agent"
    allowed = {
        "foundation": {"foundation"},
        "configuration": {"configuration", "foundation"},
        "artifacts": {"artifacts", "foundation"},
        "research": {"research", "artifacts", "foundation"},
        "jobs": {"jobs", "foundation"},
        "integrations": {"integrations", "configuration", "foundation"},
    }
    for path in _python_files(backend):
        owner = path.relative_to(backend).parts[0]
        for module, line in _imports(path, backend=backend):
            if module.split('.')[0] in {"coragent_packaging", "tools", "apps", "scripts", "skills"}:
                errors.append(f"backend imports delivery/development code: {path.relative_to(ROOT)}:{line}")
            if owner in allowed and module.startswith("research_agent.") and module.split('.')[1] not in allowed[owner]:
                errors.append(f"{owner} imports an upper layer: {path.relative_to(ROOT)}:{line}")
    # Science payloads and scheduler handlers execute without the controller.
    # Control-side skills may compose research and delivery through application.
    independent = [*_execution_resources(), *_python_files(ROOT / 'skills/core/batch-schedulers/scripts')]
    for path in independent:
        for module, line in _imports(path):
            if module.split('.')[0] in {'research_agent', 'coragent_packaging', 'apps', 'tools'}:
                errors.append(f"execution payload imports the controller: {path.relative_to(ROOT)}:{line}")
    for path in (ROOT / "apps").rglob("*.py"):
        if re.search(r"(?:from|import)\s+(?:coragent_packaging|tools|scripts)\b", path.read_text()):
            errors.append(f"application imports packaging/development code: {path.relative_to(ROOT)}")
    for path in (ROOT / "apps/agent/host").rglob("*.mjs"):
        if "@earendil-works/pi-durable" in path.read_text():
            errors.append(f"Host owns Pi durable state: {path.relative_to(ROOT)}")
    for name in ("assessment", "recovery", "execution-plan", "execution-selection", "projection"):
        path = ROOT / f"apps/agent/tasks/{name}.mjs"
        if re.search(r'from\s+[\'"][^\'\"]*(?:pi-durable|/runtime/|/host/)', path.read_text()):
            errors.append(f"task policy imports session infrastructure: {path.relative_to(ROOT)}")
    return errors


def check() -> list[str]:
    errors: list[str] = check_ownership()
    old_roots = [
        ROOT / "backend" / "src" / "research_agent" / "application" / name
        for name in ("backends", "analysis", "remote", "platforms", "structures", "reaction", "pyscf", "workspace", "providers", "io.py", "path_safety.py", "calculation_contracts.py", "runtime")
    ]
    for path in old_roots:
        if path.exists() and (path.is_file() or any(path.rglob("*.py"))):
            errors.append(f"removed research_agent.application implementation remains: {path.relative_to(ROOT)}")

    memory_root = ROOT / "backend" / "src" / "research_agent" / "research"
    for path in _python_files(memory_root):
        text = path.read_text(encoding="utf-8")
        if re.search(r"(?:from|import)\s+(?:research_agent\.(?:application|jobs)|chemical_runtime|research_compute)\b", text):
            errors.append(f"research_agent.research imports an execution namespace: {path.relative_to(ROOT)}")
    for namespace in ("artifacts", "foundation"):
        for path in _python_files(ROOT / "backend/src/research_agent" / namespace):
            if re.search(r"(?:from|import)\s+(?:research_agent\.research|research_agent\.application)\b", path.read_text()):
                errors.append(f"storage/foundation imports research policy: {path.relative_to(ROOT)}")
    for relative in RETIRED_RUNTIME_PATHS:
        path = ROOT / relative
        if path.is_file() or (path.is_dir() and any(
            item.is_file() and item.suffix in {".py", ".mjs", ".mts", ".cjs", ".cts", ".js", ".ts", ".jsx", ".tsx", ".json"}
            for item in path.rglob("*")
        )):
            errors.append(f"retired implementation remains: {relative}")
    for root in (ROOT / "backend/src", ROOT / "packages", ROOT / "apps", ROOT / "packaging", ROOT / "tools"):
        for path in _python_files(root):
            text = path.read_text(encoding="utf-8")
            if OLD_SUBPACKAGE.search(text):
                errors.append(f"removed research_agent.application subpackage reference: {path.relative_to(ROOT)}")
    required = (
        ROOT / "backend" / "src" / "research_agent" / "foundation" / "io.py",
        ROOT / "backend" / "src" / "research_agent" / "research" / "nodes.py",
        ROOT / "backend" / "src" / "research_agent" / "jobs" / "manager.py",
        ROOT / "backend" / "src" / "research_agent" / "bootstrap" / "launcher.py",
    )
    for path in required:
        if not path.is_file():
            errors.append(f"canonical implementation is missing: {path.relative_to(ROOT)}")

    # Pi SDK is the only production Agent Runtime. Keep runtime selection
    # installation-owned and prevent the removed standalone Compute/Review
    # session loops from returning.
    for relative in (
        Path("packages/agent-runtime/agents/compute") / "runtime.ts",
        Path("packages/agent-runtime/agents/review") / "runtime.ts",
    ):
        path = ROOT / relative
        if path.exists():
            errors.append(f"duplicate Pi sub-agent runtime remains: {relative}")
    forbidden_runtime_markers = (
        "CORAGENT_" + "RUNTIME_MODULE",
        "CORAGENT_" + "KERNEL_MODULE",
        "load_pi_" + "runtime(",
    )
    for root in (ROOT / "apps", ROOT / "packages", ROOT / "packaging"):
        for path in sorted(root.rglob("*.mjs")):
            if any(part in {"node_modules", ".git"} for part in path.parts):
                continue
            text = path.read_text(encoding="utf-8")
            for marker in forbidden_runtime_markers:
                if marker in text:
                    errors.append(f"removed alternate Pi runtime boundary {marker!r}: {path.relative_to(ROOT)}")
    app_server = ROOT / "apps/agent/main.mjs"
    if "source-root" in app_server.read_text(encoding="utf-8"):
        errors.append("pi-app-server exposes a replaceable source-root option")
    for path in (ROOT / "apps/agent").rglob("*.mjs"):
        if path.relative_to(ROOT).as_posix() == "apps/agent/runtime/source.mjs":
            continue
        if re.search(r"packages/(?:coding-agent|durable|ai|tui)/src/", path.read_text()):
            errors.append(f"Pi private source path outside adapter: {path.relative_to(ROOT)}")
    return errors


def main() -> int:
    errors = check()
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print("architecture boundaries: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
