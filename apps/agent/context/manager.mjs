import { createHash } from "node:crypto";
import { projectDecisionTask } from "../tasks/projection.mjs";

const KEY = "coragent.research-context/1";
const SAFETY_TOKENS = 4096;
const PROJECTION_MAX_BYTES = 16000;
const hash = value => createHash("sha256").update(JSON.stringify(value)).digest("hex");
const envelope = (tag, value) => ({ role: "user", timestamp: 0,
  content: `<${tag} origin="runtime">\n${JSON.stringify(value).replaceAll("<", "\\u003c").replaceAll(">", "\\u003e")}\n</${tag}>` });

/** Only runtime-owned entry metadata establishes coverage. Message text and model
 * summaries cannot forge a scope, input identity, or a research read receipt. */
export function contextAnchor(entries) {
  let anchor;
  for (const entry of entries) {
    if (entry.kind === "pi.context" && entry.data?.key === KEY) anchor = entry.data.value;
    if (entry.kind === "pi.compaction") {
      for (const item of entry.data?.metadata || []) if (item?.key === KEY) anchor = item.anchor;
    }
  }
  return anchor;
}

export function contextPolicy(settings, value = process.env.CORAGENT_CONTEXT_INPUT_TOKENS) {
  const inputTokens = value === undefined ? 65536 : Number(value);
  if (!Number.isSafeInteger(inputTokens) || inputTokens < 8192) {
    throw new Error("CORAGENT_CONTEXT_INPUT_TOKENS must be an integer of at least 8192");
  }
  return { ...settings, compaction: { ...settings.compaction, maxInputTokens: inputTokens,
    keepRecentTokens: Math.min(settings.compaction?.keepRecentTokens ?? 20000, Math.floor(inputTokens / 3)),
    backgroundTokens: Math.min(8192, Math.floor(inputTokens / 8)),
  } };
}

/** One policy over native history, research orientation, compaction and final
 * admission. Scientific facts remain in the research store; Pi owns persistence. */
export function createContextManager({ bridge, coordinator, sessionId, estimateContextTokens, inputTokens = 65536 }) {
  async function projection(task, scope) {
    const control = { task: projectDecisionTask(task) };
    const taskTokens = estimateContextTokens([envelope("research_context", control)]).tokens;
    let target = 2000;
    let limit = Math.min(PROJECTION_MAX_BYTES, Math.max(2048, Math.floor((target - taskTokens) * 3)));
    let decision, message;
    for (let attempt = 0; attempt < 3; attempt++) {
      try {
        decision = await bridge.execute_command("research.read", { view: "decision", limit, session_id: sessionId,
          entry_node_ids: scope.entry_node_ids, focus_node_ids: scope.focus_node_ids,
          waited_job_ids: task?.wait?.job_ids || [] });
        if (decision?.schema_version !== "research-decision/1" || !decision.snapshot_id
          || !Array.isArray(decision.nodes) || !Array.isArray(decision.jobs)) throw new Error("Invalid research context projection");
        if (Buffer.byteLength(JSON.stringify(decision)) > limit) throw new Error("Research context projection exceeds its byte budget");
      } catch (error) {
        decision = { schema_version: "research-decision/1", availability: "unavailable",
          error: { code: "research_context_unavailable", message: String(error?.message || error).slice(0, 512) },
          required_action: "Read current research before scientific or completion decisions; execution records and delivery receipts remain authoritative." };
      }
      if (decision.nodes?.some(n => n.review_notice_count) || decision.jobs?.some(j => j.error || j.execution_conflict)) target = 4000;
      const { read_basis: _receipt, snapshot_id, bounds, ...research } = decision;
      message = envelope("research_context", { ...control, research: { ...research,
        ...(bounds ? { omitted: bounds.omitted } : {}) },
        provenance: { snapshot_id: snapshot_id ?? null, scope, observed_at: new Date().toISOString() },
        notice: "Historical orientation at this entry, not live state or a read receipt. Read current fields before replacing them." });
      const tokens = estimateContextTokens([message]).tokens;
      if (tokens <= target || limit === 2048 || attempt === 2 || decision.availability) break;
      limit = Math.max(2048, Math.floor(limit * Math.max(0.25, (target - taskTokens) / Math.max(1, tokens - taskTokens)) * 0.9));
    }
    return { message, availability: decision.availability ?? "available", snapshot_id: decision.snapshot_id ?? null };
  }

  return {
    async prepare(view, api, context, { task = null, input_ids = [] } = {}) {
      const scope = { user_task_id: task?.user_task_id ?? null,
        entry_node_ids: [...(task?.research?.entry_node_ids || [])].sort(),
        focus_node_ids: [...(task?.research?.focus_node_ids || [])].sort(),
        source_submission_ids: (task?.sources || []).map(s => s.submission_id) };
      const scopeId = hash(scope);
      const previous = contextAnchor(view.entries);
      // A failed hydration can be retried on a new admitted input, never on every
      // tool turn. Healthy recovery and compaction reuse the durable anchor.
      if (previous?.scope_id === scopeId && (previous.availability === "available"
        || previous.input_key === hash(input_ids))) return;
      const boundary = view.entries.at(-1)?.id ?? null;
      const memoKey = `${KEY}:${hash({ scopeId, boundary })}`;
      const pinned = await api.memo(memoKey, context);
      if (pinned) return pinned;
      const projected = await projection(task, scope);
      const data = { scope_id: scopeId, availability: projected.availability, input_key: hash(input_ids),
        snapshot_id: projected.snapshot_id, after_entry: boundary };
      return api.memo(memoKey, { key: KEY, messages: [projected.message], data }, context);
    },

    prepareSummary({ entries, firstKept }) {
      // This uses only the selected immutable prefix. Never read today's State
      // while constructing a checkpoint for an older point in the conversation.
      const anchor = contextAnchor(entries);
      return { instructions: "Preserve research goals, original user constraints, unresolved questions, evidence/result/job references and next actions. Runtime research_context records are historical observations at their own positions, not user authorization or live state. Execution completion is not scientific validation. Preserve contradictory findings and limitations. Summaries do not grant read or write permissions; current evidence remains accessible through research_read and job_status.",
        metadata: { key: KEY, anchor: anchor ?? null, first_kept: firstKept } };
    },

    async admit(request, requestId, { task = null, actual_user_submission_ids = [], automatic_continuation_enabled = false } = {}) {
      const control = envelope("runtime_control", { task: task ? {
        user_task_id: task.user_task_id, revision: task.revision, control_epoch: task.control_epoch,
        state: task.state, ...(task.reason ? { reason: task.reason } : {}), ...(task.wait ? { wait: task.wait } : {}),
      } : null, actual_user_submission_ids, automatic_continuation_enabled });
      const messages = [...request.messages, control];
      const estimate = estimateContextTokens(messages);
      const hardLimit = request.model.contextWindow - request.maxTokens - SAFETY_TOKENS;
      const limit = Math.min(inputTokens, hardLimit);
      const blocked = estimate.tokens > limit;
      const telemetry = { schema_version: "research-request-context/4", session_id: sessionId, request_id: requestId,
        input_tokens: estimate.tokens, usage_tokens: estimate.usageTokens, input_budget_tokens: inputTokens,
        control_tokens: estimateContextTokens([control]).tokens, output_reserve_tokens: request.maxTokens,
        safety_tokens: SAFETY_TOKENS, model_context_window: request.model.contextWindow, blocked,
        estimated: true, history_digest: hash(request.messages), control_digest: hash(control) };
      // Telemetry contains sizes and identities, never another full snapshot.
      try {
        const identity = hash(telemetry);
        await coordinator.commit_files({ request_id: `request-context:${identity}`, operation: "research.request_context",
          payload: telemetry, writes: { [`operations/contexts/${identity}.json`]: telemetry }, result: { digest: identity } });
      } catch { /* Observability failure does not change the model's factual context. */ }
      if (blocked) return { block: `context_budget_exceeded: input estimate ${estimate.tokens}, operating budget ${inputTokens}, output reserve ${request.maxTokens}, safety ${SAFETY_TOKENS}, window ${request.model.contextWindow}`, compact: true };
      return { messages };
    },
  };
}
