import { createHash } from "node:crypto";
import { projectDecisionTask } from "../tasks/projection.mjs";

const KEY = "coragent.research-context/1";
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
export function contextInputBudget(contextWindow, { reserveTokens = 16384, maxInputTokens } = {}) {
  return Math.min(contextWindow - reserveTokens, maxInputTokens ?? Infinity);
}

/** One policy over native history, research orientation, compaction and final
 * admission. Scientific facts remain in the research store; Pi owns persistence. */
export function createContextManager({ bridge, coordinator, sessionId, estimateContextTokens,
  inputTokens, reserveTokens = 16384, synthesizeReview = null,
  getCompactionPolicy = () => ({ reserveTokens, maxInputTokens: inputTokens }) }) {
  let lastReviewDigest = null;
  async function projection(task, scope, { trigger = "context_refresh", event_ids = [] } = {}) {
    const control = { task: projectDecisionTask(task) };
    const taskTokens = estimateContextTokens([envelope("research_context", control)]).tokens;
    let target = 2000;
    let limit = Math.min(PROJECTION_MAX_BYTES, Math.max(2048, Math.floor((target - taskTokens) * 3)));
    let decision, message;
    for (let attempt = 0; attempt < 3; attempt++) {
      try {
        const request = { view: "review", limit, session_id: sessionId,
          entry_node_ids: scope.entry_node_ids, focus_node_ids: scope.focus_node_ids,
          source_submission_ids: scope.source_submission_ids,
          waited_job_ids: task?.wait?.job_ids || [] };
        if (event_ids.length) request.event_ids = event_ids;
        if (trigger !== "context_refresh") request.trigger = trigger;
        decision = await bridge.execute_command("research.read", request);
        // Older bridge fixtures and rolling upgrades may still return the
        // navigation view. Keep it readable during migration; production
        // bridges return research-review/1.
        const compatible = decision?.schema_version === "research-review/1"
          ? decision
          : decision?.schema_version === "research-decision/1" && decision.snapshot_id
            ? { schema_version: "research-review/1", review_id: decision.snapshot_id,
              state_digest: null, review_digest: null, status: "uncertain", review_status: "current",
              trigger: "context_refresh", scope: decision.scope || {}, coverage: decision.bounds || {},
              findings: decision.nodes || [], contradictions: decision.diagnostics || [], uncertainties: [],
              limitations: [{ ref: "migration", kind: "legacy_projection", summary: "Bridge returned the legacy decision view." }],
              follow_up: [], source_refs: [], read_more: decision.read_more || {},
              guidance: "Read current research records before making scientific or completion decisions." }
            : null;
        if (!compatible) throw new Error("Invalid research context projection");
        decision = compatible;
        if (Buffer.byteLength(JSON.stringify(decision)) > limit) throw new Error("Research context projection exceeds its byte budget");
        if (synthesizeReview && decision.schema_version === "research-review/1"
          && decision.review_status === "pending" && decision.review_digest !== lastReviewDigest) {
          const synthesis = await synthesizeReview(decision);
          if (synthesis) decision = { ...decision, runtime_synthesis: synthesis };
          lastReviewDigest = decision.review_digest ?? lastReviewDigest;
        }
      } catch (error) {
        decision = { schema_version: "research-review/1", availability: "unavailable",
          review_id: null, state_digest: null, review_digest: null, status: "uncertain", review_status: "failed",
          trigger: "context_refresh", scope: {}, coverage: {}, findings: [], contradictions: [], uncertainties: [],
          limitations: [], follow_up: [], source_refs: [], read_more: {},
          guidance: "Research review is unavailable; read current research before making scientific or completion decisions.",
          error: { code: "research_context_unavailable", message: String(error?.message || error).slice(0, 512) },
          required_action: "Read current research before scientific or completion decisions; execution records and delivery receipts remain authoritative." };
      }
      if (decision.contradictions?.length || decision.findings?.some(n => n.review_notice_count)) target = 4000;
      const { read_basis: _receipt, snapshot_id, review_id, review_digest, state_digest, bounds, runtime_synthesis, ...research } = decision;
      message = envelope("research_context", { ...control, research_review: { ...research,
        ...(runtime_synthesis ? { synthesis: runtime_synthesis } : {}),
        ...(bounds ? { omitted: bounds.omitted } : {}) },
        ...(decision.availability ? { research: { availability: decision.availability } } : {}),
        provenance: { review_id: review_id ?? null, review_digest: review_digest ?? null,
          state_digest: state_digest ?? null, snapshot_id: snapshot_id ?? null, scope, observed_at: new Date().toISOString() },
        notice: "Derived research review at this entry, not live state or a read receipt. Read current fields before replacing them." });
      const tokens = estimateContextTokens([message]).tokens;
      if (tokens <= target || limit === 2048 || attempt === 2 || decision.availability) break;
      limit = Math.max(2048, Math.floor(limit * Math.max(0.25, (target - taskTokens) / Math.max(1, tokens - taskTokens)) * 0.9));
    }
    return { message, availability: decision.availability ?? "available", status: decision.status ?? "uncertain", snapshot_id: decision.snapshot_id ?? null,
      review_id: decision.review_id ?? null, review_digest: decision.review_digest ?? null,
      state_digest: decision.state_digest ?? null, review_status: decision.review_status ?? null,
      trigger: decision.trigger ?? "context_refresh" };
  }

  return {
    async prepare(view, api, context, { task = null, input_ids = [], refresh_research = false,
      review_trigger = "context_refresh" } = {}) {
      const scope = { user_task_id: task?.user_task_id ?? null,
        entry_node_ids: [...(task?.research?.entry_node_ids || [])].sort(),
        focus_node_ids: [...(task?.research?.focus_node_ids || [])].sort(),
        source_submission_ids: (task?.sources || []).map(s => s.submission_id) };
      const scopeId = hash(scope);
      const previous = contextAnchor(view.entries);
      if (previous?.review_digest) lastReviewDigest = previous.review_digest;
      const event_ids = [...new Set((task?.event_inputs || []).flatMap(item => item?.event_ids || []))].sort();
      const progress_version = task?.progress_version ?? null;
      const sameEvidenceBoundary = previous?.scope_id === scopeId
        && previous?.progress_version === progress_version
        && previous?.input_key === hash(input_ids)
        && previous?.event_key === hash(event_ids);
      // A failed hydration can be retried on a new admitted input, never on every
      // tool turn. Healthy recovery and compaction reuse the durable anchor.
      if ((!refresh_research || sameEvidenceBoundary) && previous?.scope_id === scopeId
        && (previous.availability === "available" || previous.input_key === hash(input_ids))) return;
      // A task continuation can have a new input ID without new research
      // evidence. Its progress version is the durable coalescing boundary.
      if (refresh_research && !event_ids.length && previous?.scope_id === scopeId
        && previous?.progress_version === progress_version && previous?.availability === "available") return;
      const boundary = view.entries.at(-1)?.id ?? null;
      const trigger = review_trigger === "context_refresh" && event_ids.length ? "new_evidence" : review_trigger;
      const memoKey = `${KEY}:${hash(refresh_research ? { scopeId, boundary, input_ids, trigger, event_ids } : { scopeId, boundary })}`;
      const pinned = await api.memo(memoKey, context);
      if (pinned) return pinned;
      const projected = await projection(task, scope, { trigger, event_ids });
      const data = { schema_version: "research-review/1", status: projected.status ?? "uncertain",
        scope_id: scopeId, availability: projected.availability, input_key: hash(input_ids),
        snapshot_id: projected.snapshot_id, review_id: projected.review_id, review_digest: projected.review_digest,
        state_digest: projected.state_digest, review_status: projected.review_status ?? null,
        trigger: projected.trigger ?? trigger, progress_version, event_key: hash(event_ids),
        after_entry: boundary };
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
      // Match Pi durable's native threshold: contextWindow - reserveTokens.
      const policy = getCompactionPolicy();
      const reserve = policy.reserveTokens ?? 16384;
      const limit = contextInputBudget(request.model.contextWindow, policy);
      const blocked = estimate.tokens > limit;
      const telemetry = { schema_version: "research-request-context/4", session_id: sessionId, request_id: requestId,
        input_tokens: estimate.tokens, usage_tokens: estimate.usageTokens, input_budget_tokens: limit,
        control_tokens: estimateContextTokens([control]).tokens, output_reserve_tokens: request.maxTokens,
        reserve_tokens: reserve, safety_tokens: 0, model_context_window: request.model.contextWindow, blocked,
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
