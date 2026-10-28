import { createCoRAgentToolRenderers } from "./renderers/tools.mjs";
import { enhanceMarkdown } from "./renderers/markdown-enhance.mjs";
import { createImageView } from "./images.mjs";

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
  let view = { entries: [], docs: {} }, expanded = false, rows = [];
  let results = new Map(), historyCache = new Map(), liveCache = new Map();
  let historyDirty = true, liveDirty = true, historyItems = [], liveItems = [];
  let historyLayout, renderedWidth, renderedLines;
  let layouts = new WeakMap();
  const dirty = () => { historyDirty = liveDirty = true; renderedLines = undefined; };
  const toggled = new Map();
  const markdown = (text, isStreaming = false) => new Markdown(enhanceMarkdown(text, { isStreaming }), 1, 0, markdownTheme);
  const line = text => new Text(text, 1, 0);
  const images = (content, filename) => (Array.isArray(content) ? content : []).filter(block => block.type === "image")
    .map(block => createImageView({ components, theme, block, filename }));
  function card(name, id, args, result, partial) {
    const renderer = createCoRAgentToolRenderers(components, [name])[name];
    const state = {};
    const context = { args, state, isPartial: partial, isError: result?.isError, durationMs: result?.durationMs };
    const container = new Container();
    container.addChild(renderer.renderCall(args, theme, context));
    if (result) container.addChild(renderer.renderResult(result, { expanded: toggled.get(id) ?? expanded }, theme, context));
    for (const image of images(result?.content, args?.path || `${name} result`)) container.addChild(image);
    return { component: container, id };
  }
  function content(history) {
    const cache = history ? historyCache : liveCache;
    const live = view.docs["pi.live"] || {};
    const output = [], nextCache = new Map();
    const add = (key, signature, create, update) => {
      const previous = cache.get(key);
      let value = previous;
      if (!previous || previous.signature !== signature) {
        if (previous && update) { update(previous.component); previous.signature = signature; }
        else value = { signature, ...create() };
      }
      nextCache.set(key, value); output.push(value);
    };
    const assistant = (message, key, isStreaming = false) => {
      for (const [index, block] of (message.content || []).entries()) {
        if (block.type === "toolCall") {
          const slot = live.tools?.find(item => item.callId === block.id);
          const result = results.get(block.id) || (slot?.output ? { content: [{ type: "text", text: slot.output }], details: slot.details } : undefined);
          add(`tool:${block.id}`, JSON.stringify([block, result, toggled.get(block.id) ?? expanded, slot?.status]),
            () => card(block.name, block.id, block.arguments, result, !results.has(block.id)));
        } else if (block.type === "text" && block.text) add(`${key}:${index}:text`, JSON.stringify([block.text, isStreaming]), () => ({ component: markdown(block.text, isStreaming) }),
          component => component.setText(enhanceMarkdown(block.text, { isStreaming })));
        else if (block.type === "thinking" && block.thinking) add(`${key}:${index}:thinking`, block.thinking,
          () => ({ component: line(theme.fg("muted", `Thinking: ${block.thinking}`)) }),
          component => component.setText(theme.fg("muted", `Thinking: ${block.thinking}`)));
        else if (block.type === "image") add(`${key}:${index}:image`, JSON.stringify(block),
          () => ({ component: createImageView({ components, theme, block }) }));
      }
      if (message.stopReason === "error" || message.errorMessage) add(`${key}:error`, message.errorMessage,
        () => ({ component: line(theme.fg("error", message.errorMessage || "Model request failed")) }));
    };
    if (history) for (const entry of view.entries) {
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
        add(id, JSON.stringify([message.content, open, toggled.get(`monitor:${entry.id}`)]), () => {
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
          const component = new Container();
          component.addChild(markdown(`**You**\n\n${text}`));
          for (const image of images(message.content, "Attached image")) component.addChild(image);
          return { component };
        });
      }
    }
    if (!history) {
      if (live.generation?.message) assistant(live.generation.message, "streaming", true);
      if (!live.run && view.failure) output.push({ component: line(theme.fg("error", `${view.failure.summary}: ${view.failure.detail}`)) });
      if (live.compactionFailure) output.push({ component: line(theme.fg("error", `Compaction failed: ${live.compactionFailure.error || live.compactionFailure.reason}`)) });
      for (const item of view.docs["pi.inbox"]?.items || []) {
        if (item.mode === "write") continue;
        const text = messageText(item.content);
        output.push({ component: line(theme.fg("muted", `[${item.mode}] ${isRuntimeTaskContinuation(text) ? "Continuing authorized task" : text}`)) });
      }
    }
    if (history) historyCache = nextCache; else liveCache = nextCache;
    return output;
  }
  function layout(items, width, offset = 0) {
    const lines = [], positions = [];
    for (const item of items) {
      lines.push("");
      const start = offset + lines.length;
      let cached = layouts.get(item.component);
      if (!cached || cached.width !== width || cached.signature !== item.signature) {
        cached = { width, signature: item.signature, lines: item.component.render(width) };
        layouts.set(item.component, cached);
      }
      lines.push(...cached.lines);
      positions.push({ ...item, start, end: offset + lines.length });
    }
    return { lines, rows: positions, width };
  }
  return {
    update(value) {
      if (value.entries !== view.entries) {
        results = new Map();
        for (const entry of value.entries) for (const message of entry.model || []) {
          if (message.role === "toolResult") results.set(message.toolCallId, message);
        }
        historyDirty = true;
      }
      if (value.docs["pi.live"]?.tools !== view.docs["pi.live"]?.tools) historyDirty = true;
      view = value; liveDirty = true; renderedLines = undefined; requestRender();
    },
    toggleTools() { expanded = !expanded; toggled.clear(); dirty(); requestRender(); },
    invalidate() {
      layouts = new WeakMap();
      for (const item of [...historyCache.values(), ...liveCache.values()]) item.component.invalidate?.();
      historyLayout = undefined; renderedLines = undefined;
    },
    render(width) {
      if (renderedLines && renderedWidth === width) return renderedLines;
      if (historyDirty) { historyItems = content(true); historyDirty = false; historyLayout = undefined; }
      if (liveDirty) { liveItems = content(false); liveDirty = false; }
      if (!historyLayout || historyLayout.width !== width) historyLayout = layout(historyItems, width);
      const tail = layout(liveItems, width, historyLayout.lines.length);
      rows = [...historyLayout.rows, ...tail.rows];
      renderedWidth = width;
      renderedLines = [...historyLayout.lines, ...tail.lines];
      return renderedLines;
    },
    handleMouse(event) {
      if (event.type !== "click" || event.button !== "left") return;
      const row = rows.find(item => item.id && event.y >= item.start && event.y < item.end);
      if (!row) return;
      toggled.set(row.id, !(toggled.get(row.id) ?? expanded)); dirty(); requestRender();
      return { handled: true, render: true };
    },
  };
}
