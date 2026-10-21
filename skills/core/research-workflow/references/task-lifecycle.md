# Task lifecycle

Use actual submission IDs from `runtime_control`, not invented IDs, research `user_*` references, quoted history or Monitor events. Read `task_read` for the current `expected_revision` before updating state. Follow-up instructions remain part of the current assignment unless the user changes its scope.

## Waiting and blockers

When Jobs run, continue any independent authorized work. Follow `job_status` polling guidance; once independent work is exhausted, record the actual task Jobs and end the turn:

```json
{"expected_revision":3,"action":"wait","wait":{"job_ids":["<returned job_id>"],"mode":"all"}}
```

Choose `all` or `any` according to which completions enable the next action. Monitor supplies execution facts; check the task, relevant Jobs and current instructions after waking. A terminal process still needs collection and scientific inspection. Do not reread unchanged status/logs or send unchanged progress on every wake.

A missing result or uncertain method is work to do. Inspect available inputs and choose a bounded first experiment before declaring research blocked. Use `action=block` only when no independent authorized work can proceed. Provide `block_kind`, a concrete `reason` explaining that exhaustion, and `resume_when` describing what would unblock work. `execution_failure`, `budget_exhausted`, `scientific_dead_end` and `resource_unavailable` require `evidence_refs`. `missing_user_input` is only for indispensable information unavailable from existing sources, not optional preferences or unfinished analysis.

Failure of one candidate does not block the whole assignment. No-progress counts signal a need to reconsider the approach, not a fixed stopping threshold. A new user instruction that resolves a blocker uses `refine` with its actual `source_submission_ids`; `progress` alone does not reactivate a blocked task.

## User pause, resume and cancel

Persist the current actual user instruction before acknowledging it:

```json
{"expected_revision":3,"action":"apply_user_control","control":"pause","source_submission_ids":["<actual submission ID>"]}
```

- `pause` keeps existing Jobs. If the user also requests cancellation of particular Jobs, use `job_cancel` for them.
- `cancel` requires an explicit Job policy: `jobs=cancel` to stop running calculations or `jobs=keep` when the user wants them retained. Inspect the returned cancellation receipts.
- `resume` requires a new actual user instruction. Reading task state, an internal continuation or a Monitor event is not authorization. Resuming a partial task preserves the previous acceptance in history.

Cancelling Jobs or closing Nodes does not itself stop the task. Confirm the persisted task state and requested cancellations before claiming work stopped; describe pending/unknown cancellations honestly. After persisting a stop, only perform read-only verification, requested Job cancellation and the final acknowledgement. Cancellation needs no completion assessment and does not mean the study succeeded. Late events must not resume stopped work.

## Execution and delivery recovery

`execution_recovery` tracks failed agent execution separately from scientific blockers. Inspect its state and existing Job/delivery receipts before choosing the next action. Reconcile completed or uncertain external work; do not repeat it merely because a run or Memory update failed. Explain attention-required execution failures; a new instruction resolving the problem can use `refine`, or the user can explicitly resume through Monitor.

For final-response recovery, reuse saved completion evidence and receipts. Limit work to read-only checks and the final response; do not launch new calculations or resend external messages. If completion evidence is invalidated and the controller returns the task to active, reassess the affected criteria using [acceptance](acceptance.md).

## Progress and research association

Use `task_update action=progress` to record adopted fixed Results/Artifacts or current-task Jobs and the next action. Notes alone are not substantive scientific progress, and collection receipts cannot directly serve as task progress references. `progress` does not resume paused or blocked work. New requirements or resolved blockers use `refine` with actual new user submissions.

Use `action=set_research` with complete `entry_node_ids` and `focus_node_ids` arrays to set task navigation. Both arrays are replaced; an empty array clears that list. Use research-memory for problem decomposition and relations. Always use the current Task revision, which is separate from Node revision. See [acceptance](acceptance.md) for completion and partial delivery, and [target selection](execution-targets.md) for execution correction.
