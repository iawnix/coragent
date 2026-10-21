import pytest

from research_agent.jobs.config_contract import resolve_target, validate_job_config, resolve_selection, bound_target


def settings(default="tri"):
    return validate_job_config({"execution": {
        "default_target": default,
        "targets": {
            "local": {"type": "local", "driver": "systemd", "scheduler": "none", "location": "controller",
                       "aliases": ["direct"]},
            "tri": {"type": "local", "driver": "external", "transport": "local", "work_root": "/shared/jobs",
                     "handler": ["/bin/true"], "scheduler": "tri", "location": "controller",
                     "aliases": ["local-tri", "local-tri-queue"]},
            "slurm": {"type": "remote", "driver": "external", "transport": "ssh", "ssh_host": "login",
                       "work_root": "/shared/jobs", "handler": ["/bin/true"], "scheduler": "slurm",
                       "location": "cluster"},
        },
    }})


def test_missing_target_uses_configured_default():
    config = settings()
    assert resolve_target(config) == "tri"
    assert config["default_target"] == "tri"
    assert config["targets"]["tri"]["scheduler"] == "tri"
    assert resolve_target(validate_job_config({"execution": {
        "default_target": "local", "targets": {"local": {"type": "local", "driver": "systemd"}}
    }})) == "local"


def test_legacy_environment_configuration_is_rejected():
    with pytest.raises(ValueError, match="execution table"):
        validate_job_config({"default_environment": "local", "environments": {"local": {"kind": "local"}}})


@pytest.mark.parametrize("requested, expected", [
    ("tri", "tri"), ("TRI", "tri"), ("local-tri", "tri"), ("local-tri-queue", "tri"), ("slurm", "slurm")
])
def test_target_resolves_by_name_scheduler_or_alias(requested, expected):
    assert resolve_target(settings(), requested) == expected


def test_unknown_and_ambiguous_scheduler_fail_closed():
    config = settings()
    with pytest.raises(ValueError, match="execution_target_not_configured"):
        resolve_target(config, "pbs")
    config["targets"]["tri-2"] = dict(config["targets"]["tri"])
    config["targets"]["tri-2"]["aliases"] = ["queue"]
    config["targets"]["tri"]["aliases"] = ["queue"]
    with pytest.raises(ValueError, match="execution_target_ambiguous"):
        resolve_target(config, "queue")


def test_explicit_queue_is_not_direct_local_and_source_can_disambiguate():
    config = settings()
    assert resolve_selection(config, source_text="在local（Tri队列）计算资源上完整计算任务")['target'] == 'tri'
    with pytest.raises(ValueError, match='execution_target_not_configured'):
        resolve_selection(config, 'local', source_text="在local（Tri队列）计算资源上完整计算任务")
    with pytest.raises(ValueError, match='execution_intent_ambiguous'):
        resolve_selection(config, source_text="不要用 TRI，改用 Slurm")
    assert resolve_selection(config, source_text="改用 Slurm")['target'] == 'slurm'
    # Substrings are not scheduler names.
    assert resolve_selection(settings('local'), source_text="compare trial geometries")['target'] == 'local'


def test_scheduler_and_location_constraints_are_conjunctive():
    config = settings()
    assert resolve_selection(config, scheduler='tri', location='controller')['target'] == 'tri'
    with pytest.raises(ValueError, match='not_configured'):
        resolve_selection(config, scheduler='tri', location='cluster')
    config['targets']['second'] = dict(config['targets']['slurm'])
    with pytest.raises(ValueError, match='ambiguous'):
        resolve_selection(config, scheduler='slurm')


def test_preparation_inherits_pinned_target_and_detects_route_drift(monkeypatch):
    import json
    from research_agent.application.executors import preparation_target
    config = settings(); selection = resolve_selection(config)
    monkeypatch.setenv('CORAGENT_TASK_EXECUTION', json.dumps(selection))
    config['default_target'] = 'slurm'
    assert preparation_target(config) == 'tri'
    with pytest.raises(ValueError, match='mismatch'):
        preparation_target(config, 'slurm')
    config['targets']['tri']['submission'] = {'resources': {'cpus': 24}}
    assert bound_target(config, context=selection) == 'tri'
    config['targets']['tri']['handler'] = ['/different/queue.py']
    with pytest.raises(ValueError, match='execution_target_changed'):
        preparation_target(config)
    del config['targets']['tri']
    with pytest.raises(ValueError, match='not_configured'):
        preparation_target(config)
