# Qrun: local and SSH job queues

[简体中文](QRUN.zh-CN.md)

Qrun (Queue + Run) is a single-host CPU/memory FIFO queue. CoRAgent owns scientific
Jobs, staging and collection; Qrun owns admission, reservations and execution records.
The same Python 3.11+ program runs locally and over SSH. Modern Linux hosts use
user systemd and cgroup v2. Older hosts, including CentOS 7, can use the unprivileged
portable runtime without a user service manager or writable cgroups.

## Target configuration

Choose `transport = "local"` or `"ssh"` independently of `executor = "qrun"`.
The executor field accepts `qrun`, `pbs`, `torque`, `slurm`, `tri` and `external`.
Qrun is the bare-host executor for both local and SSH targets. Other executors
require their documented handler. Multiple local targets are supported.
The old `driver`, `supervisor`, `scheduler` and `type` configuration fields are
removed, as are the direct process/systemd executors. Existing configurations
must be rewritten using `transport` and `executor`; old direct-execution
receipts are not resumed through Qrun. systemd is Qrun's process runtime.

See [job.qrun.example.toml](../config/job.qrun.example.toml). All handler, software
binding and work-root paths belong to the execution host. The default handler,
`["qrun", "handler"]`, is replaced with a stable absolute argv by the main
installer for managed pools. Independent pools need qrun on the noninteractive PATH.
Staged SSH execution needs rsync at both ends; shared mode retains the existing
filesystem-verification contract. CPU and memory requests must be explicit,
including through target/backend defaults.

## Main installer and uninstaller

First declare the platform and scheduler entry in the main `config.toml`, using
the execution section in the example above as a starting point. Without execution
configuration the installer creates no pool. It manages explicitly configured
local Qrun entries using the default handler. Multiple local entries share one pool.
The default budget is the current
process's available CPU count minus one (at least one) and 75% of physical RAM.
Override the budget explicitly:

```sh
./install.sh --config /ABS/config.toml \
  --qrun-cpus local/qrun=8 --qrun-memory-mb local/qrun=16384
```

This assumes platform `local` has a `qrun` entry. After configuring platform
`com30` with `transport = "ssh"` and `ssh_host = "agent.com30"`, and its `qrun`
entry with `executor = "qrun"` and the default handler, enroll its remote pool explicitly:

```sh
./install.sh --config /ABS/config.toml --manage-qrun com30/qrun \
  --qrun-state-dir com30/qrun=/home/USER/.local/state/coragent/qrun \
  --qrun-cpus com30/qrun=32 --qrun-memory-mb com30/qrun=65536
```

Replace USER. New SSH pools require the state directory and both budgets. SSH
uses existing configuration and noninteractive authentication. Only the standalone
program and pool request are sent, without model configuration or credentials.
Local execution uses `/usr/bin/python3`; SSH uses `python3`. Both require 3.11+
and must remain available independently of the replaceable Agent Conda runtime.
For systemd, enable lingering beforehand: `loginctl enable-linger USER`.
Without cgroup v2, `auto` selects portable. Use `--qrun-runtime com30/qrun=portable`
to select it explicitly. Existing pools retain their runtime across upgrades.

The installation plan and `--dry-run` show pools, hosts and budgets.
`--service-scope none` writes service files without starting queues; use normal
service mode when acceptance requires execution Jobs. Custom handlers are never
implicitly adopted. `--without-managed-qrun` uses independently managed pools.
Different SSH aliases are not recognized as the same host; use one canonical alias
to avoid duplicate resource budgets.
For an existing pool, `ssh_config` can be added, changed or removed during an
upgrade while retaining its transport, SSH host and state directory. Maintenance
and uninstall use the updated connection settings. Targets sharing the pool must
agree on `ssh_config`.

Upgrades require a drained queue and preserve history and stable handler paths.
Explicit capacity flags resize drained pools; omitted flags preserve the live budget. Failures attempt to restore the
previous queue service and configuration; unreachable remotes retain ownership
records for recovery on retry. Once application service activation begins,
failures retain the new version for forward repair by rerunning the installer.

The main uninstaller removes owned local and SSH queue services, preserving history
and calculation files by default. Unfinished Jobs block removal unless explicitly
cancelled:

```sh
./uninstall.sh --cancel-qrun-jobs
./uninstall.sh --purge-qrun-state
```

`--purge-qrun-state` removes owned queue state/history, never calculation work roots.
`--purge-all` includes queue state but does not imply cancellation of unfinished Jobs.
Independently installed queues remain outside the main uninstaller's ownership.

## CentOS 7 / portable runtime

Portable is internal to Qrun: the executor remains `qrun`, independently of local
or SSH transport. Linux child subreapers, process identity records and durable
cancellation fences manage Jobs. The detached daemon survives SSH disconnects.
Installation adds owned user crontab entries for reboot and a once-per-minute
daemon restart check, preserving unrelated entries. User crontab access and an
active system cron daemon are required; uninstall removes only this pool's entries.

Both runtimes provide FIFO admission, CPU/memory reservations, timeouts, cancellation,
durable results and recovery. Portable assigns distinct CPU affinity sets to concurrent
Jobs. It samples process-tree RSS and terminates over-budget Jobs. **Sampled RSS is
not a kernel memory limit**: allocation can overshoot between samples, shared pages
may be counted more than once, and this is not a sandbox for untrusted workloads.

Completion, cancellation and timeout reap detached and double-forked descendants
before recording a result. Daemon restart never reruns Jobs. If an external `SIGKILL`
kills a Job supervisor, unverifiable descendants leave the Job `unknown` with its
reservation retained for manual recovery; this is not equivalent to cgroup isolation.

```sh
python3 -B /home/agent/soft/Qrun/qrun.py \
  --state-dir /home/agent/soft/Qrun/state \
  install --runtime portable --cpus 112 --memory-mb 377221 \
  --work-root /home/agent/soft/Qrun/jobs
```

The main installer accepts `--qrun-runtime PLATFORM/ENTRY=portable`, using the same ownership,
upgrade, rollback and uninstall flows. With the installed program and `--state-dir`,
use `service status` to inspect the daemon. Use `pause`/`resume` to persistently control dispatch. `service stop` is temporary: enabled cron
will restart it within a minute. Uninstall for persistent removal. Handler `probe`
reports the selected runtime and memory enforcement mode.

## Independent systemd installation (optional)

The wheel includes a `qrun` command. Alternatively copy only
`backend/src/research_agent/jobs/qrun.py` to the host. It uses only the standard
library; no Agent or model configuration is needed. Run on each execution host:

```sh
loginctl enable-linger USER
python3 -B /absolute/path/qrun.py \
  --state-dir /home/USER/.local/state/coragent/qrun \
  install --runtime systemd --cpus 32 --memory-mb 65536 \
  --work-root /home/USER/DATA/qrun-jobs
```

Replace USER, paths and budgets. Installation verifies the user manager and
lingering, creates a private pool, copies the standalone program to an immutable
content-named path, then installs/enables/starts a user service. Its JSON response
includes `unit`, `unit_path`, `program` and the exact `handler` argv for CoRAgent.
`--no-start` writes files without starting services. `init` creates only a pool,
`serve` runs the daemon in the foreground, and `unit` prints a service definition.

Use one canonical pool per user per execution host. Workspaces and SSH aliases
must share that pool. Independent pools must not claim overlapping budgets.
Qrun does not reserve the machine against other users or software. Keep state
on a persistent local filesystem outside the allowed work roots.

## Scheduling and recovery

- Both CPU and memory must fit before dispatch; over-capacity requests fail.
  FIFO is strict: there is no backfill, preemption, GPU allocation, named queue,
  or PBS `select`. CPU quota limits time, not exclusive core ownership.
- The host's queue dispatches independently of SSH and CoRAgent. Daemon stop
  leaves separate calculation services running; restart reconciles first.
- SQLite commits identities/reservations before launch. Repeated requests return
  the original execution ID. Lost responses never authorize a duplicate run.
- Cancellation is persisted and fences late launches. Acknowledgment does not
  prove exit. A completed result recorded before cancellation keeps its outcome.
- Resources are released only after execution and cgroup descendants terminate.
  Missing evidence stays unknown and retains capacity. Remaining descendants are
  stopped even when the wrapper has already exited.
- Results survive unit collection and host reboot. A reboot without an existing
  result fails the active Job. Calculations are never automatically rerun.
- `queue_wait_seconds` remains a CoRAgent observation setting, not automatic
  expiration. First version retains history and does not place jobs across hosts.

## Resources, jobs, logs and dispatch controls

Use the installed `qrun` wrapper, or the installed program with its `--state-dir`.
Local and SSH operations use exactly the same commands:

```sh
qrun status
qrun resources
qrun jobs
qrun list
qrun list --json
qrun jobs --all --limit 20
qrun jobs --state failed
qrun show 4
qrun logs 4
qrun logs 4 --stream stderr --follow
qrun watch
qrun pause
qrun resume
qrun config --cpus 112 --memory-mb 377221
qrun cancel 4
ssh agent.com30 /home/agent/soft/Qrun/qrun resources
```

The operator commands above support `--json`. Query responses identify `qrun-view/1`. Job IDs are persistent, increasing numbers local to the pool (for example, `4`).
Submit/recover receipts expose the same number as a string in `scheduler_id`. Keep the target/pool with the ID.
`jobs` defaults to unfinished jobs in FIFO order; `--all` includes history, newest first.
Use repeatable `--state`, `--limit` (1–100) and `--offset` for filtering/pagination.
`watch` refreshes every two seconds; `--count N` bounds refreshes; Ctrl-C exits.
`list` preserves the original unbounded ledger JSON array, fields and ascending order,
in both terminals and pipes. `list --json` is an explicit equivalent. This legacy export
has no online/freshness metadata; use `jobs --all --limit 20` for human tables and
`jobs --all --limit 20 --json` for bounded automation.

Interactive terminals emphasize success in green, running/starting in cyan,
queued/paused/cancelled and waiting reasons in yellow, and failed/timed-out/unknown,
offline warnings and excess reservations in red. State labels remain visible;
color is supplementary. Redirected/piped output, `NO_COLOR` (including an empty value),
and `TERM=dumb` disable colors. JSON output never includes color sequences.
For example, use `NO_COLOR=1 qrun jobs`. Top-level help groups queries, controls and
installation commands; internal protocol and worker entrypoints remain callable
but are omitted from everyday help. Use `qrun --help-all` for automation and the full entrypoint list.

Resource views distinguish the configured budget, ledger reservations and actual usage.
Starting, running, stopping and unknown jobs all retain their reservations. Free queue
capacity is budget minus reservations, never budget minus sampled usage. Host logical
CPUs, allowed CPUs, CPU busy percentage, MemAvailable and load include external programs.
Host availability is not queue capacity, and the queue cannot reserve memory against
unrelated programs.

Job samples include CPU core equivalents, CPU seconds, memory, sampled memory peak and
timestamp. Portable samples process-tree RSS; systemd samples cgroup v2. Missing samples
and active samples older than three seconds are explicitly stale. Historical jobs retain
samples; older deployments may have no metrics or captured logs. Sampled RSS peaks are
not exact peaks or kernel hard limits. `show` also reports paths, wait/runtime duration,
exit code, error, cleanup/cancellation state and waiting reason (paused, insufficient
resources, FIFO predecessor, exceeding reduced budget, or ready).

`pause` persists across daemon restarts while observation, cancellation and existing jobs
continue. Online budget reductions leave running jobs intact and report overcommitment;
new dispatch waits for capacity. Oversized queued jobs remain in strict FIFO and can block
followers until capacity increases or the operator cancels them. Portable CPU capacity
cannot exceed the process's allowed logical CPUs; memory cannot exceed physical RAM.
**Code upgrades still require a drained queue; ordinary budget changes do not.**

Read commands fall back to the ledger when the daemon is unavailable and label the view
OFFLINE/stale. Mutations require the daemon. Logs prefer staged application output under
logs/stdout.log or stderr.log, falling back to Qrun-captured direct script output. Only fixed
regular log files are readable, without symlink traversal; each read is bounded to 64 KiB.
Follow uses file identity/offset and ends after terminal output is drained. Logs are retained
on disk without automatic rotation; provision disk space for verbose workloads.
CoRAgent `job_probe` exposes the same overview; Job status diagnostics include usage and wait reasons.
Missing per-job samples carry `available=false` and null measurement fields. Aggregated
`job_usage.cpu_cores` and `memory_mb` retain their original meaning: sums of fresh samples,
which may cover only part of the queue. New `complete`, `total_cpu_cores` and `total_memory_mb`
make the distinction explicit: totals are null if any active sample is unavailable/stale or
the daemon is offline. An online queue with no active jobs has complete zero totals.

## Machine interface contract

Use human tables for inspection and explicit `--json` for automation. Output format does
not depend on whether stdout is a terminal; only color does. No operator command prompts
for confirmation. `--help` and `--help-all` are text discovery interfaces, even with `--json`.

### Operator JSON and exit codes

`status`, `resources`, `jobs`, `show`, `logs`, `watch`, `pause`, `resume`, `config` and
`cancel` support `--json`. Success retains every existing top-level result field and adds
`cli_version: "qrun-cli/1"`, `ok: true`, and `command` (the invoked CLI command).
Errors use the same CLI version, `ok: false`, `command`, and an `error` object with
`code`, `message`, `retryable`, `action_outcome`, and `recovery`. Parse errors have
`command: null`. Consumers must tolerate additional fields. The CLI version is distinct
from `view_version: "qrun-view/1"` and the handler's `schema_version`.

Exit status is 0 for a successful response, including an explicitly stale offline read;
1 for an operation error; 2 for argument parsing errors; 130 for an interrupted JSON
command. Always check the JSON status as well. stdout contains only JSON results; help
and the legacy `list` export are deliberate exceptions to this CLI object format.
`watch --json` and `logs --follow --json` emit **JSON Lines**, flushed after every record;
a later failure emits one error record and exits nonzero. Use `watch --count 1 --json`
for a bounded observation. The nested overview and jobs views are separate snapshots.

```sh
qrun jobs --all --limit 20 --offset 0 --json
qrun show 4 --json
qrun logs 4 --stream stderr --bytes 4096 --json
qrun watch --count 1 --json
qrun cancel 4 --json
```

A usage error, for example `qrun jobs --limit invalid --json`, returns exit 2:

```json
{"cli_version":"qrun-cli/1","ok":false,"command":null,"error":{"code":"invalid_arguments","message":"argument --limit: invalid int value: 'invalid'","retryable":false,"action_outcome":"not_submitted","recovery":"Check qrun COMMAND --help and correct the arguments."}}
```

| Error code | Meaning and recovery |
| --- | --- |
| `invalid_arguments` | Correct the arguments using command help. |
| `job_not_found` | Check the execution host, pool and numeric ID. |
| `state_unavailable` | Local state/config/ledger could not be read; check installation, paths and permissions. |
| `qrun_unavailable` | The daemon could not be reached or its acknowledgment was lost. A mutation may have applied. |
| `response_too_large` | Reduce the page or log chunk size. |
| `qrun_error` | Other daemon/runtime rejection or failure; inspect the message and current state. |
| `interrupted` | The client was interrupted; an in-flight mutation may have applied. |

`retryable` is diagnostic, **not permission to repeat a mutation**. Preserve daemon
`action_outcome` values; `unknown` is not a rejection. A CLI parse failure with
`not_submitted` happened before dispatch. After a lost control acknowledgment, query
`config`, `status` or `show` to reconcile before deciding what to do next. Control
commands do not automatically retry. For submissions, use the identity/recover workflow below.

### Observations, units and pagination

- IDs are strings containing pool-local increasing numbers. Keep the execution host and
  pool identity alongside each ID. CoRAgent workspace Job IDs are a different namespace.
- `online` confirms contact with the daemon, not independent verification of every process.
  `source` is `daemon` or `ledger`; `state_basis` is always `ledger`. `observed_at` is when
  the view was built, not when each process was inspected. Offline views set `stale=true`
  and preserve `last_heartbeat` (possibly null). A saved `running` state is not liveness proof.
- CPU budgets are logical CPU counts; `cpu_cores` is sampled core-equivalent usage. All
  memory fields ending in `_mb` use **MiB**, time durations use seconds, timestamps are UTC
  ISO 8601. Missing values are null or explicitly unavailable; never infer zero from them.
- `job_usage.complete` and the total fields describe current aggregate coverage; per-job
  `usage.available`, `stale`, `sampled_at` and `final` describe individual measurements.
  Legacy fresh-sample sums must not be treated as complete totals without checking coverage.
- `jobs` defaults to unfinished jobs in FIFO order. `--all` includes history, newest first;
  terminal-only `--state` filters also sort newest first. Responses include `order`, `total`,
  `limit`, `offset`, `has_more` and `next_offset`. Continue with `next_offset` until null.
  Pages are live snapshots, not a stable export: submissions and state changes between calls
  can move rows. Deduplicate by ID or rescan when a consistent inventory is needed.
- `logs` returns bounded `text`, byte `offset`, `identity`, `eof`, `reset` and `finished`.
  To continue, pass the returned `--offset` and `--identity`; appends then yield only new
  bytes. A changed file or truncation restarts at byte zero and sets `reset=true`.
  UTF-8 decoding replaces incomplete/invalid bytes; this is a text view, not binary export.
- Cancellation success means `accepted=true`, not termination. Poll `show ID --json` and
  check `job.execution_finished`, `state`, `cancel_requested` and `cleaned`. A completed
  result may win a cancellation race. `unknown` retains reservations. A scheduler success
  does not establish the scientific validity of outputs.

### Handler protocol and recovery

`qrun --state-dir /absolute/pool handler` reads one JSON object on stdin and writes one
`coragent-external-job/1` response. Its existing envelope and exit-0 protocol-error
behavior remain unchanged; do not expect CLI metadata or use exit status alone to judge
success. See [External Jobs](EXTERNAL_JOBS.md) for the submission/status contract.

Example submit request (paths must already exist inside an allowed execution-host work root):

```json
{"schema_version":"coragent-external-job/1","action":"submit","request_id":"example-001","job_id":"example-job","cwd":"/srv/qrun/jobs/example","script":"/srv/qrun/jobs/example/run.sh","resources":{"cpus":1,"memory_mb":512},"timeout_seconds":60}
```

Save this exact request before sending it. A successful submission returns `scheduler_id`.
After response loss, reuse **all identity fields** (`request_id`, `job_id`, `cwd`, `script`,
`resources`, `queue`, `timeout_seconds`) and change only `action` to `recover`. A found
record returns the original scheduler ID; do not generate a new request ID to retry.
Status and cancellation use the same identity fields with `action: "status"` or `"cancel"`
and the returned `scheduler_id`. Reusing an ID with different content is rejected.
`found=false` is a point-in-time absence observation, not authorization for a new identity;
repeating the same valid submit identity remains deduplicated by the daemon.

Operator commands and handler requests share the queue implementation:

| CLI command | Handler action and fields |
| --- | --- |
| `status` | `overview` (handler `status` instead requires a full job identity) |
| `resources` | `resources` |
| `jobs` | `jobs`: `all`, `states` array, `limit`, `offset` |
| `show ID` | `show`: `identifier` |
| `logs ID` | `logs`: `identifier`, `stream`, `bytes`, optional `offset`, `identity` |
| `pause`, `resume` | `pause`, `resume` |
| `config` | `overview` for reads; `configure` with `cpus` and/or `memory_mb` for changes |
| `cancel ID` | `cancel_job`: `identifier` (handler `cancel` uses a full job identity) |

Every handler request includes `schema_version`. Direct handler calls require a running
daemon; the read-only offline fallback belongs to the operator CLI. `maintenance`, `serve`,
`_run`, `_portable-run` and `service ensure` are installer/daemon entrypoints, not alternate
submission APIs. Discover them with `--help-all`, but use `handler` for machine submissions.

## Operations

Use the installed `program` with the same `--state-dir` and `jobs` or `list` (`list --json` for a full ledger export), or
`cancel 4`. Normal CoRAgent Job status/cancel/reconcile/collect APIs still
apply. Queue records include local execution paths and must remain private.

For independently installed pools, drain/cancel work, stop the recorded queue service, and run
`install` again with the same settings. A live daemon rejects reinstallation.
`init`/`install` will not overwrite pool settings. Resize the live budget using
`config`; do not edit config.json while the daemon is running. Never delete the ledger to
resolve uncertain execution. For removal, drain/cancel, stop and disable the
recorded unit, remove its `unit_path`, then run `systemctl --user daemon-reload`.
Keep history as needed. Uninstalling CoRAgent does not remove this independent
queue or stop its computations.

Deterministic tests cover FIFO, contention, cancellation, response loss,
restart/reboot, timeout, real wrappers and simulated SSH. The system-services
lane checks real resource limits, recovery and detached-descendant cancellation
using isolated, registered services and cleanup auditing. This does not certify
connectivity or installation on any particular remote server.
