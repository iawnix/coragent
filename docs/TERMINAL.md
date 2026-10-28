# Terminal

[English](TERMINAL.md) | [简体中文](TERMINAL.zh-CN.md)

`coragent --workspace <name>` opens the CoRAgent terminal, built with public
Pi TUI components. CoRAgent owns its session connection, commands and transcript
presentation; Pi Durable executes and stores the selected workspace's session.

Workspaces use the research mode automatically. No mode selection is needed; see the workspace commands below.

Use `coragent -h` for common commands and examples, or `coragent --help-all`
to include SSH options and background service details.

## Runtime shape

There is one Agent Server owner and several clients:

```text
CoRHub/Web -- Link/HTTP --+      CoRAgent Agent Server / Host API
CoRAgent TUI -- Unix/SSH ---+-->   Agent Session
Monitor -- Host RPC ---------+      Pi Durable Harness / SessionWorker
```

The Host is the Agent Server API and hosting layer. It owns routing, authentication,
session discovery, session-management RPC receipts, and
the Job Manager supervisor. The Pi Harness worker inside that same Agent Server
owns input admission and idempotency, user-task control receipts, the Agent loop, model, tools, transcript, and durable SQLite lane.
The CoRAgent TUI, Phone, and Monitor all address that same lane; none starts
another agent loop.

The Host client's RPC transport can be a local Unix socket or an SSH-launched
`coragent-host-proxy`, which forwards the same `coragent-host/3` NDJSON over SSH
stdin/stdout to a private remote socket. SSH changes the connection path, not
the owner of the workspace, session, or Agent lane.

For a remote installation, provide the remote Host socket and the proxy path:

```bash
./coragent --workspace reaction-a \
  --remote-host pi.example \
  --remote-host-socket /ABS/remote-host.sock \
  --remote-proxy-path /opt/coragent/current/agent/apps/agent/transport/ssh.mjs \
  --ssh-config ~/.ssh/config
```

Replace the socket placeholder with that installation's actual Host endpoint;
its directory and filename include installation and server identities. The proxy
example assumes `/opt/coragent` is the remote software root; a source checkout
instead uses `<checkout>/apps/agent/transport/ssh.mjs`.

The launcher gives the terminal a private local Unix proxy to the remote Host. The workspace and session
remain on the remote Host; the local directory is only a presentation cwd.

## Open a workspace

```bash
./coragent --workspace reaction-a
./coragent --workspace reaction-a -c
```

The launcher first ensures the installation Host is ready, then requests a
session descriptor and connects the terminal to the Host socket. Native Pi Harness is the only supported backend: no tmux
session or PTY scraping path is available. A second terminal
attaches to the same SQLite durable session; closing a client does not stop the
worker or interrupt a turn.

The Host service is installation-wide and scans direct child workspaces. It is
normally managed with:

```bash
systemctl --user start coragent.service
systemctl --user status coragent.service
```

Use the same commands without `--user` for a system unit. The private Host
socket is under the configured runtime directory.

## Sessions and controls

The conversation has a research/Job sidebar on terminals at least 110 columns
wide with 12 rows available for the conversation. `/sidebar off` hides it;
`/sidebar auto` or `/sidebar on` enables it when there is enough room. Narrow
terminals keep the full conversation width; `/research` and `/monitor` provide
the corresponding details. The sidebar tracks the current research task, linked
questions, next action and active Jobs; execution status is not a scientific judgment.

`/tasks` shows current execution, sleeping tasks and their next check, queued
inputs, and recovery guidance. `/retry [task-id]` selects or retries only a Pi
task parked at the restart limit. It continues from saved progress, and does
not rerun completed tools. Use `/compact` to retry a failed compaction, or
`/monitor task resume <task-id>` for a paused research task. Status refreshes
without calling a model; unavailable sources are marked explicitly.

`/image <workspace-relative path>` previews PNG, JPEG, GIF or WebP files up to
8 MiB and 40 megapixels through the Host, including over SSH. Use material paths
under `inputs/`, `artifacts/`, `runs/`, `reports/` or `outputs/`, for example
`/image outputs/plot.png`. Spaces in paths
are supported without shell quoting. Reads are version-checked and chunked;
Esc cancels further reads. This is a local preview, not an image submission to
the model. Images returned by tools or present in session messages also render
in the transcript. Rendering follows terminal capabilities: Kitty graphics
displays PNG; iTerm2 graphics also supports other image formats. Unsupported
terminals/formats show a text fallback. Export a PNG for Kitty-based previews.
No image paths or URLs in Markdown are fetched automatically.

The CoRAgent terminal provides `/resume`, `/model`, `/thinking`,
`/compact`, `/reload`, and the CoRAgent commands. `/reload` refreshes model
configuration and credentials. `/resume`
switches to another SQLite durable session in the current workspace; it does not
cross workspace boundaries. Switching disposes the old terminal connection before
attaching the selected session; background tasks continue. Other standalone Pi
session commands are not available in this remote client.

Selectors and document views own keyboard focus while open. Arrow keys navigate
and Esc returns to the editor, preserving its draft and cursor even after mouse
interaction. Execution commands such as `/compact` and `/reload` use a single
status line and leave the editor usable; no panel needs to be dismissed.
`/compact` tracks its durable operation until the summary is placed, or reports
that it was skipped, cancelled, or failed. The transcript shows a compacted
context marker; it does not print the internal summary as an ordinary reply.

Slash completion uses Pi 1.4's public Editor. Its menu appears alongside the
input; arrow keys select candidates, and Tab or a click completes them. Monitor
suggestions preserve case-sensitive IDs. Bracketed paste never executes a command.
Incomplete commands report the missing argument without executing an operation.

Failed commands return to an untouched editor for correction; late failures never
overwrite a newer draft. Press F2 on an error to read its complete message and
usage; runtime query errors also include their available command, error code,
request ID and elapsed time. Esc returns to the editor. Standard Windows Terminal
F2 sequences are supported, including sequences split across SSH packets within
the input timeout. Paths and multiline text starting with a slash remain
ordinary messages. Pasting alone never executes a command.

Command surfaces follow the active Pi theme. `›` marks keyboard focus and
`[current]` marks the applied value; selectors support clicks and wheel navigation.
Running and queued tools use the activity color, blocked tools use warning,
failures use error, and cancellation uses secondary text. With `NO_COLOR` or
`TERM=dumb`, command surfaces, completion, status and tool summaries keep text and
symbol cues.

Document views distinguish field labels, numbers, booleans and states. `/sys-prompt`
colors Markdown headings, inline code and fenced blocks while preserving the source.
Diagnostic fields show empty lists as `[]`, empty objects as `{}`,
missing values as `—`, and empty strings as `""`. Empty collections stay beside their
field labels. Empty Monitor lists show `No entries`; these are not error states.

CoRAgent command names, arguments, and completions share one catalogue:

- `/research`: review the current task's research progress, saved judgments and evidence. Read and search commands open the underlying records, including in a workspace reached over SSH. See Research progress below.
- `/sys-prompt`: inspect the current worker's CoRAgent system prompt manifest and sources without a model request.
- `/resume [session-id]`: select or specify a session in the current workspace. Cancelling keeps the current session.
- `/usage`: inspect session token totals, context and usage by model in a compact panel.
- `/monitor`: inspect the current user task, its delivery criteria and waits, associated compute Jobs, and execution records. See the Monitor commands below.
- `/quit`: disconnect this terminal while leaving the worker and its tasks running.

The nonfunctional `/debug` placeholder has been removed.

Successful command feedback expires after three seconds and informational feedback
after five; errors remain until dismissed or another input is submitted. Submitting
a message clears completed command feedback. With a selector or document open, Esc
returns to chat. In ordinary chat, Esc pauses the current user task, including
while it waits for compute with no active model reply, and interrupts any running
turn. Command feedback does not intercept this action. Compute Jobs keep running.

The Context footer refreshes independently of Monitor and research queries.
When the transcript changes, usage displays `Updating` until a matching estimate
arrives; the known capacity remains visible for the same model.
A failed request displays `Unavailable`, with its reason in `/usage`. Switching
models never reuses the old model's capacity. `Total tokens` is cumulative session
usage, not the current context size.

Usage and monitor panels, model/thinking/resume selectors, and slash completions
open above the Monitor row. The system prompt and long research results replace the
main reading area, with a fixed heading and Back/scroll hints. Every screen retains
Monitor, the input and the model/context footer. The input preserves its draft and
cursor but cannot be edited or focused while a panel or reading page is open.
Arrow keys scroll content without changing the panel height; short documents only
show Back. Closing restores editing and the transcript reading position. Background
task cancellation hints are hidden while a command surface owns Esc.

A permanent row immediately above the input separates the Monitor connection,
the user task state, and compute Job counts:

`Monitor: Connected · Task: Waiting for compute · Job: 1 running, 0 queued`

`Monitor` describes the availability of the current session's Monitor snapshot:

| Display | Meaning |
| --- | --- |
| Connected | A current snapshot was received successfully |
| Connecting | Waiting for the first snapshot, including after switching sessions |
| Disconnected | The Monitor overview request failed |
| Unknown | The snapshot is missing a valid timestamp or is older than 30 seconds |

Until a current snapshot is available, `Task` and `Job` display `Unknown`; cached
data from another session or an expired snapshot is not presented as current.
These connection and freshness states do not imply that research or compute Jobs
have paused or stopped.

`Task` directly reflects the persisted `task.state`, using the same labels as task
details and lists:

| Task state | Display |
| --- | --- |
| `active` | Researching |
| `waiting` | Waiting for compute |
| `paused` | Paused |
| `blocked` | Needs attention |
| `completing` | Preparing delivery |
| `completed` | Completed |
| `partial` | Partially completed |
| `cancelled` | Cancelled |
| `recovering` | Checking recovery |

A current snapshot with no task displays `Task: None`. Controller query failures,
disabled automatic continuation, and execution recovery do not replace the task's
state with a different activity label. Their explanations remain available in
`/monitor`, task details, execution records, and `/monitor health`. A completed
model reply does not imply a completed user task.

`Job` reports running and queued compute Jobs separately, scoped to the current
task or to the session when there is no task. Counts cover all pages and do not
indicate whether a model turn is running. No progress percentage or completion
time is inferred. The row remains visible while idle and while command panels
are open. Background refreshes preserve focus, selection, reading position, and
the input draft.

`/monitor` is a compact live current-session overview. It displays the task state,
objective, latest progress, next action, wait conditions, recovery reason, resume
condition, and effective continuation status. Job counts cover all pages for the current
task; up to five active jobs are previewed. Paused, blocked, or disabled continuation
does not promise an automatic wakeup. Long summaries explicitly link to full details. Use `/monitor task <id>`
for delivery criteria and research details, `/monitor jobs` for execution and
collection, and `/monitor run <id>` for Pi generation/tool tasks. A successful Job
is not treated as completed scientific analysis. Read the recorded Results and
their evidence; a Research Brief is only an orientation summary.

At launch, `-c` selects the latest writable SQLite durable session and
`--session-id <id>` selects an exact session. Startup `-r`/`--resume` is
rejected because the Host-mediated client must obtain an exact connection
descriptor before starting the TUI; open the terminal and use `/resume`
instead. Phone and browser-gateway prompts are submitted through Host `input/send` with a
durable request receipt and a stable `client_message_id`.

Prompt history is restored from the selected session's active transcript and remains
session-scoped; use the editor's Up/Down keys to revisit accepted prompts after
switching. On reopening, inputs outside the active transcript after compaction are
not restored.

Disconnect, interrupt, and quit are different states. A detached terminal is
only a disconnected client. Chat `Esc` pauses the current task even while waiting
for compute; Host `turn/interrupt` targets a specific active turn. Both suppress
automatic continuation. `/quit` closes only this terminal connection. If an input response is lost after dispatch, query `input/status` with the
same `client_message_id`. Pi's durable submission owns acceptance and completion;
retrying the same business ID does not create another input.

## Phone and browser

Phone clients must implement the versioned `coragent-host/3` NDJSON methods through CoRAgent Link. The
Relay transports opaque frames and does not own sessions or research state.
Phone and the terminal receive the same Pi snapshot and events. The optional
browser gateway attaches to one existing session over loopback HTTP/SSE; it
does not start Pi or a worker. This transport gateway is separate from
[CoRAgent Web](../apps/web/README.md), the read-only research browser
that does not submit prompts.

Host accepts only `initialize` with `protocol: "coragent-host/3"`. Clients using earlier Host protocols
must be updated. Capability names are the callable slash-separated methods.
Session reads and attachments accept only `after_cursor: {epoch, sequence}`;
a different Host epoch returns a current snapshot without replaying old events.
Session creation/resumption and `model/select` use `model: {provider, id}`.
Session lists use `{sessions: [...]}` and contain no legacy backend or format flags.

## Research progress

| Command | Behavior |
| --- | --- |
| `/research` | Research progress for the current task, with links to other research problems |
| `/research read [ref]` | Select a problem by title, or read a referenced problem, judgment or Result |
| `/research search [text]` | Find saved research and evidence by text; omit the text to browse recent records |

The title browser and search results provide commands for the next page and accept
`--offset` and `--limit` in records. `/research read --offset <n>` browses another
page of problem titles. Reading an explicit reference loads the complete detail
automatically and does not accept pagination flags. Search uses a case-insensitive
literal substring and previews the relevant research text. Put text that starts
with an option name after `--`.

The overview leads with the research objective and current saved judgment, including
its limitations. It then shows the evidence already obtained, the next action,
blockers and any recorded request for user input. Problem titles provide navigation;
record IDs identify the exact evidence to open. Update times show when the displayed
information was saved.

The current task determines the overview's focus. Other problems remain available
through their titles and read commands. A missing judgment is shown explicitly;
the view does not invent a conclusion from a Job's exit status. New evidence or a
superseded Result cited by the judgment is marked as requiring review, so an older
judgment is not presented as an updated assessment.

These commands read persisted records through the attached worker. They do not call
the model, update research, change task focus or resume a stopped task. Task state,
scientific conclusions and compute Job state are separate facts: a stopped task
does not establish that the research is complete, and a successful Job does not
establish a valid conclusion. Use `/monitor` for task controls and `/monitor jobs`
for execution status. Text search finds stored records; it does not generate a new
answer or replace reading their evidence.

## Monitor

Monitor unifies user-task controls and compute-Job observations. Task Controller
runs alongside the Pi Harness in the SessionWorker and uses the same durable
transaction and admission boundary. The installation Job Manager worker polls Job
status and records execution events. Pi remains the only model/tool execution loop;
Research Memory stores scientific evidence and conclusions.

| Command | Behavior |
| --- | --- |
| `/monitor` | Live overview for the current session |
| `/monitor tasks` | Current and historical user tasks |
| `/monitor task <id>` | Objective, delivery criteria, research problems, progress and waits |
| `/monitor task pause <id>` | Pause automatic task progression; running work may finish |
| `/monitor task resume <id>` | Resume the specified user task |
| `/monitor task cancel <id> --keep-jobs` | Cancel the user task and retain its compute Jobs |
| `/monitor task cancel <id> --cancel-jobs` | Cancel the user task and request cancellation of its Jobs |
| `/monitor jobs [--task <id>]` | Session Jobs or Jobs owned by one user task |
| `/monitor job <id>` | Execution and collection state |
| `/monitor job cancel <id>` | Request cancellation of one compute Job |
| `/monitor runs [--task <id>]` | Execution records grouped by Pi submission/run |
| `/monitor run <id>` | Bounded generation/tool execution details |
| `/monitor health` | Task Controller and shared Job Manager worker health |

`/monitor health` separates the worker's last successful observation and event
delivery (`last_successful_observation`, `last_successful_delivery`) and their
errors (`last_observation_error`, `last_delivery_error`). A null success time means
no success has been recorded since worker startup. A query timeout retains the
last observed Job state; it does not establish that the Job failed. Pending events
can still be delivered while another platform's query is slow.

Task details include research entry points, current focus, local plan excerpts,
original problem status, assessment/Result references, and related Jobs. Only
Jobs owned by the current session have `/monitor job` links; other Jobs remain
visible as `Outside this session`. Shared
problems appear once; relations reference their IDs. `closed` is labeled `Ended`,
which does not assert scientific success or task completion. Omitted context is
marked and `/research read <id>` opens the underlying record. Node counts do not
measure research progress. Reading these views never changes task focus or wakes
the model; there is no separate planning command.

Lists and run details accept `--limit <1–100>` and `--cursor <cursor>`. A returned
next-page command preserves the filter and page size. IDs belong to the attached
session; a missing or foreign ID produces an error. Task cancellation always
requires an explicit Job policy.

All commands call the canonical `monitor/overview`, `monitor/tasks`,
`monitor/task/read|pause|resume|cancel`, `monitor/jobs`, `monitor/job/read|cancel`,
`monitor/runs`, `monitor/run/read`, and `monitor/health` Host methods directly.
Queries do not send Agent input or call the model. Task controls read the current
revision and send a stable request identity; a revision conflict is displayed,
not silently retried. Monitor's previous status/list/enable/disable methods and
per-Job automatic-follow-up switches are removed.

Pausing a user task prevents new automatic progress without cancelling its running
Jobs. Chat Esc pauses the task and stops any current reply; `turn/interrupt`
targets a specific active turn. Both suppress automatic restart. Esc inside a Monitor panel only closes that panel. Cancelling a Job and
closing a terminal are separate actions. `/resume` switches the chat session;
`/monitor task resume` resumes work inside the current session.

Job wake and user-notification channels have independent receipts, leases and
backoff. A wake is accepted input, not proof that analysis completed. Task Controller
rechecks durable task and Job state before continuing. The Agent must still inspect
results; Monitor does not publish scientific conclusions or edit Nodes.

`workspace_manifest.json` binds the canonical `workspace_id` to both scientific
state and Host routing. There is no separate scientific identity or direct-child
alias translation.

## Session storage

The `<state_root>/pi/sessions/` tree is the only
session store used by Native Pi Harness. Workspace `.pi/sessions` history is not a
supported input and is neither resumed nor imported by the Native runtime. Durable
history lives in `<state_root>/pi/sessions/<workspace-id>/<session-id>/session.sqlite`;
metadata is in the adjacent `meta.json`. Keep research state in the workspace
Research Memory and use the Host session controls for SQLite durable sessions.

See [Architecture](ARCHITECTURE.md) and [Installation](INSTALLATION.md) for
service, package, and recovery details.

### Streaming and animation

The terminal attaches with `session/attach` using `presentation: "terminal"` and
`view_stream: true`. The reply contains a full view frame. Subsequent
`session/view` notifications carry sequenced entry splices and changed documents;
unchanged history is retained on the client. A sequence gap closes the connection
and reattaches with a fresh snapshot. Normal streaming does not issue
`session/query` reads. The same incremental transport is used between the Worker
and Host; the phone snapshot/event protocol remains unchanged.

The working indicator occupies a fixed status row and animates independently of
model tokens using Pi's public Loader. Its timer stops while a panel is open,
when work finishes, and when the terminal closes. Set
`CORAGENT_TUI_ANIMATION=0` to use static status text. Animation and input redraws
reuse the chat layout; token updates reuse the completed history and update the
current Markdown component. Unchanged history is skipped during entry comparisons,
and tool progress updates only its own card. Hidden output in a collapsed tool
continues to arrive without scheduling transcript redraws; expansion shows the
latest output. Hiding the sidebar suspends its research polling.

While reading history, a width change retains the current message and its line
offset. This does not promise character-exact positioning when a long paragraph
rewraps. Clicking a tool card pauses following and keeps its heading near its
previous screen position. Scrolling back to the bottom resumes following.
Expanded plain-text tool output reuses Pi `Text` layout caches per line; appending output
only creates components for new lines, while a width change lets Pi recompute wrapping.
Output is sanitized before it reaches the terminal renderer so tool logs cannot emit UI
control sequences.

Deterministic regression coverage in `terminal-streaming.test.mjs` includes
1,000 historical messages, repeated streamed updates, resize/compaction, timer
cleanup and hidden polling. Timing evidence stays in the private test run.
`terminal-experience.test.mjs` also covers tool progress, reading positions, card
expansion, and Chinese input and paste through Pi's full-screen renderer in a
virtual terminal. It records tool-update and input-to-render timings, terminal
output bytes and full-screen clears. These deterministic checks do not replace
hands-on acceptance in physical terminals and over real SSH connections.
`terminal-tool-output.test.mjs` covers Chinese text, blank lines, newlines, malformed
escape sequences, resizing, append and replacement. It also verifies that a 150,000-line
log does not exhaust the JavaScript call stack. Long-log evidence remains private.
