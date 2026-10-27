# Research Memory architecture

This guide describes CoRAgent's current runtime and Research Memory boundaries.
See the [maintainer guide](MAINTAINER_GUIDE.md) for validation and release procedures.

## Ownership

CoRAgent uses the native Pi Harness as its only Agent loop. Workspace is the persistent research container, independent of individual sessions. Research Memory organizes original requests, local questions, repeated attempts, explicit relations and results. It does not schedule science or certify conclusions.

| Component | Owns |
| --- | --- |
| Agent Server / Host | Service hosting; Host owns workspace admission, authentication, session routing and worker recovery discovery |
| Pi SessionWorker / durable Harness | Sole owner of session storage, conversation, model/tool execution, atomic input admission and recovery |
| Research Memory | Workspace storage contract, original requirements, Nodes, immutable Results and explicit research relations |
| Job Manager | Dispatch, execution, cancellation, reconciliation, collection, background tracking and reliable event delivery |
| Artifact Store | Immutable file bytes and provenance manifests |
| Task Controller | User task intent, lifecycle and continuation policy in the SessionWorker |
| Monitor | Management interface for Task, Run and Job; no independent scheduling state |
| Email Skill | Authorized report delivery, attachment pinning and transport receipts |
| Retrieval / Web | Rebuildable bounded views, ranking explanations and read-only navigation |

The `research_agent.research` namespace is the sole research implementation. Runtime adapters combine its data with Job and Artifact DTOs; Memory does not import execution launchers or `research_agent.application`. Shared transactions and safe file IO belong to `research_agent.foundation`. `runtime-bridge` transports commands without owning another filesystem model.

## Research model

A Node is a persistent research question. `goal` states the question and `plan` holds its current hypotheses and investigation approach. Append-only notes preserve observations, decisions and changes of direction; Results fix conclusions worth citing. Restore and reuse the relevant existing question before creating another Node. Calculation steps, parameter or platform changes, geometries and failures stay within that question unless a new research objective needs its own continuing investigation and judgment. No model-maintained Attempt entity is required.

Compound studies use existing `part_of`, `requires` and `alternative_to` relations when distinct research objectives emerge. A root Node is optional; shared questions can have multiple parents. The research scope of `coragent-user-task/6` consists of `research.entry_node_ids` and `research.focus_node_ids`, set together through `task_update` action `set_research`. These are navigation references, not ownership, a schedule or a second plan. The first Node can supply an initial binding; later Nodes are related and selected deliberately, rather than automatically added to both lists. Nodes use `research-node/2`; Result schema remains unchanged.

Node status is `open`, `paused` or `closed`. Closing means stopping active work on that question; it does not imply scientific success or cancel a Job. The authored revision changes when Node content changes, independently of background execution observations. Concurrent content changes require a new reading and explicit merge; append-only notes do not replace another author's judgment.

A Result fixes a useful observation and conclusion, limitations, actual input versions, evidence and files. It is immutable and may be negative or inconclusive. A finding is recorded as a process note or a reusable Result according to its purpose; it need not be copied into both or repeated as task progress. Explicit `supersedes` preserves the old version. A Node's selected assessment is a deliberate synthesis, not simply its latest result or latest Job failure. Publishing with `as_assessment=true` saves the Result and selects it in one transaction; a stale read saves neither. Ordinary publication leaves the current assessment unchanged. Upstream correction creates an exact review notice; it never silently replaces downstream inputs or reruns science.

## Relations and provenance

`part_of`, `requires` and `alternative_to` are explicit Agent declarations stored once. Reverse links and map indexes are generated. Containment cannot cycle; competing approaches and research feedback do not require the whole map to be a DAG. Circular current waits are diagnostics, not tool admission failures.

Actual `uses` and `cites` connections require recorded material inputs or explicit result references. Similar filenames, equal bytes, browsing and search are not evidence that a particular scientific source was adopted. Each Result retains concrete earlier versions, so feedback in the research map does not create circular evidence. Untracked input provenance remains untracked.

## Model-facing interface

| Tool | Minimum request |
| --- | --- |
| research_read | `{}` for a bounded context, or `{ref}` for an exact object |
| research_search | `{query}` |
| research_create | `{goal}` |
| research_update | `{node_id, note}` |
| research_result | `{node_id, conclusion}` |

Updates append a note and may change the Node's title, goal, plan, subjects, status or selected assessment and add/withdraw explicit relations. Result files refer to registered Artifacts. Session, workspace, request identity, read basis and revisions are supplied by the trusted adapter. Models do not maintain transaction metadata, reverse edges or a global progress object. There is no lifecycle checkpoint or yield-repair prompt.

## Workspace and storage

`workspace_manifest.json` uses `research_workspace/3`. Research records preserve original user messages and distinct author/runtime origins. Stable Node directories under `research/nodes/<id>/` contain their current view and work files; immutable results and history preserve earlier versions. Research indexes, reverse links and generated Markdown are rebuildable. Titles and relationship changes do not move directories.

Research objects use workspace-scoped numeric IDs (`task_1`, `node_1`, `job_1`, `result_1`, `art_1`). Tools, storage and clients use the same canonical ID, without display aliases. Each type has a durable sequence in `operations/identifiers.json`; reservations survive failed operations, retries reuse identity keys, and gaps are allowed. Digests still verify content. New workspaces use manifest version 3; old workspaces are not migrated.

`runs/jobs/` owns execution working directories. `operations/` owns durable intents, observations, collection/delivery receipts and exact short references. `artifacts/<id>/payload` and `manifest.json` own fixed file versions. Mutable Node work files must be registered before a Result cites them as published material. Reports remain ordinary user-facing files with fixed delivered versions.

Transactions publish coherent research updates and recover interrupted commits. Runtime, contracts and Skills must be deployed together for `research-node/2` and `coragent-user-task/6`. Earlier Node/Task formats and old graph/notebook workspaces are rejected without migration or mutation. Create a new workspace and explicitly import useful materials; no dual reader or compatibility writer is supported.

## Context and next_run

A bounded model context preserves original user intent and the authenticated trigger, then ranks relevant Nodes using event association, explicit focus, pending execution facts and research relations. Necessary result summaries and direct dependencies accompany selected Nodes. Omission has explicit read/search routes; retrieval never presents missing content as completed work. Ordinary user text cannot establish Job Manager event provenance.

Research Context is an internal part of the Agent Runtime. At each generation boundary it reads the deterministic `research_read view=brief` projection and compares scoped facts with the last committed context anchor. Initial context, scope changes and relevant fact changes append a passive `pi.context` entry atomically with the request cutoff. Unrelated activity and duplicate events do not add another entry. Input producer identity does not decide freshness. Reads and no-change decisions are memoized for recovery; failed reads are explicit and retried at a new input boundary.

Research Brief (`research-brief/1`) contains bounded facts, recent research notes, counts, contradictions, uncertainties, limitations and source references. Its state digest covers scoped candidate records, including relevant notes omitted for size, rather than the global journal sequence. The view normally targets 2,000 tokens, up to 4,000 for contradictions. The deterministic Brief prioritizes the selected current judgment, retaining its conclusion, limitations and citations together. Content that does not fit is explicitly unread with an exact read operation; no second model synthesizes a partial view. New evidence after the latest explicit assessment selection requests review without invalidating the judgment. These derived reading aids do not publish Results, select assessments, grant read/write authority or prove scientific validity. Original evidence remains accessible through research_read and job_status.

`CompactionTask.prepareSummary` supplies instructions and metadata from the selected immutable historical prefix only. Supplements are pinned before the native summary call and preserved over retry/recovery. The resulting summary retains the scope anchor as non-model metadata. Later retained context entries supersede it. No live research read is backdated into a checkpoint, and no summary establishes authorization or field-read grants. Pi retains safe tool boundaries, summary calls, retries, usage accounting and atomic/stale-aware placement. A reset deliberately starts a new orientation.

Stable policy remains in system. Historical `research_context` data uses a user-message carrier at its original position. Only the small current `runtime_control` envelope is appended per request; it carries task identity, revision, control state, waits and actual user submission IDs. Authorization is rechecked after external IO. Neither carrier becomes a user authorization. There is no separate per-request research snapshot lifecycle or model-authored memory protocol.

Context admission and patched Pi compaction share the input budget `max(0, contextWindow - max(reserveTokens, maxTokens + 4096))`, reserving the stream output override (or model maximum) and safety overhead before the SDK shrinks output. `CORAGENT_CONTEXT_INPUT_TOKENS` is an optional explicit lower cap for constrained deployments; it is not set by default. Native background compaction and recent-history retention continue to use Pi's settings. At most one blocking compaction is attempted; an oversized retained message or failed compaction blocks before the main provider request. Request telemetry (`research-request-context/4`) stores sizes and digests, not duplicate snapshots. Estimates and cache counts are not billing measurements. No historical files are migrated by this change.

The terminal shows the operating input budget alongside the model window. Queued passive writes, including background compaction summaries, do not prevent continuation failure settlement. A budget rejection becomes execution attention rather than an indefinite preparing state. After explicit recovery, Pi places queued writes at its native boundary before consuming the new input; queued user inputs retain priority.

Managed research Jobs explicitly bind node_id and the inspected Node revision at submission. The trusted tool adapter also binds the current `user_task_id`; this is separate from scientific Node ownership. Preparation and diagnostics can remain unassociated. Job Manager events retain the original associations across Node edits and session restart.

`next_run` is a real scheduling mode: persist an authenticated execution event, wait while its owning session is busy or automatic execution is paused, then submit one idempotent Pi input. Event persistence, Pi consumption and scientific interpretation are distinct facts. Lost replies reuse the same request identity; a fixed batch does not absorb later events while retrying. New notes, Node status and Memory sequence do not trigger or suppress delivery. An open Node does not create an automatic turn. A separately registered active user task can continue without a new Job event.

Job observation and event delivery advance independently. Observations interleave
workspaces, with at most four concurrent queries globally and one per named
platform across its scheduler entries. Each observation shares a 30-second
subprocess budget and a 35-second supervising CLI timeout; shutdown waits for
Python and its local query process group to finish. Observation timeout preserves
the recorded Job state. Health reports observation and delivery success and errors
separately.

The shared [Monitor limit](../contracts/monitor/jobs/limits.json) caps fixed batches
at 256 events. Batch creation, claim and completion are transactional; each session
delivers its earliest pending batch first. Durable consumption removes the Task's
pending event references in the same Pi transaction, including successor
consumption after recovery. Existing oversized batches require explicit maintenance
after verifying that Pi never accepted their original request; upgrade does not
silently change an existing batch identity.

## Persistent user tasks and Monitor

The request-only task facts share the research context budget; the bounded browsing projection still points omitted details to `task_read`. A user task spans Pi runs and compute Jobs. `task_begin`, `task_read` and `task_update` record the authorized objective, cited user submissions, delivery criteria, next action, execution plan, progress evidence and explicit waits or blockers. Scientific hypotheses and plans belong to Nodes; Tasks do not retain another initial scientific plan. Existing tools expose published evidence and Job milestones to task tracking; the Agent explicitly changes the next action, waits and controls when needed. Ordinary questions do not create tasks. A session has at most one nonterminal user task. Its control state lives only in Pi durable documents; Host does not store a duplicate task lifecycle or control receipt.

Workspace, Research Memory, Task and context management remain a cohesive research core. An ordinary
Task starts with null execution target, selection and policy, without resolving a platform. When calculation
is needed, `task_update action=bind_execution` uses the same resolver as an explicit `task_begin` or the
first `set_execution_plan`. Preparation and submission require that persisted selection; local bash and
platform diagnostics do not. The Task remains one protocol and one Pi-owned lifecycle. Research reads
compose local Job observations and replayable facts in the application layer; they do not poll a queue.
Existing Jobs retain their original recorded routes independently of changes to the current platform configuration.

The Task Controller runs inside the SessionWorker. Normal tools continue within the native Pi loop. After a completed run, a durable `task_controller` input can continue an active idle task through the same admission transaction used by other inputs. The implementation does not install an `onYield` continuation path. Watch notifications and a 30-second check reconcile outstanding work; Job waits query concrete owned Jobs and invoke no model until ready. Runs without new evidence update an advisory count and a replanning reminder, never an automatic research blocker. Terminal transient provider failures can schedule bounded, delayed successor inputs; nonretryable or exhausted failures retain an execution-recovery attention record while the research state remains active or completing. Final-response recovery retains completion evidence and allows only reads and the response. A normal answer ending is not user-task completion: proposed completion needs evidence for every criterion and a successfully delivered final response.

Pause suppresses new automatic work while the current response and Jobs can finish. Interrupting a response also pauses the user task. Resume is a user control operation. Cancellation requires an explicit keep/cancel policy for owned Jobs. Querying Monitor does not send a prompt or resume a task. `CORAGENT_AUTOMATIC_CONTINUATION=0` disables automatic input while preserving user input and read access.

When a new user request runs after a research execution failure, Monitor retains
the failure in its task details. The compact status row separates the Monitor
connection, the persisted Task state, and running/queued Job counts, as documented
in [Terminal](TERMINAL.md). Continuation errors and recovery details do not override
the Task state; unavailable or stale snapshots display unknown Task and Job values.
Admission alone does not resume automatic work. If that current user run records new task evidence or an owned Job milestone and Pi completes its submission successfully, the controller clears the old research recovery warning and allows continuation (or honors the current Job wait). Duplicate evidence, status questions, superseded inputs and failed runs cannot clear it; pause/cancel still take precedence. The recovery link survives restart, and historical failed submissions remain unchanged.

Natural-language task control uses `task_update action=apply_user_control` with the latest actual user submission consumed by the current run. The runtime checks provenance, live input membership and the current revision; automatic inputs cannot authorize controls. The stopping run can finish read-only checks, requested Job cancellations and its final acknowledgement, but cannot start more work or a replacement task. Task cancellation is committed before Job discovery/cancellation; backend failures remain durable cleanup work and do not wake the model. Job cancellation and Node status changes do not stop the top-level Task.

Progress observations and explicit progress updates share persistent identities: individual Result IDs, Artifact content digests and owned Job milestones. Plan edits, notes, Node creation and focus changes are activity without progress credit. Reusing an identity, changing a reference combination or restarting does not replenish the allowance. Each completion criterion needs fixed Result or Artifact evidence; scientific applicability remains the Agent's responsibility. These controls cannot assess whether newly produced evidence is scientifically valuable.

Host restart discovers sessions from Pi's existing catalog and reopens at most four Workers concurrently; each Worker reconciles its durable task. Recovery failures appear in `monitor/health`. No process besides the SessionWorker writes its SQLite store. The aggregate is a projection of independent Task, Pi and Job owners, not a cross-system atomic snapshot.

`/monitor` is the unified product entry point for tasks, Jobs and execution details. Host and browser transports share one canonical method list in `apps/agent/contracts/monitor.mjs`; the [Monitor contract](../contracts/monitor/README.md) describes requests and results. Pi generation/tool Tasks appear under a run's diagnostic details, never as user tasks. Existing session and Job notifications request a fresh snapshot after changes or reconnects.

Each SessionWorker owns an execution bridge and a bounded local-query bridge,
using the same Python JSONL protocol, command implementations and workspace
transactions. The query bridge admits only `research_read`, `research_search`,
`job_list` and `job_manager_assess`; it coalesces identical outstanding requests
and accepts at most 16 distinct requests. A timeout does not cancel Python work:
capacity is released when its actual response arrives or the process exits.
Tool envelopes classify a sent request timeout as an unknown outcome, with no
automatic retry; a capacity rejection before sending remains not executed.
Both processes are closed with the Worker. Query commands may recover transactions
or project events and retain the existing workspace locks.

Monitor reads persisted Task state and Job Manager observations without changing
Task lifecycle or polling schedulers. The controller resolves waits from persisted
Job observations. Cancellation discovery stays ordered behind earlier execution
requests so an in-flight submission cannot escape discovery. Context telemetry
uses Pi history and model metadata, independently of both Python bridges.

## Skills and delivery

Pi loads installed Skills natively. CoRAgent verifies installed resource digests. Read the actual Skill path supplied by Pi; relative references resolve from that Skill directory. `research-memory` teaches five small operations; research-workflow coordinates Jobs and materials; domain Skills teach scientific methods. `reaction_mapping.md` belongs to `material-preparation/references/`.

Process completion, file existence and Node closure do not establish a scientific result. Email uses existing user authorization and its own durable send identity. If Memory recording fails after transport acceptance, recover the record without resending. Installation, runtime and scientific claims each require their own evidence.

### Phone material files

Host exposes the authenticated `files/*` capabilities documented in
[`contracts/files/README.md`](../contracts/files/README.md). The Python material
projection bounds directory pages and version-checked file ranges. Explicit
`files/pin` creates a content-addressed snapshot under workspace inputs for a
phone draft; it is not a Research Memory Artifact. These operations do not attach
a session or invoke Pi. CoRHub retains the existing text-message/outbox protocol
when submitting the reference. Private state paths and links are excluded.

Task means the user objective; Run means one input-driven Agent execution; Job means external computation. Input admission is an internal Pi integration boundary for authentication, idempotency and atomic submission. Job events and task continuations use the same Task Controller policy. Producers are user, job_manager and task_controller; the separate reason field identifies user_message, job_event, task_continue, execution_retry or final_response_retry. Retired producers and research Review interfaces have no compatibility aliases.
