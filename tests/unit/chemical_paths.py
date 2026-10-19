"""Canonical import roots for the reorganized chemical skill scripts."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
SKILLS = ROOT / "domains" / "chemical" / "skills"
_RELATIVE_PATHS = (
    "_shared",
    "material-preparation/scripts/materials",
    "material-preparation/scripts/reaction",
    "material-preparation/scripts/geometry",
    "material-preparation/scripts/diagnostics",
    "material-preparation/scripts/tensor",
    "crest/scripts",
    "gaussian/scripts",
    "energetics/scripts",
    "validation/scripts",
    "candidate-generation/scripts/path",
    "candidate-generation/scripts/search",
    "candidate-generation/scripts/backends",
    "candidate-generation/scripts/neb",
    "reactive-geometry/scripts",
    "structure-assessment/scripts",
)


def configure() -> None:
    """Expose current skill subdirectories to direct unit imports."""
    for relative in reversed(_RELATIVE_PATHS):
        path = str(SKILLS / relative)
        if path not in sys.path:
            sys.path.insert(0, path)
