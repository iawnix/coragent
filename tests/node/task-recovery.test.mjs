import assert from "node:assert/strict";
import test from "node:test";
import { taskRecoveryPolicy, retryableSubmission, recoveryReady } from "../../apps/agent/tasks/recovery.mjs";

test("execution recovery classifies provider failures conservatively", () => {
  for (const detail of ["503 Service Unavailable", "429 rate limit", "fetch failed", "ECONNRESET", "Request timed out"]) {
    assert.equal(retryableSubmission({ reason: "model_error", detail }), true);
  }
  for (const record of [
    { reason: "aborted", detail: "503" }, { reason: "faulted", detail: "network error" },
    { reason: "no_model" }, { reason: "model_error", detail: "401 Unauthorized" },
    { reason: "model_error", detail: "request_hook_failed: 503 unavailable" },
    { reason: "model_error", detail: "Context length limit exceeded" },
    { reason: "model_error", detail: "Unclassified error" },
  ]) assert.equal(retryableSubmission(record), false);
});

test("recovery budget and delay are configurable, and disabled means zero successor runs", () => {
  assert.deepEqual(taskRecoveryPolicy({ CORAGENT_TASK_RECOVERY_MAX_RETRIES: "0",
    CORAGENT_TASK_RECOVERY_BASE_DELAY_MS: "10", CORAGENT_TASK_RECOVERY_MAX_DELAY_MS: "40" }),
  { maxRetries: 0, baseDelayMs: 10, maxDelayMs: 40 });
  for (const env of [{ CORAGENT_TASK_RECOVERY_MAX_RETRIES: "-1" }, { CORAGENT_TASK_RECOVERY_MAX_RETRIES: "NaN" },
    { CORAGENT_TASK_RECOVERY_BASE_DELAY_MS: "0" }, { CORAGENT_TASK_RECOVERY_MAX_DELAY_MS: "1" }]) assert.throws(() => taskRecoveryPolicy(env));
  const recovery = { state: "retrying", control_epoch: 4, next_retry_at: new Date(1000).toISOString() };
  assert.equal(recoveryReady(recovery, 4, 999), false);
  assert.equal(recoveryReady(recovery, 4, 1000), true);
  assert.equal(recoveryReady(recovery, 5, 1000), false);
  assert.equal(recoveryReady({ ...recovery, failures: 1 }, 4, 1000, 0), false);
  assert.equal(recoveryReady({ ...recovery, state: "attention_required" }, 4, 1000), false);
});


test("Monitor exposes the recovery reason and explicit resume action", async () => {
  const { formatTask } = await import("../../apps/agent/terminal/commands/monitor.mjs");
  const text = formatTask({ user_task_id: "task_1", title: "Research", state: "completing", objective: "Report", criteria: [],
    execution_recovery: { state: "attention_required", phase: "delivery", reason: "model_error", detail: "401 Unauthorized", next_retry_at: null } });
  assert.match(text, /Preparing delivery/);
  assert.match(text, /401 Unauthorized/);
  assert.match(text, /monitor task resume task_1/);
});
