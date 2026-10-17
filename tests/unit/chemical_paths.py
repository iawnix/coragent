"""Canonical import roots for the reorganized chemical skill scripts."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
SKILLS = ROOT / "domains" / "chemical" / "skills"
_RELATIVE_PATHS = (
    "_shared",
    "chemical-input/scripts/materials",
    "chemical-input/scripts/reaction",
    "chemical-input/scripts/geometry",
    "chemical-input/scripts/diagnostics",
    "chemical-input/scripts/tensor",
    "crest/scripts",
    "gaussian/scripts",
    "energetics/scripts",
    "validation/scripts",
    "candidate-generation/scripts/path",
    "candidate-generation/scripts/search",
    "candidate-generation/scripts/backends",
    "candidate-generation/scripts/neb",
    "candidate-generation/scripts/da",
    "reactive-geometry/scripts",
    "structure-cognition/scripts",
)


def configure() -> None:
    """Expose current skill subdirectories to direct unit imports."""
    for relative in reversed(_RELATIVE_PATHS):
        path = str(SKILLS / relative)
        if path not in sys.path:
            sys.path.insert(0, path)
