import { createHash } from "node:crypto";

const hash = value => createHash("sha256").update(JSON.stringify(value)).digest("hex");
const SYNTHESIS_MAX_TOKENS = 700;

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

function validateSynthesis(value, brief) {
  if (!value || !["attention", "uncertain", "oriented"].includes(value.status)
    || typeof value.summary !== "string" || !value.summary.trim()) return null;
  const refs = new Set(brief.source_refs || []);
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
    schema_version: "research-synthesis/1",
    source_state_digest: brief.state_digest,
    source_brief_digest: brief.brief_digest,
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
 * Create an optional model synthesis over a deterministic Research Brief.
 * The call has no tools and returns a validated, reference-bound projection;
 * malformed or hallucinated references are discarded by the caller.
 */
export function createResearchSynthesis({ modelRuntime, getModel, timeoutMs = 30_000 }) {
  if (typeof modelRuntime?.completeSimple !== "function" || typeof getModel !== "function") {
    throw new TypeError("Research synthesis requires a model runtime and current-model resolver");
  }
  const cache = new Map();
  return async function synthesize(brief, { signal } = {}) {
    if (brief?.schema_version !== "research-brief/1" || brief.projection_status !== "complete") return null;
    const model = await getModel();
    if (!model) return null;
    const cacheKey = hash({ provider: model.provider, model: model.id, brief: brief.brief_digest || hash(brief) });
    if (cache.has(cacheKey)) return cache.get(cacheKey);
    const input = JSON.stringify({
      state_digest: brief.state_digest,
      status: brief.status,
      coverage: brief.coverage,
      findings: brief.findings,
      contradictions: brief.contradictions,
      uncertainties: brief.uncertainties,
      limitations: brief.limitations,
      follow_up: brief.follow_up,
      source_refs: brief.source_refs,
    });
    const request = modelRuntime.completeSimple(model, {
      systemPrompt: "You are a research context summarizer. Summarize only the supplied deterministic brief. Do not invent facts, scientific validation, identities, or references. Every ref must be copied from source_refs. Return one JSON object only with status (attention|uncertain|oriented), summary, key_findings [{ref,statement}], contradictions [{ref,statement}], uncertainties [{ref,statement}], next_actions [{action,ref,reason}], source_refs []. Do not claim completion and do not propose a write unless the action is only to inspect evidence.",
      messages: [{ role: "user", content: input, timestamp: 0 }],
    }, { maxTokens: SYNTHESIS_MAX_TOKENS, reasoning: "minimal", signal: signal || AbortSignal.timeout(timeoutMs) });
    const result = request.then(response => validateSynthesis(parseObject(textFrom(response)), brief)).catch(() => null);
    if (cache.size >= 64) cache.delete(cache.keys().next().value);
    cache.set(cacheKey, result);
    return result;
  };
}
