"""Run independent analysis Jobs and export traceable JSON/CSV report data."""
import csv
import io
import json
from pathlib import Path
import sys

SKILLS = Path(__file__).resolve().parents[2]
for part in ('_shared', 'material-preparation/scripts/materials', 'material-preparation/scripts/reaction',
             'material-preparation/scripts/geometry'):
    sys.path.insert(0, str(SKILLS / part))
from analysis_material import read_json
from energy_analysis import ensemble, profile, scan_slice
from energy_cli import parse_arguments
from thermochemistry import thermochemistry
from kinetics import tst, branching
from kinetic_network import network

OPERATIONS = {'thermochemistry': thermochemistry, 'ensemble': ensemble, 'profile': profile, 'scan-slice': scan_slice, 'tst': tst, 'branching': branching, 'network': network}


def run(args):
    spec, sha = read_json(args.input)
    result = OPERATIONS[args.operation](spec)
    result['input_file_sha256'] = sha
    encoded = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + '\n'
    rows = result.get('rows', result.get('members', result.get('channels')))
    if rows is None:
        rows = [{'quantity': k, 'value': v, 'unit': 'hartree'} for k,v in result['quantities'].items()] if 'quantities' in result else [{k:v for k,v in result.items() if not isinstance(v,(dict,list))}]
    table = io.StringIO()
    if rows:
        writer = csv.DictWriter(table, fieldnames=list(rows[0]))
        writer.writeheader()
        for row in rows:
            writer.writerow({k: json.dumps(v, ensure_ascii=False) if isinstance(v, (dict,list)) else v for k,v in row.items()})
    else:
        table.write('index,targets,actual,energy_hartree,relative_energy\r\n')
    # New directory only: never overwrite source or prior evidence.
    args.output_dir.mkdir(parents=True, exist_ok=False)
    (args.output_dir / 'result.json').write_text(encoded, encoding='utf-8')
    (args.output_dir / 'table.csv').write_text(table.getvalue(), encoding='utf-8')
    return result


if __name__ == '__main__':
    result = run(parse_arguments())
    raise SystemExit(0 if result.get('status','completed') == 'completed' else 1)
