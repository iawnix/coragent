# Multi-platform task execution

Keep one research Task with multiple work items. Each Job pins one platform and entry; this does not
split a tightly coupled MPI process across unrelated clusters.

When an unbound Task needs calculation, bind its default and explicitly permitted placements with
`task_update action=bind_execution`:

```json
{
  "action": "bind_execution",
  "expected_revision": 1,
  "execution_target": {"platform": "Com30", "scheduler_entry": "qrun"},
  "execution_intent": {"source_submission_id": "1", "source_text": "Use Com30 with Qrun"},
  "execution_policy": {
    "placements": [
      {"target": {"platform": "Com30", "scheduler_entry": "qrun"},
       "intent": {"source_submission_id": "1", "source_text": "Use Com30 with Qrun"}},
      {"target": {"platform": "FEDCluster", "scheduler_entry": "tri"},
       "intent": {"source_submission_id": "1", "source_text": "Use FEDCluster with Tri"}}
    ],
    "max_in_flight": 4,
    "max_attempts": 100
  }
}
```

Use the actual current task revision and exact excerpts present in its user submissions. The default must
be in the allowed placements. Do not invent permission. `task_begin` may receive the same execution fields
when calculation is already intended; ordinary research task creation omits them.

Use task_update action=set_execution_plan with execution_plan.items. Each item requires id, work_id and
resources (cpus and memory_mb); optional fields are target, depends_on and input_artifact_ids. References in
depends_on are item IDs. Reject cycles and unknown dependencies. Omitting target uses the policy default.
Submitted/completed items cannot be changed or removed by a plan revision.
For an unbound task, the first `set_execution_plan` can include the execution target, intent and policy to
bind them atomically with the plan; omitting them resolves the configured default under the task's user
constraints. A failed plan leaves the task unbound. A bound task's plan uses its existing policy; change
that policy with `refine` and a new user source before creating a plan. An existing plan pins its policy.

Select a ready item with task_update action=select_execution_item and execution_item_id. Preparation bash
receives its trusted CORAGENT_TASK_EXECUTION context; ordinary commands still run locally. Prepare with the
item's work identity, input artifacts and resources. Submit the returned request unchanged. Runtime enforces
the context, task/entry in-flight limits and attempt budget. An unknown Job still occupies a slot.

Use task_read execution_progress for ready/blocked items and their Job states. Dispatch independent ready
items within the budget; wait through the existing task workflow when all remaining work is blocked on Jobs.
Never resubmit an uncertain item with a fresh request ID; use job_reconcile on its existing Job.

After successful execution, collect outputs and publish a scientific validation Result. Complete the item with
task_update action=complete_execution_item, execution_item_id, artifact_ids and evidence_refs including that
Result. Only artifacts from its collected Job can be handed off. Downstream context requires these artifacts
as inputs; the preparer stages their verified payloads at inputs/artifacts/<artifact_id>/payload.
Validation Results must cite every handoff Artifact in inputs or evidence_refs. Collection/transfer failure
requires recollection, not another scientific execution. Native exit success alone does not release dependencies.

Pause stops new dispatch; cancellation distinguishes retaining Jobs from requesting their cancellation.
Preserve submitted work and evidence in plan revisions. Deliberate recalculation uses a new item and work_id;
identical computation also requires the existing job_start repeat predecessor/reason/budget contract.

For optional automatic placement set execution_policy.automatic_placement=true. An item supplies backend
and candidates instead of target. Every candidate must belong to the pinned policy. Selection requires
known sufficient free CPU/memory and a configured backend, excludes paused/stale observations, and accounts
for earlier allocations in the same plan. It records a placement_reason; preparation still verifies software.
Unknown capacity (including GPU and current non-Qrun handlers) cannot justify automatic placement.
Use explicit placement for those entries. max_in_flight limits admission in the workspace; the underlying
scheduler/Qrun pool controls shared capacity across workspaces.
