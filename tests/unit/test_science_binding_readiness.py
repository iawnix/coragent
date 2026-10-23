"""Readiness is derived from descriptors, including third-party extensions."""
import os

import pytest

from research_agent.jobs.config_contract import load_job_config
from research_agent.application.environment_check import check_environments
from tests.support.platforms import execution_config


def config():
    settings = load_job_config(os.environ['CORAGENT_JOB_CONFIG'])
    settings['targets']['local/main']['backends'] = {
        'analysis': settings['targets']['local/main']['backends']['validation']}
    return settings


def extension():
    return [{'executors': [{'id': 'external.biology', 'version': '7', 'backend': 'analysis',
        'runtime': 'python', 'argv': ['{entry}', '{args}'],
        'requirements': {'python': '>=3.11', 'packages': {'numpy': '>=2,<3'}, 'imports': ['numpy']}}]}]


def test_new_domain_uses_declared_backend_and_actual_target_probe():
    try:
        report = check_environments(config(), catalogs=extension())
    except ValueError as exc:
        if str(exc) == 'environment_dependency_missing':
            pytest.skip('fixture Python environment does not include NumPy')
        raise
    row = report['local/main']['executors:external.biology@7']
    assert row['status'] == 'verified'
    assert row['environment_evidence']['observation']['python']['packages']['numpy']


def test_missing_configuration_is_reported_without_cancelling_capability():
    settings = config()
    settings['targets']['local/main']['backends'] = {}
    row = check_environments(settings, catalogs=extension())['local/main']['executors:external.biology@7']
    assert row == {'status': 'not_configured', 'backend': 'analysis'}


def test_python_wrapper_cannot_silently_use_a_native_or_duplicate_interpreter():
    settings = config()
    settings['targets']['local/main']['backends']['analysis'] = {'command': '/bin/true'}
    with pytest.raises(ValueError, match='python_binding_missing'):
        check_environments(settings, catalogs=extension(), probe=False)
    settings = config()
    settings['targets']['local/main']['backends']['analysis']['command'] = '/old/python'
    with pytest.raises(ValueError, match='execution_binding_command_mismatch'):
        check_environments(settings, catalogs=extension(), probe=False)


def test_static_validation_does_not_claim_execution_readiness():
    report = check_environments(config(), catalogs=extension(), probe=False)
    row = report['local/main']['executors:external.biology@7']
    assert row['status'] == 'configuration_validated' and row['environment_evidence'] is None


def test_bad_declared_dependency_prevents_readiness():
    entries = extension()
    entries[0]['executors'][0]['requirements']['packages']['numpy'] = '>=9999'
    with pytest.raises(ValueError, match='environment_dependency_(missing|version_mismatch)'):
        check_environments(config(), catalogs=entries)


def test_unregistered_native_binding_can_be_verified_without_claiming_a_method():
    settings = config()
    settings['targets']['local/main']['backends'] = {'native': {'command': '/bin/true'}}
    report = check_environments(settings, catalogs=[])
    row = report['local/main']['binding:native']
    assert row['status'] == 'verified'
    assert row['environment_evidence']['observation']['python'] is None


def native_platforms():
    return {'execution': execution_config('first', {name: {
        'transport': 'local', 'executor': 'qrun', 'work_root': '/fixture/' + name,
        'bindings': {'native': {'command': '/bin/true'}}}
        for name in ('first', 'second', 'third')})}


@pytest.mark.parametrize('targets,expected', [
    (None, ['first/main', 'second/main', 'third/main']),
    (['second/main'], ['second/main']),
    ([], []),
])
def test_environment_check_probes_only_selected_targets(monkeypatch, targets, expected):
    from research_agent.application import environment_check
    calls = []
    def probe(settings, selected, requirements):
        calls.append(selected['environment'])
        return {'target': selected['environment']}
    monkeypatch.setattr(environment_check, 'probe_binding', probe)
    report = check_environments(native_platforms(), catalogs=[], targets=targets)
    assert calls == expected
    assert list(report) == expected
    assert all(row['binding:native']['status'] == 'verified' for row in report.values())


def test_target_filter_preserves_configuration_and_catalog_validation():
    document = native_platforms()
    document['execution']['platforms']['third']['transport'] = 'invalid'
    with pytest.raises(ValueError, match='platform requires local or ssh transport'):
        check_environments(document, catalogs=[], targets=['first/main'])
    with pytest.raises(ValueError, match='execution_environment_not_configured'):
        check_environments(native_platforms(), catalogs=[], targets=['missing/main'])
    catalog = [{'executors': [{'id': 'native.recipe', 'version': '1', 'backend': 'native',
                              'runtime': 'native', 'argv': ['{entry}']}]}]
    with pytest.raises(ValueError, match='execution_binding_command_mismatch'):
        check_environments(native_platforms(), catalogs=catalog, targets=['first/main'], probe=False)
