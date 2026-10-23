import { createHash } from "node:crypto";
import assert from "node:assert/strict";
import test from "node:test";
import { join } from "node:path";
import { pathToFileURL } from "node:url";
import { Harness, MemoryStorage, createRegistry, defineExtension, hook, GenerationTask, LiveDoc, InboxDoc } from "@earendil-works/pi-durable";
import { createModels, fauxProvider, fauxAssistantMessage } from "@earendil-works/pi-ai";
import { TODO_CONTEXT as context } from "@earendil-works/chord/context";
import { pinnedPiSource } from "./test-environment.mjs";
import { createInputAdmission } from "../../../apps/agent/runtime/admission/input.mjs";
import { createJobAdmission } from "../../../apps/agent/runtime/admission/jobs.mjs";
import { createTaskController, UserTask } from "../../../apps/agent/tasks/controller.mjs";
import { createMonitorService } from "../../../apps/agent/tasks/service.mjs";
import { JOB_EVENT_IDS_LIMIT } from "../../../apps/agent/contracts/monitor.mjs";

const { admitSubmission } = await import(pathToFileURL(join(pinnedPiSource(), "packages/durable/src/harness/submissions.ts")).href);
const gate = () => { let resolve; const promise = new Promise(done => { resolve = done; }); return { promise, resolve }; };

async function fixture(t) {
  const faux = fauxProvider(), models = createModels(); models.setProvider(faux.provider);
  const artifacts = new Map();
  const jobs = new Map(), cancellations = [], failures = new Set(), events = new Map(), cancelOutcomes = new Map();
  let controller, admission, monitor, harness, beforeAutomatic = async () => {}, beforeAssess = async () => {};
  let requests = 0;
  const registry = createRegistry();
  registry.install(defineExtension({ name: "task-race-input", hooks: [hook(GenerationTask, {
    beforeRequest: async (_request, api, ctx) => {
      const live = await api.snapshot(LiveDoc, api.conversationId, ctx);
      for (const id of live.run.inputs) {
        const record = await (await harness.submission(id, ctx)).status(ctx);
        const origin = await admission.origin(record, ctx);
        if (origin.producer === "task_controller") { await beforeAutomatic(); await controller.validateConsumption(record, origin, ctx); }
        if (origin.producer === "job_manager") { await beforeAutomatic(); await monitor.validateConsumption(record, origin, api, ctx); }
      }
      requests++;
    },
  })] }));
  harness = await Harness.open(new MemoryStorage(), { models, registry, settings: {} }, context);
  const conversation = await harness.root(context, { agent: { model: { provider: "faux", modelId: "faux-1" } } });
  admission = createInputAdmission({ harness, conversation, LiveDoc, InboxDoc, admitSubmission });
  const allocatedTasks = new Map();
  const kernel = { execute_command: async (method, params) => {
    if (method === "research_allocate_task") {
      const key = JSON.stringify([params.session_id, params.request_id]);
      if (!allocatedTasks.has(key)) allocatedTasks.set(key, `task_${allocatedTasks.size + 1}`);
      return { identifier: allocatedTasks.get(key) };
    }
    if (method === "job_resolve_target") return { target: params.target || { platform: "local", scheduler_entry: "main" }, executor: params.target?.platform === "cluster_a" ? "slurm" : "qrun", route_digest: "sha256:" + "a".repeat(64), selection_mode: params.target ? "explicit" : "default" };
    if (method === "job_list") return { jobs: [...jobs].map(([job_id, state]) => ({ job_id, state })), next_cursor: null };
    if (method === "job_status") return { job_id: params.job_id, state: jobs.get(params.job_id) };
    if (method === "job_cancel") {
      if (failures.delete(params.job_id)) throw Object.assign(new Error("Fixture cancellation connection failed"), { code: "connection_lost" });
      cancellations.push(params.job_id);
      const state = cancelOutcomes.get(params.job_id) || "cancelled";
      jobs.set(params.job_id, state);
      return { job_id: params.job_id, state };
    }
    if (method === "artifact_read") return artifacts.get(params.artifact_id);
    if (method === "research_read") return { ref: params.ref };
    if (method === "job_manager_assess") {
      await beforeAssess();
      const task = await controller.current(context);
      return { admitted: true, obsolete: false, event_id: params.event_id, delivery_token: "event-fact",
        event: events.get(params.event_id) || { event_id: params.event_id, user_task_id: task.user_task_id, job_id: "job_a", state: jobs.get("job_a") } };
    }
    throw new Error(`Unexpected fixture command ${method}`);
  } };
  function openController() {
    controller = createTaskController({ harness, conversation, admission, LiveDoc, InboxDoc, kernel, workspaceId: "workspace", sessionId: "session", context });
    monitor = createJobAdmission({ admission, kernel, sessionId: "session", producerToken: "fixture-token", taskController: controller });
  }
  openController();
  t.after(async () => { await controller.close(); await harness.close(context); });
  faux.setResponses([fauxAssistantMessage("I will investigate")]);
  const source = await admission.submitUser({ requestId: "user-source", content: "Investigate and deliver the final report" }, context);
  await conversation.waitForIdle(context);
  await controller.begin({ title: "Research", objective: "Deliver report", source_submission_ids: [String(source.id)], criteria: [{ id: "report", description: "Final report" }] }, "begin", context);
  const assess = (task, status = "met") => {
    const content = JSON.stringify({ schema_version: "task-assessment/1", workspace_id: "workspace",
      user_task_id: task.user_task_id, requirements_revision: task.requirements_revision, criterion_id: "report",
      status, reason: "Report acceptance", conflicts: [],
      checks: [{ method: "reasoned", status, reason: "Report evaluated", evidence_refs: ["result_1"] }] });
    artifacts.set("art_1", { content, sha256: createHash("sha256").update(content).digest("hex") });
    return { criterion_id: "report", status, assessment_ref: "art_1", evidence_refs: ["result_1"] };
  };
  return { assess, get controller() { return controller; }, harness, conversation, admission, monitor, faux, jobs, cancellations, failures, events, source, cancelOutcomes, kernel,
    get requests() { return requests; }, setBeforeAutomatic: fn => { beforeAutomatic = fn; }, setBeforeAssess: fn => { beforeAssess = fn; },
    reopen: async () => { await controller.close(); openController(); } };
}

test("an early Job event cannot consume an all-Jobs wait", async t => {
  const env = await fixture(t);
  env.jobs.set("job_a", "succeeded"); env.jobs.set("job_b", "running");
  let task = await env.controller.current(context);
  task = await env.controller.update({ expected_revision: task.revision, action: "wait", wait: { job_ids: ["job_a", "job_b"], mode: "all" } }, "wait-all", context);
  env.faux.setResponses([fauxAssistantMessage("Unexpected early wake")]);
  const before = env.requests;
  const response = await env.monitor.admit({ requestId: "batch-wait", eventIds: ["event_1"], token: "fixture-token", mode: "next_run" }, context);
  await env.conversation.waitForIdle(context);
  assert.equal(response.accepted, true);
  assert.equal(response.pending, true);
  assert.deepEqual(response.deferred, {
    code: "task_waiting",
    message: "The task's explicit Job wait has not completed; events remain pending",
    job_ids: ["job_a", "job_b"],
    mode: "all",
  });
  assert.equal((await env.controller.current(context)).state, "waiting");
  assert.equal(env.requests, before, "no model request until the complete wait predicate is satisfied");
});

test("a partially failed cancel request retains responsibility across controller recovery", async t => {
  const env = await fixture(t);
  env.jobs.set("job_a", "running"); env.jobs.set("job_b", "unknown");
  env.failures.add("job_a");
  const task = await env.controller.current(context);
  const cancelled = await env.controller.control({ user_task_id: task.user_task_id, action: "cancel", request_id: "cancel-all",
    expected_revision: task.revision, jobs: "cancel" }, context);
  assert.equal(cancelled.task.cancel_jobs.errors.job_a.code, "connection_lost");
  assert.equal((await env.controller.current(context)).state, "cancelled");
  await env.reopen();
  await env.controller.reconcile(context);
  assert.deepEqual(env.jobs, new Map([["job_a", "cancelled"], ["job_b", "cancelled"]]));
  assert.deepEqual([...new Set(env.cancellations)].sort(), ["job_a", "job_b"]);
});

test("pause before first automatic consumption can resume past the invalidated reservation", async t => {
  const env = await fixture(t), entered = gate(), proceed = gate();
  env.setBeforeAutomatic(async () => { entered.resolve(); await proceed.promise; });
  env.faux.setResponses([fauxAssistantMessage("Continue after explicit resume")]);
  await env.controller.reconcile(context);
  await entered.promise;
  let task = await env.controller.current(context);
  await env.controller.control({ user_task_id: task.user_task_id, action: "pause", request_id: "pause-before-consumption", expected_revision: task.revision }, context);
  proceed.resolve();
  await env.conversation.waitForIdle(context);
  assert.equal(env.requests, 1, "paused automatic request never reached the provider");
  task = await env.controller.current(context);
  await env.controller.control({ user_task_id: task.user_task_id, action: "resume", request_id: "resume-after-pause", expected_revision: task.revision }, context);
  env.setBeforeAutomatic(async () => {});
  await env.controller.reconcile(context);
  await env.conversation.waitForIdle(context);
  assert.equal(env.requests, 2);
  assert.equal((await env.controller.current(context)).state, "active");
  assert.equal((await env.controller.current(context)).continuation.sequence, 2);
});

for (const outcome of ["full", "partial"]) test(`failed ${outcome} delivery retains acceptance and supports delivery-only recovery`, async t => {
  const env = await fixture(t), entered = gate(), fail = gate();
  env.faux.setResponses([async () => { entered.resolve(); await fail.promise; throw new Error("Final delivery rejected"); }]);
  await env.controller.reconcile(context); await entered.promise;
  const task = await env.controller.current(context);
  await env.controller.update({ expected_revision: task.revision, action: "propose_completion",
    completion_outcome: outcome, completion: [env.assess(task, outcome === "full" ? "met" : "unmet")],
    ...(outcome === "partial" ? { stop_basis: { kind: "search_exhausted", reason: "Bounded search exhausted", evidence_refs: ["result_1"] } } : {}) }, "complete", context);
  fail.resolve(); await env.conversation.waitForIdle(context);
  await env.reopen(); await env.controller.reconcile(context);
  const recovered = await env.controller.current(context);
  assert.equal(recovered.state, "completing");
  assert.equal(recovered.completion[0].criterion_id, "report");
  assert.equal(recovered.execution_recovery.state, "attention_required");
  assert.equal(recovered.execution_recovery.phase, "delivery");
  const finishing = gate(), release = gate();
  env.faux.setResponses([async () => { finishing.resolve(); await release.promise; return fauxAssistantMessage("The report is complete"); }]);
  await env.controller.control({ user_task_id: recovered.user_task_id, action: "resume", request_id: "resume-delivery",
    expected_revision: recovered.revision }, context);
  await env.controller.reconcile(); await finishing.promise;
  try {
    assert.match(await env.controller.toolRestriction(context), /read-only/);
    await assert.rejects(env.controller.binding(context), { code: "task_not_active" });
  } finally { release.resolve(); }
  await env.conversation.waitForIdle(context); await env.controller.reconcile();
  const delivered = await env.controller.current(context);
  assert.equal(delivered.state, outcome === "full" ? "completed" : "partial");
  assert.equal(delivered.completion_outcome, outcome);
  assert.deepEqual(delivered.completion, recovered.completion);
  assert.equal(delivered.execution_recovery, null);
  if (outcome === "partial") {
    const requests = env.requests;
    await env.controller.reconcile(context);
    assert.equal(env.requests, requests, "partial tasks do not automatically restart");
    const resumed = await env.controller.control({ user_task_id: delivered.user_task_id, action: "resume",
      expected_revision: delivered.revision, request_id: "resume-partial" }, context);
    assert.equal(resumed.task.state, "active");
    assert.equal(resumed.task.completion_outcome, null);
    assert.equal((await env.controller.read({ user_task_id: delivered.user_task_id }, context)).completion_history[0].outcome, "partial");
  }
});

test("mixed historical and current Job batches retain identity without driving the new task from old facts", async t => {
  const env = await fixture(t);
  const old = await env.controller.current(context);
  await env.controller.control({ user_task_id: old.user_task_id, action: "cancel", request_id: "cancel-old", expected_revision: old.revision, jobs: "keep" }, context);
  const current = await env.controller.begin({ title: "New research", objective: "Deliver new report", source_submission_ids: [String(env.source.id)], criteria: [{ id: "report", description: "New report" }] }, "begin-next", context);
  env.events.set("event_4", { event_id: "event_4", user_task_id: old.user_task_id, job_id: "job_old", state: "succeeded" });
  env.events.set("event_2", { event_id: "event_2", user_task_id: current.user_task_id, job_id: "job_current", state: "succeeded" });
  const obsolete = await env.monitor.admit({ requestId: "old-only", eventIds: ["event_4"], token: "fixture-token", mode: "next_run" }, context);
  assert.equal(obsolete.skipped, true);
  assert.equal(await env.admission.status("old-only", context), null);
  env.faux.setResponses([fauxAssistantMessage("Analyze only current Job")]);
  const draft = { requestId: "mixed-batch", eventIds: ["event_4", "event_2"], token: "fixture-token", mode: "next_run" };
  assert.equal((await env.monitor.admit(draft, context)).accepted, true);
  await env.conversation.waitForIdle(context);
  const record = await env.admission.status("mixed-batch", context);
  const origin = await env.admission.origin(record, context);
  assert.deepEqual(origin.identity.event_ids, ["event_2", "event_4"]);
  const entry = await env.conversation.commit(tx => tx.entry(record.entry), context);
  assert.match(JSON.stringify(entry.model), /event_2/);
  assert.doesNotMatch(JSON.stringify(entry.model), /event_4/);
  const before = env.requests;
  const retried = await env.monitor.admit(draft, context);
  assert.equal(retried.consumed, true);
  assert.equal(env.requests, before);
  assert.equal((await env.controller.current(context)).user_task_id, current.user_task_id);
});

test("a previous task's unreachable cancellation does not starve new authorized work", async t => {
  const env = await fixture(t);
  env.jobs.set("job_a", "running"); env.failures.add("job_a");
  const old = await env.controller.current(context);
  await env.controller.control({ user_task_id: old.user_task_id, action: "cancel", request_id: "cancel-unreachable", expected_revision: old.revision, jobs: "cancel" }, context);
  const current = await env.controller.begin({ title: "New task", objective: "Deliver new report", source_submission_ids: [String(env.source.id)], criteria: [{ id: "report", description: "New report" }] }, "new-work", context);
  env.failures.add("job_a");
  env.faux.setResponses([fauxAssistantMessage("New authorized work is progressing")]);
  const before = env.requests;
  await env.controller.reconcile(context); await env.conversation.waitForIdle(context);
  assert.equal(env.requests, before + 1);
  assert.equal((await env.controller.current(context)).user_task_id, current.user_task_id);
  const previous = await env.controller.read({ user_task_id: old.user_task_id }, context);
  assert.deepEqual(previous.cancel_jobs.pending, ["job_a"]);
  assert.equal(previous.cancel_jobs.errors.job_a.code, "connection_lost");
});

test("unknown cancellation stays explicit and reconciles the terminal receipt after recovery", async t => {
  const env = await fixture(t);
  env.jobs.set("job_a", "running"); env.cancelOutcomes.set("job_a", "unknown");
  const task = await env.controller.current(context);
  const response = await env.controller.control({ user_task_id: task.user_task_id, action: "cancel", request_id: "cancel-uncertain", expected_revision: task.revision, jobs: "cancel" }, context);
  assert.deepEqual(response.task.cancel_jobs.uncertain, ["job_a"]);
  assert.equal(response.task.cancel_jobs.receipts.job_a.state, "unknown");
  env.jobs.set("job_a", "cancelled");
  await env.reopen(); await env.controller.reconcile(context);
  const recovered = await env.controller.current(context);
  assert.deepEqual(recovered.cancel_jobs.uncertain, []);
  assert.equal(recovered.cancel_jobs.receipts.job_a.state, "cancelled");
  assert.equal(env.cancellations.length, 1, "recovery queries cancellation outcome without sending it again");
});

test("an event interrupted before consumption is delivered through resumed task continuation", async t => {
  const env = await fixture(t), entered = gate(), proceed = gate();
  env.setBeforeAutomatic(async () => { entered.resolve(); await proceed.promise; });
  env.faux.setResponses([fauxAssistantMessage("The deferred Job fact is analyzed")]);
  const draft = { requestId: "event-before-pause", eventIds: ["event_3"], token: "fixture-token", mode: "next_run" };
  await env.monitor.admit(draft, context); await entered.promise;
  let task = await env.controller.current(context);
  await env.controller.control({ user_task_id: task.user_task_id, action: "pause", request_id: "pause-event", expected_revision: task.revision }, context);
  proceed.resolve(); await env.conversation.waitForIdle(context);
  const original = await env.admission.status(draft.requestId, context);
  assert.equal(original.status, "unanswered");
  assert.equal((await env.admission.origin(original, context)).consumption, undefined);
  task = await env.controller.current(context);
  await env.controller.control({ user_task_id: task.user_task_id, action: "resume", request_id: "resume-event", expected_revision: task.revision }, context);
  env.setBeforeAutomatic(async () => {});
  await env.controller.reconcile(context); await env.conversation.waitForIdle(context);
  const response = await env.monitor.admit(draft, context);
  assert.equal(response.consumed, true);
  assert.equal((await env.admission.status(draft.requestId, context)).status, "unanswered", "original Pi outcome is not rewritten");
  assert.ok((await env.admission.origin(original, context)).successor_consumption);
  assert.deepEqual((await env.controller.current(context)).event_inputs, []);
  assert.equal(env.requests, 2, "only the resumed successor consumes the deferred event");
});

test("an interrupted full event batch is consumed before a later full batch", async t => {
  const env = await fixture(t), entered = gate(), proceed = gate();
  const eventIds = Array.from({ length: JOB_EVENT_IDS_LIMIT }, (_, index) => `event_${index + 1}`);
  const first = { requestId: "full-first", eventIds, token: "fixture-token", mode: "next_run" };
  const second = { ...first, requestId: "full-second",
    eventIds: eventIds.map((_, index) => `event_${index + JOB_EVENT_IDS_LIMIT + 1}`) };
  env.setBeforeAutomatic(async () => { entered.resolve(); await proceed.promise; });
  env.faux.setResponses([fauxAssistantMessage("Recovered first batch"), fauxAssistantMessage("Consumed second batch")]);
  await env.monitor.admit(first, context); await entered.promise;
  let task = await env.controller.current(context);
  await env.controller.control({ user_task_id: task.user_task_id, action: "pause", request_id: "pause-full", expected_revision: task.revision }, context);
  proceed.resolve(); await env.conversation.waitForIdle(context);
  task = await env.controller.current(context);
  await env.controller.control({ user_task_id: task.user_task_id, action: "resume", request_id: "resume-full", expected_revision: task.revision }, context);
  env.setBeforeAutomatic(async () => {});
  const deferred = await env.monitor.admit(second, context);
  assert.equal(deferred.pending, true);
  assert.equal(deferred.deferred.code, "task_events_pending");
  assert.equal(await env.admission.status(second.requestId, context), null);
  assert.equal((await env.controller.current(context)).event_inputs.flatMap(input => input.event_ids).length, JOB_EVENT_IDS_LIMIT);
  await env.controller.reconcile(context); await env.conversation.waitForIdle(context);
  assert.equal((await env.monitor.admit(first, context)).consumed, true);
  assert.deepEqual((await env.controller.current(context)).event_inputs, []);
  assert.equal((await env.monitor.admit(second, context)).accepted, true);
  await env.conversation.waitForIdle(context);
  assert.equal((await env.monitor.admit(second, context)).consumed, true);
  assert.deepEqual((await env.controller.current(context)).event_inputs, []);
  assert.equal(env.requests, 3);
});

test("concurrent event batches recheck pending Task events inside the admission commit", async t => {
  const env = await fixture(t), bothPrepared = gate(), commitSecond = gate();
  const first = { requestId: "concurrent-first", token: "fixture-token", mode: "next_run",
    eventIds: Array.from({ length: JOB_EVENT_IDS_LIMIT }, (_, index) => `event_${index + 1}`) };
  const second = { ...first, requestId: "concurrent-second",
    eventIds: first.eventIds.map((_, index) => `event_${index + JOB_EVENT_IDS_LIMIT + 1}`) };
  const submitInternal = env.admission.submitInternal;
  let prepared = 0;
  env.admission.submitInternal = async (draft, ctx) => {
    if (++prepared === 2) bothPrepared.resolve();
    await bothPrepared.promise;
    if (draft.requestId === second.requestId) await commitSecond.promise;
    return submitInternal(draft, ctx);
  };
  env.setBeforeAutomatic(async () => { throw new Error("Interrupted before Job event consumption"); });
  const firstAdmission = env.monitor.admit(first, context);
  const secondAdmission = env.monitor.admit(second, context);
  try {
    await bothPrepared.promise;
    assert.equal((await firstAdmission).accepted, true);
    await env.conversation.waitForIdle(context);
    const original = await env.admission.status(first.requestId, context);
    assert.equal(original.status, "unanswered");
    assert.equal((await env.admission.origin(original, context)).consumption, undefined);
    const before = await env.controller.current(context);
    assert.equal(before.event_inputs.length, 1);
    assert.equal(before.event_inputs[0].event_ids.length, JOB_EVENT_IDS_LIMIT);
    commitSecond.resolve();
    const deferred = await secondAdmission;
    assert.equal(deferred.accepted, true);
    assert.equal(deferred.pending, true);
    assert.equal(deferred.deferred.code, "task_events_pending");
    assert.equal(await env.admission.status(second.requestId, context), null);
    assert.deepEqual((await env.controller.current(context)).event_inputs, before.event_inputs);
    assert.equal(env.requests, 1, "neither unconsumed event batch reached the model");
  } finally {
    bothPrepared.resolve(); commitSecond.resolve();
    await Promise.allSettled([firstAdmission, secondAdmission]);
    env.admission.submitInternal = submitInternal;
  }
});

test("consumption clears Task events atomically and a retry repairs a retained stale pointer", async t => {
  const env = await fixture(t);
  const original = env.controller.completeJobEventConsumption;
  env.controller.completeJobEventConsumption = async () => { throw new Error("interrupted after consumption commit"); };
  const draft = { requestId: "consumption-commit", eventIds: ["event_1"], token: "fixture-token", mode: "next_run" };
  await env.monitor.admit(draft, context); await env.conversation.waitForIdle(context);
  const record = await env.admission.status(draft.requestId, context);
  assert.ok((await env.admission.origin(record, context)).consumption);
  let task = await env.controller.current(context);
  assert.deepEqual(task.event_inputs, [], "the consumption commit already removed the Task pointer");
  // Reproduce a retained pointer from the former two-commit consumption path.
  await env.conversation.commit(async tx => {
    const stored = await tx.doc(UserTask, env.conversation.id, task.user_task_id, null);
    stored.event_inputs.push({ submission_id: record.id, request_id: draft.requestId, event_ids: draft.eventIds });
  }, context);
  env.controller.completeJobEventConsumption = original;
  assert.equal((await env.monitor.admit(draft, context)).consumed, true);
  task = await env.controller.current(context);
  assert.deepEqual(task.event_inputs, []);
  assert.equal(env.requests, 1, "retrying the consumed identity does not create a model request");
});

for (const consumption of ["direct", "successor"]) test(`Task reconcile clears retained ${consumption} consumption without replaying the old batch`, async t => {
  const env = await fixture(t);
  const first = { requestId: `retained-${consumption}`, eventIds: ["event_1"], token: "fixture-token", mode: "next_run" };
  if (consumption === "successor") env.setBeforeAutomatic(async () => { throw new Error("Interrupted before consumption"); });
  env.faux.setResponses([fauxAssistantMessage("Consumed first batch")]);
  await env.monitor.admit(first, context);
  await env.conversation.waitForIdle(context);
  if (consumption === "successor") {
    const task = await env.controller.current(context);
    await env.controller.control({ user_task_id: task.user_task_id, action: "resume", request_id: "resume-retained",
      expected_revision: task.revision }, context);
    env.setBeforeAutomatic(async () => {});
    await env.controller.reconcile(context);
    await env.conversation.waitForIdle(context);
  }
  const record = await env.admission.status(first.requestId, context);
  assert.ok((await env.admission.origin(record, context))[consumption === "direct" ? "consumption" : "successor_consumption"]);
  let task = await env.controller.current(context);
  assert.deepEqual(task.event_inputs, []);
  env.jobs.set("job_wait", "running");
  task = await env.controller.update({ expected_revision: task.revision, action: "wait",
    wait: { job_ids: ["job_wait"], mode: "all" } }, "wait-after-first", context);
  await env.conversation.commit(async tx => {
    const stored = await tx.doc(UserTask, env.conversation.id, task.user_task_id, null);
    stored.event_inputs.push({ submission_id: record.id, request_id: first.requestId, event_ids: first.eventIds });
  }, context);
  const execute = env.kernel.execute_command, assessed = [];
  env.kernel.execute_command = async (method, params) => {
    if (method === "job_manager_assess") assessed.push(params.event_id);
    return execute(method, params);
  };
  const second = { ...first, requestId: `after-retained-${consumption}`, eventIds: ["event_2"] };
  assert.equal((await env.monitor.admit(second, context)).deferred.code, "task_events_pending");
  await env.controller.reconcile(context);
  assert.deepEqual((await env.controller.current(context)).event_inputs, []);
  env.jobs.set("job_wait", "succeeded");
  env.faux.setResponses([fauxAssistantMessage("Consumed second batch")]);
  assert.equal((await env.monitor.admit(second, context)).accepted, true);
  await env.conversation.waitForIdle(context);
  assert.ok((await env.admission.origin(await env.admission.status(second.requestId, context), context)).consumption);
  assert.ok(assessed.length > 0 && assessed.every(id => id === "event_2"), "the old batch is never assessed or retried");
  assert.deepEqual((await env.controller.current(context)).event_inputs, []);
  assert.equal(env.requests, 3);
});

test("pause while the consumption assessment is pending prevents the model request", async t => {
  const env = await fixture(t), entered = gate(), proceed = gate();
  let assessments = 0;
  env.setBeforeAssess(async () => { assessments++; if (assessments === 2) { entered.resolve(); await proceed.promise; } });
  env.faux.setResponses([fauxAssistantMessage("Must not be sent after pause")]);
  await env.monitor.admit({ requestId: "assessment-race", eventIds: ["event_5"], token: "fixture-token", mode: "next_run" }, context);
  await entered.promise;
  const task = await env.controller.current(context);
  await env.controller.control({ user_task_id: task.user_task_id, action: "pause", request_id: "pause-assessment", expected_revision: task.revision }, context);
  proceed.resolve(); await env.conversation.waitForIdle(context);
  assert.equal(env.requests, 1, "no request after the pause receipt while external assessment was outstanding");
  assert.equal((await env.controller.current(context)).state, "paused");
  const record = await env.admission.status("assessment-race", context);
  assert.equal((await env.admission.origin(record, context)).consumption, undefined);
});

test("single-Job cancellation identity cannot be reused for another target", async t => {
  const env = await fixture(t);
  env.jobs.set("job_a", "running"); env.jobs.set("job_b", "running");
  const service = createMonitorService({ controller: env.controller, harness: env.harness, conversation: env.conversation,
    kernel: env.kernel, workspaceId: "workspace", sessionId: "session", LiveDoc });
  const request = { method: "monitor/job/cancel", params: { job_id: "job_a", request_id: "cancel-one" } };
  const first = await service.handle(request, context);
  assert.equal(first.error, null);
  const repeated = await service.handle(request, context);
  assert.deepEqual(repeated, first);
  const reused = await service.handle({ ...request, params: { ...request.params, job_id: "job_b" } }, context);
  assert.equal(reused.error.code, "request_id_reused");
  assert.equal(env.jobs.get("job_b"), "running");
});
