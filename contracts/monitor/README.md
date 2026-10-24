# Monitor API

Monitor is the management interface; Job Manager owns background observation and event delivery.
Task Controller owns automatic continuation policy. Input admission is an internal Pi integration boundary.

Monitor uses the existing `coragent-host/3` RPC envelope and authentication.
`apps/agent/contracts/monitor.mjs` is the canonical method/capability list shared
by Host and browser transports. All methods are scoped to `workspace_id` and
`session_id`; there is no workspace-wide task mutation or alternate protocol.
Host forwards `{method, params}` unchanged to the owning SessionWorker's
`coragent.monitor.handle`. The Worker returns `{result, error}` internally;
Host exposes the result directly through its normal RPC result envelope.

## Requests

| Method | Additional parameters | Result |
| --- | --- | --- |
| `monitor/overview` | none | Overview |
| `monitor/tasks` | `limit?`, `cursor?` | Page of TaskListItem |
| `monitor/task/read` | `user_task_id` | `{task: UserTask, research: ResearchSnapshot, session_job_ids: string[]}` |
| `monitor/task/pause` | task control fields | TaskControl |
| `monitor/task/resume` | task control fields | TaskControl |
| `monitor/task/cancel` | task control fields, `jobs: "keep" \| "cancel"` | TaskControl |
| `monitor/jobs` | `user_task_id?`, `limit?`, `cursor?` | Page of Job |
| `monitor/job/read` | `job_id` | `{job: Job}` |
| `monitor/job/cancel` | `job_id`, `request_id` | `{job: Job}` |
| `monitor/runs` | `user_task_id?`, `limit?`, `cursor?` | Page of RunSummary |
| `monitor/run/read` | `run_id`, `limit?`, `cursor?` | RunDetail |
| `monitor/health` | none | Health |

Task control fields are `user_task_id`, stable `request_id`, and the current
positive `expected_revision`. Repeating the same identity and payload recovers
the Worker receipt; changing its payload is an error. A revision conflict
requires reading the task again, not silently overriding it. Cancellation must
explicitly preserve or request cancellation of owned Jobs. Cancel requests do
not prove that an external process stopped; inspect returned Job observations.

`limit` is an integer from 1 to 100. `cursor` is a nonempty opaque string from
the preceding response. Clients must not construct cursors or reuse one across
list methods. `user_task_id` names the user's work; `run_id` is Pi's first input
submission identity for that run; `pi_task_id` names an internal execution Task.
These identifiers are not interchangeable.

Unknown methods return `method_not_found`. The native slash parser maps user
commands to this same method set; queries never ask a model to interpret the command.

## Result shapes

The following definitions document wire projections, not new state owners.
Task state and control receipts belong to Pi durable, execution state belongs
to Pi, and Job facts belong to Job Manager. An overview is assembled from these
sources and is not a cross-database atomic snapshot.

```ts
type Page<T> = { items: T[]; next_cursor: string | null };
type TaskState = "active" | "waiting" | "paused" | "blocked"
  | "completing" | "completed" | "partial" | "cancelled";
type Criterion = { id: string; description: string };
type CompletionEvidence = { criterion_id: string; evidence_refs: string[] };
type ExecutionTarget = { platform: string; scheduler_entry: string };
type ExecutionSelection = {
  target: ExecutionTarget;
  executor: string;
  route_digest: string;
  selection_mode: string;
  version: number;
  sources: { submission_id: string; text: string }[];
  resolved_at: string;
};
type UserTask = {
  schema_version: "coragent-user-task/6";
  user_task_id: string;
  workspace_id: string;
  session_id: string;
  conversation_id: string;
  title: string;
  objective: string;
  next_action?: string; // Current next action, included when populated.
  sources: { submission_id: string; entry_id: unknown; text: string }[];
  criteria: Criterion[];
  execution_target: ExecutionTarget | null;
  execution_selection: ExecutionSelection | null;
  execution_policy: {
    selections: ExecutionSelection[];
    max_in_flight: number;
    max_attempts: number;
    automatic_placement: boolean;
  } | null;
  research: { entry_node_ids: string[]; focus_node_ids: string[] };
  research_context: {
    brief_id: string | null;
    state_digest: string | null;
    brief_digest: string | null;
    availability: "available" | "unavailable";
    projection_status: "complete" | "incomplete";
    refresh_reason: "initial" | "scope_changed" | "facts_changed" | "retry";
    updated_at: string | null;
  } | null;
  state: TaskState;
  reason: string | null;
  block_details?: {
    kind: "missing_user_input" | "resource_unavailable" | "execution_failure" | "budget_exhausted" | "scientific_dead_end";
    resume_when: string;
    evidence_refs: string[];
  } | null;
  revision: number;
  control_epoch: number;
  wait: { job_ids: string[]; mode: "all" | "any" } | null;
  progress: {
    summary: string;
    evidence_refs: string[];
    at: string;
  } | null;
  progress_version: number;
  progress_identities: string[];
  event_inputs: { submission_id: number; request_id: string; event_ids: string[] }[];
  completion: CompletionEvidence[] | null;
  completion_submission_id?: number;
  completion_control_epoch?: number;
  execution_recovery?: {
    state: "retrying" | "running" | "attention_required";
    phase: "research" | "delivery";
    failures: number;
    submission_id: number;
    control_epoch: number;
    reason: string;
    detail: string | null;
    next_retry_at: string | null;
  } | null;
  cancel_jobs?: {
    policy: "keep" | "cancel";
    pending: string[];
    receipts: Record<string, Job>;
    uncertain: string[];
    errors: Record<string, { code: string; message: string }>;
  };
  continuation: {
    sequence: number;
    reservation: {
      submission_id: number;
      request_id: string;
      control_epoch: number;
      progress_version: number;
    } | null;
    no_progress: number; // advisory; never automatically blocks research
  };
  audit: { action: string; actor: string; reason: string | null; revision: number; at: string }[];
  created_at: string;
  updated_at: string;
};
type TaskListItem = {
  user_task_id: string;
  revision: number; // Retained for optimistic task controls.
  title: string; // At most 256 serialized UTF-8 bytes.
  state: TaskState;
  updated_at: string;
  truncated: boolean;
};
type TaskSummary = TaskListItem & {
  objective: string; // At most 1024 serialized UTF-8 bytes.
  next_action: string | null; // Up to 1024 bytes; null when no next action applies.
  progress: { summary: string | null; at: string } | null; // Summary: 512 bytes.
  reason: string | null; // 512 bytes.
  resume_when: string | null; // 512 bytes.
  wait: { mode: "all" | "any"; job_count: number } | null;
  execution_recovery: {
    state: "retrying" | "running" | "attention_required";
    phase: "research" | "delivery";
    detail: string | null; // 512 bytes.
    next_retry_at: string | null;
  } | null;
};
type ContinuationState = "idle" | "paused" | "blocked" | "error"
  | "attention_required" | "disabled" | "checking" | "overdue"
  | "retrying" | "waiting" | "pending" | "ready";
type Overview = {
  schema_version: "coragent-monitor/2";
  workspace_id: string;
  session_id: string;
  task: TaskSummary | null;
  jobs: {
    scope: "task" | "session";
    counts: { running: number; queued: number; total: number };
    active: { job_id: string; state: string }[]; // At most five active jobs.
    active_omitted: number;
  };
  execution: { state: "running" | "idle"; run_id: string | null };
  continuation: { state: ContinuationState };
  updated_at: string;
};
type TaskControl = {
  task: UserTask;
  jobs_policy: "keep" | "cancel" | null;
  job_cancellations?: Job[];
};
type RunSummary = {
  run_id: string;
  user_task_id: string | null;
  state: "queued" | "placed" | "done" | "unanswered";
  producer: "user" | "job_manager" | "task_controller";
  reason: "user_message" | "job_event" | "task_continue" | "execution_retry" | "final_response_retry";
  generation_count: number;
};
type RunDetail = {
  run: { run_id: string; user_task_id: string | null };
  items: {
    pi_task_id: string;
    kind: string;
    state: string;
    outcome: string | null;
    started_at: number | null;
    ended_at: number | null;
    tool_name: string | null;
    result_entry_id: string | null;
    error: { code: string; failure_class?: string; retryable?: boolean; action_outcome?: string } | null;
  }[];
  next_cursor: string | null;
};
type ControllerHealth = {
  automatic_continuation_enabled: boolean;
  error: { code: string; message: string } | null;
  checking: boolean;
  last_checked_at: string | null;
  check_interval_ms: number;
  recovery_policy: { maxRetries: number; baseDelayMs: number; maxDelayMs: number };
};
type Health = {
  task_controller: ControllerHealth;
  recovery: {
    state: "recovering" | "ready" | "degraded" | "stopped";
    recovered: number;
    failures: { workspace_id: string; session_id: string; code: string; message: string }[];
  };
  host_worker_health: object | null;
  supervisor_health: object | null;
};
```

Overview contains bounded task and Job summaries. Read task or Job detail endpoints
for complete records; controller health belongs to the health response.

Task lists retain only identity, revision, title, lifecycle state, update time,
and truncation status. Overview adds the latest progress, next action, reason,
and recovery condition. `truncated: true` directs clients to `monitor/task/read`
for complete text. Audit history, original sources, criteria, research and Review
references, evidence, deduplication identities, and scheduling reservations remain
in full task detail and control responses. Controller diagnostics remain in
`monitor/health`. Summaries do not change durable task records.

`continuation.state` is computed when reading overview, not persisted as another
lifecycle. No task or a finished task is `idle`; paused and blocked tasks preserve
those states regardless of automatic-continuation configuration. For remaining
tasks the precedence is controller error, recovery requiring attention, disabled
automatic continuation, unchecked/overdue controller, execution recovery, waiting
for compute, pending reservation, then ready. A check is overdue after the greater
of 30 seconds or three check intervals. `ready` means eligible for controller
checking, not proof of an active model response; `execution.state` reports that
separately. Only `waiting` warrants “Continues when ready.”

The terminal maps these observations to five activity labels: Working, Waiting,
Stopped, Completed, and Idle. It shows `—` when the observation cannot establish
current activity. Detailed continuation explanations remain in overview; precise
lifecycle states remain in task detail and task lists. This is presentation only:
it does not change these wire fields, durable state, or scheduling behavior.

Job counts include every page for the current task within the authenticated
session. With no current task they cover the session instead. Total includes
ended jobs; queued includes created, submitted, queued, and held observations.
The active preview includes only running or queued jobs, with at most five entries;
`active_omitted` counts additional active jobs. Fetch full pages using
`monitor/jobs` with the same task scope. These reads are not atomic across pages.

`Job` is the existing Job observation/receipt DTO returned by `job_list`,
`job_status`, and `job_cancel`, with immutable `session_id` and `user_task_id`
association on listed observations. It is not a separately maintained Monitor
Job lifecycle. Missing collection or scientific-analysis evidence must not be
presented as successful analysis merely because execution succeeded.

A session without registered tasks returns no current task. This protocol requires
`coragent-user-task/6` and `research-snapshot/3`. Run indexes
cover execution observed by the Task Controller; runs without an index are not
invented from the active task graph. The diagnostic view presents
structured execution summaries, not model reasoning or secret tool arguments.

Task keeps the user objective, criteria, next action, execution plan, progress evidence and
control state. Scientific hypotheses and plans belong to `research-node/2` Nodes and their
notes; Monitor does not project another initial scientific plan. Deploy runtime, contracts
and Skills together; earlier Task/Node formats have no compatibility aliases or migration.

A research Task without calculations has null `execution_target`, `execution_selection` and
`execution_policy`. Creating, reading and resuming it does not resolve an execution platform. The first
`task_update action=bind_execution`, or `set_execution_plan`, records its calculation selection before
preparation/submission; explicit execution fields in `task_begin` may bind it immediately. This is one
Task lifecycle, not separate research and computation task types. Plans and execution progress retain
the [existing execution plan contract](../../skills/core/execution-platforms/references/plans.md).
Job views continue to read existing observations when current platform configuration is absent; remote
status/cancellation/collection uses each Job's recorded original route.

## Research in task details

`monitor/task/read` returns the complete UserTask plus the same bounded
`research-snapshot/3` returned by the internal `research_read` command. The
required `session_job_ids` lists snapshot Jobs also present in the session-scoped
`job_list` pages. Only those Jobs get executable `/monitor job` links. Jobs from
shared research outside the current session remain visible with an explicit
`Outside this session` label; Memory does not supply their owning session IDs.
This list is a read-time scope projection, not stored Job ownership. The
snapshot contract lives in `contracts/commands/results.json`; Monitor does not
maintain a second graph DTO. The Worker passes the task's `entry_node_ids` and
`focus_node_ids`, its session identity, and a 16,000-byte snapshot budget.
Task references are unique lists, limited to 128 entries and 16 focus nodes.
`progress_identities` accumulates stable Result identities, Artifact content
digests, and Job milestones over the task lifetime; tool output fingerprints
and combinations of evidence references are not separate progress.
They associate existing research questions with the task, without ownership,
scientific status, or execution permission.

The snapshot's `research` section contains the associated structural node cards,
relations, entry/focus references, and omission counts. Counts describe the
discovered local neighborhood; `unexpanded_nodes` identifies further branches,
not a complete graph census. Its `plan` excerpts are
not complete edit bases. Top-level snapshot nodes can provide related Result
summaries; unrelated recent context is not displayed as part of the task's graph.
Empty associations display no linked research problems. Shared problems appear
once, with edges referencing their IDs. `closed` is displayed as `Ended`, never
as successful validation; node counts are not task-completion percentages.

Terminal controls obtain the target revision from existing `monitor/tasks`
pages. They do not depend on reading the research snapshot, so unavailable
research does not prevent pause, resume, or cancellation.

Reading task details does not update the task, change its focus, submit input,
or wake a model. Research changes use the existing research tools and the single
`task_update set_research` binding action; there is no Monitor graph mutation or
new slash command. The task revision and research sequence identify separate
reads, not an atomic snapshot across Pi and Memory. Snapshot failures are surfaced
through the normal error envelope.

## Notifications and reconnect

A successful Monitor request subscribes that Host connection to existing
workspace Job `monitor/event` notifications. Session changes use the existing
`session/attach` and `session/event` cursor/epoch mechanism. Notifications tell
clients to refresh; they are not a second durable task-event log. After a Host
epoch change or reconnect, read a new overview and preserve focus by stable
object IDs. The browser gateway applies the same methods within its fixed,
authenticated session and requires stable mutation identity.

For execution event schemas and durable outbox semantics, see
[Job monitoring](jobs/README.md). Task Controller owns pause, resume and cancellation;
observation bindings describe execution identity and routing.
