import { createCoRAgentToolRenderers } from "./renderers/tools.mjs";
import { enhanceMarkdown } from "./renderers/markdown-enhance.mjs";

export const messageText = content => typeof content === "string" ? content
  : (content || []).filter(part => part.type === "text").map(part => part.text).join("\n");

export function isRuntimeTaskContinuation(text) {
  const value = text.trim();
  return (value.startsWith('<runtime_task_continuation origin="runtime">') && value.endsWith("</runtime_task_continuation>"))
    || value.startsWith("Continue the existing authorized user task using the runtime task snapshot.")
    || value.startsWith("Recover only the final response for the existing completion proposal.");
}

/** Presentation of public Durable views using public pi-tui components. */
export function createChatView({ components, theme, markdownTheme, requestRender }) {
  const { Text, Markdown, Container } = components;
  let view = { entries: [], docs: {} }, expanded = false, rows = [], cache = new Map();
  const toggled = new Map();
  const markdown = (text, isStreaming = false) => new Markdown(enhanceMarkdown(text, { isStreaming }), 1, 0, markdownTheme);
  const line = text => new Text(text, 1, 0);
  function card(name, id, args, result, partial) {
    const renderer = createCoRAgentToolRenderers(components, [name])[name];
    const state = {};
    const context = { args, state, isPartial: partial, isError: result?.isError, durationMs: result?.durationMs };
    const container = new Container();
    container.addChild(renderer.renderCall(args, theme, context));
    if (result) container.addChild(renderer.renderResult(result, { expanded: toggled.get(id) ?? expanded }, theme, context));
    return { component: container, id };
  }
  function content() {
    const results = new Map();
    for (const entry of view.entries) for (const message of entry.model || []) {
      if (message.role === "toolResult") results.set(message.toolCallId, message);
    }
    const live = view.docs["pi.live"] || {};
    const output = [], nextCache = new Map();
    const add = (key, signature, create) => {
      const previous = cache.get(key);
      const value = previous?.signature === signature ? previous : { signature, ...create() };
      nextCache.set(key, value); output.push(value);
    };
    const assistant = (message, key, isStreaming = false) => {
      for (const [index, block] of (message.content || []).entries()) {
        if (block.type === "toolCall") {
          const slot = live.tools?.find(item => item.callId === block.id);
          const result = results.get(block.id) || (slot?.output ? { content: [{ type: "text", text: slot.output }], details: slot.details } : undefined);
          add(`tool:${block.id}`, JSON.stringify([block, result, toggled.get(block.id) ?? expanded, slot?.status]),
            () => card(block.name, block.id, block.arguments, result, !results.has(block.id)));
        } else if (block.type === "text" && block.text) add(`${key}:${index}`, JSON.stringify([block.text, isStreaming]), () => ({ component: markdown(block.text, isStreaming) }));
        else if (block.type === "thinking" && block.thinking) add(`${key}:${index}`, block.thinking,
          () => ({ component: line(theme.fg("muted", `Thinking: ${block.thinking}`)) }));
      }
      if (message.stopReason === "error" || message.errorMessage) add(`${key}:error`, message.errorMessage,
        () => ({ component: line(theme.fg("error", message.errorMessage || "Model request failed")) }));
    };
    for (const entry of view.entries) {
      if (entry.kind === "pi.compaction") {
        add(`compaction:${entry.id}`, "compacted", () => ({ component: line(theme.fg("muted", "Context compacted")) }));
        continue;
      }
      if (!["pi.user", "pi.assistant"].includes(entry.kind)) continue;
      for (const message of entry.model || []) {
        if (message.role === "assistant") assistant(message, String(entry.id));
        if (message.role !== "user") continue;
        const text = messageText(message.content);
        const id = `user:${entry.id}`;
        const open = toggled.get(id) ?? expanded;
        add(id, JSON.stringify([text, open, toggled.get(`monitor:${entry.id}`)]), () => {
          if (isRuntimeTaskContinuation(text)) return { component: line(theme.fg("muted", "↻ Continuing authorized task · internal runtime")) };
          if (text.startsWith("A compute monitor event requires attention.")) {
            const fields = Object.fromEntries(text.split("\n").slice(1).flatMap(row => {
              const match = /^(event_id|job_id|state|reason|error_class)=(.*)$/u.exec(row);
              return match ? [[match[1], match[2]]] : [];
            }));
            return card("monitor", `monitor:${entry.id}`, fields, { content: [{ type: "text", text }], isError: fields.state === "failed" || Boolean(fields.error_class) }, false);
          }
          const skill = /<skill[^>]*name="([^"]+)"[^>]*>/u.exec(text);
          if (skill) {
            const component = new Container();
            component.addChild(line(`[skill] ${skill[1]} ${open ? "▴" : "▾"}`));
            if (open) component.addChild(markdown(text));
            return { component, id };
          }
          return { component: markdown(`**You**\n\n${text}`) };
        });
      }
    }
    if (live.generation?.message) assistant(live.generation.message, "streaming", true);
    if (!live.run && view.failure) output.push({ component: line(theme.fg("error", `${view.failure.summary}: ${view.failure.detail}`)) });
    if (live.compactionFailure) output.push({ component: line(theme.fg("error", `Compaction failed: ${live.compactionFailure.error || live.compactionFailure.reason}`)) });
    if (live.run) output.push({ component: line(theme.fg("muted", live.generation?.retry ? "Retrying model request…" : "Working…")) });
    for (const item of view.docs["pi.inbox"]?.items || []) {
      if (item.mode === "write") continue;
      const text = messageText(item.content);
      output.push({ component: line(theme.fg("muted", `[${item.mode}] ${isRuntimeTaskContinuation(text) ? "Continuing authorized task" : text}`)) });
    }
    cache = nextCache;
    return output;
  }
  return {
    update(value) { view = value; requestRender(); },
    toggleTools() { expanded = !expanded; toggled.clear(); cache.clear(); requestRender(); },
    invalidate() { cache.clear(); },
    render(width) {
      rows = [];
      const lines = [];
      for (const item of content()) {
        lines.push("");
        const start = lines.length;
        lines.push(...item.component.render(width));
        rows.push({ ...item, start, end: lines.length });
      }
      return lines;
    },
    handleMouse(event) {
      if (event.type !== "click" || event.button !== "left") return;
      const row = rows.find(item => item.id && event.y >= item.start && event.y < item.end);
      if (!row) return;
      toggled.set(row.id, !(toggled.get(row.id) ?? expanded)); cache.clear(); requestRender();
      return { handled: true, render: true };
    },
  };
}
