---
name: research-memory
description: Preserve research questions, attempts, evidence, relations, and immutable conclusions so work can resume with context.
---

# Research memory

[Chinese version](SKILL.zh-CN.md)

Use this Skill to keep a scientific study coherent across turns. Nodes hold questions, their current plan and an explicitly selected assessment; notes retain observations, decisions and changes of direction; Results fix conclusions worth citing. Jobs and Artifacts preserve execution evidence. The runtime assembles a deterministic `research-brief/1` projection, prioritizing the selected assessment over recent notes. Keep enough durable state to continue without the old chat history; read original records when details matter.

## Core operations

- `research_read {}` restores the current workspace overview; use a returned `ref` to read a Node, Result, or record.
- `research_search {query}` finds prior work with the declared filters and paging fields.
- `research_create {goal}` opens a persistent question with optional title, plan, relations, and source bindings. Put hypotheses and the investigation approach in `plan`.
- `research_update {node_id, note, references}` records a cited observation. Add `as_assessment:true` to select this new note as the current judgment; optional `plan` changes commit in the same operation.
- `research_result {node_id, conclusion}` publishes an immutable conclusion with observations, limitations, evidence references, and files.

Restore the current task and read or search for the relevant existing question before creating a Node. Keep preparation, calculations, validation, retries, parameter changes and changes of platform within that question. Create a Node only when a new research objective needs its own continuing investigation and judgment; a separately useful Result does not require a new Node. Connect a new question with the appropriate `requires`, `part_of`, or `alternative_to` relation. The first Node can supply an initial task binding; later creations do not automatically become task entries or focus. Maintain those navigation lists explicitly with `task_update action=set_research` using actual returned IDs.

## Evidence loop

After collecting a Job, inspect its output and choose the appropriate record: use a `research_update` note for an observation, decision or revised approach; use `research_result` for a conclusion worth fixing and citing. One finding need not be copied into both tools or repeated as task progress. A completed Job does not require a Result. Published conclusions cite immutable Artifacts or Results rather than mutable work files. Keep measured observations, authored conclusions, and check references distinct. Negative or inconclusive results are valid research records.

Maintain a concise current assessment after interpreting a batch of results, changing direction, or preparing to wait or deliver. State what is established, what remains unresolved, and the limits of the evidence; preserve still-valid counterevidence and alternatives rather than recording only the last Job. Cite exact returned references in `research_update.references`. Read the current Node, then save this note with `as_assessment=true`, optionally revising `plan`. Note, citations, selection and plan commit together; a stale read saves none of them. Reread and reconsider before retrying. A process note without selection leaves the current judgment intact.

The same `as_assessment=true` option on `research_result` publishes and selects a reusable conclusion atomically. Intermediate, negative and inconclusive Results are valid; an entire study need not be finished. The latest note or Result is never selected automatically. Use `assessment_ref` only to select an existing same-Node authored record or Result, and never combine it with `as_assessment=true`. A useful finding needs one appropriate record, not a duplicate progress document.

A Brief is a navigation aid: its `state_digest` and `brief_digest` identify the state it saw, while the cited Nodes, notes, Results, Jobs, and Artifacts remain authoritative. The runtime selects and assembles saved facts without a second model synthesis. A current assessment is included as a complete unit or accompanied by an explicit read requirement; do not infer omitted content. Recent notes supplement the assessment and never replace it by recency. Review new-evidence notices before relying on an older judgment. Follow pagination for long fields and reread before replacing a field after a revision conflict. Use [storage and recovery](references/storage.md) for workspace paths, revisions, and immutable files, [planning](references/planning.md) for decomposition, and [research workflow](../research-workflow/SKILL.md) for task control and Job policy.

## Working pattern

1. Restore the review and current task.
2. Read the relevant existing Node, recent notes and evidence references; search before opening another question.
3. Choose the next calculation or analysis in the domain Skill.
4. Record a useful observation as a note, or publish a reusable conclusion as a Result. Select a concise current assessment at meaningful research boundaries and revise the plan when the approach changes.
5. Maintain the concrete next action in the Task. When waiting, provide the awaited Jobs and the action to take on waking in the same `task_update` call; do not duplicate it in Node plan or a separate progress file.

When publishing a Result, use `observation` for findings, `conclusion` for interpretation, and `evidence_refs` for source records. When resuming work, follow those references to review the evidence behind the conclusion.

Before publishing or correcting a conclusion, or choosing input and supporting references, read [evidence and conclusions](references/evidence.md).
