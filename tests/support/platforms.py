"""Build named-platform fixtures from the adapters under test."""
from copy import deepcopy


def execution_config(default, adapters):
    platforms = {}
    for name, value in adapters.items():
        adapter = deepcopy(value)
        platform = {'default_scheduler': 'main'}
        for field in ('transport', 'ssh_host', 'ssh_config', 'aliases', 'connect_timeout_seconds',
                      'command_timeout_seconds', 'transfer_timeout_seconds', 'bindings', 'python'):
            if field in adapter:
                platform[field] = adapter.pop(field)
        platform['storage'] = {key: adapter.pop(key) for key in ('work_root', 'scratch_root', 'file_mode') if key in adapter}
        adapter.pop('location', None)
        platform['schedulers'] = {'main': adapter}
        platforms[name] = platform
    return {'schema_version': 2, 'default_platform': default, 'platforms': platforms}
