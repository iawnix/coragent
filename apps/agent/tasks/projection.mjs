// Bound serialized bytes, including JSON escapes and multibyte text.
function boundedText(value, bytes) {
  if (value === null || Buffer.byteLength(JSON.stringify(value)) <= bytes) return value;
  let low = 0, high = value.length;
  while (low < high) {
    const middle = Math.ceil((low + high) / 2);
    if (Buffer.byteLength(JSON.stringify(value.slice(0, middle))) <= bytes) low = middle;
    else high = middle - 1;
  }
  return value.slice(0, low);
}

/** Monitor wire summaries never expose the durable scheduling or audit records. */
export function projectMonitorTask(task, { list = false } = {}) {
  if (!task) return null;
  let truncated = false;
  const text = (value, bytes) => {
    const clipped = boundedText(value ?? null, bytes);
    truncated ||= clipped !== (value ?? null);
    return clipped;
  };
  const result = { user_task_id: task.user_task_id, revision: task.revision,
    title: text(task.title, 256), state: task.state, completion_outcome: task.completion_outcome ?? null, updated_at: task.updated_at };
  if (!list) Object.assign(result, {
    objective: text(task.objective, 1024), next_action: text(task.next_action, 1024),
    progress: task.progress ? { summary: text(task.progress.summary, 512), at: task.progress.at } : null,
    reason: text(task.reason, 512), block_kind: task.block_details?.kind ?? null,
    resume_when: text(task.block_details?.resume_when, 512),
    wait: task.wait ? { mode: task.wait.mode, job_count: task.wait.job_ids.length } : null,
    execution_plan: task.execution_plan ? { revision: task.execution_plan.revision, item_count: task.execution_plan.items.length,
      completed_count: task.execution_plan.items.filter(item => item.completion).length, active_item_id: task.active_execution_item } : null,
    execution_recovery: task.execution_recovery ? { state: task.execution_recovery.state,
      phase: task.execution_recovery.phase, detail: text(task.execution_recovery.detail, 512),
      next_retry_at: task.execution_recovery.next_retry_at } : null,
  });
  return { ...result, truncated };
}

/** A read-time scheduling observation, never a new persisted task lifecycle. */
export function projectMonitorContinuation(task, health = {}, now = Date.now()) {
  if (!task || ["completed", "partial", "cancelled"].includes(task.state)) return { state: "idle" };
  if (["paused", "blocked"].includes(task.state)) return { state: task.state };
  if (health.error) return { state: "error" };
  if (task.execution_recovery?.state === "attention_required") return { state: "attention_required" };
  if (!health.automatic_continuation_enabled) return { state: "disabled" };
  if (!health.last_checked_at) return { state: "checking" };
  if (!Number.isFinite(Date.parse(health.last_checked_at))
    || now - Date.parse(health.last_checked_at) > Math.max(30000, (health.check_interval_ms || 0) * 3)) return { state: "overdue" };
  if (task.execution_recovery) return { state: "retrying" };
  if (task.state === "waiting") return { state: "waiting" };
  return { state: task.continuation?.reservation ? "pending" : "ready" };
}

/** Current continuation hints; the historical Review may contain an older plan. */
export function projectTaskContinuation(task) {
  const result = {};
  let truncated = false;
  const text = (value, bytes) => {
    const clipped = boundedText(value, bytes);
    truncated ||= clipped !== value;
    return clipped;
  };
  if (task?.requirements_revision) result.requirements_revision = task.requirements_revision;
  if (task?.completion_outcome) result.completion_outcome = task.completion_outcome;
  if (task?.execution_target) result.execution_target = task.execution_target;
  if (task?.next_action) result.next_action = text(task.next_action, 1024);
  if (task?.block_details) {
    const block = task.block_details;
    result.block_details = { kind: block.kind, resume_when: text(block.resume_when, 512),
      evidence_refs: block.evidence_refs.slice(0, 8).map(ref => text(ref, 128)) };
    if (block.evidence_refs.length > 8) {
      result.block_details.evidence_omitted = block.evidence_refs.length - 8;
      truncated = true;
    }
  }
  if (truncated) {
    result.continuation_truncated = true;
    result.required_action = "Read task_read for the complete next action and blocker evidence before acting.";
  }
  return result;
}

/** Bounded browsing projection. Full facts remain in task_read. */
export function projectUserTask(task) {
  if (!task) return null;
  let truncated = false;
  const text = (value, bytes) => {
    const clipped = boundedText(value, bytes);
    truncated ||= clipped !== value;
    return clipped;
  };
  const sources = task.sources.length <= 4 ? task.sources : [task.sources[0], ...task.sources.slice(-3)];
  const criteria = task.criteria.slice(0, 8);
  const projection = {
    user_task_id: task.user_task_id, title: text(task.title, 256), objective: text(task.objective, 2048),
    execution_target: task.execution_target ?? null, execution_selection: task.execution_selection ? {
      target: task.execution_selection.target, executor: task.execution_selection.executor, version: task.execution_selection.version,
      selection_mode: task.execution_selection.selection_mode,
    } : null,
    requirements_revision: task.requirements_revision, completion_outcome: task.completion_outcome ?? null,
    next_action: text(task.next_action ?? null, 1024),
    state: task.state, reason: text(task.reason, 512), revision: task.revision, control_epoch: task.control_epoch,
    research: { entry_node_ids: task.research.entry_node_ids.slice(0, 8), focus_node_ids: task.research.focus_node_ids.slice(0, 8),
      entry_nodes_omitted: Math.max(0, task.research.entry_node_ids.length - 8),
      focus_nodes_omitted: Math.max(0, task.research.focus_node_ids.length - 8) },
    research_context: task.research_context ? {
      brief_id: task.research_context.brief_id, state_digest: task.research_context.state_digest,
      brief_digest: task.research_context.brief_digest, availability: task.research_context.availability,
      projection_status: task.research_context.projection_status, refresh_reason: task.research_context.refresh_reason,
      updated_at: task.research_context.updated_at,
    } : null,
    criteria: criteria.map(item => ({ id: text(item.id, 128), description: text(item.description, 256) })),
    criteria_omitted: task.criteria.length - criteria.length,
    sources: sources.map(source => ({ submission_id: source.submission_id, entry_id: source.entry_id,
      text: text(source.text, 384) })),
    sources_omitted: task.sources.length - sources.length,
    wait: task.wait ? { mode: task.wait.mode, job_ids: task.wait.job_ids.slice(0, 8).map(id => text(id, 128)),
      jobs_omitted: Math.max(0, task.wait.job_ids.length - 8) } : null,
    progress: task.progress ? { summary: text(task.progress.summary ?? null, 512), at: task.progress.at,
      evidence_refs: task.progress.evidence_refs.slice(0, 8).map(ref => text(ref, 128)),
      evidence_omitted: Math.max(0, task.progress.evidence_refs.length - 8) } : null,
    execution_recovery: task.execution_recovery ? { ...task.execution_recovery,
      detail: text(task.execution_recovery.detail ?? null, 512) } : null,
    block_details: task.block_details ? { kind: task.block_details.kind,
      resume_when: text(task.block_details.resume_when ?? null, 512),
      evidence_refs: task.block_details.evidence_refs.slice(0, 8).map(ref => text(ref, 128)),
      evidence_omitted: Math.max(0, task.block_details.evidence_refs.length - 8) } : null,
    completion: task.completion?.slice(0, 8).map(item => ({ criterion_id: text(item.criterion_id, 128),
      status: item.status, assessment_ref: item.assessment_ref, reason: text(item.reason ?? null, 512),
      evidence_refs: item.evidence_refs.slice(0, 8).map(ref => text(ref, 128)),
      evidence_omitted: Math.max(0, item.evidence_refs.length - 8) })) ?? null,
    completion_omitted: Math.max(0, (task.completion?.length || 0) - 8),
    continuation: { sequence: task.continuation.sequence, no_progress: task.continuation.no_progress },
  };
  projection.projection_truncated = truncated || projection.completion_omitted > 0
    || projection.completion?.some(item => item.evidence_omitted > 0) || projection.sources_omitted > 0 || projection.criteria_omitted > 0
    || projection.research.entry_nodes_omitted > 0 || projection.research.focus_nodes_omitted > 0
    || (projection.wait?.jobs_omitted || 0) > 0 || (projection.progress?.evidence_omitted || 0) > 0
    || (projection.block_details?.evidence_omitted || 0) > 0;
  projection.required_action = "Execution recovery is distinct from a research blocker; no_progress is an observation, not a stop condition. Full original requirements, criteria, and evidence remain in task_read. Read omitted details before revising scope or claiming completion; excerpts never relax authorization limits.";
  return projection;
}

/** Historical orientation facts, not a second authored summary. Preserve original
 * requirements; final request admission handles oversized constraints.
 * The bounded Monitor projection above remains a separate browsing contract.
 */
export function projectDecisionTask(task) {
  if (!task) return null;
  const { user_task_id, revision, state, objective, criteria } = task;
  const result = { user_task_id, revision, state, objective, criteria, requirements_revision: task.requirements_revision,
    completion_outcome: task.completion_outcome ?? null, completion: task.completion?.map(({ criterion_id, status, assessment_ref }) => ({ criterion_id, status, assessment_ref })) ?? null,
    execution_target: task.execution_target ?? null,
    ...(task.next_action ? { next_action: task.next_action } : {}) };
  if (task.title !== objective) result.title = task.title;
  if (task.reason) result.reason = task.reason;
  if (task.block_details) result.block_details = task.block_details;
  result.sources = task.sources.map(({ submission_id, entry_id, text }) => ({
    submission_id, entry_id, ...(text === objective ? { same_as: "objective" } : { text }),
  }));
  if (task.wait) result.wait = { mode: task.wait.mode, job_ids: task.wait.job_ids };
  if (task.progress) result.progress = { summary: task.progress.summary, evidence_refs: task.progress.evidence_refs };
  return result;
}
