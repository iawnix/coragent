"""Bounded CREST parsing and replay from unchanged primary outputs."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / '_shared'))
from xyz import PERIODIC_TABLE, validate_electronic_state

HARTREE_TO_KCAL = 627.5094740631
PRIMARY = ('crest.out', 'crest_conformers.xyz', 'crest_best.xyz', 'crest.energies')
READ_LIMITS = {'member_limit_reached', 'energy_table_limit_reached'}


def sha(raw):
    return 'sha256:' + hashlib.sha256(raw).hexdigest()


def version(text):
    found = set(re.findall(r'\bVersion\s*:?\s*(\d+\.\d+\.\d+)\b', text, re.I))
    return next(iter(found)) if len(found) == 1 else None


def number(value):
    result = float(value.replace('D', 'E').replace('d', 'e'))
    if not math.isfinite(result):
        raise ValueError('nonfinite value')
    return result


def input_geometry(raw):
    value = json.loads(raw)
    if value.get('schema_version') != 'chemical-material/1' or (value.get('geometry') or {}).get('unit') != 'angstrom':
        raise ValueError('chemical material with angstrom coordinates required')
    if value.get('electronic_state', {}).get('kind') != 'ground':
        raise ValueError('CREST profile requires an explicit ground-state declaration')
    atoms = value.get('atoms')
    if not isinstance(atoms, list) or not 1 <= len(atoms) <= 256:
        raise ValueError('1..256 atoms required')
    ids = [a.get('atom_id') for a in atoms]
    if any(not isinstance(i, str) or not i for i in ids) or len(set(ids)) != len(ids) or ids != value.get('atom_order', {}).get('output_atom_ids'):
        raise ValueError('material atom IDs/order inconsistent')
    rows = []
    for a in atoms:
        p = a.get('coordinates')
        if a.get('element') not in PERIODIC_TABLE[1:] or a.get('isotope') is not None:
            raise ValueError('unsupported element or explicit isotope masses')
        if not isinstance(p, list) or len(p) != 3 or any(type(x) not in (int, float) or not math.isfinite(x) for x in p):
            raise ValueError('finite Cartesian coordinates required')
        rows.append([a['element'], *p])
    validate_electronic_state(rows, value.get('charge'), value.get('multiplicity'))
    return value, rows


def frames(text, maximum):
    lines = text.splitlines(); result = []; errors = []; row = 0
    while row < len(lines):
        if not lines[row].strip():
            row += 1
            continue
        if len(result) >= maximum:
            errors.append('member_limit_reached'); break
        try:
            count = int(lines[row])
            if not 1 <= count <= 256 or row + count + 2 > len(lines):
                raise ValueError('invalid count or incomplete frame')
            title = lines[row + 1].strip()
            energy = number(title)
            atoms = []
            for line in lines[row + 2:row + count + 2]:
                fields = line.split()
                if len(fields) != 4 or fields[0] not in PERIODIC_TABLE[1:]:
                    raise ValueError('element and three coordinates required')
                atoms.append([fields[0], *[number(v) for v in fields[1:]]])
            result.append({'index': len(result) + 1, 'energy_hartree': energy, 'atoms': atoms, 'comment': title})
            row += count + 2
        except (ValueError, IndexError) as exc:
            errors.append(f'frame_{len(result) + 1}: {exc}'); break
    if not result: errors.append('no_complete_frames')
    return result, errors


def parse_primary(directory, elements, max_members=256):
    if type(max_members) is not int or not 1 <= max_members <= 1024:
        raise ValueError('max-members must be 1..1024')
    directory = Path(directory); texts = {}; digests = {}; errors = []
    for name in PRIMARY:
        path = directory / name
        if not path.is_file():
            errors.append('missing:' + name); texts[name] = ''; continue
        try:
            if path.stat().st_size > 64 * 1024 * 1024:
                errors.append('oversized:' + name); texts[name] = ''; continue
            raw = path.read_bytes()
        except OSError:
            errors.append('unreadable:' + name); texts[name] = ''; continue
        digests[name] = sha(raw)
        texts[name] = raw.decode('utf-8', errors='replace')
    log = texts['crest.out']
    detected = version(log)
    if detected != '3.0.2': errors.append('unsupported_or_missing_version')
    if 'CREST terminated normally.' not in log: errors.append('normal_termination_missing')
    members, broken = frames(texts['crest_conformers.xyz'], max_members); errors += broken
    member_limited = 'member_limit_reached' in broken
    best, broken = frames(texts['crest_best.xyz'], 1); errors += ['best:' + s for s in broken]
    relatives = []
    for line in texts['crest.energies'].splitlines():
        if not line.strip(): continue
        if len(relatives) >= max_members:
            errors.append('energy_table_limit_reached'); break
        try:
            fields = line.split()
            if len(fields) != 2 or int(fields[0]) != len(relatives) + 1:
                raise ValueError('energy indexes must be contiguous from one')
            relatives.append(number(fields[1]))
        except (ValueError, IndexError) as exc:
            errors.append('energy_table:' + str(exc)); break
    energy_limited = 'energy_table_limit_reached' in errors
    if len(relatives) != len(members) or member_limited != energy_limited:
        errors.append('energy_member_counts_differ')
    lowest = min((m['energy_hartree'] for m in members), default=None)
    # A limited prefix need not contain the global minimum. Compare its energy
    # differences against the separately retained native best geometry instead.
    if member_limited and len(best) == 1:
        lowest = best[0]['energy_hartree']
    for member in members:
        index = member['index'] - 1
        problems = []
        if [a[0] for a in member['atoms']] != elements: problems.append('element_order_differs')
        expected = (member['energy_hartree'] - lowest) * HARTREE_TO_KCAL
        if index >= len(relatives): problems.append('relative_energy_missing')
        elif abs(relatives[index] - expected) > .002: problems.append('relative_energy_disagrees')
        member.update(relative_energy_kcal_mol=relatives[index] if index < len(relatives) else None, issues=problems)
        errors += [f'member_{index + 1}:' + reason for reason in problems]
    best_matches = []
    if len(best) == 1:
        b = best[0]
        for m in members:
            same_atoms = len(m['atoms']) == len(b['atoms']) and all(a[0] == c[0] and max(abs(x - y) for x, y in zip(a[1:], c[1:])) <= 1e-6 for a, c in zip(m['atoms'], b['atoms']))
            if same_atoms and abs(m['energy_hartree'] - b['energy_hartree']) <= 1e-7 and abs(m['energy_hartree'] - lowest) <= 1e-7:
                best_matches.append(m['index'])
    if len(best) == 1 and [a[0] for a in best[0]['atoms']] != elements:
        errors.append('best:element_order_differs')
    if (not best_matches and not member_limited
            or member_limited and len(best) == 1 and any(m['energy_hartree'] < best[0]['energy_hartree'] - 1e-7 for m in members)):
        errors.append('best_not_a_lowest_energy_member')
    parsing_status = 'invalid' if any(issue not in READ_LIMITS for issue in errors) else 'limited' if errors else 'complete'
    result = {'schema_version': 'chemical-crest-primary/1', 'version': detected,
            'complete': parsing_status == 'complete', 'parsing_status': parsing_status,
            'read_budget': {'max_members': max_members, 'members_read': len(members),
                            'energy_rows_read': len(relatives), 'has_unread_members': member_limited,
                            'has_unread_energy_rows': energy_limited},
            'issues': errors, 'members': members, 'primary_sha256': digests, 'best_member_indexes': best_matches,
            'best_membership_verified': bool(best_matches),
            'energy_scope': 'XYZ comments in hartree, crest.energies in relative kcal/mol; same calculation only, not free energy'}
    if parsing_status == 'limited':
        result['next_action'] = 'Reparse the retained primary files with a larger explicit --max-members budget; do not rerun CREST. The unread tail has not been validated and the total member count is unknown.'
    return result


def reparse(directory, material_path, run_path, max_members=256):
    """Produce a derived run receipt without executing or changing native files."""
    material_path, run_path = Path(material_path), Path(run_path)
    if material_path.stat().st_size > 32 * 1024 * 1024 or run_path.stat().st_size > 64 * 1024 * 1024:
        raise ValueError('material or run receipt exceeds its read limit')
    raw_material, raw_run = material_path.read_bytes(), run_path.read_bytes()
    _, atoms = input_geometry(raw_material)
    original = json.loads(raw_run)
    if (original.get('schema_version') != 'chemical-crest-run/1'
            or original.get('material_sha256') != sha(raw_material)):
        raise ValueError('run receipt must bind the exact source material')
    parsed = parse_primary(directory, [a[0] for a in atoms], max_members)
    original_digests = original.get('primary', {}).get('primary_sha256')
    if (not isinstance(original_digests, dict) or set(original_digests) != set(PRIMARY)
            or parsed['primary_sha256'] != original_digests):
        raise ValueError('reparse requires the unchanged four primary files bound by the original run receipt')
    result = {**original, 'primary': parsed,
              'reparse_of': {'run_sha256': sha(raw_run), 'primary_sha256': original_digests}}
    if original.get('returncode') == 0 and parsed['parsing_status'] != 'invalid':
        result['status'] = 'completed'
        result.pop('error', None)
    else:
        result['status'] = 'failed'
        if original.get('returncode') == 0:
            result['error'] = {'type': 'ValueError', 'reason': 'CREST primary outputs are incomplete or inconsistent'}
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description='Reparse unchanged CREST outputs without rerunning the solver', allow_abbrev=False)
    parser.add_argument('--directory', type=Path, required=True)
    parser.add_argument('--material', type=Path, required=True)
    parser.add_argument('--run', type=Path, required=True, help='Original collected run result.json')
    parser.add_argument('--output', type=Path, required=True, help='New derived run receipt; existing files are never replaced')
    parser.add_argument('--max-members', type=int, default=256)
    args = parser.parse_args(argv)
    try:
        if args.output.exists():
            raise FileExistsError('use a new output file; original evidence is never overwritten')
        result = reparse(args.directory, args.material, args.run, args.max_members)
        with args.output.open('x', encoding='utf-8') as stream:
            stream.write(json.dumps(result, indent=2, allow_nan=False) + '\n')
        print(json.dumps({'output': str(args.output.resolve()), 'status': result['status'],
                          'parsing_status': result['primary']['parsing_status'],
                          'members_read': result['primary']['read_budget']['members_read']}))
        return 0 if result['status'] == 'completed' else 1
    except (ValueError, OSError) as exc:
        print(f'{type(exc).__name__}: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
