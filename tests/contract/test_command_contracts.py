"""Handwritten contract cases independently exercise generated boundaries."""
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from research_agent.application.api import COMMAND_DEFINITIONS, CommandError, validate_command_params

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize('command,params', [
    ('research_create', {'goal': 'Investigate the reaction', 'session_id': 'session-fixture'}),
    ('research_observe', {'read_basis': 'read_' + 'a' * 64, 'session_id': 'session-fixture'}),
    ('research_update', {'node_id': 'node_' + 'a' * 32, 'note': 'Observation', 'assessment_ref': None}),
    ('job_start', {'command': ['/bin/true'], 'environment': {'OMP_NUM_THREADS': '2'}}),
    ('artifact_read', {'artifact_id': 'art_1', 'offset': 0, 'limit': 4096}),
])
def test_application_contract_accepts_transport_values(command, params):
    validate_command_params(command, params)


@pytest.mark.parametrize('command,params', [
    ('research_create', {'goal': 'Investigate', 'unknown': True}),
    ('research_update', {'node_id': 'node_' + 'a' * 32}),
    ('research_search', {'origin': 'untrusted-origin'}),
    ('job_start', {'command': ['/bin/true'], 'environment': {'OMP_NUM_THREADS': 2}}),
    ('artifact_read', {'artifact_id': 'art_1', 'limit': '4096'}),
])
def test_application_contract_rejects_malformed_parameters(command, params):
    with pytest.raises(CommandError):
        validate_command_params(command, params)


def test_transport_context_is_not_a_public_command_parameter():
    params = {'goal': 'Investigate', 'workspace_root': '/fixture/workspace'}
    with pytest.raises(CommandError, match='unsupported fields'):
        validate_command_params('research_create', params)
    validate_command_params('research_create', params, transport_fields=('workspace_root',))


def test_model_schemas_do_not_accept_application_identity_fields():
    shared = json.loads((ROOT / 'contracts/commands/shared.json').read_text())['tools']
    for key, schema in shared.items():
        assert not {'session_id', 'workspace_id', 'principal', 'read_basis', 'producer_token'} & schema['properties'].keys(), key
    schema = shared['research_create']
    validator = Draft202012Validator(schema)
    assert not list(validator.iter_errors({'goal': 'Investigate'}))
    assert list(validator.iter_errors({'goal': 'Investigate', 'session_id': 'forged'}))


def test_generated_catalogs_and_examples_agree():
    node = json.loads((ROOT / 'apps/agent/tools/command-catalog.json').read_text())
    assert {row['id']: row for row in node['commands']} == COMMAND_DEFINITIONS
    fixtures = json.loads((ROOT / 'tests/fixtures/contracts/command-fixtures.json').read_text())
    assert {case['command'] for case in fixtures['cases']} == set(COMMAND_DEFINITIONS)
    for case in fixtures['cases']:
        validate_command_params(case['command'], case['params'])


def test_model_tool_constraints_survive_generation():
    schema = json.loads((ROOT / 'contracts/commands/shared.json').read_text())['tools']['job_start']
    validator = Draft202012Validator(schema)
    valid = {'node_id': 'node_' + 'a' * 32, 'request_file': 'reviewed.json', 'request_sha256': 'a' * 64}
    assert not list(validator.iter_errors(valid))
    assert list(validator.iter_errors({'node_id': valid['node_id'], 'request_file': 'reviewed.json'}))
    assert list(validator.iter_errors({**valid, 'repeat': {'predecessor_job_id': 'job_previous'}}))


@pytest.mark.parametrize('name', ['research.read', 'research.create', 'job.start', 'job.collect', 'artifact.read', 'research_unknown', '__proto__', None, []])
def test_retired_or_unknown_names_fail_before_dispatch(tmp_path, name):
    from research_agent.application.api import execute
    with pytest.raises(CommandError, match='unsupported command'):
        execute(name, tmp_path, {})
    assert not list(tmp_path.iterdir())


def test_canonical_retry_reuses_durable_receipt_without_alias_dispatch(tmp_path):
    from research_agent.application.api import execute
    from research_agent.research.workspace import initialize_workspace, admit_research_workspace
    from research_agent.research import nodes
    from research_agent.foundation.transactions import TransactionCoordinator
    initialize_workspace(tmp_path, 'command-identity', 'research')
    admit_research_workspace(tmp_path)
    request = {'goal': 'Preserve this question across command renaming', 'session_id': 'fixture', 'request_id': 'original-create'}
    original = nodes.create(tmp_path, {**request, '_reference_details': {}})
    coordinator = TransactionCoordinator(tmp_path)
    before = coordinator.get(request['request_id'])
    assert before['operation'] == 'research.create'  # immutable storage label, not an accepted route
    assert execute('research_create', tmp_path, request) == original
    assert coordinator.get(request['request_id']) == before
    assert execute('research_search', tmp_path, {'kind': 'node'})['total'] == 1
    with pytest.raises(CommandError, match='unsupported command'):
        execute('research.create', tmp_path, request)
