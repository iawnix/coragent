"""Independent geometry diagnostics Job."""
from pathlib import Path
import json
import sys

SKILLS = next(parent for parent in Path(__file__).resolve().parents if (parent / '_shared').is_dir())
for part in ('_shared','material-preparation/scripts/materials','material-preparation/scripts/geometry',
             'crest/scripts'):
    sys.path.insert(0,str(SKILLS/part))
_SCRIPTS = SKILLS / 'material-preparation' / 'scripts'
for _part in ('materials', 'reaction', 'geometry', 'diagnostics', 'tensor'):
    sys.path.insert(0, str(_SCRIPTS / _part))
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
