"""Reaction-site analysis emits auditable hypotheses for pose generation."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest
np = pytest.importorskip('numpy')

ROOT = Path(__file__).resolve().parents[2]
SKILLS = ROOT / 'skills' / 'chemical'
from tests.unit.chemical_paths import configure
configure()

from ensemble_material import canonical  # noqa: E402
from material import build_material  # noqa: E402
from reactive_sites import generate  # noqa: E402


def material():
    spec = {
        'schema_version': 'chemical-material-input/1', 'format': 'xyz',
        'text': ('6\nSN2 fixture\nC 0 0 0\nCl 1.8 0 0\nF 5 0 0\n'
                 'H -.36 1.02 0\nH -.36 -.51 .883\nH -.36 -.51 -.883\n'),
        'graph': {'smiles': '[CH3:1][Cl:2].[F-:3]', 'source': 'user', 'note': 'site fixture'},
        'graph_to_input': list(range(6)), 'atom_ids': ['C', 'Cl', 'F', 'H1', 'H2', 'H3'],
        'charge': -1, 'multiplicity': 1, 'electronic_state': {'kind': 'ground'},
    }
    return build_material(spec, canonical(spec))[0]


def spec(family='sn2'):
    return {
        'schema_version': 'chemical-reactive-sites/1', 'material': material(),
        'bond_changes': [{'atoms': ['C', 'F'], 'before': 0, 'after': 1},
                         {'atoms': ['C', 'Cl'], 'before': 1, 'after': 0}],
        'reaction_family': family,
    }


def test_sn2_site_exposes_roles_broken_bond_and_opposite_face():
    result = generate(spec())
    assert result['summary'] == {'forming_changes': 1, 'breaking_changes': 1,
                                 'sites': 1, 'truncated': False}
    site = result['sites'][0]
    assert site['fragment_roles']['fixed_atom'] == 'C'
    assert site['fragment_roles']['mobile_atom'] == 'F'
    assert site['reaction_center']['breaking_pairs'] == [['C', 'Cl']]
    primary, opposite = site['hypotheses']
    assert primary['direction_source'] == 'opposite_broken_bond'
    assert np.asarray(primary['direction']) == pytest.approx([-1., 0., 0.])
    assert np.asarray(opposite['direction']) == pytest.approx([1., 0., 0.])


def test_analysis_is_deterministic_and_does_not_claim_ts():
    first, second = generate(spec('generic')), generate(spec('generic'))
    assert first == second
    assert 'TS' in first['scope']
    assert first['limitations']


def test_unknown_or_inconsistent_changes_are_rejected():
    bad = spec(); bad['reaction_family'] = 'unknown'
    with pytest.raises(ValueError, match='unsupported reaction_family'):
        generate(bad)
    bad = spec(); bad['bond_changes'][0]['before'] = 1
    with pytest.raises(ValueError, match='bond change orders'):
        generate(bad)


def test_executor_declared_closure_runs_without_source_tree(tmp_path):
    descriptor = next(e for e in json.loads((SKILLS / 'execution.json').read_text())['executors']
                      if e['id'] == 'chemical.reactive-sites')
    staged = tmp_path / 'stage'; staged.mkdir()
    for path, expected in descriptor['resources'].items():
        raw = (SKILLS / path).read_bytes()
        assert 'sha256:' + hashlib.sha256(raw).hexdigest() == expected
        target = staged / path; target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(raw)
    (staged / 'input.json').write_text(json.dumps(spec()))
    result = subprocess.run(
        [sys.executable, str(staged / descriptor['entry']), '--input', 'input.json', '--output-dir', 'results'],
        cwd=staged, env={**os.environ, 'PYTHONPATH': '', 'PYTHONDONTWRITEBYTECODE': '1'},
        capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    output = json.loads((staged / 'results/result.json').read_text())
    assert output['sites'][0]['hypotheses'][0]['id'] == 'primary'
