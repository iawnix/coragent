import assert from "node:assert/strict";
import test from "node:test";
import { existsSync } from "node:fs";

test("retired compute bootstrap and implementation have no compatibility modules", () => {
  for (const name of ["capability-host-bootstrap.mjs", "pi-native-compute.mjs"]) {
    assert.equal(existsSync(new URL(`../../apps/app-server/${name}`, import.meta.url)), false);
  }
});

test("canonical command adapters reject obsolete fields instead of dropping them", async () => {
  const { commandArguments, createCommandService } = await import("../../apps/agent/tools/commands.mjs");
  let called = false;
  const service = createCommandService({ execute() { called = true; } });
  for (const params of [{ jobId: "job_1" }, { intent_id: "calc_1" }, { job_id: "job_1", unknown: null }]) {
    assert.throws(() => service.execute("job.collect", "/unused", params), /schema_field_invalid/);
    assert.throws(() => commandArguments("job.collect", params), /schema_field_invalid/);
  }
  for (const params of [{ node_ref: "node_1" }, { storage_operation: "status" }]) {
    assert.throws(() => service.execute("research.read", "/unused", params), /schema_field_invalid/);
  }
  assert.equal(called, false);
  assert.deepEqual(commandArguments("job.collect", { job_id: "job_1" }), ["--job-id", "job_1"]);
});

test("public research_search type reaches the canonical search command as kind", async () => {
  const { createResearchTools } = await import("../../apps/agent/tools/research/tools.mjs");
  const calls = [];
  const tool = createResearchTools({ commandBridge: { execute_command: async (command, params) => {
    calls.push({ command, params }); return { matches: [] };
  } } }).find(tool => tool.name === "research_search");
  for (const type of ["node", "result", "record"]) {
    await tool.execute({ query: "fixture", type }, { coragent: { workspace_root: "/unused" } }, {});
    assert.deepEqual(calls.at(-1), { command: "research.search", params: { query: "fixture", kind: type } });
  }
});
