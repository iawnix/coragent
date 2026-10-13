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
