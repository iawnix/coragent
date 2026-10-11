"""Stage reusable member geometries and a refinement manifest without starting calculations."""
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'chemical-input/scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / '_shared'))
from analysis_material import read_json, read_material
from complex_sample import sample_complex
from ensemble_cli import parse_arguments
from ensemble_material import checked, import_crest, xyz_text
from ensemble_select import select_ensemble


def run(args):
    output = args.output_dir
    if output.exists(): raise ValueError('use a new output directory; source materials are never overwritten')
    if args.operation == 'import':
        template = read_material(args.material); packet, sha = read_json(args.run)
        result = import_crest(template, packet, sha); members = result['members']
    elif args.operation == 'sample':
        spec, sha = read_json(args.input)
        result = sample_complex(spec, **{k: getattr(args, k) for k in ('mode', 'samples', 'max_attempts', 'seed', 'min_separation', 'max_separation', 'translation', 'rotation_degrees', 'clash_scale')})
        result['input_file_sha256'] = sha; members = result['members']
    else:
        source, sha = read_json(args.ensemble)
        result = select_ensemble(source, **{k: getattr(args, k) for k in ('energy_window', 'rmsd', 'max_selected', 'max_pairs', 'max_candidates', 'max_search')})
        result['source_sha256'] = sha
        members = [m for m in source['members'] if m['id'] in result['selected_ids']]
    files = {}; refinement = []
    for index, member in enumerate(members, 1):
        if member.get('material') is None: continue
        m = checked(member['material'])
        if m['coordinates'] is None: continue
        # Files use generated names rather than untrusted ensemble member IDs.
        base = f'members/{index:04d}'
        text = xyz_text(m['atoms'], m['coordinates'])
        files[base + '/geometry.xyz'] = text
        files[base + '/material.json'] = json.dumps(m['value'], indent=2, ensure_ascii=False, allow_nan=False) + '\n'
        refinement.append({'member_id': member['id'], 'geometry': base + '/geometry.xyz', 'material': base + '/material.json',
                           'charge': m['value']['charge'], 'multiplicity': m['value']['multiplicity'], 'electronic_state': m['value']['electronic_state'],
                           'energy': member.get('energy'), 'derivation': m['value'].get('derivation'),
                           'next_step': 'Choose an explicit compatible SP/optimization method and solvent, then submit an independent Job'})
    result['exports'] = refinement
    files['result.json'] = json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False) + '\n'
    files['refinement.json'] = json.dumps({'schema_version': 'chemical-refinement-manifest/1', 'members': refinement,
        'scope': 'Prepared inputs only; no optimization, state verification, convergence or higher-level energy reuse implied'}, indent=2, ensure_ascii=False, allow_nan=False) + '\n'
    output.mkdir(parents=True)
    for name, text in files.items():
        target = output / name; target.parent.mkdir(parents=True, exist_ok=True); target.write_text(text)
    return result


if __name__ == '__main__':
    run(parse_arguments())
