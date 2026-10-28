import { randomUUID } from "node:crypto";
import { setTimeout as delay } from "node:timers/promises";
import { loadPi } from "../runtime/source.mjs";
import { createChatView, messageText, isRuntimeTaskContinuation } from "./chat.mjs";
import { createCoRAgentNativeClientFacet } from "./commands/facet.mjs";
import { subscribeSession } from "./connection.mjs";
import { createCommandCompletionProvider } from "./completion.mjs";
import { createSessionInsights } from "./status/insights.mjs";
import { createSessionToolCommands } from "./commands/session-tools.mjs";
import { createWorkingStatus } from "./status/working.mjs";

/** Own presentation lifetime independently of the durable session lifetime. */
export async function createClientTui({ session, request, connect, sourceRoot, terminal }) {
  const [components, themes] = await Promise.all([loadPi("tui", sourceRoot), loadPi("theme", sourceRoot)]);
  const { TuiAltScreen, ProcessTerminal, Editor, HStack, VStack, ScrollView, Text, CombinedAutocompleteProvider, matchesKey } = components;
  themes.initTheme("dark");
  terminal ??= new ProcessTerminal();
  const tui = new TuiAltScreen(terminal);
  const editor = new Editor(tui, themes.getEditorTheme());
  const commands = new Map(), listeners = new Set(), uncertain = new Map();
  const history = new Set();
  let view = { entries: [], docs: {} }, footer, activity, presentation, feedback, feedbackTimer;
  let panel, closePanel, stopped = false, started = false, currentCommand, sidebarMode = "auto";
  const scope = { workspace_id: session.workspaceId, session_id: session.sessionId };
  const redraw = () => { if (!stopped) tui.requestRender(); };
  const active = context => !stopped && !session.signal.aborted && (!context || context === currentCommand);
  const chat = createChatView({ components, theme: themes.theme, markdownTheme: themes.getMarkdownTheme(), requestRender: redraw });
  const insights = createSessionInsights({ ...components, theme: themes.theme });
  const working = createWorkingStatus({ ...components, theme: themes.theme, requestRender: redraw, fallback: insights.activity });
  const dynamic = read => ({ invalidate() { read()?.invalidate?.(); }, render: width => read()?.render(width) || [] });
  function dismiss(value) {
    const finish = closePanel; closePanel = undefined; panel = undefined;
    working.setActive(started && !stopped); tui.setFocus(editor); finish?.(value); redraw();
  }
  function clearFeedback() { clearTimeout(feedbackTimer); feedback = undefined; redraw(); }
  function cancelCommand() { currentCommand?.lifetime.abort(); currentCommand = undefined; dismiss(); clearFeedback(); }
  async function display(component, context) {
    if (!active(context)) return;
    dismiss(); panel = component; working.setActive(false);
    const focused = { handleInput(data) {
      if (matchesKey(data, "escape")) dismiss();
      else { component.handleInput?.(data); redraw(); }
    } };
    tui.setFocus(focused); redraw();
    return new Promise(resolve => { closePanel = resolve; });
  }
  const ui = {
    isSidebarVisible: () => sidebarMode !== "off" && terminal.columns >= 110 && terminal.rows >= 18,
    updateInsights(value) { if (!stopped && insights.update(value)) redraw(); },
    setFooter(value) { footer = value; redraw(); },
    setActivity(value) { activity = value; redraw(); },
    setCommandPresentation(value) { presentation = value; },
    showStatus(message, context, kind = "info") {
      if (!active(context)) return;
      clearTimeout(feedbackTimer);
      feedback = presentation?.feedback({ command: context?.name || currentCommand?.name || "status", message, kind }) || new Text(message, 1, 0);
      if (["success", "info"].includes(kind)) feedbackTimer = setTimeout(clearFeedback, 3000);
      redraw();
    },
    showDocument: (component, context) => display(component, context),
    select(title, items, selectedValue, context) {
      if (!active(context)) return Promise.resolve(undefined);
      return display(presentation.selection({ command: context?.name || currentCommand?.name || "select", title, items, selectedValue,
        onSelect: value => dismiss(value), onCancel: () => dismiss() }), context);
    },
  };
  const queries = Object.fromEntries(["telemetry", "research", "systemPrompt", "runtime"].map(query => [query,
    args => request("session/query", { ...scope, query, ...(query === "research" ? { args } : {}) })]));
  const controller = await createCoRAgentNativeClientFacet({ sourceRoot, session });
  const registry = { replace(command) { commands.set(command.name, command); return () => commands.delete(command.name); } };
  const dispose = controller.activate({ ui, queries, commands: registry,
    transcript: { state: { subscribe(listener) { listeners.add(listener); listener(view); return () => listeners.delete(listener); } } },
  });
  registry.replace({ name: "compact", description: "Compact the current context", async run(args, context) {
    const { task_id } = await request("session/compact", { ...scope, request_id: randomUUID(), ...(args ? { instructions: args } : {}) });
    let result;
    do {
      await delay(250, undefined, { signal: session.signal });
      result = await request("session/query", { ...scope, query: "compaction", args: task_id });
    } while (result.status === "running" && active(context));
    const message = result.error || ({ skipped: "Nothing to compact.", completed: "Context compacted.", cancelled: "Compaction cancelled." }[result.status] || "Compaction running…");
    ui.showStatus(message, context, result.status === "failed" ? "error" : "success");
  } });
  registry.replace({ name: "model", description: "Select a model", async run(args, context) {
    const catalog = await request("models/list", scope);
    const value = args.trim() || await ui.select("Select model", catalog.models.map(model => ({ value: `${model.provider}/${model.id}`,
      label: `${model.provider}/${model.id}`, description: model.name })),
      catalog.selected ? `${catalog.selected.provider}/${catalog.selected.id}` : undefined, context);
    if (!value || !active(context)) return;
    const model = catalog.models.find(model => `${model.provider}/${model.id}` === value);
    if (!model) throw new Error("Model is not available. Use /model to choose a model.");
    await request("model/select", { ...scope, request_id: randomUUID(), model: { provider: model.provider, id: model.id } });
    ui.showStatus(`Selected ${value}`, context, "success");
  } });
  registry.replace({ name: "thinking", description: "Select a supported thinking level", async run(args, context) {
    if (args && !["off", "minimal", "low", "medium", "high", "xhigh"].includes(args.trim())) throw new Error("Unknown thinking level");
    const catalog = await request("models/list", scope);
    const value = args.trim() || await ui.select("Thinking level", catalog.thinking_levels.map(level => ({ value: level, label: level })), catalog.thinking_level, context);
    if (!value || !active(context)) return;
    await request("session/configure", { ...scope, request_id: randomUUID(), thinking_level: value });
    ui.showStatus(`Thinking level: ${value}`, context, "success");
  } });
  registry.replace({ name: "reload", description: "Reload model configuration and credentials", async run(_args, context) {
    await request("session/reload", { ...scope, request_id: randomUUID() });
    ui.showStatus("Reloaded model configuration and credentials.", context, "success");
  } });
  for (const command of createSessionToolCommands({ session, request, ui, insights, components, theme: themes.theme, active,
    setSidebar(mode) { sidebarMode = mode; redraw(); },
  })) registry.replace(command);
  editor.setAutocompleteProvider(createCommandCompletionProvider(CombinedAutocompleteProvider, [...commands.values()], process.cwd()));
  async function runCommand(name, args, original) {
    cancelCommand();
    const lifetime = new AbortController();
    const context = currentCommand = { name, lifetime, abortSignal: AbortSignal.any([session.signal, lifetime.signal]) };
    const command = commands.get(name);
    const fail = error => {
      if (!active(context)) return;
      if (original && !editor.getText()) editor.setText(original);
      ui.showStatus(error.message, context, "error");
    };
    if (!command) { fail(new Error(`Unknown command: /${name}`)); return; }
    const validation = command.validate?.(args);
    if (validation) { fail(new Error(validation)); return; }
    ui.showStatus("Running…", context, "running");
    try { await command.run(args, context); }
    catch (error) { fail(error); }
  }
  async function submit(text) {
    if (!text.trim() || stopped) return;
    editor.addToHistory(text); editor.setText("");
    if (text.startsWith("/")) {
      const [, name, args = ""] = /^\/([^\s]+)\s*([\s\S]*)$/u.exec(text) || [];
      await runCommand(name || "", args, text); return;
    }
    cancelCommand();
    // A retry of an unconfirmed draft must reuse its business identity.
    const client_message_id = uncertain.get(text) || randomUUID();
    uncertain.set(text, client_message_id);
    try {
      const receipt = await request("input/send", { ...scope, request_id: client_message_id,
        client_message_id, text, source: "terminal", mode: "auto" });
      if (!receipt.accepted) {
        uncertain.delete(text);
        throw new Error(receipt.error?.message || "Input was rejected");
      }
      uncertain.delete(text); redraw();
    } catch (error) {
      try {
        const receipt = await request("input/status", { ...scope, client_message_id });
        if (receipt.accepted) { uncertain.delete(text); ui.showStatus("Input accepted"); return; }
        if (receipt.state === "not_found" || receipt.state === "rejected") uncertain.delete(text);
      } catch { /* Keep the identity until acceptance is known. */ }
      if (!active()) return;
      if (!editor.getText()) editor.setText(text);
      ui.showStatus(`Input delivery could not be confirmed (${client_message_id}): ${error.message}`, undefined, "error");
    }
  }
  editor.onSubmit = text => { void submit(text); };
  const scroll = new ScrollView(chat, { follow: "end", primary: true, scrollbar: "auto" });
  chat.setScrollView(scroll);
  const conversationLayout = new HStack([
    { component: scroll, grow: 1, basis: 0, minSize: 0 },
    { component: new ScrollView(insights.sidebar, { scrollbar: "auto" }), basis: 36, shrink: 0,
      visible: viewport => sidebarMode !== "off" && viewport.width >= 110 && terminal.rows >= 18 },
  ], { gap: 1 });
  let panelHeight = 4;
  const panelSlot = { invalidate() { panel?.invalidate?.(); }, render(width) {
    panel?.setViewport?.(panelHeight, true);
    return panel?.render(width) || [];
  }, handleMouse(event) { const result = panel?.handleMouse?.(event); redraw(); return result ? { ...result, focus: false } : result; } };
  const editorSlot = { invalidate() { editor.invalidate(); }, render(width) {
    editor.setAutocompleteMaxVisible(Math.max(1, Math.min(5, terminal.rows - 9)));
    return editor.render(width);
  }, handleInput(data) { if (!panel) editor.handleInput(data); }, handleMouse(event) {
    if (panel) return { handled: true, focus: false };
    const result = editor.handleMouse(event);
    tui.setFocus(editor); return result ? { ...result, focus: false } : result;
  } };
  const layoutRoot = new VStack([
    { component: conversationLayout, grow: 1, basis: 0, minSize: 0, visible: () => !panel },
    { component: panelSlot, grow: 1, basis: 0, minSize: 4, visible: viewport => {
      panelHeight = Math.max(4, Math.min(viewport.height, terminal.rows) - editor.render(viewport.width).length - 4);
      return Boolean(panel);
    } },
    { component: dynamic(() => feedback), shrink: 0, visible: () => !panel },
    { component: dynamic(() => activity), shrink: 0 },
    { component: working, shrink: 0 },
    { component: editorSlot, shrink: 0 }, { component: dynamic(() => footer), shrink: 0 },
  ]);
  tui.setLayoutRoot(layoutRoot); tui.setFocus(editor);
  const removeInput = tui.addInputListener(data => {
    if (matchesKey(data, "ctrl+c")) {
      if (panel) cancelCommand(); else if (editor.getText()) editor.setText(""); else session.quit();
      redraw(); return { consume: true };
    }
    if (matchesKey(data, "ctrl+o")) { chat.toggleTools(); return { consume: true }; }
    if (matchesKey(data, "ctrl+l") && !panel) { void runCommand("model", ""); return { consume: true }; }
    if (matchesKey(data, "f2") && feedback?.details) { void display(feedback.details(), currentCommand); return { consume: true }; }
    if (matchesKey(data, "escape")) {
      if (panel) { cancelCommand(); return { consume: true }; }
      if (editor.isShowingAutocomplete()) return;
      if (currentCommand) { cancelCommand(); return { consume: true }; }
      clearFeedback();
      ui.showStatus("Pausing…");
      void request("session/pause", { ...scope, request_id: randomUUID() })
        .then(clearFeedback, error => ui.showStatus(error.message, undefined, "error"));
      return { consume: true };
    }
  });
  const unsubscribe = subscribeSession({ connect, workspaceId: session.workspaceId, sessionId: session.sessionId,
    onView(value) {
      for (const entry of value.entries === view.entries ? [] : value.entries) {
        if (entry.kind !== "pi.user" || history.has(entry.id)) continue;
        history.add(entry.id);
        for (const message of entry.model || []) {
          const text = messageText(message.content);
          if (message.role === "user" && text && !isRuntimeTaskContinuation(text)
            && !text.startsWith("A compute monitor event requires attention.")) editor.addToHistory(text);
        }
      }
      view = value; working.update(value); chat.update(value); for (const listener of listeners) listener(value);
    },
    onError(error) { ui.showStatus(`Reconnecting: ${error?.message || "Host connection lost"}`); },
  });
  function close() {
    if (stopped) return;
    stopped = true; working.dispose(); currentCommand?.lifetime.abort(); unsubscribe(); clearTimeout(feedbackTimer); dispose(); removeInput(); dismiss();
    session.signal.removeEventListener("abort", close);
    if (started) tui.stop();
  }
  session.signal.addEventListener("abort", close, { once: true });
  return { ui, commands: registry, tui, editor, layoutRoot,
    render: width => layoutRoot.render(width),
    start() { if (!session.signal.aborted && !stopped) { started = true; tui.start(); working.setActive(!panel); } }, close,
  };
}

export async function runClientTui(options) {
  const client = await createClientTui(options);
  try {
    if (options.session.signal.aborted) return;
    client.start();
    await new Promise(resolve => options.session.signal.addEventListener("abort", resolve, { once: true }));
  } finally { client.close(); }
}
