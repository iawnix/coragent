"""Deterministic thermodynamic identities and staged energy-analysis Jobs."""
import copy
import json
import math
import os
from pathlib import Path
import sys
import time

import pytest
pytest.importorskip('numpy')

SKILLS = Path(__file__).resolve().parents[2] / 'domains/chemical/skills'
from tests.unit.chemical_paths import configure
configure()
import energy
from energy_analysis import ensemble, profile, scan_slice
from energy_common import HARTREE_J_MOL, R, UNITS, canonical, standard_correction
from thermochemistry import oscillator_entropy, thermochemistry
from material import build_material


def molecule(stretch=0., dimer=False):
    xyz = [[0,0,0], [0,0,1+stretch], [1,0,0]]
    if dimer: xyz += [[x+5,y,z] for x,y,z in xyz]
    atoms = ['O','H','H'] * (2 if dimer else 1)
    spec = {'schema_version':'chemical-material-input/1','format':'xyz',
        'text':str(len(atoms))+'\nsynthetic geometry\n'+''.join(a+' '+' '.join(map(str,p))+'\n' for a,p in zip(atoms,xyz)),
        'graph':{'smiles':'O.O' if dimer else 'O','source':'user','note':'synthetic numerical fixture'},
        'graph_to_input':[0,3,1,2,4,5] if dimer else [0,1,2], 'charge':0, 'multiplicity':1, 'electronic_state':{'kind':'ground'}}
    return build_material(spec, 'sha256:'+'a'*64)[0]


def thermo(e=-76., stretch=0., dimer=False, thermal=True):
    m = molecule(stretch, dimer); mod = {'method':'HF','basis':'STO-3G','solvent':None}
    spec = {'schema_version':'chemical-thermochemistry-input/1',
        'electronic':{'material':m,'energy_hartree':e,'model':mod,'source_sha256':'sha256:'+'b'*64},
        'conditions':{'temperature_k':298.15,'phase':'gas','standard_state':{'kind':'pressure_pa','value':101325.}}}
    if thermal:
        spec['thermal'] = {'material':copy.deepcopy(m),'model':copy.deepcopy(mod),'source_sha256':'sha256:'+'b'*64,
            'format':'corrections','data':{'E_hartree':e,'ZPE_hartree':.02,'H_correction_hartree':.025,'G_correction_hartree':.01},
            'temperature_k':298.15,'standard_state':{'kind':'pressure_pa','value':101325.},
            'rrho':{'frequencies_cm1':[100,1500,3500] if not dimer else [100]*12,
                    'stationary_type':'minimum','geometry_class':'nonlinear','symmetry_number':2,'frequency_scale':1.}}
    return spec


def ensemble_input():
    return {'schema_version':'chemical-free-energy-ensemble-input/1','coverage':'Two synthetic supplied basins; not exhaustive',
        'degeneracy_convention':'additional_unrepresented_basins', 'members':[
            {'id':'a','thermochemistry':thermo(),'degeneracy':1,'degeneracy_evidence':'One explicit basin'},
            {'id':'b','thermochemistry':thermo(stretch=.4),'degeneracy':2,'degeneracy_evidence':'Two assumed unsampled equivalent basins for numerical test'}]}


def profile_input(thermal=True):
    return {'schema_version':'chemical-energy-profile-input/1','quantity':'G' if thermal else 'E','unit':'kJ/mol',
        'species':{'water':thermo(thermal=thermal),'complex':thermo(e=-152.1,dimer=True,thermal=thermal)},
        'states':[{'id':'R','stoichiometry':{'water':2}},{'id':'P','stoichiometry':{'complex':1}}],
        'reference':'R','comparisons':[{'from':'R','to':'P','kind':'reaction'}]}


def scan_input():
    points = [{'index':0,'targets':[1.],'actual':[1.],'deviations':[0.],'status':'succeeded','energy_hartree':-2.,
               'evidence':{'kind':'synthetic'},'primary_sha256':{'input':'sha256:'+'a'*64}},
              {'index':1,'targets':[2.],'status':'failed','energy_hartree':-100.}]
    for p in points: p['record_sha256']=canonical(p)
    return {'schema_version':'chemical-scan-slice-input/1','unit':'kJ/mol',
        'scan':{'schema_version':'chemical-scan-result/1','status':'failed','settings':{'method':'synthetic'},
                'axes':[{'kind':'distance','unit':'angstrom','tolerance':.01}],'points':points}}


def test_units_and_standard_states_against_independent_reference():
    # 1 atm gas -> 1 M: 1.89432845 kcal/mol at 298.15 K.
    delta=standard_correction({'kind':'pressure_pa','value':101325.}, {'kind':'concentration_mol_l','value':1.},298.15)
    assert delta*UNITS['kcal/mol'] == pytest.approx(1.894328445,abs=2e-8)
    assert UNITS['kcal/mol'] == pytest.approx(627.50947406,abs=1e-6)
    assert standard_correction({'kind':'concentration_mol_l','value':1.}, {'kind':'pressure_pa','value':101325.},298.15) == pytest.approx(-delta)
    assert standard_correction({'kind':'pressure_pa','value':100000.}, {'kind':'pressure_pa','value':100000.},400.) == 0.


def test_quantities_include_zpe_only_once_and_preserve_real_zero():
    spec=thermo();result=thermochemistry(spec)
    assert result['quantities']=={'E':-76.,'ZPE':.02,'E+ZPE':-75.98,'H':-75.975,'G':-75.99}
    spec['thermal']['data']['G_correction_hartree']=0.
    assert thermochemistry(spec)['quantities']['G']==-76.
    del spec['thermal']['data']['G_correction_hartree']
    assert thermochemistry(spec)['quantities']['G'] is None
    assert 'G' in thermochemistry(spec)['missing_quantities']
    assert thermochemistry(thermo(thermal=False))['quantities']['G'] is None


def test_composite_high_level_plus_low_level_correction():
    spec=thermo();spec['electronic']['energy_hartree']=-77.
    spec['electronic']['model']['method']='MP2';spec['electronic']['source_sha256']='sha256:'+'c'*64
    with pytest.raises(ValueError,match='composite'): thermochemistry(spec)
    spec['composite']=True
    r=thermochemistry(spec)
    assert r['quantities']['G']==pytest.approx(-76.99)
    assert r['quantities']['E+ZPE']==pytest.approx(-76.98)


@pytest.mark.parametrize('fault',['geometry','state','missing_geometry','same_source','temperature','zpe_twice','solvation_twice','unknown_state','boolean_energy','nan','unknown_field'])
def test_invalid_sources_and_double_counting_rejected(fault):
    s=thermo()
    if fault=='geometry':s['thermal']['material']=molecule(.5)
    if fault=='state':s['thermal']['material']['multiplicity']=3
    if fault=='missing_geometry':s['thermal']['material']['geometry']=None
    if fault=='same_source':s['electronic']['energy_hartree']=-77.
    if fault=='temperature':s['conditions']['temperature_k']=350.
    if fault=='zpe_twice':s['thermal']['data']['extra_zpe_hartree']=.02
    if fault=='solvation_twice':s['solvation_correction_hartree']=.01
    if fault=='unknown_state':s['electronic']['material']['electronic_state']={'kind':'unspecified'}
    if fault=='boolean_energy':s['electronic']['energy_hartree']=True
    if fault=='nan':s['thermal']['data']['G_correction_hartree']=float('nan')
    if fault=='unknown_field':s['eletronic']={}
    with pytest.raises(ValueError):thermochemistry(s)


def test_solution_standard_state_only_changes_g():
    s=thermo();original=thermochemistry(s)['quantities']
    gas=copy.deepcopy(s);gas['conditions']['standard_state']={'kind':'concentration_mol_l','value':1.}
    gas_result=thermochemistry(gas)
    assert gas_result['conditions']['phase']=='gas' and gas_result['model_signature']['electronic']['solvent'] is None
    assert (gas_result['quantities']['G']-original['G'])*UNITS['kcal/mol']==pytest.approx(1.894328445,abs=2e-8)
    s['electronic']['model']['solvent']={'name':'water','model':'SMD'}
    s['electronic']['source_sha256']='sha256:'+'c'*64;s['composite']=True
    s['conditions'].update(phase='solution',standard_state={'kind':'concentration_mol_l','value':1.})
    r=thermochemistry(s)
    for q in ('E','ZPE','E+ZPE','H'): assert r['quantities'][q]==original[q]
    assert (r['quantities']['G']-original['G'])*UNITS['kcal/mol']==pytest.approx(1.894328445,abs=2e-8)


def test_entropy_floor_and_ts_unstable_mode_exclusion():
    # Independent direct harmonic oscillator expression at 50 and 100 cm^-1.
    s=thermo();s['thermal']['rrho']['frequencies_cm1']=[-500.,50.,3500.]
    s['thermal']['rrho']['stationary_type']='transition_state'
    base=thermochemistry(s)['quantities']['G'];s['low_frequency_cutoff_cm1']=100.
    r=thermochemistry(s)
    def direct(v):
        x=1.4387768775039338*v/298.15
        return 8.31446261815324*(x/(math.exp(x)-1)-math.log(1-math.exp(-x)))
    delta=298.15*(direct(50)-direct(100))/2625499.6394799
    assert r['quantities']['G']-base==pytest.approx(delta,abs=1e-14)
    assert r['compatibility']['excluded_unstable_frequencies_cm1']==[-500.]
    assert r['quantities']['H']==-75.975
    assert oscillator_entropy(1e6,1.)==0.


@pytest.mark.parametrize('frequencies,kind', [([-100,10,20],'minimum'),([-100,-10,20],'transition_state'),([10,20,30],'transition_state'),([0,10,20],'minimum'),([10,20],'minimum')])
def test_rrho_mode_count_and_unstable_modes(frequencies,kind):
    s=thermo();s['thermal']['rrho'].update(frequencies_cm1=frequencies,stationary_type=kind)
    with pytest.raises(ValueError):thermochemistry(s)


@pytest.mark.parametrize('fmt',['gaussian','cf22d'])
def test_existing_thermal_adapters_and_inconsistent_totals(fmt):
    s=thermo();s['thermal']['format']=fmt
    if fmt=='gaussian':
        data={'energy_evidence':{'status':'supported'},'electronic_energy_hartree':-76.,'zero_point_correction_hartree':.02,
              'thermal_enthalpy_correction_hartree':.025,'thermal_gibbs_correction_hartree':.01,
              'electronic_plus_thermal_free_energy_hartree':-75.99,'temperature_k':298.15,'pressure_atm':1.}
        total='electronic_plus_thermal_free_energy_hartree'
    else:
        data={'schema_version':'pyscf-thermo/1','electronic_energy_hartree':-76.,'zpe_hartree':.02,
              'enthalpy_correction_hartree':.025,'gibbs_correction_hartree':.01,'gibbs_hartree':-75.99,
              'temperature_K':298.15,'pressure_Pa':101325.,'entropy':123.} # ambiguous legacy entropy is never consumed
        total='gibbs_hartree'
    s['thermal']['data']=data
    assert thermochemistry(s)['quantities']['G']==pytest.approx(-75.99)
    data[total]= -75.9
    with pytest.raises(ValueError,match='inconsistency'):thermochemistry(s)
    if fmt=='gaussian':
        data['energy_evidence']['status']='unsupported'
        with pytest.raises(ValueError,match='not supported'):thermochemistry(s)


def test_ensemble_partition_degeneracy_and_extreme_energy_stability():
    s=ensemble_input();r=ensemble(s);base=thermochemistry(thermo())['quantities']['G']
    assert r['quantities']['G']==pytest.approx(base-R*298.15/HARTREE_J_MOL*math.log(3))
    assert [m['population'] for m in r['members']]==pytest.approx([1/3,2/3])
    assert r['quantities']['H'] is None
    s['members'][1]['thermochemistry']=thermo(e=10000.,stretch=.4)
    r=ensemble(s)
    assert r['members'][1]['population']==0. and math.isfinite(r['quantities']['G'])


@pytest.mark.parametrize('fault',['duplicate_geometry','duplicate_id','zero_degeneracy','bool_degeneracy','method','conditions','missing_g','ts','coverage'])
def test_ensemble_rejects_double_counting_and_incompatible_members(fault):
    s=ensemble_input();m=s['members'][1]
    if fault=='duplicate_geometry':m['thermochemistry']=thermo()
    if fault=='duplicate_id':m['id']='a'
    if fault=='zero_degeneracy':m['degeneracy']=0
    if fault=='bool_degeneracy':m['degeneracy']=True
    if fault=='method':
        m['thermochemistry']['electronic']['model']['basis']='other';m['thermochemistry']['thermal']['model']['basis']='other'
    if fault=='conditions':m['thermochemistry']['conditions']['standard_state']['value']=100000.
    if fault=='missing_g':del m['thermochemistry']['thermal']['data']['G_correction_hartree']
    if fault=='ts':m['thermochemistry']['thermal']['rrho'].update(stationary_type='transition_state',frequencies_cm1=[-100,1500,3500])
    if fault=='coverage':s.pop('coverage')
    with pytest.raises(ValueError):ensemble(s)


def test_balanced_stoichiometry_common_reference_and_standard_state_delta_n():
    s=profile_input();r=profile(s)
    assert r['rows'][0]['relative_energy']==0.
    assert r['rows'][1]['relative_energy']==pytest.approx(-.11*2625.4996394799)
    old=r['comparisons'][0]['energy']
    for v in s['species'].values():
        v['conditions']['standard_state']['value']=202650.
    new=profile(s)['comparisons'][0]['energy']
    assert new-old==pytest.approx(-R*298.15*math.log(2)/1000.)


@pytest.mark.parametrize('fault',['imbalance','charge','isotope','unused','unknown_species','missing_g','mixed_model','zero_coefficient'])
def test_profile_rejects_bad_comparison_basis(fault):
    s=profile_input()
    if fault=='imbalance':s['states'][0]['stoichiometry']['water']=1
    if fault=='charge':
        s['species']['complex']['electronic']['material']['charge']=1
    if fault=='isotope':s['species']['complex']['electronic']['material']['atoms'][0]['isotope']=18
    if fault=='unused':s['species']['extra']=thermo()
    if fault=='unknown_species':s['states'][0]['stoichiometry']={'absent':2}
    if fault=='missing_g':del s['species']['water']['thermal']['data']['G_correction_hartree']
    if fault=='mixed_model':
        s['species']['water']['electronic']['model']['basis']='other';s['species']['water']['thermal']['model']['basis']='other'
    if fault=='zero_coefficient':s['states'][0]['stoichiometry']['water']=0
    with pytest.raises(ValueError):profile(s)


def test_electronic_profile_is_not_a_free_energy_profile():
    s=profile_input(thermal=False)
    assert profile(s)['quantity']=='E'
    s['quantity']='G'
    with pytest.raises(ValueError,match='missing quantity'):profile(s)


def test_scan_failed_energy_never_becomes_reference_or_plotted_row():
    s=scan_input();r=scan_slice(s)
    assert r['reference_hartree']==-2. and len(r['rows'])==1 and r['rows'][0]['relative_energy']==0.
    assert r['excluded']==[{'index':1,'status':'failed'}]
    s['scan']['points'][0]['energy_hartree']=-3.
    with pytest.raises(ValueError,match='digest'):scan_slice(s)


@pytest.mark.parametrize('operation,spec_factory',[
    ('thermochemistry',thermo),('ensemble-free-energy',ensemble_input),('energy-profile',profile_input),('scan-slice',scan_input)])
def test_energy_executors_through_jobs(tmp_path,operation,spec_factory):
    from research_agent.application.api import execute
    from research_agent.application.executors import prepare
    from tests.unit.test_job_recovery import workspace
    root=tmp_path/'work';workspace(root)
    source=root/'energy.json';source.write_text(json.dumps(spec_factory()))
    config=Path(os.environ['CORAGENT_JOB_CONFIG'])
    prepared=prepare(config,'local','chemical.'+operation,'1',{'input':source})
    node=execute('research.create',root,{'goal':'Independent energy analysis fixture'})['node']
    receipt=execute('job.start',root,{**prepared,'node_id':node['id']})
    try:
        for _ in range(600):
            status=execute('job.status',root,{'job_id':receipt['job_id']})
            if status['state'] in ('succeeded','failed'):break
            time.sleep(.01)
        assert status['state']=='succeeded'
        assert execute('job.collect',root,{'job_id':receipt['job_id']})['output_validation']['complete']
        output=Path(receipt['cwd'])/'results'
        result=json.loads((output/'result.json').read_text())
        assert result['input_file_sha256'].startswith('sha256:')
        assert (output/'table.csv').read_text().strip()
    finally:execute('job.cancel',root,{'job_id':receipt['job_id']})


@pytest.mark.parametrize('atoms,geometry,freqs', [('He 0 0 0','atom',[]), ('H 0 0 0\nH 0 0 0.74','linear',[4000.])])
def test_atomic_and_linear_rrho_mode_counts(atoms,geometry,freqs):
    m=build_material({'schema_version':'chemical-material-input/1','format':'xyz',
        'text':str(len(atoms.splitlines()))+'\nfixture\n'+atoms+'\n','charge':0,'multiplicity':1,
        'electronic_state':{'kind':'ground'}},'sha256:'+'f'*64)[0]
    s=thermo();s['electronic']['material']=m;s['thermal']['material']=copy.deepcopy(m)
    s['thermal']['rrho'].update(geometry_class=geometry,frequencies_cm1=freqs,symmetry_number=1)
    assert thermochemistry(s)['quantities']['G']==-75.99
    s['thermal']['rrho']['geometry_class']='nonlinear'
    with pytest.raises(ValueError,match='geometry_class'):thermochemistry(s)


def test_geometry_correspondence_reorders_and_rotates_thermal_source():
    from analysis_material import make_order
    s=thermo();m=s['thermal']['material']
    ids=m['atom_order']['input_atom_ids'];m['atom_order']=make_order(ids,[2,0,1])
    m['atoms']=[m['atoms'][i] for i in [2,0,1]]
    for atom in m['atoms']:
        x,y,z=atom['coordinates'];atom['coordinates']=[-y+4,x+2,z-3]
    result=thermochemistry(s)
    assert result['compatibility']['method']=='graph_mapping_proper_rotation'
    assert result['compatibility']['rmsd_angstrom']<1e-12


def test_graphless_ts_exact_binding_and_minimum_barrier_comparison():
    minimum=thermo();ts=thermo(e=-75.95)
    ts['thermal']['rrho'].update(stationary_type='transition_state',frequencies_cm1=[-100,1500,3500])
    for source in ('electronic','thermal'):ts[source]['material']['graph']=None
    assert thermochemistry(ts)['compatibility']['method']=='exact_ordered_geometry'
    p={'schema_version':'chemical-energy-profile-input/1','species':{'a':minimum,'ts':ts},
       'states':[{'id':'R','stoichiometry':{'a':1}},{'id':'TS','stoichiometry':{'ts':1}}],
       'reference':'R','quantity':'G','unit':'kcal/mol',
       'comparisons':[{'from':'R','to':'TS','kind':'activation'}]}
    r=profile(p)
    assert r['comparisons'][0]['energy']==pytest.approx(.05*627.50947406)
    assert not r['comparisons'][0]['validated_elementary_step']
    ts['thermal']['material']['atoms'][0]['coordinates'][0]+=.1
    with pytest.raises(ValueError,match='graphless'):thermochemistry(ts)


def test_ensemble_result_inputs_are_composable_in_profile():
    s=ensemble_input()
    p={'schema_version':'chemical-energy-profile-input/1','species':{'all':s,'one':thermo()},
       'states':[{'id':'one','stoichiometry':{'one':1}},{'id':'all','stoichiometry':{'all':1}}],
       'reference':'one','quantity':'G','unit':'kJ/mol'}
    assert profile(p)['rows'][1]['relative_energy']==pytest.approx(-R*298.15*math.log(3)/1000.)


def test_existing_output_and_sources_are_never_overwritten(tmp_path):
    from energy_cli import parse_arguments
    source=tmp_path/'input.json';source.write_text(json.dumps(thermo()))
    args=parse_arguments(['--output-dir',str(tmp_path/'out'),'thermochemistry','--input',str(source)])
    energy.run(args);saved=(args.output_dir/'result.json').read_bytes()
    with pytest.raises(FileExistsError):energy.run(args)
    assert (args.output_dir/'result.json').read_bytes()==saved
    assert json.loads(source.read_text())==thermo()
