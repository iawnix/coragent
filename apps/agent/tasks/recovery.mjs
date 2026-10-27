/** Execution recovery policy, independent of research methods and evidence counts. */
export function taskRecoveryPolicy(env = process.env) {
  const integer = (name, fallback, minimum) => {
    const value = env[name] === undefined ? fallback : Number(env[name]);
    if (!Number.isSafeInteger(value) || value < minimum || env[name] === "") throw new Error(`${name} must be an integer >= ${minimum}`);
    return value;
  };
  const policy = {
    maxRetries: integer("CORAGENT_TASK_RECOVERY_MAX_RETRIES", 2, 0),
    baseDelayMs: integer("CORAGENT_TASK_RECOVERY_BASE_DELAY_MS", 30000, 1),
    maxDelayMs: integer("CORAGENT_TASK_RECOVERY_MAX_DELAY_MS", 300000, 1),
  };
  if (policy.maxDelayMs < policy.baseDelayMs) throw new Error("Task recovery maximum delay must be >= base delay");
  return policy;
}

const providerQuotaPattern = /\b(?:DAILY_LIMIT_EXCEEDED|USAGE_LIMIT_EXCEEDED|insufficient_quota|quota_exceeded)\b|\b(?:daily|monthly|account|usage|billing|spending)[ _-](?:quota|limit)(?:[ _-](?:has been|is))?[ _-](?:exceeded|exhausted|reached)\b/iu;
const contextLimitPattern = /context.{0,20}(?:limit|overflow|length)|context_budget_exceeded/iu;

/**
 * Classify the owner of a failed Agent continuation. This is deliberately
 * separate from Task state: a model/provider failure can block a Task without
 * being a failed research Job or a controller bug.
 */
export function classifyExecutionFailure(record = {}) {
  const reason = typeof record.reason === "string" ? record.reason : "execution_failed";
  const detail = typeof record.detail === "string" ? record.detail : "";
  if (reason === "model_error") {
    if (/request_hook_failed/iu.test(detail)) return { failure_domain: "agent_runtime", failure_kind: "agent_fault" };
    if (contextLimitPattern.test(detail)) return { failure_domain: "agent_runtime", failure_kind: "context_limit" };
    return { failure_domain: "agent_runtime", failure_kind: providerQuotaPattern.test(detail) ? "provider_quota" : "provider_error" };
  }
  if (reason === "request_blocked") return { failure_domain: "agent_runtime", failure_kind: "runtime_blocked" };
  if (reason === "faulted") return { failure_domain: "agent_runtime", failure_kind: "agent_fault" };
  return { failure_domain: "agent_runtime", failure_kind: "runtime_error" };
}

/** A provider quota outage is a resource blocker even when the Agent chose the
 * legacy generic execution_failure task kind. Preserve the requested kind for
 * all other cases so existing Task semantics remain unchanged. */
export function normalizeTaskBlockKind(requestedKind, recovery, reason = "") {
  // An independent Job failure can coexist with a model outage. Do not copy
  // that outage onto an unrelated blocker merely because recovery is pending.
  if (requestedKind === "execution_failure" && recovery?.reason === "model_error"
    && classifyExecutionFailure(recovery).failure_kind === "provider_quota"
    && providerQuotaPattern.test(reason)) return "resource_unavailable";
  return requestedKind;
}

// Pi has already finished its request-level retries. Only recognizable transient
// provider failures qualify for a new run; hooks, aborts and uncertain faults do not.
export function retryableSubmission(record) {
  if (record.reason !== "model_error" || typeof record.detail !== "string") return false;
  if (classifyExecutionFailure(record).failure_kind === "provider_quota") return false;
  const message = record.detail;
  if (/request_hook_failed|\b(?:400|401|403|404)\b|unauthorized|invalid.?api.?key|context.{0,20}(?:limit|overflow|length)/i.test(message)) return false;
  return /\b(?:429|500|502|503|504)\b|rate.?limit|overloaded|temporar(?:y|ily) unavailable|service unavailable|timed?\s*out|timeout|ECONNRESET|ECONNREFUSED|ETIMEDOUT|EAI_AGAIN|fetch failed|connection (?:reset|closed)|network error/i.test(message);
}

export function recoveryReady(recovery, epoch, now, maxRetries = Infinity) {
  return recovery?.state === "retrying" && recovery.control_epoch === epoch
    && (recovery.failures ?? 0) <= maxRetries
    && recovery.next_retry_at !== null && Date.parse(recovery.next_retry_at) <= now;
}
