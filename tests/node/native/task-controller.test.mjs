import assert from "node:assert/strict";
import test from "node:test";
import { join } from "node:path";
import { pathToFileURL } from "node:url";
import { Harness, MemoryStorage, createRegistry, defineExtension, hook, GenerationTask, LiveDoc, InboxDoc } from "@earendil-works/pi-durable";
import { createModels, fauxProvider, fauxAssistantMessage } from "@earendil-works/pi-ai";
import { TODO_CONTEXT as context } from "@earendil-works/chord/context";
import { pinnedPiSource } from "./test-environment.mjs";
import { createInputAdmission, bindUserInputConversation } from "../../../apps/agent/host/admission/input.mjs";
import { createSessionAdmission } from "../../../apps/agent/host/admission/session.mjs";
import { createTaskController, UserTask } from "../../../apps/agent/tasks/controller.mjs";
import { createMonitorService } from "../../../apps/agent/tasks/service.mjs";
import { createTaskTools } from "../../../apps/agent/tasks/tools.mjs";
import { wrapToolForHarness } from "../../../apps/agent/tools/envelope.mjs";
import { createToolExecutionContext } from "../../../apps/agent/tools/context.mjs";
import { projectUserTask } from "../../../apps/agent/tasks/projection.mjs";

const { admitSubmission } = await import(pathToFileURL(join(pinnedPiSource(), "packages/durable/src/harness/submissions.ts")).href);
async function fixture(t, storage = new MemoryStorage(), controllerOptions = {}, beforeRequest) {
  const faux = fauxProvider(), models = createModels(); models.setProvider(faux.provider);
  let harness, admission, controller;
  const registry = createRegistry();
  const toolContext = createToolExecutionContext({ workspace_root: "/workspace", session_id: "session", operation_id: null,
    allowed_authorities: ["task_control"], allowed_effects: ["read", "task_write"] });
  registry.install(defineExtension({ name: "test-task-tools", tools: createTaskTools(() => controller).map(tool =>
    wrapToolForHarness(tool, { toolContext, invocation: api => ({ workspaceRoot: "/workspace", sessionId: "session", operationId: String(api.taskId) }) })) }));
  registry.install(defineExtension({ name: "test-task-input", hooks: [hook(GenerationTask, {
    beforeRequest: async (_request, api, ctx) => {
      const live = await api.snapshot(LiveDoc, api.conversationId, ctx);
      for (const id of live.run.inputs) {
        const record = await (await harness.submission(id, ctx)).status(ctx);
        const origin = await admission.origin(record, ctx);
        if (origin.producer !== "user") await controller.validateConsumption(record, origin, ctx);
      }
      return beforeRequest?.(_request, api, ctx);
    },
  })] }));
  harness = await Harness.open(storage, { models, registry, settings: { retry: { enabled: false } } }, context);
  const conversation = await harness.root(context, { agent: { model: { provider: "faux", modelId: "faux-1" } } });
  admission = createInputAdmission({ harness, conversation, LiveDoc, InboxDoc, admitSubmission });
  const jobStates = new Map(), calls = [], artifacts = new Map();
  const allocatedTasks = new Map();
  const kernel = { execute_command: async (command, params) => {
    if (command === "research.allocate_task") {
      const key = JSON.stringify([params.session_id, params.request_id]);
      if (!allocatedTasks.has(key)) allocatedTasks.set(key, `task_${allocatedTasks.size + 1}`);
      return { identifier: allocatedTasks.get(key) };
    }
    calls.push({ command, params });
    if (command === "job.list") return { jobs: [...jobStates].map(([job_id, state]) => ({ job_id, state })), next_cursor: null };
    if (command === "job.status") return { job_id: params.job_id, state: jobStates.get(params.job_id) };
    if (command === "job.cancel") { jobStates.set(params.job_id, "cancelled"); return { job_id: params.job_id, state: "cancelled" }; }
    if (command === "research.read") { if (params.ref === "missing") throw new Error("unknown evidence"); return { ref: params.ref, node_id: params.ref }; }
    if (command === "artifact.read") return { artifact_id: params.artifact_id,
      sha256: artifacts.get(params.artifact_id) };
    throw new Error(`Unexpected test command ${command}`);
  } };
  const openController = () => createTaskController({ harness, conversation, admission, LiveDoc, InboxDoc, kernel, workspaceId: "workspace", sessionId: "session", context, ...controllerOptions });
  controller = openController();
  const session = createSessionAdmission({ harness, conversation, LiveDoc, taskController: controller });
  const native = bindUserInputConversation(conversation, admission, harness, session);
  t.after(async () => { await controller.close(); await harness.close(context); });
  const begin = async () => {
    faux.setResponses([fauxAssistantMessage("Starting the research")]);
    const source = await admission.submitUser({ requestId: "user-research", content: "Research this mechanism and deliver an evidence-backed report" }, context);
    await conversation.waitForIdle(context);
    const task = await controller.begin({ title: "Research mechanism", objective: "Deliver the mechanism report",
      source_submission_ids: [String(source.id)], criteria: [{ id: "report", description: "Report supported by evidence" }] }, "begin", context);
    return task;
  };
  return { harness, conversation, admission, get controller() { return controller; }, native, faux, begin, jobStates, calls, kernel, session, artifacts,
    reopen: async () => { await controller.close(); controller = openController(); } };
}

test("idle active tasks continue beyond three evidence-free runs and explicit blockers remain recoverable", async t => {
  const { controller, conversation, faux, begin, admission } = await fixture(t);
  const task = await begin();
  assert.match(task.user_task_id, /^task_/);
  assert.equal(task.schema_version, "coragent-user-task/2");
  assert.deepEqual(task.research, { entry_node_ids: [], focus_node_ids: [] });
  assert.match(task.sources[0].text, /evidence-backed/);
  for (let round = 0; round < 4; round++) {
    faux.setResponses([fauxAssistantMessage("Another partial summary")]);
    await Promise.all([controller.reconcile(), controller.reconcile()]);
    await conversation.waitForIdle(context);
    assert.equal((await controller.current(context)).continuation.sequence, round + 1);
    const input = await admission.status(`task:${task.user_task_id}:continue:${round + 1}`, context);
    assert.equal((await admission.origin(input, context)).producer, "task_controller");
  }
  let blocking = await controller.current(context);
  assert.equal(blocking.state, "active");
  await controller.update({ action: "block", expected_revision: blocking.revision,
    reason: "The required boundary data must be supplied before further analysis" }, "explicit-block", context);
  await controller.reconcile();
  assert.equal((await controller.current(context)).state, "blocked");
  assert.equal((await controller.current(context)).continuation.no_progress, 3);

  faux.setResponses([fauxAssistantMessage("The previous approach produced no new evidence")]);
  await admission.submitUser({ requestId: "ask-blocker", content: "Why did the research stop?" }, context);
  await conversation.waitForIdle(context);
  await controller.reconcile();
  let current = await controller.current(context);
  assert.equal(current.state, "blocked", "ordinary input must not restart automatic work");
  assert.equal(current.continuation.sequence, 4);
  await assert.rejects(controller.update({ action: "refine", expected_revision: current.revision,
    source_submission_ids: [task.sources[0].submission_id] }, "old-sources", context), { code: "task_source_required" });

  faux.setResponses([fauxAssistantMessage("I will use the revised method")]);
  const source = await admission.submitUser({ requestId: "revise-method", content: "Use the supplied geometry to continue the study" }, context);
  await conversation.waitForIdle(context);
  current = await controller.current(context);
  const params = { action: "refine", expected_revision: current.revision,
    source_submission_ids: [String(source.id)], objective: "Study the supplied geometry" };
  const revised = await controller.update(params, "revise-blocked", context);
  assert.equal(revised.state, "active");
  assert.equal(revised.reason, null);
  assert.equal(revised.wait, null);
  assert.equal(revised.continuation.no_progress, 0);
  assert.equal(revised.progress_version, current.progress_version, "new instructions are not scientific evidence");
  assert.deepEqual(await controller.update(params, "revise-blocked", context), revised);
  assert.ok(revised.audit.some(item => item.actor === "agent" && item.action === "block"));

  faux.setResponses([fauxAssistantMessage("Continuing with the revised method")]);
  await controller.reconcile();
  await conversation.waitForIdle(context);
  current = await controller.current(context);
  assert.equal(current.state, "active");
  assert.equal(current.continuation.sequence, 5);
  await controller.control({ user_task_id: task.user_task_id, action: "pause", expected_revision: current.revision,
    request_id: "pause-revised" }, context);
  current = await controller.current(context);
  await assert.rejects(controller.update({ action: "refine", expected_revision: current.revision,
    source_submission_ids: [String(source.id)] }, "refine-paused", context), { code: "task_paused" });
});

const nodeId = n => `node_${n + 1}`;
const observed = (toolName, result) => [{ id: 200, model: [{ role: "toolResult", toolName, content: [], details: { result } }] }];

test("Research Review lifecycle is an idempotent Task pointer and does not advance revision", async t => {
  const { controller, begin } = await fixture(t);
  let task = await begin();
  const review = { schema_version: "research-review/1", review_id: "review_state",
    state_digest: "sha256:state", review_digest: "sha256:review", status: "attention",
    review_status: "current", trigger: "context_refresh" };
  const revision = task.revision;
  task = await controller.recordResearchReview(review, context, task.user_task_id);
  assert.equal(task.revision, revision);
  assert.deepEqual(task.research_review, { current_review_ref: "review_state",
    last_reviewed_state_digest: "sha256:state", review_digest: "sha256:review",
    review_status: "current", trigger: "context_refresh", updated_at: task.research_review.updated_at });
  const again = await controller.recordResearchReview(review, context, task.user_task_id);
  assert.equal(again.revision, revision);
  assert.deepEqual(projectUserTask(again).research_review, task.research_review);
});

test("research binding has one bounded write path, preserves task control and allows shared Nodes", async t => {
  const { controller, begin, kernel, calls } = await fixture(t);
  let task = await begin();
  const research = { entry_node_ids: Array.from({ length: 128 }, (_, n) => nodeId(n)), focus_node_ids: [nodeId(999)] };
  const request = { action: "set_research", expected_revision: task.revision, research };
  task = await controller.update(request, "bind", context);
  assert.deepEqual(await controller.update(request, "bind", context), task);
  assert.equal(task.progress_version, 0);
  assert.equal(task.state, "active");
  assert.deepEqual((await controller.read({ user_task_id: task.user_task_id }, context)).research, research);
  const projection = projectUserTask(task);
  assert.equal(projection.research.entry_node_ids.length, 8);
  assert.equal(projection.research.entry_nodes_omitted, 120);
  for (const invalid of [undefined, {}, { ...research, entry_node_ids: [nodeId(1), nodeId(1)] },
    { ...research, entry_node_ids: [...research.entry_node_ids, nodeId(128)] },
    { ...research, focus_node_ids: Array.from({ length: 17 }, (_, n) => nodeId(n)) },
    { ...research, focus_node_ids: ["result_1"] }]) {
    await assert.rejects(controller.update({ action: "set_research", expected_revision: task.revision, research: invalid }, "invalid", context), { code: "task_research_invalid" });
  }
  await assert.rejects(controller.update({ action: "progress", expected_revision: task.revision, research, evidence_refs: ["result_1"] }, "wrong-action", context), { code: "task_research_invalid" });
  const original = kernel.execute_command;
  kernel.execute_command = async (method, params) => {
    if (method === "research.read" && params.ref === nodeId(404)) throw new Error("Node not found in this workspace");
    return original(method, params);
  };
  await assert.rejects(controller.update({ action: "set_research", expected_revision: task.revision,
    research: { entry_node_ids: [nodeId(404)], focus_node_ids: [] } }, "foreign", context), /not found/);
  assert.equal((await controller.current(context)).revision, task.revision);
  await controller.control({ user_task_id: task.user_task_id, expected_revision: task.revision, action: "cancel", jobs: "keep", request_id: "finish-first" }, context);
  const next = await controller.begin({ title: "Reuse", objective: "A different question", source_submission_ids: [task.sources[0].submission_id], criteria: [{ id: "answer", description: "Answer" }] }, "next", context);
  await controller.update({ action: "set_research", expected_revision: next.revision, research }, "bind-shared", context);
  assert.deepEqual((await controller.read({ user_task_id: task.user_task_id }, context)).research, research);
  assert.ok(calls.filter(call => call.command === "research.read").every(call => call.params.field === "status"));
});

test("fixed evidence is counted once across tools, reference combinations, content aliases and restart", async t => {
  const { controller, begin, artifacts, harness, conversation, admission, kernel } = await fixture(t);
  await begin();
  const progress = async (refs, id) => controller.update({ action: "progress", expected_revision: (await controller.current(context)).revision, evidence_refs: refs }, id, context);
  await controller.observeToolResults(observed("research_result", { result: { id: "result_1" } }), context);
  await progress(["result_1"], "same");
  await progress(["result_1", "result_2"], "combination");
  await progress(["result_2"], "subset");
  assert.equal((await controller.current(context)).progress_version, 2);
  artifacts.set("art_1", "ab".repeat(32)); artifacts.set("art_2", "sha256:" + "ab".repeat(32));
  await controller.observeToolResults(observed("artifact_create", { artifact_id: "art_1", sha256: "ab".repeat(32) }), context);
  await progress(["art_2"], "alias");
  assert.equal((await controller.current(context)).progress_version, 3);
  for (let n = 3; n < 140; n++) await controller.observeToolResults(observed("research_result", { result: { id: `result_${n}` } }), context);
  const task = await controller.current(context);
  assert.equal(task.progress_identities.length, 140);
  await controller.close();
  const reopened = createTaskController({ harness, conversation, admission, LiveDoc, InboxDoc, kernel, workspaceId: "workspace", sessionId: "session", context });
  t.after(() => reopened.close());
  await reopened.update({ action: "progress", expected_revision: task.revision, evidence_refs: ["result_1", "result_2", "art_2"] }, "after-restart", context);
  await reopened.observeToolResults(observed("research_result", { result: { id: "result_1" } }), context);
  assert.equal((await reopened.current(context)).progress_version, task.progress_version);
});

test("committed updates replay before external validation, even after another task replaces their owner", async t => {
  const { controller, begin, kernel, jobStates } = await fixture(t);
  const original = await begin();
  const binding = { action: "set_research", expected_revision: original.revision,
    research: { entry_node_ids: [nodeId(1)], focus_node_ids: [] } };
  const bound = await controller.update(binding, "bind-replay", context);
  jobStates.set("job_original", "running");
  const progress = { action: "progress", expected_revision: bound.revision, evidence_refs: ["job_original"] };
  const progressed = await controller.update(progress, "progress-replay", context);
  await controller.control({ user_task_id: progressed.user_task_id, expected_revision: progressed.revision,
    action: "cancel", jobs: "keep", request_id: "cancel-original" }, context);
  jobStates.clear();
  const next = await controller.begin({ title: "New assignment", objective: "Investigate a separate question",
    source_submission_ids: [original.sources[0].submission_id], criteria: [{ id: "new", description: "New evidence" }] }, "next-assignment", context);
  let externalReads = 0;
  kernel.execute_command = async () => { externalReads += 1; throw new Error("Memory temporarily unavailable"); };
  assert.deepEqual(await controller.update(binding, "bind-replay", context), bound);
  assert.deepEqual(await controller.update(progress, "progress-replay", context), progressed);
  await assert.rejects(controller.update({ ...binding, research: { entry_node_ids: [], focus_node_ids: [] } }, "bind-replay", context), { code: "request_id_reused" });
  await assert.rejects(controller.update({ ...progress, evidence_refs: ["job_other"] }, "progress-replay", context), { code: "request_id_reused" });
  assert.equal(externalReads, 0);
  assert.deepEqual(await controller.current(context), next);
  await assert.rejects(controller.update({ ...binding, expected_revision: next.revision }, "new-binding", context), /Memory temporarily unavailable/);
  assert.equal(externalReads, 1, "new operations still perform their required validation");
});

test("canonical Artifact IDs deduplicate progress and support completion", async t => {
  const { controller, begin, artifacts, calls, conversation, faux } = await fixture(t);
  await begin();
  const artifactId = "art_1", digest = "ab".repeat(32);
  artifacts.set(artifactId, digest); artifacts.set("art_1", "sha256:" + digest);
  let task = await controller.current(context);
  task = await controller.update({ action: "progress", expected_revision: task.revision, evidence_refs: [artifactId] }, "canonical-artifact", context);
  assert.deepEqual(calls.at(-1), { command: "artifact.read", params: { artifact_id: artifactId, limit: 1 } });
  task = await controller.update({ action: "progress", expected_revision: task.revision, evidence_refs: ["art_1", artifactId] }, "both-artifact-selectors", context);
  await controller.observeToolResults(observed("artifact_register", { artifact_id: artifactId, sha256: digest }), context);
  assert.deepEqual((await controller.current(context)).progress_identities, [`artifact:${digest}`]);
  assert.equal((await controller.current(context)).progress_version, 1);
  let entered, finish;
  const ready = new Promise(resolve => { entered = resolve; });
  faux.setResponses([() => new Promise(resolve => { entered(); finish = () => resolve(fauxAssistantMessage("The report is retained.")); })]);
  await controller.reconcile(); await ready;
  task = await controller.current(context);
  try {
    task = await controller.update({ action: "propose_completion", expected_revision: task.revision,
      completion: [{ criterion_id: "report", evidence_refs: [artifactId] }] }, "canonical-artifact-completion", context);
    assert.equal(task.state, "completing");
  } finally { finish(); }
  await conversation.waitForIdle(context); await controller.reconcile();
  assert.equal((await controller.current(context)).state, "completed");
  assert.ok(calls.some(call => call.command === "artifact.read" && call.params.artifact_id === "art_1"));
  assert.ok(!calls.some(call => call.command === "research.read" && call.params.ref === artifactId));
});

test("new planning records and changing evidence combinations cannot hide an idle research loop", async t => {
  const { controller, conversation, faux, begin } = await fixture(t);
  await begin();
  for (let n = 0; n < 3; n++) {
    faux.setResponses([fauxAssistantMessage("Revise the plan again")]);
    await controller.reconcile(); await conversation.waitForIdle(context);
    await controller.observeToolResults(observed("research_create", { node: { id: nodeId(n) } }), context);
    await controller.observeToolResults(observed("research_update", { ref: `note_${n}` }), context);
    let task = await controller.current(context);
    await controller.update({ action: "set_research", expected_revision: task.revision,
      research: { entry_node_ids: [nodeId(n)], focus_node_ids: [] } }, `bind-${n}`, context);
    task = await controller.current(context);
    await controller.update({ action: "progress", expected_revision: task.revision, evidence_refs: [nodeId(n), `note_${n}`] }, `planning-${n}`, context);
  }
  faux.setResponses([fauxAssistantMessage("Reassess the method without inventing evidence")]);
  await controller.reconcile(); await conversation.waitForIdle(context);
  const task = await controller.current(context);
  assert.equal(task.state, "active"); assert.equal(task.progress_version, 0);
  assert.equal(task.continuation.no_progress, 3);
  assert.equal(task.continuation.sequence, 4);
  await assert.rejects(controller.update({ action: "propose_completion", expected_revision: task.revision,
    completion: [{ criterion_id: "report", evidence_refs: [nodeId(1)] }] }, "node-completion", context), { code: "task_completion_evidence_invalid" });
});

test("Job progress recognizes real milestones once, not status polls or reconciliation timestamps", async t => {
  const { controller, begin, jobStates, kernel } = await fixture(t);
  await begin(); jobStates.set("job_1", "running");
  await controller.observeToolResults(observed("job_start", { job_id: "job_1", submitted_at: "2026-10-10" }), context);
  let task = await controller.current(context);
  await controller.update({ action: "progress", expected_revision: task.revision, evidence_refs: ["job_1"] }, "same-job", context);
  await controller.observeToolResults(observed("job_status", { job_id: "job_1", state: "running", observed_at: "later" }), context);
  assert.equal((await controller.current(context)).progress_version, 1);
  jobStates.set("job_1", "failed");
  await controller.observeToolResults(observed("job_status", { job_id: "job_1", state: "failed" }), context);
  await controller.observeToolResults(observed("job_reconcile", { job_id: "job_1", state: "failed", observed_at: "newer" }), context);
  await controller.observeToolResults(observed("job_collect", { job_id: "job_1", status: { state: "failed" }, result_receipt: { collection_state: "partial" } }), context);
  assert.equal((await controller.current(context)).progress_version, 2);
  const original = kernel.execute_command;
  kernel.execute_command = async (method, params) => method === "job.list"
    ? { jobs: [{ job_id: "job_1", state: "failed", collection_state: "complete", latest_result_receipt_ref: "job_result_fixed" }], next_cursor: null }
    : original(method, params);
  await controller.observeToolResults(observed("job_collect", { job_id: "job_1", status: { state: "failed" }, result_receipt: { collection_state: "complete" } }), context);
  task = await controller.current(context);
  await controller.update({ action: "progress", expected_revision: task.revision, evidence_refs: ["job_1"] }, "collected-again", context);
  assert.equal((await controller.current(context)).progress_version, 3);
  assert.deepEqual(task.progress_identities, ["job:job_1:accepted", "job:job_1:terminal", "job:job_1:collected"]);
});

test("a pause during external Node validation wins before the Pi commit", async t => {
  const { controller, begin, kernel } = await fixture(t);
  const task = await begin();
  let entered, finish;
  const started = new Promise(resolve => { entered = resolve; });
  kernel.execute_command = async (_method, params) => { entered(); await new Promise(resolve => { finish = resolve; }); return { node_id: params.ref }; };
  const binding = controller.update({ action: "set_research", expected_revision: task.revision,
    research: { entry_node_ids: [nodeId(1)], focus_node_ids: [] } }, "racing-bind", context);
  await started;
  await controller.control({ user_task_id: task.user_task_id, expected_revision: task.revision, action: "pause", request_id: "pause-validation" }, context);
  finish();
  await assert.rejects(binding, { code: "task_revision_conflict" });
  assert.equal((await controller.current(context)).state, "paused");
  assert.deepEqual((await controller.current(context)).research.entry_node_ids, []);
});

test("automatic evidence observation cannot overwrite pause or reset progress after it", async t => {
  const { controller, begin, kernel } = await fixture(t);
  const task = await begin();
  let entered, finish;
  const ready = new Promise(resolve => { entered = resolve; });
  kernel.execute_command = async method => { assert.equal(method, "job.list"); entered(); await new Promise(resolve => { finish = resolve; }); return { jobs: [{ job_id: "job_racing", state: "running" }], next_cursor: null }; };
  const observing = controller.observeToolResults(observed("job_start", { job_id: "job_racing", submitted_at: "2026-10-10" }), context);
  await ready;
  await controller.control({ user_task_id: task.user_task_id, expected_revision: task.revision, action: "pause", request_id: "pause-progress" }, context);
  finish(); await observing;
  const current = await controller.current(context);
  assert.equal(current.state, "paused");
  assert.equal(current.progress_version, 0);
  assert.deepEqual(current.progress_identities, []);
});

test("automatic observation skips historical Jobs while crediting current evidence without reading it again", async t => {
  const { controller, begin, kernel } = await fixture(t);
  await begin();
  let ownershipReads = 0;
  kernel.execute_command = async method => {
    assert.equal(method, "job.list", "persisted Result and Artifact successes must not trigger another payload read");
    ownershipReads += 1;
    return { jobs: [{ job_id: "job_current", state: "running" }], next_cursor: null };
  };
  await controller.observeToolResults([
    ...observed("job_status", { job_id: "job_historical", state: "succeeded" }),
    ...observed("job_collect", { job_id: "job_historical", status: { state: "succeeded" }, result_receipt: { collection_state: "complete" } }),
    ...observed("job_status", { job_id: "job_current", state: "running" }),
    ...observed("job_status", { job_id: "job_current", state: "running" }),
    ...observed("research_result", { result: { id: "result_current" } }),
    ...observed("artifact_create", { artifact_id: "art_1", sha256: "ab".repeat(32), size_bytes: 100_000_000 }),
    ...observed("artifact_register", { artifact_id: "art_2", sha256: "ab".repeat(32), size_bytes: 100_000_000 }),
  ], context);
  const task = await controller.current(context);
  assert.equal(ownershipReads, 1);
  assert.equal(task.progress_version, 1);
  assert.deepEqual(new Set(task.progress_identities), new Set(["result:result_current", `artifact:${"ab".repeat(32)}`, "job:job_current:accepted"]));
  assert.ok(!task.progress.evidence_refs.includes("job_historical"));
  await assert.rejects(controller.update({ action: "progress", expected_revision: task.revision,
    evidence_refs: ["job_historical"] }, "foreign-progress", context), { code: "task_evidence_invalid" });
  await controller.observeToolResults(observed("artifact_register", { artifact_id: "art_3", sha256: "ab".repeat(32) }), context);
  assert.equal((await controller.current(context)).progress_version, 1);
});

test("old task schema is rejected rather than initialized or migrated", async t => {
  const { controller, begin, conversation } = await fixture(t);
  const task = await begin();
  await conversation.commit(async tx => { const stored = await tx.doc(UserTask, conversation.id, task.user_task_id, null); stored.schema_version = "coragent-user-task/1"; delete stored.research; }, context);
  await assert.rejects(controller.current(context), { code: "task_schema_unsupported" });
});

test("concrete Job waits do not generate inputs and reconcile already finished Jobs", async t => {
  const { controller, conversation, faux, begin, jobStates } = await fixture(t);
  let task = await begin(); jobStates.set("job_1", "running");
  task = await controller.update({ expected_revision: task.revision, action: "wait", wait: { job_ids: ["job_1"], mode: "all" } }, "wait", context);
  await controller.reconcile(); await controller.reconcile();
  assert.equal((await controller.current(context)).continuation.sequence, 0);
  jobStates.set("job_1", "succeeded");
  faux.setResponses([fauxAssistantMessage("Analyze the finished Job")]);
  await controller.reconcile(); await conversation.waitForIdle(context);
  assert.equal((await controller.current(context)).continuation.sequence, 1);
});

test("native abort persists pause and control retries are idempotent", async t => {
  const { controller, conversation, native, faux, begin } = await fixture(t);
  await begin();
  let entered;
  const ready = new Promise(resolve => { entered = resolve; });
  faux.setResponses([(_ctx, options) => new Promise((_, reject) => {
    entered(); options.signal.addEventListener("abort", () => reject(options.signal.reason), { once: true });
  })]);
  await controller.reconcile(); await ready;
  await native.abort(context); await conversation.waitForIdle(context);
  let task = await controller.current(context);
  assert.equal(task.state, "paused");
  await controller.reconcile(); assert.equal((await controller.current(context)).continuation.sequence, 1);
  const control = { user_task_id: task.user_task_id, action: "resume", expected_revision: task.revision, request_id: "resume" };
  const result = await controller.control(control, context);
  assert.deepEqual(await controller.control(control, context), result);
  await assert.rejects(controller.control({ ...control, action: "pause" }, context), { code: "request_id_reused" });
});

test("a negative theoretical Result completes a zero-Job task only after the final Pi answer", async t => {
  const { controller, conversation, faux, begin, kernel, calls } = await fixture(t);
  await begin(); let finish, entered;
  const original = kernel.execute_command;
  kernel.execute_command = async (method, params) => method === "research.read"
    ? { ref: params.ref, result: { id: params.ref, observation: "Derived counterexample", conclusion: "The proposed statement does not hold" } }
    : original(method, params);
  const ready = new Promise(resolve => { entered = resolve; });
  faux.setResponses([() => new Promise(resolve => { entered(); finish = () => resolve(fauxAssistantMessage("The final report")); })]);
  await controller.reconcile(); await ready;
  let task = await controller.current(context);
  await assert.rejects(controller.update({ expected_revision: task.revision, action: "propose_completion", completion: [] }, "incomplete", context), { code: "task_completion_incomplete" });
  task = await controller.update({ expected_revision: task.revision, action: "propose_completion", completion: [{ criterion_id: "report", evidence_refs: ["result_1", nodeId(1)] }] }, "complete", context);
  assert.equal(task.state, "completing");
  finish(); await conversation.waitForIdle(context); await controller.reconcile();
  assert.equal((await controller.current(context)).state, "completed");
  assert.equal(calls.some(call => call.command.startsWith("job.")), false);
});

test("task sources reject internal continuations and Monitor queries never resume work", async t => {
  const fixtureValue = await fixture(t);
  const { controller, conversation, faux, begin, admission, harness, kernel } = fixtureValue;
  const task = await begin(); faux.setResponses([fauxAssistantMessage("partial")]);
  await controller.reconcile(); await conversation.waitForIdle(context);
  const automatic = await admission.status(`task:${task.user_task_id}:continue:1`, context);
  await assert.rejects(controller.begin({ title: "fake", objective: "fake", source_submission_ids: [String(automatic.id)], criteria: [] }, "fake", context), { code: "task_source_invalid" });
  const service = createMonitorService({ controller, harness, conversation, kernel, workspaceId: "workspace", sessionId: "session", LiveDoc });
  for (const method of ["monitor/overview", "monitor/tasks", "monitor/health", "monitor/jobs", "monitor/runs"]) {
    assert.equal((await service.handle({ method, params: {} }, context)).error, null);
  }
  assert.equal((await controller.current(context)).continuation.sequence, 1);
  assert.equal((await service.handle({ method: "monitor/overview", params: { session_id: "other" } }, context)).error.code, "monitor_scope_mismatch");
});

test("durable tool progress resets idle-loop protection without mandatory task checkpoints", async t => {
  const { controller, conversation, faux, begin } = await fixture(t);
  await begin();
  for (let round = 0; round < 5; round++) {
    faux.setResponses([fauxAssistantMessage("Partial report")]);
    await controller.reconcile(); await conversation.waitForIdle(context);
    await controller.observeToolResults([{ id: 100 + round, model: [{ role: "toolResult", toolName: "research_result", isError: false,
      details: { result: { result: { id: `result_${round}` } } }, content: [] }] }], context);
  }
  assert.equal((await controller.current(context)).state, "active");
  assert.equal((await controller.current(context)).continuation.no_progress, 0);
  assert.equal((await controller.current(context)).progress_version, 5);
  const before = (await controller.current(context)).revision;
  await controller.observeToolResults([{ id: 104, model: [{ role: "toolResult", toolName: "research_result", isError: false,
    details: { result: { result: { id: "result_4" } } }, content: [] }] }], context);
  assert.equal((await controller.current(context)).revision, before);
});

test("canonical task tools run through the trusted Harness envelope", async t => {
  const { controller, conversation, faux, admission } = await fixture(t);
  faux.setResponses([fauxAssistantMessage("begin")]);
  const input = await admission.submitUser({ requestId: "source", content: "Complete the research" }, context);
  await conversation.waitForIdle(context);
  const toolContext = createToolExecutionContext({ workspace_root: "/workspace", session_id: "session", operation_id: null,
    allowed_authorities: ["task_control"], allowed_effects: ["read", "task_write"] });
  const [begin, read] = createTaskTools(() => controller).map(tool => wrapToolForHarness(tool, { toolContext,
    invocation: api => ({ workspaceRoot: "/workspace", sessionId: "session", operationId: String(api.taskId) }) }));
  const result = await begin.execute({ title: "Work", objective: "Complete research", source_submission_ids: [String(input.id)],
    criteria: [{ id: "report", description: "Deliver a report" }] }, { taskId: 99, callId: "begin" }, context);
  assert.equal(result.isError, undefined);
  assert.equal(result.details.envelope.ok, true);
  const readResult = await read.execute({}, { taskId: 100, callId: "read" }, context);
  assert.equal(readResult.details.result.user_task_id, result.details.result.user_task_id);
});

test("task context bounds original requirements, waits, progress and escaped text", async t => {
  const { begin } = await fixture(t);
  const task = await begin();
  const long = "\u0001中文😀".repeat(10000);
  const projected = projectUserTask({ ...task, title: long, objective: long, reason: long,
    sources: Array.from({ length: 1000 }, (_, id) => ({ submission_id: String(id), entry_id: id, text: long })),
    criteria: Array.from({ length: 1000 }, (_, id) => ({ id: String(id), description: long })),
    wait: { mode: "all", job_ids: Array(1000).fill(long) },
    progress: { summary: long, at: "2026-10-10", evidence_refs: Array(1000).fill(long) },
  });
  assert.ok(Buffer.byteLength(JSON.stringify(projected)) < 16000);
  assert.equal(projected.sources.length, 4);
  assert.equal(projected.sources_omitted, 996);
  assert.equal(projected.projection_truncated, true);
  assert.match(projected.required_action, /task_read/);
});

test("read-only task listing never retries a pending cancellation; reconciliation does", async t => {
  const { controller, kernel } = await fixture(t);
  let attempts = 0;
  kernel.execute_command = async command => {
    assert.equal(command, "job.cancel"); attempts += 1;
    if (attempts === 1) throw new Error("temporary runtime disconnect");
    return { job_id: "job_1", state: "cancelled" };
  };
  await assert.rejects(controller.cancelJob({ job_id: "job_1", request_id: "cancel-single" }, context));
  await controller.list(context);
  assert.equal(attempts, 1);
  await controller.reconcile();
  assert.equal(attempts, 2);
  const result = await controller.cancelJob({ job_id: "job_1", request_id: "cancel-single" }, context);
  assert.equal(result.job.state, "cancelled");
  assert.equal(attempts, 2);
});

for (const mode of ["all", "any"]) test(`completed ${mode} waits release Job binding during the same live run`, async t => {
  const { controller, conversation, faux, begin, jobStates, harness } = await fixture(t);
  await begin();
  let entered, finish;
  const ready = new Promise(resolve => { entered = resolve; });
  faux.setResponses([() => new Promise(resolve => { entered(); finish = () => resolve(fauxAssistantMessage("Independent work can now continue")); })]);
  await controller.reconcile(); await ready;
  try {
    jobStates.set("job_1", "running"); jobStates.set("job_2", "running");
    let task = await controller.current(context);
    await controller.update({ action: "wait", expected_revision: task.revision,
      wait: { job_ids: ["job_1", "job_2"], mode } }, "wait-live", context);
    await assert.rejects(controller.binding(context), { code: "task_not_active" });
    jobStates.set("job_1", "succeeded");
    if (mode === "all") {
      await assert.rejects(controller.binding(context), { code: "task_not_active" });
      jobStates.set("job_2", "failed");
    }
    await controller.reconcile();
    assert.ok((await harness.snapshot(LiveDoc, conversation.id, context)).run);
    task = await controller.current(context);
    assert.equal(task.state, "active"); assert.equal(task.wait, null);
    assert.deepEqual(await controller.binding(context), { user_task_id: task.user_task_id });
    assert.equal(task.continuation.sequence, 1, "settling wait must not submit another run");
  } finally { finish(); }
  await conversation.waitForIdle(context);
});

test("pause wins while completed waits are being observed", async t => {
  const { controller, begin, jobStates, kernel } = await fixture(t);
  let task = await begin(); jobStates.set("job_1", "running");
  task = await controller.update({ action: "wait", expected_revision: task.revision,
    wait: { job_ids: ["job_1"], mode: "all" } }, "wait", context);
  let entered, finish;
  const ready = new Promise(resolve => { entered = resolve; });
  const execute = kernel.execute_command;
  kernel.execute_command = async (command, params) => command === "job.status"
    ? new Promise(resolve => { entered(); finish = () => resolve({ job_id: "job_1", state: "succeeded" }); })
    : execute(command, params);
  const binding = controller.binding(context);
  const rejected = assert.rejects(binding, { code: "task_not_active" });
  await ready;
  await controller.control({ user_task_id: task.user_task_id, expected_revision: task.revision,
    action: "pause", request_id: "pause-wait" }, context);
  finish(); await rejected;
  assert.equal((await controller.current(context)).state, "paused");
});

for (const producer of ["task_controller", "monitor"]) for (const control of [null, "pause", "cancel", "user"]) test(`${producer} blocked run finalization respects ${control || "its consumed run identity"}`, async t => {
  const { controller, begin, conversation, faux, admission, harness } = await fixture(t);
  let task = await begin();
  let entered, finish;
  const ready = new Promise(resolve => { entered = resolve; });
  faux.setResponses([() => new Promise(resolve => { entered(); finish = () => resolve(fauxAssistantMessage("Need a missing input from the user")); })]);
  const requestId = producer === "monitor" ? "monitor-block" : `task:${task.user_task_id}:continue:1`;
  if (producer === "monitor") await admission.submitInternal({ requestId, producer, content: "Review the completed fixture Job",
    identity: { event_ids: ["event_fixture"] }, basis: { task_revision: task.revision,
      control_epoch: task.control_epoch, task_owners: [task.user_task_id] } }, context);
  else await controller.reconcile();
  await ready;
  const record = await admission.status(requestId, context);
  const origin = await admission.origin(record, context);
  try {
    task = await controller.current(context);
    task = await controller.update({ action: "block", expected_revision: task.revision,
      reason: "Missing required boundary data; no independent analysis remains" }, "block", context);
    await controller.assertExecutionAllowed(record, origin, context);
    await assert.rejects(controller.assertExecutionAllowed(record, { ...origin, consumption: null }, context));
    await assert.rejects(controller.binding(context), { code: "task_not_active" });
    if (control === "user") {
      faux.setResponses([fauxAssistantMessage("The blocker still requires a missing input")]);
      await admission.submitUser({ requestId: "new-question", content: "Explain the blocker" }, context);
      await assert.rejects(controller.assertExecutionAllowed(record, origin, context));
    } else if (control) {
      await controller.control({ user_task_id: task.user_task_id, expected_revision: task.revision,
        action: control, request_id: control, ...(control === "cancel" ? { jobs: "keep" } : {}) }, context);
      await assert.rejects(controller.assertExecutionAllowed(record, origin, context));
    }
  } finally { finish(); }
  await conversation.waitForIdle(context);
  await assert.rejects(controller.assertExecutionAllowed(record, origin, context), undefined,
    "the finalization permission expires with the live run");
  await controller.reconcile();
  assert.equal((await controller.current(context)).continuation.sequence, 1);
});

test("Job receipts produce actionable evidence errors without masquerading as owned Jobs", async t => {
  const { controller, begin, jobStates } = await fixture(t);
  const task = await begin(); jobStates.set("job_1", "succeeded");
  await assert.rejects(controller.update({ action: "progress", expected_revision: task.revision,
    evidence_refs: ["job_result_1"] }, "receipt", context), /cite the owning job_id/);
  await assert.rejects(controller.update({ action: "progress", expected_revision: task.revision,
    evidence_refs: ["job_2"] }, "foreign", context), /must belong/);
  const updated = await controller.update({ action: "progress", expected_revision: task.revision,
    evidence_refs: ["job_1"] }, "owned", context);
  assert.equal(updated.progress_version, 1);
});

test("scope cannot be weakened by reusing the original instruction", async t => {
  const { controller, begin } = await fixture(t);
  const task = await begin();
  await assert.rejects(controller.update({ action: "refine", expected_revision: task.revision,
    source_submission_ids: [task.sources[0].submission_id],
    criteria: [{ id: "partial", description: "Explain missing work instead" }] }, "weaken", context),
  { code: "task_source_required" });
  assert.deepEqual((await controller.current(context)).criteria, task.criteria);
});

test("transient wait status failure preserves user access and can recover", async t => {
  const { controller, begin, jobStates, kernel } = await fixture(t);
  let task = await begin(); jobStates.set("job_1", "running");
  task = await controller.update({ action: "wait", expected_revision: task.revision,
    wait: { job_ids: ["job_1"], mode: "all" } }, "wait-unavailable", context);
  const execute = kernel.execute_command;
  kernel.execute_command = async (command, params) => {
    if (command === "job.status") throw new Error("Fixture status service unavailable");
    return execute(command, params);
  };
  assert.equal((await controller.current(context)).state, "waiting");
  assert.equal(controller.health().error.code, "task_wait_observation_failed");
  await assert.rejects(controller.binding(context), { code: "task_not_active" });
  kernel.execute_command = execute; jobStates.set("job_1", "succeeded");
  assert.deepEqual(await controller.binding(context), { user_task_id: task.user_task_id });
});

const transientFailure = () => ({ ...fauxAssistantMessage(""), stopReason: "error", errorMessage: "503 Service Unavailable" });
const recoveryOptions = clock => ({ recoveryPolicy: { maxRetries: 2, baseDelayMs: 100, maxDelayMs: 200 }, now: () => clock.value });

test("budget failure with a queued compaction settles after Job wait and resumes once", async t => {
  let block = false, queued;
  const env = await fixture(t, new MemoryStorage(), {}, async () => {
    if (!block) return;
    block = false;
    let task = await env.controller.current(context);
    await env.controller.update({ action: "wait", expected_revision: task.revision,
      wait: { job_ids: ["job_1"], mode: "all" } }, "wait-before-budget-failure", context);
    const first = (await env.conversation.context(context)).entries[0].id;
    queued = await env.conversation.submit({ type: "write", requestId: "pending-summary",
      entry: { kind: "pi.compaction", head: first,
        model: [{ role: "user", content: "Retained research constraints", timestamp: 0 }] } }, context);
    return { block: "context_budget_exceeded: fixture input exceeds operating budget" };
  });
  await env.begin(); env.jobStates.set("job_1", "running"); block = true;
  env.faux.setResponses([() => { assert.fail("blocked input must not reach provider"); }]);
  await env.controller.reconcile(); await env.conversation.waitForIdle(context);
  assert.equal((await queued.status(context)).status, "queued");
  env.jobStates.set("job_1", "succeeded");
  await env.reopen(); await env.controller.reconcile();
  const task = await env.controller.current(context);
  assert.equal(task.state, "active");
  assert.equal(task.continuation.reservation, null);
  assert.equal(task.execution_recovery.state, "attention_required");
  assert.equal(task.execution_recovery.reason, "request_blocked");
  await env.controller.reconcile();
  assert.equal((await env.controller.current(context)).continuation.sequence, 1);
  env.faux.setResponses([fauxAssistantMessage("Resume from retained evidence")]);
  await env.controller.control({ user_task_id: task.user_task_id, action: "resume", request_id: "resume-after-budget-fix",
    expected_revision: task.revision }, context);
  await env.controller.reconcile(); await env.conversation.waitForIdle(context);
  assert.equal((await queued.status(context)).status, "done");
  assert.equal((await env.harness.snapshot(InboxDoc, env.conversation.id, context)).items.length, 0);
  assert.equal((await env.controller.current(context)).continuation.sequence, 2);
  assert.equal((await env.admission.status("task:task_1:continue:1", context)).status, "unanswered");
  assert.equal((await env.admission.status("task:task_1:continue:2", context)).status, "done");
});

test("transient execution recovers once after its durable delay without blocking research", async t => {
  const clock = { value: 1000 }, env = await fixture(t, new MemoryStorage(), recoveryOptions(clock));
  const task = await env.begin();
  env.faux.setResponses([transientFailure()]);
  await env.controller.reconcile(); await env.conversation.waitForIdle(context);
  await env.controller.reconcile();
  let current = await env.controller.current(context);
  assert.equal(current.state, "active");
  assert.equal(current.execution_recovery.state, "retrying");
  assert.equal(current.execution_recovery.failures, 1);
  assert.equal(Date.parse(current.execution_recovery.next_retry_at), 1100);
  const original = await env.admission.status(`task:${task.user_task_id}:continue:1`, context);
  assert.equal(original.status, "unanswered");
  await env.reopen();
  await env.controller.reconcile();
  assert.equal((await env.controller.current(context)).continuation.sequence, 1);
  clock.value = 1100;
  env.faux.setResponses([fauxAssistantMessage("Continue analysis from the retained evidence")]);
  await Promise.all([env.controller.reconcile(), env.controller.reconcile()]);
  await env.conversation.waitForIdle(context);
  assert.equal((await env.controller.current(context)).continuation.sequence, 2);
  assert.equal((await env.admission.status(original.requestId, context)).status, "unanswered");
  // Hold independent work to inspect the successful recovery settlement without launching another reply.
  let entered, finish;
  const ready = new Promise(resolve => { entered = resolve; });
  env.faux.setResponses([() => new Promise(resolve => { entered(); finish = () => resolve(fauxAssistantMessage("Continuing")); })]);
  await env.controller.reconcile(); await ready;
  try { assert.equal((await env.controller.current(context)).execution_recovery, null); }
  finally { finish(); }
  await env.conversation.waitForIdle(context);
});

test("recovery budget survives restart, ignores new evidence, and rejects Monitor bypass", async t => {
  const clock = { value: 1000 }, env = await fixture(t, new MemoryStorage(), recoveryOptions(clock));
  await env.begin();
  for (let failure = 1; failure <= 3; failure++) {
    env.faux.setResponses([transientFailure()]);
    await env.controller.reconcile(); await env.conversation.waitForIdle(context);
    let current = await env.controller.current(context);
    await env.controller.update({ action: "progress", expected_revision: current.revision,
      evidence_refs: [`result_${failure}`] }, `evidence-${failure}`, context);
    await env.controller.reconcile();
    current = await env.controller.current(context);
    assert.equal(current.execution_recovery.failures, failure);
    assert.equal(current.state, "active");
    assert.equal(current.execution_recovery.state, failure < 3 ? "retrying" : "attention_required");
    await assert.rejects(env.admission.submitInternal({ requestId: `event-${failure}`, producer: "monitor",
      identity: { event_ids: ["event_1"] }, content: "A Job finished", basis: { task_revision: current.revision,
        control_epoch: current.control_epoch, task_owners: [current.user_task_id] } }, context), { code: "task_execution_recovery" });
    await env.reopen();
    clock.value += failure === 1 ? 100 : 200;
  }
  await env.controller.reconcile();
  assert.equal((await env.controller.current(context)).continuation.sequence, 3);
  const current = await env.controller.current(context);
  env.faux.setResponses([fauxAssistantMessage("The provider has recovered")]);
  await env.controller.control({ user_task_id: current.user_task_id, action: "resume", request_id: "resume-execution",
    expected_revision: current.revision }, context);
  await env.controller.reconcile(); await env.conversation.waitForIdle(context);
  assert.equal((await env.controller.current(context)).continuation.sequence, 4);
});

for (const scenario of ["tool", "progress", "wait", "disabled", "failed", "duplicate", "query", "pause", "cancel", "superseded"])
test(`user recovery ${scenario} follows current input evidence and Pi outcome`, async t => {
  const clock = { value: 1000 }, options = recoveryOptions(clock), env = await fixture(t, new MemoryStorage(), options);
  await env.begin();
  await env.controller.observeToolResults(observed("research_result", { result: { id: "result_old" } }), context);
  env.faux.setResponses([transientFailure()]);
  await env.controller.reconcile(); await env.conversation.waitForIdle(context); await env.controller.reconcile();
  const failed = await env.admission.status("task:task_1:continue:1", context);
  const entered = Promise.withResolvers(), finish = Promise.withResolvers();
  env.faux.setResponses([async () => {
    entered.resolve(); await finish.promise;
    return scenario === "failed" ? transientFailure() : fauxAssistantMessage("User response finished");
  }]);
  const input = await env.admission.submitUser({ requestId: "user-recovery", content: "Continue the research" }, context);
  await entered.promise;
  try {
    let task = await env.controller.current(context);
    assert.equal(task.execution_recovery.state, "attention_required", "admission alone cannot resume automatic work");
    if (scenario === "progress") {
      await env.controller.update({ action: "progress", expected_revision: task.revision,
        evidence_refs: ["result_new"] }, "user-evidence", context);
    } else if (scenario === "wait") {
      env.jobStates.set("job_new", "running");
      await env.controller.observeToolResults(observed("job_start", { job_id: "job_new", submitted_at: "now" }), context);
      task = await env.controller.current(context);
      await env.controller.update({ action: "wait", expected_revision: task.revision,
        wait: { job_ids: ["job_new"], mode: "all" } }, "user-wait", context);
    } else if (scenario !== "query") {
      await env.controller.observeToolResults(observed("research_result", { result: { id: scenario === "duplicate" ? "result_old" : "result_new" } }), context);
    }
    if (["pause", "cancel"].includes(scenario)) {
      task = await env.controller.current(context);
      await env.controller.control({ user_task_id: task.user_task_id, expected_revision: task.revision,
        action: scenario, request_id: `user-${scenario}`, ...(scenario === "cancel" ? { jobs: "keep" } : {}) }, context);
    } else if (scenario === "superseded") {
      env.faux.setResponses([fauxAssistantMessage("Answer the later question only")]);
      await env.admission.submitUser({ requestId: "later-query", content: "What just happened?", whenBusy: "followUp" }, context);
    }
  } finally { finish.resolve(); }
  await env.conversation.waitForIdle(context);
  if (scenario === "disabled") options.enabled = false;
  await env.reopen();
  env.faux.setResponses([fauxAssistantMessage("Continue from saved evidence")]);
  await env.controller.reconcile(); await env.conversation.waitForIdle(context);
  let task = await env.controller.current(context);
  assert.equal((await env.admission.status(failed.requestId, context)).status, "unanswered", "failure history is retained");
  if (["tool", "progress", "wait", "disabled"].includes(scenario)) {
    assert.equal(task.execution_recovery, null);
    assert.equal(task.continuation.sequence, ["wait", "disabled"].includes(scenario) ? 1 : 2);
    assert.ok(task.audit.some(item => item.action === "user_execution_recovered"));
    if (scenario === "wait") {
      assert.equal(task.state, "waiting");
      env.jobStates.set("job_new", "succeeded");
      await env.controller.reconcile(); await env.conversation.waitForIdle(context);
      task = await env.controller.current(context);
      assert.equal(task.continuation.sequence, 2, "completed Job wait resumes automatically");
    }
  } else {
    assert.equal(task.continuation.sequence, 1);
    if (["pause", "cancel"].includes(scenario)) assert.equal(task.state, scenario === "pause" ? "paused" : "cancelled");
    else {
      assert.equal(task.execution_recovery.state, "attention_required");
      assert.equal(task.execution_recovery.submission_id, scenario === "failed" ? input.id : failed.id);
      await env.controller.reconcile();
      assert.equal((await env.controller.current(context)).continuation.sequence, 1);
    }
  }
});

for (const control of ["pause", "cancel", "user"]) test(`${control} supersedes pending execution recovery`, async t => {
  const clock = { value: 1000 }, env = await fixture(t, new MemoryStorage(), recoveryOptions(clock));
  await env.begin(); env.faux.setResponses([transientFailure()]);
  await env.controller.reconcile(); await env.conversation.waitForIdle(context); await env.controller.reconcile();
  let task = await env.controller.current(context);
  if (control === "user") {
    env.faux.setResponses([fauxAssistantMessage("A transient execution failure occurred")]);
    const input = await env.admission.submitUser({ requestId: "ask", content: "Why did execution stop?" }, context);
    await env.conversation.waitForIdle(context);
    clock.value = 2000; await env.controller.reconcile();
    task = await env.controller.current(context);
    assert.equal(task.execution_recovery.state, "attention_required");
    assert.equal(task.continuation.sequence, 1);
    const resumed = await env.controller.update({ action: "refine", expected_revision: task.revision,
      source_submission_ids: [String(input.id)] }, "refine-recovery", context);
    assert.equal(resumed.execution_recovery, null);
  } else {
    await env.controller.control({ user_task_id: task.user_task_id, action: control, request_id: control,
      expected_revision: task.revision, ...(control === "cancel" ? { jobs: "keep" } : {}) }, context);
    clock.value = 2000; await env.controller.reconcile();
    assert.equal((await env.controller.current(context)).continuation.sequence, 1);
    assert.equal((await env.controller.current(context)).state, control === "pause" ? "paused" : "cancelled");
  }
});

test("an unclassified execution fault requires attention without declaring a research blocker", async t => {
  const env = await fixture(t);
  await env.begin(); env.faux.setResponses([() => { throw new Error("Malformed execution state"); }]);
  await env.controller.reconcile(); await env.conversation.waitForIdle(context); await env.controller.reconcile();
  const task = await env.controller.current(context);
  assert.equal(task.state, "active");
  assert.equal(task.execution_recovery.state, "attention_required");
  assert.equal(task.execution_recovery.next_retry_at, null);
  await env.controller.reconcile();
  assert.equal((await env.controller.current(context)).continuation.sequence, 1);
});


test("disabling recovery prevents a pending retry after restart", async t => {
  const clock = { value: 1000 }, options = recoveryOptions(clock);
  const env = await fixture(t, new MemoryStorage(), options);
  await env.begin(); env.faux.setResponses([transientFailure()]);
  await env.controller.reconcile(); await env.conversation.waitForIdle(context); await env.controller.reconcile();
  assert.equal((await env.controller.current(context)).execution_recovery.state, "retrying");
  options.recoveryPolicy.maxRetries = 0;
  await env.reopen(); clock.value = 2000;
  await env.controller.reconcile();
  const task = await env.controller.current(context);
  assert.equal(task.state, "active");
  assert.equal(task.execution_recovery.state, "attention_required");
  assert.equal(task.continuation.sequence, 1);
});

const taskControlCall = args => ({ ...fauxAssistantMessage(""), stopReason: "toolUse",
  content: [{ type: "toolCall", id: "user-control", name: "task_update", arguments: args }] });

for (const action of ["pause", "cancel"]) test(`natural-language ${action} persists through the model tool and survives reconciliation/reopen`, async t => {
  const env = await fixture(t);
  await env.begin();
  env.jobStates.set("job_55", "running"); env.jobStates.set("job_56", "running");
  const params = async control => ({ action: "apply_user_control", control,
    expected_revision: (await env.controller.current(context)).revision,
    source_submission_ids: [String((await env.admission.latest(context)).id)],
    ...(control === "cancel" ? { jobs: "cancel" } : {}) });
  env.faux.setResponses([async () => taskControlCall(await params(action)), async () => {
    const current = await env.controller.current(context);
    assert.equal(current.state, action === "pause" ? "paused" : "cancelled");
    assert.ok(await env.controller.toolRestriction(context, "job_start"));
    assert.ok(await env.controller.toolRestriction(context, "task_begin"));
    assert.equal(await env.controller.toolRestriction(context, "job_cancel"), null);
    await assert.rejects(env.controller.binding(context), { code: "task_not_active" });
    return fauxAssistantMessage("已停止这项研究，不会继续启动计算或分析。");
  }]);
  const input = await env.admission.submitUser({ requestId: "stop-research", content: action === "pause" ? "先暂停研究，保留计算" : "停掉这个研究，也停止正在运行的计算" }, context);
  await env.conversation.waitForIdle(context);
  assert.equal((await (await env.harness.submission(input.id, context)).status(context)).status, "done", "stop acknowledgement must be deliverable");
  for (let i = 0; i < 4; i++) await env.controller.reconcile();
  let task = await env.controller.current(context);
  assert.equal(task.state, action === "pause" ? "paused" : "cancelled");
  assert.equal(task.continuation.sequence, 0);
  assert.equal(task.sources.at(-1).submission_id, String(input.id));
  assert.equal(env.jobStates.get("job_55"), action === "cancel" ? "cancelled" : "running");
  await env.reopen();
  for (let i = 0; i < 4; i++) await env.controller.reconcile();
  task = await env.controller.current(context);
  assert.equal(task.continuation.sequence, 0);
  if (action === "cancel") assert.deepEqual((await env.controller.prepareMonitor([
    { event: { event_id: "ended", user_task_id: task.user_task_id } }], context)).events, []);
  await assert.rejects(env.admission.submitInternal({ requestId: "late-event", producer: "monitor", content: "Job ended",
    identity: { event_ids: ["ended"] }, basis: { task_revision: task.revision,
      control_epoch: task.control_epoch, task_owners: [task.user_task_id] } }, context), { code: "task_paused" });
  if (action === "pause") {
    env.faux.setResponses([async () => taskControlCall(await params("resume")), fauxAssistantMessage("继续研究")]);
    await env.admission.submitUser({ requestId: "resume-research", content: "继续这个研究" }, context);
    await env.conversation.waitForIdle(context);
    assert.equal((await env.controller.current(context)).state, "active");
  }
});

test("task cancellation commits before unavailable Job discovery, and retries cleanup without another model run", async t => {
  const env = await fixture(t); await env.begin();
  env.jobStates.set("job_55", "running");
  const execute = env.kernel.execute_command;
  let unavailable = true;
  env.kernel.execute_command = async (command, params) => {
    if (command === "job.list") {
      assert.equal((await env.controller.current(context)).state, "cancelled", "scheduling must stop before external Job discovery");
      if (unavailable) throw new Error("deterministic disconnected Job backend");
    }
    return execute(command, params);
  };
  env.faux.setResponses([async () => taskControlCall({ action: "apply_user_control", control: "cancel", jobs: "cancel",
    expected_revision: (await env.controller.current(context)).revision,
    source_submission_ids: [String((await env.admission.latest(context)).id)] }), fauxAssistantMessage("研究已取消，计算取消仍待核实。")]);
  await env.admission.submitUser({ requestId: "stop-offline", content: "停掉研究和计算" }, context);
  await env.conversation.waitForIdle(context);
  let task = await env.controller.current(context);
  assert.equal(task.state, "cancelled"); assert.equal(task.cancel_jobs.discovery_pending, true);
  assert.ok(task.cancel_jobs.errors.discovery);
  unavailable = false;
  await env.reopen(); await env.controller.reconcile();
  task = await env.controller.current(context);
  assert.equal(task.cancel_jobs.discovery_pending, false);
  assert.deepEqual(task.cancel_jobs.pending, []);
  assert.equal(task.cancel_jobs.receipts.job_55.state, "cancelled");
  assert.equal(task.continuation.sequence, 0);
});

for (const source of ["automatic", "historical"]) test(`internal runs cannot control a task using ${source} authorization`, async t => {
  const env = await fixture(t); const original = await env.begin();
  let entered, finish;
  const ready = new Promise(resolve => { entered = resolve; });
  env.faux.setResponses([() => new Promise(resolve => { entered(); finish = () => resolve(fauxAssistantMessage("partial")); })]);
  await env.controller.reconcile(); await ready;
  try {
    const task = await env.controller.current(context);
    const id = source === "automatic" ? String((await env.admission.latest(context)).id) : original.sources[0].submission_id;
    await assert.rejects(env.controller.update({ action: "apply_user_control", control: "cancel", jobs: "cancel",
      expected_revision: task.revision, source_submission_ids: [id] }, "invalid-control", context),
    { code: source === "automatic" ? "task_source_invalid" : "task_control_source_invalid" });
    assert.equal((await env.controller.current(context)).state, "active");
    assert.equal(env.calls.some(call => call.command === "job.cancel"), false);
  } finally { finish(); }
  await env.conversation.waitForIdle(context);
});

test("a stop tool cannot reuse a superseded user instruction, and its own receipt replays without new cancellations", async t => {
  const env = await fixture(t); await env.begin();
  let entered, finish;
  const ready = new Promise(resolve => { entered = resolve; });
  env.faux.setResponses([() => new Promise(resolve => { entered(); finish = () => resolve(fauxAssistantMessage("ack")); }), fauxAssistantMessage("new input")]);
  const first = await env.admission.submitUser({ requestId: "first-stop", content: "停止研究" }, context);
  await ready;
  try {
    await env.admission.submitUser({ requestId: "new-user", content: "先说明现在的状态", whenBusy: "followUp" }, context);
    const task = await env.controller.current(context);
    await assert.rejects(env.controller.update({ action: "apply_user_control", control: "pause",
      expected_revision: task.revision, source_submission_ids: [String(first.id)] }, "old-stop", context), { code: "task_control_source_invalid" });
  } finally { finish(); }
  await env.conversation.waitForIdle(context);
  let applied, request;
  env.jobStates.set("job_55", "running");
  env.faux.setResponses([async () => {
    request = { action: "apply_user_control", control: "cancel", jobs: "cancel",
      expected_revision: (await env.controller.current(context)).revision,
      source_submission_ids: [String((await env.admission.latest(context)).id)] };
    applied = await env.controller.update(request, "stable-stop", context);
    return fauxAssistantMessage("已停止");
  }]);
  await env.admission.submitUser({ requestId: "final-stop", content: "现在停止研究并取消计算" }, context);
  await env.conversation.waitForIdle(context);
  const count = env.calls.filter(call => call.command === "job.cancel").length;
  const replayed = await env.controller.update(request, "stable-stop", context);
  assert.equal(replayed.task.state, applied.task.state);
  assert.equal(env.calls.filter(call => call.command === "job.cancel").length, count);
  await assert.rejects(env.controller.update({ ...request, control: "resume", jobs: undefined }, "stable-stop", context), { code: "request_id_reused" });
});

for (const control of ["pause", "cancel"]) test(`a ${control} steered into a consumed automatic run permits only its stop finalization`, async t => {
  const env = await fixture(t); await env.begin();
  let entered, finish, stopped, acknowledge;
  const ready = new Promise(resolve => { entered = resolve; });
  const finalized = new Promise(resolve => { stopped = resolve; });
  let stopInput;
  env.faux.setResponses([
    () => new Promise(resolve => { entered(); finish = () => resolve({ ...fauxAssistantMessage(""), stopReason: "toolUse",
      content: [{ type: "toolCall", id: "read-before-stop", name: "task_read", arguments: {} }] }); }),
    async () => taskControlCall({ action: "apply_user_control", control,
      expected_revision: (await env.controller.current(context)).revision,
      source_submission_ids: [String(stopInput.id)], ...(control === "cancel" ? { jobs: "keep" } : {}) }),
    () => new Promise(resolve => { stopped(); acknowledge = () => resolve(fauxAssistantMessage("研究已停止")); }),
  ]);
  await env.controller.reconcile(); await ready;
  const automatic = await env.admission.latest(context);
  stopInput = await env.admission.submitUser({ requestId: "steered-stop", content: "停止研究", whenBusy: "steer" }, context);
  finish(); await finalized;
  const record = await (await env.harness.submission(automatic.id, context)).status(context);
  const origin = await env.admission.origin(record, context);
  try {
    const task = await env.controller.current(context);
    assert.equal(task.state, control === "pause" ? "paused" : "cancelled");
    await env.controller.assertExecutionAllowed(record, origin, context);
    await assert.rejects(env.controller.assertExecutionAllowed(record, { ...origin, consumption: null }, context));
    await assert.rejects(env.controller.begin({ title: "Replacement", objective: "Restart",
      source_submission_ids: [String(stopInput.id)], criteria: [{ id: "again", description: "More work" }] }, "replacement", context), { code: "task_not_active" });
    await assert.rejects(env.controller.binding(context), { code: "task_not_active" });
    if (control === "pause") {
      await env.controller.control({ user_task_id: task.user_task_id, action: "pause", expected_revision: task.revision,
        request_id: "new-monitor-pause" }, context);
      await assert.rejects(env.controller.assertExecutionAllowed(record, origin, context));
    }
  } finally { acknowledge(); }
  await env.conversation.waitForIdle(context);
  await assert.rejects(env.controller.assertExecutionAllowed(record, origin, context));
  for (let i = 0; i < 3; i++) await env.controller.reconcile();
  assert.equal((await env.controller.current(context)).continuation.sequence, 1);
});
