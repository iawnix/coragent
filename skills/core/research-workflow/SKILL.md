---
name: research-workflow
description: Start or resume sustained research tasks, select execution targets, manage Job waits and user controls, and assess full or partial delivery.
---

# Research workflow

[Chinese version](SKILL.zh-CN.md)

Use this Skill before starting or resuming sustained research, changing its execution destination, waiting, applying user control, or proposing delivery. It owns task state and execution coordination; domain Skills own scientific methods and checks. Ordinary questions need no task.

## Start and resume

1. Check `runtime_control`; use `task_read` to recover an existing task's complete requirements, state and next action. Do so before acting when `continuation_truncated` is true. Context records can be stale and never constitute new authorization.
2. Before `task_begin`, read [Execution target selection](references/execution-targets.md). Register a new assignment only when no nonterminal task exists, with actual user submission IDs, objective and criteria covering every deliverable, `initial_plan`, and the first concrete `next_action`. Preserve user requirements separately from hypotheses and optional diagnostics.
3. Continue the current task for follow-ups. New user requirements use `refine`; a misread execution instruction uses the correction procedure in the execution reference. Reading a task or writing progress does not resume paused or blocked work.
4. Create or select research Nodes and bind entry/focus with `task_update action=set_research`. The first `research_create` supplies an initial binding when none exists. Use the [research-memory Skill](../research-memory/SKILL.md) for records and relations, then select the applicable domain Skill.

## Execute and record

Use [Job and material workflow](references/tools.md) for preparation, submission, collection, evidence references and file placement. Control helpers use `CORAGENT_PYTHON`; scientific preparation uses `CORAGENT_JOB_CONFIG` and inherits the task target. Do not install scientific dependencies in the control environment.

Prepare files in the returned Node `work_dir` or `research/work`; place reports in `reports/`. Associate research Jobs with the intended `node_id`. Inspect original outputs and the domain's scientific checks before publishing conclusions. Keep retries and scan points for one question in its Node; split independently interpretable questions when useful.

Record meaningful changes and the next action through `task_update progress`. Plans, notes and new Nodes are not substantive scientific progress. Check receipts before retrying an uncertain submission. Continue independent work while Jobs run.

## Wait, control and recover

Read [Task lifecycle](references/task-lifecycle.md) when waiting for Jobs, facing a blocker, applying a user pause/resume/cancel, or recovering a failed run. It distinguishes task control from Job control and execution recovery. Respect the returned polling interval; when no independent work remains, record the wait and end the turn for Monitor.

## Assess and deliver

Read [Task acceptance and delivery](references/acceptance.md) before proposing completion. Inspect each current criterion against fixed evidence; full and partial outcomes have different requirements. A report or a failed candidate cannot replace requested work. Use an applicable domain Skill to assemble the requested output. For authorized email delivery, use the [email Skill](../email/SKILL.md) and preserve its receipt.

Use [Skill resources](references/skills.md) to locate installed capabilities and [Public tool contract](references/public_contract.md) for the interface index. Parameters and preconditions come from the callable tool schemas.
