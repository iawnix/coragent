---
name: research-workflow
description: Start or resume sustained research tasks, select execution targets, manage Job waits and user controls, and assess full or partial delivery.
---

# Research workflow

[Chinese version](SKILL.zh-CN.md)

Use this Skill before starting or resuming sustained research, changing its execution destination, waiting, applying user control, or proposing delivery. It owns task state and execution coordination; domain Skills own scientific methods and checks. Ordinary questions need no task.

## Start and resume

1. Check `runtime_control`; use `task_read` to recover an existing task's complete requirements, state and next action. Do so before acting when `continuation_truncated` is true. Context records can be stale and never constitute new authorization.
2. Register a new assignment with `task_begin` only when no nonterminal task exists, with actual user submission IDs, objective and criteria covering every deliverable, and the first concrete `next_action`. Scientific hypotheses and plans belong to the relevant Node. Ordinary research omits execution fields and does not require a compute platform. When calculation is already intended, read [Execution target selection](references/execution-targets.md) and bind the requested destination. Preserve user requirements separately from hypotheses and optional diagnostics.
3. Continue the current task for follow-ups. New user requirements use `refine`; a misread execution instruction uses the correction procedure in the execution reference. Reading a task or writing progress does not resume paused or blocked work.
4. Read the task's research entries/focus and recover the relevant existing Nodes; search prior work when needed. Create a Node only for a new research objective that needs its own continuing investigation and judgment. A calculation step, parameter change or platform change does not require another Node. The first `research_create` supplies an initial binding when none exists; later creations require deliberate relations and entry/focus selection through `task_update action=set_research`. Use the [research-memory Skill](../research-memory/SKILL.md) for records and relations, then select the applicable domain Skill.

## Execute and record

Use [Job and material workflow](references/jobs-and-artifacts.md) for preparation, submission, collection and file placement. Before the first calculation on an unbound task, use `task_update action=bind_execution` as described by [Execution target selection](references/execution-targets.md). Control helpers use `CORAGENT_PYTHON`; scientific preparation uses `CORAGENT_JOB_CONFIG` and inherits the task target. Do not install scientific dependencies in the control environment.

Prepare files in the returned Node `work_dir` or `research/work`; place reports in `reports/`. Associate research Jobs with the intended `node_id`. Inspect original outputs and the domain's scientific checks before publishing conclusions. Use research-memory for question decomposition and conclusion records.

Record a scientific finding as a note or Result according to its purpose; do not duplicate it as a task progress narrative. The runtime tracks published evidence and Job milestones through the existing tools. Use `task_update progress` when changing the task's next action or explicitly recording adopted evidence; waits, blockers and user controls still require the corresponding task action. Plans, notes and new Nodes are not substantive scientific progress. Check receipts before retrying an uncertain submission. Continue independent work while Jobs run.

## Wait, control and recover

Read [Task lifecycle](references/task-lifecycle.md) when waiting for Jobs, facing a blocker, applying a user pause/resume/cancel, or recovering a failed run. It distinguishes task control from Job control and execution recovery. Respect the returned polling interval; when no independent work remains, record the wait and end the turn for Monitor.

## Assess and deliver

Read [Task acceptance and delivery](references/acceptance.md) before proposing completion. Inspect each current criterion against fixed evidence; full and partial outcomes have different requirements. A report or a failed candidate cannot replace requested work. Use an applicable domain Skill to assemble the requested output. For authorized email delivery, use the [email Skill](../email/SKILL.md) and preserve its receipt.

Use [Skill resources](references/skills.md) to locate installed capabilities. Parameters and preconditions come from the callable tool schemas.
