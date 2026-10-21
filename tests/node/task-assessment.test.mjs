import assert from "node:assert/strict";
import test from "node:test";
import { verifyAssessment, checkCompletion } from "../../apps/agent/tasks/assessment.mjs";
import { resolveTaskSelection } from "../../apps/agent/tasks/execution-selection.mjs";

const task = { workspace_id: "workspace", user_task_id: "task_1", requirements_revision: 2,
  criteria: [{ id: "connection", description: "Verify the connection" }] };
const item = { criterion_id: "connection", status: "met", assessment_ref: "art_2", evidence_refs: ["art_1"] };
const document = () => ({ schema_version: "task-assessment/1", ...task, criterion_id: "connection", status: "met",
  reason: "Current evidence supports the connection", conflicts: [],
  checks: [{ method: "programmatic", status: "met", reason: "Connection validator passed", evidence_refs: ["art_1"] }] });
const bridge = value => ({ execute_command: async () => ({ content: JSON.stringify(value), next_offset: null }) });

test("a failure report cannot satisfy full completion merely by existing", async () => {
  const failed = document(); failed.status = failed.checks[0].status = "unmet";
  await assert.rejects(verifyAssessment(bridge(failed), task, item, async () => []), /statuses must agree/);
  await assert.rejects(verifyAssessment(bridge({ ...failed, status: "met" }), task, item, async () => []), /conflicts with its checks/);
  assert.throws(() => checkCompletion(task, { completion: [{ ...item, status: "unmet" }], completion_outcome: "full" }), /Full completion/);
});

test("assessment scope, revisions, conflicts and referenced evidence are checked", async () => {
  for (const change of [{ requirements_revision: 1 }, { user_task_id: "task_2" }, { workspace_id: "elsewhere" }, { conflicts: ["contradictory result"] }, { checks: [] }]) {
    await assert.rejects(verifyAssessment(bridge({ ...document(), ...change }), task, item, async () => []));
  }
  const unsupported = document(); unsupported.checks[0].evidence_refs = ["art_9"];
  await assert.rejects(verifyAssessment(bridge(unsupported), task, item, async () => []), /Check evidence/);
  let options;
  const verified = await verifyAssessment(bridge(document()), task, item, async (_refs, _ctx, opts) => { options = opts; return ["fixed"]; });
  assert.equal(options.current, true);
  assert.deepEqual(verified.evidence_identities, ["fixed"]);
});

test("partial closure requires a stopping basis and preserves unmet criteria", () => {
  const params = { completion: [{ ...item, status: "undetermined" }], completion_outcome: "partial" };
  assert.throws(() => checkCompletion(task, params), /stopping basis/);
  checkCompletion(task, { ...params, stop_basis: { kind: "search_exhausted", reason: "Bounded search exhausted" } });
  assert.throws(() => checkCompletion(task, { ...params, completion: [item, item] }), /exactly once/);
});

test("target intent must quote a real source and resolution is delegated once", async () => {
  const calls = [];
  const kernel = { execute_command: async (command, args) => { calls.push([command, args]);
    return { target: "queue_a", route_digest: "sha256:" + "a".repeat(64), selection_mode: "explicit" }; } };
  const sources = [{ submission_id: "24", text: "Use local (TRI queue) for this task" }];
  await assert.rejects(resolveTaskSelection(kernel, { execution_intent: { source_submission_id: "24", source_text: "use Slurm" } }, sources), /quote/);
  const selection = await resolveTaskSelection(kernel, { execution_intent: { source_submission_id: "24", source_text: "local (TRI queue)", scheduler: "tri" } }, sources);
  assert.equal(calls.length, 1); assert.equal(calls[0][0], "job_resolve_target");
  assert.equal(selection.version, 1); assert.equal(selection.sources[0].text, "local (TRI queue)");
});
