"""Keep development answers and reaction-specific shortcuts out of distribution."""
import copy
import json
from pathlib import Path

import pytest

from scripts.package_inventory import RETIRED_RUNTIME_PATHS, release_files
from tests.unit.test_chemical_path_execution import SPEC, helper, irc_helper
from tests.unit.test_chemical_geometry_regressions import REACTANTS, PRODUCT
from reaction_checks import reaction
from path_specification import select_strategy


ROOT = Path(__file__).resolve().parents[2]


def test_release_contains_no_development_answers_or_retired_reaction_tools():
    files = release_files()
    for name in files:
        assert 'tests' not in Path(name).parts
        assert 'local_debug' not in Path(name).parts
        assert not any(name.startswith(p) if p.endswith('/') else name == p
                       for p in RETIRED_RUNTIME_PATHS)
        path = ROOT / name
        if path.suffix in {'.md', '.py', '.json', '.mjs', '.toml', '.txt'}:
            text = path.read_text()
            assert REACTANTS not in text and PRODUCT not in text, name
    registry = json.loads((ROOT / 'domains/chemical/execution.json').read_text())
    retired = {'chemical.reaction_mapping', 'chemical.gaussian_saddle',
               'chemical.gaussian_irc_connectivity', 'chemical.diels_alder_path'}
    for group in ('executors', 'validators', 'acceptance_profiles'):
        assert not retired.intersection(e['id'] for e in registry[group])


@pytest.mark.parametrize('operation', ['reaction', 'candidate', 'irc'])
@pytest.mark.parametrize('kind', ['diels_alder', 'named_reaction'])
def test_reaction_names_do_not_supply_a_hidden_transformation(tmp_path, operation, kind):
    spec = copy.deepcopy(SPEC)
    spec['transformation'] = {'kind': kind}
    with pytest.raises(ValueError, match='explicit'):
        if operation == 'reaction':
            reaction(spec['mapped_smiles'], spec['transformation'])
        elif operation == 'irc':
            irc_helper.validate_spec(spec)
        else:
            source = tmp_path / 'spec.json'
            source.write_text(json.dumps(spec))
            helper.prepare_candidates(source, tmp_path / 'candidates')
    assert not (tmp_path / 'candidates').exists()


def test_geometry_strategy_depends_on_supplied_geometry_and_not_reaction_names():
    assert select_strategy(SPEC) == 'mapped_endpoints'
    assert select_strategy({**SPEC, 'endpoints': {}}) == 'provided_endpoints'
    with pytest.raises(ValueError, match='candidate_strategy'):
        select_strategy({**SPEC, 'candidate_strategy': 'diels_alder'})
