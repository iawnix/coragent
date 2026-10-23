# CoRAgent Job Monitor

Monitor owns the durable execution wake outbox under
`operations/monitors/<monitor_id>/`. A `coragent-job-monitor/2` binding fixes the
workspace, Job, owning session, `user_task_id` (a task ID or null), and research Node/revision (both present or both null) at dispatch.
Events use `coragent-job-monitor-event/2`; delivery receipts use
`coragent-job-monitor-delivery/2`.

Job observation and outbox delivery run independently. Observation uses recorded
Job routes, interleaves workspaces, and allows four concurrent queries globally
with one per named platform, across its scheduler entries. Each Job observation
shares a 30-second budget across its subprocess commands; the Node supervisor
also applies a 35-second CLI timeout. Timeout or cancellation stops the local
query process group, and the supervisor waits for Python to exit before releasing
the query slot. An observation timeout preserves the last recorded Job state and
reports a health error. It does not cancel the scientific Job. Stopping local SSH
does not establish that every remote query process has exited.

`next_run` is required on authenticated internal Monitor admission. Host and
Worker reject other modes. Admission checks Pi's active run and inbox in the
same transaction as input submission. Busy sessions keep events pending without
adding a follow-up input. Events for a session form fixed batches of at most 256
events before first admission; [limits.json](limits.json) is the shared limit
source for batching, Host/Worker admission and research context. Retries reuse
the same request ID and members. New events form another batch. Each delivery
pass attempts only the earliest pending batch of each session; later batches
wait for its acknowledgement while other sessions can proceed.

Batch creation, claims and completion use workspace transactions. Redo writes are
retained until all files are durably committed, then replaced by a compact receipt
with request identity, result and digests. A claim returns
the validated events and one token for the batch; completion acknowledges all
claimed members atomically. The delivery worker uses two Python CLI calls per
batch, `claim` and `complete`, instead of per-event calls. Claims expire after
60 seconds. Existing oversized batches retain their identity and fail with
`monitor_batch_too_large`; upgrades do not automatically repartition them.
Maintenance must stop delivery and verify that Pi never accepted the original
request before repairing such a batch. An expired claim or `delivered: false`
alone does not prove that it was never accepted.

Admission, consumption, and scientific analysis are separate facts. Delivery is
acknowledged after durable model-input consumption, or when the same event was
already acknowledged. A lost response or Worker restart recovers the existing
input rather than rotating its identity. A task resumed after a pre-consumption
interruption can inherit the undelivered event in its next canonical continuation;
`successor_consumption` records the consuming submission on the original provenance,
without rewriting the original Pi outcome or changing the fixed event batch.
Consumption evidence and removal from the Task's pending event inputs commit
together, including inherited events and their successor receipts. Retrying an
already consumed request also clears any remaining pending reference.
Provider failures preserve the original
input and remain diagnosable. Monitor never marks scientific results complete.

Admission distinguishes an accepted wake, a deferred wake, and a failed wake.
When the owning Task Controller is waiting for Jobs, admission returns an
accepted pending delivery with `deferred.code = "task_waiting"`; this is an
expected synchronization result, so the Worker keeps the delivery pending and
does not record a Monitor health error. `deferred.code = "task_events_pending"`
likewise waits for an earlier admitted batch to be consumed before admitting new
events. Transport, authentication, observation,
and uncertain Host failures remain retryable errors.

Worker health records `last_successful_observation` and
`last_successful_delivery`, with separate `last_observation_error` and
`last_delivery_error` values. `last_successful_poll` advances after all current
observations succeed; successful event delivery cannot hide a failing query.

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
