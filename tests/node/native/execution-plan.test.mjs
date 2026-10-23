import test from "node:test";
import assert from "node:assert/strict";
import { resolveExecutionPolicy, resolveExecutionPlan, executionItemContext, projectExecutionPlan } from "../../../apps/agent/tasks/execution-plan.mjs";

const selection = platform => ({ target: { platform, scheduler_entry: "main" }, executor: "qrun",
  route_digest: "sha256:" + "a".repeat(64), selection_mode: "explicit" });
const kernel = { async execute_command(command, params) {
  assert.equal(command, "job_resolve_target");
  return selection(params.target.platform);
} };
const policy = { selections: [selection("FEDCluster"), selection("Com30")], max_in_flight: 2, max_attempts: 10 };
const item = (id, platform, depends_on = []) => ({ id, work_id: id, target: { platform }, depends_on,
  resources: { cpus: 2, memory_mb: 1024 } });

test("one task resolves independent items on multiple platforms", async () => {
  const plan = await resolveExecutionPlan(kernel, { items: [item("a", "FEDCluster"), item("b", "Com30")] }, policy, null, []);
  assert.deepEqual(plan.items.map(row => row.selection.target.platform), ["FEDCluster", "Com30"]);
  assert.equal(plan.revision, 1);
});

test("plan rejects cycles and unknown dependencies before dispatch", async () => {
  await assert.rejects(resolveExecutionPlan(kernel, { items: [item("a", "Com30", ["b"]), item("b", "Com30", ["a"])] }, policy, null, []), /cycle/);
  await assert.rejects(resolveExecutionPlan(kernel, { items: [item("a", "Com30", ["missing"])] }, policy, null, []), /Unknown dependency/);
});

test("plan cannot expand destinations beyond the pinned user policy", async () => {
  await assert.rejects(resolveExecutionPlan(kernel, { items: [item("a", "1WCluster")] }, policy, null, []), /outside/);
});

test("dependency handoff requires completion and carries exact artifact references", async () => {
  const plan = await resolveExecutionPlan(kernel, { items: [item("a", "FEDCluster"), item("b", "Com30", ["a"])] }, policy, null, []);
  const task = { execution_selection: policy.selections[0], execution_policy: policy, execution_plan: plan };
  assert.throws(() => executionItemContext(task, "b"), /not been collected/);
  plan.items[0].completion = { artifact_ids: ["art_1"], evidence_refs: ["result_1"] };
  const context = executionItemContext(task, "b");
  assert.deepEqual(context.item.input_artifact_ids, ["art_1"]);
  assert.equal(context.selection.target.platform, "Com30");
});

test("submitted items are immutable while independent unsubmitted work can be extended", async () => {
  const draft = { items: [item("a", "Com30")] };
  const plan = await resolveExecutionPlan(kernel, draft, policy, null, []);
  const jobs = [{ job_id: "job_1", execution_item: { id: "a" }, state: "unknown" }];
  await assert.rejects(resolveExecutionPlan(kernel, { items: [item("a", "FEDCluster")] }, policy, plan, jobs), /cannot be changed/);
  const extended = await resolveExecutionPlan(kernel, { items: [...draft.items, item("b", "FEDCluster")] }, policy, plan, jobs);
  assert.equal(extended.revision, 2);
  assert.equal(projectExecutionPlan({ execution_plan: extended }, jobs).items[0].state, "unknown");
});

test("policy placement evidence must cite actual user text", async () => {
  const sources = [{ submission_id: "1", text: "Use Com30 with Qrun" }];
  const draft = { placements: [{ target: { platform: "Com30" }, intent: { source_submission_id: "1", source_text: "Use Com30 with Qrun" } }], max_in_flight: 2, max_attempts: 5 };
  assert.equal((await resolveExecutionPolicy(kernel, draft, selection("Com30"), sources)).max_in_flight, 2);
  draft.placements[0].intent.source_text = "Invented destination permission";
  await assert.rejects(resolveExecutionPolicy(kernel, draft, selection("Com30"), sources), /actual cited user/);
});

test("automatic placement uses only permitted software and known unreserved capacity", async () => {
  const automatic = { ...policy, automatic_placement: true };
  const capacities = { Com30: { cpus: 2, memory_mb: 1024 }, FEDCluster: { cpus: 2, memory_mb: 1024 } };
  const resources = { async execute_command(command, params) {
    if (command === "job_resolve_target") return selection(params.target.platform);
    if (command === "job_platforms") return { platforms: Object.fromEntries(Object.keys(capacities).map(name =>
      [name, { schedulers: { main: { software: ["structure"] } } }])) };
    assert.equal(command, "job_resources");
    return { available: true, free: capacities[params.execution_target.platform], observed_at: "fixture" };
  } };
  const draft = { items: ["a", "b"].map(id => ({ id, work_id: id, backend: "structure",
    candidates: [{ platform: "Com30" }, { platform: "FEDCluster" }], resources: { cpus: 2, memory_mb: 1024 } })) };
  const plan = await resolveExecutionPlan(resources, draft, automatic, null, []);
  assert.deepEqual(plan.items.map(row => row.selection.target.platform), ["Com30", "FEDCluster"]);
  capacities.FEDCluster = null;
  await assert.rejects(resolveExecutionPlan(resources, draft, automatic, null, []), /No permitted candidate/);
  await assert.rejects(resolveExecutionPlan(resources, draft, policy, null, []), /requires permission/);
  draft.items[0].candidates = [{ platform: "1WCluster" }];
  await assert.rejects(resolveExecutionPlan(resources, draft, automatic, null, []), /outside the pinned policy/);
});

test("placement list order never overrides the task default", async () => {
  const sources = [{ submission_id: "1", text: "Use FEDCluster. Use Com30." }];
  const placements = ["FEDCluster", "Com30"].map(platform => ({ target: { platform },
    intent: { source_submission_id: "1", source_text: "Use " + platform } }));
  const permitted = await resolveExecutionPolicy(kernel, { placements, max_in_flight: 2, max_attempts: 4 }, selection("Com30"), sources);
  const draft = { items: [{ id: "a", work_id: "a", resources: { cpus: 1, memory_mb: 512 } }] };
  const plan = await resolveExecutionPlan(kernel, draft, permitted, null, []);
  assert.equal(plan.items[0].selection.target.platform, "Com30");
});
