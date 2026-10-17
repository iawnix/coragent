"""Run the deterministic structure cognition report."""
import json
from pathlib import Path
import sys

SKILLS = Path(__file__).resolve().parents[2]
for part in ('_shared', 'chemical-input/scripts/materials', 'structure-cognition/scripts'):
    # Keep this skill's own cli.py ahead of shared chemical-input CLI modules.
    sys.path.append(str(SKILLS / part))

from cognition import _read, cognize  # noqa: E402
from cli import parse_arguments  # noqa: E402


def run(args):
    material, material_sha = _read(args.material)
    context, _ = _read(args.context)
    result = cognize(material, context, material_sha256=material_sha)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False) + '\n', encoding='utf-8')
    return result


if __name__ == '__main__':
    run(parse_arguments())
