import { createHash } from "node:crypto";
import { projectDecisionTask, projectTaskContinuation } from "../tasks/projection.mjs";
import { JOB_EVENT_IDS_LIMIT } from "../contracts/monitor.mjs";

const KEY = "coragent.research-context/2";
const PROJECTION_MAX_BYTES = 16000;
const hash = value => createHash("sha256").update(JSON.stringify(value)).digest("hex");
// Version fingerprints belong to the runtime anchor, not the model's research
// background. Keep evidence references and retrieval routes in the projection.
function modelResearchBrief(brief) {
  const { brief_id, state_digest, brief_digest, read_basis, ...research } = brief;
  return research;
}
const envelope = (tag, value) => ({ role: "user", timestamp: 0,
  content: `<${tag} origin="runtime">\n${JSON.stringify(value).replaceAll("<", "\\u003c").replaceAll(">", "\\u003e")}\n</${tag}>` });

/** Only runtime-owned entry metadata establishes coverage. Message text and model
 * summaries cannot forge a scope, input identity, or a research read receipt. */
export function contextAnchor(entries) {
  let anchor;
  for (const entry of entries) {
    const keys = [entry.kind === "pi.context" ? entry.data?.key : null,
      ...(entry.kind === "pi.compaction" ? (entry.data?.metadata || []).map(item => item?.key) : [])];
    if (keys.some(key => typeof key === "string" && key.startsWith("coragent.research-context/") && key !== KEY)) {
      throw new Error("context_schema_unsupported: start a new session with the current research context protocol");
    }
    if (entry.kind === "pi.context" && entry.data?.key === KEY) anchor = entry.data.value;
    if (entry.kind === "pi.compaction") {
      for (const item of entry.data?.metadata || []) if (item?.key === KEY) anchor = item.anchor;
    }
  }
  return anchor;
}

export function contextPolicy(settings, value = process.env.CORAGENT_CONTEXT_INPUT_TOKENS) {
  const inputTokens = value === undefined ? undefined : Number(value);
  if (inputTokens !== undefined && (!Number.isSafeInteger(inputTokens) || inputTokens < 8192)) {
    throw new Error("CORAGENT_CONTEXT_INPUT_TOKENS must be an integer of at least 8192");
  }
  if (inputTokens === undefined) return settings;
  return { ...settings, compaction: { ...settings.compaction, maxInputTokens: inputTokens,
    keepRecentTokens: Math.min(settings.compaction?.keepRecentTokens ?? 20000, Math.floor(inputTokens / 3)),
    backgroundTokens: Math.min(8192, Math.floor(inputTokens / 8)),
  } };
}

/** Pi durable's threshold, shared by final admission and terminal telemetry. */
export function contextInputBudget(contextWindow, { reserveTokens = 16384, maxInputTokens } = {}, maxTokens = 0) {
  // Preserve the requested answer budget before the SDK has to shrink it.
  // Match Pi's patched threshold and its 4096-token request safety margin.
  const reserve = Math.max(reserveTokens, maxTokens > 0 ? maxTokens + 4096 : 0);
  return Math.max(0, Math.min(contextWindow - reserve, maxInputTokens ?? Infinity));
}

/** One policy over native history, research orientation, compaction and final
 * admission. Scientific facts remain in the research store; Pi owns persistence. */
export function createContextManager({ bridge, coordinator, sessionId, estimateContextTokens,
  inputTokens, reserveTokens = 16384,
  getCompactionPolicy = () => ({ reserveTokens, maxInputTokens: inputTokens }) }) {
  async function projection(task, scope, eventIds) {
    const control = { task: projectDecisionTask(task) };
    const taskTokens = estimateContextTokens([envelope("research_context", control)]).tokens;
    let target = 2000;
    let limit = Math.min(PROJECTION_MAX_BYTES, Math.max(2048, Math.floor((target - taskTokens) * 3)));
    let brief;
    for (let attempt = 0; attempt < 3; attempt++) {
      brief = await bridge.execute_command("research_read", {
        view: "brief", limit, session_id: sessionId,
        entry_node_ids: scope.entry_node_ids, focus_node_ids: scope.focus_node_ids,
        source_submission_ids: scope.source_submission_ids, waited_job_ids: scope.waited_job_ids,
        ...(eventIds.length ? { event_ids: eventIds } : {}),
      });
      if (brief?.schema_version !== "research-brief/1"
        || !["complete", "incomplete"].includes(brief.projection_status)
        || !["brief_id", "state_digest", "brief_digest"].every(key => typeof brief[key] === "string" && brief[key])
        || !["findings", "contradictions", "uncertainties", "limitations", "follow_up", "source_refs"].every(key => Array.isArray(brief[key]))) {
        throw new Error("Invalid research brief projection");
      }
      if (Buffer.byteLength(JSON.stringify(brief)) > limit) throw new Error("Research brief exceeds its byte budget");
      if (brief.contradictions.length) target = 4000;
      const tokens = estimateContextTokens([envelope("research_context", { ...control, research_brief: modelResearchBrief(brief) })]).tokens;
      if (tokens <= target || limit === 2048 || attempt === 2) break;
      limit = Math.max(2048, Math.floor(limit * Math.max(0.25, (target - taskTokens) / Math.max(1, tokens - taskTokens)) * 0.9));
    }
    return brief;
  }

  return {
    async prepare(view, api, context, { task = null, input_ids = [], event_ids = [] } = {}) {
      const scope = { user_task_id: task?.user_task_id ?? null,
        requirements_revision: task?.requirements_revision ?? null,
        entry_node_ids: [...(task?.research?.entry_node_ids || [])].sort(),
        focus_node_ids: [...(task?.research?.focus_node_ids || [])].sort(),
        source_submission_ids: (task?.sources || []).map(s => s.submission_id),
        waited_job_ids: [...(task?.wait?.job_ids || [])].sort() };
      const scopeId = hash(scope);
      const previous = contextAnchor(view.entries);
      const eventIds = [...new Set([...event_ids, ...(task?.event_inputs || []).flatMap(item => item?.event_ids || [])])].sort();
      if (eventIds.length > JOB_EVENT_IDS_LIMIT || eventIds.some(id => typeof id !== "string" || !/^event_[1-9][0-9]*$/u.test(id))) {
        throw new Error("invalid_job_events: research context requires authenticated event references");
      }
      const inputKey = hash(input_ids);
      // A failed local read is retried on a new admitted input, not on every tool turn.
      if (previous?.scope_id === scopeId && previous.availability === "unavailable" && previous.input_key === inputKey) return;
      const boundary = view.entries.at(-1)?.id ?? null;
      const memoKey = `${KEY}:${hash({ scopeId, boundary, input_ids, eventIds })}`;
      const pinned = await api.memo(memoKey, context);
      if (pinned) return pinned.prepared ?? undefined;
      let brief;
      try {
        // Local deterministic read: every generation checks scoped facts, regardless
        // of who submitted its input. A repeated fact version adds no history entry.
        brief = await projection(task, scope, eventIds);
      } catch (error) {
        brief = { schema_version: "research-brief/1", brief_id: null, state_digest: null, brief_digest: null,
          status: "uncertain", projection_status: "incomplete", availability: "unavailable",
          findings: [], contradictions: [], uncertainties: [], limitations: [], follow_up: [], source_refs: [],
          error: { code: "research_context_unavailable", message: String(error?.message || error).slice(0, 512) },
          required_action: "Read current research before scientific or completion decisions." };
      }
      if (previous?.scope_id === scopeId && previous.availability === "available"
        && previous.state_digest === brief.state_digest && previous.projection_status === brief.projection_status) {
        await api.memo(memoKey, { prepared: null }, context);
        return;
      }
      const refreshReason = !previous ? "initial" : previous.scope_id !== scopeId ? "scope_changed"
        : previous.availability === "unavailable" ? "retry" : "facts_changed";
      const message = envelope("research_context", { task: projectDecisionTask(task),
        research_brief: modelResearchBrief(brief),
        provenance: { scope, refresh_reason: refreshReason, observed_at: new Date().toISOString() },
        notice: "Historical research brief, not live state or a read receipt. Read current fields before replacing them." });
      const data = { schema_version: "research-context/1", scope_id: scopeId,
        availability: brief.availability ?? "available", status: brief.status, input_key: inputKey,
        brief_id: brief.brief_id, brief_digest: brief.brief_digest, state_digest: brief.state_digest,
        projection_status: brief.projection_status,
        refresh_reason: refreshReason, after_entry: boundary };
      const prepared = { key: KEY, messages: [message], data };
      await api.memo(memoKey, { prepared }, context);
      return prepared;
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
        ...projectTaskContinuation(task),
      } : null, actual_user_submission_ids, automatic_continuation_enabled });
      const messages = [...request.messages, control];
      const estimate = estimateContextTokens(messages);
      // Match Pi durable's native threshold, including the requested output.
      const policy = getCompactionPolicy();
      const reserve = policy.reserveTokens ?? 16384;
      const limit = contextInputBudget(request.model.contextWindow, policy, request.maxTokens);
      const blocked = estimate.tokens > limit;
      const telemetry = { schema_version: "research-request-context/4", session_id: sessionId, request_id: requestId,
        input_tokens: estimate.tokens, usage_tokens: estimate.usageTokens, input_budget_tokens: limit,
        control_tokens: estimateContextTokens([control]).tokens, output_reserve_tokens: request.maxTokens,
        reserve_tokens: reserve, safety_tokens: request.maxTokens > 0 ? 4096 : 0, model_context_window: request.model.contextWindow, blocked,
        estimated: true, history_digest: hash(request.messages), control_digest: hash(control) };
      // Telemetry contains sizes and identities, never another full snapshot.
      try {
        const identity = hash(telemetry);
        await coordinator.commit_files({ request_id: `request-context:${identity}`, operation: "research.request_context",
          payload: telemetry, writes: { [`operations/contexts/${identity}.json`]: telemetry }, result: { digest: identity } });
      } catch { /* Observability failure does not change the model's factual context. */ }
      if (blocked) return { block: `context_budget_exceeded: input estimate ${estimate.tokens}, budget ${limit}, reserve ${reserve}, window ${request.model.contextWindow}`, compact: true };
      return { messages };
    },
  };
}
