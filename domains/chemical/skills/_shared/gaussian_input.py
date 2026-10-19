"""Cartesian Gaussian structure serialization and round-trip verification."""
import math
import re

from geometry_safety import parse_gaussian_coordinate_blocks


def read_structures(body, count):
    parts = [part.strip() for part in re.split(r'\n[ \t]*\n', body) if part.strip()]
    if len(parts) != 2 * count:
        raise ValueError(f'expected {count} complete title and charge/multiplicity + Cartesian coordinate sections')
    structures = []
    for index in range(count):
        title, geometry = parts[2 * index:2 * index + 2]
        if re.fullmatch(r'-?\d+\s+\d+', title.splitlines()[0]):
            raise ValueError(f'structure {index + 1} needs a title before its charge/multiplicity')
        lines = geometry.splitlines()
        if not re.fullmatch(r'-?\d+\s+\d+', lines[0]):
            raise ValueError(f'structure {index + 1} is missing its charge/multiplicity header')
        blocks = parse_gaussian_coordinate_blocks(geometry)
        if len(blocks) != 1 or len(blocks[0]) != len(lines) - 1:
            raise ValueError(f'structure {index + 1} requires complete plain Cartesian coordinates')
        charge, multiplicity = map(int, lines[0].split())
        if multiplicity < 1 or any(not math.isfinite(v) for atom in blocks[0] for v in atom[1:]):
            raise ValueError('positive multiplicity and finite coordinates required')
        structures.append({'title': title, 'charge': charge, 'multiplicity': multiplicity, 'atoms': blocks[0]})
    return structures


def verify_structures(body, expected):
    """Compare serialized coordinates and state with the already mapped request."""
    actual = read_structures(body, len(expected))
    for index, (got, wanted) in enumerate(zip(actual, expected), 1):
        if any(got[key] != wanted[key] for key in ('title', 'charge', 'multiplicity')):
            raise ValueError(f'structure {index} title or electronic state differs after serialization')
        atoms = wanted['atoms']
        if [a[0] for a in got['atoms']] != [a[0] for a in atoms]:
            raise ValueError(f'structure {index} atom count or element order differs after serialization')
        if any(not math.isclose(x, y, rel_tol=1e-11, abs_tol=5e-10)
               for a, b in zip(got['atoms'], atoms) for x, y in zip(a[1:], b[1:])):
            raise ValueError(f'structure {index} coordinates differ after serialization')
    return actual


def serialize_structures(structures):
    parts = []
    for structure in structures:
        title = structure['title']
        if not isinstance(title, str) or not title.strip() or any(not line.strip() for line in title.splitlines()):
            raise ValueError('structure title must contain nonempty lines')
        if type(structure['charge']) is not int or type(structure['multiplicity']) is not int:
            raise ValueError('integer charge and multiplicity required')
        rows = []
        for atom in structure['atoms']:
            if len(atom) != 4 or any(not math.isfinite(float(v)) for v in atom[1:]):
                raise ValueError('Cartesian atoms require an element and three finite coordinates')
            rows.append(atom[0] + ' ' + ' '.join(f'{float(v):.12g}' for v in atom[1:]))
        parts.append(f'{title}\n\n{structure["charge"]} {structure["multiplicity"]}\n' + '\n'.join(rows) + '\n\n')
    body = ''.join(parts)
    verify_structures(body, structures)
    return body


def inspect_qst_structures(body, route):
    kinds = re.findall(r'\bqst([23])\b', route, re.I)
    if not kinds:
        return
    if len(kinds) != 1:
        raise ValueError('declare exactly one QST2 or QST3 operation per Gaussian link')
    count = int(kinds[0])
    try:
        structures = read_structures(body, count)
    except ValueError as error:
        raise ValueError(f'QST{count} requires {count} complete structures: {error}') from error
    reference = structures[0]
    for structure in structures[1:]:
        if [a[0] for a in structure['atoms']] != [a[0] for a in reference['atoms']]:
            raise ValueError('QST structures must have identical atom counts and element order; supply an explicit atom mapping before serialization')
        if any(structure[key] != reference[key] for key in ('charge', 'multiplicity')):
            raise ValueError('QST structures must have identical charge/multiplicity')
    return structures
