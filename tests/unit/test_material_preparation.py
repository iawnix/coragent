"""Import real structure data without inferring a mechanism or running a solver."""
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import time

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / 'domains/chemical/skills/material-preparation/scripts/materials'
from tests.unit.chemical_paths import configure
configure()
spec = importlib.util.spec_from_file_location('chemical_material_import', SCRIPTS / 'material.py')
material = importlib.util.module_from_spec(spec)
spec.loader.exec_module(material)

COMPLEX = '6\r\nuser complex; preserve orientation\r\nO 0.00000000001 0 0\r\nH 0 0 0.96\r\nH 0 .93 -.24\r\nO 5.0 2.0 1.0\r\nH 5.0 2.0 1.96\r\nH 5.0 2.93 .76\r\n'


def request(text=COMPLEX, fmt='xyz', **extra):
    return {'schema_version': 'chemical-material-input/1', 'format': fmt, 'text': text, **extra}


def run_import(tmp_path, value):
    source = tmp_path / 'input.json'
    source.write_text(json.dumps(value, ensure_ascii=False))
    return material.import_material(source, tmp_path / 'output')


def test_xyz_complex_bytes_and_orientation_survive_import_without_defaults(tmp_path):
    result = run_import(tmp_path, request(arrangement='complex', fragments=[[0, 1, 2], [3, 4, 5]]))
    assert (tmp_path / 'output/source.txt').read_bytes() == COMPLEX.encode()
    assert (tmp_path / 'output/geometry.xyz').read_bytes() == COMPLEX.encode()
    assert result['atoms'][3]['coordinates'] == [5., 2., 1.]
    assert result['atoms'][0]['coordinates'][0] == 1e-11
    assert result['charge'] is None and result['multiplicity'] is None
    assert result['graph'] is None and result['identity'] is None
    assert result['electronic_state']['kind'] == 'unspecified'
    assert result['electron_count_parity'] == 'not_assessed'
    assert result['arrangement'] == 'complex'
    assert result['geometry']['status'] == 'supplied_not_assessed'
    assert result['fragments']['groups'] == [['atom_1', 'atom_2', 'atom_3'], ['atom_4', 'atom_5', 'atom_6']]


def test_reordering_is_reversible_and_keeps_ids_and_fragments(tmp_path):
    order = [3, 0, 5, 2, 4, 1]
    result = run_import(tmp_path, request(new_to_old=order, fragments=[[0, 1, 2], [3, 4, 5]]))
    stored = json.loads((tmp_path / 'output/atom_order.json').read_text())
    assert stored['new_to_old'] == order
    restored = [result['atoms'][stored['old_to_new'][i]] for i in range(6)]
    assert [a['input_index'] for a in restored] == list(range(6))
    assert [a['coordinates'] for a in restored] == [r['coordinates'] for r in material.xyz_text(COMPLEX)]
    assert result['fragments']['groups'][1] == ['atom_4', 'atom_5', 'atom_6']
    lines = (tmp_path / 'output/geometry.xyz').read_bytes().decode().splitlines()
    assert lines[2:] == [COMPLEX.splitlines()[i + 2] for i in order]
    assert (tmp_path / 'output/source.txt').read_bytes() == COMPLEX.encode()
    assert result['source']['input_sha256'] == 'sha256:' + hashlib.sha256((tmp_path / 'input.json').read_bytes()).hexdigest()


def test_smiles_preserves_explicit_h_isotopes_and_maps_without_embedding(tmp_path):
    result = run_import(tmp_path, request('[2H:7][O:2][H:8]', 'smiles', multiplicity=1))
    assert [a['atom_map'] for a in result['atoms']] == [7, 2, 8]
    assert [a['isotope'] for a in result['atoms']] == [2, None, None]
    assert result['charge'] == 0 and result['charge_source'] == 'supplied_graph'
    assert result['electron_count_parity'] == 'compatible'
    assert result['geometry'] is None
    assert not (tmp_path / 'output/geometry.xyz').exists()
    assert result['electronic_state']['kind'] == 'unspecified', 'multiplicity does not select an electronic state'


def test_smiles_does_not_turn_disconnected_species_into_an_assumed_complex(tmp_path):
    result = run_import(tmp_path, request('[Na+].[Cl-]', 'smiles'))
    assert result['arrangement'] == 'unspecified'
    assert result['fragments']['source'] == 'supplied_graph'
    assert len(result['fragments']['groups']) == 2
    assert result['charge'] == 0


def test_unresolved_name_keeps_original_without_network_or_invented_structure(tmp_path):
    result = run_import(tmp_path, request('用户描述的未知络合物', 'name'))
    assert result['source']['text'] == '用户描述的未知络合物'
    assert result['atoms'] == [] and result['identity'] is None
    assert 'graph' in result['unknown_fields']
    assert 'geometry' in result['unknown_fields']
    assert result['atom_order']['new_to_old'] == []


def test_selected_name_graph_remains_attributed_and_supports_structure_compare(tmp_path):
    result = run_import(tmp_path, request('乙醇', 'name', graph={
        'smiles': 'CCO', 'source': 'lookup', 'note': 'Selected candidate from a separately collected resolver result'}))
    assert result['source']['text'] == '乙醇'
    assert result['graph']['source'] == 'lookup'
    assert len(result['atoms']) == 9
    assert sum(a['origin'] == 'added_hydrogen' for a in result['atoms']) == 6
    from chemical_identity import compare
    target = tmp_path / 'reference-structure.json'
    target.write_text(json.dumps({'smiles': 'CCO'}))
    assert compare(target, tmp_path / 'output/material.json')['status'] == 'match'


def test_xyz_graph_correspondence_preserves_geometry_and_explicit_identity(tmp_path):
    text = '3\ninput order H H O\nH 0 0 .96\nH 0 .93 -.24\nO 0 0 0\n'
    result = run_import(tmp_path, request(text, graph={'smiles': 'O', 'source': 'user', 'note': 'User identifies water'},
                                          graph_to_input=[2, 0, 1], new_to_old=[2, 0, 1]))
    assert [a['element'] for a in result['atoms']] == ['O', 'H', 'H']
    assert result['graph']['graph_to_input'] == [2, 0, 1]
    assert result['atoms'][1]['coordinates'] == [0., 0., .96]
    assert result['graph']['geometry_identity'] == 'not_assessed'


def test_excited_state_description_is_not_a_wavefunction_or_support_claim(tmp_path):
    state = {'kind': 'excited', 'root': 2, 'method': 'TDDFT/B3LYP', 'label': 'S2 candidate'}
    result = run_import(tmp_path, request('O', 'smiles', multiplicity=1, electronic_state=state))
    assert result['electronic_state']['root'] == 2
    assert result['electronic_state']['verification'] == 'not_assessed'
    assert result['electron_count_parity'] == 'compatible'


@pytest.mark.parametrize('extra', [
    {'charge': True}, {'multiplicity': True}, {'multiplicity': 0},
    {'new_to_old': [0] * 6}, {'new_to_old': [False, 1, 2, 3, 4, 5]},
    {'atom_ids': ['same'] * 6}, {'fragments': [[0, 1, 2], [2, 3, 4, 5]]},
    {'coordinate_unit': 'bohr'}, {'graph_to_input': list(range(6))},
    {'electronic_state': {'kind': 'excited', 'root': 2}},
    {'electronic_state': {'kind': 'ground', 'root': 1, 'method': 'HF'}},
    {'silent_unknown_option': True},
])
def test_invalid_or_ambiguous_metadata_is_rejected_before_output(tmp_path, extra):
    with pytest.raises(ValueError):
        run_import(tmp_path, request(**extra))
    assert not (tmp_path / 'output').exists()


@pytest.mark.parametrize('text', [COMPLEX + COMPLEX, '2\nshort\nH 0 0 0\n',
                                 '1\nnonfinite\nH NaN 0 0\n', '1\nextra\nH 0 0 0 9\n'])
def test_xyz_does_not_silently_drop_frames_or_extra_atom_properties(tmp_path, text):
    with pytest.raises(ValueError):
        run_import(tmp_path, request(text))
    assert not (tmp_path / 'output').exists()


@pytest.mark.parametrize('value', [
    request('O\nCCO', 'smiles'), request('CCO ethanol', 'smiles'), request('*C', 'smiles'),
    request('O', 'smiles', charge=1), request('O', 'smiles', multiplicity=2),
    request('O', 'smiles', fragments=[[0], [1, 2]]),
    request('water', 'name', new_to_old=[]),
    request('3\nwater\nO 0 0 0\nH 0 0 1\nH 0 1 0\n',
            graph={'smiles': 'O', 'source': 'user', 'note': 'water'}),
    request('3\nwater\nO 0 0 0\nH 0 0 1\nH 0 1 0\n',
            graph={'smiles': 'O', 'source': 'user', 'note': 'water'}, graph_to_input=[1, 0, 2]),
])
def test_graph_state_and_atom_correspondence_conflicts_are_not_normalized_away(tmp_path, value):
    with pytest.raises(ValueError):
        run_import(tmp_path, copy.deepcopy(value))
    assert not (tmp_path / 'output').exists()


def test_material_executor_runs_staged_code_and_collects_reusable_geometry(tmp_path):
    from research_agent.application.api import execute
    from research_agent.application.executors import prepare
    from tests.unit.test_job_recovery import workspace
    root = tmp_path / 'workspace'
    workspace(root)
    node = execute('research.create', root, {'goal': 'Preserve the supplied complex for later calculation'})['node']
    source = root / 'material-input.json'
    source.write_text(json.dumps(request(arrangement='complex')))
    prepared = prepare(Path(os.environ['CORAGENT_JOB_CONFIG']), 'local', 'chemical.material', '1', {'material': source})
    assert not list((root / 'operations/executions').glob('*.json'))
    job = execute('job.start', root, {**prepared, 'node_id': node['id']})
    try:
        for _ in range(300):
            status = execute('job.status', root, {'job_id': job['job_id']})
            if status['state'] in {'succeeded', 'failed'}:
                break
            time.sleep(.01)
        assert status['state'] == 'succeeded'
        collected = execute('job.collect', root, {'job_id': job['job_id']})
        assert collected['output_validation']['complete']
        assert (Path(job['cwd']) / 'results/geometry.xyz').read_bytes() == COMPLEX.encode()
        geometry = next(a for a in collected['artifacts'] if a['provenance']['source_path'].endswith('/geometry.xyz'))
        published = execute('research.result', root, {'node_id': node['id'],
            'conclusion': 'Preserved supplied geometry; no optimization or state verification performed.',
            'files': [{'name': 'complex.xyz', 'artifact_ref': geometry['artifact_id']}]})
        assert published['result_saved']
    finally:
        execute('job.cancel', root, {'job_id': job['job_id']})
