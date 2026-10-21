import json
import pytest
import sys
import time
from pathlib import Path
from research_agent.application.execution import dispatch
from research_agent.application.job_manager import command
from tests.unit.test_job_recovery import workspace



def binding_record():
    return {'schema_version': 'coragent-job-monitor/2', 'monitor_id': 'monitor_1',
            'workspace_id': 'fixture', 'job_id': 'job_1', 'job_digest': 'sha256:'+'a'*64,
            'session_id': 's', 'user_task_id': None, 'node_id': None, 'node_revision': None,
            'wake_policy': 'next_run', 'notify_policy': 'none', 'created_at': '2026-10-21T00:00:00Z',
            'sequence': 0, 'last_state': None}


def write_binding(folder):
    path = folder / 'binding.json'
    path.write_text(json.dumps(binding_record()))
    return path


def test_terminal_job_wakes_once_and_reclaims_failed_delivery(tmp_path):
    workspace(tmp_path)
    job=dispatch('start',{'root':str(tmp_path),'request_id':'job_wake',
        'session_id':'session_original','command':[sys.executable,'-c','pass']})
    for _ in range(100):
        command(tmp_path,'tick',{})
        rows=command(tmp_path,'pending',{})['deliveries']
        if rows:break
        time.sleep(.02)
    assert len(rows)==1
    event_id=rows[0]['event_id']
    first=command(tmp_path,'claim',{'event_id':event_id,'channel':'wake'})
    assert first['claimed'] and first['session_id']=='session_original'
    assert command(tmp_path,'claim',{'event_id':event_id,'channel':'notify'})['claimed'] is False
    command(tmp_path,'complete',{'event_id':event_id,'channel':'wake','claim_token':first['claim_token'],'error':'host offline'})
    before = {p: p.read_bytes() for p in (tmp_path/'operations/monitors').rglob('*.json')}
    view = command(tmp_path, 'list', {})['monitors'][0]
    assert view['last_state'] == 'succeeded'
    assert view['pending_count'] == 1
    assert view['last_observed_at']
    assert view['last_error'] == 'host offline'
    assert {p: p.read_bytes() for p in before} == before
    assert 'enabled' not in view
    for action in ('enable', 'disable'):
        with pytest.raises(ValueError):
            command(tmp_path, action, {'monitor_id': view['monitor_id']})
    second=command(tmp_path,'claim',{'event_id':event_id,'channel':'wake'})
    assert second['request_id']==first['request_id']
    command(tmp_path,'complete',{'event_id':event_id,'channel':'wake','claim_token':second['claim_token'],'delivered':True})
    command(tmp_path,'tick',{})
    assert command(tmp_path,'pending',{})['deliveries']==[]
    view = command(tmp_path, 'status', {})['monitors'][0]
    assert view['pending_count'] == 0
    assert view['last_error'] is None


def test_pending_delivery_does_not_read_research_memory(tmp_path):
    workspace(tmp_path)
    folder=tmp_path/'operations/monitors/monitor_1/deliveries'
    folder.mkdir(parents=True)
    write_binding(folder.parent)
    (folder/'event_1.json').write_text(json.dumps({'schema_version':'coragent-job-monitor-delivery/2',
        'event_id':'event_1','session_id':'s','request_id':'job-wake:event_1','delivered':False}))
    # Even an unavailable Memory projection cannot hide a runtime event.
    import shutil
    shutil.rmtree(tmp_path/'research')
    rows=command(tmp_path,'pending',{})['deliveries']
    assert len(rows)==1
    assert command(tmp_path,'pending',{})['deliveries']==rows


def test_long_queue_emits_one_diagnostic_event_without_poll_wakes(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from research_agent.jobs import JobReceipt, JobState, ExternalJobPlatform
    from research_agent.application import job_manager
    workspace(tmp_path)
    config = tmp_path/'job.toml'
    config.write_text('[execution]\ndefault_target="cluster"\n[execution.targets.cluster]\n'
                      'driver="external"\ntransport="ssh"\nssh_host="fixture"\nwork_root="/scratch"\n'
                      'handler=["/bin/true"]\n[execution.targets.cluster.submission]\nqueue="batch"\nqueue_wait_seconds=60\n')
    monkeypatch.setenv('CORAGENT_JOB_CONFIG', str(config))
    # Exercise submission and Monitor registration with a queued remote Job;
    # local processes have no scheduler queue or queue-wait threshold.
    def submit(platform, spec):
        receipt = JobReceipt(spec.job_id, platform.name, '2026-10-09T00:00:00+00:00', spec.command,
                             str(spec.cwd), metadata={**spec.metadata, 'scheduler_id': '123.fixture'},
                             workspace_id=spec.workspace_id)
        (spec.cwd/'receipt.json').write_text(json.dumps(receipt.__dict__))
        return receipt
    monkeypatch.setattr(ExternalJobPlatform, 'start', submit)
    dispatch('start',{'root':str(tmp_path),'request_id':'job_queue','session_id':'s',
        'command':['/bin/true']})
    status = SimpleNamespace(state=JobState.QUEUED,exit_code=None,error=None,diagnostics={'wait_seconds':10})
    monkeypatch.setattr(job_manager,'_job_manager',lambda root:SimpleNamespace(job_status=lambda receipt:status))
    command(tmp_path,'tick',{})
    assert command(tmp_path,'pending',{})['deliveries']==[]
    status.diagnostics={'wait_seconds':61,'queue_diagnosis':'feasible procs: 0'}
    for _ in range(3):command(tmp_path,'tick',{})
    rows=command(tmp_path,'pending',{})['deliveries'];assert len(rows)==1
    event=command(tmp_path,'event',{'event_id':rows[0]['event_id']})
    assert event['status']['reason']=='queue_wait_exceeded'
    assert event['status']['diagnostics']['queue_diagnosis']=='feasible procs: 0'


def test_batches_are_stable_across_retry_and_new_events(tmp_path):
    workspace(tmp_path)
    folder=tmp_path/'operations/monitors/monitor_1/deliveries';folder.mkdir(parents=True)
    write_binding(folder.parent)
    def add(name, **extra):
        (folder/f'{name}.json').write_text(json.dumps({'schema_version':'coragent-job-monitor-delivery/2','event_id':name,'session_id':'s',
            'request_id':'job-wake:'+name,'delivered':False,**extra}))
    add('event_1');add('event_2')
    rows=command(tmp_path,'pending',{})['deliveries']
    assert rows[0]['request_id']==rows[1]['request_id']
    assert rows[0]['batch_event_ids']==['event_1','event_2']
    add('event_3')
    again=command(tmp_path,'pending',{})['deliveries']
    assert again[:2]==rows
    assert again[2]['request_id']!=rows[0]['request_id']
    add('event_4',claim_token='uncertain-rpc',batch_event_ids=['event_4'])
    old=command(tmp_path,'pending',{})['deliveries'][-1]
    assert old['request_id']=='job-wake:event_4'


def test_monitor_status_observes_outbox_without_claiming_or_batching(tmp_path):
    workspace(tmp_path)
    folder = tmp_path/'operations/monitors/monitor_1'
    (folder/'deliveries').mkdir(parents=True)
    write_binding(folder)
    pending = folder/'deliveries/event_1.json'
    pending.write_text(json.dumps({'schema_version':'coragent-job-monitor-delivery/2','event_id':'event_1','session_id':'s','request_id':'wake_pending','delivered':False}))
    (folder/'deliveries/event_2.json').write_text(json.dumps({'schema_version':'coragent-job-monitor-delivery/2','event_id':'event_2','session_id':'s','request_id':'wake_done','delivered':True}))
    before = pending.read_bytes()
    result = command(tmp_path,'status',{})
    assert [row['event_id'] for row in result['pending_deliveries']] == ['event_1']
    assert result['pending_deliveries'][0]['session_id'] == 's'
    assert pending.read_bytes() == before


def test_delivery_retry_identity_is_independent_of_research_notes(tmp_path):
    workspace(tmp_path)
    folder = tmp_path/'operations/monitors/monitor_1/deliveries'
    folder.mkdir(parents=True)
    write_binding(folder.parent)
    path = folder/'event_1.json'
    path.write_text(json.dumps({'schema_version':'coragent-job-monitor-delivery/2', 'event_id':'event_1',
        'session_id':'s', 'request_id':'original', 'delivered':False, 'batch_event_ids':['event_1']}))
    row = command(tmp_path, 'claim', {'event_id':'event_1', 'channel':'wake'})
    command(tmp_path, 'complete', {'event_id':'event_1', 'channel':'wake', 'claim_token':row['claim_token'], 'error':'busy'})
    retry = command(tmp_path, 'pending', {})['deliveries'][0]
    assert retry['request_id'] == 'original'
    assert command(tmp_path, 'pending', {})['deliveries'][0] == retry


@pytest.mark.parametrize('extra', [{'enabled': True}, {'enabled': False}, {'unexpected': 'field'}])
def test_unknown_binding_fields_cannot_mutate_or_claim_outbox(tmp_path, extra):
    from research_agent.application.job_manager import read_binding
    workspace(tmp_path)
    folder = tmp_path / 'operations/monitors/monitor_1'
    (folder / 'deliveries').mkdir(parents=True)
    binding = {**binding_record(), **extra}
    path = folder / 'binding.json'
    path.write_text(json.dumps(binding))
    pending = folder / 'deliveries/event_1.json'
    pending.write_text(json.dumps({'schema_version': 'coragent-job-monitor-delivery/2',
        'event_id': 'event_1', 'session_id': 's', 'request_id': 'wake_original', 'delivered': False}))
    original = {p: p.read_bytes() for p in (path, pending)}
    with pytest.raises(ValueError, match='monitor_binding_schema_invalid'):
        read_binding(path)
    for action, args in [('pending', {}), ('claim', {'event_id': 'event_1', 'channel': 'wake'})]:
        with pytest.raises(ValueError, match='monitor_binding_schema_invalid'):
            command(tmp_path, action, args)
    assert command(tmp_path, 'tick', {})['registration_errors'] == ['monitor_binding_schema_invalid']
    assert all(p.read_bytes() == content for p, content in original.items())


@pytest.mark.parametrize('mutation', [
    lambda value: value.pop('user_task_id'),
    lambda value: value.update(node_id='node_1', node_revision=None),
    lambda value: value.update(job_id='invalid'),
    lambda value: value.update(schema_version='unsupported'),
])
def test_invalid_binding_is_rejected_without_rewriting(tmp_path, mutation):
    from research_agent.application.job_manager import read_binding
    value = binding_record()
    mutation(value)
    path = tmp_path / 'binding.json'
    path.write_text(json.dumps(value))
    with pytest.raises(ValueError, match='monitor_binding_schema_invalid'):
        read_binding(path)
    assert json.loads(path.read_text()) == value


@pytest.mark.parametrize('kind', ['event', 'delivery'])
def test_outbox_records_are_checked_against_current_schema(tmp_path, kind):
    from research_agent.application.job_manager import validate_event, read_delivery
    if kind == 'event':
        value = {**binding_record(), 'schema_version': 'coragent-job-monitor-event/2',
            'event_id': 'event_1', 'sequence': 1, 'state': 'failed', 'previous_state': None,
            'status_digest': 'sha256:'+'b'*64, 'program_status': None, 'exit_status': 1,
            'error_class': None, 'error': None, 'observed_at': '2026-10-21T00:00:00Z',
            'status': {'state': 'failed'}}
        check = validate_event
    else:
        value = {'schema_version': 'coragent-job-monitor-delivery/2', 'event_id': 'event_1',
            'session_id': 's', 'request_id': 'wake', 'delivered': False}
        def check(value):
            path = tmp_path / 'delivery.json'
            path.write_text(json.dumps(value))
            return read_delivery(path)
    assert check(value) == value
    for extra in ({'enabled': True}, {'enabled': False}, {'unknown': 1}):
        with pytest.raises(ValueError, match=f'monitor_{kind}_schema_invalid'):
            check({**value, **extra})
