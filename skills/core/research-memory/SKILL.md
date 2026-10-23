---
name: research-memory
description: Preserve research questions, attempts, evidence, relations, and immutable conclusions so work can resume with context.
---

# Research memory

[Chinese version](SKILL.zh-CN.md)

Use this Skill to keep a scientific study coherent across turns. Nodes hold questions and their current plan; notes retain observations, decisions and changes of direction; Results fix conclusions worth citing. Jobs and Artifacts preserve execution evidence. The runtime supplies a `research-brief/1` projection with recent notes and source references; read the original records when details matter.

## Core operations

- `research_read {}` restores the current workspace overview; use a returned `ref` to read a Node, Result, or record.
- `research_search {query}` finds prior work with the declared filters and paging fields.
- `research_create {goal}` opens a persistent question with optional title, plan, relations, and source bindings. Put hypotheses and the investigation approach in `plan`.
- `research_update {node_id, note}` records observations, plans, status, relations, or an assessment reference.
- `research_result {node_id, conclusion}` publishes an immutable conclusion with observations, limitations, evidence references, and files.

Restore the current task and read or search for the relevant existing question before creating a Node. Keep preparation, calculations, validation, retries, parameter changes and changes of platform within that question. Create a Node only when a new research objective needs its own continuing investigation and judgment; a separately useful Result does not require a new Node. Connect a new question with the appropriate `requires`, `part_of`, or `alternative_to` relation. The first Node can supply an initial task binding; later creations do not automatically become task entries or focus. Maintain those navigation lists explicitly with `task_update action=set_research` using actual returned IDs.

## Evidence loop

After collecting a Job, inspect its output and choose the appropriate record: use a `research_update` note for an observation, decision or revised approach; use `research_result` for a conclusion worth fixing and citing. One finding need not be copied into both tools or repeated as task progress. A completed Job does not require a Result. Published conclusions cite immutable Artifacts or Results rather than mutable work files. Keep measured observations, authored conclusions, and check references distinct. Negative or inconclusive results are valid research records.

The latest Result is not automatically the Node's current assessment. Use `as_assessment=true` only when the new conclusion represents that judgment. Publication and selection then commit together; a stale read saves neither. Reread the Node and reconsider before retrying. Ordinary publication leaves the selected assessment unchanged.

A review projection is a navigation aid: its `state_digest` and `brief_digest` identify the state it saw, while the cited Nodes, notes, Results, Jobs, and Artifacts remain authoritative. Brief note excerpts and counts help recover the process; they do not publish conclusions or select an assessment. Follow pagination for long fields and reread before replacing a field after a revision conflict. Use [storage and recovery](references/storage.md) for workspace paths, revisions, and immutable files, [planning](references/planning.md) for decomposition, and [research workflow](../research-workflow/SKILL.md) for task control and Job policy.

## Working pattern

1. Restore the review and current task.
2. Read the relevant existing Node, recent notes and evidence references; search before opening another question.
3. Choose the next calculation or analysis in the domain Skill.
4. Record a useful observation or decision as a note, or publish a reusable conclusion as a Result. Revise the current plan when the approach changes.
5. Update task navigation, next action or waiting state when needed, preserving competing explanations and unresolved questions.

When publishing a Result, use `observation` for findings, `conclusion` for interpretation, and `evidence_refs` for source records. When resuming work, follow those references to review the evidence behind the conclusion.

Before publishing or correcting a conclusion, or choosing input and supporting references, read [evidence and conclusions](references/evidence.md).
