import { TOOL_CONTRACTS, toolResult } from "../shared.mjs";
import { boundWorkspaceRoot } from "../context.mjs";
import { withJobQueryRecovery } from "./query-recovery.mjs";

export function createJobTools({ commandBridge, getTaskBinding = async () => null }) {
  // Advisory only: always query live execution state, never cache a running
  // result or change task scheduling in response to repeated reads.
  const observations = new Map();
  return [
    ["jobStart", "start"], ["jobStatus", "status"], ["jobCollect", "collect"],
    ["jobCancel", "cancel"], ["jobProbe", "probe"], ["jobReconcile", "reconcile"],
  ].map(([key, operation]) => ({
    ...TOOL_CONTRACTS[key],
    async execute(params, api, context) {
      context?.abortSignal.throwIfAborted();
      const toolContext = api.coragent;
      const root = boundWorkspaceRoot(params, toolContext);
      const { root: _root, ...request } = params;
      const taskBinding = operation === "start" ? await getTaskBinding(context) : null;
      const invoke = () => commandBridge.execute_command(`job.${operation}`, operation === "start" ? {
        ...request,
        ...(!params.prepared_ref && !params.request_file ? { request_id: params.request_id || `${toolContext.operation_id}:${api.callId}` } : {}),
        session_id: toolContext.session_id,
        ...(taskBinding === null ? {} : { user_task_id: taskBinding.user_task_id }),
        ...(taskBinding?.compute_environment ? { required_environment: taskBinding.compute_environment } : {}),
      } : request);
      const result = await (["status", "collect", "reconcile"].includes(operation)
        ? withJobQueryRecovery(root, `job_${operation}`, params, invoke) : invoke());
      if (operation === "status" && ["running", "queued", "held", "submitted", "created"].includes(result.state)) {
        const key = JSON.stringify([root, toolContext.session_id, result.job_id || params.job_id || params.event_id]);
        const previous = observations.get(key);
        const count = previous?.state === result.state ? previous.count + 1 : 0;
        observations.delete(key);
        observations.set(key, { state: result.state, count });
        if (observations.size > 256) observations.delete(observations.keys().next().value);
        const polling = { unchanged_observations: count, recommended_interval_seconds: Math.min(60, 10 * 2 ** Math.min(count, 3)),
          guidance: "Continue independent work. If none remains, use task_update action=wait with this job_id and finish the turn; Monitor will wake the task. Repeated unchanged reads are not progress." };
        const output = toolResult(result, JSON.stringify({ ...result, polling }, null, 2));
        output.details.polling = polling;
        return output;
      }
      if (operation === "status") observations.delete(JSON.stringify([root, toolContext.session_id, result.job_id || params.job_id || params.event_id]));
      return toolResult(result);
    },
  }));
}
