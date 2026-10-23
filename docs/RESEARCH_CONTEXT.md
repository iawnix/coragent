# Research Context

Research Memory holds durable research records. Research Context prepares model
context through the single `research_read(view="brief")` interface, which returns
`research-brief/1`. The program selects and excerpts recorded facts. An optional
Research Synthesis adds a model summary; neither projection certifies scientific
validity or writes a new assessment.

Research records, workspace management, and context preparation remain parts of
the research core. Preparing a Brief combines local records and saved Job
observations. It does not resolve computing platforms or contact schedulers.
Job Manager refreshes external state; local event projection connects those
durable observations to research records.

## What a resumed model receives

A Node retains the research question in `goal`, the current investigation approach
in `plan`, and an explicitly selected current assessment in `assessment_ref`.
Node version 2 has no `proposal` or `progress` field. Ordinary notes capture
attempts, observations, and next steps without requiring a second progress copy.
Results remain immutable publications. Declared relations and index views remain
available for navigation and reuse.

The Brief presents the current question, explicit assessment, recent process notes,
and Jobs needing attention as separate findings. A note has `kind="note"` and
`selected_assessment=false` unless an explicit `assessment_ref` selects it. Other
selected historical records retain `kind="record"`; a published Result retains
`kind="result"`. A new note or completed Job does not automatically become a
Result, change an assessment, or establish scientific correctness.

Each scoped Node contributes up to three recent process notes, ordered by immutable
record sequence, newest first. An older note explicitly selected as the assessment
may appear separately and also counts toward note coverage. Excerpts and references
share the Brief's byte budget. `content_omitted`, `coverage.notes`, and
`coverage.omitted.notes` distinguish
visible detail from omitted history. Exact references remain usable with
`research_read(ref=...)`; `research_search(node_id=..., kind="note", limit=...,
offset=...)` provides complete paginated history and its total count.

Citations come from actual record identities and explicit reference fields.
Reference-shaped text inside a note does not create a citation. Notes are process
records, including when their wording expresses confidence or a tentative result.

## Selection and refresh

Selection starts with Task focus, authenticated event Nodes, waited Job Nodes, and
Task entries. It includes direct `part_of`, `requires`, `alternative_to`, and
selected-assessment citation relations. An unbound session receives at most one
recent Node created by that session as a navigation hint.

`GenerationTask.prepareContext` performs a local deterministic read for each
generation. Python selects facts without asking a model what to retrieve. The
scope includes task identity, requirements revision, entries, focus, user sources,
and waited Jobs. The state digest includes scoped Nodes, Results, relations,
diagnostics, Job observations, all scoped ordinary-note identities and sequences,
and the content digests of their three most recent notes. Older note bodies are
not loaded merely to compute this digest.

Appending an ordinary note in the selected scope refreshes the Brief even when
the Node revision does not change. Notes on unrelated Nodes do not change an
explicitly scoped digest. Scoped candidates omitted by the display budget still
participate in refresh decisions. The next generation appends new `pi.context`
only when scope or relevant facts change; identical facts are not reinjected.

Pi memo pins prepared context to the generation boundary. Recovery reuses that
prepared value. Compaction summarizes selected historical context and does not
insert today's research state into an earlier summary. Read failures produce an
explicit unavailable state; a new input can retry.

## Independent status and input budgets

- `availability` states whether research background is available.
- `projection_status` is `complete` or `incomplete` for synchronization of durable
  execution events into research records.
- `synthesis_status` is `not_requested`, `ready`, or `failed` for optional model
  synthesis.

Task continuation, Brief refresh, and synthesis success are independent. Results,
terminal or exceptional Jobs, and contradictions may request a tool-free model
synthesis of the selected Brief. It uses only supplied references, is cached by
the Brief digest, and never writes Research Memory. Incomplete projection skips
synthesis. Synthesis failure leaves the deterministic Brief available.

Research background targets 2,000 tokens, or 4,000 when contradictions need more
space. The complete request still includes conversation history, tool results,
compaction, and recent inputs. Its input limit is the smaller of
`contextWindow - reserveTokens` and an optional `maxInputTokens`. Pi may perform
one blocking compaction before a request; a request that still exceeds its budget
is not sent. `/usage` exposes request estimates.

Only `view="brief"` and `research-brief/1` define this read contract. Caller-chosen
refresh triggers and the former `view="review"` are not accepted. The Task context
pointer records the version actually injected; it does not claim scientific review.
