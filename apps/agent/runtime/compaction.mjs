/** A successful summary is complete only after its write has reached the conversation. */
export async function compactionOutcome(harness, conversation, operationId, context, { wait = false } = {}) {
  const id = Number(operationId);
  const task = /^[1-9][0-9]*$/u.test(String(operationId)) && Number.isSafeInteger(id) ? await harness.getTask(id, context) : undefined;
  if (!task || task.kind !== "pi.compaction" || task.conversationId !== conversation.id) throw new Error(`Unknown compaction: ${operationId}`);
  const state = wait ? (await harness.waitForTask(id, context)).state : task.state;
  if (state.status !== "terminal") return { status: "running", error: null };
  const outcome = state.outcome;
  if (outcome.status === "aborted") return { status: "cancelled", error: null };
  if (outcome.status !== "completed") return { status: "failed", error: outcome.error?.message || outcome.reason || "Compaction failed" };
  if (outcome.result.submissionId !== undefined) {
    const submission = await harness.submission(outcome.result.submissionId, context);
    if (!submission) return { status: "failed", error: "Compaction summary submission is missing" };
    const placed = await (wait ? submission.wait(context) : submission.status(context));
    if (placed.status === "unanswered") return { status: "failed", error: placed.reason };
    if (placed.status !== "done") return { status: "running", error: null };
  }
  return { status: outcome.result.entryId !== undefined || outcome.result.submissionId !== undefined ? "completed" : "skipped", error: null };
}
