"""Local geometry observations under explicit atom identity; never a mechanism verdict."""
import math

import numpy as np
from rdkit import Chem

from conformers import internal_value, state_comparison
from ensemble_material import canonical, checked
from material import object_fields


def ids(value, material, name, minimum=1):
    if (not isinstance(value, list) or not minimum <= len(value) <= len(material['ids'])
            or any(not isinstance(i, str) or i not in material['ids'] for i in value)
            or len(set(value)) != len(value)):
        raise ValueError(name + ' requires distinct known local atom IDs')
    return [material['ids'].index(i) for i in value]


def align(reference, target, indices):
    """Fit target to reference with a proper rotation on an explicit subset."""
    x, y = reference[indices], target[indices]
    xc, yc = x.mean(axis=0), y.mean(axis=0)
    u, _, vt = np.linalg.svd((y-yc).T @ (x-xc))
    rotation = u @ np.diag([1., 1., 1. if np.linalg.det(u@vt) >= 0 else -1.]) @ vt
    fitted = (target-yc) @ rotation+xc
    residual = np.linalg.norm(fitted-reference, axis=1)
    return fitted, {'rmsd_angstrom': float(np.sqrt(np.mean(residual[indices]**2))),
                    'rotation_determinant': float(np.linalg.det(rotation)),
                    'fit_rank': int(min(np.linalg.matrix_rank(x-xc), np.linalg.matrix_rank(y-yc))),
                    'per_atom_displacement_angstrom': residual.tolist()}


def coordinates(spec, material):
    rows = spec.get('coordinates', [])
    if not isinstance(rows, list) or len(rows) > 256: raise ValueError('at most 256 internal coordinates')
    result = []
    labels = set()
    for row in rows:
        object_fields(row, ('id', 'atoms', 'minimum', 'maximum'), 'internal coordinate')
        label = row.get('id')
        if not isinstance(label,str) or not label or len(label)>128 or label in labels:
            raise ValueError('unique internal coordinate IDs required')
        labels.add(label)
        group = ids(row.get('atoms'),material,'coordinate atoms',2)
        if len(group) not in (2,3,4): raise ValueError('coordinate needs 2/3/4 atoms')
        low, high = row.get('minimum'), row.get('maximum')
        if (low is None) != (high is None): raise ValueError('provide both coordinate bounds or neither')
        if low is not None:
            if any(type(v) not in (int,float) or not math.isfinite(v) for v in (low,high)):
                raise ValueError('finite bounds required')
            if len(group)==2 and not 0 <= low <= high: raise ValueError('distance bounds require 0 <= minimum <= maximum')
            if len(group)==3 and not 0 <= low <= high <=180: raise ValueError('angle bounds must be within 0..180')
            if len(group)==4 and not all(-180<=v<=180 for v in (low,high)): raise ValueError('dihedral bounds must be within -180..180')
        result.append((row,group))
    return result


def coordinate_rows(definitions, xyz):
    result = []
    for row, group in definitions:
        value = internal_value(xyz[group])
        low, high = row.get('minimum'), row.get('maximum')
        verdict = 'not_assessed'
        if value is not None and low is not None:
            inside = low <= value <= high if low <= high else value >= low or value <= high
            verdict = 'within_declared_bounds' if inside else 'outside_declared_bounds'
        result.append({**row, 'kind': {2:'distance',3:'angle',4:'dihedral'}[len(group)],
                       'unit': 'angstrom' if len(group)==2 else 'degree', 'value': value, 'status': verdict})
    return result


def local_diagnostics(spec):
    object_fields(spec, ('schema_version','material','reference','mapping','reaction_center',
                        'spectators','coordinates','allowed_contacts','contact_scale'), 'local diagnostics')
    if spec.get('schema_version') != 'chemical-local-diagnostics-input/1': raise ValueError('local diagnostics schema required')
    m = checked(spec['material']); xyz = m['coordinates']
    if xyz is None or not 1 <= len(m['ids']) <= 256: raise ValueError('1..256 atoms with coordinates required')
    center = ids(spec.get('reaction_center'),m,'reaction_center')
    spectators = ids(spec.get('spectators', []),m,'spectators',0)
    if set(center)&set(spectators): raise ValueError('reaction center and spectators must be disjoint')
    scale = spec.get('contact_scale', .75)
    if type(scale) not in (int,float) or not math.isfinite(scale) or not .1 <= scale <= 1.5:
        raise ValueError('contact_scale must be within 0.1..1.5')
    allowed = spec.get('allowed_contacts', [])
    if not isinstance(allowed,list) or len(allowed)>512: raise ValueError('bounded allowed contact list required')
    pairs = set()
    for pair in allowed:
        group=ids(pair,m,'allowed contact',2)
        if len(group)!=2: raise ValueError('contact requires exactly two atoms')
        pairs.add(tuple(sorted(group)))
    table = Chem.GetPeriodicTable()
    radii = [table.GetRcovalent(a['element']) for a in m['atoms']]
    contacts=[]; neighbors=[]
    distances=np.linalg.norm(xyz[:,None]-xyz[None,:],axis=2)
    for i in center:
        nearest=sorted((j for j in range(len(xyz)) if j!=i),key=lambda j:distances[i,j])[:6]
        neighbors.append({'atom_id':m['ids'][i], 'nearest':[{'atom_id':m['ids'][j], 'distance_angstrom':float(distances[i,j])} for j in nearest]})
    for i in range(len(xyz)):
        for j in range(i+1,len(xyz)):
            if i not in center and j not in center: continue
            threshold=scale*(radii[i]+radii[j])
            if distances[i,j] < threshold:
                contacts.append({'atoms':[m['ids'][i],m['ids'][j]],'distance_angstrom':float(distances[i,j]),
                    'threshold_angstrom':float(threshold),'declared_allowed':(i,j) in pairs})
    result={'schema_version':'chemical-local-diagnostics-result/1','source_sha256':canonical(spec),
        'material_sha256':m['sha256'],'atom_ids':m['ids'],'reaction_center':spec['reaction_center'],
        'neighbors':neighbors,'short_contacts':contacts,'contact_scale':scale,
        'coordinates':coordinate_rows(coordinates(spec,m),xyz),'comparison':None,
        'electronic_structure':'not_assessed','scientific_verdict':'not_assessed',
        'scope':'Explicit-coordinate observations and covalent-radius proximity heuristic; no bond-order, valence, electronic-state or TS certification'}
    if spec.get('reference') is not None:
        ref=checked(spec['reference'])
        if ref['coordinates'] is None or len(ref['ids'])!=len(m['ids']): raise ValueError('reference coordinates and matching atom count required')
        mapping=spec.get('mapping')
        if (not isinstance(mapping,list) or len(mapping)!=len(m['ids']) or
            any(not isinstance(p,list) or len(p)!=2 or any(not isinstance(i,str) for i in p) for p in mapping)):
            raise ValueError('complete material-to-reference mapping required')
        mapping_dict=dict(mapping)
        if set(mapping_dict)!=set(m['ids']) or set(mapping_dict.values())!=set(ref['ids']): raise ValueError('mapping must be a bijection')
        order=[ref['ids'].index(mapping_dict[i]) for i in m['ids']]
        if any((a['element'],a.get('isotope'))!=(ref['atoms'][j]['element'],ref['atoms'][j].get('isotope')) for a,j in zip(m['atoms'],order)):
            raise ValueError('mapped elements/isotopes differ')
        refxyz=ref['coordinates'][order]
        heavy=[i for i,a in enumerate(m['atoms']) if a['element']!='H'] or list(range(len(xyz)))
        _,global_fit=align(refxyz,xyz,heavy)
        _,local_fit=align(refxyz,xyz,center)
        result['comparison']={'reference_sha256':ref['sha256'],'heavy_atom_fit':global_fit,
            'reaction_center_fit':local_fit,'state_declarations':state_comparison(ref['value'],m['value']),
            'spectator_rmsd_after_center_fit_angstrom':float(np.sqrt(np.mean(np.array(local_fit['per_atom_displacement_angstrom'])[spectators]**2))) if spectators and local_fit['fit_rank']>=2 else None,
            'spectator_fit_status':'assessed' if spectators and local_fit['fit_rank']>=2 else 'not_assessed_requires_noncollinear_center_and_spectators'}
    elif 'mapping' in spec: raise ValueError('mapping without reference')
    return result
