"""Synthetic Gaussian records, transition tensors and analytic crossing seams."""
import copy
import json
import os
from pathlib import Path
import re
import sys
import time
import tomllib

import pytest
np = pytest.importorskip('numpy')
from tests.unit.test_energetics import molecule
from tests.unit.test_path_search import molecule as h2

SKILLS=Path(__file__).resolve().parents[2]/'skills/chemical'
sys.path.insert(0,str(SKILLS/'gaussian/scripts'))
import electronic
from electronic_contract import BOHR_ANGSTROM,electronic_material,settings,route
from electronic_parse import parse_electronic
from state_tracking import track_states
sys.path.insert(0,str(SKILLS/'surface-crossing/scripts'))
from crossing_check import check_crossing,projected,seam_basis
from mecp_engine import mecp


def config(theory='ground'):
    return settings({'theory':theory,'functional':'HF','basis':'STO-3G','threads':1,'memory_mb':256,'timeout_seconds':3.,
        **({'root':1,'nstates':2} if theory!='ground' else {})})


def excited_material(theory='td'):
    m=molecule();m['electronic_state']={'kind':'excited','method':'TDHF' if theory=='td' else 'TDA','root':1}
    return electronic_material(m)


def log_text(m,s,task='sp',coords=None):
    xyz=m['coordinates'] if coords is None else coords
    from xyz import PERIODIC_TABLE
    out=route(m,s,task)+'\n ----\n Gaussian 16, Revision A.03,\n'
    out+=f' Charge = {m["value"]["charge"]} Multiplicity = {m["value"]["multiplicity"]}\n'
    out+=' Input orientation:\n ----\n Center Atomic Type X Y Z\n ----\n'
    for i,(a,row) in enumerate(zip(m['atoms'],xyz)):
        out+=f' {i+1} {PERIODIC_TABLE.index(a["element"])} 0 '+ ' '.join(map(str,row))+'\n'
    out+=' ----\n SCF Done: E('+('R' if m['value']['multiplicity']==1 else 'U')+s['functional']+') = -76.000000000 A.U. after 8 cycles\n'
    if s['theory']!='ground':
        out+=' Excited State 1: Singlet-A 2.7211 eV 455.60 nm f=0.0010 <S**2>=0.000\n 1 -> 2 0.707\n'
        out+=' This state for optimization and/or second-order correction.\n'
        out+=' Total Energy, E('+('TD-HF/TD-DFT' if s['theory']=='td' else 'CIS/TDA')+') = -75.900000000\n'
        out+=' Excited State 2: Singlet-B 5.4423 eV 227.80 nm f=0.0020 <S**2>=0.000\n 1 -> 3 0.707\n'
    elif m['value']['multiplicity']!=1:
        spin=(m['value']['multiplicity']-1)/2;out+=f' S**2 before annihilation {spin*(spin+1):.4f}, after {spin*(spin+1):.4f}\n'
    out+=' Center Atomic Forces (Hartrees/Bohr)\n Number Number X Y Z\n ----\n'
    for i,a in enumerate(m['atoms']):out+=f' {i+1} {PERIODIC_TABLE.index(a["element"])} 0.0001 0.0 0.0\n'
    out+=' ----\n'
    if task=='opt':
        out+=' Maximum Force 0.0001 0.00045 YES\n RMS     Force 0.0001 0.0003 YES\n Maximum Displacement 0.0001 0.0018 YES\n RMS     Displacement 0.0001 0.0012 YES\n Stationary point found\n'
    return out+' Normal termination of Gaussian 16\n'


@pytest.mark.parametrize('theory',['ground','td','tda'])
def test_target_energy_and_gradient_never_use_reference_as_excited_energy(theory):
    m=electronic_material(molecule()) if theory=='ground' else excited_material(theory);s=config(theory)
    r=parse_electronic(log_text(m,s),m,s,'sp')
    assert r['final']['energy_hartree']==(-76. if theory=='ground' else -75.9)
    assert r['final']['reference_scf_energy_hartree']==-76.
    assert r['final']['gradient_hartree_per_angstrom'][0][0]==pytest.approx(-.0001/.529177210903)
    assert r['state_continuity']['status']=='not_assessed'


@pytest.mark.parametrize('fault',['root','total','energy','gradient','termination','spin','geometry','stale_scf','wrong_model','unsupported_total'])
def test_excited_parser_refuses_incomplete_or_mixed_evidence(fault):
    m=excited_material();s=config('td');text=log_text(m,s)
    if fault=='root':text=text.replace('Excited State 1:','Excited State 3:')
    if fault=='total':text='\n'.join(l for l in text.splitlines() if 'Total Energy' not in l)
    if fault=='energy':text=text.replace('-75.900000000','-75.800000000')
    if fault=='gradient':text=text.replace('Forces (Hartrees/Bohr)','Forces (eV/Angstrom)')
    if fault=='termination':text=text.replace('Normal termination','Error termination')
    if fault=='spin':text=text.replace('<S**2>=0.000','<S**2>=1.000')
    if fault=='geometry':text=log_text(m,s,coords=m['coordinates']+1.)
    if fault=='stale_scf':text=text.replace(' Normal termination',' SCF Done: E(RHF) = -76.1 A.U. after 4 cycles\n Normal termination')
    if fault=='wrong_model':text=text.replace('E(RHF)','E(RB3LYP)')
    if fault=='unsupported_total':text=text.replace('E(TD-HF/TD-DFT)','E(CCSD)')
    with pytest.raises(ValueError):parse_electronic(text,m,s,'sp')


def test_optimization_checks_numeric_convergence_and_repeated_state_evidence():
    m=excited_material('tda');s=config('tda');text=log_text(m,s,'opt')
    assert parse_electronic(text,m,s,'opt')['optimization_convergence']
    text=text.replace('Maximum Force 0.0001','Maximum Force 0.001')
    with pytest.raises(ValueError,match='numeric'):parse_electronic(text,m,s,'opt')


@pytest.mark.parametrize('theory', ['ground', 'td', 'tda'])
def test_electronic_optimization_uses_gaussian_negligible_force_completion(theory):
    m = electronic_material(molecule()) if theory == 'ground' else excited_material(theory)
    s = config(theory)
    text = log_text(m, s, 'opt').replace('0.0001 0.0018 YES', '0.002 0.0018 NO').replace(
        ' Stationary point found', ' Optimization completed on the basis of negligible forces.\n Stationary point found')
    result = parse_electronic(text, m, s, 'opt')
    assert result['optimization_completion_reason'] == 'gaussian_negligible_forces'
    assert result['optimization_convergence']['Maximum Displacement']['converged'] == 'NO'


def tracking_input(flip=False):
    first=[{'root':1,'energy_hartree':-75.,'multiplicity':1,'transition_density':[[1,0],[0,0]]},
           {'root':2,'energy_hartree':-74.,'multiplicity':1,'transition_density':[[0,0],[0,1]]}]
    second=copy.deepcopy(first)
    if flip:second[0]['transition_density'],second[1]['transition_density']=second[1]['transition_density'],second[0]['transition_density']
    frames=[{'material':molecule(.1*i),'source_sha256':'sha256:'+c*64,'basis_definition_sha256':'sha256:'+'c'*64,
        'ao_overlap':[[1,0],[0,1]],'states':states} for i,(c,states) in enumerate([('a',first),('b',second)])]
    return {'schema_version':'chemical-state-tracking-input/1','frames':frames,'initial_root':1,
        'links':[{'from_source_sha256':frames[0]['source_sha256'],'to_source_sha256':frames[1]['source_sha256'],
                  'source_sha256':'sha256:'+'d'*64,'ao_cross_overlap':[[1,0],[0,1]]}]}


def test_transition_density_tracking_detects_root_flip_not_just_root_labels():
    assert track_states(tracking_input())['status']=='consistent_character'
    r=track_states(tracking_input(True));assert r['status']=='root_changed' and r['final_root']==2
    s=tracking_input();s['frames'][1]['states'][0]['transition_density']=[[-1,0],[0,0]]
    assert track_states(s)['status']=='consistent_character' # arbitrary global phase


@pytest.mark.parametrize('fault',['degenerate','ambiguous','bad_metric','missing_density','binding'])
def test_state_tracking_ambiguity_and_invalid_metrics(fault):
    s=tracking_input()
    if fault=='degenerate':
        s['frames'][1]['states'][1]['energy_hartree']=-75.000001
        assert track_states(s)['status']=='inconclusive';return
    if fault=='ambiguous':
        s['frames'][1]['states'][1]['transition_density']=[[1,0],[0,0]]
        assert track_states(s)['status']=='inconclusive';return
    if fault=='bad_metric':s['links'][0]['ao_cross_overlap']=[[2,0],[0,2]]
    if fault=='missing_density':s['frames'][1]['states'][0]['transition_density']=None
    if fault=='binding':s['links'][0]['from_source_sha256']='sha256:'+'e'*64
    with pytest.raises(ValueError):track_states(s)


def evidence(m,xyz,energy,gradient,hessian=None):
    spin=(m['value']['multiplicity']-1)/2;s=config()
    result={'schema_version':'chemical-electronic-evaluation/1','atom_ids':m['ids'],'elements':[a['element'] for a in m['atoms']],
        'charge':m['value']['charge'],'multiplicity':m['value']['multiplicity'],'electronic_state':m['value']['electronic_state'],
        'coordinate_unit':'angstrom','gradient_unit':'hartree/angstrom','gradient_quantity':'dE/dR','source_sha256':'sha256:'+'e'*64,
        'model':{k:v for k,v in s.items() if k not in ('threads','memory_mb','timeout_seconds','max_cycles')},
        'final':{'coordinates':np.asarray(xyz).tolist(),'energy_hartree':float(energy),'gradient_hartree_per_angstrom':np.asarray(gradient).tolist(),'spin_squared':spin*(spin+1)}}
    if hessian is not None:
        result['final']['hessian_hartree_per_angstrom2']=np.asarray(hessian).tolist();result['hessian_provenance']={'kind':'analytic_fixture'}
    return result


def crossing_input(curvature=True):
    a=electronic_material(molecule());b=copy.deepcopy(a['value']);b['multiplicity']=3;b=electronic_material(b)
    xyz=a['coordinates'];normal=np.zeros(xyz.shape);normal[0,0]=-1.;normal[2,0]=1.
    values=[evidence(m,xyz,0.,gradient,np.eye(xyz.size) if curvature else None) for m,gradient in [(a,normal),(b,-normal)]]
    return {'schema_version':'chemical-crossing-check-input/1','materials':[a['value'],b['value']],'surfaces':values}


def test_crossing_checks_gap_stationarity_and_seam_curvature_separately():
    s=crossing_input();r=check_crossing(s)
    assert r['numerical_mecp_conditions'] and r['curvature']['seam_internal_dimensions']==2
    s['surfaces'][0]['final']['energy_hartree']=.01
    assert not check_crossing(s)['numerically_stationary']
    s=crossing_input(False)
    assert check_crossing(s)['numerically_stationary'] and not check_crossing(s)['numerical_mecp_conditions']
    s=crossing_input();xyz=np.asarray(s['surfaces'][0]['final']['coordinates']);g=np.asarray(s['surfaces'][0]['final']['gradient_hartree_per_angstrom']).reshape(-1)
    tangent=seam_basis(xyz,2*g)[:,0];h=np.eye(xyz.size)-2*np.outer(tangent,tangent)
    for v in s['surfaces']:v['final']['hessian_hartree_per_angstrom2']=h.tolist()
    assert check_crossing(s)['curvature']['status']=='fail'


@pytest.mark.parametrize('fault',['state','units','spin','geometry','gradient','model'])
def test_crossing_evidence_binding(fault):
    s=crossing_input()
    if fault=='state':s['materials'][1]['multiplicity']=1
    if fault=='units':s['surfaces'][0]['gradient_unit']='hartree/bohr'
    if fault=='spin':s['surfaces'][1]['final']['spin_squared']=4.
    if fault=='geometry':s['surfaces'][0]['final']['coordinates'][0][0]=.1
    if fault=='gradient':s['surfaces'][0]['final']['gradient_hartree_per_angstrom']=s['surfaces'][1]['final']['gradient_hartree_per_angstrom']
    if fault=='model':s['surfaces'][0]['model']['functional']='B3LYP'
    with pytest.raises(ValueError):check_crossing(s)


class Parabola:
    def __init__(self,m,s):self.m=m
    def evaluate(self,xyz,directory):
        delta=xyz[1]-xyz[0];distance=np.linalg.norm(delta);center=1. if self.m['value']['multiplicity']==1 else 3.
        e=(distance-center)**2;g=2*(distance-center)*delta/distance
        return evidence(self.m,xyz,e,np.array([-g,g]))


def mecp_input():
    return {'schema_version':'chemical-mecp-input/1','material':h2(1.4),'multiplicities':[1,3],
        'settings':config(),'max_steps':30,'max_evaluations':200,'hessian_step_angstrom':.001}


def test_mecp_finds_analytic_seam_with_independent_curvature(tmp_path):
    r=mecp(mecp_input(),tmp_path/'mecp',Parabola)
    assert r['status']=='converged' and r['check']['numerical_mecp_conditions']
    xyz=np.array(r['iterations'][-1]['coordinates'])
    assert np.linalg.norm(xyz[1]-xyz[0])==pytest.approx(2.,abs=1e-6)
    assert r['check']['energy_gap_hartree']==pytest.approx(0.,abs=1e-7)
    assert not r['validated_global_mecp']


def test_mecp_budget_and_failed_second_surface_preserve_last_candidate(tmp_path):
    s=mecp_input();s['max_evaluations']=3
    r=mecp(s,tmp_path/'mecp',Parabola)
    assert r['status']=='failed' and r['evaluations']==3 and len(r['iterations'])==1
    assert r['candidate_evaluations'] and (tmp_path/'mecp/result.json').is_file()


def fake_gaussian(path):
    path.write_text('''#!/usr/bin/env python3
import sys,re,math
text=sys.stdin.read();lines=text.splitlines();route=next(l for l in lines if l.startswith('#'))
header=next(i for i,l in enumerate(lines) if re.fullmatch(r'-?\\d+ \\d+',l));charge,mult=map(int,lines[header].split())
atoms=[]
for line in lines[header+1:]:
 if not line.strip():break
 p=line.split();atoms.append((p[0],[float(v) for v in p[1:]]))
td='TD=' in route or 'TDA=' in route;method=re.search(r'#p (\\S+?)/',route)[1]
energy=-76.;grads=[[0.,0.,0.] for a in atoms]
if not td and len(atoms)==2:
 delta=[atoms[1][1][i]-atoms[0][1][i] for i in range(3)];r=math.sqrt(sum(v*v for v in delta));c=1. if mult==1 else 3.
 energy=(r-c)**2;g=[2*(r-c)*v/r for v in delta];grads=[[-v for v in g],g]
print(route);print(' ----');print(' Gaussian 16, Revision A.03,');print(' Charge =',charge,'Multiplicity =',mult)
print(' Input orientation:\\n ----\\n Center Atomic Type X Y Z\\n ----')
z={'H':1,'O':8}
for i,(a,row) in enumerate(atoms):print(i+1,z[a],0,*row)
print(' ----');print(' SCF Done: E('+method+') = '+str(energy)+' A.U. after 8 cycles')
if td:
 print(' Excited State 1: Singlet-A 2.7211 eV 455.60 nm f=0.0010 <S**2>=0.000')
 print(' 1 -> 2 0.707');print(' This state for optimization and/or second-order correction.')
 print(' Total Energy, E('+('CIS/TDA' if 'TDA=' in route else 'TD-HF/TD-DFT')+') = -75.900000000')
 print(' Excited State 2: Singlet-B 5.4423 eV 227.80 nm f=0.0020 <S**2>=0.000')
elif mult!=1:
 s=(mult-1)/2;print(' S**2 before annihilation',s*(s+1),', after',s*(s+1))
print(' Center Atomic Forces (Hartrees/Bohr)\\n Number Number X Y Z\\n ----')
for i,((a,row),grad) in enumerate(zip(atoms,grads)):print(i+1,z[a],*[-v*.529177210903 for v in grad])
print(' ----')
if 'Opt=' in route:
 print(' Maximum Force 0.0 0.00045 YES\\n RMS     Force 0.0 0.0003 YES\\n Maximum Displacement 0.0 0.0018 YES\\n RMS     Displacement 0.0 0.0012 YES\\n Stationary point found')
print(' Normal termination of Gaussian 16')
''');path.chmod(0o700);return path


@pytest.mark.parametrize('operation',['electronic-gaussian','state-tracking','mecp-gaussian','crossing-check','gradient-gaussian','neb-gaussian'])
def test_electronic_and_crossing_jobs(tmp_path,monkeypatch,operation):
    from research_agent.application.api import execute
    from research_agent.application.executors import prepare
    from tests.unit.test_job_recovery import workspace
    root=tmp_path/'work';workspace(root)
    config_path=Path(os.environ['CORAGENT_JOB_CONFIG']);text=config_path.read_text();binding=tomllib.loads(text)['execution']['targets']['local']['bindings']['structure']['python']
    text+='\n[execution.targets.local.bindings.path_gaussian]\ncommand='+json.dumps(str(fake_gaussian(tmp_path/'g16')))+'\n[execution.targets.local.bindings.path_gaussian.python]\n'+''.join(k+'='+json.dumps(v)+'\n' for k,v in binding.items())
    config_path=tmp_path/'electronic-job.toml';config_path.write_text(text);monkeypatch.setenv('CORAGENT_JOB_CONFIG',str(config_path))
    if operation=='electronic-gaussian':s={'schema_version':'chemical-electronic-input/1','material':excited_material()['value'],'settings':config('td'),'task':'opt'}
    elif operation=='state-tracking':s=tracking_input(True)
    elif operation=='crossing-check':s=crossing_input()
    elif operation=='gradient-gaussian':s={'schema_version':'chemical-gradient-input/1','material':h2(1.4),'settings':config()}
    elif operation=='neb-gaussian':s={'schema_version':'chemical-neb-input/2','reactant':h2(.8,center=True),'product':h2(1.2,center=True),
        'mapping':[['atom_1','atom_1'],['atom_2','atom_2']],'settings':config(),'image_count':3,'max_steps':0}
    else:s=mecp_input();s['material']=h2(2.);s['hessian_step_angstrom']=None
    submission = None
    if operation == 'electronic-gaussian':
        # A JSON calculation can specify resources once on the Job. The pinned
        # source stays unchanged; the runner resolves omitted settings at runtime.
        s['settings'].pop('threads'); s['settings'].pop('memory_mb')
        submission = {'resources': {'cpus': 12, 'memory_mb': 16384}}
    path=root/'input.json';path.write_text(json.dumps(s));request=prepare(config_path,'local','chemical.'+operation,'2' if operation=='neb-gaussian' else '1',{'input':path}, submission=submission)
    node=execute('research_create',root,{'goal':'Bound electronic/crossing fixture'})['node'];receipt=execute('job_start',root,{**request,'node_id':node['id']})
    try:
        for _ in range(600):
            status=execute('job_status',root,{'job_id':receipt['job_id']})
            if status['state'] in ('succeeded','failed'):break
            time.sleep(.01)
        assert status['state']=='succeeded'
        assert execute('job_collect',root,{'job_id':receipt['job_id']})['output_validation']['complete']
        if operation == 'electronic-gaussian':
            result = json.loads((Path(receipt['cwd']) / 'results/result.json').read_text())
            assert result['settings']['threads'] == 12
            assert result['settings']['memory_mb'] == 14745
            assert json.loads(path.read_text()) == s
    finally:execute('job_cancel',root,{'job_id':receipt['job_id']})


def test_density_overlap_is_invariant_under_ao_basis_rotation():
    s=tracking_input();theta=.7;q=np.array([[np.cos(theta),-np.sin(theta)],[np.sin(theta),np.cos(theta)]])
    s['frames'][1]['basis_definition_sha256']='sha256:'+'f'*64
    for state in s['frames'][1]['states']:
        state['transition_density']=(q.T@np.asarray(state['transition_density'])@q).tolist()
    s['links'][0]['ao_cross_overlap']=q.tolist()
    assert track_states(s)['status']=='consistent_character'


def test_zero_energy_gap_with_tangential_force_is_not_stationary():
    s=crossing_input();xyz=np.asarray(s['surfaces'][0]['final']['coordinates']);g=np.asarray(s['surfaces'][0]['final']['gradient_hartree_per_angstrom'])
    tangent=seam_basis(xyz,2*g.reshape(-1))[:,0].reshape(xyz.shape)
    for record in s['surfaces']:
        record['final']['gradient_hartree_per_angstrom']=(np.asarray(record['final']['gradient_hartree_per_angstrom'])+tangent).tolist()
    assert not check_crossing(s)['numerically_stationary']


def test_gaussian_calculator_gradient_sign_and_units_against_finite_difference(tmp_path):
    from gaussian_path import GaussianPathCalculator
    from path_contract import material as path_material
    from gradient_contract import evaluate_evidence
    m=path_material(h2(1.4));calculator=GaussianPathCalculator(m,config(),str(fake_gaussian(tmp_path/'g16')))
    xyz=m['coordinates'];delta=np.zeros_like(xyz);delta[1,0]=1e-5
    value=calculator.evaluate(xyz,tmp_path/'center');e,force=evaluate_evidence(value,m,xyz,calculator.model)
    plus=calculator.evaluate(xyz+delta,tmp_path/'plus');minus=calculator.evaluate(xyz-delta,tmp_path/'minus')
    derivative=(plus['energy']['value']-minus['energy']['value'])/(2e-5)
    assert force[1,0]==pytest.approx(-derivative,abs=1e-9)
    assert e==pytest.approx(.16)


def test_electronic_timeout_preserves_failure_and_removes_gaussian_scratch(tmp_path):
    from electronic_cli import parse_arguments
    program=tmp_path/'slow-g16'
    program.write_text('#!/usr/bin/env python3\nimport os,time\nfrom pathlib import Path\nPath(os.environ["GAUSS_SCRDIR"],"scratch-file").write_text("fixture")\ntime.sleep(30)\n')
    program.chmod(0o700);s={'schema_version':'chemical-electronic-input/1','material':excited_material()['value'],'settings':config('td'),'task':'sp'}
    s['settings']['timeout_seconds']=.15
    path=tmp_path/'input.json';path.write_text(json.dumps(s));out=tmp_path/'out'
    args=parse_arguments(['--output-dir',str(out),'run','--input',str(path),'--executable',str(program)])
    result=electronic.run(args)
    assert result['status']=='failed' and result['error']['type']=='TimeoutExpired'
    assert (out/'result.json').is_file() and (out/'calculation/program.out').is_file()
    assert not (out/'calculation/scratch').exists()


def test_crossing_rejects_unidentified_surface_methods():
    s=crossing_input()
    for record in s['surfaces']:record['model'].pop('functional')
    with pytest.raises(ValueError,match='functional'):check_crossing(s)
