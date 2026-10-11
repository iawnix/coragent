"""Finite projected mean-energy descent with Newton correction of the energy gap."""
import copy
from pathlib import Path
import subprocess

import numpy as np
from electronic_contract import electronic_material,settings
from energy_common import canonical,integer,number,schema
from path_process import write_json
from crossing_check import check_crossing,projected,surface


def bound_material(template,xyz):
    value=copy.deepcopy(template['value'])
    for a,row in zip(value['atoms'],xyz):a['coordinates']=list(map(float,row))
    # Crossing motion may change connectivity; retain its origin, not an asserted graph.
    value['derivation']={'operation':'crossing_candidate','source_material_sha256':template['sha256'],'source_graph':value.get('graph')}
    value['graph']=None;value['fragments']={'groups':None,'source':'unassigned'}
    return value


def mecp(spec,output,calculator_factory):
    schema(spec,'chemical-mecp-input/1',('material','multiplicities','settings','max_steps','max_evaluations','step_size',
        'max_displacement_angstrom','gap_tolerance_hartree','gradient_tolerance','hessian_step_angstrom'))
    base=electronic_material(spec['material']);multiplicities=spec.get('multiplicities');config=settings(spec['settings'])
    if config['theory']!='ground' or base['value']['electronic_state'].get('kind')!='ground':raise ValueError('MECP requires ground-spin SCF surfaces')
    if not isinstance(multiplicities,list) or len(multiplicities)!=2 or multiplicities[0]==multiplicities[1]:raise ValueError('two different spin multiplicities required')
    materials=[]
    for mult in multiplicities:
        integer(mult,'multiplicity',20);value=copy.deepcopy(base['value']);value['multiplicity']=mult
        value['electronic_state']={'kind':'ground'};materials.append(electronic_material(value))
    steps=spec.get('max_steps',100)
    if type(steps) is not int or not 0<=steps<=1000:raise ValueError('max_steps must be 0..1000')
    budget=integer(spec.get('max_evaluations',500),'max_evaluations',10000)
    alpha=number(spec.get('step_size',.2),'step_size',True);cap=number(spec.get('max_displacement_angstrom',.1),'max displacement',True)
    if cap>1:raise ValueError('max displacement cannot exceed 1 angstrom')
    gap_tol=number(spec.get('gap_tolerance_hartree',1e-5),'gap tolerance',True);grad_tol=number(spec.get('gradient_tolerance',1e-4),'gradient tolerance',True)
    hstep=spec.get('hessian_step_angstrom')
    if hstep is not None:
        number(hstep,'hessian step',True)
        if not 1e-4<=hstep<=.01:raise ValueError('Hessian step must be 1e-4..0.01 angstrom')
    calculators=[calculator_factory(m,config) for m in materials];xyz=base['coordinates'].copy();out=Path(output)
    out.mkdir(parents=True,exist_ok=False)
    result={'schema_version':'chemical-mecp-result/1','request_sha256':canonical(spec),'status':'running','iterations':[],
        'evaluations':0,'optimizer':'capped_projected_mean_gradient_with_Newton_gap_correction',
        'state_scope':'two distinct declared spin SCF surfaces; wavefunction identity not proved','validated_global_mecp':False}
    def evaluate(coords,folder):
        records=[]
        for i,(m,calc) in enumerate(zip(materials,calculators)):
            if result['evaluations']>=budget:raise RuntimeError('evaluation budget exhausted')
            result['evaluations']+=1;write_json(out/'result.json',result)
            record=calc.evaluate(coords,out/folder/f'state_{i}')
            surface(record,m,coords);records.append(record)
        return records
    try:
        for iteration in range(steps+1):
            records=evaluate(xyz,Path(f'iterations/{iteration:04d}'))
            values=[surface(v,m,xyz) for v,m in zip(records,materials)]
            gap,diff,tangent,lagrange=projected(*values)
            result['iterations'].append({'index':iteration,'coordinates':xyz.tolist(),'energies_hartree':[v[0] for v in values],
                'gap_hartree':gap,'max_projected_gradient':float(np.max(np.linalg.norm(tangent.reshape(xyz.shape),axis=1))),
                'sources':[v['source_sha256'] for v in records]})
            candidate=[bound_material(m,xyz) for m in materials]
            # The candidate replaces identity only; evaluator declarations use plain ground kind.
            check_input={'schema_version':'chemical-crossing-check-input/1','materials':candidate,'surfaces':records,
                'gap_tolerance_hartree':gap_tol,'gradient_tolerance':grad_tol}
            result.update(candidate_materials=candidate,candidate_evaluations=records,check=check_crossing(check_input))
            if result['check']['numerically_stationary']:
                if hstep is not None:
                    hessians=[np.zeros((xyz.size,xyz.size)),np.zeros((xyz.size,xyz.size))];sources=[[],[]]
                    for axis in range(xyz.size):
                        delta=np.zeros(xyz.size);delta[axis]=hstep;delta=delta.reshape(xyz.shape)
                        minus=evaluate(xyz-delta,Path(f'hessian/{axis:04d}/minus'));plus=evaluate(xyz+delta,Path(f'hessian/{axis:04d}/plus'))
                        for i,m in enumerate(materials):
                            hessians[i][:,axis]=(surface(plus[i],m,xyz+delta)[1]-surface(minus[i],m,xyz-delta)[1])/(2*hstep)
                            sources[i]+=[minus[i]['source_sha256'],plus[i]['source_sha256']]
                    records=copy.deepcopy(records)
                    for i in range(2):
                        records[i]['final']['hessian_hartree_per_angstrom2']=hessians[i].tolist()
                        records[i]['hessian_provenance']={'method':'central_difference_of_gradients','step_angstrom':hstep,'source_sha256s':sources[i]}
                    check_input['surfaces']=records;result.update(candidate_evaluations=records,check=check_crossing(check_input))
                result['status']='seam_saddle' if result['check']['curvature']['status']=='fail' else 'converged'
                break
            if iteration==steps:result['status']='step_limit';break
            displacement=(-alpha*tangent-gap*diff/np.dot(diff,diff)).reshape(xyz.shape)
            maximum=float(np.max(np.linalg.norm(displacement,axis=1)))
            if maximum>cap:displacement*=cap/maximum
            xyz=xyz+displacement
            if not np.isfinite(xyz).all():raise ValueError('nonfinite MECP update')
            write_json(out/'result.json',result)
    except (ValueError,RuntimeError,OSError,subprocess.TimeoutExpired) as exc:
        result.update(status='failed',error={'type':type(exc).__name__,'reason':str(exc)})
    finally:write_json(out/'result.json',result)
    return result
