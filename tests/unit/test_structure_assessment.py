import copy
import json
import sys
from pathlib import Path

import pytest
pytest.importorskip('numpy')

ROOT = Path(__file__).resolve().parents[2]
SKILLS = ROOT / 'skills/chemical'
from tests.unit.chemical_paths import configure
configure()

from cognition import cognize  # noqa: E402
from material import build_material  # noqa: E402


def material(distance=1.8):
    spec = {
        'schema_version': 'chemical-material-input/1', 'format': 'xyz',
        'text': f'6\nC-Cl candidate\nC 0 0 0\nCl {distance} 0 0\nF 5 0 0\n'
                'H -.36 1.02 0\nH -.36 -.51 .883\nH -.36 -.51 -.883\n',
        'graph': {'smiles': '[CH3:1][Cl:2].[F-:3]', 'source': 'user', 'note': 'test graph'},
        'graph_to_input': list(range(6)), 'atom_ids': ['a', 'b', 'f', 'h1', 'h2', 'h3'], 'charge': -1,
        'multiplicity': 1, 'electronic_state': {'kind': 'ground'},
        'arrangement': 'separate_reactants',
    }
    return build_material(spec, 'sha256:' + 'a' * 64)[0]


def context(**updates):
    value = {
        'schema_version': 'chemical-structure-context/1',
        'role_hint': 'ts_candidate', 'reaction_center': ['a', 'b'],
        'bond_changes': [{'atoms': ['a', 'b'], 'before': 1, 'after': 0,
                          'note': 'breaking candidate'}],
        'reference_material': None, 'notes': 'fixture hypothesis',
    }
    value.update(updates)
    return value


def test_cognition_keeps_non_equilibrium_candidate_as_observation():
    result = cognize(material(), context())
    assert result['status'] == 'assessed'
    assert result['role_assessment'] == {'role': 'ts_candidate', 'basis': 'declared'}
    row = result['reaction_center']['bond_changes'][0]
    assert row['graph_consistency'] == 'before_order_matches_graph'
    assert row['observation']['relation'] == 'normal_like'
    assert result['geometry_observations']['local_angles'][0]['status'] == 'observed_only'
    assert 'geometry_safety_has_hard_failure' not in result['uncertainties']
    assert result['scope'].startswith('Structural observations')


def test_cognition_reports_overlap_without_calling_it_a_ts_failure():
    result = cognize(material(.1539), context())
    assert result['status'] == 'partial'
    assert result['geometry_observations']['safety']['verdict'] == 'unsafe'
    assert result['reaction_center']['bond_changes'][0]['observation']['relation'] == 'collapsed'
    assert any(row['skill'] == 'geometry-preflight' for row in result['follow_up'])


def test_cognition_without_context_preserves_uncertainty():
    result = cognize(material(), {'schema_version': 'chemical-structure-context/1'})
    assert result['status'] == 'partial'
    assert result['role_assessment']['basis'] == 'unresolved'
    assert 'reaction_center_not_declared' in result['uncertainties']
    assert 'structure_role_not_declared' in result['uncertainties']
    assert any(row['skill'] == 'reaction-investigation' for row in result['follow_up'])


def test_reference_comparison_requires_same_atom_identity_and_reports_change():
    current = material(1.8)
    reference = material(3.0)
    result = cognize(current, context(reference_material=reference))
    assert result['comparison']['status'] == 'assessed'
    delta = next(row for row in result['comparison']['pair_distance_deltas'] if row['atoms'] == ['a', 'b'])
    assert delta['distance_delta_angstrom'] == pytest.approx(-1.2)
    bad = copy.deepcopy(reference)
    bad['graph'] = None
    bad['atoms'][0]['atom_id'] = 'x'
    bad['atom_order']['input_atom_ids'][0] = 'x'
    bad['atom_order']['output_atom_ids'][0] = 'x'
    with pytest.raises(ValueError, match='identical atom IDs'):
        cognize(current, context(reference_material=bad))


def test_context_rejects_duplicate_or_unknown_reaction_atoms():
    with pytest.raises(ValueError, match='distinct known atom IDs'):
        cognize(material(), context(reaction_center=['a', 'a']))
    with pytest.raises(ValueError, match='known atom IDs'):
        cognize(material(), context(bond_changes=[{'atoms': ['a', 'missing'], 'before': 0, 'after': 1}]))
