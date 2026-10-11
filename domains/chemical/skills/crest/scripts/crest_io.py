"""Strict primary-output parsing for CREST 3.0.2; preserve a valid partial prefix."""
import hashlib
import math
from pathlib import Path
import re

from xyz import PERIODIC_TABLE

HARTREE_TO_KCAL = 627.5094740631
PRIMARY = ('crest.out', 'crest_conformers.xyz', 'crest_best.xyz', 'crest.energies')


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
    if len(relatives) != len(members): errors.append('energy_member_counts_differ')
    lowest = min((m['energy_hartree'] for m in members), default=None)
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
    if not best_matches: errors.append('best_not_a_lowest_energy_member')
    return {'schema_version': 'chemical-crest-primary/1', 'version': detected, 'complete': not errors,
            'issues': errors, 'members': members, 'primary_sha256': digests, 'best_member_indexes': best_matches,
            'energy_scope': 'XYZ comments in hartree, crest.energies in relative kcal/mol; same calculation only, not free energy'}
