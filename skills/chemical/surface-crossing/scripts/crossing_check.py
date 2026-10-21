"""Energy degeneracy, constrained stationarity and optional seam curvature checks."""
import numpy as np

from analysis_material import numeric_array
from electronic_contract import electronic_material, settings
from energy_common import canonical, fields, number, schema, source


def surface(value,m,xyz):
    if not isinstance(value,dict) or value.get('schema_version')!='chemical-electronic-evaluation/1':raise ValueError('electronic evaluation contract required')
    if value.get('atom_ids')!=m['ids'] or value.get('elements')!=[a['element'] for a in m['atoms']] or value.get('charge')!=m['value']['charge']:
        raise ValueError('surface atom/charge binding differs')
    if value.get('multiplicity')!=m['value']['multiplicity'] or value.get('electronic_state')!=m['value']['electronic_state']:
        raise ValueError('surface state binding differs')
    if value.get('coordinate_unit')!='angstrom' or value.get('gradient_unit')!='hartree/angstrom' or value.get('gradient_quantity')!='dE/dR':
        raise ValueError('surface coordinate/gradient units or sign differ')
    source(value.get('source_sha256'));final=value.get('final',{})
    coords=numeric_array(final.get('coordinates'),xyz.shape,'surface coordinates')
    if not np.allclose(coords,xyz,rtol=0,atol=2e-6):raise ValueError('surface geometry differs')
    model=value.get('model',{});settings(model)
    if model.get('theory')!='ground' or m['value']['electronic_state'].get('kind')!='ground':raise ValueError('crossing solver only supports distinct ground-spin SCF surfaces')
    spin=(m['value']['multiplicity']-1)/2;observed=number(final.get('spin_squared'),'spin squared')
    tolerance=number(model.get('spin_tolerance'),'spin tolerance',True)
    if tolerance>.5 or abs(observed-spin*(spin+1))>tolerance:raise ValueError('surface spin evidence outside tolerance')
    gradient=numeric_array(final.get('gradient_hartree_per_angstrom'),xyz.shape,'surface gradient').reshape(-1)
    return number(final.get('energy_hartree'),'surface energy'),gradient


def projected(a,b):
    ea,ga=a;eb,gb=b;difference=ga-gb;norm=float(np.linalg.norm(difference))
    if norm<1e-10:raise ValueError('singular gradient difference; regular crossing seam cannot be established')
    mean=(ga+gb)/2;lagrange=float(np.dot(mean,difference)/(norm*norm));tangent=mean-lagrange*difference
    return ea-eb,difference,tangent,lagrange


def seam_basis(xyz,difference):
    n=len(xyz);centered=xyz-xyz.mean(axis=0);columns=[]
    for axis in np.eye(3):
        columns.append(np.tile(axis,(n,1)).reshape(-1));columns.append(np.cross(centered,axis).reshape(-1))
    columns.append(difference/np.linalg.norm(difference))
    matrix=np.stack(columns,axis=1);u,s,_=np.linalg.svd(matrix,full_matrices=True)
    rank=int(np.sum(s>max(s[0],1.)*1e-8))
    return u[:,rank:]


def check_crossing(spec):
    schema(spec,'chemical-crossing-check-input/1',('materials','surfaces','gap_tolerance_hartree','gradient_tolerance','curvature_tolerance'))
    if not isinstance(spec.get('materials'),list) or len(spec['materials'])!=2 or not isinstance(spec.get('surfaces'),list) or len(spec['surfaces'])!=2:
        raise ValueError('crossing check requires two materials and evaluations')
    materials=[electronic_material(v) for v in spec['materials']];a,b=materials;xyz=a['coordinates']
    if a['ids']!=b['ids'] or a['coordinates'].shape!=b['coordinates'].shape or not np.allclose(xyz,b['coordinates'],rtol=0,atol=1e-9):raise ValueError('crossing materials require identical ordered geometries')
    if ([(x['element'],x.get('isotope')) for x in a['atoms']] != [(x['element'],x.get('isotope')) for x in b['atoms']] or a['value']['charge']!=b['value']['charge']):raise ValueError('crossing surfaces must share composition and charge')
    if a['value']['multiplicity']==b['value']['multiplicity']:raise ValueError('same-spin degeneracy/conical intersections are outside this solver')
    values=[surface(v,m,xyz) for v,m in zip(spec['surfaces'],materials)]
    models=[v['model'] for v in spec['surfaces']]
    if models[0]!=models[1]:raise ValueError('crossing models must match')
    gap,difference,tangent,lagrange=projected(*values)
    gap_tol=number(spec.get('gap_tolerance_hartree',1e-5),'gap tolerance',True)
    grad_tol=number(spec.get('gradient_tolerance',1e-4),'gradient tolerance',True)
    curvature_tol=number(spec.get('curvature_tolerance',1e-5),'curvature tolerance',True)
    grad=float(np.max(np.linalg.norm(tangent.reshape(xyz.shape),axis=1)))
    stationary=abs(gap)<=gap_tol and grad<=grad_tol;curvature={'status':'not_assessed','reason':'both Cartesian Hessians required'}
    hessians=[v['final'].get('hessian_hartree_per_angstrom2') for v in spec['surfaces']]
    if all(h is not None for h in hessians):
        checked=[]
        for h,v in zip(hessians,spec['surfaces']):
            h=numeric_array(h,(xyz.size,xyz.size),'surface Hessian')
            if not np.allclose(h,h.T,rtol=0,atol=1e-5):raise ValueError('surface Hessian is not symmetric')
            if not v.get('hessian_provenance'):raise ValueError('Hessian provenance required')
            checked.append((h+h.T)/2)
        lagrangian=(checked[0]+checked[1])/2-lagrange*(checked[0]-checked[1]);basis=seam_basis(xyz,difference)
        eigenvalues=np.linalg.eigvalsh(basis.T@lagrangian@basis)
        curvature={'status':'pass' if np.all(eigenvalues>curvature_tol) else 'fail' if np.any(eigenvalues<-curvature_tol) else 'inconclusive',
            'eigenvalues_hartree_per_angstrom2':eigenvalues.tolist(),'seam_internal_dimensions':len(eigenvalues),
            'excluded':'Cartesian translations, rotations and regular seam normal'}
    return {'schema_version':'chemical-crossing-check-result/1','request_sha256':canonical(spec),
        'energy_gap_hartree':gap,'max_projected_gradient_hartree_per_angstrom':grad,'lagrange_multiplier':lagrange,
        'numerically_stationary':stationary,'curvature':curvature,
        'numerical_mecp_conditions':stationary and curvature['status']=='pass',
        'thresholds':{'gap_hartree':gap_tol,'gradient_hartree_per_angstrom':grad_tol,'curvature':curvature_tol},
        'electronic_state_identity':'declared_spin_and_S2_only_not_wavefunction_verified',
        'scope':'Different-spin regular-seam constrained stationarity/curvature, conditional on supplied state derivatives; not ordinary TS/IRC, global MECP, SOC, same-spin conical intersection or nonadiabatic dynamics.'}
