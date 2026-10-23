"""Release ownership rules; source roots are declared once in source-layout.json."""
from __future__ import annotations

import fnmatch
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
LAYOUT = json.loads((ROOT / "packaging/coragent_packaging/manifests/source-layout.json").read_text())
PACKAGE_FILES = [*LAYOUT["roots"], *LAYOUT["files"], *LAYOUT["generated"], *("!" + value for value in LAYOUT["exclude"])]
REQUIRED_RUNTIME_FILES = frozenset(LAYOUT["required"])
REQUIRED_TARBALL_FILES = REQUIRED_RUNTIME_FILES | {"package.json", *LAYOUT["files"]}
RETIRED_RUNTIME_PATHS = ("scripts/", "components/", "services/", "apps/agent-cli/", "apps/agent/pi/", "apps/agent/host/admission/", "backend/tests/", "prompts/", "plugins/", "backend/src/research_agent/execution_plugins/",
    "backend/src/research_agent/jobs/registry.py", "backend/src/research_agent/jobs/scheduler.py",
    "backend/src/research_agent/jobs/process_scheduler.py", "backend/src/research_agent/jobs/remote.py",
    "apps/app-server/", "extensions/", "packages/agent-core/", "packages/agent-runtime/", "packages/runtime-bridge/", "packages/research-state/",
    "skills/chemical/candidate-generation/scripts/da/",
    "skills/chemical/candidate-generation/references/gaussian_path.md",
    "skills/chemical/candidate-generation/references/gaussian_path.zh-CN.md",
    "skills/chemical/validation/scripts/reaction_mapping.py",
    "skills/chemical/validation/scripts/gaussian_saddle.py",
    "skills/chemical/validation/scripts/gaussian_irc_connectivity.py")
SKILL_ENTRIES = json.loads((ROOT / "package.json").read_text())["pi"]["skills"]
SKILL_ENTRY_FILES = sorted(str(p.relative_to(ROOT)) for root in (ROOT / relative for relative in SKILL_ENTRIES) for p in root.rglob("SKILL.md"))
FORBIDDEN_PARTS = {"local_debug", ".git", ".agents", "__pycache__", ".pytest_cache", "node_modules", "tests"}


def release_files(root: Path = ROOT) -> set[str]:
    """Select existing authored files, without descending into private/cache trees."""
    files = set(LAYOUT["files"])
    for name in LAYOUT["roots"]:
        for path in (root / name).rglob("*"):
            relative = path.relative_to(root)
            if path.is_file() and path.suffix not in {".pyc", ".pyo", ".tmp"} and not any(part.endswith(".egg-info") for part in relative.parts) and not FORBIDDEN_PARTS.intersection(relative.parts) and not any(fnmatch.fnmatchcase(relative.as_posix(), pattern) for pattern in LAYOUT["exclude"]):
                files.add(relative.as_posix())
    return files
