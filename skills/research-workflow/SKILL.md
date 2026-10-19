---
name: research-workflow
description: Coordinate tasks, research Nodes, scientific Jobs, materials, evidence, and delivery through the native research loop.
---

# Research workflow

[Chinese version](SKILL.zh-CN.md)

Use this Skill to run a sustained research assignment. It connects user requirements, Research Memory, domain Skills, managed Jobs, evidence inspection, and final delivery. The domain Skill owns scientific method; this Skill owns task state, execution lifecycle, and durable progress.

## Start and resume

1. Check `runtime_control` and the `research-review/1` context; use `task_read` to recover an existing task's requirements and state.
2. Use `task_begin` only for a new assignment when no nonterminal task exists, with actual user submission IDs, an objective and criteria covering every deliverable, `initial_plan`, and `next_action`. Follow-ups continue the current task; update new user requirements through `task_update action=refine`. Reading a task does not resume paused or blocked work: pause requires explicit user resume, and a resolved blocker requires `refine` with a new user instruction.
3. Create or select Nodes with `research_create`, then bind entry/focus Nodes with `task_update action=set_research`.
4. Read the relevant domain Skill and choose the next discriminating operation.

Use `task_update` for meaningful progress, an explicit wait, a concrete blocker, completion evidence, or a user pause/resume/cancel. User controls are persisted with `action=apply_user_control`, the current `expected_revision`, the actual `source_submission_ids`, and `control`. For cancellation, set `jobs=cancel` or `jobs=keep` according to the user's intent and inspect returned cancellation receipts.

## Execute and record

Prepare files under the returned research `work_dir` or `research/work`; reports go in `reports/`. Start managed scientific calculations with `job_start`, passing the intended `node_id`; collect outputs with `job_collect`. Preparation and diagnostics may be unassociated. Inspect convergence, geometry, frequencies, connectivity, and method metadata before writing `research_update` or `research_result`.

Keep a question's retries and scan points in its Node. When a route stops yielding information, record the failure mode and change the method, seed, endpoint, or hypothesis. Check the existing receipt before repeating a submission; an uncertain dispatch is reconciled through its identity and receipt.

## Delivery loop

Match every delivery criterion to immutable Results or Materials, identify remaining Jobs, and use the report/domain Skill to assemble the requested output. Partial and negative results are useful progress; completion follows the agreed scope and evidence. For email delivery, use the [email Skill](../email/SKILL.md), prepare the message, and retain its send receipt.

Read [Tools and execution](references/tools.md) for Job commands and file conventions, [Exact Skill resource paths](references/skills.md) for domain routing, and [Generated public contract](references/public_contract.md) for the callable interface. For multistep chemistry, use the [pathway evidence contract](../../domains/chemical/skills/reaction-investigation/references/pathway_execution.md).
