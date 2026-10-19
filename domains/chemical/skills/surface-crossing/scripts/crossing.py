"""Crossing Jobs remain independent of ordinary TS validators."""
from pathlib import Path
import sys

SKILLS=Path(__file__).resolve().parents[2]
for part in ('_shared','material-preparation/scripts/materials','material-preparation/scripts/reaction',
             'energetics/scripts','candidate-generation/scripts/path',
             'candidate-generation/scripts/search','candidate-generation/scripts/backends',
             'gaussian/scripts'):
    sys.path.insert(0,str(SKILLS/part))
from analysis_material import read_json
from crossing_cli import parse_arguments
from crossing_check import check_crossing
from electronic import GaussianElectronic
from mecp_engine import mecp
from path_process import write_json


def run(args):
    spec,sha=read_json(args.input)
    if args.operation=='mecp':return mecp(spec,args.output_dir,lambda m,s:GaussianElectronic(m,s,args.executable))
    result=check_crossing(spec);result['input_file_sha256']=sha
    args.output_dir.mkdir(parents=True,exist_ok=False);write_json(args.output_dir/'result.json',result)
    return result


if __name__=='__main__':
    result=run(parse_arguments())
    raise SystemExit(0 if result.get('status','converged')=='converged' else 1)
