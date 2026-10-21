import { timingSafeEqual } from "node:crypto";

export const JOB_ADMISSION_SERVICE_ID = "coragent.job-admission";
const fail = (code, message) => Object.assign(new Error(`${code}: ${message}`), { code });

/** Assess durable delivery identity outside Pi commits. Only authenticated producers reach admission. */
export function createJobAdmission({ admission, kernel, sessionId, wakeMessage, producerToken, taskController }) {
  if (!taskController || !["prepareJobEvents", "validateConsumption", "assertExecutionAllowed", "completeJobEventConsumption"]
    .every(name => typeof taskController[name] === "function")) {
    throw new TypeError("Job event admission requires Task Controller policy");
  }
  function authenticate(token) {
    const expected = Buffer.from(producerToken || "");
    const actual = Buffer.from(typeof token === "string" ? token : "");
    if (!expected.length || actual.length !== expected.length || !timingSafeEqual(actual, expected)) {
      throw fail("internal_producer_required", "Internal admission requires the supervised producer identity");
    }
  }
  const assess = async id => {
    const result = await kernel.execute_command("job_manager_assess", { event_id: id, session_id: sessionId });
    if (typeof result?.admitted !== "boolean" || !result.delivery_token) {
      throw fail("invalid_job_event_assessment", "Invalid Job Manager assessment");
    }
    return result;
  };
  function eventIdentity(ids) {
    if (!Array.isArray(ids) || !ids.length || ids.length > 256 || ids.some(id => typeof id !== "string" || !/^event_[1-9][0-9]*$/u.test(id))) {
      throw fail("invalid_job_events", "Job Manager input requires structured eventIds");
    }
    return { event_ids: [...new Set(ids)].sort() };
  }
  const response = async action => {
    try { return await action(); }
    catch (error) { return { accepted: false, error: { code: error.code || "internal_admission_failed", message: error.message } }; }
  };
  const accepted = record => ({ accepted: true, operation_id: String(record.id) });
  async function jobEventResult(record, identity, context) {
    const origin = await admission.origin(record, context);
    if (origin?.consumption || origin?.successor_consumption) return { ...accepted(record), consumed: true };
    if (record.status === "unanswered") {
      const prepared = await taskController.prepareJobEvents(await Promise.all(identity.event_ids.map(assess)), context);
      if (prepared.deferred) return { ...accepted(record), pending: true, deferred: prepared.deferred };
      if (!prepared.events.length) return { accepted: true, skipped: true };
      return { ...accepted(record), pending: true };
    }
    return { ...accepted(record), pending: true };
  }
  return {
    admit: ({ requestId, eventIds, token, mode }, context) => response(async () => {
      authenticate(token);
      if (mode !== "next_run") throw fail("invalid_job_event_mode", "Job Manager admission requires mode=next_run");
      const identity = eventIdentity(eventIds);
      const existing = await admission.recoverInternal(requestId, "job_manager", identity, context);
      if (existing) return jobEventResult(existing, identity, context);
      const events = await Promise.all(identity.event_ids.map(assess));
      if (events.some(event => !event.obsolete && !event.admitted)) {
        return { accepted: false, pending: true, assessments: events,
          error: { code: "job_events_paused", message: "Automatic delivery is paused; events remain pending" } };
      }
      const prepared = await taskController.prepareJobEvents(events.filter(event => event.admitted), context);
      if (prepared.deferred) return { accepted: true, pending: true, deferred: prepared.deferred };
      const active = prepared.events;
      if (!active.length) return { accepted: true, skipped: true };
      const basis = { events: Object.fromEntries(events.map(event => [event.event_id, event.delivery_token])),
        task_owners: active.map(event => event.event.user_task_id ?? null), ...prepared.basis };
      await admission.submitInternal({ requestId, producer: "job_manager", identity, basis,
        content: active.map(event => wakeMessage(event.event)).join("\n\n"), whenBusy: "reject" }, context);
      return jobEventResult(await admission.status(requestId, context), identity, context);
    }),
    // Called before first model consumption. The evidence belongs to the
    // submission and survives generation-task changes and Worker recovery.
    async validateConsumption(record, origin, api, context) {
      if (origin.consumption) {
        await taskController.assertExecutionAllowed(record, origin, context);
        await taskController.completeJobEventConsumption(record, context);
        return;
      }
      let basis;
      if (origin.producer === "job_manager") {
        const events = await Promise.all(origin.identity.event_ids.map(assess));
        const active = events.filter(event => !event.obsolete);
        if (active.some(event => !event.admitted)) throw fail("job_events_paused", "Automatic event delivery was paused");
        if (!active.length) {
          throw fail("job_event_superseded", "Job Manager input is no longer eligible in the delivery outbox");
        }
        basis = Object.fromEntries(events.map(event => [event.event_id, event.delivery_token]));
      } else { throw fail("invalid_producer", "This route accepts only Job Manager inputs"); }
      await taskController.validateConsumption(record, origin, context, basis);
      await taskController.completeJobEventConsumption(record, context);
    },
  };
}
