import { createHash } from "node:crypto";

const hash = value => createHash("sha256").update(JSON.stringify(value)).digest("hex");
const REVIEW_MAX_TOKENS = 700;

function textFrom(response) {
  return (response?.content || []).filter(part => part?.type === "text").map(part => part.text).join("\n").trim();
}

function parseObject(value) {
  const clean = value.replace(/^```(?:json)?\s*/u, "").replace(/\s*```$/u, "").trim();
  try {
    const parsed = JSON.parse(clean);
    return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? parsed : null;
  } catch {
    return null;
  }
}

function boundedText(value, limit = 1000) {
  if (typeof value !== "string") return null;
  return value.length <= limit ? value : value.slice(0, limit);
}

function validateSynthesis(value, review) {
  if (!value || !["attention", "uncertain", "oriented"].includes(value.status)
    || typeof value.summary !== "string" || !value.summary.trim()) return null;
  const refs = new Set(review.source_refs || []);
  const list = (items, key) => Array.isArray(items) ? items.slice(0, 8).flatMap(item => {
    if (!item || typeof item !== "object" || typeof item.statement !== "string") return [];
    const ref = item.ref === undefined || item.ref === null ? null : item.ref;
    if (ref !== null && (!refs.has(ref) || typeof ref !== "string")) return [];
    return [{ ...(ref === null ? {} : { ref }), [key]: boundedText(item.statement),
      ...(item.reason ? { reason: boundedText(item.reason, 500) } : {}) }];
  }) : [];
  const next = Array.isArray(value.next_actions) ? value.next_actions.slice(0, 6).flatMap(item => {
    if (!item || typeof item !== "object" || typeof item.action !== "string") return [];
    if (/\b(write|publish|start|launch|close|complete|send)\b/iu.test(item.action)) return [];
    const ref = item.ref === undefined || item.ref === null ? null : item.ref;
    if (ref !== null && (!refs.has(ref) || typeof ref !== "string")) return [];
    return [{ action: boundedText(item.action, 300), ...(ref === null ? {} : { ref }),
      ...(item.reason ? { reason: boundedText(item.reason, 500) } : {}) }];
  }) : [];
  return {
    schema_version: "research-review-synthesis/1",
    source_state_digest: review.state_digest,
    source_review_digest: review.review_digest,
    status: value.status,
    summary: boundedText(value.summary),
    key_findings: list(value.key_findings, "statement"),
    contradictions: list(value.contradictions, "statement"),
    uncertainties: list(value.uncertainties, "statement"),
    next_actions: next,
    source_refs: Array.isArray(value.source_refs)
      ? [...new Set(value.source_refs.filter(ref => typeof ref === "string" && refs.has(ref)))].slice(0, 24)
      : [],
  };
}

/**
 * Create an optional model synthesis over a deterministic Research Review.
 * The call has no tools and returns a validated, reference-bound projection;
 * malformed or hallucinated references are discarded by the caller.
 */
export function createResearchReviewer({ modelRuntime, model, timeoutMs = 30_000 }) {
  if (!modelRuntime || !model) return null;
  const cache = new Map();
  return async function synthesize(review, { signal } = {}) {
    if (review?.schema_version !== "research-review/1" || review.review_status !== "pending") return null;
    const cacheKey = review.state_digest || hash(review);
    if (cache.has(cacheKey)) return cache.get(cacheKey);
    const input = JSON.stringify({
      state_digest: review.state_digest,
      status: review.status,
      coverage: review.coverage,
      findings: review.findings,
      contradictions: review.contradictions,
      uncertainties: review.uncertainties,
      limitations: review.limitations,
      follow_up: review.follow_up,
      source_refs: review.source_refs,
    });
    const request = modelRuntime.completeSimple(model, {
      systemPrompt: "You are a research-state reviewer. Summarize only the supplied deterministic review. Do not invent facts, scientific validation, identities, or references. Every ref must be copied from source_refs. Return one JSON object only with status (attention|uncertain|oriented), summary, key_findings [{ref,statement}], contradictions [{ref,statement}], uncertainties [{ref,statement}], next_actions [{action,ref,reason}], source_refs []. Do not claim completion and do not propose a write unless the action is only to inspect evidence.",
      messages: [{ role: "user", content: input, timestamp: 0 }],
    }, { maxTokens: REVIEW_MAX_TOKENS, reasoning: "minimal", signal: signal || AbortSignal.timeout(timeoutMs) });
    const result = request.then(response => validateSynthesis(parseObject(textFrom(response)), review)).catch(() => null);
    cache.set(cacheKey, result);
    return result;
  };
}
