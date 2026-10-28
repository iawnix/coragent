import { randomUUID } from "node:crypto";
import { createDocumentView } from "../renderers/document.mjs";
import { readWorkspaceImage, createImageView } from "../images.mjs";

export function createSessionToolCommands({ session, request, ui, insights, components, theme, active, setSidebar }) {
  const scope = { workspace_id: session.workspaceId, session_id: session.sessionId };
  const refresh = async () => {
    const value = await request("session/query", { ...scope, query: "runtime" });
    if (!session.signal.aborted) ui.updateInsights({ runtime: value, runtimeError: null });
    return value;
  };
  return [
    { name: "tasks", description: "Inspect execution, waits and recovery", async run(_args, context) {
      try { await refresh(); }
      catch (error) { ui.updateInsights({ runtimeError: error.message }); }
      if (!active(context)) return;
      await ui.showDocument(createDocumentView({ ...components, theme, wrapText: components.wrapTextWithAnsi,
        title: "Execution & recovery", command: "tasks", body: () => insights.details(), mode: "page" }), context);
    } },
    { name: "retry", description: "Retry a task paused at the restart limit", argumentHint: "[task-id]",
      validate: args => args && !/^[1-9]\d*$/u.test(args.trim()) ? "Use /retry [task-id]." : undefined,
      async run(args, context) {
        const snapshot = await refresh();
        if (!active(context)) return;
        const tasks = snapshot.tasks.filter(task => task.retryable);
        if (!tasks.length && !args.trim()) { ui.showStatus("No tasks are paused at the restart limit.", context); return; }
        const id = args.trim() || await ui.select("Retry paused execution", tasks.map(task => ({ value: task.id,
          label: `${task.kind} #${task.id}`, description: `${task.restarts} restarts · continue from saved progress` })), undefined, context);
        if (!id || !active(context)) return;
        await request("session/retry", { ...scope, request_id: randomUUID(), task_id: id });
        await refresh();
        ui.showStatus(`Retry requested for task ${id}.`, context, "success");
      },
    },
    { name: "sidebar", description: "Show research and jobs beside the conversation", argumentHint: "[auto|on|off]",
      getArgumentCompletions: prefix => ["auto", "on", "off"].filter(value => value.startsWith(prefix)).map(value => ({ value, label: value })),
      validate: args => args && !["auto", "on", "off"].includes(args.trim()) ? "Use /sidebar [auto|on|off]." : undefined,
      async run(args, context) {
        const mode = args.trim() || "auto";
        setSidebar(mode);
        ui.showStatus(mode === "off" ? "Sidebar hidden." : "Sidebar enabled on wide terminals. Use /research or /monitor on narrow terminals.", context);
      },
    },
    { name: "image", description: "Preview an image from the workspace", argumentHint: "<path>",
      validate: args => args.trim() ? undefined : "Use /image <workspace-relative path>.",
      async run(args, context) {
        const block = await readWorkspaceImage({ request, workspaceId: session.workspaceId, path: args.trim(), signal: context.abortSignal });
        if (active(context)) await ui.showDocument(createImageView({ components, theme, block, filename: block.filename, panel: true }), context);
      },
    },
  ];
}
