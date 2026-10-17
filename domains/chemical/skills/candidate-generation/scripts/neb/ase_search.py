"""ASE NEB entries for the version 2 input and calculator contracts."""
from pathlib import Path
import sys

SKILLS = next(parent for parent in Path(__file__).resolve().parents if (parent / '_shared').is_dir())
for part in ('_shared', 'chemical-input/scripts/materials', 'chemical-input/scripts/reaction',
             'crest/scripts', 'gaussian/scripts', 'energetics/scripts',
             'candidate-generation/scripts/path', 'candidate-generation/scripts/search',
             'candidate-generation/scripts/backends', 'candidate-generation/scripts/neb'):
    sys.path.insert(0, str(SKILLS/part))
from analysis_material import read_json
from ase_neb import neb
from gaussian_path import GaussianPathCalculator
from path_xtb import XtbCalculator
from ase_cli import parse_arguments


def run(args):
    spec, _ = read_json(args.input)
    cls = XtbCalculator if args.operation == 'neb-xtb' else GaussianPathCalculator
    return neb(spec, args.output_dir, lambda m,s: cls(m,s,args.executable))


if __name__ == '__main__':
    result = run(parse_arguments())
    raise SystemExit(0 if result['status'] == 'converged' else 1)
