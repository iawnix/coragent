"""Transition-density character tracking with explicit AO overlap metrics."""
import numpy as np

from analysis_material import numeric_array, validate_material
from energy_common import canonical, fields, integer, number, schema, source


def metric(raw,name):
    n=len(raw) if isinstance(raw,list) else 0
    if not 1<=n<=128: raise ValueError('AO metric size must be 1..128')
    matrix=numeric_array(raw,(n,n),name)
    if not np.allclose(matrix,matrix.T,rtol=0,atol=1e-10) or np.linalg.eigvalsh(matrix)[0]<=1e-10:
        raise ValueError('AO overlap metric must be symmetric positive definite')
    return matrix


def track_states(spec):
    schema(spec,'chemical-state-tracking-input/1',('frames','links','initial_root','minimum_overlap','minimum_margin','degeneracy_hartree'))
    frames=spec.get('frames');links=spec.get('links')
    if not isinstance(frames,list) or not 2<=len(frames)<=32 or not isinstance(links,list) or len(links)!=len(frames)-1:
        raise ValueError('tracking needs 2..32 frames and one overlap link per adjacent pair')
    floor=number(spec.get('minimum_overlap',.8),'minimum_overlap',True)
    margin=number(spec.get('minimum_margin',.1),'minimum_margin',True)
    gap=number(spec.get('degeneracy_hartree',1e-4),'degeneracy_hartree',True)
    if floor>1 or margin>1:raise ValueError('overlap thresholds must not exceed one')
    parsed=[];identities=None
    for frame in frames:
        fields(frame,('material','source_sha256','basis_definition_sha256','ao_overlap','states'),'state frame')
        source(frame.get('source_sha256'));source(frame.get('basis_definition_sha256'))
        m=validate_material(frame['material'],canonical(frame['material']))
        current=(m['ids'],[(a['element'],a.get('isotope')) for a in m['atoms']],m['value'].get('charge'))
        if identities is not None and identities!=current:raise ValueError('tracking requires explicit consistent atom ordering, isotopes and charge')
        identities=current
        if m['coordinates'] is None:raise ValueError('tracking frames require bound geometries')
        overlap=metric(frame.get('ao_overlap'),'AO overlap');states=frame.get('states')
        if not isinstance(states,list) or not 1<=len(states)<=32:raise ValueError('bounded candidate state list required')
        rows={}
        for state in states:
            fields(state,('root','energy_hartree','multiplicity','transition_density'),'state')
            root=integer(state.get('root'),'root',128)
            if root in rows:raise ValueError('duplicate frame root')
            integer(state.get('multiplicity'),'multiplicity',100);number(state.get('energy_hartree'),'state energy')
            density=numeric_array(state.get('transition_density'),overlap.shape,'AO transition density')
            norm=float(np.trace(density.T@overlap@density@overlap))
            if norm<=1e-16:raise ValueError('nonzero transition density required')
            rows[root]=(state,density,norm)
        parsed.append((overlap,rows))
    current=integer(spec.get('initial_root'),'initial_root',128)
    if current not in parsed[0][1]:raise ValueError('initial root missing from first frame')
    rows=[];ambiguous=False;changed=False
    for index,link in enumerate(links):
        fields(link,('from_source_sha256','to_source_sha256','source_sha256','ao_cross_overlap'),'overlap link')
        source(link.get('source_sha256'))
        if link.get('from_source_sha256')!=frames[index]['source_sha256'] or link.get('to_source_sha256')!=frames[index+1]['source_sha256']:
            raise ValueError('cross-overlap frame binding differs')
        sa,left=parsed[index];sb,right=parsed[index+1]
        cross=numeric_array(link.get('ao_cross_overlap'),(len(sa),len(sb)),'AO cross overlap')
        joint=np.block([[sa,cross],[cross.T,sb]])
        if np.linalg.eigvalsh(joint)[0]<-1e-8:raise ValueError('inconsistent AO cross-overlap metric')
        selected,da,na=left[current];candidates=[]
        for root,(state,db,nb) in right.items():
            if state['multiplicity']!=selected['multiplicity']:continue
            score=abs(float(np.trace(da.T@cross@db@cross.T)))/(na*nb)**.5
            if score>1+1e-7:raise ValueError('transition-density overlap exceeds Cauchy bound')
            candidates.append({'root':root,'overlap':min(score,1.),'energy_hartree':state['energy_hartree']})
        candidates.sort(key=lambda item:(-item['overlap'],item['root']))
        if not candidates:
            rows.append({'from_frame':index,'from_root':current,'status':'inconclusive','reason':'no_same_spin_candidates'});ambiguous=True;break
        best=candidates[0];second=candidates[1]['overlap'] if len(candidates)>1 else 0.
        degenerate=any(abs(other['energy_hartree']-selected['energy_hartree'])<=gap and other['multiplicity']==selected['multiplicity'] for root,(other,_,_) in left.items() if root!=current)
        degenerate=degenerate or any(abs(c['energy_hartree']-best['energy_hartree'])<=gap for c in candidates[1:])
        uncertain=best['overlap']<floor or best['overlap']-second<margin or degenerate
        rows.append({'from_frame':index,'from_root':current,'candidate_root':best['root'], 'candidates':candidates,
            'near_degenerate':degenerate,'status':'inconclusive' if uncertain else 'root_changed' if best['root']!=current else 'consistent_character'})
        if uncertain:ambiguous=True;break
        changed=changed or best['root']!=current;current=best['root']
    return {'schema_version':'chemical-state-tracking-result/1','request_sha256':canonical(spec),
        'status':'inconclusive' if ambiguous else 'root_changed' if changed else 'consistent_character',
        'final_root':None if ambiguous else current,'links':rows,
        'thresholds':{'minimum_overlap':floor,'minimum_margin':margin,'degeneracy_hartree':gap},
        'scope':'Absolute normalized AO transition-density overlaps with supplied intra/cross-geometry metrics; tracks transition character, not full many-electron wavefunction fidelity. Gaussian printed configurations alone cannot supply these tensors.'}
