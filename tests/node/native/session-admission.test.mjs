import assert from 'node:assert/strict';
import test from 'node:test';
import { join } from 'node:path';
import { pathToFileURL } from 'node:url';
import { Harness, MemoryStorage, createRegistry, LiveDoc, InboxDoc } from '@earendil-works/pi-durable';
import { createModels, fauxProvider, fauxAssistantMessage } from '@earendil-works/pi-ai';
import { TODO_CONTEXT as context } from '@earendil-works/chord/context';
import { pinnedPiSource } from './test-environment.mjs';
import { createSessionAdmission } from '../../../apps/agent/runtime/admission/session.mjs';
import { createInputAdmission } from '../../../apps/agent/runtime/admission/input.mjs';
import { createTaskController, UserTasks } from '../../../apps/agent/tasks/controller.mjs';

test('interrupt aborts its active turn; a late retry leaves the next turn running', { timeout: 10000 }, async t => {
  const faux = fauxProvider();
  const models = createModels(); models.setProvider(faux.provider);
  const harness = await Harness.open(new MemoryStorage(), { models, registry: createRegistry(), settings: {} }, context);
  t.after(() => harness.close(context));
  const conversation = await harness.root(context, { agent: { model: { provider: 'faux', modelId: 'faux-1' } } });
  const admission = createSessionAdmission({ harness, conversation, LiveDoc });
  const start = async content => {
    let reached; let aborted = false;
    const ready = new Promise(resolve => { reached = resolve; });
    faux.setResponses([(_ctx, options) => new Promise((_, reject) => {
      reached(); options.signal.addEventListener('abort', () => { aborted = true; reject(options.signal.reason); }, { once: true });
    })]);
    const submission = await conversation.submit({ type: 'input', content }, context);
    await ready;
    return { id: String(submission.id), aborted: () => aborted };
  };
  const first = await start('first');
  assert.equal((await admission.interrupt({ turnId: 'unrelated' }, context)).accepted, false);
  assert.equal(first.aborted(), false);
  assert.equal((await admission.interrupt({ turnId: first.id }, context)).accepted, true);
  await conversation.waitForIdle(context);
  assert.equal(first.aborted(), true);
  const second = await start('second');
  assert.equal((await admission.interrupt({ turnId: first.id }, context)).accepted, false);
  assert.equal(second.aborted(), false);
  assert.equal((await admission.interrupt({ turnId: second.id }, context)).accepted, true);
  await conversation.waitForIdle(context);
  assert.equal(second.aborted(), true);
  await assert.rejects(admission.interrupt({}, context), /turn_id/);
});

test('session abort pauses a waiting Task without a live model run or cancelling its Job', async t => {
  const { admitSubmission } = await import(pathToFileURL(join(pinnedPiSource(), 'packages/durable/src/harness/submissions.ts')));
  const faux = fauxProvider(), models = createModels(); models.setProvider(faux.provider);
  const harness = await Harness.open(new MemoryStorage(), { models, registry: createRegistry(), settings: {} }, context);
  const conversation = await harness.root(context, { agent: { model: { provider: 'faux', modelId: 'faux-1' } } });
  const input = createInputAdmission({ harness, conversation, LiveDoc, InboxDoc, admitSubmission });
  const job = { job_id: 'job_1', state: 'running' };
  const calls = [];
  const kernel = { async execute_command(command) {
    calls.push(command);
    if (command === 'research_allocate_task') return { identifier: 'task_1' };
    if (command === 'job_list') return { jobs: [{ ...job }], next_cursor: null };
    throw new Error(`Unexpected command while pausing: ${command}`);
  } };
  const controller = createTaskController({ harness, conversation, admission: input, LiveDoc, InboxDoc,
    kernel, queryKernel: kernel, workspaceId: 'workspace', sessionId: 'session', context });
  t.after(async () => { await controller.close(); await harness.close(context); });
  const session = createSessionAdmission({ harness, conversation, LiveDoc, taskController: controller });
  faux.setResponses([fauxAssistantMessage('I will wait for the calculation.')]);
  const source = await input.submitUser({ requestId: 'start-waiting-research', content: 'Wait for the calculation and report its result.' }, context);
  await conversation.waitForIdle(context);
  const task = await controller.begin({ title: 'Waiting research', objective: 'Report the calculation result',
    source_submission_ids: [String(source.id)], criteria: [{ id: 'result', description: 'Report the result.' }] }, 'begin', context);
  const waiting = await controller.update({ expected_revision: task.revision, action: 'wait',
    wait: { job_ids: ['job_1'], mode: 'all' } }, 'wait', context);
  assert.equal(waiting.state, 'waiting');
  assert.equal((await harness.snapshot(LiveDoc, conversation.id, context)).run, undefined);

  await session.abort(context);
  const paused = await controller.current(context);
  assert.equal(paused.state, 'paused');
  assert.equal(paused.control_epoch, waiting.control_epoch + 1);
  assert.equal((await harness.snapshot(UserTasks, conversation.id, context)).automatic_suppressed, true);
  assert.equal(job.state, 'running');
  assert.ok(!calls.includes('job_cancel'));

  job.state = 'succeeded';
  await controller.reconcile();
  assert.equal((await controller.current(context)).state, 'paused', 'Job completion must not resume a user-paused Task');
  assert.equal((await harness.snapshot(LiveDoc, conversation.id, context)).run, undefined);
});
