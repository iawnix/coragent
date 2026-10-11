"""Explicit Gaussian ground/TD/TDA state and resource contracts."""
import re

import numpy as np
from analysis_material import validate_material, numeric_array
from energy_common import canonical, fields, integer, label, number
from xyz import validate_electronic_state

BOHR_ANGSTROM=.529177210903
EV_HARTREE=27.211386245988
FUNCTIONALS={'HF','B3LYP','PBE1PBE','CAM-B3LYP','wB97XD','APFD'}


def electronic_material(value):
    m=validate_material(value,canonical(value))
    if not 1<=len(m['atoms'])<=128 or m['coordinates'] is None: raise ValueError('electronic calculation requires 1..128 supplied atoms')
    if any(a.get('isotope') is not None for a in m['atoms']): raise ValueError('explicit isotope masses require a dedicated Gaussian input adapter')
    validate_electronic_state([(a['element'],0,0,0) for a in m['atoms']],value.get('charge'),value.get('multiplicity'))
    return m


def settings(value):
    fields(value,('theory','functional','basis','root','nstates','threads','memory_mb','timeout_seconds','max_cycles','spin_tolerance'),'electronic settings')
    if value.get('theory') not in ('ground','td','tda'): raise ValueError('theory must be ground, td or tda')
    if value.get('functional') not in FUNCTIONALS: raise ValueError('functional outside verified analytic-gradient route scope')
    if not isinstance(value.get('basis'),str) or not re.fullmatch(r'[A-Za-z0-9+*(),._-]+',value['basis']): raise ValueError('one explicit Gaussian basis token required')
    if value['basis'].lower() in ('gen','genecp','chkbasis'): raise ValueError('external or checkpoint basis not supported here')
    result=dict(value)
    for key,default,maximum in [('threads',1,256),('memory_mb',2000,1048576),('max_cycles',100,1000)]:
        result[key]=integer(value.get(key,default),key,maximum)
    result['timeout_seconds']=number(value.get('timeout_seconds',600.),'timeout_seconds',True)
    if result['timeout_seconds']>86400: raise ValueError('timeout exceeds one day')
    result['spin_tolerance']=number(value.get('spin_tolerance',.1),'spin_tolerance',True)
    if result['spin_tolerance']>.5: raise ValueError('spin tolerance exceeds supported bound')
    if value['theory']!='ground':
        result['nstates']=integer(value.get('nstates'), 'nstates',32);result['root']=integer(value.get('root'),'root',32)
        if result['root']>result['nstates']: raise ValueError('root exceeds nstates')
    elif value.get('root') is not None or value.get('nstates') is not None: raise ValueError('ground calculation cannot select TD roots')
    return result


def state_scope(m,s):
    state=m['value'].get('electronic_state',{});mult=m['value']['multiplicity']
    if s['theory']=='ground':
        if state.get('kind')!='ground': raise ValueError('ground SCF requires explicit ground-state declaration within the requested multiplicity')
    elif (mult!=1 or state.get('kind')!='excited' or state.get('root')!=s['root']
          or state.get('method') != ('TDA' if s['theory']=='tda' else 'TDHF' if s['functional']=='HF' else 'TDDFT')):
        raise ValueError('TD/TDA scope is singlet excitations of a closed-shell singlet reference, with matching method/root declaration')


def route(m,s,task):
    if task not in ('sp','opt'): raise ValueError('electronic task must be sp or opt')
    state_scope(m,s)
    reference='R' if m['value']['multiplicity']==1 else 'U'
    method=reference+s['functional']
    excitation='' if s['theory']=='ground' else f' {s["theory"].upper()}=(Singlets,NStates={s["nstates"]},Root={s["root"]})'
    operation='Force' if task=='sp' else f'Opt=(Cartesian,MaxCycles={s["max_cycles"]})'
    return f'#p {method}/{s["basis"]}{excitation} {operation} NoSymm SCF=(Tight,MaxCycle={s["max_cycles"]})'


def input_text(m,s,task,xyz=None):
    coords=m['coordinates'] if xyz is None else numeric_array(xyz,m['coordinates'].shape,'input geometry')
    text=f'%nprocshared={s["threads"]}\n%mem={s["memory_mb"]}MB\n'+route(m,s,task)+'\n\nBound state calculation\n\n'
    text+=f'{m["value"]["charge"]} {m["value"]["multiplicity"]}\n'
    text+=''.join(a['element']+' '+' '.join(format(float(v),'.16g') for v in row)+'\n' for a,row in zip(m['atoms'],coords))
    return text+'\n'
