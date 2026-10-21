"""Reaction-independent material, endpoint and solver contracts."""
import math
import re

import numpy as np

from analysis_material import numeric_array
from conformers import state_comparison
from ensemble_material import canonical, checked, derive_material, xyz_text
from material import object_fields
from xyz import validate_electronic_state
from geometry_safety import assess, require_safe
from gaussian_input import serialize_structures, inspect_qst_structures
from job_resources import runtime_settings

BOHR_ANGSTROM = .529177210903


def positive(value, name):
    if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
        raise ValueError(name + ' must be finite and positive')
    return value


def integer(value, low, high, name):
    if type(value) is not int or not low <= value <= high: raise ValueError(f'{name} must be {low}..{high}')
    return value


def material(value):
    m = checked(value)
    if m['coordinates'] is None or not 2 <= len(m['atoms']) <= 256: raise ValueError('2..256 atoms with supplied coordinates required')
    if value.get('electronic_state', {}).get('kind') != 'ground': raise ValueError('this profile requires explicit ground state')
    if any(a.get('isotope') is not None for a in m['atoms']): raise ValueError('explicit isotope masses need a separate solver input')
    validate_electronic_state([[a['element']] for a in m['atoms']], value.get('charge'), value.get('multiplicity'))
    bonded = [(b.GetBeginAtomIdx(), b.GetEndAtomIdx()) for b in m['mol'].GetBonds()] if m['mol'] is not None else None
    geometry(m['coordinates'], elements=[a['element'] for a in m['atoms']], bonded_pairs=bonded)
    return m


def geometry(xyz, *, elements=None, bonded_pairs=None, reaction_pairs=(), profile='general'):
    xyz = numeric_array(xyz, (len(xyz), 3), 'geometry')
    # When a low-level caller has no material metadata, retain the historical
    # role of this helper (finite/non-coincident coordinates only).  All
    # material-bound callers pass real elements and bonds below, enabling the
    # stronger non-reaction contact check without rejecting synthetic/path
    # fixtures that intentionally omit atom identity.
    known_elements = elements if elements is not None else ['H'] * len(xyz)
    require_safe(assess(known_elements, xyz, bonded_pairs=bonded_pairs,
                        reaction_pairs=reaction_pairs, profile=profile,
                        clash_scale=.75))
    return xyz


def settings(value, backend):
    value = runtime_settings(value, memory=backend == 'gaussian')
    common = ('method', 'threads', 'timeout_seconds', 'solvent', 'solvent_model')
    allowed = (*common, 'basis', 'memory_mb', 'max_cycles') if backend == 'gaussian' else (*common, 'opt_level', 'force_constant')
    object_fields(value, allowed, 'solver settings')
    if not set(common) <= value.keys(): raise ValueError('explicit method, resources and solvent settings required')
    integer(value['threads'], 1, 256, 'threads'); positive(value['timeout_seconds'], 'timeout_seconds')
    if value['solvent_model'] == 'gas':
        if value['solvent'] is not None: raise ValueError('gas model requires null solvent')
    elif value['solvent_model'] == ('SMD' if backend == 'gaussian' else 'ALPB'):
        if not isinstance(value['solvent'], str) or not re.fullmatch(r'[A-Za-z0-9_+-]+', value['solvent']): raise ValueError('single solvent identifier required')
    else: raise ValueError('unsupported solvent model')
    if backend == 'xtb':
        if value['method'] not in ('gfn1', 'gfn2'): raise ValueError('xTB profile supports gfn1/gfn2')
        if value.get('opt_level', 'tight') not in ('normal', 'tight', 'verytight'): raise ValueError('unsupported opt level')
        if 'force_constant' in value: positive(value['force_constant'], 'force_constant')
    elif backend == 'gaussian':
        for name in ('method', 'basis'):
            if not isinstance(value.get(name), str) or not re.fullmatch(r'[A-Za-z0-9+*(),._-]+', value[name]): raise ValueError('single method/basis tokens required')
        if value['basis'].lower() in ('gen', 'genecp', 'chkbasis'): raise ValueError('external basis sections are outside this preparer')
        integer(value.get('memory_mb'), 1, 1048576, 'memory_mb')
        integer(value.get('max_cycles', 200), 1, 2000, 'max_cycles')
    else: raise ValueError('unknown backend')
    return dict(value)


def ordered_other(reference, other, pairs):
    if not isinstance(pairs, list) or len(pairs) != len(reference['ids']): raise ValueError('complete explicit atom mapping required')
    if any(not isinstance(p, list) or len(p) != 2 for p in pairs): raise ValueError('mapping requires pairs of local atom IDs')
    left, right = [p[0] for p in pairs], [p[1] for p in pairs]
    if (len(other['ids']) != len(left) or len(set(left)) != len(left) or len(set(right)) != len(right)
            or set(left) != set(reference['ids']) or set(right) != set(other['ids'])): raise ValueError('mapping must be a complete bijection')
    mapping = dict(pairs); order = [other['ids'].index(mapping[i]) for i in reference['ids']]
    if any(reference['atoms'][i]['element'] != other['atoms'][j]['element'] for i,j in enumerate(order)):
        raise ValueError('mapped elements differ')
    state = state_comparison(reference['value'], other['value'])
    if state['status'] != 'compatible_declarations': raise ValueError('endpoint state declarations must be explicitly compatible')
    return other['coordinates'][order], order


def endpoints(spec):
    r, p = material(spec['reactant']), material(spec['product'])
    pxyz, order = ordered_other(r, p, spec.get('mapping'))
    return r, p, pxyz, order


def gaussian_header(s, route):
    solvent = '' if s['solvent_model'] == 'gas' else f' SCRF=(SMD,Solvent={s["solvent"]})'
    return f'%chk=path.chk\n%nprocshared={s["threads"]}\n%mem={s["memory_mb"]}MB\n#p {s["method"]}/{s["basis"]} {route} SCF=Tight Int=UltraFine NoSymm{solvent}\n\n'


def gaussian_geometry(m, xyz, title):
    if len(xyz) != len(m['atoms']):
        raise ValueError('coordinate count differs from material')
    return serialize_structures([{'title': title, 'charge': m['value']['charge'],
                                 'multiplicity': m['value']['multiplicity'],
                                 'atoms': [(a['element'], *row) for a, row in zip(m['atoms'], xyz)]}])


def qst(spec):
    object_fields(spec, ('schema_version', 'reactant', 'product', 'mapping', 'guess', 'guess_mapping', 'settings'), 'QST input')
    if spec.get('schema_version') != 'chemical-qst-input/1': raise ValueError('chemical-qst-input/1 required')
    r, p, pxyz, order = endpoints(spec); s = settings(spec['settings'], 'gaussian')
    geometries = [('reactant', r['coordinates']), ('product', pxyz)]
    correspondence = {'product_to_reactant_order': order}
    if spec.get('guess') is not None:
        guess = material(spec['guess']); xyz, order = ordered_other(r, guess, spec.get('guess_mapping'))
        geometries.append(('guess', xyz)); correspondence['guess_to_reactant_order'] = order
    elif 'guess_mapping' in spec: raise ValueError('guess mapping without a guess')
    kind = 'QST3' if len(geometries) == 3 else 'QST2'
    route = f'Opt=({kind},CalcFC,MaxCycles={s.get("max_cycles", 200)}) Freq'
    body = ''.join(gaussian_geometry(r, xyz, name) for name, xyz in geometries)
    inspect_qst_structures(body, route)
    text = gaussian_header(s, route) + body
    return text, {'schema_version': 'chemical-qst-preparation/1', 'kind': kind, 'source_sha256': canonical(spec),
                  'atom_ids': r['ids'], 'correspondence': correspondence, 'settings': s,
                  'endpoint_status': 'supplied_geometries_not_certified_minima',
                  'scope': 'Explicitly mapped inputs only; no endpoint optimization, mechanism or elementary-step certification'}, r


def candidate_material(template, coords, provenance):
    """A path image retains lineage without asserting reactant connectivity."""
    value = derive_material(template, coords, provenance)
    value['derivation'].update(reference_graph=value['graph'], reference_fragments=value['fragments'],
                               source_atom_maps={a['atom_id']:a['atom_map'] for a in value['atoms']})
    value['graph'] = None; value['identity'] = None
    value['fragments'] = {'groups':None, 'source':'unknown'}; value['arrangement'] = 'unspecified'
    for atom in value['atoms']: atom['atom_map'] = None
    value['unknown_fields'] = sorted(set(value['unknown_fields']) | {'graph','fragments','arrangement'})
    value['limitations'].append('Path candidate connectivity is unassigned; reference graph, fragments and atom-map tags remain only in derivation. Local atom IDs retain correspondence.')
    return value
