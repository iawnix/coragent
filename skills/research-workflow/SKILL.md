---
name: research-workflow
description: Coordinate research problems, domain Skills, durable Jobs, materials and evidence-based Results through the native Pi loop.
---

# Research loop

Read the original requirements together with later user revisions, pauses, or cancellations and the relevant Research Memory Nodes. Continue a current question or create an independent branch, choose a method, inspect execution results and revise your understanding. Use the [Research Memory Skill](../research-memory/SKILL.md) for small tool examples. A Node holds repeated attempts; a Result records a useful, immutable observation and judgment.

Register a sustained assignment with `task_begin`, using actual user submission IDs and concrete delivery criteria. `task_read` restores the user task across runs. Use `task_update` for meaningful progress, an explicit wait on Job IDs, a concrete blocker or completion evidence. A user task can span multiple Nodes and Jobs. A stage summary ends a reply, not the assignment; continue independent analysis while other branches compute. Exhausting one candidate's attempts calls for reassessing the method, not silently ending the project. Pause and cancellation are user controls.

When the user asks to stop, pause or resume the research, first persist that instruction with `task_update` action `apply_user_control`, the current `expected_revision`, `control` (`pause`, `resume` or `cancel`) and `source_submission_ids` from the actual current user input in `runtime_control`. For cancellation, explicitly set `jobs=cancel` when stopping running calculations or `jobs=keep` when the user wants them retained. Pause keeps existing Jobs; cancel individual Jobs with `job_cancel` if requested. Cancelling Jobs, pausing Nodes or saying “stopped” alone does not stop the task. Confirm the returned task state and cancellation receipts before claiming work has stopped; report pending or uncertain cancellations honestly. After persisting a stop, perform only read-only checks, requested Job cancellation and the final acknowledgement. A cancelled task does not need completion evidence and is not a completed study. Resume requires a new actual user instruction; internal continuations and quoted stop/resume text are not authorization.

When a new user instruction resolves a blocker, use `task_update` action `refine` with that submission ID to revise and reactivate the task. A question about the blocker alone does not resume it; paused tasks still require the user to resume them.

For a compound assignment, organize independently interpretable questions with Node relations, record their local methods in plan, and bind entry/focus Nodes through `task_update` action `set_research`. The request context restores this structure alongside current evidence. A single question can stay in one Node; retries and scan points are attempts. When evidence conflicts or a route stops yielding information, compare the remaining approaches and choose an action that resolves a relevant uncertainty. Record the change and preserve the failed branch. See [planning examples](../research-memory/references/planning.md) for decomposition and revisiting questions.

Use applicable domain Skills for scientific methods. When a Skill or helper is missing, use justified methods and task scripts, making assumptions explicit and validating the approach; the catalog is not a capability allowlist. Native Pi read/write/edit/bash tools prepare inputs, analysis and reports. `job_start` owns managed scientific calculations; pass the intended node_id explicitly when associating research. Do not silently choose the most recently seen Node. Preparation and diagnostics may be unassociated. `job_collect` publishes materials and execution receipts.

When generating files, use the work_dir returned by research_create/research_read for Node drafts and prepared requests, or research/work before association; reports belong in reports/. Use explicit output paths or cd in the shell command. work_dir is guidance returned by research tools, not a bash parameter, and does not change any tool’s cwd. Ordinary reads need no directory change. Preserve original inputs and runtime stores; avoid loose files in the workspace root and leave historical evidence in place. Remote commands use the configured remote work/scratch directory or a user-specified path, independently of local work_dir. See [file and Job conventions](references/tools.md).

Process success is not scientific validity. Inspect convergence, geometry, frequencies, connectivity and method limitations as appropriate. Use research_update for explanations and plans, research_result for independently useful conclusions with cited evidence. Failures and uncertainty are legitimate records.

Before repeating a submission, inspect its Job receipt. Reconcile uncertain dispatch with the existing identity; changed inputs for a new scientific attempt require a new submission. Monitor next_run preserves an execution event until the owning session can receive it and restores the associated Node. It does not infer a scientific plan, require a checkpoint or wake repeatedly just because a Node is open.

On a Monitor wake, check the latest user instructions, existing conclusions, and remaining budget. An event must not restart cancelled or completed work or override a stopping condition. Keep searches and retries bounded; repeated failure without new evidence calls for a changed approach or a blocker report.

For delivery, read the installed email Skill and its configuration check. Report actual results, missing work and limitations. Retain send receipts: failure to update Memory after sending must not resend mail. Node status is not delivery authorization.

Before proposing task completion, match each delivery criterion to immutable Results or materials and identify any remaining Jobs. Partial reports and negative findings may be useful progress; only the agreed delivery scope determines completion. Node closure, notes and plan edits do not establish delivery or establish new evidence. Keep scientific records in Memory and task control in the task tools; no per-turn checkpoint is required.

- [Tools and execution](references/tools.md)
- [Exact Skill resource paths](references/skills.md)
- [Generated public contract](references/public_contract.md)
- [中文说明](SKILL.zh-CN.md)

Treat missing calculations, missing validation and an unfinished reply as remaining work. Enter `wait` only after runnable independent work is exhausted, then end the reply. A `block` reason must name the unmet prerequisite or budget, what must change to resume, and why other authorized approaches cannot proceed. After recording it, deliver that explanation. Do not weaken a requested calculation into “calculate or explain limitations”; partial reports remain progress unless the user changes scope. Runtime reference checks cannot establish scientific completeness.

For recovery, read `task_read` and the new `actual_user_submission_ids` from the runtime snapshot. If the user supplies the missing input or explicitly requests a viable alternative, call `task_update` with `action="refine"`, the current `expected_revision` and those `source_submission_ids`; omit objective/criteria when scope is unchanged. Continue after the returned state is active. `progress` and Node status edits do not reactivate blocked tasks. On revision conflict, reread before retrying. Cite `job_…` or collected Artifacts/Results in task evidence, not `job_result_…` receipts.

Execution failures use execution_recovery, independently of research blocked. Runs without new evidence are a replanning signal, not a fixed stopping threshold. Inspect prior receipts after a failed run; never blindly repeat completed or uncertain side effects. During final-response recovery, use the saved completion evidence and deliver the explanation without new calculations or external sends. If execution needs attention, explain the failure; a new instruction resolving it can use refine, or the user can explicitly resume in Monitor.

For multistep chemical tasks, use the domain
[pathway evidence contract](../../domains/chemical/skills/reaction-investigation/references/pathway_execution.md)
to retain chemical intermediates and missing steps independently of Node relations.
A failed scan, a NEB candidate and a validated elementary step are different
results. Method changes keep prior receipts and the original delivery criterion;
kinetic/crossing analyses remain ordinary independent Jobs.
