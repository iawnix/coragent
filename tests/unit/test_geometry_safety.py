import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'domains/chemical/skills/_shared'))
sys.path.insert(0, str(ROOT / 'domains/chemical/skills/gaussian/scripts'))

from geometry_safety import assess, assess_gaussian_input  # noqa: E402
from input_job import inspect_input  # noqa: E402


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
