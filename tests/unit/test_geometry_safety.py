import json
import math
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'skills/chemical/_shared'))
sys.path.insert(0, str(ROOT / 'skills/chemical/gaussian/scripts'))

from geometry_safety import assess, assess_gaussian_input  # noqa: E402
from gaussian_input import inspect_input  # noqa: E402


def test_reaction_center_can_be_non_equilibrium_but_cannot_collapse():
    allowed = assess(['C', 'C'], [[0, 0, 0], [1.8, 0, 0]], reaction_pairs=[(0, 1)], profile='ts_candidate')
    assert allowed['verdict'] == 'safe'
    assert allowed['checks']['reaction_center'] == 'warning'

    collapsed = assess(['C', 'C'], [[0, 0, 0], [0.1539, 0, 0]], reaction_pairs=[(0, 1)], profile='ts_candidate')
    assert collapsed['verdict'] == 'unsafe'
    assert collapsed['hard_failures'][0]['kind'] == 'catastrophic_overlap'


def test_nonreaction_short_contact_is_hard_failure():
    result = assess(['C', 'C'], [[0, 0, 0], [0.9, 0, 0]], profile='ts_candidate')
    assert result['verdict'] == 'unsafe'
    assert any(row['kind'] == 'nonreaction_short_contact' for row in result['hard_failures'])


def test_hydrogen_contacts_use_connectivity_without_rejecting_h2_or_reaction_pairs():
    xyz = [[0, 0, 0], [.758, 0, 0]]
    assert assess(['H', 'H'], xyz, bonded_pairs=[])['verdict'] == 'unsafe'
    assert assess(['H', 'H'], xyz, fragment_groups=[[0], [1]])['verdict'] == 'unsafe'
    assert assess(['H', 'H'], xyz, bonded_pairs=[(0, 1)])['verdict'] == 'safe'
    assert assess(['H', 'H'], xyz, bonded_pairs=[], reaction_pairs=[(0, 1)])['verdict'] == 'safe'
    unknown = assess(['H', 'H'], xyz)
    assert unknown['verdict'] == 'safe'
    assert any(w['kind'] == 'hydrogen_contact_needs_connectivity' for w in unknown['warnings'])
    assert assess(['H', 'H'], [[0, 0, 0], [.58, 0, 0]])['verdict'] == 'unsafe'
    assert assess(['H', 'H'], [[0, 0, 0], [.1, 0, 0]], reaction_pairs=[(0, 1)])['verdict'] == 'unsafe'


def test_nonreaction_bond_changes_are_reported_with_reference_distances():
    reference = [[0, 0, 0], [1.1, 0, 0]]
    xyz = [[0, 0, 0], [1.6, 0, 0]]
    result = assess(['C', 'H'], xyz, bonded_pairs=[(0, 1)], reference_coordinates=reference)
    assert result['verdict'] == 'safe'
    assert result['checks']['bond_lengths'] == 'warning'
    pair = next(w for w in result['warnings'] if w['kind'] == 'nonreaction_bond_length_change')['pairs'][0]
    assert pair['delta_angstrom'] == pytest.approx(.5)
    reacting = assess(['C', 'H'], xyz, bonded_pairs=[(0, 1)], reaction_pairs=[(0, 1)], reference_coordinates=reference)
    assert reacting['checks']['bond_lengths'] == 'pass'


def test_bent_fragment_straightening_is_reported_even_for_a_breaking_bond():
    angle = math.radians(105.6)
    reference = [[1.31, 0, 0], [0, 0, 0], [.98 * math.cos(angle), .98 * math.sin(angle), 0]]
    linear = [[1.31, 0, 0], [0, 0, 0], [-.98, 0, 0]]
    result = assess(['O', 'O', 'H'], linear, bonded_pairs=[(0, 1), (1, 2)],
                    reaction_pairs=[(1, 2)], reference_coordinates=reference, profile='ts_candidate')
    assert result['verdict'] == 'safe'  # A diagnostic, not a stationary-point verdict.
    assert result['checks']['bond_angles'] == 'warning'
    observed = next(w for w in result['warnings'] if w['kind'] == 'bond_angle_change')['angles'][0]
    assert observed['atoms'] == [0, 1, 2]
    assert observed['angle_degrees'] == pytest.approx(180.)
    assert observed['reference_angle_degrees'] == pytest.approx(105.6)
    assert observed['reaction_pairs'] == [[1, 2]]


def test_reference_angle_check_preserves_linear_molecules_and_rigid_poses():
    linear = [[-1.16, 0, 0], [0, 0, 0], [1.16, 0, 0]]
    rotated = [[4, 2 + row[0], 3] for row in linear]
    result = assess(['O', 'C', 'O'], rotated, bonded_pairs=[(0, 1), (1, 2)],
                    reference_coordinates=linear)
    assert result['verdict'] == 'safe'
    assert result['checks']['bond_angles'] == 'pass'
    assert not any(w['kind'] == 'bond_angle_change' for w in result['warnings'])
    for metadata in ({}, {'bonded_pairs': [(0, 1), (1, 2)]}, {'reference_coordinates': linear}):
        assert assess(['O', 'C', 'O'], linear, **metadata)['checks']['bond_angles'] == 'not_assessed'


@pytest.mark.parametrize('coordinates,kind', [([[float('nan'), 0, 0]], 'nonfinite_coordinates'),
                                             ([[float('inf'), 0, 0]], 'nonfinite_coordinates'),
                                             ([[10001, 0, 0]], 'coordinates_out_of_bounds'),
                                             (['000'], 'atom_coordinate_shape'),
                                             ([0, 0, 0], 'atom_coordinate_shape'),
                                             ([[0, 0]], 'atom_coordinate_shape')])
def test_invalid_coordinate_arrays_are_rejected(coordinates, kind):
    report = assess(['H'], coordinates)
    assert report['verdict'] == 'unsafe'
    assert report['hard_failures'][0]['kind'] == kind


def test_scientific_array_callers_share_the_pure_geometry_checker():
    import numpy as np
    result = assess(['H', 'H'], np.array([[0, 0, 0], [.74, 0, 0]]),
                    bonded_pairs=[(np.int64(0), np.int64(1))],
                    reference_coordinates=np.array([[0, 0, 0], [.75, 0, 0]]))
    assert result['verdict'] == 'safe'
    with pytest.raises(ValueError, match='pair'):
        assess(['H', 'H'], [[0, 0, 0], [.74, 0, 0]], reaction_pairs=[(np.bool_(False), 1)])


@pytest.mark.parametrize('pairs', [[(0, 2)], [(0, 0)], [(False, 1)], [[0]]])
def test_invalid_pair_metadata_is_not_silently_ignored(pairs):
    with pytest.raises(ValueError, match='pair'):
        assess(['H', 'H'], [[0, 0, 0], [1, 0, 0]], reaction_pairs=pairs)


def test_gaussian_blocks_are_assessed_independently():
    text = '''%chk=test.chk
%nprocshared=1
%mem=256MB
#p HF/STO-3G Opt=(QST2)

reactant

0 1
C 0 0 0
C 1.8 0 0

product

0 1
C 0 0 0
C 0.1539 0 0

'''
    reports = assess_gaussian_input(text, profile='ts_candidate')
    assert len(reports) == 2
    assert reports[0]['verdict'] == 'safe'
    assert reports[1]['verdict'] == 'unsafe'


def test_direct_gaussian_input_rejects_t001_style_overlap(tmp_path):
    path = tmp_path / 'input.gjf'
    path.write_text('''%chk=bad.chk
%nprocshared=1
%mem=256MB
#p HF/STO-3G Opt=(TS)\n
bad seed

0 1
C 0 0 0
C 0.1539 0 0

''')
    with pytest.raises(ValueError, match='geometry safety failed'):
        inspect_input(path, 'HF', 'STO-3G', 0, 1, 1, 256)
