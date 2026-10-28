/** Keep checkpoints, tool arguments and submission content out of status responses. */
export async function inspectRuntime(harness, context) {
  const inspection = await harness.inspect(context);
  const tasks = inspection.tasks.map(({ record, state }) => ({
    id: String(record.id), kind: record.kind, state: state.kind,
    restarts: record.restarts || 0,
    ...(state.kind === "sleeping" ? { until: state.until } : {}),
    ...(state.kind === "waiting" ? { waiting_on: state.on.map(String) } : {}),
    ...(state.kind === "blocked" ? { reason: state.reason } : {}),
    retryable: state.kind === "blocked" && state.reason === "restart_limit",
  }));
  tasks.sort((a, b) => Number(b.retryable) - Number(a.retryable) || Number(a.id) - Number(b.id));
  return {
    scheduling: inspection.scheduling, updated_at: new Date().toISOString(),
    counts: tasks.reduce((counts, task) => ({ ...counts, [task.state]: (counts[task.state] || 0) + 1 }), {}),
    queued_inputs: inspection.submissions.filter(item => item.status === "queued").length,
    tasks: tasks.slice(0, 100), omitted: Math.max(0, tasks.length - 100),
  };
}

/** Only explicitly parked work can be retried; finished tools must not be replayed. */
export async function retryRuntimeTask(harness, taskId, context) {
  const id = Number(taskId);
  if (!/^[1-9]\d*$/u.test(String(taskId)) || !Number.isSafeInteger(id)) {
    throw Object.assign(new Error("Invalid runtime task ID"), { code: "invalid_task" });
  }
  const inspection = await harness.inspect(context);
  const task = inspection.tasks.find(item => item.record.id === id);
  if (task?.state.kind !== "blocked" || task.state.reason !== "restart_limit") {
    throw Object.assign(new Error("This task is no longer paused at the restart limit. Refresh /tasks."), { code: "task_not_retryable" });
  }
  await harness.retryTask(id, context);
  return { accepted: true, task_id: String(id) };
}
