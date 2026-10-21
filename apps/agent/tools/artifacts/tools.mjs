import { TOOL_CONTRACTS, toolResult } from "../shared.mjs";
import { boundWorkspaceRoot } from "../context.mjs";

export function createArtifactTools({ commandBridge }) {
  return ["artifact_register", "artifact_create", "artifact_read"]
    .map((name) => ({
      ...TOOL_CONTRACTS[name],
      async execute(params, api, context) {
        context?.abortSignal.throwIfAborted();
        boundWorkspaceRoot(params, api.coragent);
        const { root: _root, ...request } = params;
        return toolResult(await commandBridge.execute_command(name, request));
      },
    }));
}
