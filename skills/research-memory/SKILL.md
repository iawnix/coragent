---
name: research-memory
description: Preserve research questions, attempts, evidence, relations, and immutable conclusions so work can resume with context.
---

# Research memory

## Script routing

Use the [script routing map](../../docs/skill-script-routing.md#research-memory) before invoking a bundled script. It identifies the supported entrypoint and interface; helper files under `scripts/` are not standalone commands. Do not inspect source code to discover invocation details.

**Entrypoint:** none bundled; use the documented runtime or generic Job route.

[Chinese version](SKILL.zh-CN.md)

Use this Skill to keep a scientific study coherent across turns. Nodes hold questions and hypotheses, Jobs and Artifacts hold execution evidence, and Results hold durable interpretations. The runtime supplies a `research-review/1` projection; read the referenced source records when details matter.

## Core operations

- `research_read {}` restores the current workspace overview; use a returned `ref` to read a Node, Result, or record.
- `research_search {query}` finds prior work with the declared filters and paging fields.
- `research_create {goal}` opens a persistent question with optional title, proposal, plan, relations, and source bindings.
- `research_update {node_id, note}` records observations, plans, status, relations, or an assessment reference.
- `research_result {node_id, conclusion}` publishes an immutable conclusion with observations, limitations, evidence references, and files.

Keep a question, its retries, and parameter changes in one Node. Create a related Node for an independently interpretable branch and connect it with `requires`, `part_of`, or `alternative_to`. Associate entry/focus Nodes with the current task through `task_update action=set_research` using actual returned IDs.

## Evidence loop

After collecting a Job, inspect its output, then write the scientific observation with `research_update`. Publish a Result when the observation is useful independently; cite immutable Artifacts or Results rather than mutable work files. Keep measured observations, authored conclusions, and check references separate. Negative or inconclusive results are valid research records.

A review projection is a navigation aid: its `state_digest` and `review_digest` identify the state it saw, while the cited Nodes, Results, Jobs, and Artifacts remain authoritative. Follow pagination for long fields and reread before replacing a field after a revision conflict. Use [storage and recovery](references/storage.md) for workspace paths, revisions, and immutable files, [planning](references/planning.md) for decomposition, and [research workflow](../research-workflow/SKILL.md) for task control and Job policy.

## Working pattern

1. Restore the review and current task.
2. Read the focused Node and its evidence references.
3. Choose the next calculation or analysis in the domain Skill.
4. Record what changed after execution.
5. Publish a Result or revise the plan, preserving competing branches and unresolved questions.

When publishing a Result, use `observation` for findings, `conclusion` for interpretation, and `evidence_refs` for source records. When resuming work, follow those references to review the evidence behind the conclusion.
