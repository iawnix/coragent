"""Finite improved-tangent NEB with optional climbing image and capped force relaxation."""
import math
from pathlib import Path
import subprocess

import numpy as np

from analysis_material import numeric_array
from ensemble_material import canonical, xyz_text
from gradient_contract import evaluate_evidence
from material import object_fields
from path_contract import candidate_material, endpoints, geometry, integer, positive
from path_process import write_json


def nudged_forces(images, energies, forces, spring, climbing=None):
    result = np.zeros_like(images)
    for i in range(1, len(images)-1):
        forward = (images[i+1]-images[i]).reshape(-1); backward = (images[i]-images[i-1]).reshape(-1)
        ef, ei, eb = energies[i+1], energies[i], energies[i-1]
        if ef > ei > eb: tangent = forward
        elif ef < ei < eb: tangent = backward
        else:
            high, low = max(abs(ef-ei),abs(eb-ei)), min(abs(ef-ei),abs(eb-ei))
            if high < 1e-15: tangent = forward + backward
            else: tangent = forward*high + backward*low if ef > eb else forward*low + backward*high
        norm = np.linalg.norm(tangent)
        if norm < 1e-12: raise ValueError('degenerate NEB tangent; revise path images')
        tangent = tangent / norm; f = forces[i].reshape(-1); projection = np.dot(f,tangent)*tangent
        result[i] = (f - 2*projection if i == climbing else f - projection + spring*(np.linalg.norm(forward)-np.linalg.norm(backward))*tangent).reshape(images[i].shape)
    return result


def neb(spec, output, calculator_factory):
    object_fields(spec, ('schema_version','reactant','product','mapping','settings','image_count','images','max_steps','fmax','spring','step_size','max_displacement','climb_after'), 'NEB input')
    if spec.get('schema_version') != 'chemical-neb-input/1': raise ValueError('chemical-neb-input/1 required')
    m,p,pxyz,order = endpoints(spec); s = spec['settings']
    if not isinstance(s, dict): raise ValueError('calculator settings object required')
    count = integer(spec.get('image_count', 7),3,32,'image_count'); steps = integer(spec.get('max_steps',100),0,1000,'max_steps')
    fmax = positive(spec.get('fmax',.001),'fmax'); spring = positive(spec.get('spring',.05),'spring')
    step_size = positive(spec.get('step_size',1.),'step_size'); max_displacement = positive(spec.get('max_displacement',.05),'max_displacement')
    climb_after = spec.get('climb_after')
    if climb_after is not None: integer(climb_after,0,steps,'climb_after')
    if spec.get('images') is not None:
        images = numeric_array(spec['images'], (count,len(m['ids']),3), 'path images')
        if not np.allclose(images[0],m['coordinates'],atol=1e-9,rtol=0) or not np.allclose(images[-1],pxyz,atol=1e-9,rtol=0): raise ValueError('path endpoints differ from mapped materials')
        interpolation = 'provided_in_reactant_atom_order'
    else:
        images = np.array([(1-t)*m['coordinates']+t*pxyz for t in np.linspace(0,1,count)])
        interpolation = 'linear_cartesian_no_alignment'
    for image in images: geometry(image)
    if any(np.linalg.norm(b-a) < 1e-10 for a,b in zip(images,images[1:])): raise ValueError('duplicate adjacent NEB images')
    out = Path(output)
    if out.exists(): raise ValueError('new output directory required')
    calculator = calculator_factory(m,s); out.mkdir(parents=True)
    result = {'schema_version':'chemical-neb-result/1', 'status':'running', 'source_sha256':canonical(spec),
              'model':calculator.model, 'atom_ids':m['ids'], 'product_to_reactant_order':order,
              'settings':{'image_count':count,'max_steps':steps,'fmax_hartree_per_angstrom':fmax,'spring_hartree_per_angstrom2':spring,
                          'step_size_angstrom2_per_hartree':step_size,'max_displacement_angstrom':max_displacement,'climb_after':climb_after,
                          'optimizer':'capped_projected_force_relaxation','interpolation':interpolation},
              'endpoint_status':'fixed_supplied_geometries_not_certified_minima', 'iterations':[], 'images':images.tolist(),
              'scope':'Finite single-surface NEB candidate search; endpoints not optimized, no minimum/saddle/IRC certification or exhaustive path coverage'}
    write_json(out/'result.json', result)
    cached_endpoints = {}; energies = None
    try:
        for step in range(steps+1):
            evaluations = []; result['current_iteration'] = {'index':step,'evaluated_images':[]}
            write_json(out/'result.json',result)
            for i, xyz in enumerate(images):
                if i in cached_endpoints: value = cached_endpoints[i]
                else:
                    value = calculator.evaluate(xyz, out/f'iterations/{step:04d}/image_{i:03d}')
                    if i in (0,count-1): cached_endpoints[i]=value
                energy, force = evaluate_evidence(value,m,xyz,calculator.model)
                evaluations.append((energy,force))
                result['current_iteration']['evaluated_images'].append({'index':i,'evidence':value})
                write_json(out/'result.json',result)
            energies = np.array([e[0] for e in evaluations]); forces = np.array([e[1] for e in evaluations])
            result.pop('pending_images', None)
            result.update(images=images.tolist(),energies_hartree=energies.tolist(),max_neb_force_hartree_per_angstrom=None)
            high = int(np.argmax(energies[1:-1]))+1
            climbing = high if climb_after is not None and step >= climb_after else None
            nudged = nudged_forces(images,energies,forces,spring,climbing)
            maximum = float(np.linalg.norm(nudged[1:-1],axis=2).max())
            result['iterations'].append({'index':step,'energies_hartree':energies.tolist(),'max_neb_force_hartree_per_angstrom':maximum,'climbing_image':climbing})
            result['max_neb_force_hartree_per_angstrom'] = maximum
            if maximum <= fmax and (climb_after is None or climbing is not None):
                result['status']='converged'; break
            if step == steps: result['status']='step_limit'; break
            displacement = nudged[1:-1]*step_size
            norms = np.linalg.norm(displacement,axis=2)
            displacement *= min(1.,max_displacement/max(float(norms.max()),1e-30))
            proposed = images.copy(); proposed[1:-1] += displacement
            for xyz in proposed: geometry(xyz)
            images = proposed
            # Persist the exact next geometry before any new calculator attempt.
            result['pending_images'] = images.tolist(); write_json(out/'result.json',result)
    except (ValueError, RuntimeError, OSError, subprocess.TimeoutExpired) as exc:
        result.update(status='failed',error={'type':type(exc).__name__,'reason':str(exc)})
    if energies is not None:
        high = int(np.argmax(energies[1:-1]))+1
        # Last fully evaluated geometries, never a newer unevaluated iterate.
        xyz = np.array(result['images'][high])
        candidate = candidate_material(m,xyz,{'operation':'neb_image','source_sha256':canonical(spec),'image_index':high})
        write_json(out/'candidate.material.json',candidate); (out/'candidate.xyz').write_text(xyz_text(m['atoms'],xyz))
        result['candidate']={'image_index':high,'kind':'highest_evaluated_internal_image','validated_ts':False}
    write_json(out/'result.json',result)
    return result
