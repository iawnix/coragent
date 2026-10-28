import assert from "node:assert/strict";
import test from "node:test";
import { inspectRuntime, retryRuntimeTask } from "../../../apps/agent/runtime/inspection.mjs";
import { readWorkspaceImage } from "../../../apps/agent/terminal/images.mjs";
import { createSessionToolCommands } from "../../../apps/agent/terminal/commands/session-tools.mjs";

const PNG = Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=", "base64");
const task = (id, state) => ({ record: { id, kind: "pi.generation", restarts: 5, input: "hidden", checkpoint: { secret: "hidden" } }, state });

test("runtime inspection projects waits and prioritizes parked tasks without exposing checkpoints", async () => {
  const tasks = Array.from({ length: 105 }, (_, index) => task(index + 1, { kind: "sleeping", until: 12345 }));
  tasks.push(task(200, { kind: "blocked", reason: "restart_limit", error: "hidden" }));
  const value = await inspectRuntime({ inspect: async () => ({ scheduling: "running", tasks, submissions: [{ status: "queued", content: "hidden" }] }) });
  assert.equal(value.tasks.length, 100);
  assert.equal(value.tasks[0].id, "200");
  assert.equal(value.tasks[0].retryable, true);
  assert.equal(value.tasks[1].until, 12345);
  assert.equal(value.omitted, 6);
  assert.equal(value.counts.sleeping, 105);
  assert.equal(value.queued_inputs, 1);
  assert.doesNotMatch(JSON.stringify(value), /hidden|checkpoint/);
});

test("recovery rejects malformed, completed, running and non-retryable blocked tasks", async () => {
  let state = { kind: "running" }, calls = [];
  const harness = { inspect: async () => ({ tasks: [task(7, state)] }), retryTask: async id => calls.push(id) };
  for (const id of ["-1", "1e2", "0", "x", "9007199254740993"]) await assert.rejects(retryRuntimeTask(harness, id), { code: "invalid_task" });
  for (const next of [{ kind: "running" }, { kind: "sleeping" }, { kind: "blocked", reason: "migration_failed" }]) {
    state = next;
    await assert.rejects(retryRuntimeTask(harness, "7"), { code: "task_not_retryable" });
  }
  await assert.rejects(retryRuntimeTask(harness, "8"), { code: "task_not_retryable" });
  assert.deepEqual(calls, []);
  state = { kind: "blocked", reason: "restart_limit" };
  assert.deepEqual(await retryRuntimeTask(harness, "7"), { accepted: true, task_id: "7" });
  assert.deepEqual(calls, [7]);
});

function files(change = page => page) {
  const file = { path: "plots/研究 plot.png", kind: "file", size: PNG.length, version: "v1" }, calls = [];
  return { calls, async request(method, params) {
    calls.push([method, params]);
    assert.equal(params.workspace_id, "remote");
    if (method === "files/stat") return { file, max_chunk_bytes: 17 };
    assert.equal(params.expected_version, "v1");
    const bytes = PNG.subarray(params.offset, params.offset + params.length);
    return change({ file, offset: params.offset, data_base64: bytes.toString("base64"), next_offset: params.offset + bytes.length,
      eof: params.offset + bytes.length === PNG.length });
  } };
}

test("image preview reads remote workspace pages with one version and preserves paths with spaces", async () => {
  const server = files();
  const image = await readWorkspaceImage({ request: server.request, workspaceId: "remote", path: "plots/研究 plot.png" });
  assert.equal(image.mimeType, "image/png");
  assert.deepEqual(Buffer.from(image.data, "base64"), PNG);
  assert.ok(server.calls.length > 2);
  assert.ok(server.calls.every(([method]) => method.startsWith("files/")));
});

test("image preview rejects changed, invalid, oversized and cancelled reads", async () => {
  for (const change of [page => ({ ...page, file: { ...page.file, version: "v2" } }),
    page => ({ ...page, next_offset: page.offset }), page => ({ ...page, eof: true })]) {
    await assert.rejects(readWorkspaceImage({ request: files(change).request, workspaceId: "remote", path: "plot.png" }));
  }
  for (const path of ["../plot.png", "/absolute.png", "x\n.png"]) await assert.rejects(readWorkspaceImage({ request: assert.fail, path }));
  await assert.rejects(readWorkspaceImage({ path: "large.png", request: async () => ({ file: { kind: "file", size: 9 * 1024 * 1024 } }) }), /8 MiB/);
  await assert.rejects(readWorkspaceImage({ path: "plot.png", request: assert.fail, signal: AbortSignal.abort() }), { name: "AbortError" });
});

test("retry selection uses session scope and ignores a selection cancelled during a session change", async () => {
  let selected = "7", active = true;
  const calls = [], session = { workspaceId: "w", sessionId: "s", signal: new AbortController().signal };
  const commands = createSessionToolCommands({ session, components: {}, ui: {
    updateInsights() {}, showStatus() {}, select: async () => selected,
  }, request: async (method, params) => {
    calls.push([method, params]);
    return { tasks: [{ id: "7", kind: "pi.generation", restarts: 5, retryable: true }] };
  }, active: () => active });
  const retry = commands.find(command => command.name === "retry");
  await retry.run("", {});
  assert.equal(calls.filter(([method]) => method === "session/retry").length, 1);
  assert.deepEqual(calls.find(([method]) => method === "session/retry")[1], {
    workspace_id: "w", session_id: "s", task_id: "7", request_id: calls[1][1].request_id,
  });
  calls.length = 0; selected = undefined;
  await retry.run("", {});
  assert.ok(calls.every(([method]) => method === "session/query"));
  active = false;
  await retry.run("7", {});
  assert.ok(calls.every(([method]) => method === "session/query"));
});
