"""Physical geometry invariants and staged execution; no solver or model calls."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest
np = pytest.importorskip('numpy')

ROOT = Path(__file__).resolve().parents[2]
SKILLS = ROOT/'skills/chemical'
from tests.unit.chemical_paths import configure
configure()
from reactive_geometry import generate, run, diagnostics
from geometry_contract import validate
from geometry_ops import apply
from material import build_material
from ensemble_material import canonical, checked
from path_contract import qst


def source_material(isotope=False):
    # Explicit mapped SN2 reactants; C, Cl, F, then the three carbon hydrogens.
    spec = {'schema_version': 'chemical-material-input/1', 'format': 'xyz',
            'text': '6\nDeterministic reactant geometry\nC 0 0 0\nCl 1.8 0 0\nF 5 0 0\nH -.36 1.02 0\nH -.36 -.51 .883\nH -.36 -.51 -.883\n',
            'graph': {'smiles': '[CH3:1][Cl:2].[F-:3]', 'source': 'user', 'note': 'explicit test graph'},
            'graph_to_input': list(range(6)), 'atom_ids': ['C', 'Cl', 'F', 'H1', 'H2', 'H3'],
            'charge': -1, 'multiplicity': 1, 'electronic_state': {'kind': 'ground'}}
    if isotope: spec['graph']['smiles'] = '[CH3:1][Cl:2].[18F-:3]'
    return build_material(spec, canonical(spec))[0]


def request():
    return {'schema_version': 'chemical-reactive-geometry/1', 'material': source_material(),
            'bond_changes': [{'atoms': ['C', 'F'], 'before': 0, 'after': 1}, {'atoms': ['C', 'Cl'], 'before': 1, 'after': 0}],
            'edit_hypotheses': [{'id': 'backside', 'note': 'Test backside approach using the C-Cl local axis', 'source_refs': [],
                'operations': [{'kind': 'place', 'atoms': ['C', 'F'], 'mobile_atoms': ['F'],
                                'direction': {'kind': 'away', 'atoms': ['C', 'Cl']}, 'values': [2.4, 2.6]}]}],
            'sampling': {'count': 16, 'seed': 3}}


def mode(request, amplitudes=(.1, -.1)):
    v = [[0.,0.,0.] for _ in request['material']['atoms']]
    v[0] = [1.,0.,0.]; v[1] = [.25,0.,0.]
    return {'kind': 'displace', 'representation': 'cartesian_direction', 'vectors': v, 'values': list(amplitudes),
            'atom_ids': [a['atom_id'] for a in request['material']['atoms']],
            'material_sha256': canonical(request['material']), 'source_ref': 'artifact:mode'}


def test_backside_placement_changes_wrong_approach_and_preserves_skeleton():
    spec = request(); before = copy.deepcopy(spec)
    result = generate(spec)
    assert spec == before and result == generate(spec)
    assert result['summary'] == {'attempted': 2, 'accepted': 2, 'rejected': 0, 'enumeration_complete': True, 'unexplored_hypotheses': []}
    for row in result['candidates']:
        xyz = np.array(row['coordinates'])
        assert xyz[2,0] < 0  # Original F was on the leaving-group side.
        assert xyz[[0,1,3,4,5]] == pytest.approx(checked(spec['material'])['coordinates'][[0,1,3,4,5]])
        assert row['diagnostics']['coordinates'][0]['actual'] == pytest.approx(row['diagnostics']['coordinates'][0]['target'])
        assert row['material']['graph'] is None and row['material']['charge'] == -1
        assert row['material']['derivation']['reference_graph'] is not None
        assert checked(row['material'])['ids'] == ['C','Cl','F','H1','H2','H3']
        assert row['validated_ts'] is False and row['preoptimization'] == 'not_run'


def test_modes_keep_zero_vectors_relative_amplitudes_and_evidence():
    spec = request(); h = spec['edit_hypotheses'][0]; h['source_refs'] = ['artifact:mode']; h['operations'] = [mode(spec)]
    result = generate(spec)
    assert len(result['candidates']) == 2
    for row, amplitude in zip(result['candidates'], [.1,-.1]):
        delta = np.array(row['coordinates'])-checked(spec['material'])['coordinates']
        assert delta[0,0] == pytest.approx(amplitude)
        assert delta[1,0] == pytest.approx(amplitude*.25)
        assert np.count_nonzero(delta[2:]) == 0
        assert row['source_refs'] == ['artifact:mode']
        assert row['material']['derivation']['source_refs'] == ['artifact:mode']


@pytest.mark.parametrize('fault', ['digest','order','mass_weighted','zero','missing_evidence'])
def test_displacement_requires_bound_cartesian_evidence(fault):
    spec = request(); h = spec['edit_hypotheses'][0]; h['source_refs'] = ['artifact:mode']; op = mode(spec); h['operations'] = [op]
    if fault == 'digest': op['material_sha256'] = 'sha256:'+'0'*64
    if fault == 'order': op['atom_ids'].reverse()
    if fault == 'mass_weighted': op['representation'] = 'mass_weighted'
    if fault == 'zero': op['vectors'] = [[0,0,0]]*6
    if fault == 'missing_evidence': h['source_refs'] = []
    with pytest.raises(ValueError): generate(spec)


def test_combined_edits_recheck_all_targets_on_final_geometry():
    spec = request(); ops = spec['edit_hypotheses'][0]['operations']; ops[0]['values'] = [2.4]
    ops.append({'kind': 'distance', 'atoms': ['C','F'], 'mobile_atoms': ['F'], 'values': [2.8]})
    result = generate(spec)
    assert result['status'] == 'no_candidates'
    assert 'final_target_not_met' in result['rejected'][0]['diagnostics']['reasons']
    assert result['rejected'][0]['diagnostics']['coordinates'][0]['actual'] == pytest.approx(2.8)


def test_local_atom_stretch_rejects_broken_protected_bonds():
    spec = request(); h = spec['edit_hypotheses'][0]; h['source_refs'] = ['artifact:mode']
    op = mode(spec, (.5,)); op['vectors'] = [[0,0,0]]*6; op['vectors'][3] = [0,1,0]; h['operations'] = [op]
    result = generate(spec)
    assert not result['candidates'] and 'protected_bond_distortion' in result['rejected'][0]['diagnostics']['reasons']


def test_clashes_include_reactive_pairs_and_same_fragment_atoms():
    spec = request(); op = spec['edit_hypotheses'][0]['operations'][0]; op['values'] = [.2]
    result = generate(spec)
    assert not result['candidates'] and 'atomic_clash' in result['rejected'][0]['diagnostics']['reasons']
    spec = request(); spec['material']['atoms'][3]['coordinates'] = [0,0,0]
    result = generate(spec)
    assert not result['candidates'] and 'atomic_clash' in result['rejected'][0]['diagnostics']['reasons']


def test_wrong_side_contact_is_rejected_even_when_reactive_distance_matches():
    spec = request(); op = spec['edit_hypotheses'][0]['operations'][0]
    op['direction'] = {'kind':'vector','vector':[1,0,0]}; op['values'] = [2.4]
    result = generate(spec)
    assert result['status'] == 'no_candidates'
    assert result['rejected'][0]['diagnostics']['coordinates'][0]['actual'] == pytest.approx(2.4)
    assert any(set(c['atoms']) == {'Cl','F'} for c in result['rejected'][0]['diagnostics']['clashes'])


def test_degenerate_frame_is_preserved_as_rejected_candidate():
    spec = request(); op = spec['edit_hypotheses'][0]['operations'][0]
    op['direction'] = {'kind':'normal','atoms':['C','Cl','H1']}
    spec['material']['atoms'][3]['coordinates'] = [-1,0,0]
    result = generate(spec)
    assert not result['candidates'] and any('degenerate' in r for r in result['rejected'][0]['diagnostics']['reasons'])


def test_angle_and_dihedral_rotate_groups_without_internal_distortion():
    ids = ['A','B','C','D','E']
    original = np.array([[1,0,0],[0,0,0],[0,1,0],[0,1,1],[.2,1,1.3]], float)
    for kind, atoms, mobile, target in [('angle',['A','B','C'],['C','D','E'],120.), ('dihedral',['A','B','C','D'],['D','E'],-45.)]:
        xyz = original.copy(); op = {'kind':kind,'atoms':atoms,'mobile_atoms':mobile}
        trace = apply(op,xyz,ids,[],target,np.random.default_rng(0))
        from conformers import internal_value
        assert internal_value(xyz[[ids.index(a) for a in atoms]]) == pytest.approx(target)
        group = [ids.index(a) for a in mobile]
        assert np.linalg.norm(xyz[group[-1]]-xyz[group[0]]) == pytest.approx(np.linalg.norm(original[group[-1]]-original[group[0]]))
        assert np.linalg.det(trace['rotation']) == pytest.approx(1.)


def test_placement_aligns_mobile_frame_and_preserves_chirality():
    ids=['A','B','C','D','E','F']
    xyz=np.array([[0,0,0],[4,0,0],[5,0,0],[4,1,0],[4,0,1],[4,-1,0]],float)
    original=xyz.copy()
    op={'kind':'place','atoms':['A','B'],'mobile_atoms':ids[1:], 'direction':{'kind':'vector','vector':[1,0,0]},
        'mobile_direction':{'kind':'away','atoms':['B','C']}}
    trace=apply(op,xyz,ids,[],(2.,45.),np.random.default_rng(0))
    assert xyz[1] == pytest.approx([2,0,0])
    assert (xyz[1]-xyz[2]) == pytest.approx([-1,0,0])
    assert np.linalg.det(trace['rotation']) == pytest.approx(1)
    assert np.linalg.norm(xyz[1:,None]-xyz[None,1:],axis=2) == pytest.approx(np.linalg.norm(original[1:,None]-original[None,1:],axis=2))


def test_count_bound_and_duplicate_geometries_are_reported():
    spec=request(); spec['sampling']['count']=1
    result=generate(spec)
    assert not result['summary']['enumeration_complete'] and result['summary']['unexplored_hypotheses']==['backside']
    spec=request(); spec['edit_hypotheses'][0]['operations'][0]['twists']=[0,90]
    result=generate(spec)
    assert len(result['candidates'])==2 and len(result['rejected'])==2
    assert all('duplicate_geometry' in r['diagnostics']['reasons'] for r in result['rejected'])


def test_candidate_material_can_be_reused_and_given_to_qst3():
    spec=request(); candidate=generate(spec)['candidates'][0]['material']
    later=request(); later['reference_material']=later['material']; later['material']=candidate
    later['edit_hypotheses'][0]['operations']=[{'kind':'distance','atoms':['C','F'],'mobile_atoms':['F'],'values':[2.5]}]
    assert generate(later)['candidates']
    mapping=[[i,i] for i in checked(candidate)['ids']]
    text, manifest, _=qst({'schema_version':'chemical-qst-input/1','reactant':spec['material'],'product':spec['material'],
        'mapping':mapping,'guess':candidate,'guess_mapping':mapping,'settings':{'method':'HF','basis':'STO-3G','threads':1,
        'memory_mb':128,'timeout_seconds':60,'solvent_model':'gas','solvent':None}})
    assert manifest['kind']=='QST3' and 'QST3' in text


def test_repeated_edit_keeps_isotope_and_map_lineage_with_graphless_source():
    spec=request(); spec['material']=source_material(isotope=True)
    first=generate(spec)['candidates'][0]['material']
    spec['reference_material']=spec['material']; spec['material']=first
    second=generate(spec)['candidates'][0]['material']
    assert second['atoms'][2]['isotope']==18
    assert second['derivation']['source_atom_maps']==first['derivation']['source_atom_maps']
    assert second['derivation']['source_material_sha256']==canonical(first)
    assert second['derivation']['reference_graph'] is not None


def test_later_edit_cannot_silently_undo_approach_orientation():
    spec=request();op=spec['edit_hypotheses'][0]['operations'][0];op['values']=[2.4]
    spec['edit_hypotheses'][0]['operations'].append({'kind':'angle','atoms':['Cl','C','F'],
                                                 'mobile_atoms':['F'],'values':[170.]})
    # Avoid a collinear initial angle: the explicit direction places F 5 degrees off the axis.
    op['direction']={'kind':'vector','vector':[-1.,.08749,0.]}
    result=generate(spec)
    assert not result['candidates']
    assert 'final_approach_direction_not_met' in result['rejected'][0]['diagnostics']['reasons']


def test_planar_faces_use_opposite_normals_without_reflection():
    ids=['A','B','C','D']
    initial=np.array([[0,0,0],[1,0,0],[0,1,0],[5,0,0]],float)
    for sign in (-1,1):
        xyz=initial.copy()
        op={'kind':'place','atoms':['A','D'],'mobile_atoms':['D'],
            'direction':{'kind':'normal','atoms':['A','B','C'],'sign':sign}}
        trace=apply(op,xyz,ids,[],(2.,0.),np.random.default_rng(0))
        assert xyz[3]==pytest.approx([0,0,sign*2.])
        assert np.linalg.det(trace['rotation'])==pytest.approx(1.)


@pytest.mark.parametrize('fault', ['unknown_atom','missing_graph','wrong_before','unknown_field','boolean','wrong_group','duplicate_change'])
def test_invalid_input_produces_no_output(fault,tmp_path):
    spec=request()
    if fault=='unknown_atom': spec['bond_changes'][0]['atoms'][1]='missing'
    if fault=='missing_graph': spec['material']['graph']=None
    if fault=='wrong_before': spec['bond_changes'][1]['before']=2
    if fault=='unknown_field': spec['sampling']['cotn']=12
    if fault=='boolean': spec['material']['atoms'][0]['coordinates'][0]=True
    if fault=='wrong_group': spec['edit_hypotheses'][0]['operations'][0]['mobile_atoms']=['F','H1']
    if fault=='duplicate_change': spec['bond_changes']*=2
    path=tmp_path/'input.json';path.write_text(json.dumps(spec));out=tmp_path/'out'
    with pytest.raises(ValueError):run(path,out)
    assert not out.exists()


def test_rejected_geometry_and_source_are_exported_without_overwrite(tmp_path):
    spec=request();spec['edit_hypotheses'][0]['operations'][0]['values']=[.2]
    src=tmp_path/'input.json';src.write_text(json.dumps(spec));out=tmp_path/'out'
    result=run(src,out)
    assert result['status']=='no_candidates' and (out/'rejected/candidate-0001/geometry.xyz').is_file()
    assert json.loads((out/'input.json').read_text())==spec
    with pytest.raises(ValueError,match='empty'):run(src,out)


def test_executor_declared_closure_runs_without_source_tree(tmp_path):
    descriptor=next(e for e in json.loads((SKILLS/'execution.json').read_text())['executors'] if e['id']=='chemical.reactive-geometry')
    staged=tmp_path/'stage';staged.mkdir()
    import hashlib
    for path, expected in descriptor['resources'].items():
        raw=(SKILLS/path).read_bytes()
        assert 'sha256:'+hashlib.sha256(raw).hexdigest()==expected
        target=staged/path;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
    (staged/'input.json').write_text(json.dumps(request()))
    result=subprocess.run([sys.executable, str(staged/descriptor['entry']), '--input','input.json','--output-dir','results'],
                          cwd=staged,env={**os.environ,'PYTHONPATH':'','PYTHONDONTWRITEBYTECODE':'1'},capture_output=True,text=True,timeout=30)
    assert result.returncode==0,result.stderr
    output=json.loads((staged/'results/result.json').read_text())
    assert len(output['candidates'])==2
    for row in output['candidates']:
        assert (staged/'results'/row['xyz']['path']).is_file()
        assert checked(json.loads((staged/'results/candidates'/row['id']/'material.json').read_text()))['ids']==row['atom_ids']


@pytest.mark.parametrize('collapse', [False, True])
def test_registered_job_collects_candidates_or_rejection_evidence(tmp_path, collapse):
    import time
    from research_agent.application.api import execute
    from research_agent.application.executors import prepare
    from tests.unit.test_job_recovery import workspace
    root=tmp_path/'workspace';root.mkdir();workspace(root)
    spec=request()
    if collapse: spec['edit_hypotheses'][0]['operations'][0]['values']=[.2]
    source=root/'edits.json';source.write_text(json.dumps(spec))
    node=execute('research_create',root,{'goal':'Deterministic reactive geometry fixture'})['node']
    request_file=prepare(os.environ['CORAGENT_JOB_CONFIG'],'local','chemical.reactive-geometry','1',{'input':source})
    receipt=execute('job_start',root,{**request_file,'node_id':node['id']})
    try:
        deadline=time.monotonic()+20
        while time.monotonic()<deadline:
            state=execute('job_status',root,{'job_id':receipt['job_id']})['state']
            if state in {'succeeded','failed','cancelled'}:break
            time.sleep(.05)
        assert state==('failed' if collapse else 'succeeded')
        collected=execute('job_collect',root,{'job_id':receipt['job_id']})
        assert collected['output_validation']['complete']
        result=next(a for a in collected['artifacts'] if a['provenance']['source_path'].endswith('/result.json'))
        data=json.loads(Path(result['location']).read_text())
        assert data['status']==('no_candidates' if collapse else 'candidates_generated')
        assert any(a['provenance']['source_path'].endswith('/geometry.xyz') for a in collected['artifacts'])
    finally:execute('job_cancel',root,{'job_id':receipt['job_id']})
