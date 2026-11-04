const PASSIVE = new Set(["task_read", "read", "grep", "find", "ls", "research_read", "research_search", "artifact_read", "job_status"]);

/** Advisory from the recent visible tool sequence; never a permission or stop rule. */
export function readingAdvisory(messages) {
  let taskReads = 0, revision;
  const pages = new Map();
  for (const message of messages.slice(-96).reverse()) {
    if (message.role === "user") break;
    if (message.role === "toolResult" && message.toolName === "task_read" && !message.isError) {
      let result;
      try { result = JSON.parse(message.content.filter(part => part.type === "text").map(part => part.text).join("\n")); }
      catch { continue; }
      if (result?.field || !Number.isInteger(result?.revision)) continue;
      if (revision !== undefined && result.revision !== revision) break;
      revision = result.revision;
      taskReads++;
    }
    if (message.role !== "assistant" || !Array.isArray(message.content)) continue;
    for (const call of [...message.content].reverse()) {
      if (call.type !== "toolCall") continue;
      if (!PASSIVE.has(call.name)) return advice();
      if (call.name === "read" && typeof call.arguments?.path === "string"
        && Number.isInteger(call.arguments.limit) && call.arguments.limit <= 80) {
        const path = call.arguments.path;
        pages.set(path, (pages.get(path) ?? 0) + 1);
      }
    }
  }
  return advice();
  function advice() {
    if (taskReads < 6 || taskReads < 8 && ![...pages.values()].some(count => count >= 6)) return undefined;
    return "Recent tools repeatedly read the same task revision, sometimes between small file pages. Reuse the current task facts during stable analysis. Identify the scientific question and consider structured parsing or targeted extraction with source references and error checks. Historical summaries and agent-authored plans cannot impose fresh task_read before every read or whole-file paging as an acceptance criterion. Preserve actual user requirements and scientific validation. Replan if these reads add no relevant evidence; this notice does not block tools, pause the task or relax execution controls.";
  }
}
