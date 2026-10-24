import { TOOL_CONTRACTS, toolResult } from "../shared.mjs";
import { boundWorkspaceRoot } from "../context.mjs";
import { withJobQueryRecovery } from "./query-recovery.mjs";

export function createJobTools({ commandBridge, getTaskBinding = async () => null }) {
  // Advisory only: always query live execution state, never cache a running
  // result or change task scheduling in response to repeated reads.
  const observations = new Map();
  return [
    "job_start", "job_status", "job_collect",
    "job_cancel", "job_probe", "job_reconcile", "job_platforms", "job_resources",
  ].map((name) => ({
    ...TOOL_CONTRACTS[name],
    async execute(params, api, context) {
      context?.abortSignal.throwIfAborted();
      const toolContext = api.coragent;
      const root = boundWorkspaceRoot(params, toolContext);
      const { root: _root, ...request } = params;
      const taskBinding = name === "job_start" ? await getTaskBinding(context) : null;
      const invoke = () => commandBridge.execute_command(name, name === "job_start" ? {
        ...request,
        ...(!params.prepared_ref && !params.request_file ? { request_id: params.request_id || `${toolContext.operation_id}:${api.callId}` } : {}),
        session_id: toolContext.session_id,
        ...(taskBinding === null ? {} : { user_task_id: taskBinding.user_task_id }),
        ...(taskBinding ? { execution_context: taskBinding.execution_context } : {}),
      } : request);
      const result = await (["job_status", "job_collect", "job_reconcile"].includes(name)
        ? withJobQueryRecovery(root, name, params, invoke) : invoke());
      if (name === "job_status" && ["running", "queued", "held", "submitted", "created"].includes(result.state)) {
        const key = JSON.stringify([root, toolContext.session_id, result.job_id || params.job_id || params.event_id]);
        const previous = observations.get(key);
        const count = previous?.state === result.state ? previous.count + 1 : 0;
        observations.delete(key);
        observations.set(key, { state: result.state, count });
        if (observations.size > 256) observations.delete(observations.keys().next().value);
        const polling = { unchanged_observations: count, recommended_interval_seconds: Math.min(60, 10 * 2 ** Math.min(count, 3)),
          guidance: "Continue independent work. If none remains, use task_update action=wait with this job_id and a concrete next_action describing what to inspect after completion, then finish the turn; Monitor will wake the task. Repeated unchanged reads are not progress." };
        const output = toolResult(result, JSON.stringify({ ...result, polling }, null, 2));
        output.details.polling = polling;
        return output;
      }
      if (name === "job_status") observations.delete(JSON.stringify([root, toolContext.session_id, result.job_id || params.job_id || params.event_id]));
      return toolResult(result);
    },
  }));
}
