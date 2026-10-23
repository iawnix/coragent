"""Durable, domain-neutral Job wake outbox. Never sends notifications."""
import hashlib
import json
import re
import time
import uuid
from types import SimpleNamespace
from research_agent.jobs import JobState
from datetime import datetime, timezone
from pathlib import Path
from importlib.resources import files
from jsonschema import Draft202012Validator
from research_agent.foundation.transactions import TransactionCoordinator, workspace_transaction, write_json, read_json
from .execution import _recorded_job_manager, _receipt
from research_agent.research.operational_ids import allocate_id

_CONTRACTS = json.loads(files(__package__).joinpath('monitor_contracts.json').read_text())
_VALIDATORS = {name: Draft202012Validator(schema) for name, schema in _CONTRACTS.items()}
JOB_EVENT_IDS_LIMIT = json.loads(files(__package__).joinpath('monitor_limits.json').read_text())['max_event_ids']


def validate_record(kind, value):
    if not _VALIDATORS[kind].is_valid(value):
        raise ValueError(f'monitor_{kind}_schema_invalid')
    return value


def now():return datetime.now(timezone.utc).isoformat()
def read(path):return read_json(path)
def write(path,value):
    write_json(path, value)
def digest(value):return 'sha256:'+hashlib.sha256(json.dumps(value,sort_keys=True).encode()).hexdigest()


def read_binding(path):
    return validate_record('binding', read(path))


def read_delivery(path):
    return validate_record('delivery', read(path))


def monitor_view(path):
    """Project existing observations and outbox facts for Host clients."""
    binding = read_binding(path)
    pending = [row for p in sorted((path.parent / 'deliveries').glob('*.json'))
               if not (row := read_delivery(p)).get('delivered')]
    events = [validate_event(read(p)) for p in (path.parent / 'events').glob('*.json')]
    latest = max(events, key=lambda event: event['sequence'], default={})
    errors = [row['error'] for row in pending if row.get('error')]
    return {**binding, 'pending_count': len(pending),
            'last_observed_at': latest.get('observed_at'),
            'last_error': errors[-1] if errors else latest.get('error')}


def bind(root, intent, session_id):
    if not session_id:return
    job=intent['job_id'];mid=allocate_id(root, 'monitor', job)
    path=root/'operations/monitors'/mid/'binding.json'
    if path.exists():
        read_binding(path)
        return
    manifest=read(root/'workspace_manifest.json')
    write(path,{'schema_version':'coragent-job-monitor/2','monitor_id':mid,'workspace_id':manifest['workspace_id'],
        'job_id':job,'node_id':intent.get('node_id'),'node_revision':intent.get('node_revision'),
        'user_task_id':intent.get('user_task_id'),
        'job_digest':digest(intent),'session_id':session_id,'wake_policy':'next_run','notify_policy':'none',
        'created_at':now(),'sequence':0,'last_state':None})


def command(root, action, args):
    root=Path(root).resolve();base=root/'operations/monitors'
    if action == 'tick':
        return _tick(root, base, args)
    with TransactionCoordinator(root).locked():
        return _command(root,base,action,args)


def _command(root,base,action,args):
    manifest=read(root/'workspace_manifest.json');workspace_id=manifest['workspace_id']
    bindings=sorted(base.glob('*/binding.json'))
    if args.get('monitor_id'):bindings=[p for p in bindings if p.parent.name==args['monitor_id']]
    if action == 'observations':
        observations, errors = [], []
        for path in bindings:
            try:
                binding = read_binding(path)
                intent = read(root / 'operations/jobs' / (binding['job_id'] + '.json'))
                if intent['schema_version'] != 'job_intent/4' or intent['job_id'] != binding['job_id']:
                    raise ValueError('monitor_job_intent_mismatch')
                observations.append({'monitor_id': binding['monitor_id'], 'platform': intent['platform']})
            except Exception as error:
                errors.append(f'{path.parent.name}: {error}')
        return {'observations': observations, 'registration_errors': errors}
    if action in {'list','status'}:
        result = {'workspace_id':workspace_id,'monitors':[monitor_view(p) for p in bindings]}
        if action == 'status':
            # Observation must not claim, batch or retry the delivery outbox.
            result['pending_deliveries'] = [
                {key: row.get(key) for key in ('session_id', 'request_id', 'event_id', 'error')}
                for binding in bindings for path in sorted((binding.parent/'deliveries').glob('*.json'))
                if not (row := read_delivery(path)).get('delivered')]
        return result
    if action=='health':
        write(base/'health.json',{'checked_at':now(),'error':args.get('error')});return {'ok':True}
    if action=='tick':
        raise ValueError('tick must observe outside the workspace transaction')
    return _delivery_command(root,base,action,args)


def _tick(root, base, args):
    from research_agent.jobs.command_scope import observation_deadline
    bindings=sorted(base.glob('*/binding.json'))
    if args.get('monitor_id'):bindings=[p for p in bindings if p.parent.name==args['monitor_id']]
    errors=[];observed=[]
    for p in bindings:
        try:
            row=read_binding(p)
            receipt = None
            with observation_deadline(args.get('timeout_seconds', 30)):
                try:
                    runtime = _recorded_job_manager(root, row['job_id'])
                    receipt=_receipt(root,{'job_id':row['job_id']}, runtime=runtime)
                    status=runtime.job_status(receipt)
                except FileNotFoundError:
                    status=SimpleNamespace(state=JobState.UNKNOWN,exit_code=None,error='dispatch intent has no receipt; reconcile required')
            status_value={key:getattr(status,key,None) for key in ('exit_code','started_at','finished_at','error','diagnostics')}
            status_value['state']=status.state.value
            observed.append(_commit_observation(root, {'monitor_id':row['monitor_id'],
                'status':status_value,'receipt':receipt.__dict__ if receipt else None}))
        except Exception as exc:errors.append(str(exc))
    return {'monitors':observed,'registration_errors':errors}



@workspace_transaction('job.monitor_observation')
def _commit_observation(root, request):
    p=root/'operations/monitors'/request['monitor_id']/'binding.json'
    row=read_binding(p)
    status=SimpleNamespace(**request['status'])
    receipt=SimpleNamespace(**request['receipt']) if request['receipt'] else SimpleNamespace(
        job_id=row['job_id'], workspace_id=row['workspace_id'], metadata={})
    if receipt:
        if receipt.job_id!=row['job_id']:
            raise ValueError('monitor_binding_mismatch')
        from .job_state import observe_execution
        conflict = observe_execution(root,receipt,request['status'])
        if conflict:
            status.state = "unknown"
            status.error = "job_terminal_conflict: explicit reconciliation required"
    state=status.state
    result={'monitor_id':row['monitor_id'],'state':state}
    diagnostics = getattr(status, 'diagnostics', {}) or {}
    threshold = receipt.metadata.get('queue_wait_seconds') if receipt is not None else None
    queue_wait = (state in {'queued','held'} and threshold and
                  (diagnostics.get('wait_seconds') or 0) >= threshold and not row.get('queue_wait_reported'))
    if state==row.get('last_state') and not queue_wait:return result
    if queue_wait: row['queue_wait_reported'] = True
    previous=row.get('last_state');row['last_state']=state
    # Queue/running transitions are retained without waking the Agent.
    if state not in {'succeeded','failed','timed_out','cancelled','unknown'} and not queue_wait:
        write(p,row);return result
    row['sequence']+=1
    eid=allocate_id(root, 'event', [row['monitor_id'], row['sequence'], state])
    event={**row,'schema_version':'coragent-job-monitor-event/2','event_id':eid,'state':state,
        'previous_state':previous,'status_digest':digest({'state':state,'exit_code':status.exit_code}),
        'program_status':None,'exit_status':status.exit_code,'error_class':None,
        'error':status.error,'observed_at':now(),'status':{'state':state,'exit_code':status.exit_code,'diagnostics':diagnostics, 'reason':'queue_wait_exceeded' if queue_wait else 'state_changed'}}
    write(p.parent/'events'/f'{eid}.json',event)
    write(p.parent/'deliveries'/f'{eid}.json',{'schema_version':'coragent-job-monitor-delivery/2','event_id':eid,'session_id':row['session_id'],
        'request_id':'job-wake:'+eid,'delivered':False})
    write(p,row)
    return result



def _delivery_command(root,base,action,args):
    deliveries=sorted(base.glob('*/deliveries/*.json'))
    if action=='pending':
        pending = [(p, row) for p in deliveries if not (row := read_delivery(p)).get('delivered')]
        for path, _ in pending:
            read_binding(path.parent.parent / 'binding.json')
        # Persist immutable batch membership before Host admission. Retries and
        # uncertain RPC outcomes must reuse both identity and message payload.
        sessions = {}
        for path, row in pending:
            if not row.get('batch_event_ids'):
                sessions.setdefault(row.get('session_id'), []).append((path, row))
        for rows in sessions.values():
            rows.sort(key=lambda item: _event_number(item[1]['event_id']))
            for offset in range(0, len(rows), JOB_EVENT_IDS_LIMIT):
                _assign_batch(root, rows[offset:offset + JOB_EVENT_IDS_LIMIT])
        # Task Controller owns admission policy; the outbox retains facts only.
        # Keep a partially acknowledged batch ahead of newer events by using
        # its full immutable membership, including already delivered members.
        return {'deliveries': sorted((row for _, row in pending), key=_delivery_order)}
    if action in {'claim', 'complete'}:
        return _batch_delivery(root, deliveries, action, args)
    eid=args.get('event_id')
    path=next((p for p in deliveries if p.stem==eid),None)
    if path is None:raise ValueError('unknown monitor event')
    if action=='event':
        return validate_event(read(path.parent.parent/'events'/f'{eid}.json'))
    raise ValueError('unknown monitor command')


def _batch_delivery(root, paths, action, args):
    if args.get('channel') != 'wake':
        return {'claimed': False}
    request_id = args.get('request_id')
    if not isinstance(request_id, str) or not request_id:
        raise ValueError('monitor_request_id_required: claim and complete select a fixed batch')
    rows = [(path, row) for path in paths if (row := read_delivery(path))['request_id'] == request_id]
    if not rows:
        raise ValueError('unknown monitor batch')
    for path, _ in rows:
        read_binding(path.parent.parent / 'binding.json')
    first = rows[0][1]
    members = first.get('batch_event_ids')
    if (not members or set(members) != {row['event_id'] for _, row in rows}
            or any(row['session_id'] != first['session_id'] or row.get('batch_event_ids') != members
                   for _, row in rows)):
        raise ValueError('monitor_batch_membership_invalid')
    pending = [(path, row) for path, row in rows if not row['delivered']]
    coordinator = TransactionCoordinator(root)
    if action == 'claim':
        if not pending:
            return {'claimed': False}
        if len(members) > JOB_EVENT_IDS_LIMIT:
            raise ValueError('monitor_batch_too_large: preserve the original request; '
                             'verify that Pi never accepted it before repairing the batch')
        if any(row.get('lease_until', 0) > time.time() for _, row in pending):
            return {'claimed': False}
        events = []
        for path, row in sorted(rows, key=lambda item: item[1]['event_id']):
            event = validate_event(read(path.parent.parent / 'events' / path.name))
            if event['event_id'] != row['event_id'] or event['session_id'] != row['session_id']:
                raise ValueError('monitor_delivery_binding_mismatch')
            events.append(event)
        token, lease_until = uuid.uuid4().hex, time.time() + 60
        writes = {str(path.relative_to(root)): {**row, 'claim_token': token, 'lease_until': lease_until}
                  for path, row in pending}
        result = {'claimed': True, 'request_id': request_id, 'session_id': first['session_id'],
                  'claim_token': token, 'lease_until': lease_until}
        committed = coordinator.commit_files('monitor-claim:' + token, 'job.monitor_claim',
            {'request_id': request_id, 'claim_token': token}, writes=writes, result=result)['result']
        # Immutable events and membership already live in the outbox. Return
        # them to the caller without copying them into every retry receipt.
        return {**committed, 'batch_event_ids': members, 'events': events}
    token = args.get('claim_token')
    if not isinstance(token, str) or not token:
        raise ValueError('stale wake claim')
    transaction_id = 'monitor-complete:' + token
    payload = {'request_id': request_id, 'claim_token': token,
               'delivered': bool(args.get('delivered')), 'error': args.get('error')}
    if coordinator.get(transaction_id):
        return coordinator.commit_files(transaction_id, 'job.monitor_complete', payload,
                                        writes={}, result={})['result']
    if not pending or any(row.get('claim_token') != token or row.get('lease_until', 0) <= time.time()
                          for _, row in pending):
        raise ValueError('stale wake claim')
    writes = {str(path.relative_to(root)): {**row, 'delivered': payload['delivered'],
              'error': payload['error'], 'lease_until': 0} for path, row in pending}
    return coordinator.commit_files(transaction_id, 'job.monitor_complete', payload,
                                    writes=writes, result={'ok': True})['result']


def _event_number(event_id):
    return int(event_id.removeprefix('event_'))


def _delivery_order(row):
    members = row.get('batch_event_ids') or [row['event_id']]
    return row['session_id'], min(map(_event_number, members)), _event_number(row['event_id'])


def _assign_batch(root, rows):
    ids = sorted(row['event_id'] for _, row in rows)
    batch_digest = hashlib.sha256(':'.join(ids).encode()).hexdigest()
    request_id = 'job-wake-batch:' + batch_digest
    writes = {str(path.relative_to(root)): {**row, 'request_id': request_id, 'batch_event_ids': ids}
              for path, row in rows}
    # One redo decision owns every member. A crash during file replacement is
    # recovered before the next pending/claim observes this batch.
    TransactionCoordinator(root).commit_files('monitor-batch:' + batch_digest, 'job.monitor_batch',
        {'session_id': rows[0][1]['session_id'], 'event_ids': ids}, writes=writes,
        result={'request_id': request_id, 'event_ids': ids})
    for path, row in rows:
        row.update(writes[str(path.relative_to(root))])


def validate_event(event):
    return validate_record('event', event)


def assess(root, event_id, session_id):
    if not isinstance(event_id, str) or not re.fullmatch(r"event_[1-9][0-9]*", event_id):
        raise ValueError("invalid monitor event identity")
    root = Path(root)
    with TransactionCoordinator(root).locked():
        paths = list((root / "operations/monitors").glob(f"*/events/{event_id}.json"))
        if len(paths) != 1:
            raise ValueError("unknown monitor event")
        event = validate_event(read(paths[0]))
        if event["workspace_id"] != read(root / "workspace_manifest.json")["workspace_id"] or event["session_id"] != session_id:
            raise ValueError("monitor event belongs to another workspace or session")
        delivery = read_delivery(paths[0].parent.parent / "deliveries" / paths[0].name)
        if delivery['event_id'] != event_id or delivery['session_id'] != session_id:
            raise ValueError("monitor_delivery_binding_mismatch")
        obsolete = bool(delivery.get("delivered"))
        read_binding(paths[0].parent.parent / "binding.json")
        return {"event_id": event_id, "event": event, "obsolete": obsolete,
                "admitted": not obsolete, "reason": "already_delivered" if obsolete else "attention_required",
                "delivery_token": digest({"event_id": event_id, "request_id": delivery["request_id"], "delivered": obsolete})}
