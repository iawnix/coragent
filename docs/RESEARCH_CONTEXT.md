# Research Context

Research Memory holds durable research records. Research Context prepares model
context through the single `research_read(view="brief")` interface, which returns
`research-brief/1`. The program deterministically selects recorded facts without
an additional model summary. The projection does not certify scientific validity
or write a new assessment.

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

At a meaningful research boundary, `research_update(note=..., references=[...],
as_assessment=true, plan=...)` can save the note, its evidence references, the
assessment selection, and an updated plan in one transaction. The judgment should
state established findings, unresolved questions, counterevidence, and limitations;
it need not be a final answer. Ordinary notes remain history. `plan` describes the
investigation strategy; Task `next_action` records the next execution action.
`task_update(action="wait", wait=..., next_action=...)` saves the waiting condition
and the action to take after waking together.

The Brief presents the current question, explicit assessment, recent process notes,
and Jobs needing attention as separate findings. A note has `kind="note"` and
`selected_assessment=false` unless an explicit `assessment_ref` selects it. Other
selected historical records retain `kind="record"`; a published Result retains
`kind="result"`. A new note or completed Job does not automatically become a
Result, change an assessment, or establish scientific correctness.

Each scoped Node contributes up to three recent process notes, ordered by immutable
record sequence, newest first. An older note explicitly selected as the assessment
may appear separately and also counts toward note coverage. The selected judgment
has priority over process notes, so adding notes does not displace it merely by age.
Its complete text, limitations, and explicit citations are included together or
marked `content_omitted=true` with an exact read operation. Scientific text is
never shortened to a prefix that could lose a number or qualification. Goal and
plan use `omitted_fields` when their complete text cannot fit. `coverage.notes`
and `coverage.omitted.notes` distinguish visible records from omitted history.
Read an omitted judgment before decisions that depend on it. Exact references remain usable with
`research_read(ref=...)`; `research_search(node_id=..., kind="note", limit=...,
offset=...)` provides complete paginated history and its total count.

Citations come from actual record identities and explicit reference fields.
Reference-shaped text inside a note does not create a citation. Notes are process
records, including when their wording expresses confidence or a tentative result.
A missing selected judgment produces a `current_assessment_missing` cue. A Result
or terminal/collected Job observation recorded after the judgment produces
`new_evidence_after_assessment`, asking the agent to review its relevance. Neither
cue automatically replaces the judgment or invalidates its scientific content.

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

Automatically injected model background omits `brief_id`, `state_digest`,
`brief_digest`, and `read_basis`. Brief identity and version fingerprints remain
in durable runtime metadata for deduplication and recovery after compaction.
Research facts, contradictions, evidence references, and retrieval routes remain
visible to the model. This projection does not change research-tool read receipts.

Pi memo pins prepared context to the generation boundary. Recovery reuses that
prepared value. Compaction summarizes selected historical context and does not
insert today's research state into an earlier summary. Read failures produce an
explicit unavailable state; a new input can retry.

## Independent status and input budgets

- `availability` states whether research background is available.
- `projection_status` is `complete` or `incomplete` for synchronization of durable
  execution events into research records.

Task continuation and Brief refresh are independent. The agent evaluates the
recorded evidence and saves a judgment through the same research tools; context
preparation does not call another model to reinterpret it. Incomplete projection
remains visible and is not hidden by generated prose.

Research background targets 2,000 tokens, or 4,000 when contradictions need more
space. The complete request still includes conversation history, tool results,
compaction, and recent inputs. Its input limit is the smaller of
`contextWindow - max(reserveTokens, maxTokens + 4096)` and an optional
`maxInputTokens`, floored at zero. `maxTokens` is the stream override or model
output maximum. Pi may perform
one blocking compaction before a request; a request that still exceeds its budget
is not sent. `/usage` exposes request estimates.

## Cache diagnostics

Set `CORAGENT_CACHE_DIAGNOSTICS=1` in a new Worker's environment to enable local
diagnostics (off by default). Existing Workers do not change automatically.
`request-cache.jsonl` beside the session's `session.sqlite` rotates at about
8 MiB and retains one previous file. Records never enter model context.

The observer covers `openai-completions` and `openai-responses` HTTP/SSE requests.
Each HTTP attempt has request and response records linked by `request_id` and
`attempt`, with generation ID, authenticated input sources/reasons, compaction
head ID, request gap, and numeric input/cache usage from the raw response.
`not_reported` is distinct from an explicit zero cache count. `completeSimple`
calls, including summaries, use a separate `auxiliary` comparison stream.

Comparison uses the final HTTP JSON message array, with separate comparisons for
tools and top-level instructions. `common_prefix_bytes_lower_bound` measures
matching 1 KiB JSON byte blocks, **not tokens** or guaranteed cache reuse. Keyed
fingerprints remain in process memory; the first comparison after restart is
unknown. No bodies, tool results, URLs, headers, credentials, or raw errors are
logged. Unsupported transports and missing fields remain unknown. Diagnostic
write failures do not prevent inference.

Check compaction, message prefixes, tools, and instructions before attributing
low cache usage to the gateway or upstream. Use synthetic long-context controls
starting near 128k, comparing exact repeats and appended messages; high cache
reuse in a small prompt does not establish long-context behavior.

Run `python3 -B tools/test/cache_probe.py --size-k 128` for the deterministic local
probe. Add `--live --installation /path/to/coragent` to use configured credentials
and incur real model usage (default `CPA/gpt-6-astra`; override with `--provider`
and `--model`). Specify `--pi-runtime` if multiple runtimes are installed.
The probe uses the installed Pi adapter and current context/diagnostic source;
it is not full research Worker acceptance. It sends at most four requests: cold,
exact repeat, appended instruction, and a local echo tool result. Each request
allows 512 output tokens and 120 seconds, with no retries. Size is approximate;
provider usage is authoritative. Synthetic content is generated in memory, with
no research workspace or session reads. Credentials stay in process memory.
Private manifests, diagnostics and reports live under `local_debug/cache-probes/`.
The probe stops on failure or unexpectedly large input. Larger 256/512 scales
must be selected explicitly; ordinary test suites never run live probes.

Only `view="brief"` and `research-brief/1` define this read contract. Caller-chosen
refresh triggers and the former `view="review"` are not accepted. The Task context
pointer records the version actually injected; it does not claim scientific review.
