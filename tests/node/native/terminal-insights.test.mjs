import assert from "node:assert/strict";
import test from "node:test";
import { join } from "node:path";
import { pathToFileURL } from "node:url";
import { pinnedPiSource } from "./test-environment.mjs";
import { createImageView } from "../../../apps/agent/terminal/images.mjs";
import { createChatView } from "../../../apps/agent/terminal/chat.mjs";
import { createSessionInsights, runtimeSummary } from "../../../apps/agent/terminal/status/insights.mjs";
import { Harness, MemoryStorage, createRegistry, defineTask, defineExtension } from "@earendil-works/pi-durable";
import { createModels } from "@earendil-works/pi-ai";
import { TODO_CONTEXT as context } from "@earendil-works/chord/context";
import { inspectRuntime, retryRuntimeTask } from "../../../apps/agent/runtime/inspection.mjs";

const components = await import(pathToFileURL(join(pinnedPiSource(), "packages/tui/src/index.ts")));
const themes = await import(pathToFileURL(join(pinnedPiSource(), "packages/coding-agent/src/modes/interactive/theme/theme.ts")));
themes.initTheme("dark");
const theme = { fg: (_, text) => text, bold: text => text };
const PNG = { type: "image", mimeType: "image/png", data: "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=" };
const runtime = () => ({ updated_at: new Date().toISOString(), scheduling: "running", counts: {}, tasks: [], queued_inputs: 0 });

test("real Harness inspection and explicit retry preserve sleeping and completed work", { timeout: 10000 }, async t => {
  let executions = 0;
  const until = Date.now() + 60000;
  let asleep;
  const sleeping = new Promise(resolve => { asleep = resolve; });
  const work = defineTask({ name: "test.recovery", version: 1, initial: () => ({ phase: "run" }),
    phases: { run: async (_task, runtime, ctx) => {
      executions++;
      await runtime.commit(() => ({ status: "terminal", outcome: { status: "completed", result: "done" } }), ctx);
    } }, abort: async () => {} });
  const sleeper = defineTask({ name: "test.sleep", version: 1, initial: () => ({ phase: "run" }),
    phases: {
      run: async (_task, runtime, ctx) => { await runtime.sleepUntil(until, { phase: "done" }, ctx); asleep(); },
      done: async (_task, runtime, ctx) => runtime.commit(() => ({ status: "terminal", outcome: { status: "completed", result: null } }), ctx),
    }, abort: async () => {} });
  const registry = createRegistry();
  registry.install(defineExtension({ name: "recovery-test", tasks: [work, sleeper] }));
  const harness = await Harness.open(new MemoryStorage(), { models: createModels(), registry, settings: { restartLimit: 2 } }, context);
  t.after(() => harness.close(context));
  const conversation = await harness.root(context);
  const ids = await conversation.commit(async tx => {
    const parked = await tx.createTask(work, null, { ownership: { kind: "conversation" } });
    const sleeping = await tx.createTask(sleeper, null, { ownership: { kind: "conversation" } });
    return { parked, sleeping };
  }, context);
  // Seed the persisted state of an interrupted task before the scheduler starts.
  await harness.commitWith(async tx => {
    tx.setTask({ ...await tx.task(ids.parked), restarts: 2 });
  }, context);
  harness.resume();
  await sleeping;
  await new Promise(resolve => setImmediate(resolve));
  const before = await inspectRuntime(harness, context);
  assert.equal(before.tasks.find(task => task.id === String(ids.parked)).retryable, true);
  assert.equal(before.tasks.find(task => task.id === String(ids.sleeping)).until, until);
  assert.equal(executions, 0);
  await retryRuntimeTask(harness, String(ids.parked), context);
  const finished = await harness.waitForTask(ids.parked, context);
  assert.equal(finished.state.outcome.result, "done");
  assert.equal(executions, 1);
  await assert.rejects(retryRuntimeTask(harness, String(ids.parked), context), { code: "task_not_retryable" });
  assert.equal((await inspectRuntime(harness, context)).tasks.find(task => task.id === String(ids.sleeping)).state, "sleeping");
  assert.equal(executions, 1);
});

test("image previews render terminal graphics, text fallbacks and malformed data without breaking the transcript", () => {
  const saved = components.getCapabilities();
  try {
    for (const protocol of ["kitty", "iterm2", null]) {
      components.setCapabilities({ images: protocol, trueColor: false, hyperlinks: false });
      const image = createImageView({ components, theme, block: PNG, filename: "实验.png", panel: true });
      image.setViewport(8);
      const rendered = image.render(40).join("\n");
      assert.match(rendered, /实验.png/);
      assert.match(rendered, /Esc Back/);
      if (protocol === "kitty") assert.ok(rendered.includes("\x1b_G"));
      if (protocol === "iterm2") assert.ok(rendered.includes("\x1b]1337;File="));
      if (protocol === null) assert.match(rendered, /[Ii]mage/);
    }
    const invalid = createImageView({ components, theme, block: { ...PNG, data: "invalid" } });
    assert.match(invalid.render(80).join("\n"), /Preview unavailable/);
    components.setCapabilities({ images: "kitty", trueColor: false, hyperlinks: false });
    const injected = createImageView({ components, theme, block: { ...PNG, data: PNG.data + "\x1b]52;c;injected\x07" } });
    const safe = injected.render(80).join("\n");
    assert.ok(safe.includes("\x1b_G"));
    assert.ok(!safe.includes("\x1b]52;"));
    components.setCapabilities({ images: null, trueColor: false, hyperlinks: false });
    const chat = createChatView({ components, theme: themes.theme, markdownTheme: themes.getMarkdownTheme(), requestRender() {} });
    chat.update({ docs: {}, entries: [
      { id: 1, kind: "pi.user", model: [{ role: "user", content: [PNG] }] },
      { id: 2, kind: "pi.assistant", model: [{ role: "assistant", content: [{ type: "toolCall", id: "read1", name: "read", arguments: { path: "plot.png" } }] }] },
      { id: 3, kind: "pi.tool", model: [{ role: "toolResult", toolCallId: "read1", content: [PNG] }] },
    ] });
    assert.match(chat.render(90).join("\n"), /Attached image/);
    assert.match(chat.render(90).join("\n"), /plot.png.*1×1/);
    chat.toggleTools();
    assert.match(chat.render(90).join("\n"), /plot.png.*1×1/);
  } finally { components.setCapabilities(saved); }
});

test("sidebar reflects fresh task scope, hides stale data and fits narrow CJK text", () => {
  const insights = createSessionInsights({ ...components, theme });
  const task = { user_task_id: "task1", title: "比较两个反应路径", state: "paused", next_action: "检查振动频率" };
  const monitor = { updated_at: new Date().toISOString(), task, jobs: { counts: { running: 2, queued: 1 }, active: [{ job_id: "job1", state: "running" }] } };
  insights.update({ runtime: runtime(), monitor, research: { task, result: { scope: { focus_node_ids: ["node1"] },
    findings: [{ kind: "node", ref: "node1", title: "势垒高度" }] } } });
  const text = () => insights.sidebar.render(36).join("\n");
  assert.match(text(), /势垒高度/);
  assert.match(text(), /task resume/);
  for (const width of [12, 24, 36]) for (const line of insights.sidebar.render(width)) assert.ok(components.visibleWidth(line) <= width);
  insights.update({ monitor: { ...monitor, task: { ...task, user_task_id: "task2" } } });
  assert.doesNotMatch(text(), /势垒高度/);
  insights.update({ monitorError: "offline" });
  assert.match(text(), /Jobs unavailable/);
  assert.doesNotMatch(text(), /job1|2 running/);
});

test("execution status distinguishes sleeping, restart limit and compaction failures", () => {
  const state = runtime();
  state.counts.sleeping = 1;
  state.tasks = [{ id: "2", kind: "pi.generation", state: "sleeping", until: Date.now() + 5000 }];
  assert.match(runtimeSummary(state), /Waiting.*next check/);
  state.counts.blocked = 1;
  assert.match(runtimeSummary(state), /Needs attention/);
  assert.match(runtimeSummary(state, { docs: { "pi.live": { compactionFailure: { error: "too long" } } } }), /Compaction failed/);
  assert.match(runtimeSummary({ ...state, updated_at: "2000-01-01T00:00:00Z" }), /unavailable/);
});
