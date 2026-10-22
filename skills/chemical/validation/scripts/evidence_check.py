"""Independent executor dispatcher; check results do not mutate research state."""
import json
from pathlib import Path
import sys

SCRIPTS = Path(__file__).resolve().parents[2]
for _part in ('material-preparation/scripts/materials', 'material-preparation/scripts/reaction',
              'material-preparation/scripts/geometry', 'material-preparation/scripts/tensor'):
    sys.path.insert(0, str(SCRIPTS / _part))
sys.path.insert(0, str(SCRIPTS / 'gaussian' / 'scripts'))
from analysis_material import read_json, read_material
from check_cli import parse_arguments
from check_common import stationary
from gaussian_evidence import gaussian_evidence
from irc_check import irc_check
from mode_check import mode_check


def run(args):
    material = read_material(args.material)
    if args.operation == 'gaussian':
        result = gaussian_evidence(material, args.evidence, kind=args.kind, section_index=args.section_index, constraints=args.constraints)
    else:
        evidence, sha = read_json(args.evidence)
        options = {'negative_threshold': args.negative_threshold, 'near_zero': args.near_zero}
        sources = {'material': material['sha256'], 'evidence': sha}
        if args.operation == 'stationary':
            result = stationary(material, evidence, kind=args.kind, **options)
        elif args.operation == 'mode':
            coordinates, sources['coordinates'] = read_json(args.coordinates)
            result = mode_check(material, evidence, coordinates, step=args.step, **options)
        else:
            forward, sources['forward'] = read_json(args.forward)
            reverse, sources['reverse'] = read_json(args.reverse)
            reactant, product = read_material(args.reactant), read_material(args.product)
            sources.update(reactant=reactant['sha256'], product=product['sha256'])
            result = irc_check(material, evidence, [forward, reverse], [reactant, product],
                endpoint_rmsd=args.endpoint_rmsd, origin_rmsd=args.origin_rmsd,
                max_search=args.max_search, max_candidates=args.max_candidates,
                energy_tolerance=args.energy_tolerance, max_step_rmsd=args.max_step_rmsd, policy=args.policy, **options)
        result['sources'] = sources
    encoded = json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False) + '\n'
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as handle:
        handle.write(encoded)
    return result


if __name__ == '__main__':
    run(parse_arguments())
