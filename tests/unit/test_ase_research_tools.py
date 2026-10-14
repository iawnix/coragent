"""Real ASE and offline figures; native solvers use deterministic fixtures."""
import copy
import json
import os
import hashlib
from pathlib import Path
import subprocess
import sys
import time
import tomllib

import numpy as np
import pytest
from ase import Atoms
from ase.io import read
from ase.units import Hartree
from PIL import Image

from tests.unit.test_path_search import Analytic, endpoints, fake_xtb, molecule, potential, settings
from tests.unit.test_electronic_crossing import config as gaussian_settings, fake_gaussian, h2
from tests.unit.test_energetics import profile_input

SKILLS = Path(__file__).resolve().parents[2] / 'domains/chemical/skills'
sys.path.insert(0, str(SKILLS/'report/scripts'))
from ase_neb import EvidenceCalculator, neb
from ensemble_material import canonical, checked, xyz_text
from local_diagnostics import local_diagnostics
from material import build_material
from path_contract import material
from research_report import build_report
from trajectory import normalize, write_trajectory


def neb_spec():
    return {'schema_version':'chemical-neb-input/2', **endpoints(), 'settings':settings(),
            'image_count':3, 'images':[[[0,0,0],[1,0,0]],[[0,0,0],[1.8,.3,0]],[[0,0,0],[3,0,0]]],
            'climb_after':0, 'max_steps':200, 'fmax_ev_per_angstrom':.001}


@pytest.mark.parametrize('identifier', ['chemical.neb-xtb','chemical.neb-gaussian'])
def test_retired_neb_requests_cannot_fall_back_to_ase(identifier):
    from research_agent.application.executors import registered_executor
    with pytest.raises(ValueError, match='not_registered'):
        registered_executor(identifier, '1')
    base, entry=registered_executor(identifier, '2')
    assert entry['entry'].endswith('/ase_search.py')
    assert entry['cli'].endswith('/ase_cli.py')
    assert not (base/'skills/candidate-generation/scripts/neb_engine.py').exists()


@pytest.mark.parametrize('optimizer', ['FIRE','BFGS'])
def test_ase_optimizers_find_saddle_and_write_bound_paths(tmp_path,optimizer):
    spec=neb_spec();spec['optimizer']=optimizer
    r=neb(spec,tmp_path/'neb',Analytic)
    assert r['status']=='converged'
    assert np.allclose(r['images'][1],[[0,0,0],[2,0,0]],atol=2e-5)
    assert r['images'][0]==spec['images'][0] and r['images'][-1]==spec['images'][-1]
    assert r['max_neb_force_ev_per_angstrom']<=spec['fmax_ev_per_angstrom']
    assert r['engine']['name']=='ASE' and not r['candidate']['validated_ts']
    frames=read(tmp_path/'neb/iterations/0000/path.traj',index=':')
    assert len(frames)==3
    assert frames[1].get_potential_energy()/Hartree==pytest.approx(potential(frames[1].positions)[0])
    assert all(i['climbing_image']==1 for i in r['iterations'])


def test_ase_bridge_units_sign_and_cache(tmp_path):
    m=material(molecule(1.4));backend=Analytic(m,{})
    ledger={'attempted':0,'limit':3,'evaluations':[]}
    calc=EvidenceCalculator(backend,m,tmp_path,ledger,0)
    atoms=Atoms('HH',positions=m['coordinates']);atoms.calc=calc
    force=atoms.get_forces();energy=atoms.get_potential_energy()
    delta=np.zeros((2,3));delta[1,0]=1e-6
    numerical=(potential(atoms.positions+delta)[0]-potential(atoms.positions-delta)[0])/2e-6
    assert force[1,0]==pytest.approx(-numerical*Hartree,abs=1e-7)
    assert energy==pytest.approx(potential(atoms.positions)[0]*Hartree)
    assert backend.calls==1
    atoms.positions[1,0]+=.01;atoms.get_forces()
    assert backend.calls==2 and ledger['attempted']==2


@pytest.mark.parametrize('budget', [2,3,4])
def test_ase_budget_keeps_only_complete_geometry_energy_pair(tmp_path,budget):
    s=neb_spec();s['max_evaluations']=budget
    r=neb(s,tmp_path/'neb',Analytic)
    assert r['status']=='failed' and r['evaluation_count']==budget
    ledger=json.loads((tmp_path/'neb/evaluations.json').read_text())
    assert len(ledger['evaluations'])==budget
    if budget<3:
        assert r['images'] is None and r['candidate'] is None
    else:
        assert r['candidate'] is not None
        for xyz,e in zip(r['images'],r['energies_hartree']):assert potential(np.array(xyz))[0]==pytest.approx(e)
        assert r['pending_images']!=r['images']


def test_ase_native_failure_preserves_attempt_receipt(tmp_path):
    class Fails(Analytic):
        def evaluate(self,xyz,directory):
            if self.calls>=3:raise ValueError('deterministic backend failure')
            return super().evaluate(xyz,directory)
    r=neb(neb_spec(),tmp_path/'neb',Fails)
    assert r['status']=='failed' and r['images']==neb_spec()['images']
    ledger=json.loads((tmp_path/'neb/evaluations.json').read_text())
    assert ledger['evaluations'][-1]['status']=='failed'
    assert json.loads((tmp_path/'neb/result.json').read_text())==r


def test_idpp_and_early_climb_use_ase_without_native_idpp_evaluations(tmp_path):
    s=neb_spec();s.pop('images');s.update(interpolation='idpp',climb_after=20,max_steps=0)
    r=neb(s,tmp_path/'neb',Analytic)
    assert r['status']=='converged' and r['evaluation_count']==3
    assert r['iterations'][0]['climbing_image']==1
    assert r['settings']['interpolation']=='idpp'


def test_early_climbing_stays_active_until_converged(tmp_path):
    s=neb_spec();s.update(climb_after=200,fmax_ev_per_angstrom=.05)
    s['images'][1][1]=[1.8,0,0]
    r=neb(s,tmp_path/'neb',Analytic)
    assert r['status']=='converged' and len(r['iterations'])>1
    assert len(r['iterations'])<200
    assert all(row['climbing_image']==1 for row in r['iterations'])
    assert r['images'][1][1][0]==pytest.approx(2,abs=.001)


def test_ase_force_failure_cannot_pair_old_geometry_with_new_energy(tmp_path,monkeypatch):
    from ase.mep import NEB
    original=NEB.get_forces;calls=[]
    def fail_on_new_geometry(band):
        xyz=np.array([a.positions for a in band.images])
        if calls and not np.array_equal(xyz,calls[0]):raise ValueError('synthetic force assembly failure')
        calls.append(xyz.copy())
        return original(band)
    monkeypatch.setattr(NEB,'get_forces',fail_on_new_geometry)
    r=neb(neb_spec(),tmp_path/'neb',Analytic)
    assert r['status']=='failed' and r['images']!=calls[0].tolist()
    assert r['max_neb_force_ev_per_angstrom'] is None
    for xyz,e in zip(r['images'],r['energies_hartree']):assert potential(np.array(xyz))[0]==pytest.approx(e)


@pytest.mark.parametrize('fault', ['version','units','duplicate','collision','reinterpolate','spin','steps'])
def test_ase_rejects_incompatible_input(tmp_path,fault):
    s=neb_spec()
    if fault=='version':s['schema_version']='chemical-neb-input/1'
    if fault=='units':s['fmax']=.1
    if fault=='duplicate':s['images'][1]=s['images'][0]
    if fault=='collision':s['images'][1][1]=[0,0,0]
    if fault=='reinterpolate':s['interpolation']='idpp'
    if fault=='spin':s['product']['multiplicity']=3
    if fault=='steps':s['max_steps']=True
    with pytest.raises(ValueError):neb(s,tmp_path/'bad',Analytic)
    assert not (tmp_path/'bad').exists()


def local_spec(xyz=None):
    points=xyz if xyz is not None else [[0.,0,0],[1.,0,0],[0.,1,0],[0.,0,1]]
    m=build_material({'schema_version':'chemical-material-input/1','format':'xyz',
        'text':xyz_text([{'element':'C'}]*4,points),'charge':0,'multiplicity':1,
        'electronic_state':{'kind':'ground'}},'sha256:'+'a'*64)[0]
    return {'schema_version':'chemical-local-diagnostics-input/1','material':m,
        'reaction_center':['atom_1','atom_2','atom_3'],'spectators':['atom_4'],
        'coordinates':[{'id':'distance','atoms':['atom_1','atom_2'],'minimum':.9,'maximum':1.1}],
        'allowed_contacts':[['atom_1','atom_2']]}


def test_local_rotation_translation_fit_and_spectator_displacement():
    s=local_spec();original=checked(s['material'])['coordinates']
    rotation=np.array([[0.,-1,0],[1,0,0],[0,0,1.]])
    transformed=original@rotation+[3,-2,4]
    s['reference']=copy.deepcopy(s['material']);s['material']=local_spec(transformed)['material']
    s['mapping']=[[i,i] for i in checked(s['material'])['ids']]
    r=local_diagnostics(s);comparison=r['comparison']
    assert comparison['heavy_atom_fit']['rmsd_angstrom']<1e-12
    assert comparison['spectator_rmsd_after_center_fit_angstrom']<1e-12
    transformed[3,2]+=.7;s['material']=local_spec(transformed)['material']
    r=local_diagnostics(s)
    assert r['comparison']['spectator_rmsd_after_center_fit_angstrom']==pytest.approx(.7)
    assert r['coordinates'][0]['status']=='within_declared_bounds'
    flags={tuple(c['atoms']):c['declared_allowed'] for c in r['short_contacts']}
    assert flags[('atom_1','atom_2')] and not flags[('atom_1','atom_3')]
    assert r['scientific_verdict']=='not_assessed'


def test_local_fit_never_reflects_or_certifies_collinear_spectators():
    s=local_spec();s['reference']=copy.deepcopy(s['material']);s['mapping']=[[f'atom_{i}',f'atom_{i}'] for i in range(1,5)]
    xyz=checked(s['material'])['coordinates'];xyz[:,2]*=-1;s['material']=local_spec(xyz)['material']
    fit=local_diagnostics(s)['comparison']['heavy_atom_fit']
    assert fit['rmsd_angstrom']>.1 and fit['rotation_determinant']==pytest.approx(1.)
    s['reaction_center']=['atom_1','atom_2']
    r=local_diagnostics(s)
    assert r['comparison']['spectator_rmsd_after_center_fit_angstrom'] is None


def test_local_wrapped_dihedral_and_degenerate_angle():
    s=local_spec([[1,0,0],[0,0,0],[0,1,0],[-1,1,.001]])
    s['coordinates']=[{'id':'torsion','atoms':[f'atom_{i}' for i in range(1,5)],'minimum':170,'maximum':-170}]
    r=local_diagnostics(s);assert r['coordinates'][0]['status']=='within_declared_bounds'
    s=local_spec([[0,0,0],[0,0,0],[0,1,0],[1,1,0]])
    s['coordinates']=[{'id':'angle','atoms':['atom_1','atom_2','atom_3'],'minimum':80,'maximum':100}]
    row=local_diagnostics(s)['coordinates'][0]
    assert row['value'] is None and row['status']=='not_assessed'


@pytest.mark.parametrize('fault',['mapping','isotope','overlap','unknown_atom','spectator_type'])
def test_local_rejects_ambiguous_identity_and_groups(fault):
    s=local_spec();s['reference']=copy.deepcopy(s['material']);s['mapping']=[[f'atom_{i}',f'atom_{i}'] for i in range(1,5)]
    if fault=='mapping':s['mapping'][-1]=s['mapping'][0]
    if fault=='isotope':s['reference']['atoms'][0]['isotope']=13
    if fault=='overlap':s['spectators']=['atom_1']
    if fault=='unknown_atom':s['reaction_center']=['unknown']
    if fault=='spectator_type':s['spectators']=False
    with pytest.raises(ValueError):local_diagnostics(s)


def trajectory_spec():
    return {'schema_version':'chemical-trajectory-input/1','material':molecule(),
        'kind':'optimization','source_sha256':'sha256:'+'b'*64,'model':{'method':'synthetic'},
        'frames':[{'coordinates':[[0,0,0],[x,0,0]],'energy_hartree':e} for x,e in [(1.,-1.),(1.2,None),(1.4,-.9)]],
        'coordinates':[{'id':'H-H','atoms':['atom_1','atom_2']}],
        'display_bonds':[['atom_1','atom_2']],'animation_frames':3}


def test_trajectory_files_preserve_missing_energy_and_frame_order(tmp_path):
    r=write_trajectory(trajectory_spec(),tmp_path/'trajectory')
    assert r['frames'][1]['energy_hartree'] is None
    assert r['animation_frame_indices']==[0,1,2]
    assert r['frames'][2]['internal_coordinates'][0]['value']==pytest.approx(1.4)
    with Image.open(tmp_path/'trajectory/trajectory.gif') as gif:assert gif.n_frames==3
    assert all((tmp_path/'trajectory'/f).is_file() for f in r['files'])
    assert len(read(tmp_path/'trajectory/trajectory.xyz',index=':'))==3
    assert '1,,1.2' in (tmp_path/'trajectory/profile.csv').read_text()


def test_mode_is_normalized_cartesian_illustration_without_energy(tmp_path):
    s=trajectory_spec();s.pop('frames');s.pop('model');s.update(kind='mode',amplitude_angstrom=.2,
        mode={'vectors':[[0,0,0],[4,0,0]],'representation':'cartesian_displacement','frequency_cm1':-500.})
    _,r=normalize(s);xyz=np.array([f['coordinates'] for f in r['frames']])
    assert np.max(np.abs(xyz[:,1,0]-1))==pytest.approx(.2)
    assert all(f['energy_hartree'] is None for f in r['frames'])
    assert r['source_status']=='mode_illustration_not_dynamics_or_irc'
    assert r['mode']['frequency_cm1']==-500. and r['mode']['amplitude_angstrom']==.2
    r=write_trajectory(s,tmp_path/'mode');assert (tmp_path/'mode/profile.png').is_file()


def test_partial_neb_trajectory_keeps_source_status(tmp_path):
    s=neb_spec();s['max_steps']=0;r=neb(s,tmp_path/'neb',Analytic)
    trajectory={'schema_version':'chemical-trajectory-input/1','material':s['reactant'],'neb_result':r,'kind':'neb'}
    _,value=normalize(trajectory)
    assert value['source_status']=='step_limit' and value['source_sha256']==canonical(r)
    trajectory['source_sha256']='sha256:'+'a'*64
    with pytest.raises(ValueError,match='digest'):normalize(trajectory)
    trajectory.pop('source_sha256');r['schema_version']='chemical-neb-result/1'
    with pytest.raises(ValueError,match='terminal NEB result'):normalize(trajectory)


@pytest.mark.parametrize('fault',['source','energy_model','nan','order','amplitude','two_sources'])
def test_trajectory_invalid_sources_are_rejected(fault):
    s=trajectory_spec()
    if fault=='source':s.pop('source_sha256')
    if fault=='energy_model':s.pop('model')
    if fault=='nan':s['frames'][0]['energy_hartree']=float('nan')
    if fault=='order':s['frames'][0]['coordinates'].append([0,0,0])
    if fault=='amplitude':s['amplitude_angstrom']=.1
    if fault=='two_sources':s['mode']={}
    with pytest.raises(ValueError):normalize(s)


def report_spec():
    result=local_diagnostics(local_spec())
    review={'schema_version':'research-review/1','review_id':'review_'+'a'*64,
        'state_digest':'sha256:'+'b'*64,'review_digest':None,'status':'attention',
        'review_status':'current','source_refs':['node_1','result_1'],
        'findings':[{'ref':'node_1','kind':'node','summary':'Geometry remains preliminary'}],
        'contradictions':[{'ref':'job_1','kind':'job_failure','summary':'Execution failed'}],
        'uncertainties':[{'ref':'node_1','kind':'node','summary':'No validated assessment'}],
        'limitations':[],'follow_up':[{'action':'inspect_job','ref':'job_1'}],
        'trigger':'context_refresh'}
    review['review_digest']=canonical({key:value for key,value in review.items() if key!='review_digest'})
    return {'schema_version':'chemical-research-report-input/1','title':'Synthetic path report',
        'question':'Does the candidate have evidence of a TS?',
        'assessment':'Insufficient evidence; geometry alone is not validation.',
        'limitations':['Synthetic data; no native chemistry benchmark.'],
        'evidence':[{'id':'geometry','label':'Local geometry','result':result,'source_sha256':canonical(result)}],
        'structures':[{'label':'Supplied geometry','material':molecule()}], 'research_review':review}


def test_report_recomputes_energy_and_preserves_evidence_and_links(tmp_path):
    s=report_spec();s['energy_profile']=profile_input();s['trajectory']=trajectory_spec()
    r=build_report(s,tmp_path/'report')
    assert r['scientific_validation']=='not_assessed' and r['author_assessment']==s['assessment']
    assert r['evidence'][0]['result']==s['evidence'][0]['result']
    assert r['energy']['rows'][0]['relative_energy']==0
    assert r['energy']['rows'][1]['relative_energy']<0
    assert all((tmp_path/'report'/f).is_file() for f in r['files'])
    text=(tmp_path/'report/report.md').read_text()
    assert '![Discrete energy levels](energy.png)' in text
    assert '![Trajectory illustration](trajectory/trajectory.gif)' in text
    assert s['limitations'][0] in text
    assert r['research_review']==s['research_review']
    assert '## Research Review' in text and 'Execution failed' in text


@pytest.mark.parametrize('fault',['digest','review_digest','incompatible_energy'])
def test_report_rejects_unbound_evidence_or_incomparable_energy(tmp_path,fault):
    s=report_spec()
    if fault=='digest':s['evidence'][0]['result']['scientific_verdict']='invented'
    elif fault=='review_digest':s['research_review']['review_digest']='sha256:'+'c'*64
    else:
        s['energy_profile']=profile_input();s['energy_profile']['species']['complex']['electronic']['model']['basis']='other'
    with pytest.raises(ValueError):build_report(s,tmp_path/'report')
    assert not (tmp_path/'report').exists()


@pytest.mark.parametrize('operation',['neb-xtb','neb-gaussian','local-diagnostics','trajectory','research-report'])
def test_registered_tools_through_real_jobs(tmp_path,monkeypatch,operation):
    from research_agent.application.api import execute
    from research_agent.application.executors import prepare
    from tests.unit.test_job_recovery import workspace
    root=tmp_path/'work';workspace(root)
    config=Path(os.environ['CORAGENT_JOB_CONFIG']);text=config.read_text()
    binding=tomllib.loads(text)['environments']['local']['backends']['structure']['python']
    if operation.startswith('neb-'):
        backend='path_'+operation.split('-')[1]
        native=fake_xtb(tmp_path/'xtb') if backend=='path_xtb' else fake_gaussian(tmp_path/'g16')
        text+='\n[environments.local.backends.'+backend+']\ncommand='+json.dumps(str(native))+'\n'
        text+='[environments.local.backends.'+backend+'.python]\n'+''.join(k+'='+json.dumps(v)+'\n' for k,v in binding.items())
        spec={'schema_version':'chemical-neb-input/2','reactant':h2(.8,center=True),'product':h2(1.2,center=True),
            'mapping':[['atom_1','atom_1'],['atom_2','atom_2']],
            'settings':settings() if backend=='path_xtb' else gaussian_settings(), 'image_count':3,'max_steps':0}
    elif operation=='local-diagnostics':spec=local_spec()
    elif operation=='trajectory':spec=trajectory_spec()
    else:spec=report_spec()
    config=tmp_path/'job.toml';config.write_text(text);monkeypatch.setenv('CORAGENT_JOB_CONFIG',str(config))
    source=root/'input.json';source.write_text(json.dumps(spec))
    prepared=prepare(config,'local','chemical.'+operation,'2' if operation.startswith('neb-') else '1',{'input':source})
    node=execute('research.create',root,{'goal':'ASE and analysis operation fixture'})['node']
    receipt=execute('job.start',root,{**prepared,'node_id':node['id']})
    try:
        for _ in range(1500):
            status=execute('job.status',root,{'job_id':receipt['job_id']})
            if status['state'] in ('succeeded','failed'):break
            time.sleep(.01)
        assert status['state']=='succeeded'
        assert execute('job.collect',root,{'job_id':receipt['job_id']})['output_validation']['complete']
        result=json.loads((Path(receipt['cwd'])/'results/result.json').read_text())
        if operation.startswith('neb-'):assert result['status']=='converged' and result['engine']['name']=='ASE'
    finally:execute('job.cancel',root,{'job_id':receipt['job_id']})


def test_prepared_path_lock_is_dependency_complete_and_runs_real_ase(tmp_path):
    lock=SKILLS.parent/'environments/path.lock'
    identity=hashlib.sha256(lock.read_bytes()).hexdigest()[:20]
    prefix=Path(os.environ['CORAGENT_TEST_ENV_ROOT'])/'deps/scientific/path'/identity
    assert (prefix/'.prepared.json').is_file(), 'Prepare the public path profile before tests'
    python=prefix/'bin/python'
    result=subprocess.run([str(python),'-I','-B','-c',
        'import ase,scipy,numpy,rdkit,matplotlib; from PIL import Image; '
        'from ase import Atoms; from ase.calculators.emt import EMT; from ase.optimize import FIRE; '
        'assert ase.__version__=="3.29.0"; '
        'a=Atoms("H2",positions=[[0,0,0],[0,0,1]]); a.calc=EMT(); '
        'assert FIRE(a,logfile=None).run(fmax=0.05,steps=200)'],cwd=tmp_path,capture_output=True)
    assert result.returncode==0
    result=subprocess.run([str(python),'-I','-B','-m','pip','check'],cwd=tmp_path,capture_output=True)
    assert result.returncode==0
