"""Independent pathway audit entry; no research/task state mutation."""
import json
from pathlib import Path
import sys

SKILLS=Path(__file__).resolve().parents[2]
for part in ('_shared','chemical-input/scripts','validation/scripts','energetics/scripts'):
    sys.path.insert(0,str(SKILLS/part))
from analysis_material import read_json
from pathway import pathway
from pathway_cli import parse_arguments


def run(args):
    spec,sha=read_json(args.input);result=pathway(spec);result['input_file_sha256']=sha
    encoded=json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+'\n'
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open('x',encoding='utf-8') as handle:handle.write(encoded)
    return result


if __name__=='__main__':run(parse_arguments())
