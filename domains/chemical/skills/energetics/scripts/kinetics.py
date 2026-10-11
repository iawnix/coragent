"""Concentration-form elementary TST and explicitly bounded initial branching."""
import math

from energy_analysis import profile
from energy_common import (HARTREE_J_MOL, R, canonical, concentration, fields,
    finite_result, integer, label, number, schema, source)

KB_OVER_H = 2.0836619123327578e10  # K^-1 s^-1, exact SI h and k_B


def tst(spec):
    schema(spec, 'chemical-tst-input/1', ('profile', 'reactant_state', 'transition_state', 'active_reactants',
        'transmission_coefficient', 'evidence', 'concentrations_mol_l'))
    study = spec['profile']
    if study.get('quantity') != 'G': raise ValueError('TST requires a Gibbs free-energy profile')
    data = profile(study)
    states = {s['id']:s['stoichiometry'] for s in study['states']}
    initial, target = spec.get('reactant_state'), spec.get('transition_state')
    if initial not in states or target not in states or initial == target: raise ValueError('distinct known reactant and TS states required')
    active = spec.get('active_reactants')
    if not isinstance(active,dict) or not active or set(active)-set(states[initial]): raise ValueError('explicit active reactants required')
    for key,n in active.items():
        integer(n,'active coefficient',3)
        if n != states[initial][key]: raise ValueError('active coefficient must equal its reactant-state coefficient')
    order = sum(active.values())
    if not 1 <= order <= 3: raise ValueError('TST molecularity supports 1..3')
    spectators = {k:n for k,n in states[initial].items() if k not in active}
    if any(states[target].get(k) != n for k,n in spectators.items()): raise ValueError('spectators must be identical on both sides of the barrier')
    activated = {k:n for k,n in states[target].items() if k not in spectators}
    if len(activated) != 1 or list(activated.values()) != [1]: raise ValueError('TS state needs one activated complex plus unchanged spectators')
    ts_key = next(iter(activated)); ts_source = study['species'][ts_key]
    if ts_source.get('thermal',{}).get('rrho',{}).get('stationary_type') != 'transition_state':
        raise ValueError('activated complex needs a declared first-order TS thermal source')
    for key in active:
        item = study['species'][key]
        if item['schema_version'] != 'chemical-free-energy-ensemble-input/1' and item.get('thermal',{}).get('rrho',{}).get('stationary_type') != 'minimum':
            raise ValueError('active reactants must have minimum thermochemistry')
    evidence = spec.get('evidence')
    if not isinstance(evidence,list) or not evidence: raise ValueError('elementary-step evidence references required')
    for item in evidence:
        fields(item,('source_sha256','note'),'evidence');source(item.get('source_sha256'));label(item.get('note'),'evidence note')
    kappa = number(spec.get('transmission_coefficient'),'transmission_coefficient',True)
    if kappa > 1: raise ValueError('this classical TST implementation permits 0 < kappa <= 1; tunnelling is separate')
    energies = {row['id']:row['absolute_hartree'] for row in data['rows']}
    barrier = energies[target]-energies[initial]
    if barrier < 0: raise ValueError('negative barrier is outside activated-TST assumptions')
    temperature = data['conditions']['temperature_k']; c0 = concentration(data['conditions']['standard_state'],temperature)
    logk = math.log(kappa)+math.log(KB_OVER_H*temperature)+(1-order)*math.log(c0)-barrier*HARTREE_J_MOL/(R*temperature)
    rate = math.exp(logk) if logk > -745 else 0.
    actual = spec.get('concentrations_mol_l'); flux = None; log_flux = None
    if actual is not None:
        if not isinstance(actual,dict) or set(actual) != set(active): raise ValueError('concentrations must specify exactly the active reactants')
        for c in actual.values():
            if number(c,'concentration') < 0: raise ValueError('concentration cannot be negative')
        if any(c == 0 for c in actual.values()): flux = 0.
        else:
            log_flux = logk + sum(n*math.log(actual[k]) for k,n in active.items())
            flux = math.exp(log_flux) if log_flux > -745 else 0.
    return finite_result({'schema_version':'chemical-tst-result/1','request_sha256':canonical(spec),
        'barrier_hartree':barrier,'temperature_k':temperature,'standard_concentration_mol_l':c0,
        'molecularity':order,'rate_constant':rate,'log_rate_constant':logk,
        'rate_unit':{1:'s^-1',2:'L mol^-1 s^-1',3:'L^2 mol^-2 s^-1'}[order],
        'initial_flux_mol_l_s':flux,'log_initial_flux':log_flux,'transmission_coefficient':kappa,
        'activated_complex_sha256':canonical(ts_source),
        'precursor_sha256':canonical({'state':states[initial],'active':active,
            'species':{k:study['species'][k] for k in states[initial]},'conditions':data['conditions']}),
        'conditions':data['conditions'],'model_signature':data['model_signature'],
        'elementary_step_certified':False,'evidence':evidence,
        'scope':'Classical concentration-form TST conditional on supplied elementary-step evidence. No tunnelling, diffusion, automatic recrossing or population equilibration model.'})


def branching(spec):
    schema(spec,'chemical-branching-input/1',('channels','assumptions'))
    expected = {'equilibrated_common_precursor':True,'irreversible_products':True,'no_product_interconversion':True}
    if spec.get('assumptions') != expected: raise ValueError('branching requires explicit equilibrated common precursor, irreversible products and no product interconversion')
    channels = spec.get('channels')
    if not isinstance(channels,dict) or not 2 <= len(channels) <= 32: raise ValueError('branching requires 2..32 named channels')
    rows = {label(k,'channel id'):tst(v) for k,v in channels.items()}; first = next(iter(rows.values()))
    if len({r['activated_complex_sha256'] for r in rows.values()}) != len(rows): raise ValueError('duplicate activated complex; distinct labels or notes cannot establish distinct reaction channels')
    actual=next(iter(channels.values())).get('concentrations_mol_l')
    if any(c.get('concentrations_mol_l')!=actual for c in channels.values()): raise ValueError('common precursor channels require identical actual concentrations when supplied')
    if actual is not None and any(v<=0 for v in actual.values()): raise ValueError('initial branching at zero precursor concentration is undefined; use conditional rates or a network')
    for r in rows.values():
        if r['precursor_sha256'] != first['precursor_sha256'] or r['model_signature'] != first['model_signature']:
            raise ValueError('branching requires identical precursors, source models and conditions')
    peak = max(r['log_rate_constant'] for r in rows.values())
    weights = {k:math.exp(r['log_rate_constant']-peak) for k,r in rows.items()}; total = math.fsum(weights.values())
    return finite_result({'schema_version':'chemical-branching-result/1','request_sha256':canonical(spec),
        'channels':[{ 'id':k,'initial_branch_fraction':weights[k]/total,**r} for k,r in rows.items()],
        'assumptions':expected,'scope':'Initial irreversible branching for the supplied common precursor and channels; not time-dependent yields, reversibility, depletion or global selectivity.'})
