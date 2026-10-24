import { parseSlashCommand, COMMAND_DEFINITIONS } from "../../tools/commands.mjs";
import { projectMonitorTask } from "../../tasks/projection.mjs";

// A non-local Chord service: callers always reach the attached worker, including
// over SSH. The worker supplies the identity and the already-bound kernel bridge.
export const CLIENT_QUERIES_SERVICE_ID = "coragent.client-queries";

export function createClientQueries({ workspaceId, sessionId, queryBridge, promptManifest, readTelemetry, currentTask }) {
  const envelope = (result) => ({ workspace_id: workspaceId, session_id: sessionId, result });
  async function readRecord(params, context) {
    let first, offset = 0;
    const chunks = [];
    while (true) {
      context?.abortSignal?.throwIfAborted();
      const page = await queryBridge.execute_command("research_read", { ...params, offset, limit: 32000 });
      context?.abortSignal?.throwIfAborted();
      if (first && ["ref", "content_sha256", "total_characters", "node_revision"].some(key => page[key] !== first[key])) {
        throw Object.assign(new Error("Research changed while reading. Open this record again."), { code: "research_changed" });
      }
      const end = offset + [...page.text].length;
      if (page.schema_version !== "research-read/2" || page.ref !== params.ref
          || !page.content_sha256 || page.offset_unit !== "unicode_characters" || page.offset !== offset
          || end > page.total_characters || page.next_offset !== (end < page.total_characters ? end : null)
          || (page.next_offset !== null && end <= offset)) {
        throw Object.assign(new Error("Research returned an inconsistent page."), { code: "research_page_invalid" });
      }
      first ??= page;
      chunks.push(page.text);
      if (page.next_offset === null) return { ...first, text: chunks.join(""), offset: 0, next_offset: null };
      offset = page.next_offset;
    }
  }
  return {
    async telemetry(context) {
      context?.abortSignal?.throwIfAborted();
      return envelope(await readTelemetry(context));
    },
    async research(input, context) {
      context?.abortSignal?.throwIfAborted();
      try {
        if (typeof input !== "string") throw new TypeError("research arguments must be text");
        const invocation = parseSlashCommand("research", input);
        if (COMMAND_DEFINITIONS[invocation.command]?.effect !== "read") throw new Error("Terminal research queries must be read-only");
        if (!input.trim()) {
          const task = await currentTask(context);
          context?.abortSignal?.throwIfAborted();
          const entry_node_ids = [...(task?.research?.entry_node_ids || [])];
          const focus_node_ids = [...(task?.research?.focus_node_ids || [])];
          const waited_job_ids = [...(task?.wait?.job_ids || [])];
          const scoped = entry_node_ids.length || focus_node_ids.length;
          // A recent question authored by this session is only a navigation hint.
          // It must not stand in for a task that has no linked research.
          const result = await queryBridge.execute_command("research_read", {
            view: "brief", session_id: scoped ? sessionId : null,
            entry_node_ids, focus_node_ids, waited_job_ids, limit: 32000,
          });
          context?.abortSignal?.throwIfAborted();
          return { ...envelope(result), task: projectMonitorTask(task) };
        }
        const result = invocation.command === "research_read" && invocation.params.ref
          ? await readRecord(invocation.params, context)
          : await queryBridge.execute_command(invocation.command, invocation.params);
        context?.abortSignal?.throwIfAborted();
        return envelope(result);
      } catch (error) {
        // Pi deliberately masks arbitrary remote exceptions. Preserve useful
        // command errors as data instead of reporting "Internal server error".
        return { ...envelope(null), error: { code: error.code || error.name, message: error.message, details: error.details || {} } };
      }
    },
    async systemPrompt(context) {
      context?.abortSignal?.throwIfAborted();
      return envelope(promptManifest);
    },
  };
}
