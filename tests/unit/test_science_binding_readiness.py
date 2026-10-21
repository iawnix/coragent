"""Readiness is derived from descriptors, including third-party extensions."""
import os

import pytest

from research_agent.jobs.config_contract import load_job_config
from research_agent.application.environment_check import check_environments


def config():
    settings = load_job_config(os.environ['CORAGENT_JOB_CONFIG'])
    settings['targets']['local']['backends'] = {
        'analysis': settings['targets']['local']['backends']['validation']}
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
    row = report['local']['executors:external.biology@7']
    assert row['status'] == 'verified'
    assert row['environment_evidence']['observation']['python']['packages']['numpy']


def test_missing_configuration_is_reported_without_cancelling_capability():
    settings = config()
    settings['targets']['local']['backends'] = {}
    row = check_environments(settings, catalogs=extension())['local']['executors:external.biology@7']
    assert row == {'status': 'not_configured', 'backend': 'analysis'}


def test_python_wrapper_cannot_silently_use_a_native_or_duplicate_interpreter():
    settings = config()
    settings['targets']['local']['backends']['analysis'] = {'command': '/bin/true'}
    with pytest.raises(ValueError, match='python_binding_missing'):
        check_environments(settings, catalogs=extension(), probe=False)
    settings = config()
    settings['targets']['local']['backends']['analysis']['command'] = '/old/python'
    with pytest.raises(ValueError, match='execution_binding_command_mismatch'):
        check_environments(settings, catalogs=extension(), probe=False)


def test_static_validation_does_not_claim_execution_readiness():
    report = check_environments(config(), catalogs=extension(), probe=False)
    row = report['local']['executors:external.biology@7']
    assert row['status'] == 'configuration_validated' and row['environment_evidence'] is None


def test_bad_declared_dependency_prevents_readiness():
    entries = extension()
    entries[0]['executors'][0]['requirements']['packages']['numpy'] = '>=9999'
    with pytest.raises(ValueError, match='environment_dependency_(missing|version_mismatch)'):
        check_environments(config(), catalogs=entries)


def test_unregistered_native_binding_can_be_verified_without_claiming_a_method():
    settings = config()
    settings['targets']['local']['backends'] = {'native': {'command': '/bin/true'}}
    report = check_environments(settings, catalogs=[])
    row = report['local']['binding:native']
    assert row['status'] == 'verified'
    assert row['environment_evidence']['observation']['python'] is None
