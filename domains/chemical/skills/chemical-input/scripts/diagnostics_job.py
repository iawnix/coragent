"""Independent geometry diagnostics Job."""
from pathlib import Path
import json
import sys

SKILLS=Path(__file__).resolve().parents[2]
for part in ('_shared','crest/scripts'):
    sys.path.insert(0,str(SKILLS/part))
from analysis_material import read_json
from diagnostics_cli import parse_arguments
from local_diagnostics import local_diagnostics


def run(args):
    spec,sha=read_json(args.input)
    result=local_diagnostics(spec);result['input_file_sha256']=sha
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open('x') as stream:
        stream.write(json.dumps(result,indent=2,allow_nan=False)+'\n')
    return result


if __name__=='__main__':run(parse_arguments())
