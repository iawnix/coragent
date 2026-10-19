"""Run the standalone geometry safety checker."""
import json
from pathlib import Path
import sys

SKILLS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SKILLS / '_shared'))
from geometry_safety import assess
from cli import parse_arguments


def run(args):
    value = json.loads(args.input.read_text(encoding='utf-8'))
    if value.get('schema_version') != 'chemical-geometry-safety-input/1':
        raise ValueError('chemical-geometry-safety-input/1 required')
    result = assess(value.get('elements'), value.get('coordinates'),
                    bonded_pairs=value.get('bonded_pairs'),
                    reaction_pairs=value.get('reaction_pairs', []),
                    fragment_groups=value.get('fragment_groups'),
                    reference_coordinates=value.get('reference_coordinates'),
                    profile=value.get('profile', 'general'),
                    clash_scale=value.get('clash_scale'))
    result.update(schema_version='chemical-geometry-safety/1')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False) + '\n', encoding='utf-8')
    return result


if __name__ == '__main__':
    run(parse_arguments())
