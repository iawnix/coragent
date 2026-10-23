import copy
import pytest

from research_agent.jobs.config_contract import (
    validate_job_config, resolve_target, resolve_selection, bound_target,
    configuration_document, resolve_submission, target_identity,
)


def document():
    return {'execution': {'schema_version': 2, 'default_platform': 'FEDCluster', 'platforms': {
        'FEDCluster': {'transport': 'local', 'aliases': ['fed'], 'default_scheduler': 'tri',
            'storage': {'work_root': '/shared/jobs', 'scratch_root': '/scratch'},
            'bindings': {'xtb': {'command': '/soft/xtb'}},
            'submission': {'resources': {'cpus': 2, 'memory_mb': 2048}},
            'schedulers': {'tri': {'executor': 'tri', 'handler': ['/bin/true']},
                'qrun': {'executor': 'qrun', 'submission': {'resources': {'cpus': 4}},
                    'limits': {'cpus': 8, 'memory_mb': 4096}}}},
        'Com30': {'transport': 'ssh', 'ssh_host': 'agent.com30', 'default_scheduler': 'qrun',
            'storage': {'work_root': '/home/agent/soft/Qrun/jobs'},
            'schedulers': {'qrun': {'executor': 'qrun'}}},
        '1WCluster': {'transport': 'ssh', 'ssh_host': 'agent.1w', 'enabled': False},
    }}}


def test_platform_entry_resolution_has_no_composite_user_label():
    settings = validate_job_config(document())
    assert resolve_target(settings) == 'FEDCluster/tri'
    assert resolve_target(settings, {'platform': 'FED'}) == 'FEDCluster/tri'
    assert resolve_target(settings, {'platform': 'Com30'}, scheduler='Qrun') == 'Com30/qrun'
    assert resolve_selection(settings, {'platform': 'Com30'})['target'] == {
        'platform': 'Com30', 'scheduler_entry': 'qrun'}
    with pytest.raises(ValueError):
        resolve_target(settings, 'com30_qrun')
    with pytest.raises(ValueError, match='unavailable'):
        resolve_target(settings, {'platform': '1WCluster'})


def test_unknown_legacy_configuration_is_not_a_second_protocol():
    with pytest.raises(ValueError, match='unsupported'):
        validate_job_config({'execution': {'default_target': 'local', 'targets': {}}})


def test_entry_inheritance_and_limits():
    settings = validate_job_config(document())
    tri, qrun = settings['targets']['FEDCluster/tri'], settings['targets']['FEDCluster/qrun']
    assert tri['work_root'] == qrun['work_root'] == '/shared/jobs'
    assert tri['backends'] == qrun['backends'] == {'xtb': {'command': '/soft/xtb'}}
    assert resolve_submission(settings, 'FEDCluster/qrun')['resources'] == {'cpus': 4, 'memory_mb': 2048}
    with pytest.raises(ValueError, match='limit_exceeded'):
        resolve_submission(settings, 'FEDCluster/qrun', requested={'resources': {'cpus': 9}})


def test_platform_alias_collision_and_entry_connection_override_are_rejected():
    raw = document(); raw['execution']['platforms']['Com30']['aliases'] = ['FED']
    with pytest.raises(ValueError, match='ambiguous'):
        validate_job_config(raw)
    raw = document(); raw['execution']['platforms']['Com30']['schedulers']['qrun']['ssh_host'] = 'elsewhere'
    with pytest.raises(ValueError, match='unsupported'):
        validate_job_config(raw)


def test_duplicate_executor_requires_matching_default_or_explicit_entry():
    raw = document(); entries = raw['execution']['platforms']['FEDCluster']['schedulers']
    entries['cpu'] = {'executor': 'slurm', 'handler': ['/bin/true']}
    entries['gpu'] = {'executor': 'slurm', 'handler': ['/bin/true']}
    settings = validate_job_config(raw)
    with pytest.raises(ValueError, match='ambiguous'):
        resolve_target(settings, {'platform': 'FEDCluster'}, scheduler='slurm')
    assert resolve_target(settings, {'platform': 'FEDCluster', 'scheduler_entry': 'gpu'}, scheduler='slurm') == 'FEDCluster/gpu'


def test_binding_survives_default_change_but_detects_route_change():
    raw = document(); settings = validate_job_config(raw)
    selection = resolve_selection(settings, {'platform': 'Com30'})
    context = {'selection': selection}
    raw['execution']['default_platform'] = 'Com30'
    updated = validate_job_config(raw)
    assert bound_target(updated, context=context) == 'Com30/qrun'
    with pytest.raises(ValueError, match='mismatch'):
        bound_target(updated, {'platform': 'FEDCluster'}, context=context)
    raw['execution']['platforms']['Com30']['ssh_host'] = 'changed'
    with pytest.raises(ValueError, match='changed'):
        bound_target(validate_job_config(raw), context=context)


def test_installer_publication_preserves_shared_values_and_entry_changes():
    settings = validate_job_config(document())
    candidate = copy.deepcopy(settings)
    candidate['targets']['Com30/qrun']['handler'] = ['/installed/qrun', 'handler']
    published = configuration_document(candidate)
    assert 'targets' not in published['execution']
    assert published['execution']['platforms']['FEDCluster']['bindings'] == {'xtb': {'command': '/soft/xtb'}}
    assert validate_job_config(published)['targets']['Com30/qrun']['handler'] == ['/installed/qrun', 'handler']


def test_source_intent_rejects_executor_contradiction():
    settings = validate_job_config(document())
    with pytest.raises(ValueError, match='conflict'):
        resolve_selection(settings, {'platform': 'Com30'}, scheduler='tri', source_text='用 Qrun')
    assert resolve_selection(settings, {'platform': 'FEDCluster'}, source_text='用 Tri')['target'] == target_identity('FEDCluster/tri')


def test_unconfigured_scheduler_in_source_does_not_silently_use_default():
    with pytest.raises(ValueError, match='scheduler_ambiguous_or_missing'):
        resolve_selection(validate_job_config(document()), {'platform': 'Com30'}, source_text='Use PBS')


def test_discovery_explains_shared_and_overridden_values_without_credentials():
    from research_agent.jobs.config_contract import platform_catalog
    raw = document()
    entry = raw['execution']['platforms']['FEDCluster']['schedulers']['qrun']
    entry.update(bindings={'xtb': {'command': '/alternate/xtb'}},
                 storage={'work_root': '/alternate/jobs'}, handler_environment={'TOKEN': 'private-value'})
    catalog = platform_catalog(validate_job_config(raw))
    local = catalog['platforms']['FEDCluster']['schedulers']
    assert local['tri']['sources']['bindings']['xtb'] == 'platform'
    assert local['qrun']['sources']['bindings']['xtb'] == 'scheduler_entry'
    assert local['qrun']['sources']['storage']['scratch_root'] == 'platform'
    assert local['qrun']['storage']['work_root'] == '/alternate/jobs'
    assert 'private-value' not in str(catalog)


def test_opaque_pbs_select_cannot_bypass_entry_resource_limits():
    raw = document()
    entry = raw['execution']['platforms']['FEDCluster']['schedulers']['tri']
    entry.update(executor='pbs', limits={'cpus': 4})
    raw['execution']['platforms']['FEDCluster'].pop('submission')
    with pytest.raises(ValueError, match='limit_unverifiable'):
        resolve_submission(validate_job_config(raw), 'FEDCluster/tri',
                           requested={'resources': {'select': '1:ncpus=20'}})
