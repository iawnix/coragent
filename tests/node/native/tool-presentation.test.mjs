import assert from "node:assert/strict";
import test from "node:test";
import { join } from "node:path";
import { pathToFileURL } from "node:url";
import { createCoRAgentToolRenderers } from "../../../apps/agent/terminal/renderers/tools.mjs";
import { enhanceMarkdown, enhanceAdmonitions, linkifyBareUrls, normalizeCircledNumbers } from "../../../apps/agent/terminal/renderers/markdown-enhance.mjs";
import { PI_BUILTIN_TOOL_NAMES } from "../../../apps/agent/pi/presentation.mjs";
import { pinnedPiSource } from "./test-environment.mjs";

const source = pinnedPiSource();
const fromSource = path => import(pathToFileURL(join(source, path)));
const tui = await fromSource("packages/tui/src/index.ts");
const colors = [];
const theme = { fg(color, text) { colors.push(color); return text; }, bold(text) { return text; } };

test("tool identity stays visible while output remains collapsible", () => {
  const renderer = createCoRAgentToolRenderers(tui, ["research_read"]).research_read;
  const raw = JSON.stringify({ nodes: Array.from({ length: 100 }, (_, i) => ({ id: i, summary: "x".repeat(100) })) }, null, 2);
  const state = {};
  const args = { path: "/home/iaw/pi-jcim/ci-557d872664c1-d94b834f/text/page-041.txt", payload: raw };
  const call = renderer.renderCall(args, theme, { expanded: false, isPartial: true, state });
  assert.ok(call.render(60).length <= 4);
  assert.match(call.render(120).join("\n"), /· research_read .*page-041\.txt/);
  assert.doesNotMatch(call.render(120).join("\n"), /▾/);
  const result = { content: [{ type: "text", text: raw }] };
  const collapsed = renderer.renderResult(result, { expanded: false }, theme,
    { args, state, durationMs: 420 });
  assert.equal(collapsed.render(120).join("\n"), "");
  assert.match(call.render(120).join("\n"), /✓ research_read .*420ms.*▾/);
  const expanded = renderer.renderResult(result, { expanded: true }, theme,
    { args, state, durationMs: 420 });
  assert.match(call.render(120).join("\n"), /✓ research_read .*420ms.*▴/);
  assert.ok(expanded.render(60).length > 100);
  assert.match(expanded.render(120).join("\n"), /nodes/);
});

test("execution marks do not leak business states into generic cards", t => {
  const previous = {TERM:process.env.TERM,NO_COLOR:process.env.NO_COLOR};
  process.env.TERM='xterm-256color'; delete process.env.NO_COLOR;
  t.after(()=>{for(const [key,value] of Object.entries(previous)) {
    if(value===undefined) delete process.env[key]; else process.env[key]=value;
  }});
  const renderer = createCoRAgentToolRenderers(tui, ["job_status"]).job_status;
  const state = {};
  const args = { job_id: "job_9" };
  const call = renderer.renderCall(args, theme, { args, state, isPartial: true });
  assert.match(call.render(120).join("\n"), /· job_status.*job_9/);
  colors.length = 0;
  renderer.renderResult({ content: [{ type: "text", text: '{"status":{"state":"succeeded"}}' }],
    details: { result: { status: { state: "succeeded" } } } }, {}, theme,
    { args, state, durationMs: 1200 });
  const completed = call.render(120).join("\n");
  assert.match(completed, /✓ job_status.*job_9.*1\.2s.*▾/);
  assert.doesNotMatch(completed, /succeeded|Object/);
  assert.ok(colors.includes("success"));
  renderer.renderResult({ content: [{ type: "text", text: "failed" }], isError: true }, {}, theme,
    { args, state, isError: true, durationMs: 1200 });
  assert.match(call.render(120).join("\n"), /× job_status.*job_9.*1\.2s.*▾/);
  for (const durationMs of [undefined, null, NaN, -1]) {
    renderer.renderResult({ content: [] }, {}, theme, { args, state, durationMs });
    assert.doesNotMatch(call.render(60).join("\n"), /\d+(?:\.\d+)?(?:ms|s)/);
  }
});

test("built-in bash uses the compact single-line card", () => {
  const renderer = createCoRAgentToolRenderers(tui, ["bash"]).bash;
  const state = {};
  const context = { args: { command: "python prepare.py --input candidate.json" }, state };
  const call = renderer.renderCall(context.args, theme, { ...context, isPartial: true });
  assert.match(call.render(120).join("\n"), /· bash  +python prepare\.py/);
  assert.doesNotMatch(call.render(120).join("\n"), /▾/);
  const result = renderer.renderResult(
    { content: [{ type: "text", text: "stdout line\nstderr line" }] },
    {}, theme, { args: context.args, state, durationMs: 850 },
  );
  assert.equal(result.render(120).join("\n"), "");
  assert.match(call.render(120).join("\n"), /✓ bash  +python prepare\.py.*850ms.*▾/);
  const failed = renderer.renderResult(
    { content: [{ type: "text", text: "ModuleNotFoundError" }], isError: true },
    {}, theme, { args: context.args, state, isError: true, durationMs: 850 },
  );
  assert.equal(failed.render(120).join("\n"), "");
  assert.match(call.render(120).join("\n"), /× bash  +python prepare\.py.*850ms.*▾/);
  const expanded = renderer.renderResult(
    { content: [{ type: "text", text: "stdout line\nstderr line" }] },
    { expanded: true }, theme, { args: context.args, state, durationMs: 850 },
  );
  assert.match(call.render(120).join("\n"), /▴/);
  assert.match(expanded.render(120).join("\n"), /stdout line\s*\nstderr line/);
});

test("all Pi built-in coding tools use the compact card states", () => {
  const names = ["read", "write", "edit", "grep", "find", "ls", "powershell"];
  assert.deepEqual(names, PI_BUILTIN_TOOL_NAMES.slice(1));
  const renderers = createCoRAgentToolRenderers(tui, PI_BUILTIN_TOOL_NAMES);
  for (const name of names) {
    const state = {};
    const args = name === "grep" ? { pattern: "needle", path: "." }
      : name === "find" ? { pattern: "*.xyz", path: "." }
        : { path: "sample.txt" };
    const call = renderers[name].renderCall(args, theme, { args, state, isPartial: true });
    assert.match(call.render(120).join("\n"), new RegExp(`· ${name}`));
    assert.doesNotMatch(call.render(120).join("\n"), /▾/);

    const done = renderers[name].renderResult(
      { content: [{ type: "text", text: `${name} output` }] },
      {}, theme, { args, state, durationMs: 650 },
    );
    assert.match(done.render(120).join("\n"), /^$/);

    const failed = renderers[name].renderResult(
      { content: [{ type: "text", text: "failure" }], isError: true },
      {}, theme, { args, state, isError: true },
    );
    assert.match(call.render(120).join("\n"), new RegExp(`× ${name}`));
    assert.equal(failed.render(120).join("\n"), "");

    const expanded = renderers[name].renderResult(
      { content: [{ type: "text", text: `${name} full output` }] },
      { expanded: true }, theme, { args, state, durationMs: 650 },
    );
    assert.match(call.render(120).join("\n"), /▴/);
    assert.match(expanded.render(120).join("\n"), new RegExp(`${name} full output`));
  }
});

test("markdown presentation enhances prose while preserving code and protected states", () => {
  const source = [
    "See https://example.com/docs.",
    "Inline `https://example.com/raw` stays literal.",
    "> [!WARNING] Check https://example.com/warn",
    "> Keep the warning readable.",
    "① first ⑳ last",
    "```text",
    "https://example.com/code",
    "① code",
    "```",
  ].join("\n");
  const enhanced = enhanceMarkdown(source, { messageType: "assistant", isStreaming: false, availableWidth: 80 });
  assert.match(enhanced, /See \[https:\/\/example\.com\/docs\]\(https:\/\/example\.com\/docs\)\./);
  assert.match(enhanced, /Inline `https:\/\/example\.com\/raw` stays literal\./);
  assert.match(enhanced, /> \*\*\[WARNING\]\*\* Check \[https:\/\/example\.com\/warn\]\(https:\/\/example\.com\/warn\) Keep the warning readable\./);
  assert.match(enhanced, /\(1\) first \(20\) last/);
  assert.match(enhanced, /```text\nhttps:\/\/example\.com\/code\n① code\n```/);
  assert.equal(linkifyBareUrls("`https://example.com` https://example.com"), "`https://example.com` [https://example.com](https://example.com)");
  assert.equal(enhanceAdmonitions("> [!NOTE] hi"), "> **[NOTE]** hi");
  assert.equal(normalizeCircledNumbers("①②③ `④`\n```\n⑤\n```"), "(1)(2)(3) `④`\n```\n⑤\n```");
  assert.equal(enhanceMarkdown("https://example.com", { messageType: "assistant-thinking", isStreaming: false }), "https://example.com");
  assert.equal(enhanceMarkdown("https://example.com", { messageType: "assistant", isStreaming: true }), "https://example.com");
});

test('monochrome tool summaries retain state without calling color functions',t=>{
  const previous=process.env.NO_COLOR;process.env.NO_COLOR='1';
  t.after(()=>{if(previous===undefined) delete process.env.NO_COLOR;else process.env.NO_COLOR=previous;});
  const renderer=createCoRAgentToolRenderers(tui,['job_start']).job_start;
  const noColor={fg(){throw Error('unexpected color');},bold(){throw Error('unexpected emphasis');}};
  const state = {};
  const call = renderer.renderCall({},noColor,{state});
  assert.match(call.render(60).join('\n'),/job_start/);
  renderer.renderResult({content:[],details:{result:{state:'queued'}}},{},noColor,{state});
  assert.match(call.render(60).join('\n'),/job_start/);
});

test("native chat applies registered renderers and expands cards without losing their transcript", async () => {
  const { ExperimentalChatView, configureToolRenderers, configureMarkdownTransformers } = await fromSource("packages/coding-agent/src/experimental/client-tui-chat.ts");
  const { initTheme } = await fromSource("packages/coding-agent/src/modes/interactive/theme/theme.ts");
  initTheme("dark");
  configureToolRenderers(createCoRAgentToolRenderers(tui, ["research_read"]));
  configureMarkdownTransformers([enhanceMarkdown]);
  const view = new ExperimentalChatView({ requestRender() {} }, process.cwd());
  const raw = "evidence\n".repeat(100);
  try {
    const persisted = { docs: {}, entries: [
      { id: 0, kind: "pi.user", model: [{ role: "user", content: "See https://example.com and `https://example.com/raw`." }] },
      { id: 0.5, kind: "pi.assistant", model: [{ role: "assistant", stopReason: "stop", content: [{ type: "text", text: "> [!NOTE] Rendered note\n\n① item" }] }] },
      { id: 1, kind: "pi.assistant", model: [{ role: "assistant", stopReason: "toolUse", content: [{ type: "toolCall", id: "one", name: "research_read", arguments: { mode: "context" } }] }] },
      { id: 2, kind: "pi.tool-result", model: [{ role: "toolResult", toolCallId: "one", toolName: "research_read", isError: false, durationMs: 1250, content: [{ type: "text", text: raw }] }] },
    ] };
    view.apply(persisted);
    const initial = view.transcript.render(60).join("\n");
    assert.match(initial, /example\.com/);
    assert.match(initial, /Rendered note/);
    assert.match(initial, /\(1\) item/);
    assert.match(initial, /research_read/);
    const collapsed = view.transcript.render(60).length;
    view.toggleTools();
    assert.ok(view.transcript.render(60).length > collapsed + 50);
    assert.match(view.transcript.render(60).join("\n"), /evidence/);
    view.toggleTools();
    assert.equal(view.transcript.render(60).length, collapsed);
    // A newly attached presentation gets the recorded duration without a live timer.
    const reattached = new ExperimentalChatView({ requestRender() {} }, process.cwd());
    try {
      reattached.apply(persisted);
      assert.match(reattached.transcript.render(60).join("\n"), /1\.3s/);
    } finally { reattached.dispose(); }
  } finally { view.dispose(); configureToolRenderers({}); configureMarkdownTransformers([]); }
});

test("skill invocations keep attached failures inside one collapsible card", async () => {
  const { SkillInvocationMessageComponent } = await fromSource("packages/coding-agent/src/modes/interactive/components/skill-invocation-message.ts");
  const { parseSkillBlock } = await fromSource("packages/coding-agent/src/core/agent-session.ts");
  const { initTheme } = await fromSource("packages/coding-agent/src/modes/interactive/theme/theme.ts");
  initTheme("dark");
  const block = parseSkillBlock([
    '<skill name="chemical-input" location="/package/domains/chemical/skills/chemical-input/SKILL.md">',
    "# Chemical input",
    "</skill>",
    "",
    "<harness>\n[error] Tool call blocked\n</harness>",
  ].join("\n"));
  assert.ok(block);
  const component = new SkillInvocationMessageComponent(block);
  const collapsed = component.render(120).join("\n");
  assert.match(collapsed, /\[skill\].*chemical-input.*▾/);
  assert.doesNotMatch(collapsed, /Tool call blocked/);
  component.setExpanded(true);
  const expanded = component.render(120).join("\n");
  assert.match(expanded, /chemical-input.*▴/);
  assert.match(expanded, /Tool call blocked/);
  component.setExpanded(false);
  assert.doesNotMatch(component.render(120).join("\n"), /Tool call blocked/);
});

test("monitor wake messages use the compact collapsible monitor card", async () => {
  const { ExperimentalChatView, configureToolRenderers } = await fromSource("packages/coding-agent/src/experimental/client-tui-chat.ts");
  const { initTheme } = await fromSource("packages/coding-agent/src/modes/interactive/theme/theme.ts");
  initTheme("dark");
  configureToolRenderers(createCoRAgentToolRenderers(tui, ["monitor"]));
  const view = new ExperimentalChatView({ requestRender() {} }, process.cwd());
  const text = [
    "A compute monitor event requires attention.",
    "event_id=event_15", "monitor_id=monitor_15", "job_id=job_15", "node_id=node_2",
    "state=failed", "reason=state_changed", "program_status=unknown",
    "Read research_read and inspect the Job result before deciding what to do.",
    "Use job_status, job_collect, or job_reconcile to reconcile status.",
  ].join("\n");
  try {
    view.apply({ docs: {}, entries: [{ id: 4, kind: "pi.user", model: [{ role: "user", content: text }] }] });
    const collapsed = view.transcript.render(100).join("\n");
    assert.match(collapsed, /× monitor\s+job_15\s+▾/);
    assert.doesNotMatch(collapsed, /event_id=event_15/);
    view.toggleTools();
    const expanded = view.transcript.render(100).join("\n");
    assert.match(expanded, /event_id=event_15/);
    assert.match(expanded, /reason=state_changed/);
  } finally {
    view.dispose();
    configureToolRenderers({});
  }
});
