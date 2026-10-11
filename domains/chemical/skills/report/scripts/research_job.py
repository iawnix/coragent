"""Independent trajectory and report package Jobs."""
from pathlib import Path
import sys

SKILLS=Path(__file__).resolve().parents[2]
for part in ('_shared','chemical-input/scripts','crest/scripts','energetics/scripts','candidate-generation/scripts'):
    sys.path.insert(0,str(SKILLS/part))
from analysis_material import read_json
from research_cli import parse_arguments


def run(args):
    spec,_=read_json(args.input)
    if args.operation=='trajectory':
        from trajectory import write_trajectory
        return write_trajectory(spec,args.output_dir)
    from research_report import build_report
    return build_report(spec,args.output_dir)


if __name__=='__main__':run(parse_arguments())
