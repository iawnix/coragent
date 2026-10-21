"""Synthetic potentials and native fixtures exercise path contracts, not chemistry accuracy."""
import copy
import json
import math
import os
from pathlib import Path
import re
import sys
import time
import tomllib

import pytest

np = pytest.importorskip('numpy')

SKILLS = Path(__file__).resolve().parents[2] / 'domains/chemical/skills'
from tests.unit.chemical_paths import configure
configure()
import search
from ensemble_material import canonical, checked, xyz_text
from gradient_contract import calculation, evaluate_evidence
from input_job import inspect_input
from material import build_material
from ase_neb import neb
from path_contract import BOHR_ANGSTROM, material, qst
from path_xtb import XtbCalculator, gradient_file
from path_gaussian import GaussianOptimizer, constrained_start
from scan_engine import axes_for, scan


def molecule(x=1., n=2, permutation=None, center=False):
    coords = [[0.,0.,0.],[x,0.,0.]] + ([[0.,1.,0.]] if n == 3 else [])
    if center: coords = [[p[0]-x/2,p[1],p[2]] for p in coords]
    spec = {'schema_version':'chemical-material-input/1','format':'xyz',
            'text':xyz_text([{'element':'H'}]*n,coords), 'charge':0,'multiplicity':1 if n==2 else 2,
            'electronic_state':{'kind':'ground'}}
    if permutation: spec['new_to_old']=permutation
    return build_material(spec,'sha256:'+'a'*64)[0]


def settings(backend='xtb'):
    s={'method':'gfn2','threads':1,'timeout_seconds':2.,'solvent':None,'solvent_model':'gas'}
    if backend=='gaussian': s.update(method='HF',basis='STO-3G',memory_mb=256,max_cycles=10)
    return s


def endpoints():
    return {'reactant':molecule(),'product':molecule(3.,permutation=[1,0]),
            'mapping':[['atom_1','atom_1'],['atom_2','atom_2']]}


def qst_input(guess=False):
    s={'schema_version':'chemical-qst-input/1',**endpoints(),'settings':settings('gaussian')}
    if guess: s.update(guess=molecule(2.),guess_mapping=copy.deepcopy(s['mapping']))
    return s


@pytest.mark.parametrize('guess',[False,True])
def test_qst_reorders_endpoints_and_preserves_separate_guess(tmp_path,guess):
    s=qst_input(guess); before=copy.deepcopy(s); text,result,m=qst(s)
    assert s==before and result['kind']==('QST3' if guess else 'QST2')
    inp=tmp_path/'input.gjf';inp.write_text(text)
    assert inspect_input(inp,'HF','STO-3G',0,1,1,256)['routes']
    assert result['correspondence']['product_to_reactant_order']==[1,0]
    assert text.count('\n0 1\n')==(3 if guess else 2)
    assert '3.0 0.0 0.0' in text and ('2.0 0.0 0.0' in text)==guess


@pytest.mark.parametrize('fault',['missing_mapping','duplicate','wrong_element','spin','excited','isotope','missing_guess_mapping'])
def test_qst_rejects_ambiguous_or_incompatible_inputs(fault):
    s=qst_input(fault=='missing_guess_mapping')
    if fault=='missing_mapping': s.pop('mapping')
    if fault=='duplicate': s['mapping'][1]=s['mapping'][0]
    if fault=='wrong_element': s['product']['atoms'][0]['element']='F'
    if fault=='spin': s['product']['multiplicity']=3
    if fault=='excited': s['product']['electronic_state']['kind']='excited'
    if fault=='isotope': s['product']['atoms'][0]['isotope']=2
    if fault=='missing_guess_mapping': s.pop('guess_mapping')
    with pytest.raises(ValueError): qst(s)


def model(m):
    return {'method':'synthetic_double_well','charge':0,'multiplicity':m['value']['multiplicity'],'constraints':[]}


def potential(xyz):
    delta=xyz[1,0]-2.; energy=(delta*delta-1.)**2 + float(np.sum(xyz[0]**2))+xyz[1,1]**2+xyz[1,2]**2
    grad=np.zeros_like(xyz);grad[0]=2*xyz[0];grad[1]=[4*delta*(delta*delta-1),2*xyz[1,1],2*xyz[1,2]]
    return float(energy),grad


class Analytic:
    def __init__(self,m,s): self.material=m;self.model=model(m);self.calls=0
    def evaluate(self,xyz,directory):
        self.calls+=1;energy,grad=potential(xyz)
        return calculation(self.material,xyz,self.model,energy,grad*BOHR_ANGSTROM,{'kind':'synthetic_fixture'})


def test_calculator_units_sign_and_geometry_binding_against_finite_difference():
    m=material(molecule(1.4));xyz=m['coordinates'];xyz[1,1]=.2
    e,g=potential(xyz);evidence=calculation(m,xyz,model(m),e,g*BOHR_ANGSTROM,{'kind':'synthetic'})
    energy,force=evaluate_evidence(evidence,m,xyz,model(m))
    numerical=np.zeros_like(xyz)
    for i in range(2):
        for j in range(3):
            plus=xyz.copy();minus=xyz.copy();plus[i,j]+=1e-5;minus[i,j]-=1e-5
            numerical[i,j]=(potential(plus)[0]-potential(minus)[0])/2e-5
    assert energy==e and np.allclose(force,-numerical,atol=1e-8)
    evidence['gradient']['unit']='hartree/angstrom';evidence['gradient']['values']=g.tolist()
    assert np.allclose(evaluate_evidence(evidence,m,xyz,model(m))[1],force)


@pytest.mark.parametrize('fault',['energy_only','forces','unit','permutation','geometry','model','nan','not_converged'])
def test_bad_calculator_evidence_cannot_drive_neb(fault):
    m=material(molecule());xyz=m['coordinates'];e,g=potential(xyz)
    ev=calculation(m,xyz,model(m),e,g*BOHR_ANGSTROM,{'kind':'synthetic'})
    if fault=='energy_only':ev.pop('gradient')
    if fault=='forces':ev['gradient']['quantity']='force'
    if fault=='unit':ev['gradient']['unit']='eV/angstrom'
    if fault=='permutation':ev['atom_ids'].reverse()
    if fault=='geometry':ev['coordinates'][1][0]+=.2
    if fault=='model':ev['model']={}
    if fault=='nan':ev['gradient']['values'][1][0]=float('nan')
    if fault=='not_converged':ev['converged']=False
    with pytest.raises(ValueError): evaluate_evidence(ev,m,xyz,model(m))


def neb_input():
    spec={'schema_version':'chemical-neb-input/2',**endpoints(),'settings':settings(),'image_count':3,
          'images':[[[0,0,0],[1,0,0]],[[0,0,0],[2,.3,0]],[[0,0,0],[3,0,0]]],
          'max_steps':200,'fmax_ev_per_angstrom':1e-5,'max_step_angstrom':.05,'climb_after':0}
    return spec


def test_climbing_neb_converges_on_independent_analytic_potential(tmp_path):
    spec=neb_input();result=neb(spec,tmp_path/'neb',Analytic)
    assert result['status']=='converged'
    assert result['max_neb_force_ev_per_angstrom']<=1e-5
    assert np.allclose(result['images'][1],[[0,0,0],[2,0,0]],atol=1e-5)
    assert result['images'][0]==spec['images'][0] and result['images'][-1]==spec['images'][-1]
    assert result['candidate']['validated_ts'] is False
    assert result['iterations'][-1]['climbing_image']==1


def test_neb_limit_and_partial_calculator_failure_keep_only_evaluated_candidate(tmp_path):
    s=neb_input();s['max_steps']=0
    result=neb(s,tmp_path/'limited',Analytic)
    assert result['status']=='step_limit' and result['candidate']
    class Fails(Analytic):
        def evaluate(self,xyz,directory):
            if self.calls>=3: raise ValueError('synthetic calculator failure')
            return super().evaluate(xyz,directory)
    s['max_steps']=2
    result=neb(s,tmp_path/'failed',Fails)
    assert result['status']=='failed' and len(result['iterations'])==1
    assert result['images']==s['images'] and result['pending_images']!=s['images']


def test_neb_requires_no_collisions_and_no_duplicate_images(tmp_path):
    s=neb_input();s['images'][1]=s['images'][0]
    with pytest.raises(ValueError,match='duplicate'):neb(s,tmp_path/'bad',Analytic)
    s=neb_input();s['images'][1][1]=[0,0,0]
    with pytest.raises(ValueError,match='coincident'):neb(s,tmp_path/'bad',Analytic)


def scan_input(two=False,backend='xtb'):
    axes=[{'kind':'distance','atoms':['atom_1','atom_2'],'values':[1.,1.5,2.], 'unit':'angstrom','tolerance':.01}]
    if two: axes.append({'kind':'distance','atoms':['atom_1','atom_3'],'values':[1.,2.], 'unit':'angstrom','tolerance':.01})
    return {'schema_version':'chemical-scan-input/1','material':molecule(n=3 if two else 2),'settings':settings(backend),'axes':axes}


class Optimizer:
    def __init__(self,m,s):self.m=m
    def optimize(self,xyz,axes,targets,directory):
        directory.mkdir(parents=True);(directory/'evidence.txt').write_text('synthetic fixture')
        xyz[1,0]=targets[0]
        if len(targets)>1:xyz[2,1]=targets[1]
        return xyz,float(sum(t*t for t in targets)),{'converged':True,'kind':'synthetic_fixture'}


def test_2d_scan_and_terminal_continuation_do_not_repeat_successes(tmp_path):
    s=scan_input(True);first=scan(s,tmp_path/'first','xtb',Optimizer,max_points=2)
    assert first['status']=='partial' and first['executed_points']==2 and len(first['points'])==6
    assert first['points'][1]['targets']==[1.,2.]
    resumed=scan({**s,'previous':first},tmp_path/'resumed','xtb',Optimizer)
    assert resumed['status']=='completed' and resumed['executed_points']==4
    assert all(p['status']=='succeeded' for p in resumed['points'])
    assert resumed['candidate']['point_index']==5
    assert resumed['points'][0]['reused_from_sha256']==canonical(first)


@pytest.mark.parametrize('fault',['running','changed_settings','tampered_record','unknown_point'])
def test_scan_does_not_replay_unknown_or_mismatched_dispatch(tmp_path,fault):
    s=scan_input();first=scan(s,tmp_path/'first','xtb',Optimizer,max_points=1)
    if fault=='running':first['status']='running'
    if fault=='changed_settings':s['settings']['method']='gfn1'
    if fault=='tampered_record':first['points'][0]['energy_hartree']=-100
    if fault=='unknown_point':first['points'][1]['status']='running'
    with pytest.raises(ValueError):scan({**s,'previous':first},tmp_path/'resumed','xtb',Optimizer)


def test_failed_scan_targets_are_retained_and_retry_is_explicit(tmp_path):
    class Wrong(Optimizer):
        def optimize(self,xyz,axes,targets,directory):
            coords,e,ev=super().optimize(xyz,axes,targets,directory)
            coords[1,0]+=.5;return coords,e,ev
    s=scan_input();first=scan(s,tmp_path/'first','xtb',Wrong)
    assert first['status']=='failed' and 'candidate' not in first
    assert first['points'][0]['actual']==[1.5] and first['points'][0]['energy_hartree']==1.
    second=scan({**s,'previous':first},tmp_path/'second','xtb',Optimizer)
    assert second['status']=='failed' and second['executed_points']==0
    third=scan({**s,'previous':first,'retry_failed':True},tmp_path/'third','xtb',Optimizer)
    assert third['status']=='completed'


def fake_xtb(path,mode='normal'):
    path.write_text(f'''#!{sys.executable}
import math, subprocess, sys, time
from pathlib import Path
args=sys.argv
if {mode!r} == 'timeout':
    child=subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)'])
    Path('child.pid').write_text(str(child.pid))
    time.sleep(60)
lines=Path('input.xyz').read_text().splitlines()
coords=[[float(v) for v in line.split()[1:]] for line in lines[2:]]
if '--opt' in args:
    row=next(l for l in Path('constraints.inp').read_text().splitlines() if 'distance:' in l)
    target=float(row.split(',')[-1]);coords[1]=[target,0.,0.]
    Path('xtbopt.xyz').write_text('2\\noptimized fixture\\n'+''.join('H '+' '.join(str(v) for v in p)+'\\n' for p in coords))
r=math.sqrt(sum((b-a)**2 for a,b in zip(coords[0],coords[1])))
e=-1.+.5*(r-1.)**2
print('* xtb version 6.7.1')
print('Hamiltonian GFN2-xTB')
print('convergence criteria satisfied after 4 iterations')
print('| TOTAL ENERGY',e+(99 if '--opt' in args else 0),'Eh')
if '--opt' in args: print('GEOMETRY OPTIMIZATION CONVERGED AFTER 4 ITERATIONS')
print('* finished run on fixture')
if '--grad' in args:
    g=[[(r-1)*(b-a)/r for a,b in zip(coords[0],coords[1])]]
    g=[[-v for v in g[0]],g[0]]
    text='$grad\\n cycle = 1 SCF energy = '+str(e)+' |dE/dxyz| = 0\\n'
    text+=''.join(' '.join(str(v/{BOHR_ANGSTROM}) for v in p)+' h\\n' for p in coords)
    text+=''.join(' '.join(str(v*{BOHR_ANGSTROM}) for v in p)+'\\n' for p in g)+'$end\\n'
    if {mode!r}=='bad_gradient': text=text.replace('$end','')
    Path('gradient').write_text(text)
''');path.chmod(0o755);return path


def fake_gaussian(path):
    path.write_text(f'''#!{sys.executable}
import sys
text=sys.stdin.read();route=next(l for l in text.splitlines() if l.startswith('#'))
atoms=[list(map(float,l.split()[1:])) for l in text.splitlines() if l.startswith('H ')]
target=sum((a-b)**2 for a,b in zip(atoms[0],atoms[1]))**.5
assert next(l for l in text.splitlines() if l.startswith('B ')).split() == ['B','1','2','F']
print(route+'\\n ----------------')
print(' Charge = 0 Multiplicity = 1')
print(' Standard orientation:\\n ----\\n Center Atomic Atomic Coordinates (Angstroms)\\n Number Number Type X Y Z\\n ----')
print(' 1 1 0 0.0 0.0 0.0')
print(' 2 1 0',target,'0.0 0.0\\n ----')
print(' SCF Done: E(RHF) = -1.000000 A.U.')
print(' Maximum Force 0.00001 0.00045 YES\\n RMS     Force 0.00001 0.00030 YES')
print(' Maximum Displacement 0.00001 0.0018 YES\\n RMS     Displacement 0.00001 0.0012 YES')
print(' Stationary point found.\\n Normal termination of Gaussian')
''');path.chmod(0o755);return path


def test_xtb_adapter_geometry_gradient_and_restraint_energy_separation(tmp_path):
    native=fake_xtb(tmp_path/'xtb');m=material(molecule(1.5));calc=XtbCalculator(m,settings(),str(native))
    ev=calc.evaluate(m['coordinates'],tmp_path/'gradient')
    energy,forces=evaluate_evidence(ev,m,m['coordinates'],calc.model)
    assert energy==pytest.approx(-.875) and forces[1,0]==pytest.approx(-.5)
    result=scan(scan_input(),tmp_path/'scan','xtb',lambda m,s:XtbCalculator(m,s,str(native)))
    assert result['status']=='completed'
    assert result['points'][-1]['energy_hartree']==pytest.approx(-.5)
    assert result['points'][-1]['evidence']['optimization']['total_energy_hartree']==pytest.approx(98.5)


@pytest.mark.parametrize('fault',['truncated','wrong_geometry','energy','nonfinite','element'])
def test_native_gradient_rejects_inconsistent_primary_data(tmp_path,fault):
    native=fake_xtb(tmp_path/'xtb');m=material(molecule(1.5));calc=XtbCalculator(m,settings(),str(native))
    ev=calc.evaluate(m['coordinates'],tmp_path/'gradient');text=(tmp_path/'gradient/gradient').read_text()
    xyz=m['coordinates'].copy();energy=ev['energy']['value']
    if fault=='truncated':text=text.replace('$end','')
    if fault=='wrong_geometry':xyz[1,0]+=.1
    if fault=='energy':energy+=.1
    if fault=='nonfinite':text=text.replace('0.0','nan',1)
    if fault=='element':text=text.replace(' h',' f',1)
    with pytest.raises(ValueError):gradient_file(text,m,xyz,energy)


@pytest.mark.parametrize('completion', ['all_criteria', 'negligible_forces'])
def test_gaussian_scan_uses_native_constraints_and_checks_actual_coordinates(tmp_path, completion):
    native=fake_gaussian(tmp_path/'g16')
    if completion == 'negligible_forces':
        native.write_text(native.read_text().replace('0.00001 0.0018 YES', '0.002 0.0018 NO').replace(
            ' Stationary point found.', ' Optimization completed on the basis of negligible forces.\\n Stationary point found.'))
    result=scan(scan_input(backend='gaussian'),tmp_path/'scan','gaussian',lambda m,s:GaussianOptimizer(m,s,str(native)))
    assert result['status']=='completed'
    assert result['points'][-1]['actual'] == pytest.approx([2.], abs=1e-7)
    text = (tmp_path/'scan/points/0002/input.gjf').read_text()
    assert '\nB 1 2 F\n' in text and 'B 1 2 2 F' not in text
    assert result['points'][-1]['evidence']['start_coordinates']


def test_failed_gaussian_scan_preserves_parsed_last_geometry(tmp_path):
    native = fake_gaussian(tmp_path / 'g16')
    native.write_text(native.read_text().replace('Stationary point found.', 'Optimization stopped.').replace(
        'Normal termination of Gaussian', 'Error termination via Lnk1e') + '\nsys.exit(1)\n')
    result = scan(scan_input(backend='gaussian'), tmp_path / 'scan', 'gaussian',
                  lambda m, s: GaussianOptimizer(m, s, str(native)))
    assert result['status'] == 'failed'
    assert 'candidate' not in result
    folder = tmp_path / 'scan/points/0000'
    assert (folder / 'last_geometry.xyz').is_file()
    assert not json.loads((folder / 'parsed.json').read_text())['summary']['optimization_completed']


@pytest.mark.parametrize('kind,indexes,target', [
    ('distance', [0, 1], 2.5), ('angle', [0, 1, 2], 115.), ('dihedral', [0, 1, 2, 3], -179.),
])
def test_gaussian_seed_projection_matches_internal_coordinates(kind, indexes, target):
    from conformers import internal_value
    xyz = np.array([[1., 0, 0], [0, 0, 0], [0, 0, 1], [1., 1, 1]])
    before = xyz.copy()
    result = constrained_start(xyz, [{'kind': kind, 'indexes': indexes}], [target])
    assert internal_value(result[indexes]) == pytest.approx(target, abs=1e-5)
    assert np.array_equal(xyz, before)


def test_gaussian_projection_handles_coupled_axes_and_rejects_inconsistent_targets():
    xyz = np.array([[0., 0, 0], [1., 0, 0], [1., 1, 0]])
    axes = [{'kind': 'distance', 'indexes': [0, 1]}, {'kind': 'distance', 'indexes': [1, 2]}]
    result = constrained_start(xyz, axes, [2., 3.])
    assert np.linalg.norm(result[0] - result[1]) == pytest.approx(2.)
    assert np.linalg.norm(result[1] - result[2]) == pytest.approx(3.)
    with pytest.raises(ValueError, match='cannot satisfy'):
        constrained_start(xyz, [axes[0], axes[0]], [2., 3.])


@pytest.mark.parametrize('operation',['qst-prepare','scan-xtb','scan-gaussian','neb-xtb','gradient-xtb'])
def test_registered_path_operations_through_jobs(tmp_path,monkeypatch,operation):
    from research_agent.application.api import execute
    from research_agent.application.executors import prepare
    from tests.unit.test_job_recovery import workspace
    root=tmp_path/'work';workspace(root)
    config=Path(os.environ['CORAGENT_JOB_CONFIG']);text=config.read_text();data=tomllib.loads(text)
    binding=data['execution']['targets']['local']['bindings']['structure']['python']
    for backend,program in [('path_xtb',fake_xtb(tmp_path/'xtb')),('path_gaussian',fake_gaussian(tmp_path/'g16'))]:
        text=re.sub(r'(?ms)^\[execution\.targets\.local\.bindings\.'+backend+r'\]\n.*?(?=^\[|\Z)','',text)
        text+='\n[execution.targets.local.bindings.'+backend+']\ncommand = '+json.dumps(str(program))+'\n'
        text+='[execution.targets.local.bindings.'+backend+'.python]\n'+''.join(k+' = '+json.dumps(v)+'\n' for k,v in binding.items())
    config=tmp_path/'job.toml';config.write_text(text);monkeypatch.setenv('CORAGENT_JOB_CONFIG',str(config))
    if operation=='qst-prepare':spec=qst_input(True)
    elif operation.startswith('scan'):spec=scan_input(backend=operation.split('-')[1])
    elif operation=='gradient-xtb':spec={'schema_version':'chemical-gradient-input/1','material':molecule(1.5),'settings':settings()}
    else:
        spec={'schema_version':'chemical-neb-input/2',**endpoints(),'settings':settings(),'image_count':3,'max_steps':0}
        spec.update(reactant=molecule(center=True),product=molecule(3.,permutation=[1,0],center=True))
    source=root/'input.json';source.write_text(json.dumps(spec))
    prepared=prepare(config,'local','chemical.'+operation,'2' if operation=='neb-xtb' else '1',{'input':source})
    node=execute('research.create',root,{'goal':'Independent path operation fixture'})['node']
    receipt=execute('job.start',root,{**prepared,'node_id':node['id']})
    try:
        for _ in range(600):
            status=execute('job.status',root,{'job_id':receipt['job_id']})
            if status['state'] in ('succeeded','failed'):break
            time.sleep(.01)
        # This monotonic synthetic path has nonzero climbing force. With no
        # optimizer steps it must remain limited, while retaining collectable evidence.
        assert status['state']==('failed' if operation=='neb-xtb' else 'succeeded')
        assert execute('job.collect',root,{'job_id':receipt['job_id']})['output_validation']['complete']
        result=json.loads((Path(receipt['cwd'])/'results/result.json').read_text())
        if operation=='neb-xtb':assert result['status']=='step_limit' and not result['candidate']['validated_ts']
        if operation=='qst-prepare':assert result['kind']=='QST3'
    finally:execute('job.cancel',root,{'job_id':receipt['job_id']})


@pytest.mark.parametrize('backend', ['xtb', 'gaussian'])
def test_scan_angle_and_dihedral_contracts(backend):
    from scan_engine import measure
    from tests.unit.test_crest_ensembles import water
    m=water()
    axis={'kind':'angle','atoms':['atom_2','atom_1','atom_3'],'values':[104.5],'unit':'degree','tolerance':1.}
    parsed=axes_for([axis],m)
    assert measure(parsed,m['coordinates'],[104.5])[2]
    points=np.array([[1.,0,0],[0,0,0],[0,1,0],[-1,1,.001]])
    axis={'kind':'dihedral','indexes':[0,1,2,3],'tolerance':1.}
    actual,deviation,matched=measure([axis],points,[180.])
    assert matched and deviation[0]<.1


def test_native_timeout_retains_failed_point_and_reaps_descendants(tmp_path):
    native=fake_xtb(tmp_path/'xtb','timeout');s=scan_input();s['axes'][0]['values']=[1.]
    s['settings']['timeout_seconds']=.4
    result=scan(s,tmp_path/'out','xtb',lambda m,s:XtbCalculator(m,s,str(native)))
    assert result['status']=='failed' and result['points'][0]['error']['type']=='TimeoutExpired'
    pid=int((tmp_path/'out/points/0000/child.pid').read_text());proc=Path(f'/proc/{pid}/stat')
    assert not proc.exists() or proc.read_text().split()[2]=='Z'
    assert json.loads((tmp_path/'out/result.json').read_text())==result


def test_gradient_entrypoint_retains_failure_receipt(tmp_path):
    from search_cli import parse_arguments
    native=fake_xtb(tmp_path/'xtb','bad_gradient')
    spec={'schema_version':'chemical-gradient-input/1','material':molecule(1.5),'settings':settings()}
    source=tmp_path/'input.json';source.write_text(json.dumps(spec))
    result=search.run(parse_arguments(['--input',str(source),'--output-dir',str(tmp_path/'out'),'gradient-xtb','--executable',str(native)]))
    assert result['status']=='failed' and result['error']['type']=='ValueError'
    assert (tmp_path/'out/evaluation/gradient').is_file()


def test_core_neb_accepts_independent_calculator_settings(tmp_path):
    s=neb_input();s['settings']={'analytic_fixture':True}
    result=neb(s,tmp_path/'out',Analytic)
    assert result['status']=='converged' and result['model']['method']=='synthetic_double_well'


def test_path_environment_profile_is_opt_in_and_preserves_wrapper_bindings(tmp_path):
    from scripts import _job_install as jobs
    from tests.unit.test_job_installation import options
    config=tmp_path/'job.toml'
    config.write_text('[execution]\ndefault_target="local"\n[execution.targets.local]\ntype="local"\ndriver="process"\n'
                      '[execution.targets.local.bindings.xtb]\ncommand="/native/xtb"\n'
                      '[execution.targets.local.bindings.path_xtb]\ncommand="/native/xtb"\n')
    value=jobs.plan(options(tmp_path,'--job-config',str(config),'--job-profile','local:path'))
    assert len(value['environments'])==1
    row=value['environments'][0]
    assert row['backends']==['path_xtb']
    assert row['profile']=='path'


@pytest.mark.parametrize('backend',['xtb','gaussian'])
def test_native_output_cannot_silently_change_charge_or_spin(tmp_path,backend):
    if backend=='xtb':
        native=fake_xtb(tmp_path/'xtb')
        text=native.read_text().replace("print('Hamiltonian GFN2-xTB')", "print('Hamiltonian GFN2-xTB'); print('net charge 1')")
        cls=XtbCalculator
    else:
        native=fake_gaussian(tmp_path/'g16');text=native.read_text().replace('Charge = 0 Multiplicity = 1','Charge = 0 Multiplicity = 3')
        cls=GaussianOptimizer
    native.write_text(text)
    result=scan(scan_input(backend=backend),tmp_path/'out',backend,lambda m,s:cls(m,s,str(native)))
    assert result['status']=='failed' and not result.get('candidate')


def test_path_candidates_do_not_assert_reactant_connectivity():
    from path_contract import candidate_material
    source={'schema_version':'chemical-material-input/1','format':'xyz',
            'text':'2\nfixture\nH 0 0 0\nH .74 0 0\n','charge':0,'multiplicity':1,
            'electronic_state':{'kind':'ground'},'graph':{'smiles':'[H:7][H:9]','source':'user','note':'reactant'},'graph_to_input':[0,1]}
    m=material(build_material(source,'sha256:'+'a'*64)[0])
    candidate=candidate_material(m,[[0,0,0],[2,0,0]],{'operation':'synthetic_path'})
    checked_candidate=checked(candidate)
    assert checked_candidate['ids']==m['ids'] and checked_candidate['mol'] is None
    assert candidate['graph'] is None and candidate['identity'] is None
    assert candidate['derivation']['source_atom_maps']=={'atom_1':7,'atom_2':9}
    assert candidate['derivation']['reference_graph']['smiles']=='[H:7][H:9]'
    assert candidate['fragments']['groups'] is None and m['mol'] is not None
