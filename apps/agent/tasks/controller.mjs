import { createHash } from "node:crypto";
import { defineDoc, defineDocFamily } from "@earendil-works/pi-durable";
import { resolveTaskSelection } from "./execution-selection.mjs";
import { verifyAssessment, checkCompletion } from "./assessment.mjs";
import { taskRecoveryPolicy, retryableSubmission, recoveryReady } from "./recovery.mjs";
import { hasPendingInput } from "../host/admission/input.mjs";
import shared from "../../../contracts/commands/shared.json" with { type: "json" };

export const UserTasks = defineDoc({ kind: "coragent.user-tasks", version: 1,
  scope: "conversation", history: "latest", fork: "initial",
  initial: () => ({ current: null, ids: [], cancellation_tasks: [], job_cancellations: [], automatic_suppressed: false, user_epoch: 0, latest_user_submission_id: null }) });
export const UserTask = defineDocFamily({ kind: "coragent.user-task", version: 2, family: true,
  scope: "conversation", history: "latest", fork: "initial", initial: () => ({}) });
const ControlReceipt = defineDocFamily({ kind: "coragent.task-control-receipt", version: 1, family: true,
  scope: "conversation", history: "latest", fork: "initial", initial: () => ({}) });
// A block ends scheduling, but the run that recorded it must deliver its explanation.
const BlockFinalization = defineDocFamily({ kind: "coragent.task-block-finalization", version: 1, family: true,
  scope: "conversation", history: "latest", fork: "initial", initial: () => ({}) });
// A user-directed stop disables scheduling immediately, but its consumed run
// may still verify cancellations and acknowledge the user's instruction.
const UserControlFinalization = defineDocFamily({ kind: "coragent.task-user-control-finalization", version: 1, family: true,
  scope: "conversation", history: "latest", fork: "initial", initial: () => ({}) });
// Link user-driven recovery to Pi's submission outcome. Merely asking a question
// must not restart automatic work; new task evidence and a successful run must agree.
const UserRecoveryAttempt = defineDocFamily({ kind: "coragent.task-user-recovery", version: 1, family: true,
  scope: "conversation", history: "latest", fork: "initial", initial: () => ({}) });
const terminal = new Set(["completed", "partial", "cancelled"]);
const jobFinished = new Set(["succeeded", "failed", "timed_out", "cancelled", "collected", "unknown"]);
const hash = value => createHash("sha256").update(JSON.stringify(value)).digest("hex");
const copy = value => JSON.parse(JSON.stringify(value));
export const taskError = (code, message) => Object.assign(new Error(message), { code });
const requireValue = (ok, code, message) => { if (!ok) throw taskError(code, message); };
const stamp = () => new Date().toISOString();
const researchSchema = shared.tools.task_update.properties.research;
const reviewStatuses = new Set(["current", "pending", "stale", "running", "failed"]);
const blockKinds = new Set(shared.tools.task_update.properties.block_kind.enum);
const reviewProjection = data => {
  requireValue(data && data.schema_version === "research-review/1", "research_review_invalid", "Research Review projection schema is unsupported");
  requireValue(reviewStatuses.has(data.review_status), "research_review_invalid", "Research Review lifecycle status is invalid");
  for (const key of ["review_id", "state_digest", "review_digest"])
    requireValue(data[key] === null || typeof data[key] === "string", "research_review_invalid", `Research Review ${key} must be text or null`);
  requireValue(data.review_status === "failed" || (data.review_id && data.state_digest),
    "research_review_invalid", "A usable Research Review requires review and state digests");
  requireValue(typeof data.status === "string" && data.status.length > 0, "research_review_invalid", "Research Review status is required");
  return { current_review_ref: data.review_id ?? null, last_reviewed_state_digest: data.state_digest ?? null,
    review_digest: data.review_digest ?? null, review_status: data.review_status,
    trigger: typeof data.trigger === "string" ? data.trigger : null, updated_at: stamp() };
};
const taskRecord = task => {
  if (task) requireValue(task.schema_version === "coragent-user-task/2", "task_schema_unsupported", "User tasks require coragent-user-task/2");
  return task;
};
const resultIdentity = ref => `result:${ref}`;
const artifactIdentity = artifact => {
  requireValue(typeof artifact.sha256 === "string" && /^(sha256:)?[a-f0-9]{64}$/.test(artifact.sha256),
    "task_evidence_invalid", "Artifact evidence must have a fixed content digest");
  return `artifact:${artifact.sha256.replace(/^sha256:/, "")}`;
};
const jobIdentities = (job, observed) => {
  const status = observed.status || observed, identities = [], ref = job.job_id;
  if (observed.submitted_at || ["submitted", "queued", "held", "running", "succeeded", "failed", "timed_out", "cancelled"].includes(status.state)) identities.push(`job:${ref}:accepted`);
  if (!observed.execution_conflict && !job.execution_conflict && ["succeeded", "failed", "timed_out", "cancelled"].includes(status.state)) identities.push(`job:${ref}:terminal`);
  if (!observed.execution_conflict && !job.execution_conflict && (observed.result_receipt?.collection_state === "complete"
    || job.collection_state === "complete" && job.latest_result_receipt_ref)) identities.push(`job:${ref}:collected`);
  return identities;
};

/** Policy only: Pi owns all execution, submissions, transactions and recovery. */
export function createTaskController({ harness, conversation, admission, LiveDoc, InboxDoc,
  kernel, workspaceId, sessionId, context, intervalMs = 30000, enabled = true, recoveryPolicy = taskRecoveryPolicy(), now = Date.now }) {
  let stopped = false, started = false, timer, recoveryTimer, unsubscribe, scheduled = false, running = false, lastError = null, lastCheckedAt = null;
  const currentTx = async tx => {
    const index = await tx.doc(UserTasks, conversation.id);
    return { index, task: taskRecord(index.current ? await tx.doc(UserTask, conversation.id, index.current, null) : null) };
  };
  const changed = (task, action, actor, reason) => {
    task.revision += 1; task.updated_at = stamp();
    task.audit.push({ action, actor, reason, revision: task.revision, at: task.updated_at });
  };
  const getCurrent = async ctx => {
    const index = await harness.snapshot(UserTasks, conversation.id, ctx);
    return taskRecord(index?.current ? await harness.snapshot(UserTask, conversation.id, index.current, ctx) : null);
  };
  const sourceRecords = async (ids, ctx) => {
    requireValue(Array.isArray(ids) && ids.length > 0, "task_source_required", "Cite the actual user submission IDs");
    return Promise.all([...new Set(ids)].map(async id => {
      const record = await (await harness.submission(Number(id), ctx))?.status(ctx);
      requireValue(record?.conversationId === conversation.id && (await admission.origin(record, ctx))?.producer === "user",
        "task_source_invalid", "Task requirements must cite actual user submissions in this conversation");
      const entry = await conversation.commit(tx => tx.entry(record.entry), ctx);
      const text = (entry.model || []).filter(message => message.role === "user").map(message =>
        typeof message.content === "string" ? message.content : message.content.filter(part => part.type === "text").map(part => part.text).join("\n")).join("\n");
      return { submission_id: String(record.id), entry_id: record.entry, text };
    }));
  };
  const verifyResearch = async research => {
    requireValue(research && Object.keys(research).length === researchSchema.required.length,
      "task_research_invalid", "Supply the complete entry_node_ids and focus_node_ids lists");
    for (const [key, schema] of Object.entries(researchSchema.properties)) {
      const ids = research[key];
      requireValue(Array.isArray(ids) && ids.length <= schema.maxItems && new Set(ids).size === ids.length
        && ids.every(id => typeof id === "string" && new RegExp(schema.items.pattern).test(id)),
      "task_research_invalid", `${key} requires unique Node references, at most ${schema.maxItems}`);
    }
    // The workspace-bound Memory reader validates each Node against its manifest.
    await Promise.all([...new Set([...research.entry_node_ids, ...research.focus_node_ids])].map(async ref => {
      const read = await kernel.execute_command("research_read", { ref, field: "status", limit: 1024 });
      requireValue(read.node_id === ref, "task_research_invalid", "Research reference must resolve to a Node in this workspace");
    }));
  };
  const verifyEvidence = async (refs, ctx, { completion = false, current = false, userTaskId } = {}) => {
    requireValue(Array.isArray(refs) && refs.length > 0, "task_evidence_required", "Completion and progress require evidence references");
    requireValue(!refs.some(ref => ref.startsWith("job_result_")), "task_evidence_invalid",
      "Job result receipts are not task evidence references; cite the owning job_id or collected Artifact/Result references");
    const jobs = refs.some(ref => ref.startsWith("job_")) ? await ownedJobs(userTaskId) : [];
    const identities = await Promise.all([...new Set(refs)].map(async ref => {
      ctx?.abortSignal?.throwIfAborted();
      if (/^art_[1-9][0-9]*$/.test(ref)) {
        const selector = { artifact_id: ref };
        const artifact = await kernel.execute_command("artifact_read", { ...selector, limit: 1 });
        return [artifactIdentity(artifact)];
      }
      if (ref.startsWith("job_")) {
        const job = jobs.find(item => item.job_id === ref);
        requireValue(job, "task_evidence_invalid", "Job evidence must belong to this task");
        return jobIdentities(job, await kernel.execute_command("job_status", { job_id: ref }));
      }
      const read = await kernel.execute_command("research_read", { ref, limit: 1 });
      requireValue(read.ref === ref, "task_evidence_invalid", "Evidence reference did not resolve");
      if (ref.startsWith("result_")) {
        requireValue(!current || !(read.review_notice_count || read.review_notices?.length),
          "task_evidence_stale", "A met criterion cannot rely on a Result requiring review; publish a current assessment with current evidence");
        return [resultIdentity(ref)];
      }
      return [];
    }));
    const fixed = [...new Set(identities.flat())];
    requireValue(!completion || fixed.some(identity => identity.startsWith("result:") || identity.startsWith("artifact:")),
      "task_completion_evidence_invalid", "Each criterion requires immutable Results or Artifacts; Node, note or execution activity alone is insufficient");
    return fixed;
  };
  const recordProgress = (task, identities) => {
    const previous = new Set(task.progress_identities);
    const novel = identities.filter(identity => !previous.has(identity));
    if (!novel.length) return false;
    task.progress_identities.push(...novel);
    task.progress_version += 1; task.continuation.no_progress = 0;
    return true;
  };
  async function ownedJobs(userTaskId) {
    const jobs = []; let cursor;
    do {
      const page = await kernel.execute_command("job_list", { session_id: sessionId, user_task_id: userTaskId, limit: 100, ...(cursor ? { cursor } : {}) });
      jobs.push(...page.jobs); cursor = page.next_cursor;
    } while (cursor);
    return jobs;
  }
  async function settleCancellations(task, ctx) {
    if (task.cancel_jobs.discovery_pending) {
      let jobs, error;
      try { jobs = await ownedJobs(task.user_task_id); }
      catch (failure) { error = { code: failure.code || "job_cancellation_discovery_failed", message: failure.message }; }
      await conversation.commit(async tx => {
        const current = await tx.doc(UserTask, conversation.id, task.user_task_id, null);
        if (!current.cancel_jobs.discovery_pending) return;
        if (error) {
          current.cancel_jobs.errors.discovery = error;
          changed(current, "job_cancel_error", "runtime", error.code);
          return;
        }
        delete current.cancel_jobs.errors.discovery;
        current.cancel_jobs.discovery_pending = false;
        current.cancel_jobs.pending = [...new Set([...current.cancel_jobs.pending,
          ...jobs.filter(job => !jobFinished.has(job.state) || job.state === "unknown").map(job => job.job_id)])];
        if (!current.cancel_jobs.pending.length && !current.cancel_jobs.uncertain.length) {
          const index = await tx.doc(UserTasks, conversation.id);
          index.cancellation_tasks = index.cancellation_tasks.filter(id => id !== task.user_task_id);
        }
        changed(current, "job_cancel_discovery", "runtime", "Owned Jobs selected after task cancellation was committed");
      }, ctx);
      if (error) return;
      task = await controller.read({ user_task_id: task.user_task_id }, ctx);
    }
    for (const jobId of [...task.cancel_jobs.pending, ...task.cancel_jobs.uncertain]) {
      const observing = task.cancel_jobs.uncertain.includes(jobId);
      let result, error;
      try { result = await kernel.execute_command(observing ? "job_status" : "job_cancel", { job_id: jobId }); }
      catch (failure) { error = { code: failure.code || "job_cancellation_failed", message: failure.message }; }
      await conversation.commit(async tx => {
        const current = await tx.doc(UserTask, conversation.id, task.user_task_id, null);
        if (error) {
          current.cancel_jobs.errors[jobId] = error;
          changed(current, "job_cancel_error", "runtime", error.code);
          return;
        }
        delete current.cancel_jobs.errors[jobId];
        current.cancel_jobs.receipts[jobId] = result;
        current.cancel_jobs.pending = current.cancel_jobs.pending.filter(id => id !== jobId);
        current.cancel_jobs.uncertain = current.cancel_jobs.uncertain.filter(id => id !== jobId);
        if (!jobFinished.has(result.state) || result.state === "unknown") current.cancel_jobs.uncertain.push(jobId);
        changed(current, "job_cancel_receipt", "runtime", result.state);
        if (!current.cancel_jobs.pending.length && !current.cancel_jobs.uncertain.length) {
          const index = await tx.doc(UserTasks, conversation.id);
          index.cancellation_tasks = index.cancellation_tasks.filter(id => id !== task.user_task_id);
        }
      }, ctx);
    }
  }
  async function settleJobCancellation(requestId, ctx) {
    const intent = await harness.snapshot(ControlReceipt, conversation.id, hash(requestId), ctx);
    if (intent.result) return intent.result;
    const result = { job: await kernel.execute_command("job_cancel", { job_id: intent.job_id }) };
    await conversation.commit(async tx => {
      const stored = await tx.doc(ControlReceipt, conversation.id, hash(requestId), null);
      stored.result = result;
      const index = await tx.doc(UserTasks, conversation.id);
      index.job_cancellations = index.job_cancellations.filter(id => id !== requestId);
    }, ctx);
    return result;
  }
  async function receipt(tx, requestId, payload, action) {
    requireValue(typeof requestId === "string" && requestId.length > 0, "request_id_required", "Task mutation requires a stable request_id");
    const stored = await tx.doc(ControlReceipt, conversation.id, hash(requestId), null);
    const fingerprint = hash(payload);
    if (stored.fingerprint) {
      requireValue(stored.fingerprint === fingerprint, "request_id_reused", "Task request identity belongs to another operation");
      return copy(stored.result);
    }
    const result = await action();
    Object.assign(stored, { fingerprint, result: copy(result) });
    return result;
  }
  async function readReceipt(requestId, payload, ctx) {
    requireValue(typeof requestId === "string" && requestId.length > 0, "request_id_required", "Task mutation requires a stable request_id");
    const stored = await harness.snapshot(ControlReceipt, conversation.id, hash(requestId), ctx);
    if (!stored?.fingerprint) return null;
    requireValue(stored.fingerprint === hash(payload), "request_id_reused", "Task request identity belongs to another operation");
    return copy(stored.result);
  }
  async function pauseInTransaction(tx, reason) {
    const { index, task } = await currentTx(tx);
    index.automatic_suppressed = true;
    if (task && !terminal.has(task.state)) {
      task.state = "paused"; task.reason = reason; task.control_epoch += 1;
      changed(task, "pause", "user", reason);
    }
  }
  const policy = {
    async beforeAdmission(tx, { producer, identity, basis }) {
      const { index, task } = await currentTx(tx);
      if (producer === "user") {
        index.user_epoch += 1;
        if (task && !terminal.has(task.state)) {
          task.control_epoch += 1;
          if (task.execution_recovery) {
            task.execution_recovery.state = "attention_required";
            task.execution_recovery.next_retry_at = null;
          }
          changed(task, "user_input", "user", "New user input supersedes pending automatic input");
        }
        return null;
      }
      requireValue(enabled && !index.automatic_suppressed, "task_paused", "Automatic input is suppressed");
      if (task?.execution_recovery) requireValue(producer === "task_controller"
        && recoveryReady(task.execution_recovery, task.control_epoch, now(), recoveryPolicy.maxRetries),
      "task_execution_recovery", "Execution recovery is pending or needs attention; inspect the recovery record before resuming");
      if (producer === "task_controller") {
        requireValue(task?.user_task_id === identity.user_task_id && ["active", "completing"].includes(task.state)
          && task.control_epoch === basis.control_epoch && task.revision === basis.revision,
        "task_superseded", "Task continuation basis changed");
      } else if (task) {
        requireValue(["active", "waiting"].includes(task.state), "task_paused", "Task does not accept automatic events");
        requireValue(task.revision === basis.task_revision && task.control_epoch === basis.control_epoch,
          "task_superseded", "Task event assessment changed before admission");
        const owners = basis.task_owners;
        requireValue(owners.every(owner => owner === task.user_task_id), "task_event_obsolete", "Events belong to a different user task");
        task.state = "active"; task.wait = null;
      }
      if (task?.continuation.reservation) {
        const previous = await tx.submissionByRequest(conversation.id, task.continuation.reservation.request_id);
        requireValue(["done", "unanswered"].includes(previous?.status), "busy", "An automatic continuation is already reserved");
      }
      return task ? { user_task_id: task.user_task_id, control_epoch: task.control_epoch } : null;
    },
    async afterAdmission(tx, { id, requestId, producer, identity, control }) {
      if (producer === "user") {
        const { index, task } = await currentTx(tx);
        index.latest_user_submission_id = String(id);
        if (["active", "waiting"].includes(task?.state) && task.execution_recovery?.phase === "research") {
          const attempt = await tx.doc(UserRecoveryAttempt, conversation.id, task.user_task_id, null);
          Object.assign(attempt, { submission_id: id, request_id: requestId, control_epoch: task.control_epoch,
            recovery_submission_id: task.execution_recovery.submission_id, progressed: false });
        }
        return;
      }
      if (!control) return;
      const task = await tx.doc(UserTask, conversation.id, control.user_task_id, null);
      task.continuation.sequence += 1;
      task.continuation.reservation = { submission_id: id,
        request_id: requestId,
        control_epoch: control.control_epoch, progress_version: task.progress_version };
      if (task.execution_recovery) {
        task.execution_recovery.state = "running"; task.execution_recovery.next_retry_at = null;
        if (task.state === "completing") {
          task.completion_submission_id = id; task.completion_control_epoch = task.control_epoch;
        }
      }
      if (producer === "monitor") task.event_inputs.push({ submission_id: id, request_id: requestId, event_ids: identity.event_ids });
      // The Pi submission is referenced, never copied into a second lifecycle.
    },
  };
  admission.setPolicy(policy);

  async function recordUserRecoveryProgress(tx, task) {
    if (task.execution_recovery?.phase !== "research" || !["active", "waiting"].includes(task.state)) return;
    const attempt = await tx.doc(UserRecoveryAttempt, conversation.id, task.user_task_id, null);
    const live = await tx.doc(LiveDoc, conversation.id);
    if (attempt.control_epoch === task.control_epoch && live.run?.inputs.includes(attempt.submission_id)
      && attempt.recovery_submission_id === task.execution_recovery.submission_id) attempt.progressed = true;
  }

  async function settleUserRecovery(ctx) {
    await conversation.commit(async tx => {
      const { task } = await currentTx(tx);
      if (!task?.execution_recovery || !["active", "waiting"].includes(task.state)) return;
      const attempt = await tx.doc(UserRecoveryAttempt, conversation.id, task.user_task_id, null);
      if (!attempt.submission_id || attempt.control_epoch !== task.control_epoch
        || attempt.recovery_submission_id !== task.execution_recovery.submission_id) return;
      const live = await tx.doc(LiveDoc, conversation.id), inbox = await tx.doc(InboxDoc, conversation.id);
      if (live.run || hasPendingInput(inbox.items)) return;
      const record = await tx.submissionByRequest(conversation.id, attempt.request_id);
      if (!["done", "unanswered"].includes(record?.status)) return;
      delete attempt.submission_id;
      if (record.status === "unanswered") {
        recordExecutionFailure(task, record, "research", true);
      } else if (attempt.progressed) {
        task.execution_recovery = null;
        changed(task, "user_execution_recovered", "runtime", "User execution completed with new task evidence");
      }
    }, ctx);
  }

  async function settleWait(ctx) {
    const basis = await getCurrent(ctx);
    if (basis?.state !== "waiting") return basis;
    let statuses;
    try {
      statuses = await Promise.all(basis.wait.job_ids.map(job_id => kernel.execute_command("job_status", { job_id })));
    } catch (error) {
      ctx?.abortSignal?.throwIfAborted();
      // Status refresh must not prevent a user from reading or correcting a waiting task.
      lastError = { code: error.code || "task_wait_observation_failed", message: error.message };
      return getCurrent(ctx);
    }
    const ready = basis.wait.mode === "any" ? statuses.some(job => jobFinished.has(job.state)) : statuses.every(job => jobFinished.has(job.state));
    if (!ready) return basis;
    await conversation.commit(async tx => {
      const { task } = await currentTx(tx);
      if (task?.user_task_id !== basis.user_task_id || task.revision !== basis.revision
        || task.control_epoch !== basis.control_epoch || task.state !== "waiting") return;
      task.state = "active"; task.wait = null;
      changed(task, "wait_ready", "runtime", "The explicit Job wait has completed");
    }, ctx);
    return getCurrent(ctx);
  }

  async function assertExecution(tx, record, origin) {
        const { index, task } = await currentTx(tx);
        let finalizingStop = false;
        if (task && ["paused", "cancelled"].includes(task.state) && origin.consumption) {
          const receipt = await tx.doc(UserControlFinalization, conversation.id, task.user_task_id, null);
          const live = await tx.doc(LiveDoc, conversation.id);
          finalizingStop = receipt.control_epoch === task.control_epoch && receipt.submission_id === live.run?.inputs[0]
            && receipt.submission_ids?.includes(record.id) && live.run?.inputs.includes(record.id)
            && origin.consumption.submission_id === record.id;
        }
        requireValue(enabled && (!index.automatic_suppressed || finalizingStop), "task_paused", "Automatic execution was paused");
        let finalizingBlock = false;
        if (task?.state === "blocked" && origin.consumption) {
          const receipt = await tx.doc(BlockFinalization, conversation.id, task.user_task_id, null);
          const live = await tx.doc(LiveDoc, conversation.id);
          finalizingBlock = receipt.control_epoch === task.control_epoch && receipt.submission_id === live.run?.inputs[0]
            && origin.consumption.submission_id === record.id
            && receipt.submission_ids?.includes(record.id) && live.run?.inputs.includes(record.id);
        }
        if (origin.producer === "task_controller") {
          requireValue(task?.user_task_id === origin.identity.user_task_id && (finalizingBlock || finalizingStop || !["paused", "blocked", "cancelled", "completed", "partial"].includes(task.state)),
            "task_superseded", "Task no longer permits automatic execution");
          if (!origin.consumption) requireValue(task.control_epoch === origin.admission_basis.control_epoch,
            "task_superseded", "New user input superseded this automatic continuation");
        } else if (task) {
          requireValue(finalizingBlock || finalizingStop || !["paused", "blocked", "cancelled", "completed", "partial"].includes(task.state), "task_paused", "Task is not accepting automatic execution");
          if (!origin.consumption) requireValue(task.continuation.reservation?.submission_id === record.id
            && task.continuation.reservation.control_epoch === task.control_epoch,
          "task_superseded", "New user input superseded this automatic event");
        }
  }
  const controller = {
    inputOrigin: (record, ctx) => admission.origin(record, ctx),
    async toolRestriction(ctx, toolName) {
      const task = await getCurrent(ctx);
      const live = await harness.snapshot(LiveDoc, conversation.id, ctx);
      if (task && ["paused", "cancelled"].includes(task.state)) {
        const receipt = await harness.snapshot(UserControlFinalization, conversation.id, task.user_task_id, ctx);
        if (receipt?.control_epoch === task.control_epoch && receipt.submission_id === live?.run?.inputs[0]) {
          if (toolName === "job_cancel") return null;
          return "The user stopped this task. Only read-only checks, Job cancellation and the final acknowledgement are permitted; do not launch work or create a replacement task.";
        }
      }
      if (task?.execution_recovery?.phase !== "delivery") return null;
      if (live?.run?.inputs[0] !== task.completion_submission_id) return null;
      const record = await (await harness.submission(task.completion_submission_id, ctx)).status(ctx);
      if ((await admission.origin(record, ctx))?.producer !== "task_controller") return null;
      return "Delivery recovery permits read-only tools and the final response. Existing completion evidence is retained; do not repeat calculations, writes or external delivery.";
    },
    async cancelJob({ job_id, request_id }, ctx) {
      requireValue(typeof request_id === "string" && request_id.length > 0, "request_id_required", "Job cancellation requires a stable request_id");
      await conversation.commit(async tx => {
        const stored = await tx.doc(ControlReceipt, conversation.id, hash(request_id), null);
        const fingerprint = hash({ action: "cancel_job", job_id });
        if (stored.fingerprint) {
          requireValue(stored.fingerprint === fingerprint, "request_id_reused", "Cancellation identity belongs to another operation");
          return;
        }
        Object.assign(stored, { fingerprint, job_id });
        const index = await tx.doc(UserTasks, conversation.id);
        index.job_cancellations.push(request_id);
      }, ctx);
      return settleJobCancellation(request_id, ctx);
    },
    assertExecutionAllowed: (record, origin, ctx) => conversation.commit(tx => assertExecution(tx, record, origin), ctx),
    async prepareMonitor(events, ctx) {
      const task = await getCurrent(ctx);
      const eligible = events.filter(event => task && !terminal.has(task.state)
        ? event.event.user_task_id === task.user_task_id
        : !task && !event.event.user_task_id);
      if (!eligible.length) return { events: [], basis: {} };
      if (task?.state === "waiting") {
        const statuses = await Promise.all(task.wait.job_ids.map(job_id => kernel.execute_command("job_status", { job_id })));
        const ready = task.wait.mode === "any" ? statuses.some(job => jobFinished.has(job.state)) : statuses.every(job => jobFinished.has(job.state));
        if (!ready) return { events: [], basis: {}, deferred: {
          code: "task_waiting",
          message: "The task's explicit Job wait has not completed; events remain pending",
          job_ids: task.wait.job_ids,
          mode: task.wait.mode,
        } };
      }
      return { events: eligible, basis: task ? { task_revision: task.revision, control_epoch: task.control_epoch } : {} };
    },
    current: settleWait, pauseInTransaction,
    async binding(ctx) {
      requireValue(!await controller.toolRestriction(ctx), "task_not_active", "This run may only finalize the user's stop request");
      const task = await settleWait(ctx);
      if (!task || terminal.has(task.state)) return null;
      requireValue(task.state === "active", "task_not_active", "Only an active user task may start new Jobs");
      return { user_task_id: task.user_task_id,
        ...(task.execution_target ? { execution_target: task.execution_target, route_digest: task.execution_selection?.route_digest } : {}) };
    },
    async read({ user_task_id }, ctx) {
      const task = await harness.snapshot(UserTask, conversation.id, user_task_id, ctx);
      requireValue(task?.user_task_id, "task_not_found", "User task does not exist in this conversation");
      return taskRecord(task);
    },
    /** Bind the first research Node to an otherwise unbound active task.
     * This is a derived runtime convenience: it deliberately does not advance
     * the user-task revision, so a task_update using the task_begin revision
     * remains valid in the same model turn. Explicit set_research remains the
     * authority once a task already has a research scope. */
    async bindResearchNode(nodeId, ctx, expectedTaskId) {
      requireValue(typeof nodeId === "string" && /^node_[1-9][0-9]*$/.test(nodeId),
        "task_research_invalid", "Research binding requires an existing Node reference");
      return conversation.commit(async tx => {
        const { task } = await currentTx(tx);
        if (!task || !["active", "waiting"].includes(task.state)) return null;
        if (task.user_task_id !== expectedTaskId) return null;
        if (task.research.entry_node_ids.length || task.research.focus_node_ids.length) return null;
        if (task.audit.some(item => ["set_research", "research_bind"].includes(item.action))) return null;
        task.research = { entry_node_ids: [nodeId], focus_node_ids: [nodeId] };
        task.audit.push({ action: "research_bind", actor: "runtime", reason: "First Node bound as the task research focus", revision: task.revision, at: stamp() });
        task.updated_at = stamp();
        return { user_task_id: task.user_task_id, research: copy(task.research), auto_bound: true };
      }, ctx);
    },
    /** Persist only the derived Review pointer used by Monitor. Review facts
     * remain in the research store and do not advance the user-task revision. */
    async recordResearchReview(data, ctx, expectedTaskId = null) {
      const pointer = reviewProjection(data);
      return conversation.commit(async tx => {
        const { task } = await currentTx(tx);
        if (!task || terminal.has(task.state) || expectedTaskId && task.user_task_id !== expectedTaskId) return null;
        const previous = task.research_review;
        const same = previous && ["current_review_ref", "last_reviewed_state_digest", "review_digest", "review_status", "trigger"]
          .every(key => previous[key] === pointer[key]);
        if (!same) task.research_review = pointer;
        return copy(task);
      }, ctx);
    },
    async list(ctx, { limit = 25, cursor } = {}) {
      const index = await harness.snapshot(UserTasks, conversation.id, ctx);
      const offset = cursor === undefined ? 0 : Number(cursor);
      requireValue(Number.isSafeInteger(offset) && offset >= 0, "invalid_cursor", "Task cursor must be a nonnegative integer");
      const ids = [...(index?.ids || [])].reverse();
      return { items: await Promise.all(ids.slice(offset, offset + limit).map(id => controller.read({ user_task_id: id }, ctx))),
        next_cursor: offset + limit < ids.length ? String(offset + limit) : null };
    },
    async begin(params, requestId, ctx) {
      requireValue(!await controller.toolRestriction(ctx), "task_not_active", "This run may only finalize the user's stop request");
      const replayed = await readReceipt(requestId, params, ctx);
      if (replayed !== null) return replayed;
      const sources = await sourceRecords(params.source_submission_ids, ctx);
      const selection = await resolveTaskSelection(kernel, params, sources);
      requireValue(new Set(params.criteria.map(c => c.id)).size === params.criteria.length, "task_criteria_invalid", "Criterion IDs must be unique");
      return conversation.commit(tx => receipt(tx, requestId, params, async () => {
        const { index, task: existing } = await currentTx(tx);
        requireValue(!existing || terminal.has(existing.state), "task_already_exists", "This conversation already has a nonterminal user task; update it");
        const { identifier: id } = await kernel.execute_command("research_allocate_task", { session_id: sessionId, request_id: requestId });
        const task = await tx.doc(UserTask, conversation.id, id, null);
        Object.assign(task, { schema_version: "coragent-user-task/2", user_task_id: id,
          workspace_id: workspaceId, session_id: sessionId, conversation_id: conversation.id,
          title: params.title, objective: params.objective, sources, criteria: params.criteria,
          execution_target: selection.target, execution_selection: selection, requirements_revision: 1,
          initial_plan: params.initial_plan || "Preserve the user's deliverables, establish the research scope, and produce evidence for the first decision before choosing the next action.",
          next_action: params.next_action || "Read the current requirements and perform the first concrete evidence-producing action.",
          state: "active", reason: null, revision: 1, control_epoch: 1, wait: null,
          progress: null, progress_version: 0, completion: null, completion_outcome: null, completion_stop_basis: null, execution_recovery: null, block_details: null,
          research: { entry_node_ids: [], focus_node_ids: [] }, research_review: null, progress_identities: [],
          event_inputs: [],
          continuation: { sequence: 0, reservation: null, no_progress: 0 }, audit: [],
          created_at: stamp(), updated_at: stamp() });
        index.current = id; index.ids.push(id); index.automatic_suppressed = false;
        return copy(task);
      }), ctx);
    },
    async update(params, requestId, ctx) {
      const replayed = await readReceipt(requestId, params, ctx);
      if (replayed !== null) return replayed;
      const basis = await getCurrent(ctx);
      if (params.action === "apply_user_control") {
        const sources = await sourceRecords(params.source_submission_ids, ctx);
        requireValue(basis, "task_not_active", "No current task exists");
        return controller.control({ user_task_id: basis.user_task_id, action: params.control,
          request_id: requestId, expected_revision: params.expected_revision, jobs: params.jobs }, ctx,
        { sources, payload: params, control_epoch: basis.control_epoch });
      }
      const sources = params.action === "refine" ? await sourceRecords(params.source_submission_ids, ctx) : null;
      requireValue(params.action === "set_research" || params.research === undefined, "task_research_invalid", "Research bindings use set_research");
      requireValue(["refine", "correct_execution"].includes(params.action) || (params.execution_target === undefined && params.execution_intent === undefined), "task_constraint_invalid", "Execution target changes require refine and a new user source");
      const changingTarget = params.execution_target !== undefined || params.execution_intent !== undefined;
      const selection = changingTarget && ["refine", "correct_execution"].includes(params.action)
        ? await resolveTaskSelection(kernel, params, params.action === "correct_execution" ? basis.sources : sources, basis.execution_selection) : null;
      if (params.action === "correct_execution") requireValue(params.reason?.trim() && selection
        && selection.selection_mode === "explicit", "execution_correction_invalid", "Correction needs the original explicit instruction and an audit reason");
      if (params.criteria) requireValue(new Set(params.criteria.map(c => c.id)).size === params.criteria.length,
        "task_criteria_invalid", "Criterion IDs must be unique");
      if (params.action === "set_research") await verifyResearch(params.research);
      const identities = params.action === "progress" ? await verifyEvidence(params.evidence_refs, ctx, { userTaskId: basis?.user_task_id }) : [];
      if (params.action === "block") {
        requireValue(typeof params.reason === "string" && params.reason.trim(), "task_reason_required", "A blocker needs an explanation");
        requireValue(blockKinds.has(params.block_kind), "task_block_invalid", "A blocker needs a supported block_kind");
        requireValue(typeof params.resume_when === "string" && params.resume_when.trim(), "task_block_invalid", "A blocker needs a concrete resume_when condition");
        const requiresEvidence = params.block_kind !== "missing_user_input";
        requireValue(!requiresEvidence || Array.isArray(params.evidence_refs) && params.evidence_refs.length > 0,
          "task_block_evidence_required", "This blocker kind requires evidence_refs");
        const blockEvidence = params.evidence_refs
          ? await verifyEvidence(params.evidence_refs, ctx, { userTaskId: basis?.user_task_id }) : [];
        requireValue(!requiresEvidence || blockEvidence.length > 0,
          "task_block_evidence_required", "A blocker needs verified Result, Artifact or owned Job evidence; plans and notes alone are insufficient");
      }
      let assessed = null;
      if (params.action === "propose_completion") {
        checkCompletion(basis, params);
        for (const item of params.completion) await verifyEvidence(item.evidence_refs, ctx, { completion: true, userTaskId: basis.user_task_id });
        assessed = await Promise.all(params.completion.map(item => verifyAssessment(kernel, basis, item, verifyEvidence, ctx)));
        const jobs = await ownedJobs(basis.user_task_id);
        requireValue(jobs.every(job => ["succeeded", "failed", "timed_out", "cancelled"].includes(job.state)),
          "task_jobs_unsettled", "Reconcile outstanding Jobs before closing the task");
        if (params.completion_outcome === "partial") {
          const stop = params.stop_basis;
          if (stop.kind === "user_requested") {
            const userSources = await sourceRecords(stop.source_submission_ids, ctx);
            requireValue(userSources.some(source => source.text.includes(stop.source_text || "\0")),
              "task_source_invalid", "Partial closure must quote the user's stopping instruction");
          } else await verifyEvidence(stop.evidence_refs, ctx, { completion: true, userTaskId: basis.user_task_id });
        }
      }
      if (params.action === "wait") {
        const task = await getCurrent(ctx);
        const jobs = await ownedJobs(task?.user_task_id);
        requireValue(params.wait?.job_ids?.length && params.wait.job_ids.every(id => jobs.some(job => job.job_id === id)),
          "task_wait_invalid", "Wait must cite Jobs owned by the current user task");
      }
      return conversation.commit(tx => receipt(tx, requestId, params, async () => {
        const { task } = await currentTx(tx);
        requireValue(task && !terminal.has(task.state), "task_not_active", "No nonterminal task exists");
        requireValue(task.revision === params.expected_revision, "task_revision_conflict", "Read current task before updating it");
        requireValue(task.user_task_id === basis?.user_task_id && task.control_epoch === basis.control_epoch,
          "task_superseded", "Task control changed while references were being verified");
        requireValue(task.state !== "paused", "task_paused", "Only the user may resume a paused task");
        requireValue(task.state !== "blocked" || ["refine", "correct_execution", "progress", "set_research", "block"].includes(params.action),
          "task_blocked", "Resolve the blocker with refine and the new user submission ID before continuing work");
        if (params.action === "refine") {
          if (params.objective !== undefined || params.criteria !== undefined || changingTarget) {
            requireValue(sources.some(source => !task.sources.some(previous => previous.submission_id === source.submission_id)),
              "task_source_required", "Changing the agreed scope requires a new user instruction; partial evidence does not reduce delivery criteria");
          }
          if (task.state === "blocked" || task.execution_recovery) {
            requireValue(sources.some(source => !task.sources.some(previous => previous.submission_id === source.submission_id)),
              "task_source_required", "Resuming blocked research or failed execution requires a new user instruction resolving the issue");
            task.state = "active"; task.reason = null; task.wait = null;
            task.continuation.no_progress = 0;
          }
          if (params.objective !== undefined) task.objective = params.objective;
          if (params.criteria !== undefined) task.criteria = params.criteria;
          if (selection) { task.execution_target = selection.target; task.execution_selection = selection; }
          if (params.objective !== undefined || params.criteria !== undefined) task.requirements_revision += 1;
          task.execution_recovery = null;
          task.block_details = null;
          task.completion = null; task.completion_outcome = null; task.completion_stop_basis = null; delete task.completion_submission_id; delete task.completion_control_epoch;
          if (task.state === "completing") task.state = "active";
          task.sources.push(...sources); task.control_epoch += 1;
          if (params.next_action !== undefined) task.next_action = params.next_action;
        } else if (params.action === "correct_execution") {
          requireValue(selection.target !== task.execution_target, "execution_correction_invalid", "Correction must fix a different target, not silently accept changed routing");
          task.execution_target = selection.target; task.execution_selection = selection;
          task.control_epoch += 1;
          task.completion = null; task.completion_outcome = null; task.completion_stop_basis = null;
          delete task.completion_submission_id; delete task.completion_control_epoch;
          if (task.state === "completing") task.state = "active";
        } else if (params.action === "progress") {
          if (recordProgress(task, identities)) await recordUserRecoveryProgress(tx, task);
          task.progress = { summary: params.reason ?? null, evidence_refs: params.evidence_refs, at: stamp() };
          if (params.next_action !== undefined) task.next_action = params.next_action;
        } else if (params.action === "set_research") {
          task.research = copy(params.research);
        } else if (params.action === "wait") {
          task.state = "waiting"; task.wait = params.wait; task.block_details = null;
        } else if (params.action === "block") {
          requireValue(params.reason, "task_reason_required", "A blocker needs an explanation");
          const live = await tx.doc(LiveDoc, conversation.id);
          const finalization = await tx.doc(BlockFinalization, conversation.id, task.user_task_id, null);
          // Generation task IDs change after tools; Pi input IDs identify the continuing run.
          Object.assign(finalization, { submission_id: live.run?.inputs[0] ?? null,
            submission_ids: live.run?.inputs ?? [], control_epoch: task.control_epoch });
          task.state = "blocked"; task.reason = params.reason; task.wait = null;
          task.block_details = { kind: params.block_kind, resume_when: params.resume_when, evidence_refs: params.evidence_refs ?? [] };
          task.execution_recovery = null; task.completion = null; task.completion_outcome = null; task.completion_stop_basis = null; delete task.completion_submission_id; delete task.completion_control_epoch;
        } else if (params.action === "propose_completion") {
          const live = await tx.doc(LiveDoc, conversation.id);
          requireValue(live.run?.inputs.length, "task_completion_run_required", "Completion must be delivered in an active model run");
          task.state = "completing"; task.wait = null; task.completion = assessed;
          task.completion_outcome = params.completion_outcome; task.completion_stop_basis = params.stop_basis || null;
          task.completion_submission_id = live.run.inputs[0]; task.completion_control_epoch = task.control_epoch;
          task.execution_recovery = null;
        } else throw taskError("task_action_invalid", "Unknown task update action");
        changed(task, params.action, "agent", params.reason || null);
        return copy(task);
      }), ctx);
    },
    async observeToolResults(entries, ctx) {
      const basis = await getCurrent(ctx);
      if (!basis || !["active", "waiting"].includes(basis.state)) return;
      const substantive = new Set(["research_result", "artifact_create", "artifact_register", "job_start", "job_status", "job_collect", "job_reconcile", "job_cancel"]);
      const observations = [], refs = [], identities = [];
      let reviewPending = false;
      for (const entry of entries) for (const message of entry.model || []) {
        if (message.role !== "toolResult" || message.isError || !substantive.has(message.toolName)) continue;
        const result = message.details.result;
        if (message.toolName === "research_result") { refs.push(result.result.id); identities.push(resultIdentity(result.result.id)); reviewPending = true; }
        else if (message.toolName.startsWith("artifact_")) { refs.push(result.artifact_id); identities.push(artifactIdentity(result)); reviewPending = true; }
        else if (result.accepted !== false) observations.push(result);
        if (message.toolName === "job_collect" || message.toolName === "job_reconcile"
          || message.toolName === "job_status" && jobFinished.has(result.state)) reviewPending = true;
      }
      // Successful tool receipts already attest immutable products. Only Job
      // ownership needs a read; queries of historical Jobs remain valid tools.
      const jobs = observations.length ? await ownedJobs(basis.user_task_id) : [];
      for (const observed of observations) {
        const job = jobs.find(item => item.job_id === observed.job_id);
        if (job) { refs.push(job.job_id); identities.push(...jobIdentities(job, observed)); }
      }
      if (!refs.length) return;
      await conversation.commit(async tx => {
        const { task } = await currentTx(tx);
        if (task?.user_task_id !== basis.user_task_id || task.control_epoch !== basis.control_epoch || !["active", "waiting"].includes(task.state)) return;
        if (!recordProgress(task, [...new Set(identities)])) return;
        await recordUserRecoveryProgress(tx, task);
        task.progress = { summary: "Recorded new research evidence or execution milestone",
          evidence_refs: [...new Set(refs)], at: stamp(), review_pending: reviewPending };
        changed(task, "tool_progress", "runtime", task.progress.summary);
      }, ctx);
    },
    async control({ user_task_id, action, request_id, expected_revision, jobs }, ctx, userInstruction = null) {
      requireValue(["pause", "resume", "cancel"].includes(action), "task_action_invalid", "Unknown task control action");
      if (action === "cancel") requireValue(["keep", "cancel"].includes(jobs), "task_cancel_policy_required", "Specify jobs=keep or jobs=cancel");
      else requireValue(jobs === undefined, "task_cancel_policy_invalid", "Job policy belongs only to cancellation");
      const result = await conversation.commit(tx => receipt(tx, request_id,
        userInstruction?.payload || { user_task_id, action, expected_revision, jobs }, async () => {
          const { index, task } = await currentTx(tx);
          requireValue(task?.user_task_id === user_task_id && (!terminal.has(task.state) || task.state === "partial" && action === "resume"), "task_not_active", "Task is not the current nonterminal task");
          requireValue(task.revision === expected_revision, "task_revision_conflict", "Read the current task revision before controlling it");
          const live = await tx.doc(LiveDoc, conversation.id);
          if (userInstruction) {
            requireValue(task.control_epoch === userInstruction.control_epoch, "task_superseded", "Task control changed during source verification");
            requireValue(userInstruction.sources.some(source => source.submission_id === index.latest_user_submission_id)
              && userInstruction.sources.every(source => live.run?.inputs.includes(Number(source.submission_id))),
            "task_control_source_invalid", "Cite the latest actual user instruction consumed by this run; automatic inputs and historical instructions cannot control a task");
            task.sources.push(...userInstruction.sources.filter(source => !task.sources.some(previous => previous.submission_id === source.submission_id)));
          }
          if (task.state === "partial" && action === "resume") {
            task.completion_history = [...(task.completion_history || []), { completion: copy(task.completion), outcome: task.completion_outcome,
              stop_basis: copy(task.completion_stop_basis), closed_at: task.updated_at }];
            task.completion = null; task.completion_outcome = null; task.completion_stop_basis = null;
            delete task.completion_submission_id; delete task.completion_control_epoch;
          }
          task.control_epoch += 1;
          task.state = action === "resume" ? "active" : action === "pause" ? "paused" : "cancelled";
          task.reason = action === "resume" ? null : `User requested ${action}`;
          task.block_details = null;
          index.automatic_suppressed = action !== "resume";
          if (action !== "resume") {
            task.wait = null; task.execution_recovery = null;
            if (userInstruction) {
              const finalization = await tx.doc(UserControlFinalization, conversation.id, task.user_task_id, null);
              Object.assign(finalization, { control_epoch: task.control_epoch, submission_id: live.run.inputs[0],
                submission_ids: [...live.run.inputs] });
            }
          }
          if (action === "resume") {
            task.continuation.no_progress = 0; task.wait = null;
            task.execution_recovery = null;
            if (task.completion && task.completion_submission_id !== undefined) {
              task.state = "completing"; task.completion_control_epoch = task.control_epoch;
              task.execution_recovery = { state: "retrying", phase: "delivery", failures: 0,
                submission_id: task.completion_submission_id, control_epoch: task.control_epoch,
                reason: "user_resume", detail: null, next_retry_at: new Date(now()).toISOString() };
            }
          }
          if (action === "cancel") {
            task.cancel_jobs = { policy: jobs, discovery_pending: jobs === "cancel", pending: [], receipts: {}, uncertain: [], errors: {} };
            if (jobs === "cancel") index.cancellation_tasks.push(task.user_task_id);
            if (live.run && !userInstruction) {
              const runTask = await tx.task(live.run.taskId);
              if (runTask && runTask.state.status !== "terminal") tx.setTask({ ...runTask, abortRequested: true });
            }
          }
          changed(task, action, "user", task.reason);
          return { task: copy(task), jobs_policy: jobs || null };
        }), ctx);
      if (action === "cancel" && jobs === "cancel") {
        await settleCancellations(await controller.read({ user_task_id }, ctx), ctx);
        result.task = await controller.read({ user_task_id }, ctx);
        result.job_cancellations = Object.values(result.task.cancel_jobs.receipts);
      }
      harness.resume(); schedule();
      return result;
    },
    async validateConsumption(record, origin, ctx, consumptionBasis = origin.admission_basis) {
      const inherited = origin.producer === "task_controller" ? origin.admission_basis.event_inputs : [];
      const inheritedEvents = inherited?.length ? await Promise.all(inherited.flatMap(input => input.event_ids).map(event_id =>
        kernel.execute_command("job_monitor_assess", { event_id, session_id: sessionId }))) : [];
      requireValue(inheritedEvents.every(event => event.obsolete || event.admitted), "monitor_paused", "Deferred event delivery is paused");
      await admission.recordConsumption(record, consumptionBasis, ctx, tx => assertExecution(tx, record, origin));
      for (const input of inherited || []) {
        await admission.recordSuccessorConsumption(await admission.status(input.request_id, ctx), record.id,
          { event_ids: input.event_ids }, ctx);
      }
      if (inherited?.length) {
        const consumedIds = inherited.map(input => input.submission_id);
        await conversation.commit(async tx => {
          const { task } = await currentTx(tx);
          if (task) task.event_inputs = task.event_inputs.filter(input => !consumedIds.includes(input.submission_id));
        }, ctx);
      }
    },
    async completeMonitorConsumption(record, ctx) {
      await conversation.commit(async tx => {
        const { task } = await currentTx(tx);
        if (task) task.event_inputs = task.event_inputs.filter(input => input.submission_id !== record.id);
      }, ctx);
    },
    async reconcile(ctx = context) {
      const index = await harness.snapshot(UserTasks, conversation.id, ctx);
      for (const requestId of index?.job_cancellations || []) {
        try { await settleJobCancellation(requestId, ctx); }
        catch (error) { lastError = { code: error.code || "job_cancellation_failed", message: error.message }; }
      }
      for (const id of index?.cancellation_tasks || []) await settleCancellations(await controller.read({ user_task_id: id }, ctx), ctx);
      let task = await settleWait(ctx);
      if (!task || !["active", "waiting", "completing"].includes(task.state)) return;
      const [live, inbox] = await Promise.all([harness.snapshot(LiveDoc, conversation.id, ctx), harness.snapshot(InboxDoc, conversation.id, ctx)]);
      // A queued compaction write is safe to flush at the next boundary. Only
      // queued user/steering inputs should hold back internal task recovery.
      if (live?.run || hasPendingInput(inbox?.items)) return;
      await settleUserRecovery(ctx);
      task = await getCurrent(ctx);
      if (!enabled) return;
      if (task.state === "completing") {
        const delivery = await (await harness.submission(task.completion_submission_id, ctx)).status(ctx);
        if (!["done", "unanswered"].includes(delivery.status)) return;
        let assessmentError = null;
        if (delivery.status === "done") {
          try {
            for (const item of task.completion) {
              const checked = await verifyAssessment(kernel, task, item, verifyEvidence, ctx);
              requireValue(JSON.stringify(checked.evidence_identities) === JSON.stringify(item.evidence_identities),
                "task_evidence_changed", "Fixed acceptance evidence changed after the completion proposal");
            }
          } catch (error) { assessmentError = error; }
        }
        await conversation.commit(async tx => {
          const { task: current } = await currentTx(tx);
          if (current.revision !== task.revision || current.state !== "completing") return;
          if (assessmentError) {
            current.state = "active"; current.reason = "Completion evidence requires reassessment: " + assessmentError.message;
            current.completion = null; current.completion_outcome = null; current.completion_stop_basis = null;
            delete current.completion_submission_id; delete current.completion_control_epoch;
            current.next_action = "Reassess the changed or unavailable acceptance evidence; retain existing delivery receipts and do not repeat external delivery.";
            changed(current, "completion_invalidated", "task_controller", current.reason);
          } else if (delivery.status === "done") {
            current.state = current.completion_outcome === "partial" ? "partial" : "completed";
            current.execution_recovery = null;
            current.reason = current.state === "partial" ? "Partial delivery recorded; unmet criteria retained" : "All criterion assessments met and final response recorded";
            changed(current, current.state, "task_controller", current.reason);
          } else {
            recordExecutionFailure(current, delivery, "delivery",
              current.completion_control_epoch !== undefined && current.completion_control_epoch !== current.control_epoch);
          }
          if (current.continuation.reservation?.submission_id === delivery.id) current.continuation.reservation = null;
        }, ctx);
      } else {
        if (task.state === "waiting") return;
        await conversation.commit(async tx => {
          const { task: current } = await currentTx(tx);
          if (current.revision !== task.revision || current.state !== "active") return;
          const reservation = current.continuation.reservation;
          if (!reservation) return;
          const record = await tx.submissionByRequest(conversation.id, reservation.request_id);
          if (!["done", "unanswered"].includes(record?.status)) return;
          if (reservation.control_epoch === current.control_epoch) {
            if (record.status === "unanswered") recordExecutionFailure(current, record, "research");
            else {
              current.execution_recovery = null;
              if (reservation.progress_version === current.progress_version) current.continuation.no_progress += 1;
            }
          }
          current.continuation.reservation = null;
          changed(current, "reconcile", "task_controller", current.reason);
        }, ctx);
      }
      task = await getCurrent(ctx);
      if (!["active", "completing"].includes(task.state)) return;
      if (task.execution_recovery?.state === "retrying" && task.execution_recovery.failures > recoveryPolicy.maxRetries) {
        await conversation.commit(async tx => {
          const { task: current } = await currentTx(tx);
          if (current.revision !== task.revision) return;
          current.execution_recovery.state = "attention_required";
          current.execution_recovery.next_retry_at = null;
          changed(current, "recovery_budget", "task_controller", "The configured execution recovery budget is exhausted");
        }, ctx);
        return;
      }
      if (task.execution_recovery && !recoveryReady(task.execution_recovery, task.control_epoch, now(), recoveryPolicy.maxRetries)) {
        clearTimeout(recoveryTimer);
        if (started && task.execution_recovery.state === "retrying" && task.execution_recovery.control_epoch === task.control_epoch) {
          recoveryTimer = setTimeout(schedule, Math.max(1, Math.min(2147483647, Date.parse(task.execution_recovery.next_retry_at) - now())));
          recoveryTimer.unref();
        }
        return;
      }
      const requestId = `task:${task.user_task_id}:continue:${task.continuation.sequence + 1}`;
      try {
        await admission.submitInternal({ requestId, producer: "task_controller", whenBusy: "reject",
          identity: { user_task_id: task.user_task_id, request_id: requestId },
          basis: { control_epoch: task.control_epoch, revision: task.revision, event_inputs: task.event_inputs },
          content: task.state === "completing"
            ? "Recover only the final response for the existing completion proposal. Read the retained evidence if needed and deliver the final explanation. Do not repeat scientific calculations, writes, emails or other external deliveries. The runtime will complete the task after this response is recorded."
            : "Continue the existing authorized user task using the runtime task snapshot. This is an internal continuation, not new user authorization. Work until verified completion, a concrete Job wait, or an explicit blocker. "
            + "User-directed stops must be persisted with task_update action=apply_user_control when consuming the actual user instruction; this internal input is not control authorization. Job cancellation and Node status alone do not stop the task. "
            + (task.continuation.no_progress > 0 ? "Recent runs recorded no new evidence. Reassess the approach and remaining independent work; this count does not establish a research blocker. " : "")
            + (task.execution_recovery ? "The previous execution failed. Inspect existing tool and Job receipts before continuing; do not replay completed or uncertain external actions." : "") }, ctx);
      } catch (error) {
        if (!["busy", "task_superseded", "task_paused", "task_execution_recovery"].includes(error.code)) throw error;
      }
    },
    async snapshot(ctx) { return { task: await settleWait(ctx), automatic_continuation_enabled: enabled }; },
    health: () => ({ automatic_continuation_enabled: enabled, error: lastError, checking: running, last_checked_at: lastCheckedAt, check_interval_ms: intervalMs, recovery_policy: { ...recoveryPolicy } }),
    start() {
      started = true;
      unsubscribe = harness.subscribeCommits(() => schedule());
      timer = setInterval(schedule, intervalMs); timer.unref(); schedule();
    },
    async close() { stopped = true; clearInterval(timer); clearTimeout(recoveryTimer); unsubscribe?.(); while (running) await new Promise(resolve => setTimeout(resolve, 5)); },
  };
  function recordExecutionFailure(task, record, phase, superseded = false) {
    const previous = task.execution_recovery;
    if (previous?.submission_id === record.id) return;
    const failures = (previous?.control_epoch === task.control_epoch ? previous.failures : 0) + 1;
    const retry = !superseded && retryableSubmission(record) && failures <= recoveryPolicy.maxRetries;
    const delay = Math.min(recoveryPolicy.maxDelayMs, recoveryPolicy.baseDelayMs * 2 ** Math.min(failures - 1, 30));
    task.execution_recovery = { state: retry ? "retrying" : "attention_required", phase, failures,
      submission_id: record.id, control_epoch: task.control_epoch,
      reason: record.reason || "execution_failed", detail: record.detail || null,
      next_retry_at: retry ? new Date(now() + delay).toISOString() : null };
    changed(task, "execution_failure", "task_controller", retry
      ? "Execution failed; bounded recovery is scheduled" : "Execution needs attention; research has not been marked blocked");
  }
  function schedule() {
    if (!started || stopped || scheduled || running) return;
    scheduled = true;
    setImmediate(async () => {
      scheduled = false;
      if (stopped || running) return;
      running = true;
      try { lastError = null; await controller.reconcile(); }
      catch (error) { lastError = { code: error.code || "task_reconcile_failed", message: error.message }; }
      finally { running = false; lastCheckedAt = stamp(); }
    });
  }
  return controller;
}
