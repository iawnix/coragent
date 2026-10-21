import sys
from pathlib import Path

_SKILLS = next(parent for parent in Path(__file__).resolve().parents if (parent / "_shared").is_dir())
_SCRIPTS = _SKILLS / "material-preparation" / "scripts"
for _part in ("materials", "reaction", "geometry", "diagnostics", "tensor", "_shared"):
    sys.path.insert(0, str(_SCRIPTS / _part if _part != "_shared" else _SKILLS / _part))

"""Independent structure analysis entry points for the existing Job runtime."""
import json

from analysis_cli import parse_arguments
from analysis_material import read_json, read_material
from conformers import compare_conformers
from correspondence import mappings
from tensor_order import reorder_tensors


def run(args):
    if args.operation == 'reorder':
        tensors, tensor_sha = read_json(args.tensors)
        order, order_sha = read_json(args.order)
        result = reorder_tensors(tensors, order)
        result['provenance']['sources'] = {'tensors': tensor_sha, 'order': order_sha}
    else:
        left, right = read_material(args.left), read_material(args.right)
        options = dict(fixed_pairs=args.fixed_pairs, max_candidates=args.max_candidates, max_search=args.max_search)
        if args.operation == 'map':
            result = mappings(left, right, mode=args.mode, **options)
        else:
            result = compare_conformers(left, right, rmsd_threshold=args.rmsd_threshold,
                internal_coordinates=args.internal_coordinates, distance_tolerance=args.distance_tolerance,
                angle_tolerance=args.angle_tolerance, **options)
    # Validate/serialize before creating output. Exclusive creation protects sources
    # and historical results, including when an output aliases an input path.
    encoded = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + '\n'
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as handle:
        handle.write(encoded)
    return result


if __name__ == '__main__':
    run(parse_arguments())
