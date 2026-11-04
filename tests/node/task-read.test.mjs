import assert from "node:assert/strict";
import test from "node:test";
import { readTask } from "../../apps/agent/tasks/read.mjs";

const fixture = () => ({ user_task_id: "task_1", revision: 750, state: "active",
  objective: "Verify both IRC endpoints and retain contradictory evidence.",
  sources: [{ submission_id: "11", text: "Use 12 CPUs; do not send results externally." }],
  criteria: [{ id: "irc", description: "Verify connectivity, not only program termination." }],
  execution_policy: { max_in_flight: 1 }, next_action: "Inspect endpoint structures.",
  audit: Array.from({ length: 750 }, (_, revision) => ({ revision, reason: "historical progress ".repeat(25) })),
  progress_identities: Array.from({ length: 1000 }, (_, i) => `artifact:${i}`), event_inputs: [],
  completion_history: [{ outcome: "partial", completion: [] }] });

test("long task histories do not crowd out requirements, limits or the next action", () => {
  const task = fixture(), original = structuredClone(task), view = readTask(task);
  assert.ok(Buffer.byteLength(JSON.stringify(view, null, 2)) < 24000);
  for (const key of ["objective", "sources", "criteria", "execution_policy", "next_action", "revision", "state"])
    assert.deepEqual(view[key], task[key]);
  assert.equal(view.audit, undefined);
  assert.equal(view.completion_history, undefined);
  assert.ok(view.read_more.audit.expected_digest);
  assert.deepEqual(task, original, "model projection must not change the durable task");
});

test("oversized user requirements and history can be reconstructed without truncation", () => {
  const task = fixture();
  task.sources[0].text = '\u0001中文😀\\"'.repeat(4000) + "Do not omit the final constraint.";
  const view = readTask(task);
  assert.equal(view.sources, undefined);
  assert.ok(view.read_more.sources);
  assert.ok(Buffer.byteLength(JSON.stringify(view, null, 2)) < 24000);
  for (const field of ["sources", "audit"]) {
    let offset = 0, content = "";
    do {
      const page = readTask(task, { ...view.read_more[field], offset, limit: 12000 });
      assert.ok(Buffer.byteLength(JSON.stringify(page, null, 2)) < 24000);
      content += page.content;
      assert.ok(page.next_offset === null || page.next_offset > offset);
      offset = page.next_offset;
    } while (offset !== null);
    assert.deepEqual(JSON.parse(content), task[field]);
  }
});

test("field pagination rejects mixed versions but survives unrelated task changes", () => {
  const task = fixture(), page = readTask(task, { field: "sources", limit: 12 });
  const query = { field: "sources", offset: page.next_offset, expected_digest: page.digest };
  task.revision++;
  task.audit.push({ reason: "unrelated update" });
  assert.doesNotThrow(() => readTask(task, query));
  task.sources[0].text += "Changed constraint";
  assert.throws(() => readTask(task, query), { code: "task_field_changed" });
  assert.throws(() => readTask(task, { field: "sources", offset: 12 }), { code: "task_digest_required" });
  assert.throws(() => readTask(task, { field: "constructor" }), { code: "task_field_unknown" });
  assert.equal(readTask(null), null);
});
