"""Analytic kinetics, pathway bookkeeping and independent Job integration."""
import copy
import json
import math
import os
from pathlib import Path
import sys
import time

import pytest
from tests.unit.test_energetics import thermo, molecule

SKILLS=Path(__file__).resolve().parents[2]/'domains/chemical/skills'
sys.path.insert(0,str(SKILLS/'reaction-investigation/scripts'))
import pathway_job
from pathway import pathway
from kinetics import tst,branching,KB_OVER_H
from kinetic_network import network
from energy_common import HARTREE_J_MOL,R


def tst_input(barrier=.02):
    ts=thermo(e=-76.+barrier);ts['thermal']['rrho'].update(stationary_type='transition_state',frequencies_cm1=[-500,1500,3500])
    return {'schema_version':'chemical-tst-input/1','profile':{'schema_version':'chemical-energy-profile-input/1',
        'species':{'A':thermo(),'TS':ts},'states':[{'id':'R','stoichiometry':{'A':1}},{'id':'TS','stoichiometry':{'TS':1}}],
        'reference':'R','quantity':'G','unit':'kJ/mol'},'reactant_state':'R','transition_state':'TS',
        'active_reactants':{'A':1},'transmission_coefficient':1.,
        'evidence':[{'source_sha256':'sha256:'+'d'*64,'note':'Synthetic elementary-step fixture; no real TS claim'}]}


def branch_input():
    return {'schema_version':'chemical-branching-input/1','channels':{'fast':tst_input(.02),'slow':tst_input(.021)},
        'assumptions':{'equilibrated_common_precursor':True,'irreversible_products':True,'no_product_interconversion':True}}


def rate(k,order=1):
    return {'value':k,'order':order,'unit':f'(mol/L)^{1-order}/s','source_sha256':'sha256:'+'a'*64,'note':'Analytic fixture'}


def network_input(reverse=False):
    return {'schema_version':'chemical-kinetic-network-input/1','species':{'A':molecule(),'B':molecule(.1)},
        'temperature_k':298.15,'reactions':[{'id':'r1','reactants':{'A':1},'products':{'B':1},'forward':rate(2.),
            **({'reverse':rate(1.)} if reverse else {})}],
        'initial_mol_l':{'A':1.,'B':0.},'times_s':[0.,.1,.5,1.,3.],
        'solver':{'rtol':1e-8,'atol_mol_l':1e-12}}


def pathway_input():
    species={k:{'material':molecule(i*.1),'origin':{'kind':'provided' if k=='A' else 'hypothesis',
        'source_sha256':'sha256:'+'a'*64,**({} if k=='A' else {'hypothesis_id':'h'})}} for i,k in enumerate('ABC')}
    return {'schema_version':'chemical-pathway-input/1','species':species,
        'hypotheses':{'h':{'statement':'A to B to C','falsifier':'IRC reaches another basin','source_sha256':'sha256:'+'b'*64}},
        'steps':[{'id':f's{i}','kind':'elementary','hypothesis_id':'h','reactants':{a:1},'products':{b:1},
            'mapping':[[[a,0,f'atom_{j}'],[b,0,f'atom_{j}']] for j in range(1,4)],'observations':[]} for i,(a,b) in enumerate([('A','B'),('B','C')])],
        'routes':{'two_steps':['s0','s1']},'reactants':{'A':1},'products':{'C':1},
        'budget':{'max_jobs':10,'max_candidates':5},'unexplored':['Other mechanisms']}


def test_tst_independent_eyring_formula_and_actual_flux():
    s=tst_input();s['concentrations_mol_l']={'A':.02};r=tst(s)
    expected=(1.380649e-23*298.15/6.62607015e-34)*math.exp(-.02*2625499.6394799/(8.31446261815324*298.15))
    assert r['rate_constant']==pytest.approx(expected,rel=1e-10)
    assert r['initial_flux_mol_l_s']==pytest.approx(expected*.02)
    assert r['rate_unit']=='s^-1' and not r['elementary_step_certified']


def test_bimolecular_tst_standard_state_invariance():
    s=tst_input();p=s['profile'];p['species']['TS']=thermo(e=-151.96,dimer=True)
    p['species']['TS']['thermal']['rrho'].update(stationary_type='transition_state',frequencies_cm1=[-500]+[100]*11)
    p['states'][0]['stoichiometry']['A']=2;s['active_reactants']['A']=2
    original=tst(s)
    assert original['rate_unit']=='L mol^-1 s^-1'
    for entry in p['species'].values():entry['conditions']['standard_state']={'kind':'concentration_mol_l','value':1.}
    assert tst(s)['rate_constant']==pytest.approx(original['rate_constant'],rel=1e-10)


@pytest.mark.parametrize('fault',['electronic_barrier','negative_barrier','missing_evidence','different_stoich','minimum_ts','negative_concentration','kappa'])
def test_invalid_tst_scope(fault):
    s=tst_input()
    if fault=='electronic_barrier':s['profile']['quantity']='E'
    if fault=='negative_barrier':s=tst_input(-.01)
    if fault=='missing_evidence':s['evidence']=[]
    if fault=='different_stoich':s['active_reactants']['A']=2
    if fault=='minimum_ts':s['profile']['species']['TS']['thermal']['rrho'].update(stationary_type='minimum',frequencies_cm1=[100,1500,3500])
    if fault=='negative_concentration':s['concentrations_mol_l']={'A':-1.}
    if fault=='kappa':s['transmission_coefficient']=2.
    with pytest.raises(ValueError):tst(s)


def test_branching_shared_precursor_ratio_is_not_thermodynamic_product_order():
    s=branch_input()
    for name,channel in s['channels'].items():
        p=channel['profile'];p['species']['product']=thermo(e=-76.1 if name=='fast' else -76.2)
        p['states'].append({'id':'P','stoichiometry':{'product':1}})
    r=branching(s);fractions={row['id']:row['initial_branch_fraction'] for row in r['channels']}
    assert fractions['fast']/fractions['slow']==pytest.approx(math.exp(.001*HARTREE_J_MOL/(R*298.15)))
    assert fractions['fast']>fractions['slow'] # The slow product is thermodynamically lower.
    s['channels']['slow']['profile']['species']['A']=thermo(e=-76.001)
    with pytest.raises(ValueError,match='identical precursors'):branching(s)


def test_branching_rejects_reversibility_and_duplicate_channels():
    s=branch_input();s['assumptions']['irreversible_products']=False
    with pytest.raises(ValueError):branching(s)
    s=branch_input();s['channels']['slow']=copy.deepcopy(s['channels']['fast'])
    with pytest.raises(ValueError,match='duplicate'):branching(s)


@pytest.mark.parametrize('reverse',[False,True])
def test_network_matches_closed_form_and_conserves_total(reverse):
    r=network(network_input(reverse));assert r['status']=='completed'
    for row in r['rows']:
        t=row['time_s'];c=row['concentrations_mol_l']
        expected=1/3+2/3*math.exp(-3*t) if reverse else math.exp(-2*t)
        assert c['A']==pytest.approx(expected,rel=2e-7,abs=1e-10)
        assert c['A']+c['B']==pytest.approx(1.,abs=1e-12)
        assert min(c.values())>=0
    assert r['solver']['max_scaled_local_error']<=1.
    assert r['solver']['max_invariant_drift_mol_l']<1e-12


def test_bimolecular_depletion_and_catalyst_preservation():
    s=network_input();s['species']['B']=molecule(dimer=True);s['species']['cat']=molecule(.3)
    s['initial_mol_l'].update(B=0.,cat=.25)
    s['reactions']=[{'id':'association','reactants':{'A':2,'cat':1},'products':{'B':1,'cat':1},'forward':rate(4.,3)}]
    for row in network(s)['rows']:
        t=row['time_s'];c=row['concentrations_mol_l']
        assert c['A']==pytest.approx(1/(1+2*t),rel=2e-7)
        assert c['A']+2*c['B']==pytest.approx(1.,abs=1e-12)
        assert c['cat']==.25


def test_network_sequential_intermediate_is_not_omitted():
    s=network_input();s['species']['C']=molecule(.2);s['initial_mol_l']['C']=0.
    s['reactions'].append({'id':'r2','reactants':{'B':1},'products':{'C':1},'forward':rate(1.)})
    for row in network(s)['rows']:
        t=row['time_s'];c=row['concentrations_mol_l']
        assert c['B']==pytest.approx(2*(math.exp(-t)-math.exp(-2*t)),rel=2e-7,abs=1e-10)
        assert sum(c.values())==pytest.approx(1.,abs=1e-12)


@pytest.mark.parametrize('fault',['mass','unit','negative','unknown_initial','time','duplicate','spin'])
def test_network_bad_data_rejected(fault):
    s=network_input()
    if fault=='mass':s['reactions'][0]['products']['B']=2
    if fault=='unit':s['reactions'][0]['forward']['unit']='s'
    if fault=='negative':s['initial_mol_l']['A']=-1.
    if fault=='unknown_initial':s['initial_mol_l']['X']=0.
    if fault=='time':s['times_s']=[0,1,.5]
    if fault=='duplicate':s['reactions'].append(copy.deepcopy(s['reactions'][0]))
    if fault=='spin':s['species']['A']['multiplicity']=2
    with pytest.raises(ValueError):network(s)


def test_network_budget_returns_partial_without_clipping():
    s=network_input();s['solver']['max_steps']=1
    r=network(s);assert r['status']=='step_limit' and len(r['rows'])<len(s['times_s'])
    assert min(r['last_state']['concentrations_mol_l'].values())>=0


def test_tst_rate_inputs_bind_network_species():
    s=network_input();s['reactions'][0]['forward']=tst_input()
    assert network(s)['status']=='completed'
    s['species']['A']=molecule(.5)
    with pytest.raises(ValueError,match='binding'):network(s)


def test_two_step_pathway_retains_intermediate_and_missing_evidence():
    s=pathway_input();r=pathway(s)
    assert r['status']=='incomplete' and len(r['steps'])==2
    assert r['routes'][0]['gaps']==[] and all(step['mapping']=='pass' for step in r['steps'])
    assert r['species_origins']['B']['hypothesis_id']=='h'
    s['routes']['two_steps']=['s0','missing','s1']
    r=pathway(s)
    assert any(g['reason']=='missing_step' for g in r['routes'][0]['gaps'])


def test_r_only_retains_budget_and_does_not_claim_completion():
    s=pathway_input();s['products']=None
    r=pathway(s)
    assert r['status']=='incomplete' and r['budget']==s['budget'] and r['unexplored']
    assert r['routes'][0]['gaps'][-1]['reason']=='product_target_unspecified'


def test_conflicting_observations_and_disconnected_steps_are_retained():
    s=pathway_input();s['steps'][1]['reactants']={'A':1};s['steps'][1]['mapping']=None
    s['steps'][0]['observations']=[{'source_sha256':'sha256:'+'c'*64,'interpretation':'conflicts','note':'Unexpected IRC exit'}]
    r=pathway(s)
    assert r['steps'][0]['status']=='conflicted'
    assert any(g['reason']=='shared_intermediate_or_spectator_mismatch' for g in r['routes'][0]['gaps'])


@pytest.mark.parametrize('operation,factory', [('tst',tst_input),('branching',branch_input),('kinetic-network',network_input),('pathway-check',pathway_input)])
def test_kinetics_and_pathway_jobs(tmp_path,operation,factory):
    from research_agent.application.api import execute
    from research_agent.application.executors import prepare
    from tests.unit.test_job_recovery import workspace
    root=tmp_path/'work';workspace(root);path=root/'input.json';path.write_text(json.dumps(factory()))
    request=prepare(Path(os.environ['CORAGENT_JOB_CONFIG']),'local','chemical.'+operation,'1',{'input':path})
    node=execute('research.create',root,{'goal':'Independent kinetic/pathway fixture'})['node']
    receipt=execute('job.start',root,{**request,'node_id':node['id']})
    try:
        for _ in range(600):
            status=execute('job.status',root,{'job_id':receipt['job_id']})
            if status['state'] in ('succeeded','failed'):break
            time.sleep(.01)
        assert status['state']=='succeeded'
        assert execute('job.collect',root,{'job_id':receipt['job_id']})['output_validation']['complete']
    finally:execute('job.cancel',root,{'job_id':receipt['job_id']})


def test_pathway_recomputes_bound_mode_and_irc_evidence():
    from tests.unit.test_general_evidence_checks import study,coordinates
    saddle,evidence,paths,targets=study()
    s=pathway_input();s['species']={key:{'material':target['value'],'origin':{'kind':'provided','source_sha256':'sha256:'+'a'*64}} for key,target in zip('AB',targets)}
    s['steps']=s['steps'][:1];s['steps'][0]['validation']={'saddle_material':saddle['value'],'saddle_evidence':evidence,'mode_coordinates':coordinates(),'paths':paths}
    s['routes']={'one_step':['s0']};s['products']={'B':1}
    result=pathway(s)
    assert result['status']=='supported_within_scope' and result['steps'][0]['validation']['status']=='pass'
    s['steps'][0]['validation']['paths'][0]['complete']=False
    assert pathway(s)['status']=='incomplete'


@pytest.mark.parametrize('fault',['concentration_conflict','zero_precursor','duplicate_relabel'])
def test_branching_concentration_and_activated_complex_identity(fault):
    s=branch_input()
    for channel in s['channels'].values():channel['concentrations_mol_l']={'A':.1}
    if fault=='concentration_conflict':s['channels']['slow']['concentrations_mol_l']['A']=.2
    if fault=='zero_precursor':
        for channel in s['channels'].values():channel['concentrations_mol_l']['A']=0.
    if fault=='duplicate_relabel':
        s['channels']['slow']=copy.deepcopy(s['channels']['fast']);s['channels']['slow']['evidence'][0]['note']='Relabeled duplicate'
    with pytest.raises(ValueError):branching(s)
