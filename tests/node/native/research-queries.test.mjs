import assert from 'node:assert/strict';
import test from 'node:test';
import { createClientQueries } from '../../../apps/agent/runtime/services/queries.mjs';

const task = {
  user_task_id: 'task_7', revision: 3, title: 'Compare reaction paths',
  objective: 'Determine which reaction path is supported by the evidence', state: 'waiting',
  next_action: 'Validate the new structures before comparing energies',
  updated_at: '2026-10-24T10:00:00Z',
  research: { entry_node_ids: ['node_2'], focus_node_ids: ['node_4'] },
  wait: { mode: 'all', job_ids: ['job_6', 'job_7'] },
  progress: { summary: 'Candidate structures saved', at: '2026-10-24T09:00:00Z' },
  continuation: { reservation: 'internal-reservation' },
  sources: [{ text: 'Original user input', submission_id: 'submission_8' }],
};

test('default research reads the current task scope through the canonical brief without mutating it', async () => {
  const original = structuredClone(task), calls = [], contexts = [];
  const brief = { schema_version: 'research-brief/1', findings: [{ ref: 'node_4', kind: 'node' }] };
  const context = { abortSignal: new AbortController().signal };
  const queries = createClientQueries({ workspaceId: 'worker-workspace', sessionId: 'worker-session',
    async currentTask(value) { contexts.push(value); return task; },
    queryBridge: { async execute_command(command, params) { calls.push([command, params]); return brief; } },
  });
  const response = await queries.research('  ', context);
  assert.equal(response.workspace_id, 'worker-workspace');
  assert.equal(response.session_id, 'worker-session');
  assert.equal(response.result, brief);
  assert.deepEqual(contexts, [context]);
  assert.deepEqual(calls, [['research_read', {
    view: 'brief', session_id: 'worker-session', entry_node_ids: ['node_2'], focus_node_ids: ['node_4'],
    waited_job_ids: ['job_6', 'job_7'], limit: 32000,
  }]]);
  assert.equal(response.task.user_task_id, 'task_7');
  assert.equal(response.task.state, 'waiting');
  assert.equal(response.task.objective, task.objective);
  assert.equal(response.task.next_action, task.next_action);
  assert.equal(response.task.updated_at, task.updated_at);
  assert.deepEqual(response.task.wait, { mode: 'all', job_count: 2 });
  assert.equal(response.task.continuation, undefined);
  assert.equal(response.task.sources, undefined);
  assert.deepEqual(task, original);
});

test('unbound research suppresses the session-recent fallback while preserving worker identity', async () => {
  for (const current of [null, { ...task, research: { entry_node_ids: [], focus_node_ids: [] }, wait: null }]) {
    const calls = [];
    const queries = createClientQueries({ workspaceId: 'worker-workspace', sessionId: 'worker-session',
      async currentTask() { return current; },
      queryBridge: { async execute_command(command, params) { calls.push([command, params]); return { findings: [] }; } },
    });
    const response = await queries.research('');
    assert.deepEqual(calls, [['research_read', {
      view: 'brief', session_id: null, entry_node_ids: [], focus_node_ids: [], waited_job_ids: [], limit: 32000,
    }]]);
    assert.equal(response.workspace_id, 'worker-workspace');
    assert.equal(response.session_id, 'worker-session');
    assert.equal(response.task?.user_task_id ?? null, current?.user_task_id ?? null);
    assert.deepEqual(response.result.findings, []);
  }
});

test('stopped task research stays readable with its actual lifecycle state', async () => {
  const queries = createClientQueries({ workspaceId: 'w', sessionId: 's',
    async currentTask() { return { ...task, state: 'cancelled', wait: null, reason: 'Stopped by user' }; },
    queryBridge: { async execute_command() { return { status: 'uncertain', findings: [] }; } },
  });
  const response = await queries.research('');
  assert.equal(response.task.state, 'cancelled');
  assert.equal(response.task.reason, 'Stopped by user');
  assert.equal(response.result.status, 'uncertain');
});

test('waiting on a job without linked research does not enable unrelated session fallback', async () => {
  let request;
  const queries = createClientQueries({ workspaceId: 'w', sessionId: 's',
    async currentTask() { return { ...task, research: { entry_node_ids: [], focus_node_ids: [] } }; },
    queryBridge: { async execute_command(command, params) { request = params; return { findings: [] }; } },
  });
  await queries.research('');
  assert.equal(request.session_id, null);
  assert.deepEqual(request.waited_job_ids, ['job_6', 'job_7']);
});

test('research browsing and search stay workspace-wide and do not depend on task availability', async () => {
  const calls = [];
  const queries = createClientQueries({ workspaceId: 'w', sessionId: 's',
    async currentTask() { throw new Error('Explicit browsing must not read task state'); },
    queryBridge: { async execute_command(command, params) { calls.push([command, params]); return { content: 'record' }; } },
  });
  for (const input of ['read', 'read --offset 20', 'search competing paths']) {
    assert.deepEqual(await queries.research(input), { workspace_id: 'w', session_id: 's', result: { content: 'record' } });
  }
  assert.deepEqual(calls, [
    ['research_search', { kind: 'node', query: '' }],
    ['research_search', { kind: 'node', query: '', offset: 20 }],
    ['research_search', { query: 'competing paths' }],
  ]);
});

function pagesFor(text, ref = 'node_4', width = 7) {
  const characters = [...text];
  return Array.from({ length: Math.ceil(characters.length / width) }, (_, index) => {
    const offset = index * width, end = Math.min(offset + width, characters.length);
    return { schema_version: 'research-read/2', ref, content_sha256: 'sha256:consistent-record',
      node_revision: 3, text: characters.slice(offset, end).join(''), offset,
      offset_unit: 'unicode_characters', total_characters: characters.length,
      next_offset: end < characters.length ? end : null };
  });
}

test('explicit records assemble complete Unicode content from consistent canonical pages', async () => {
  const text = JSON.stringify({ node: { title: '反应路径 🧪', goal: '保留全部判断与限制' } });
  const pages = pagesFor(text), calls = [];
  pages[0].read_basis = { node_id: 'node_4', fields: ['title'] };
  pages[1].read_basis = { node_id: 'node_4', fields: ['goal'] };
  const first = structuredClone(pages[0]);
  const queries = createClientQueries({ workspaceId: 'w', sessionId: 's', currentTask: assert.fail,
    queryBridge: { async execute_command(command, params) { calls.push([command, params]); return pages.shift(); } },
  });
  const response = await queries.research('read node_4');
  assert.deepEqual(response, { workspace_id: 'w', session_id: 's',
    result: { ...first, text, offset: 0, next_offset: null } });
  assert.ok(calls.length > 1);
  for (const [index, [command, params]] of calls.entries()) {
    assert.equal(command, 'research_read');
    assert.deepEqual(params, { ref: 'node_4', offset: index * 7, limit: 32000 });
  }
});

test('record updates during pagination return a reopen error without mixing revisions or retrying', async () => {
  for (const [key, value] of [
    ['content_sha256', 'sha256:changed-record'], ['ref', 'node_9'], ['total_characters', 100], ['node_revision', 4],
  ]) {
    const pages = pagesFor(JSON.stringify({ node: { title: 'Current judgment' } }));
    pages[1][key] = value;
    let reads = 0;
    const queries = createClientQueries({ workspaceId: 'w', sessionId: 's', currentTask: assert.fail,
      queryBridge: { async execute_command() { reads++; return pages.shift(); } },
    });
    const response = await queries.research('read node_4');
    assert.equal(response.result, null);
    assert.equal(response.error.code, 'research_changed');
    assert.match(response.error.message, /Open this record again/);
    assert.equal(reads, 2);
  }
});

test('inconsistent record pagination cannot silently skip content or loop', async () => {
  for (const change of [
    { next_offset: 0 }, { next_offset: 8 }, { offset: 2 }, { text: '' }, { offset_unit: 'bytes' },
  ]) {
    const pages = pagesFor(JSON.stringify({ node: { title: 'Current judgment' } }));
    Object.assign(pages[0], change);
    let reads = 0;
    const queries = createClientQueries({ workspaceId: 'w', sessionId: 's', currentTask: assert.fail,
      queryBridge: { async execute_command() { reads++; return pages.shift(); } },
    });
    const response = await queries.research('read node_4');
    assert.equal(response.result, null);
    assert.equal(response.error.code, 'research_page_invalid');
    assert.equal(reads, 1);
  }
});

test('abort and query errors discard partial records', async () => {
  for (const failure of ['abort', 'query']) {
    const controller = new AbortController(), pages = pagesFor(JSON.stringify({ node: { title: 'Current judgment' } }));
    let reads = 0;
    const queries = createClientQueries({ workspaceId: 'w', sessionId: 's', currentTask: assert.fail,
      queryBridge: { async execute_command() {
        reads++;
        if (reads === 2) {
          if (failure === 'abort') controller.abort();
          else throw Object.assign(new Error('Query timed out'), { code: 'research_timeout' });
        }
        return pages.shift();
      } },
    });
    const response = await queries.research('read node_4', { abortSignal: controller.signal });
    assert.equal(response.result, null);
    assert.equal(response.error.code, failure === 'abort' ? 20 : 'research_timeout');
    assert.equal(reads, 2);
  }
});

test('malformed or mutation arguments cannot invoke the query bridge or current task', async () => {
  const calls = [];
  const queries = createClientQueries({ workspaceId: 'w', sessionId: 's',
    currentTask: async () => { calls.push('task'); },
    queryBridge: { async execute_command() { calls.push('query'); } },
  });
  for (const input of ['update node_2', 'read node_2 extra', 'task resume task_7', { session_id: 'other' }]) {
    const response = await queries.research(input);
    assert.equal(response.workspace_id, 'w');
    assert.equal(response.session_id, 's');
    assert.equal(response.result, null);
    assert.ok(response.error.message);
  }
  assert.deepEqual(calls, []);
});

test('task and research failures retain useful details without substituting stale results', async () => {
  for (const failure of ['task', 'research']) {
    const error = Object.assign(new Error('Current research unavailable'), {
      code: 'research_unavailable', details: { request_id: 'query_4' },
    });
    const queries = createClientQueries({ workspaceId: 'w', sessionId: 's',
      async currentTask() { if (failure === 'task') throw error; return task; },
      queryBridge: { async execute_command() { throw error; } },
    });
    assert.deepEqual(await queries.research(''), {
      workspace_id: 'w', session_id: 's', result: null,
      error: { code: 'research_unavailable', message: 'Current research unavailable', details: { request_id: 'query_4' } },
    });
  }
});

test('aborted task reads do not continue into research queries', async () => {
  const controller = new AbortController();
  const queries = createClientQueries({ workspaceId: 'w', sessionId: 's',
    async currentTask() { controller.abort(); return task; },
    queryBridge: { execute_command: assert.fail },
  });
  const response = await queries.research('', { abortSignal: controller.signal });
  assert.equal(response.result, null);
  assert.equal(response.error.code, 20);
  await assert.rejects(queries.research('', { abortSignal: controller.signal }), { name: 'AbortError' });
});
