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

// Pi has already finished its request-level retries. Only recognizable transient
// provider failures qualify for a new run; hooks, aborts and uncertain faults do not.
export function retryableSubmission(record) {
  if (record.reason !== "model_error" || typeof record.detail !== "string") return false;
  const message = record.detail;
  if (/request_hook_failed|\b(?:400|401|403|404)\b|unauthorized|invalid.?api.?key|context.{0,20}(?:limit|overflow|length)/i.test(message)) return false;
  return /\b(?:429|500|502|503|504)\b|rate.?limit|overloaded|temporar(?:y|ily) unavailable|service unavailable|timed?\s*out|timeout|ECONNRESET|ECONNREFUSED|ETIMEDOUT|EAI_AGAIN|fetch failed|connection (?:reset|closed)|network error/i.test(message);
}

export function recoveryReady(recovery, epoch, now, maxRetries = Infinity) {
  return recovery?.state === "retrying" && recovery.control_epoch === epoch
    && (recovery.failures ?? 0) <= maxRetries
    && recovery.next_retry_at !== null && Date.parse(recovery.next_retry_at) <= now;
}
