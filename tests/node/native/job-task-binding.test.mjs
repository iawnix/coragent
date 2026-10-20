import assert from "node:assert/strict";
import test from "node:test";
import { createJobTools } from "../../../apps/agent/tools/jobs/tools.mjs";
import { createToolExecutionContext } from "../../../apps/agent/tools/context.mjs";

const context = { abortSignal: new AbortController().signal };
const api = { callId: "call_submit", coragent: createToolExecutionContext({
  workspace_root: "/home/iaw/project/TSPi/local_debug/job-binding", session_id: "session_owner",
  operation_id: "pi_tool_1", allowed_authorities: ["execution_runtime"], allowed_effects: ["execution_control"],
}) };

test("Job submission binds the runtime user task for raw and prepared requests", async () => {
  const calls = [];
  const [start] = createJobTools({
    commandBridge: { execute_command: async (command, params) => { calls.push({ command, params }); return { job_id: "job_owned" }; } },
    getTaskBinding: async () => ({ user_task_id: "task_1" }),
  });
  assert.equal("user_task_id" in start.parameters.properties, false, "model cannot select task ownership");
  await start.execute({ command: ["true"] }, api, context);
  await start.execute({ prepared_ref: "p1" }, api, context);
  assert.equal(calls[0].params.user_task_id, "task_1");
  assert.equal(calls[0].params.session_id, "session_owner");
  assert.equal(calls[0].params.request_id, "pi_tool_1:call_submit");
  assert.equal(calls[1].params.user_task_id, "task_1");
  assert.equal(calls[1].params.prepared_ref, "p1");
  assert.equal("request_id" in calls[1].params, false, "prepared identity remains owned by the prepared request");
});

test("paused task binding rejects a new Job before invoking the runtime", async () => {
  let submitted = false;
  const [start] = createJobTools({ commandBridge: { execute_command: () => { submitted = true; } },
    getTaskBinding: async () => { throw new Error("task_not_active"); },
  });
  await assert.rejects(start.execute({ command: ["true"] }, api, context), /task_not_active/);
  assert.equal(submitted, false);
});

test("task destination reaches runtime for raw, file and registered requests", async () => {
  const calls = [];
  const [start] = createJobTools({
    commandBridge: { execute_command: async (_command, params) => { calls.push(params); return { job_id: "job_1" }; } },
    getTaskBinding: async () => ({ user_task_id: "task_1", compute_environment: "cluster_a" }),
  });
  assert.equal("required_environment" in start.parameters.properties, false);
  for (const params of [{ command: ["true"] }, { request_file: "request.json", request_sha256: "abc" }, { prepared_ref: "prepared_1" }]) {
    await start.execute(params, api, context);
  }
  assert.equal(calls.length, 3);
  assert.ok(calls.every(p => p.required_environment === "cluster_a"));
  assert.equal(calls[1].request_file, "request.json");
  assert.equal("platform" in calls[1], false, "task constraint checks but never rewrites a prepared request");
});

test("unchanged Job observations recommend waiting while terminal results stay fresh", async () => {
  let state = "running", reads = 0;
  const [, status] = createJobTools({ commandBridge: { execute_command: async () => {
    reads += 1; return { job_id: "job_1", state };
  } } });
  for (const seconds of [10, 20, 40, 60, 60]) {
    const result = await status.execute({ job_id: "job_1" }, api, context);
    assert.equal(result.details.polling.recommended_interval_seconds, seconds);
  }
  state = "succeeded";
  const result = await status.execute({ job_id: "job_1" }, api, context);
  assert.equal(reads, 6);
  assert.equal(result.details.result.state, "succeeded");
  assert.equal(result.details.polling, undefined);
});
