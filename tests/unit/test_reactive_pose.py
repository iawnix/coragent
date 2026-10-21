"""Reaction-center pose generation remains deterministic and provenance-safe."""
import json
import hashlib
import os
import subprocess
import sys

import pytest
np = pytest.importorskip('numpy')

ROOT = __import__('pathlib').Path(__file__).resolve().parents[2]
SKILLS = ROOT / 'domains' / 'chemical' / 'skills'
from tests.unit.chemical_paths import configure
configure()

from ensemble_material import canonical  # noqa: E402
from material import build_material, digest  # noqa: E402
from reactive_pose import generate, run  # noqa: E402


def material(*, reversed_order=False):
    if reversed_order:
        text = ('6\nSN2 fixture\nF 5 0 0\nC 0 0 0\nCl 1.8 0 0\n'
                'H -.36 1.02 0\nH -.36 -.51 .883\nH -.36 -.51 -.883\n')
        graph_to_input = [1, 2, 0, 3, 4, 5]
        atom_ids = ['F', 'C', 'Cl', 'H1', 'H2', 'H3']
    else:
        text = ('6\nSN2 fixture\nC 0 0 0\nCl 1.8 0 0\nF 5 0 0\n'
                'H -.36 1.02 0\nH -.36 -.51 .883\nH -.36 -.51 -.883\n')
        graph_to_input = list(range(6))
        atom_ids = ['C', 'Cl', 'F', 'H1', 'H2', 'H3']
    spec = {
        'schema_version': 'chemical-material-input/1', 'format': 'xyz', 'text': text,
        'graph': {'smiles': '[CH3:1][Cl:2].[F-:3]', 'source': 'user', 'note': 'pose fixture'},
        'graph_to_input': graph_to_input, 'atom_ids': atom_ids,
        'charge': -1, 'multiplicity': 1, 'electronic_state': {'kind': 'ground'},
    }
    return build_material(spec, canonical(spec))[0]


def request(source, *, atoms=('C', 'F'), count=8, sampling=None):
    settings = {'count': count, 'seed': 7, 'direction_count': 3,
                'distances': [[2.0, 2.35]], 'twists': [0.0, 120.0]}
    if sampling:
        settings.update(sampling)
    return {'schema_version': 'chemical-reactive-pose/1', 'material': source,
            'bond_changes': [{'atoms': list(atoms), 'before': 0, 'after': 1}],
            'sampling': settings}


def test_reverse_pair_order_uses_selected_fixed_and_mobile_atoms():
    source = material(reversed_order=True)
    spec = request(source, atoms=('F', 'C'), count=1,
                   sampling={'direction_count': 1, 'distances': [[2.03]], 'twists': [0.]})
    result = generate(spec)
    assert result['summary']['accepted'] == 1
    candidate = result['candidates'][0]
    xyz = np.asarray(candidate['coordinates'])
    assert np.linalg.norm(xyz[0] - xyz[1]) == pytest.approx(2.03)
    assert xyz[0, 0] < 0  # F is the smaller moving fragment in this atom order.
    assert candidate['material']['graph'] is None
    assert candidate['material']['identity'] is None
    assert candidate['material']['derivation']['reference_graph'] is not None
    assert candidate['material']['unknown_fields'] == sorted(candidate['material']['unknown_fields'])


def test_sampling_is_seeded_and_enumeration_summary_is_truthful():
    spec = request(material(), count=8)
    first, second = generate(spec), generate(spec)
    assert first == second
    assert first['summary']['attempted'] == 8
    assert first['summary']['enumeration_complete'] is False

    complete = generate(request(material(), count=12,
                                 sampling={'direction_count': 1, 'distances': [[2.0]], 'twists': [0.]}))
    assert complete['summary']['attempted'] == 1
    assert complete['summary']['enumeration_complete'] is True


def _multi_material():
    spec = {
        'schema_version': 'chemical-material-input/1', 'format': 'xyz',
        'text': ('7\nmultiple forming contacts\nC 0 0 0\nCl 1.8 0 0\nF 5 0 0\n'
                 'O 6.4 0 0\nH -.36 1.02 0\nH -.36 -.51 .883\nH -.36 -.51 -.883\n'),
        'graph': {'smiles': '[CH3:1][Cl:2].[F:3][O:4]', 'source': 'user', 'note': 'pose fixture'},
        'graph_to_input': list(range(7)), 'atom_ids': ['C', 'Cl', 'F', 'O', 'H1', 'H2', 'H3'],
        'charge': 0, 'multiplicity': 2, 'electronic_state': {'kind': 'ground'},
    }
    return build_material(spec, canonical(spec))[0]


def test_multi_contact_rigid_fit_accepts_consistent_targets_and_rejects_inconsistent_ones():
    source = _multi_material()
    base = {'schema_version': 'chemical-reactive-pose/1', 'material': source,
            'bond_changes': [{'atoms': ['C', 'F'], 'before': 0, 'after': 1},
                             {'atoms': ['C', 'O'], 'before': 0, 'after': 1}],
            'sampling': {'count': 1, 'seed': 0, 'direction_count': 1, 'twists': [0.]}}
    accepted = json.loads(json.dumps(base))
    accepted['sampling']['distances'] = [[2.0], [3.4]]
    result = generate(accepted)
    assert result['summary']['accepted'] == 1
    assert result['candidates'][0]['diagnostics']['transforms'][0]['pair_residual'] < 1e-8

    rejected = json.loads(json.dumps(base))
    rejected['sampling']['distances'] = [[2.0], [4.0]]
    result = generate(rejected)
    assert result['summary']['accepted'] == 0
    assert result['rejected'][0]['diagnostics']['reasons'] == ['multi_pair_rigid_fit_residual']


def test_run_writes_raw_xyz_digest_and_candidate_material(tmp_path):
    source = material()
    spec = request(source, count=1,
                   sampling={'direction_count': 1, 'distances': [[2.0]], 'twists': [0.]})
    input_path = tmp_path / 'input.json'
    output_dir = tmp_path / 'results'
    input_path.write_text(json.dumps(spec))
    result = run(input_path, output_dir)
    row = result['candidates'][0]
    xyz_path = output_dir / row['xyz']['path']
    assert row['xyz']['sha256'] == digest(xyz_path.read_bytes())
    assert json.loads((xyz_path.parent / 'material.json').read_text())['graph'] is None


def test_executor_declared_closure_runs_without_source_tree(tmp_path):
    descriptor = next(e for e in json.loads((SKILLS.parent / 'execution.json').read_text())['executors']
                      if e['id'] == 'chemical.reactive-pose')
    staged = tmp_path / 'stage'
    staged.mkdir()
    for path, expected in descriptor['resources'].items():
        raw = (SKILLS.parent / path).read_bytes()
        assert 'sha256:' + hashlib.sha256(raw).hexdigest() == expected
        target = staged / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
    spec = request(material(), count=1,
                   sampling={'direction_count': 1, 'distances': [[2.0]], 'twists': [0.]})
    (staged / 'input.json').write_text(json.dumps(spec))
    result = subprocess.run(
        [sys.executable, str(staged / descriptor['entry']), '--input', 'input.json', '--output-dir', 'results'],
        cwd=staged, env={**os.environ, 'PYTHONPATH': '', 'PYTHONDONTWRITEBYTECODE': '1'},
        capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    output = json.loads((staged / 'results/result.json').read_text())
    assert len(output['candidates']) == 1
    row = output['candidates'][0]
    assert (staged / 'results' / row['xyz']['path']).is_file()
    assert json.loads((staged / 'results/candidates' / row['id'] / 'material.json').read_text())['graph'] is None


def test_forming_bond_must_cross_reference_fragments():
    source = material()
    spec = request(source, atoms=('Cl', 'H1'), count=1)
    with pytest.raises(ValueError, match='separate reference fragments'):
        generate(spec)
