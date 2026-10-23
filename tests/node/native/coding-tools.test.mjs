import assert from "node:assert/strict";
import { mkdir, mkdtemp, readFile, writeFile, rm } from "node:fs/promises";
import { join } from "node:path";
import test from "node:test";
import { TODO_CONTEXT, withAbortSignal } from "@earendil-works/chord/context";
import { createCodingTools } from "../../../apps/agent/runtime/coding-tools.mjs";
import { loadPi } from "../../../apps/agent/runtime/source.mjs";
import { TEST_ROOT } from "./test-environment.mjs";
import { codingExecutionContext } from "../../../apps/agent/tasks/execution-plan.mjs";

async function fixture(t, getSelection) {
  const cwd = await mkdtemp(join(TEST_ROOT, "c-"));
  const { ExecutionEnvs } = await loadPi("setup");
  const environments = new ExecutionEnvs(cwd);
  t.after(async () => { await environments.cleanup(TODO_CONTEXT); await rm(cwd, { recursive: true, force: true }); });
  const tools = await createCodingTools(cwd, getSelection);
  const invoke = async (name, args, context = TODO_CONTEXT) => {
    const output = [];
    let details;
    const api = { callId: `test_${name}`, taskId: "task_1", conversationId: "root",
      env: environments.env({ cwd }), agent: async () => ({ cwd }),
      output: chunk => output.push(String(chunk)), diagnostic() {},
      details: async value => { details = value; } };
    const result = await tools.find(tool => tool.name === name).execute(args, api, context);
    return { ...result, details: result.details ?? details,
      text: result.content?.map(item => item.type === "text" ? item.text : "").join("\n") ?? output.join("") };
  };
  return { cwd, tools, invoke };
}

test("the seven native coding tools execute against the same Unicode workspace", async t => {
  const { cwd, tools, invoke } = await fixture(t);
  assert.deepEqual(tools.map(tool => tool.name), ["read", "write", "edit", "bash", "grep", "find", "ls"]);
  assert.equal(tools.some(tool => tool.name === "powershell"), false);
  await invoke("write", { path: "研究 文件.txt", content: "alpha\nbeta\n" });
  await invoke("edit", { path: "研究 文件.txt", edits: [{ oldText: "beta", newText: "gamma" }] });
  assert.equal((await invoke("read", { path: "研究 文件.txt" })).text.trim(), "alpha\ngamma");
  assert.equal(await readFile(join(cwd, "研究 文件.txt"), "utf8"), "alpha\ngamma\n");
  assert.match((await invoke("bash", { command: "printf 'shell result'" })).text, /shell result/);
  assert.match((await invoke("grep", { pattern: "gamma", path: "." })).text, /研究 文件.txt/);
  assert.match((await invoke("find", { pattern: "*.txt", path: "." })).text, /研究 文件.txt/);
  assert.match((await invoke("ls", { path: "." })).text, /研究 文件.txt/);
});

test("native search tools preserve ignore rules, literal matching and bounded results", async t => {
  const { cwd, invoke } = await fixture(t);
  await mkdir(join(cwd, ".git"));
  await writeFile(join(cwd, ".gitignore"), "ignored.txt\n");
  await writeFile(join(cwd, "ignored.txt"), "needle\n");
  await writeFile(join(cwd, "a.txt"), "needle.\n".repeat(20));
  await writeFile(join(cwd, "b.txt"), "NEEDLE.\n");
  const grep = await invoke("grep", { pattern: "needle.", literal: true, ignoreCase: true, limit: 2 });
  assert.doesNotMatch(grep.text, /ignored.txt/);
  assert.ok(grep.details?.matchLimitReached || /limit|truncat/i.test(grep.text));
  const found = await invoke("find", { pattern: "*.txt" });
  assert.match(found.text, /a.txt/); assert.match(found.text, /b.txt/); assert.doesNotMatch(found.text, /ignored.txt/);
  const listed = await invoke("ls", { limit: 1 });
  assert.ok(listed.details?.entryLimitReached || /limit|truncat/i.test(listed.text));
  const missing = invoke("ls", { path: "absent" });
  await assert.rejects(missing, /not found|not exist|ENOENT/i);
});

test("search cancellation reaches the original Pi implementations", async t => {
  const { invoke } = await fixture(t);
  const controller = new AbortController(); controller.abort();
  const context = withAbortSignal(controller.signal, TODO_CONTEXT);
  for (const name of ["grep", "find", "ls"]) {
    await assert.rejects(invoke(name, name === "ls" ? {} : { pattern: "anything" }, context), /abort/i);
  }
});

test("bash inherits the current pinned target without shell interpolation or stale context", async t => {
  let selection = { selection: { target: "tri'$(touch should-not-exist)", route_digest: "sha256:" + "a".repeat(64),
    } };
  const { cwd, invoke } = await fixture(t, async () => selection);
  const response = await invoke("bash", { command: 'printf "%s" "$CORAGENT_TASK_EXECUTION"' });
  assert.ok(response.text.includes(JSON.stringify({ ...selection, workspace_root: cwd })));
  assert.doesNotMatch(response.text, /sources/);
  await assert.rejects(readFile(join(cwd, "should-not-exist")), { code: "ENOENT" });
  selection = null;
  const empty = await invoke("bash", { command: 'printf "context=%s" "${CORAGENT_TASK_EXECUTION-unset}"' });
  assert.match(empty.text, /context=unset/);
});

test("ordinary bash runs locally for a task with no calculation destination", async t => {
  const task = { state: "active", execution_target: null, execution_selection: null,
    execution_policy: null, execution_plan: null, active_execution_item: null };
  const { cwd, invoke } = await fixture(t, async () => codingExecutionContext(task));
  const response = await invoke("bash", { command: 'pwd\nprintf "%s" "$CORAGENT_TASK_EXECUTION"' });
  assert.ok(response.text.includes(cwd));
  assert.ok(response.text.includes(JSON.stringify({ unselected: true, workspace_root: cwd })));
});
