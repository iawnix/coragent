---
name: execution-platforms
description: Select named local or SSH computation platforms, scheduler entries, software environments and storage; inspect resources and coordinate multi-platform task placement and artifact handoffs.
---

# Execution platforms

Use `job_platforms` to discover configured platforms and scheduler entries. A platform owns transport,
common software bindings and storage; an entry chooses the executor. `local`/`ssh` describes submission
connectivity, independently of `tri`, `qrun`, `pbs`, `torque`, `slurm` or `external`.

Select with `execution_target: {"platform":"Com30","scheduler_entry":"qrun"}`. There is no separately
configured `com30_qrun` label. Omit the entry only to use that platform's default. `job_resolve_target`
is the runtime authority for matching names and aliases; ambiguous or unavailable entries must be resolved
before submission. A busy platform does not authorize moving data or computation elsewhere.

An ordinary research Task has no calculation destination. When calculation is needed, read `task_read`:
if `execution_selection` is null, call `task_update` with the current `expected_revision`,
`action="bind_execution"`, and the intended `execution_target`. Omit the target only to resolve the
configured default under the task's original user constraints. Preserve explicit scheduler instructions
with `execution_intent` quoting an actual task source. `task_begin` can bind immediately when these fields
are supplied; a first `set_execution_plan` can bind and create its plan together. Preparation and `job_start`
require this persisted binding. Subsequent destination changes use `refine` with a new user source;
`correct_execution` uses the original explicit instruction and a reason to correct a misreading.

`job_resources` observes capacity and usage where the scheduler supplies them. Unknown values are not zero;
snapshots do not guarantee admission. `job_probe` checks infrastructure, not scientific software. Use the
software environment checker before preparation and a real check Job when compute-node readiness matters.

Ordinary bash stays on the controller. Prepare a scientific Job with
`"$CORAGENT_PYTHON" -m research_agent.application.executors --config "$CORAGENT_JOB_CONFIG" --platform Com30 --scheduler-entry qrun ...`.
Select the scientific recipe with `--executor` or the script's software binding with `--backend`;
these do not select the queue adapter. Submit the returned request file and digest unchanged with `job_start`.
An unbound Task does not block ordinary bash or platform diagnostics. Existing Jobs keep their recorded
routes for status, cancellation and collection after platform configuration changes.

For platform setup and inherited environment/storage configuration, read [configuration](references/configuration.md).
For a task distributed across platforms, read [execution plans](references/plans.md) before creating its policy.
Use [batch-schedulers](../batch-schedulers/SKILL.md) for native queue behavior. Installation and service ownership
belong to the main installer and ordinary operations documentation.
