import assert from 'node:assert/strict';
import test from 'node:test';
import { existsSync } from 'node:fs';
import { mkdtemp, readFile, rm, writeFile } from 'node:fs/promises';
import { join } from 'node:path';
import { setTimeout as delay } from 'node:timers/promises';
import { TEST_ROOT } from './test-environment.mjs';
import { create_python_runtime_bridge, create_query_runtime_bridge } from '../../../apps/agent/bridge/client.mjs';
import { create_jsonl_subprocess_transport } from '../../../apps/agent/bridge/transport.mjs';
import { createClientQueries } from '../../../apps/agent/runtime/services/queries.mjs';
import { attachToolErrorEnvelope } from '../../../apps/agent/tools/envelope.mjs';

// A gated, serial JSONL server: releasing the file lets the current operation
// finish. No timing guess is needed to put execution in front of a UI query.
const server = `
import { createInterface } from 'node:readline';
import { existsSync, appendFileSync, writeFileSync } from 'node:fs';
import { setTimeout as delay } from 'node:timers/promises';
for await (const line of createInterface({ input: process.stdin })) {
  const { id, payload } = JSON.parse(line);
  appendFileSync('calls', payload.command + '\\n');
  if (payload.params?.hold) {
    writeFileSync('started', '');
    while (!existsSync('release')) await delay(5);
  }
  console.log(JSON.stringify({ id, ok: true, result: { command: payload.command } }));
}
`;
async function fixture(t, options = {}) {
  const root = await mkdtemp(join(TEST_ROOT, 'query-bridge-'));
  const script = join(root, 'server.mjs');
  await writeFile(script, server);
  t.after(() => rm(root, { recursive: true, force: true }));
  return { root, options: { workspace_root: root, command: process.execPath, args: [script], cwd: root, ...options } };
}
async function until(check) {
  const deadline = Date.now() + 5000;
  while (!await check()) {
    assert.ok(Date.now() < deadline, 'gated worker did not reach its expected state');
    await delay(10);
  }
}

test('terminal queries use an independent worker while execution is blocked', async t => {
  const { root, options } = await fixture(t);
  const execution = create_python_runtime_bridge(options);
  const query = create_query_runtime_bridge(options);
  try {
    let finished = false;
    const slow = execution.execute_command('job_status', { hold: true }).then(result => { finished = true; return result; });
    await until(() => existsSync(join(root, 'started')));
    const queries = createClientQueries({ workspaceId: 'fixture', sessionId: 'session', queryBridge: query });
    const response = await queries.research('');
    assert.equal(response.result.command, 'research_read');
    assert.equal(finished, false);
    assert.equal((await query.execute_command('job_list')).command, 'job_list');
    assert.throws(() => query.execute_command('job_status'), /Not a local runtime query/);
    assert.throws(() => query.execute_command('research_create'), /Not a local runtime query/);
    assert.equal(query.transaction_commit, undefined);
    await writeFile(join(root, 'release'), '');
    assert.equal((await slow).command, 'job_status');
  } finally { await Promise.all([execution.close(), query.close()]); }
});

test('query backpressure survives timeout and coalesces requests until the actual reply', async t => {
  const { root, options } = await fixture(t, { timeout_ms: 800, max_pending: 2, coalesce: true });
  const transport = create_jsonl_subprocess_transport(options);
  const held = { command: 'research_read', params: { hold: true } };
  const capture = promise => promise.then(value => ({ value }), error => ({ error }));
  try {
    const first = capture(transport.request('execute_command', held));
    const duplicate = capture(transport.request('execute_command', held));
    await until(() => existsSync(join(root, 'started')));
    const second = capture(transport.request('execute_command', { command: 'job_list' }));
    await assert.rejects(transport.request('execute_command', { command: 'research_search' }), { code: 'kernel_request_busy' });
    const { error } = await first;
    assert.equal(error.code, 'kernel_request_timeout');
    assert.equal(error.details.command, 'research_read');
    assert.equal(error.details.pending_requests, 2);
    assert.ok(error.details.elapsed_ms >= 800);
    assert.deepEqual(error.details.outstanding.map(item => item.command), ['research_read', 'job_list']);
    assert.equal((await duplicate).error, error);
    assert.equal((await second).error.code, 'kernel_request_timeout');
    // A timed-out request may still execute. A new refresh must not enqueue it again.
    assert.equal((await capture(transport.request('execute_command', held))).error, error);
    await assert.rejects(transport.request('execute_command', { command: 'research_search' }), { code: 'kernel_request_busy' });
    assert.equal(await readFile(join(root, 'calls'), 'utf8'), 'research_read\n');
    await writeFile(join(root, 'release'), '');
    // Actual late replies release capacity and permit a fresh observation.
    await until(async () => {
      const result = await capture(transport.request('execute_command', { command: 'research_search' }));
      return Boolean(result.value);
    });
    assert.equal((await transport.request('execute_command', held)).command, 'research_read');
    const calls = (await readFile(join(root, 'calls'), 'utf8')).trim().split('\n');
    assert.equal(calls.filter(command => command === 'research_read').length, 2);
    assert.equal(calls.filter(command => command === 'job_list').length, 1);
  } finally { await transport.close(); }
});

test('closing a query worker rejects outstanding reads and releases its process', async t => {
  const { root, options } = await fixture(t);
  const query = create_query_runtime_bridge(options);
  const pending = assert.rejects(query.execute_command('research_read', { hold: true }), { code: 'transport_closed' });
  try { await until(() => existsSync(join(root, 'started'))); }
  finally { await query.close(); }
  await pending;
  await assert.rejects(query.execute_command('research_read'), { code: 'transport_closed' });
  await query.close();
});

test('a sent mutation that times out has an unknown outcome and is not safe to retry', async t => {
  const { root, options } = await fixture(t, { timeout_ms: 800, max_pending: 1 });
  const execution = create_python_runtime_bridge(options);
  const outcome = execution.execute_command('job_start', { hold: true }).catch(error => error);
  try {
    await until(() => existsSync(join(root, 'started')));
    const error = await outcome;
    assert.equal(error.code, 'kernel_request_timeout');
    const envelope = attachToolErrorEnvelope(error, 'job_start', 'call-1').toolEnvelope;
    assert.equal(envelope.error.failure_class, 'ambiguous');
    assert.equal(envelope.error.action_outcome, 'unknown');
    assert.equal(envelope.error.retryable, false);
    await assert.rejects(execution.execute_command('job_start'), error => {
      const { error: failure } = attachToolErrorEnvelope(error, 'job_start', 'call-2').toolEnvelope;
      assert.equal(failure.code, 'kernel_request_busy');
      assert.equal(failure.action_outcome, 'not_executed');
      assert.equal(failure.retryable, true);
      return true;
    });
    await writeFile(join(root, 'release'), '');
    await until(async () => {
      try { await execution.execute_command('job_list'); return true; }
      catch (error) { if (error.code === 'kernel_request_busy') return false; throw error; }
    });
    assert.equal((await readFile(join(root, 'calls'), 'utf8')).trim(), 'job_start\njob_list');
  } finally { await execution.close(); }
});
