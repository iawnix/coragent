import { recordJobLookup } from "../jobs/query-recovery.mjs";
import { TOOL_CONTRACTS, toolResult } from "../shared.mjs";
import { createCommandService } from "../commands.mjs";
import { boundWorkspaceRoot } from "../context.mjs";
import { RESEARCH_MEMORY_WRITE_PRINCIPAL } from "../../bridge/ports.mjs";

const RESEARCH_OUTPUT_LIMITS = Object.freeze({ maxBytes: 50 * 1024, maxLines: 2000, retain: "head" });

export function createResearchTools({ commandBridge, getResearchTaskId = async () => null, bindResearchNode = async () => null }) {
  const commands = createCommandService({ execute: ({ command, params, signal }) => {
    signal?.throwIfAborted();
    return commandBridge.execute_command(command, params);
  } });
  return ["research_read", "research_search", "research_create", "research_update", "research_result"].map((name) => ({
    ...TOOL_CONTRACTS[name],
    outputLimits: RESEARCH_OUTPUT_LIMITS,
    async execute(params, api, context) {
      const root = boundWorkspaceRoot(params, api.coragent);
      const {root: _root, ...request} = params;
      const writing = ["research_create", "research_update", "research_result"].includes(name);
      if (name !== "research_search") request.session_id = api.coragent?.session_id;
      if (writing) {
        requireNativeWrites(name, api.coragent);
        request.request_id = `${api.coragent.session_id}:${api.coragent.operation_id}:${api.callId}`;
      }
      const taskId = name === "research_create" ? await getResearchTaskId(context) : null;
      let result = await commands.execute(name, root, request, context?.abortSignal);
      if (name === "research_create" && result?.node?.id && taskId) {
        const binding = await bindResearchNode(result.node.id, context, taskId);
        if (binding) result = { ...result, task_research_binding: binding };
      }
      const visible = researchToolView(result, name, params);
      if (visible.complete && result?.read_basis) await commands.execute("research_observe", root, { session_id: request.session_id, read_basis: result.read_basis }, context?.abortSignal);
      if (!writing) recordJobLookup(root);
      return toolResult(visible.value, visible.text);
    },
  }));
}

// Pi bounds explicit tool text after execute. Compact JSON avoids line-limit
// truncation; oversized replies keep commit outcomes and offer smaller reads.
// Their omitted Node fields must never advance the session's read receipt.
function researchToolView(result, name, params) {
  const text = JSON.stringify(result);
  if (Buffer.byteLength(text) <= RESEARCH_OUTPUT_LIMITS.maxBytes) return {value: result, text, complete: true};
  const read = [];
  if (name === "research_read" || name === "research_search") {
    read.push({tool: name, ...params, limit: Math.max(1, Math.min(name === "research_search" ? 5 : 2000, Math.floor((params.limit || 16000) / 2)))});
  } else {
    for (const ref of new Set([result.node?.id, result.result?.id, result.ref].filter(Boolean))) {
      read.push({tool: "research_read", ref, limit: 2000});
    }
  }
  const value = {content_omitted: true,
    message: "The response exceeds the tool output budget. Read the listed references in smaller pages. For a large Node, select one field, for example field=plan. Omitted Node fields have not been acknowledged as read.",
    ...Object.fromEntries(["schema_version", "accepted", "result_saved", "assessment_selected", "ref"].filter(key => key in result).map(key => [key, result[key]])),
    ...(result.node ? {node: {id: result.node.id, revision: result.node.revision}} : {}),
    ...(result.task_research_binding ? {task_research_binding: result.task_research_binding} : {}),
    ...(result.result ? {result: {id: result.result.id, node_id: result.result.node_id}} : {}), read};
  return {value, text: JSON.stringify(value), complete: false};
}


function requireNativeWrites(toolName, toolContext) {
  // Every write requires the Host-bound Root Agent principal.
  if (toolContext?.principal !== RESEARCH_MEMORY_WRITE_PRINCIPAL) {
    throw new Error(`${toolName} requires the Root Agent principal`);
  }
}
