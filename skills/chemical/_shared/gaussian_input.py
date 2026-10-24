"""Pure Gaussian input validation, structure serialization and round-trip checks."""
import importlib.util
import math
from pathlib import Path, PurePosixPath
import re

# Load the pinned sibling without importing a same-named ambient module or
# changing the control interpreter's module search path.
_geometry_spec = importlib.util.spec_from_file_location(
    'gaussian_geometry_safety', Path(__file__).with_name('geometry_safety.py'))
_geometry = importlib.util.module_from_spec(_geometry_spec)
_geometry_spec.loader.exec_module(_geometry)
parse_gaussian_coordinate_blocks = _geometry.parse_gaussian_coordinate_blocks
assess_gaussian_input = _geometry.assess_gaussian_input
require_safe = _geometry.require_safe


def coordinate_text(value, precision=12):
    """Keep Cartesian coordinates unambiguous to Gaussian's integer flag parser."""
    mantissa, separator, exponent = format(float(value), f'.{precision}g').partition('e')
    if '.' not in mantissa:
        mantissa += '.0'
    return mantissa + separator + exponent


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
            rows.append(atom[0] + ' ' + ' '.join(coordinate_text(v) for v in atom[1:]))
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


def local_reference(value):
    path = PurePosixPath(value.strip())
    if path.is_absolute() or '..' in path.parts or not path.parts or '\\' in value:
        raise ValueError('Gaussian file references must be relative staged paths')
    return str(path)


def inspect_input(path, method, basis, charge, multiplicity, threads, memory_mb):
    text = Path(path).read_text()
    if not text.endswith('\n\n'):
        raise ValueError('Gaussian input must end with a blank line (two trailing newline characters)')
    sections = re.split(r'(?im)^\s*--Link1--\s*$', text)
    references, checkpoints, routes = set(), set(), []
    for section in sections:
        preceding_checkpoints = set(checkpoints)
        route_match = re.search(r'(?ms)^\s*(#[^\n]*(?:\n[^\n]+)*?)\n\s*\n', section)
        if not route_match:
            raise ValueError('Gaussian input needs a route section followed by a blank line')
        route = route_match.group(1).strip(); routes.append(route)
        coordinate = r'(?im)^\s*(?:[A-Z][a-z]?|\d+)\s+(?:[-+]?\d+(?:\.\d*)?(?:[EeDd][-+]?\d+)?\s+){2}[-+]?\d+(?:\.\d*)?(?:[EeDd][-+]?\d+)?\s*$'
        title = section[route_match.end():].split('\n\n', 1)[0]
        if re.search(coordinate, route) or re.search(coordinate, title):
            raise ValueError('Gaussian coordinate record in route/title section; restore blank section boundaries')
        if f'{method}/{basis}'.lower() not in re.sub(r'\s+', '', route).lower():
            raise ValueError('every Gaussian link must explicitly match the requested method/basis')
        cpus = re.findall(r'(?im)^\s*%nproc(?:shared)?\s*=\s*(\d+)\s*$', section)
        if len(cpus) != 1 or int(cpus[0]) != threads:
            raise ValueError('every Gaussian link must declare the requested %nprocshared')
        memory = re.findall(r'(?im)^\s*%mem\s*=\s*(\d+)\s*(MB|GB)\s*$', section)
        if len(memory) != 1 or int(memory[0][0]) * (1024 if memory[0][1].upper() == 'GB' else 1) != memory_mb:
            raise ValueError('every Gaussian link must declare the requested memory in MB or GB')
        headers = re.findall(r'(?m)^\s*(-?\d+)\s+(\d+)\s*$', section[route_match.end():])
        if not headers and not re.search(r'geom\s*=\s*\(?allcheck', route, re.I):
            raise ValueError('missing charge/multiplicity header')
        if any((int(c), int(m)) != (charge, multiplicity) for c, m in headers):
            raise ValueError('input charge/multiplicity differs from request')
        inspect_qst_structures(section[route_match.end():], route)
        for key, value in re.findall(r'(?im)^\s*%(\w+)\s*=\s*(.*?)\s*$', section):
            key = key.lower()
            if key in {'chk', 'oldchk'}:
                ref = local_reference(value)
                if key == 'oldchk' and ref not in checkpoints: references.add(ref)
                if key == 'chk': checkpoints.add(ref)
                if key == 'chk' and re.search(r'(?:geom|guess)\s*=\s*\(?(?:allcheck|check|read)', route, re.I) and ref not in preceding_checkpoints and not re.search(r'(?im)^\s*%oldchk\s*=', section):
                    references.add(ref)
            elif key not in {'mem', 'nproc', 'nprocshared', 'nosave'}:
                raise ValueError(f'unsupported Link 0 directive %{key}; use staged chk/oldchk, mem and nprocshared')
        for ref in re.findall(r'(?m)^\s*@([^\s]+)\s*$', section): references.add(local_reference(ref))
        if re.search(r'\b(external|include)\s*=', route, re.I):
            raise ValueError('external executable and route include directives are unsupported')
        if re.search(r'\birc\b', route, re.I):
            size = re.search(r'\bstepsize\s*=\s*([^,\s)]+)', route, re.I)
            if size and (not re.fullmatch(r'-?[1-9]\d*', size[1])):
                raise ValueError('Gaussian IRC StepSize must be a nonzero integer; fractional values such as 0.5 are invalid')
    geometry_reports = assess_gaussian_input(text, profile='ts_candidate')
    for report in geometry_reports:
        require_safe(report)
    return {'routes': routes, 'references': sorted(references), 'checkpoints': sorted(checkpoints),
            'geometry_safety': {'status': 'passed' if geometry_reports else 'not_assessed',
                                'blocks': geometry_reports}}
