"""Actual Job/parser/validator execution with synthetic Gaussian output, never a chemistry calculation."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys
import time

import pytest
np = pytest.importorskip('numpy')
Chem = pytest.importorskip('rdkit.Chem')

ROOT=Path(__file__).resolve().parents[2]
SKILLS=ROOT/'skills/chemical'
from tests.unit.chemical_paths import configure
configure()
from reaction_checks import reaction, ordered_molecule
from path_validation import log_checks
from path_specification import preparation_spec
from gaussian_io import read_xyz, parse_log
spec=importlib.util.spec_from_file_location('chemical_candidate_path',SKILLS/'candidate-generation/scripts/path/prepare_path.py')
helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
irc_spec=importlib.util.spec_from_file_location('chemical_irc_preparation',SKILLS/'validation/scripts/irc_preparation.py')
irc_helper=importlib.util.module_from_spec(irc_spec);irc_spec.loader.exec_module(irc_helper)

REACTANTS='[CH2:1]1[CH:2]=[CH:3][CH2:4]1'
PRODUCT='[CH2:1]=[CH:2][CH:3]=[CH2:4]'
SPEC={'schema_version':'chemical-path-spec/1','mapped_smiles':REACTANTS+'>>'+PRODUCT,
      'transformation':{'kind':'explicit','bond_changes':[
          {'atoms':[1,2],'before':1,'after':2},
          {'atoms':[1,4],'before':1,'after':0},
          {'atoms':[2,3],'before':2,'after':1},
          {'atoms':[3,4],'before':1,'after':2}]},
      'method':'M062X','basis':'6-31G**','charge':0,'multiplicity':1,'threads':12,'memory_mb':4000}


def candidate(tmp_path, conformers=1):
    source=tmp_path/'spec.json';source.write_text(json.dumps(SPEC))
    result=helper.prepare_candidates(source,tmp_path/'candidates',conformers,True)
    assert all(row['status']=='prepared' for row in result['candidates']),result
    return result,result['candidates'][0]


def test_candidates_are_reproducible_bound_ordered_inputs_and_keep_branches(tmp_path):
    for name in ('first','second'):(tmp_path/name).mkdir()
    first,a=candidate(tmp_path/'first',2);second,b=candidate(tmp_path/'second',2)
    assert len(first['candidates'])==2
    assert a['files']['ts.gjf']['sha256']==b['files']['ts.gjf']['sha256']
    from input_job import inspect_input
    for row in first['candidates']:
        path=Path(row['files']['ts.gjf']['path'])
        assert 'QST2' in inspect_input(path,'M062X','6-31G**',0,1,12,4000)['routes'][0]
        molecule=preparation_spec(json.loads(Path(row['files']['spec.json']['path']).read_text()))[1][0]
        assert len(json.loads(Path(row['files']['atom_order.json']['path']).read_text())['atoms'])==Chem.AddHs(molecule).GetNumAtoms()
    bad=copy.deepcopy(SPEC);bad['transformation']['bond_changes'][0]['after']=3
    (tmp_path/'bad.json').write_text(json.dumps(bad))
    with pytest.raises(ValueError,match='bond changes'):
        helper.prepare_candidates(tmp_path/'bad.json',tmp_path/'bad')
    assert not (tmp_path/'bad').exists()


def orientation(atoms):
    lines=[' Standard orientation:', ' ---------------------------------------------------------------------',
           ' Center Atomic Atomic Coordinates (Angstroms)', ' Number Number Type X Y Z',
           ' ---------------------------------------------------------------------']
    for i,(symbol,*coords) in enumerate(atoms,1):
        lines.append(f' {i} {Chem.GetPeriodicTable().GetAtomicNumber(symbol)} 0 '+ ' '.join(f'{x:.9f}' for x in coords))
    return '\n'.join(lines+[' ---------------------------------------------------------------------'])


def synthetic_logs(row):
    """Parser fixtures only: midpoint geometry and interpolated mode are not a computed TS."""
    _,_,reactants=read_xyz(Path(row['files']['reactants.xyz']['path']))
    _,_,product=read_xyz(Path(row['files']['product.xyz']['path']))
    spec=json.loads(Path(row['files']['spec.json']['path']).read_text())
    endpoint_reactants=reactants
    r=np.array([a[1:] for a in reactants]);p=np.array([a[1:] for a in product]);middle=(r+p)/2
    saddle=[(a[0],*v) for a,v in zip(reactants,middle)]
    vector=p-r;vector/=np.linalg.norm(vector)
    title=' SYNTHETIC FIXTURE: exercises parser and runtime, not physical chemistry\n %nprocshared=12\n %mem=4000MB\n CoRAgentSpec '+hashlib.sha256(Path(row['files']['spec.json']['path']).read_bytes()).hexdigest()+'\n'
    route=Path(row['files']['ts.gjf']['path']).read_text().splitlines()[3]
    log=title+route+'\n ----------------\n Charge = 0 Multiplicity = 1\n'+orientation(saddle)+'\n SCF Done: E(RM062X) = -270.0 A.U.\n'
    log+=' Maximum Force 0.00001 0.00045 YES\n RMS     Force 0.00001 0.00030 YES\n Maximum Displacement 0.00001 0.0018 YES\n RMS     Displacement 0.00001 0.0012 YES\n Stationary point found.\n Harmonic frequencies\n'
    for start in range(0,3*len(saddle)-6,3):
        fs=[-200.0 if start+i==0 else 100.+start+i for i in range(3)]
        log+=' Frequencies -- '+ ' '.join(map(str,fs))+'\n Red. masses -- 1.0 1.0 1.0\n Atom  AN      X Y Z        X Y Z        X Y Z\n'
        for index,(symbol,*_) in enumerate(saddle):
            values=list(vector[index]) if start==0 else [0.,0.,0.]
            log+=f' {index+1} {Chem.GetPeriodicTable().GetAtomicNumber(symbol)} '+' '.join(f'{x:.9f}' for x in values+[0.]*6)+'\n'
    log+=' Thermochemistry\n Normal termination of Gaussian\n'
    result={'ts':log}
    for direction,endpoint in [('forward',product),('reverse',endpoint_reactants)]:
        route=f'#p M062X/6-31G** IRC=({direction.capitalize()},CalcFC,MaxPoints=80,StepSize=5) Geom=AllCheck Guess=Read SCF=Tight Int=UltraFine NoSymm'
        text=title+route+'\n ----------------\n Charge = 0 Multiplicity = 1\n'+orientation(saddle)+'\n'
        text+=f' Point Number 1 in {direction.upper()} path direction\n SCF Done: E(RM062X) = -270.1 A.U.\n Point Number: 1 Path Number: 1\n CURRENT STRUCTURE\n'
        for i,(symbol,*coords) in enumerate(endpoint,1):text+=f' {i} {Chem.GetPeriodicTable().GetAtomicNumber(symbol)} '+' '.join(f'{x:.9f}' for x in coords)+'\n'
        text+=f' NET REACTION COORDINATE UP TO THIS POINT = 1.0\n Calculation of {direction.upper()} path complete.\n Normal termination of Gaussian\n'
        result[direction]=text
    return spec,result


def test_unsupported_irc_energy_remains_reference_only(tmp_path):
    from gaussian_io import parse_irc_log
    _, row = candidate(tmp_path)
    _, logs = synthetic_logs(row)
    path = tmp_path / 'irc.out'
    path.write_text(logs['forward'].replace('M062X/6-31G**', 'MP2/6-31G**'))
    parsed = parse_irc_log(path)
    assert parsed['summary']['energy_evidence']['status'] == 'unsupported'
    assert parsed['points'][0]['reference_scf_energy_hartree'] == -270.1
    assert parsed['points'][0]['electronic_energy_hartree'] is None
    assert parsed['atoms'], 'endpoint geometry remains available for separate analysis'


def run_job(root, params):
    from research_agent.application.execution import dispatch
    job=dispatch('start',{'root':str(root),'timeout_seconds':20,**params})
    deadline=time.monotonic()+20
    while time.monotonic()<deadline:
        status=dispatch('status',{'root':str(root),'job_id':job['job_id']})
        if status['state'] in {'succeeded','failed','cancelled','timed_out'}:break
        time.sleep(.02)
    else:
        dispatch('cancel',{'root':str(root),'job_id':job['job_id']});raise AssertionError('fixture Job timed out')
    result=dispatch('collect',{'root':str(root),'job_id':job['job_id']})
    assert status['state']=='succeeded',(result,Path(result['stderr']).read_text() if result.get('stderr') else '')
    return result


def selected(result, suffix):
    return next(a for a in result['artifacts'] if a['provenance']['source_path'].endswith(suffix))


@pytest.mark.parametrize('destinations', [
    ['./validator_inputs.json'], ['validator_result.json'], ['./spec.json'],
    ['logs/stdout.log'], ['module.py', './module.py'], ['library', 'library/module.py'],
])
def test_registered_validator_rejects_resource_target_collisions(tmp_path, monkeypatch, destinations):
    from tests.unit.test_job_recovery import workspace
    from research_agent.application.validators import prepare
    workspace(tmp_path)
    package=tmp_path/'package';domain=package/'skills'/'fixture';domain.mkdir(parents=True)
    script=domain/'validator.py';script.write_text('print("fixture")\n')
    digest='sha256:'+hashlib.sha256(script.read_bytes()).hexdigest()
    descriptor={'id':'fixture.validator','version':'1','entry':'validator.py','sha256':digest,'backend':'validation',
                'resources':{name:{'path':'validator.py','sha256':digest} for name in destinations}}
    (domain/'execution.json').write_text(json.dumps({'schema_version':'coragent-execution/1','name':'fixture','version':'1.0.0','executors':[],'validators':[descriptor],'acceptance_profiles':[]}))
    (package/'package.json').write_text(json.dumps({'coragent':{'execution':['skills/fixture/execution.json']}}))
    monkeypatch.setenv('CORAGENT_PACKAGE_ROOT',str(package))
    with pytest.raises(ValueError,match='execution_(resource_path_invalid|destinations_overlap_or_reserved)'):
        prepare(tmp_path,{'validator_id':'fixture.validator', "validator_version": "1",'input_artifact_ids':['art_unused']})


def test_generic_jobs_execute_candidate_gaussian_and_registered_validators(tmp_path):
    from tests.unit.test_job_recovery import workspace
    from research_agent.application.evidence import dispatch as artifact
    from research_agent.application.validators import prepare
    workspace(tmp_path)
    _,row=candidate(tmp_path);spec,logs=synthetic_logs(row)
    spec_record=artifact('register',{'root':str(tmp_path),'path':row['files']['spec.json']['path']})
    ref=spec_record['artifact_id']
    with pytest.raises(ValueError,match='collected_output'):
        prepare(tmp_path,{'validator_id':'chemical.gaussian_frequency', "validator_version": "1",'input_artifact_ids':[ref]})
    fixture=tmp_path/'fixture_solver.py'
    fixture.write_text(f'#!{sys.executable}\nimport sys,json\nfrom pathlib import Path\nlogs=json.loads({json.dumps(json.dumps(logs))})\ntext=sys.stdin.read()\nassert "IRC=" not in text or any(option in text for option in ("CalcFC", "ReadCartesianFC", "FCCards")), "IRC requires a supported Hessian source"\nkey="forward" if "IRC=(Forward" in text else "reverse" if "IRC=(Reverse" in text else "ts"\nPath(key+".chk").write_bytes(b"synthetic fixture checkpoint")\nprint(logs[key])\n')
    fixture.chmod(0o755)
    def gaussian(gjf,job_id,validation,checkpoint=None):
        inputs=[{'source':str(SKILLS/'gaussian/scripts'),'destination':'skills/chemical/gaussian/scripts'},
                {'source':str(SKILLS/'_shared'),'destination':'skills/chemical/_shared'},
                {'source':str(gjf),'destination':'input.gjf'}, {'source':str(fixture),'destination':'fixture_solver.py'}]
        if checkpoint:inputs.append({'source':str(checkpoint),'destination':'ts.chk'})
        command=[sys.executable,'skills/chemical/gaussian/scripts/run.py','--input-gjf','input.gjf','--executable',str(fixture),
                 '--output-dir','results','--method','M062X','--basis','6-31G**','--threads','12','--memory-mb','4000','--validation',validation]
        outputs=[{'path':'results/'+name,'required':True} for name in ['gaussian.out','parsed.json','result.json']+(['ts.chk'] if validation=='saddle' else ['irc_path_summary.json','gaussian_endpoint.xyz'])]
        return run_job(tmp_path,{'request_id':job_id,'command':command,'inputs':inputs,'outputs':outputs})
    ts=gaussian(row['files']['ts.gjf']['path'],'job_ts','saddle')
    raw=selected(ts,'parsed.json')['artifact_id']
    validated=run_job(tmp_path,{'request_id':'job_saddle','validator_id':'chemical.gaussian_frequency', "validator_version": "1",'input_artifact_ids':[raw]})
    assert validated['result_receipt']['validator_result']['verdict']=='pass'
    proof = validated['result_receipt']['validator_result']
    assert proof['execution_status'] == 'succeeded'
    assert proof['parsing']['status'] == 'not_reported'
    assert 'excludes IRC and mode character' in proof['scope']
    assert proof['provenance']['status'] == 'verified'
    assert proof['provenance']['input_versions'][raw].startswith('sha256:')
    checkpoint=selected(ts,'ts.chk')
    irc=irc_helper.prepare_irc(Path(row['files']['spec.json']['path']),Path(checkpoint['location']),tmp_path/'irc')
    forwards=gaussian(irc['inputs'][0]['path'],'job_forward','irc',irc['checkpoint']['path'])
    reverse=gaussian(irc['inputs'][1]['path'],'job_reverse','irc',irc['checkpoint']['path'])
    for collected in (forwards, reverse):
        summary=json.loads(Path(selected(collected,'irc_path_summary.json')['location']).read_text())
        assert summary['path_complete_marker']
    # The frequency validator receives bound collected bytes, not a reaction recipe.
    Path(selected(ts,'parsed.json')['location']).write_text('{}')
    with pytest.raises(ValueError,match='digest_mismatch'):
        prepare(tmp_path,{'validator_id':'chemical.gaussian_frequency', 'validator_version':'1','input_artifact_ids':[raw]})


def test_gaussian_log_binding_detects_changed_method_state_and_source(tmp_path):
    _, row = candidate(tmp_path)
    spec, logs = synthetic_logs(row)
    spec['_bound_spec_sha256'] = hashlib.sha256(Path(row['files']['spec.json']['path']).read_bytes()).hexdigest()
    atoms, _ = ordered_molecule(preparation_spec(spec)[1][0])
    path = tmp_path / 'log.out'
    for old, new, failed_check in [
        ('M062X/6-31G**', 'HF/6-31G**', 'method_basis'),
        ('%nprocshared=12', '%nprocshared=1', 'processor_binding'),
        ('%mem=4000MB', '%mem=1000MB', 'memory_binding'),
        ('Charge = 0 Multiplicity = 1', 'Charge = 1 Multiplicity = 2', 'electronic_state'),
        ('CoRAgentSpec ', 'UnknownSpec ', 'specification_binding'),
    ]:
        path.write_text(logs['ts'])
        assert all(v['verdict'] == 'pass' for v in log_checks(path, spec, atoms)[1].values())
        path.write_text(logs['ts'].replace(old, new))
        assert log_checks(path, spec, atoms)[1][failed_check]['verdict'] != 'pass'
