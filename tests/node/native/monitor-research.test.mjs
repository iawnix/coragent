import assert from 'node:assert/strict';
import test from 'node:test';
import { createMonitorService } from '../../../apps/agent/tasks/service.mjs';
import { formatMonitor } from '../../../apps/agent/terminal/commands/monitor.mjs';
import { createTerminalSession } from '../../../apps/agent/terminal/session.mjs';
import { projectMonitorTask, projectMonitorContinuation } from '../../../apps/agent/tasks/projection.mjs';

const task = {
  schema_version: 'coragent-user-task/5', user_task_id: 'task_1', title: 'Compare methods',
  objective: 'Explain the comparison and its limits', state: 'active', criteria: [],
  research: { entry_node_ids: ['node_1', 'node_2'], focus_node_ids: ['node_3'] },
  updated_at: '2026-10-10T00:00:00Z', revision: 7,
  research_context: { brief_id: 'brief_state', state_digest: 'sha256:state',
    brief_digest: 'sha256:review', availability: 'available', projection_status: 'complete', synthesis_status: 'not_requested', refresh_reason: 'initial', updated_at: '2026-10-10T00:00:01Z' },
};
const snapshot = {
  schema_version: 'research-snapshot/3', sequence: 42,
  research: {
    entry_node_ids: task.research.entry_node_ids, focus_node_ids: task.research.focus_node_ids,
    nodes: [
      { id: 'node_1', revision: 1, title: 'Method A', status: 'closed', assessment_ref: 'result_a',
        plan: 'Compare the numerical estimates', content_omitted: false, read: { ref: 'node_1', field: 'relations' } },
      { id: 'node_3', revision: 3, title: 'Shared convergence question', status: 'open', assessment_ref: null,
        plan: 'Bound the numerical error', content_omitted: true, read: { ref: 'node_3', field: 'relations' } },
    ],
    relations: [
      { id: 'edge_a', source: 'node_3', kind: 'part_of', target: 'node_1' },
      { id: 'edge_b', source: 'node_3', kind: 'part_of', target: 'node_2' },
    ],
    omitted: { entry_node_ids: 0, focus_node_ids: 0, nodes: 1, relations: 2, unexpanded_nodes: 1 },
  },
  nodes: [
    { id: 'node_1', recent_results: [{ id: 'result_a', summary: 'Uncertainty remains' }] },
    { id: 'node_4', title: 'Unrelated recent research' },
  ],
  running_jobs: [{ job_id: 'job_a', node_id: 'node_3' }, { job_id: 'job_unrelated', node_id: 'node_4' }],
  uncollected_jobs: [],
};

test('Monitor task research uses the canonical read without mutating focus or admitting input', async () => {
  const original = structuredClone(task), calls = [], reads = [];
  const service = createMonitorService({ workspaceId: 'w', sessionId: 's',
    controller: { async read(params) { reads.push(params); return task; } },
    kernel: { async execute_command(command, params) {
      calls.push([command, params]);
      return command === 'research_read' ? snapshot : { jobs: [{ job_id: 'job_a' }], next_cursor: null };
    } },
  });
  const rpc = [];
  const session = createTerminalSession({ workspaceId: 'w', sessionId: 's',
    async request(method, params) {
      rpc.push(method);
      const response = await service.handle({ method, params });
      assert.equal(response.error, null);
      return response.result;
    },
  });
  for (let attempt = 0; attempt < 2; attempt++) {
    const response = await session.monitor('monitor/task/read', { user_task_id: 'task_1' });
    assert.equal(response.task, task);
    assert.equal(response.research, snapshot);
    assert.deepEqual(response.session_job_ids, ['job_a']);
  }
  assert.deepEqual(rpc, ['monitor/task/read', 'monitor/task/read']);
  assert.equal(reads.length, 2);
  assert.deepEqual(calls, Array.from({ length: 2 }, () => [['research_read', {
    session_id: 's', entry_node_ids: ['node_1', 'node_2'], focus_node_ids: ['node_3'], limit: 16000,
  }], ['job_list', { session_id: 's', limit: 100 }]]).flat());
  assert.deepEqual(task, original);
});

test('Monitor displays shared graph references, partial plans and ended status without success claims', () => {
  const view = formatMonitor('monitor/task/read', { task, research: snapshot, session_job_ids: ['job_a'] });
  assert.match(view, /Research problems/);
  assert.match(view, /Entry references: node_1, node_2/);
  assert.match(view, /Current focus: node_3/);
  assert.match(view, /Status: closed · Ended/);
  assert.match(view, /Plan: Bound the numerical error/);
  assert.match(view, /Excerpt only/);
  assert.match(view, /Assessment reference: result_a/);
  assert.match(view, /Result: result_a · Uncertainty remains/);
  assert.equal(view.match(/Shared convergence question/g).length, 1);
  assert.match(view, /node_3 part_of node_1/);
  assert.match(view, /node_3 part_of node_2/);
  assert.match(view, /Omitted: nodes 1, relations 2/);
  assert.match(view, /\/research read node_3/);
  assert.match(view, /\/monitor job job_a/);
  assert.doesNotMatch(view, /Unrelated recent research|job_unrelated|\d+%|Status:.*succeeded/);
});

test('unbound tasks do not claim recent workspace research as their own', () => {
  const unbound = { ...snapshot, research: { entry_node_ids: [], focus_node_ids: [], nodes: [], relations: [],
    omitted: { entry_node_ids: 0, focus_node_ids: 0, nodes: 0, relations: 0, unexpanded_nodes: 0 } } };
  const view = formatMonitor('monitor/task/read', {
    task: { ...task, research: { entry_node_ids: [], focus_node_ids: [] } }, research: unbound, session_job_ids: [],
  });
  assert.match(view, /No research problems linked/);
  assert.doesNotMatch(view, /Unrelated recent research|Uncertainty remains|\/monitor job job_a/);
});

test('research snapshot errors surface through the existing Monitor error envelope', async () => {
  let calls = 0;
  const service = createMonitorService({ workspaceId: 'w', sessionId: 's',
    controller: { async read() { return task; } },
    kernel: { async execute_command() {
      calls++;
      throw Object.assign(new Error('Research unavailable'), { code: 'research_read_failed' });
    } },
  });
  const response = await service.handle({ method: 'monitor/task/read', params: { user_task_id: 'task_1' } });
  assert.deepEqual(response, { result: null, error: { code: 'research_read_failed', message: 'Research unavailable' } });
  assert.equal(calls, 1);
});

test('Monitor overview omits internal records and duplicate review and policy fields', async () => {
  const service = createMonitorService({ workspaceId: 'w', sessionId: 's',
    controller: { async current() { return task; }, health() { return { automatic_continuation_enabled: false }; } },
    kernel: { async execute_command(command) { return command === 'job_list' ? { jobs: [], next_cursor: null } : {}; } },
    harness: { async snapshot() { return null; } }, conversation: { id: 'c' }, LiveDoc: {} });
  const response = await service.handle({ method: 'monitor/overview', params: {} });
  assert.equal(response.error, null);
  assert.equal(response.result.schema_version, 'coragent-monitor/2');
  assert.equal(response.result.research_context, undefined);
  assert.equal(response.result.task.research_context, undefined);
  assert.equal(response.result.task_controller, undefined);
  assert.equal(response.result.automatic_continuation_enabled, undefined);
  assert.equal(response.result.continuation.state, 'disabled');
  assert.equal(response.result.task.revision, task.revision);
});

test('task controls read revision through task pages even when research is unavailable', async () => {
  const calls = [];
  const session = createTerminalSession({ workspaceId: 'w', sessionId: 's', async request(method, params) {
    calls.push([method, params]);
    if (method === 'monitor/task/read') throw new Error('Research unavailable');
    if (method === 'monitor/tasks') return params.cursor
      ? { items: [projectMonitorTask(task, { list: true })], next_cursor: null }
      : { items: [{ user_task_id: 'task_3', revision: 1 }], next_cursor: 'page2' };
    return { task };
  } });
  for (const action of ['pause', 'resume', 'cancel']) {
    await session.monitor(`monitor/task/${action}`, { user_task_id: 'task_1', ...(action === 'cancel' ? { jobs: 'keep' } : {}) });
    assert.equal(calls.at(-1)[0], `monitor/task/${action}`);
    assert.equal(calls.at(-1)[1].expected_revision, 7);
    assert.match(calls.at(-1)[1].request_id, /^terminal-monitor-/);
    assert.equal(calls.at(-2)[1].cursor, 'page2');
  }
  assert.equal(calls.some(([method]) => method === 'monitor/task/read' || method === 'input/send'), false);
  await assert.rejects(session.monitor('monitor/task/pause', { user_task_id: 'task_2' }), { code: 'task_not_found' });
  assert.equal(calls.at(-1)[0], 'monitor/tasks');
});

test('shared research keeps external Jobs visible without offering unusable session commands', async () => {
  const shared = { ...snapshot, running_jobs: [
    { job_id: 'job_a', node_id: 'node_3' },
    { job_id: 'job_external', node_id: 'node_3' },
  ] };
  const calls = [];
  const service = createMonitorService({ workspaceId: 'w', sessionId: 's',
    controller: { async read() { return task; } },
    kernel: { async execute_command(command, params) {
      calls.push([command, params]);
      if (command === 'research_read') return shared;
      assert.equal(command, 'job_list');
      assert.equal(params.session_id, 's');
      return params.cursor
        ? { jobs: [{ job_id: 'job_a', session_id: 's' }], next_cursor: null }
        : { jobs: [{ job_id: 'job_other', session_id: 's' }], next_cursor: 'page2' };
    } },
  });
  const detail = await service.handle({ method: 'monitor/task/read', params: { user_task_id: 'task_1' } });
  assert.equal(detail.error, null);
  assert.deepEqual(detail.result.session_job_ids, ['job_a']);
  assert.equal(detail.result.research, shared);
  assert.equal(calls.at(-1)[1].cursor, 'page2');
  const view = formatMonitor('monitor/task/read', detail.result);
  assert.match(view, /node_3: \/monitor job job_a/);
  assert.match(view, /node_3: job_external · Outside this session/);
  assert.doesNotMatch(view, /\/monitor job job_external|job_other/);
  assert.equal((await service.handle({ method: 'monitor/job/read', params: { job_id: 'job_a' } })).result.job.job_id, 'job_a');
  assert.equal((await service.handle({ method: 'monitor/job/read', params: { job_id: 'job_external' } })).error.code, 'job_not_found');
});

test('Monitor summaries are bounded and task pages preserve control revisions without growing records', async () => {
  const huge = '研究\n"'.repeat(20000);
  const full = { ...task, title: huge, objective: huge, next_action: huge, reason: huge,
    progress: { summary: huge, at: task.updated_at, evidence_refs: [huge] },
    block_details: { resume_when: huge, evidence_refs: [huge] },
    execution_recovery: { state: 'retrying', phase: 'research', detail: huge, failures: 20, next_retry_at: null },
    sources: [{ text: huge }], audit: [{ reason: huge }], progress_identities: [huge],
    continuation: { reservation: { request_id: huge } }, event_inputs: [huge] };
  const summary = projectMonitorTask(full);
  assert.ok(Buffer.byteLength(JSON.stringify(summary)) < 5000);
  assert.equal(summary.truncated, true);
  for (const field of ['sources', 'criteria', 'audit', 'research', 'research_context', 'continuation', 'progress_identities', 'event_inputs']) {
    assert.equal(summary[field], undefined, field);
  }
  assert.equal(summary.execution_recovery.failures, undefined);
  const service = createMonitorService({ workspaceId: 'w', sessionId: 's',
    controller: { async list(_ctx, params) { assert.equal(params.cursor, 'page2'); return { items: [full], next_cursor: 'page3' }; },
      async read() { return full; } },
    kernel: { async execute_command(command) { return command === 'research_read' ? snapshot : { jobs: [], next_cursor: null }; } },
  });
  const page = await service.handle({ method: 'monitor/tasks', params: { cursor: 'page2' } });
  assert.equal(page.error, null);
  assert.equal(page.result.next_cursor, 'page3');
  assert.deepEqual(Object.keys(page.result.items[0]).sort(), ['completion_outcome', 'revision', 'state', 'title', 'truncated', 'updated_at', 'user_task_id']);
  assert.equal(page.result.items[0].revision, 7);
  const detail = await service.handle({ method: 'monitor/task/read', params: { user_task_id: task.user_task_id } });
  assert.equal(detail.error, null);
  assert.equal(detail.result.task, full);
});

test('Monitor overview counts every scoped job page and previews only active work', async () => {
  for (const current of [task, null]) {
    const calls = [];
    const pages = [
      [{ job_id: 'ended', state: 'succeeded' }, { job_id: 'run', state: 'running' }],
      ['created', 'submitted', 'queued', 'held', 'running', 'failed'].map((state, i) => ({ job_id: `job_${i}`, state, secret: 'omit' })),
    ];
    const service = createMonitorService({ workspaceId: 'w', sessionId: 's',
      controller: { async current() { return current; }, health() { return {}; } },
      harness: { async snapshot() { return null; } }, conversation: { id: 'c' }, LiveDoc: {},
      kernel: { async execute_command(command, params) {
        assert.equal(command, 'job_list');
        calls.push(params);
        return { jobs: pages[params.cursor ? 1 : 0], next_cursor: params.cursor ? null : 'page2' };
      } },
    });
    const response = await service.handle({ method: 'monitor/overview' });
    assert.equal(response.error, null);
    assert.equal(calls.length, 2);
    for (const params of calls) {
      assert.equal(params.session_id, 's');
      assert.equal(params.user_task_id, current?.user_task_id);
    }
    const jobs = response.result.jobs;
    assert.equal(jobs.scope, current ? 'task' : 'session');
    assert.deepEqual(jobs.counts, { running: 2, queued: 4, total: 8 });
    assert.equal(jobs.active.length, 5);
    assert.equal(jobs.active_omitted, 1);
    assert.equal(jobs.active.some(job => ['succeeded', 'failed'].includes(job.state)), false);
    assert.ok(jobs.active.every(job => Object.keys(job).sort().join(',') === 'job_id,state'));
  }
});

test('effective continuation respects controls, health, policy and recovery before promising a wakeup', () => {
  const now = Date.parse('2026-10-19T00:00:00Z');
  const health = { automatic_continuation_enabled: true, last_checked_at: new Date(now).toISOString(), check_interval_ms: 1000 };
  const state = (value, h = health) => projectMonitorContinuation(value, h, now).state;
  assert.equal(state(null), 'idle');
  for (const terminal of ['completed', 'cancelled']) assert.equal(state({ ...task, state: terminal }), 'idle');
  for (const control of ['paused', 'blocked']) assert.equal(state({ ...task, state: control }, { ...health, error: {} }), control);
  assert.equal(state(task, { ...health, error: {} }), 'error');
  assert.equal(state(task, { ...health, automatic_continuation_enabled: false }), 'disabled');
  assert.equal(state(task, { ...health, last_checked_at: null }), 'checking');
  for (const last_checked_at of ['invalid', new Date(now - 31000).toISOString()]) {
    assert.equal(state(task, { ...health, last_checked_at }), 'overdue');
  }
  assert.equal(state(task, { ...health, check_interval_ms: undefined, last_checked_at: new Date(now - 31000).toISOString() }), 'overdue');
  assert.equal(state({ ...task, execution_recovery: { state: 'attention_required' } }), 'attention_required');
  assert.equal(state({ ...task, execution_recovery: { state: 'retrying' } }), 'retrying');
  assert.equal(state({ ...task, state: 'waiting' }), 'waiting');
  assert.equal(state({ ...task, state: 'waiting' }, { ...health, automatic_continuation_enabled: false }), 'disabled');
  assert.equal(state({ ...task, continuation: { reservation: {} } }), 'pending');
  assert.equal(state(task), 'ready');
});

test('overview explains next action and blocker recovery without review internals or false wakeup promises', () => {
  const blocked = { ...task, state: 'blocked', next_action: 'Compare the two verified datasets',
    reason: 'The reference dataset is missing', block_details: { resume_when: 'Provide the reference dataset' } };
  const view = formatMonitor('monitor/overview', { task: projectMonitorTask(blocked), continuation: { state: 'blocked' },
    execution: { state: 'idle' }, jobs: { scope: 'task', counts: {}, active: [], active_omitted: 0 } });
  assert.match(view, /Next: Compare the two verified datasets/);
  assert.match(view, /To resume: Provide the reference dataset/);
  assert.match(view, /Status: Stopped/);
  assert.doesNotMatch(view, /sha256|brief_state|Continues when ready|Automatic continuation: On/);
  const detail = formatMonitor('monitor/task/read', { task: blocked, research: snapshot, session_job_ids: [] });
  assert.match(detail, /To resume: Provide the reference dataset/);
});

test('the same Stopped label retains distinct causes and resume guidance in overview', () => {
  const cases = [
    ['paused', 'paused', /The task is paused/],
    ['cancelled', 'idle', /The task was cancelled/],
    ['blocked', 'blocked', /Research is blocked/],
    ['active', 'disabled', /Automatic continuation is off.*\/monitor health/],
    ['active', 'error', /Automatic continuation failed.*\/monitor health/],
    ['active', 'attention_required', /Execution recovery needs attention.*execution records/],
  ];
  for (const [state, continuation, explanation] of cases) {
    const view = formatMonitor('monitor/overview', { task: projectMonitorTask({ ...task, state }),
      execution: { state: 'idle' }, continuation: { state: continuation } });
    assert.match(view, /Status: Stopped/);
    assert.match(view, explanation);
  }
});
