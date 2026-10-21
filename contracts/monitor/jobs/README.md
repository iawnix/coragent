# CoRAgent Job Monitor

Monitor owns the durable execution wake outbox under
`operations/monitors/<monitor_id>/`. A `coragent-job-monitor/2` binding fixes the
workspace, Job, owning session, `user_task_id` (a task ID or null), and research Node/revision (both present or both null) at dispatch.
Events use `coragent-job-monitor-event/2`; delivery receipts use
`coragent-job-monitor-delivery/2`.

`next_run` is required on authenticated internal Monitor admission. Host and
Worker reject other modes. Admission checks Pi's active run and inbox in the
same transaction as input submission. Busy sessions keep events pending without
adding a follow-up input. Events for a session form a fixed batch before first
admission; retries reuse the same request ID and members. New events form another
batch. Claims expire after 60 seconds.

Admission, consumption, and scientific analysis are separate facts. Delivery is
acknowledged after durable model-input consumption, or when the same event was
already acknowledged. A lost response or Worker restart recovers the existing
input rather than rotating its identity. A task resumed after a pre-consumption
interruption can inherit the undelivered event in its next canonical continuation;
`successor_consumption` records the consuming submission on the original provenance,
without rewriting the original Pi outcome or changing the fixed event batch.
Provider failures preserve the original
input and remain diagnosable. Monitor never marks scientific results complete.

Admission distinguishes an accepted wake, a deferred wake, and a failed wake.
When the owning Task Controller is waiting for Jobs, admission returns an
accepted pending delivery with `deferred.code = "task_waiting"`; this is an
expected synchronization result, so the Worker keeps the delivery pending and
does not record a Monitor health error. Transport, authentication, observation,
and uncertain Host failures remain retryable errors.

Eligibility depends on the event, workspace/session and user-task binding, delivery
receipt, and the current task control state. It does not read Research Memory versions, Node status, checkpoints or
summaries. Closing a Node and failing a Memory projection cannot hide a Job
failure. The Job worker creates no model turn without an execution event. The
SessionWorker Task Controller can independently continue a registered active user
task through the same admission boundary, even when no Job is running.

User task pause suppresses future automatic input and consumption while observations
continue. Pending event batches keep their stable identities. The current model
request may finish; an explicit reply interruption also pauses automatic work.
An event associated with another user task cannot advance the current task.

Public TUI and Host methods are specified by the [Monitor API](../README.md).
Low-level Job observation and delivery records are internal. Task Controller
owns user pause, resume and cancellation.

The event contains the submitted Node revision. The Agent can read that Node,
inspect or collect Job outputs, and publish its own research interpretation.
Actual input and output provenance remains in Job receipts and Artifact Store.

The current record schemas are [binding](binding.schema.json), [event](event.schema.json)
and [delivery](delivery.schema.json). Unknown fields and invalid record shapes are
rejected. Python validates persisted records using generated copies of these schemas;
Host validates bindings and events before notifying clients, including matching the
workspace, Job, task and session identities.
