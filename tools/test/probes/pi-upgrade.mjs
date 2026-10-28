import assert from 'node:assert/strict';
import test from 'node:test';
import { fork, execFile } from 'node:child_process';
import { createServer } from 'node:http';
import { mkdir, mkdtemp, rm, writeFile, readFile, copyFile, access, cp } from 'node:fs/promises';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { promisify } from 'node:util';
import { setTimeout as delay } from 'node:timers/promises';
import { DatabaseSync } from 'node:sqlite';

const legacy = process.env.CORAGENT_TEST_LEGACY_SOURCE;
const candidate = process.env.CORAGENT_TEST_CANDIDATE_SOURCE;
const execute = promisify(execFile);
const childPath = fileURLToPath(new URL('./pi-upgrade-worker.mjs', import.meta.url));
async function until(predicate) {
  for (let i = 0; i < 600; i++) { const value = await predicate(); if (value) return value; await delay(50); }
  assert.fail('Rehearsal condition timed out');
}
function schema(path) {
  const db = new DatabaseSync(path, { readOnly: true });
  try { return db.prepare('SELECT version FROM durable_schema').get().version; } finally { db.close(); }
}
function messages(view) { return view.entries.flatMap(entry => entry.model || []); }
function text(view) { return JSON.stringify(messages(view)); }

async function fixture(t) {
  const root = await mkdtemp(join(process.env.CORAGENT_TEST_ROOT, 'upgrade-'));
  const cwd = join(root, 'workspace'), agent = join(root, 'agent'), sessionPath = join(root, 'sessions', 'work', 'legacy');
  await mkdir(agent); await mkdir(sessionPath, { recursive: true });
  await execute(process.env.CORAGENT_PYTHON, [join(legacy, 'apps/cli/workspace_mode.py'), '--root', cwd, '--workspace-id', 'work']);
  await writeFile(join(cwd, 'input.txt'), 'Synthetic legacy input. 中文资料。\n');
  const metadata = { id: 'legacy', sessionId: 'legacy', workspaceId: 'work', cwd, path: sessionPath, createdAt: Date.now() };
  await writeFile(join(sessionPath, 'meta.json'), JSON.stringify({ createdAt: metadata.createdAt, cwd, workspaceId: 'work' }));
  const calls = [], children = new Set(), sockets = new Set();
  let reply = () => 'Synthetic answer.', failure;
  const server = createServer(async (req, res) => {
    try {
      let raw = ''; for await (const part of req) raw += part;
      const request = JSON.parse(raw); calls.push(request);
      const step = await reply(request);
      res.writeHead(200, { 'content-type': 'text/event-stream' });
      const delta = typeof step === 'string' ? { role: 'assistant', content: step } : step.hold
        ? { role: 'assistant', content: 'Interrupted draft' }
        : { role: 'assistant', tool_calls: [{ index: 0, id: `call_${calls.length}`, type: 'function', function: { name: step.name, arguments: JSON.stringify(step.arguments) } }] };
      res.write(`data: ${JSON.stringify({ id: `reply_${calls.length}`, object: 'chat.completion.chunk', created: 1, model: 'fixture', choices: [{ index: 0, delta, finish_reason: null }] })}\n\n`);
      if (step.hold) return;
      res.write(`data: ${JSON.stringify({ id: `reply_${calls.length}`, object: 'chat.completion.chunk', created: 1, model: 'fixture', choices: [{ index: 0, delta: {}, finish_reason: typeof step === 'string' ? 'stop' : 'tool_calls' }] })}\n\n`);
      res.end('data: [DONE]\n\n');
    } catch (error) { failure = error; res.writeHead(500); res.end('Synthetic fixture failed'); }
  });
  server.on('connection', socket => { sockets.add(socket); socket.on('close', () => sockets.delete(socket)); });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  await writeFile(join(agent, 'models.json'), JSON.stringify({ providers: { fixture: {
    api: 'openai-completions', apiKey: 'fixture-only', baseUrl: `http://127.0.0.1:${server.address().port}/v1`,
    models: [{ id: 'fixture', name: 'Fixture', reasoning: false, input: ['text'], contextWindow: 200000, maxTokens: 4096,
      cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 } }],
  } } }));
  await writeFile(join(agent, 'settings.json'), JSON.stringify({ retry: { enabled: false }, compaction: { enabled: false, keepRecentTokens: 0 } }));
  function launch(side) {
    const product = side === 'legacy' ? legacy : candidate;
    const pi = side === 'legacy' ? process.env.CORAGENT_TEST_LEGACY_PI : process.env.CORAGENT_TEST_PI_RUNTIME_ROOT;
    const child = fork(childPath, [], { detached: true, cwd, execArgv: ['--import', join(pi, 'packages/coding-agent/src/experimental/source-resolver.ts')],
      env: { ...process.env, CORAGENT_UPGRADE_SIDE: side, CORAGENT_PACKAGE_ROOT: product, CORAGENT_PI_RUNTIME_ROOT: pi,
        CORAGENT_INPUT_PRODUCER_TOKEN: 'fixture-only', CORAGENT_AUTOMATIC_CONTINUATION: '0', CORAGENT_DEBUG: '1',
        PI_AGENT_DIR: agent, PI_CODING_AGENT_DIR: agent,
        PYTHONPATH: [join(product, 'backend/src'), join(product, 'packaging'), product].join(':') },
      stdio: ['ignore', 'inherit', 'inherit', 'ipc'] });
    children.add(child);
    const pending = new Map(); let next = 0;
    const exited = new Promise(resolve => child.once('exit', resolve));
    child.on('message', message => {
      const entry = pending.get(message.id); if (!entry) return;
      pending.delete(message.id); clearTimeout(entry.timer);
      if (message.error) entry.reject(Object.assign(new Error(message.error.message), message.error)); else entry.resolve(message.result);
    });
    child.once('exit', () => {
      children.delete(child);
      for (const entry of pending.values()) { clearTimeout(entry.timer); entry.reject(new Error('Rehearsal process exited')); }
      pending.clear();
    });
    function request(method, params = {}) {
      return new Promise((resolve, reject) => {
        const id = ++next, timer = setTimeout(() => { pending.delete(id); reject(new Error(`Rehearsal RPC timed out: ${method}`)); }, 45000);
        pending.set(id, { resolve, reject, timer }); child.send({ id, method, params });
      });
    }
    return { request, async open() { await request('open', { metadata }); }, async close() { await request('close'); await exited; },
      async crash() { process.kill(-child.pid, 'SIGKILL'); await exited; } };
  }
  t.after(async () => {
    for (const child of children) { try { process.kill(-child.pid, 'SIGKILL'); } catch {} }
    for (const socket of sockets) socket.destroy();
    await new Promise(resolve => server.close(resolve));
    await rm(root, { recursive: true, force: true });
  });
  return { root, cwd, database: join(sessionPath, 'session.sqlite'), calls, launch, metadata,
    reply(fn) { reply = fn; }, check() { assert.ifError(failure); },
    async done(client, requestId) { return until(async () => { assert.ifError(failure); const value = await client.request('status', { requestId });
      if (value?.status === 'unanswered') assert.fail(JSON.stringify(value)); return value?.status === 'done' && value; }); } };
}

test('legacy history and compaction survive upgrade and backup restores a working 1.1 session', { timeout: 120000 }, async t => {
  const f = await fixture(t); let client = f.launch('legacy'); await client.open();
  for (let i = 0; i < 3; i++) {
    f.reply(() => `LEGACY ANSWER ${i}: ` + '中文长文本。'.repeat(800));
    await client.request('submit', { requestId: `history-${i}`, content: `LEGACY INPUT ${i}: ` + '保留研究约束。'.repeat(800) });
    await f.done(client, `history-${i}`);
  }
  f.reply(() => 'MIGRATION SUMMARY: preserve the synthetic research constraints.');
  await client.request('compact', { instructions: 'Preserve research constraints.' });
  const before = await until(async () => { const view = await client.request('view'); return view.entries.some(e => e.kind === 'pi.compaction') && view; });
  await client.close(); assert.equal(schema(f.database), 1);
  await cp(f.cwd, join(f.root, 'workspace-backup'), { recursive: true });
  client = f.launch('candidate'); await client.open();
  assert.equal(schema(f.database), 2); assert.equal(schema(f.database + '.pre-pi-1.4'), 1);
  assert.deepEqual((await client.request('view')).entries, before.entries);
  f.reply(request => { assert.match(JSON.stringify(request.messages), /MIGRATION SUMMARY/); return 'NEW VERSION ANSWER'; });
  await client.request('submit', { requestId: 'new-version', content: 'Continue after upgrade.' }); await f.done(client, 'new-version');
  assert.match(text(await client.request('view')), /NEW VERSION ANSWER/);
  await client.close();
  await copyFile(f.database + '.pre-pi-1.4', f.database);
  for (const suffix of ['-wal', '-shm']) await rm(f.database + suffix, { force: true });
  await rm(f.cwd, { recursive: true }); await cp(join(f.root, 'workspace-backup'), f.cwd, { recursive: true });
  client = f.launch('legacy'); await client.open();
  assert.equal(schema(f.database), 1); assert.deepEqual((await client.request('view')).entries, before.entries);
  f.reply(() => 'ROLLBACK ANSWER');
  await client.request('submit', { requestId: 'rollback', content: 'Continue after rollback.' }); await f.done(client, 'rollback');
  assert.match(text(await client.request('view')), /ROLLBACK ANSWER/); await client.close(); f.check();
});

test('legacy blocked research and its evidence remain blocked after upgrade', { timeout: 90000 }, async t => {
  const f = await fixture(t); let step = 0;
  f.reply(request => {
    const envelope = request.messages.findLast(message => typeof message.content === 'string' && message.content.startsWith('<runtime_control origin="runtime">'));
    const state = JSON.parse(envelope.content.split('\n')[1]);
    return [
      { name: 'task_begin', arguments: { title: 'Migration research', objective: 'Retain synthetic research through upgrade.', source_submission_ids: state.actual_user_submission_ids,
        criteria: [{ id: 'finding', description: 'Retain a reproducible finding.' }], next_action: 'Create a research Node.' } },
      { name: 'research_create', arguments: { title: 'Migration evidence', goal: 'Retain the synthetic observation.', plan: 'Wait for missing input.' } },
      { name: 'task_update', arguments: { action: 'block', expected_revision: state.task?.revision, block_kind: 'missing_user_input',
        reason: 'A boundary value is required.', resume_when: 'The user supplies a boundary value.' } },
      'Blocked pending a boundary value.',
    ][step++] ?? assert.fail('Blocked research resumed unexpectedly');
  });
  let client = f.launch('legacy'); await client.open();
  await client.request('submit', { requestId: 'research', content: 'Start the synthetic migration research.' }); await f.done(client, 'research');
  const before = await client.request('view'), beforeTask = await client.request('task'); assert.equal(beforeTask?.state, 'blocked');
  assert.equal(beforeTask.research.entry_node_ids.length, 1);
  await client.close(); client = f.launch('candidate'); await client.open();
  const after = await client.request('view'), afterTask = await client.request('task');
  for (const [key, value] of Object.entries(beforeTask)) assert.deepEqual(afterTask[key], value, `Task field preserved: ${key}`);
  assert.deepEqual(after.entries, before.entries); await delay(500); assert.equal(step, 4);
  step = 0;
  f.reply(request => {
    const envelope = request.messages.findLast(message => typeof message.content === 'string' && message.content.startsWith('<runtime_control origin="runtime">'));
    const state = JSON.parse(envelope.content.split('\n')[1]);
    return [
      { name: 'task_update', arguments: { action: 'refine', expected_revision: state.task.revision, source_submission_ids: state.actual_user_submission_ids } },
      { name: 'research_result', arguments: { node_id: beforeTask.research.entry_node_ids[0], conclusion: 'The supplied synthetic boundary value is zero.' } },
      { name: 'task_update', arguments: { action: 'block', expected_revision: state.task.revision, block_kind: 'missing_user_input',
        reason: 'The next synthetic input is required.', resume_when: 'The user supplies the next input.' } },
      'UPGRADED RESEARCH CONTINUED',
    ][step++] ?? assert.fail('Unexpected research continuation');
  });
  await client.request('submit', { requestId: 'resume-research', content: 'Use boundary value zero and continue the research.' });
  await f.done(client, 'resume-research');
  const resumed = await client.request('task');
  assert.equal(resumed.user_task_id, beforeTask.user_task_id);
  assert.deepEqual(resumed.research, beforeTask.research);
  assert.match(text(await client.request('view')), /UPGRADED RESEARCH CONTINUED/);
  assert.equal(step, 4);
  await client.close(); f.check();
});

test('a 1.1 generation interrupted by process death resumes in the 1.4 Worker', { timeout: 90000 }, async t => {
  const f = await fixture(t); f.reply(() => ({ hold: true }));
  let client = f.launch('legacy'); await client.open();
  await client.request('submit', { requestId: 'inflight-generation', content: 'Recover this interrupted generation.' });
  await until(() => f.calls.length === 1); await client.crash();
  assert.equal(schema(f.database), 1);
  f.reply(() => 'RECOVERED GENERATION'); client = f.launch('candidate'); await client.open();
  await f.done(client, 'inflight-generation');
  const view = await client.request('view');
  assert.equal(messages(view).filter(m => m.role === 'user' && JSON.stringify(m.content).includes('Recover this interrupted generation.')).length, 1);
  assert.match(text(view), /RECOVERED GENERATION/); assert.equal(f.calls.length, 2);
  await client.close(); f.check();
});

test('a 1.1 tool checkpoint resumes without repeating its preceding completed tool', { timeout: 90000 }, async t => {
  const f = await fixture(t); let step = 0;
  const command = 'printf entered > migration-tool-entered; while [ ! -f migration-tool-release ]; do sleep 0.05; done; printf "RECOVERED TOOL" > migration-tool-result; cat migration-tool-result';
  f.reply(request => {
    if (step === 2) assert.match(request.messages.filter(m => m.role === 'tool').at(-1).content, /interrupted/i);
    return [
    { name: 'read', arguments: { path: 'input.txt' } },
    { name: 'bash', arguments: { command } },
    // The old OS process died. A new explicit call retries this idempotent fixture only.
    { name: 'bash', arguments: { command } },
    'RECOVERED TOOL ANSWER',
  ][step++] ?? assert.fail('Unexpected extra tool generation'); });
  let client = f.launch('legacy'); await client.open();
  await client.request('submit', { requestId: 'inflight-tool', content: 'Read the fixture input, then run the gated local command.' });
  await until(async () => { try { await access(join(f.cwd, 'migration-tool-entered')); return true; } catch { return false; } });
  await client.crash(); await writeFile(join(f.cwd, 'migration-tool-release'), 'release');
  client = f.launch('candidate'); await client.open(); await f.done(client, 'inflight-tool');
  const view = await client.request('view'), results = messages(view).filter(m => m.role === 'toolResult');
  await writeFile(join(process.env.CORAGENT_TEST_RUN_ROOT, 'report/upgrade-tool-results.json'), JSON.stringify(results));
  assert.equal(results.filter(m => m.toolName === 'read').length, 1);
  const shellResults = results.filter(m => m.toolName === 'bash');
  assert.equal(shellResults.length, 2);
  assert.equal(shellResults[0].isError, true);
  assert.match(JSON.stringify(shellResults[0].content), /interrupted/i);
  assert.equal(Boolean(shellResults[1].isError), false);
  assert.equal(await readFile(join(f.cwd, 'migration-tool-result'), 'utf8'), 'RECOVERED TOOL');
  assert.match(text(view), /RECOVERED TOOL ANSWER/); assert.equal(step, 4);
  await client.close(); f.check();
});
