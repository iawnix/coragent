"""Closed, well-mixed mass-action networks with adaptive step-doubled RK4."""
from collections import Counter
import math

import numpy as np

from energy_common import canonical, composition, fields, finite_result, integer, label, material, number, schema, source
from kinetics import tst


def side(value, species):
    if not isinstance(value,dict) or not value or set(value)-set(species): raise ValueError('nonempty known stoichiometric side required')
    for n in value.values(): integer(n,'stoichiometric coefficient',8)
    if sum(value.values()) > 8: raise ValueError('network reaction order exceeds 8')
    return value


def totals(stoich, materials):
    atoms = Counter();charge = 0
    for k,n in stoich.items():
        atoms.update({a:v*n for a,v in composition(materials[k]).items()});charge += n*materials[k]['value']['charge']
    return atoms,charge


def rate_constant(value, reactants, temperature):
    if value.get('schema_version') == 'chemical-tst-input/1':
        result = tst(value)
        if value['active_reactants'] != reactants or result['temperature_k'] != temperature: raise ValueError('TST active reactants/temperature differ from network channel')
        return result['rate_constant']
    fields(value,('value','order','unit','source_sha256','note'),'rate constant')
    order = sum(reactants.values())
    if type(value.get('order')) is not int or value['order'] != order or value.get('unit') != f'(mol/L)^{1-order}/s':
        raise ValueError('rate order/unit disagrees with mass-action reactants')
    source(value.get('source_sha256'));label(value.get('note'),'rate evidence note')
    k = number(value.get('value'),'rate constant')
    if k < 0: raise ValueError('rate constant cannot be negative')
    return k


def network(spec):
    schema(spec,'chemical-kinetic-network-input/1',('species','reactions','temperature_k','initial_mol_l','times_s','solver'))
    temperature = number(spec.get('temperature_k'),'temperature_k',True)
    species = spec.get('species'); reactions = spec.get('reactions')
    if not isinstance(species,dict) or not 1 <= len(species) <= 64: raise ValueError('network requires 1..64 species')
    materials = {label(k,'species id'):material(v) for k,v in species.items()}; ids=list(species)
    if not isinstance(reactions,list) or not 1 <= len(reactions) <= 128: raise ValueError('network requires 1..128 reactions')
    columns=[];powers=[];rates=[];reaction_ids=set()
    for reaction in reactions:
        fields(reaction,('id','reactants','products','forward','reverse'),'reaction')
        key=label(reaction.get('id'),'reaction id')
        if key in reaction_ids: raise ValueError('duplicate reaction id')
        reaction_ids.add(key)
        left=side(reaction.get('reactants'),species);right=side(reaction.get('products'),species)
        if left == right: raise ValueError('reaction must change concentrations')
        if totals(left,materials) != totals(right,materials): raise ValueError('network atom/isotope/charge imbalance')
        for a,b,rate in [(left,right,reaction['forward'])]+([(right,left,reaction['reverse'])] if reaction.get('reverse') is not None else []):
            # TST requests also bind species, not just reused names.
            if rate.get('schema_version') == 'chemical-tst-input/1':
                for ident in a:
                    declared=rate['profile']['species'][ident]
                    if declared['schema_version']=='chemical-free-energy-ensemble-input/1': declared=declared['members'][0]['thermochemistry']
                    if canonical(declared['electronic']['material']) != canonical(species[ident]): raise ValueError('TST/network species binding differs')
            rates.append(rate_constant(rate,a,temperature))
            powers.append([a.get(k,0) for k in ids]);columns.append([b.get(k,0)-a.get(k,0) for k in ids])
    stoich=np.asarray(columns,dtype=float).T; exponents=np.asarray(powers,dtype=int); constants=np.asarray(rates)
    initial=spec.get('initial_mol_l')
    if not isinstance(initial,dict) or set(initial)!=set(species): raise ValueError('explicit initial concentration for every species required')
    y=np.array([number(initial[k],'initial concentration') for k in ids])
    if np.any(y<0): raise ValueError('initial concentration cannot be negative')
    times=spec.get('times_s')
    if not isinstance(times,list) or not 2<=len(times)<=1001: raise ValueError('2..1001 observation times required')
    times=[number(v,'time') for v in times]
    if times[0]!=0 or any(b<=a for a,b in zip(times,times[1:])): raise ValueError('times must start at zero and strictly increase')
    cfg=fields(spec.get('solver',{}),('rtol','atol_mol_l','max_steps'),'solver')
    rtol=number(cfg.get('rtol',1e-7),'rtol',True);atol=number(cfg.get('atol_mol_l',1e-12),'atol',True)
    if rtol>1e-2 or atol>1e-3: raise ValueError('solver tolerances too loose')
    max_steps=integer(cfg.get('max_steps',100000),'max_steps',1000000)
    # Every left-nullspace invariant includes hidden conserved moieties as well as atom totals.
    u,s,_=np.linalg.svd(stoich,full_matrices=True); rank=int(np.sum(s>max(stoich.shape)*np.finfo(float).eps*(s[0] if len(s) else 1)))
    invariants=u[:,rank:].T; baseline=invariants@y
    initial_y=y.copy();t=0.;dt=(times[-1]-times[0])/100;attempts=0;accepted=0;rejected=0;max_error=0.;max_drift=0.
    rows=[{'time_s':0.,'concentrations_mol_l':dict(zip(ids,y.tolist()))}];status='completed';reason=None
    def rhs(values):
        if np.any(values<0) or not np.isfinite(values).all(): raise ArithmeticError('nonpositive integration stage')
        with np.errstate(over='raise',invalid='raise'):
            flux=constants*np.prod(values[None,:]**exponents,axis=1)
            result=stoich@flux
        if not np.isfinite(result).all(): raise ArithmeticError('nonfinite network derivative')
        return result
    def rk(values,h):
        a=rhs(values);b=rhs(values+h*a/2);c=rhs(values+h*b/2);d=rhs(values+h*c)
        out=values+h*(a+2*b+2*c+d)/6
        if np.any(out<0) or not np.isfinite(out).all(): raise ArithmeticError('negative integration result')
        return out
    for target in times[1:]:
        while t<target:
            if attempts>=max_steps:
                status='step_limit';reason='explicit RK4 budget exhausted; stiff networks may require a dedicated solver';break
            h=min(dt,target-t)
            if t+h==t or h<=0:
                status='failed';reason='time step underflow';break
            attempts+=1
            try:
                coarse=rk(y,h);fine=rk(rk(y,h/2),h/2)
                error=float(np.max(np.abs(fine-coarse)/(15*(atol+rtol*np.maximum(np.abs(y),np.abs(fine))))))
            except (ArithmeticError,FloatingPointError,OverflowError):
                rejected+=1;dt=h*.25;continue
            if error>1:
                rejected+=1;dt=h*max(.1,.9*error**(-.2));continue
            fine = fine + (fine-coarse)/15
            if np.any(fine<0) or not np.isfinite(fine).all():
                rejected+=1;dt=h*.25;continue
            drift=float(np.max(np.abs(invariants@fine-baseline),initial=0.))
            if drift>10*(atol+rtol*max(float(np.max(initial_y)),1e-12)):
                status='failed';reason='stoichiometric invariant drift exceeds tolerance';break
            y=fine;t=target if h==target-t else t+h;accepted+=1
            max_error=max(max_error,error);max_drift=max(max_drift,drift)
            dt=h*min(4.,max(.2,.9*error**(-.2) if error else 4.))
        if status!='completed':break
        rows.append({'time_s':target,'concentrations_mol_l':dict(zip(ids,y.tolist()))})
    return finite_result({'schema_version':'chemical-kinetic-network-result/1','request_sha256':canonical(spec),
        'status':status,'reason':reason,'temperature_k':temperature,'species':ids,'rows':rows,
        'last_state':{'time_s':t,'concentrations_mol_l':dict(zip(ids,y.tolist()))},
        'solver':{'method':'adaptive_RK4_Richardson','rtol':rtol,'atol_mol_l':atol,'max_steps':max_steps,
                  'attempts':attempts,'accepted':accepted,'rejected':rejected,'max_scaled_local_error':max_error,
                  'max_invariant_drift_mol_l':max_drift,'independent_invariants':len(invariants)},
        'thermodynamic_detailed_balance':'not_assessed',
        'scope':'Closed constant-volume well-mixed deterministic mass action at fixed temperature, supplied species and rates; no chemostats, stochastic chemistry, automatic mechanism discovery or stiff-solver guarantee.'})
