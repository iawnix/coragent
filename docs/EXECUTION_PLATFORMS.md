# Named execution platforms

[简体中文](EXECUTION_PLATFORMS.zh-CN.md)

CoRAgent separates a platform's connection, shared software and storage from its scheduler entries.
The sole public configuration is `execution.schema_version = 2`. Selection is a structured object:
`{"platform":"Com30","scheduler_entry":"qrun"}`. `Com30/qrun` is a derived adapter key used in
installation options and Job records; it is not another configurable label.

## Configuration

```toml
[execution]
schema_version = 2
default_platform = "FEDCluster"

[execution.platforms.FEDCluster]
transport = "local"
default_scheduler = "tri"
storage.work_root = "/ABS/fed/jobs"
storage.file_mode = "staged"

[execution.platforms.FEDCluster.schedulers.tri]
executor = "tri"
handler = ["/ABS/python3", "/ABS/tri.py"]

[execution.platforms.Com30]
transport = "ssh"
ssh_host = "agent.com30"
default_scheduler = "qrun"
storage.work_root = "/home/agent/soft/Qrun/jobs"
storage.file_mode = "staged"

[execution.platforms.Com30.schedulers.qrun]
executor = "qrun"
# The main installer replaces this for a managed pool.
handler = ["qrun", "handler"]
submission.resources = {cpus = 4, memory_mb = 4096}
limits = {cpus = 112, memory_mb = 377221, max_in_flight = 20}

[execution.platforms.Com30.bindings.gaussian]
command = "/ABS/gaussian/g16"
activation_script = "/ABS/gaussian/activate.sh"

[execution.platforms."1WCluster"]
transport = "ssh"
ssh_host = "agent.1w"
enabled = false
```

Replace `/ABS` paths with verified installations. This example does not deploy services or assert that
software is installed. Leave 1WCluster disabled until its scheduler and storage are established.
For an independently installed Qrun pool, replace the default handler with the
exact argv returned by that installation, including its state directory; the
main installer's management options do not take ownership of that pool.

Platform IDs/aliases match without case sensitivity; scheduler entry IDs are exact. An explicit entry wins;
otherwise the platform's default entry applies. Scheduler-type selection is restricted to the selected
platform. Entries share `python`, `bindings`, `storage`, `submission` and `allowed_queues`. An overridden
software binding replaces the whole binding; storage and resource defaults merge by field. Entries cannot
override the platform transport or SSH endpoint. Queue permissions and entry resource limits apply after
merging. CPUs are logical CPUs and `memory_mb` is MiB.

Python bindings retain explicit Conda executable, prefix and lock reference. Native software uses command,
activation script and environment variables. `storage.scratch_root` supplies a default for software scratch.
Keep handler credentials in the installation credential store; discovery does not expose their values.

## Commands and task execution

- `job_platforms` lists platforms, entries, software bindings, effective storage, submission defaults, limits
  and whether storage/software values came from the platform or entry. Binding presence is not readiness.
- `job_resolve_target` resolves the structured selection and pins its route digest.
- `job_resources` queries the selected handler. Qrun reports pool capacity, reservation, free capacity,
  observed usage and enforcement. Other current handlers return unknown capacity; unknown is not zero.
- Preparation uses `--platform Com30 --scheduler-entry qrun`. Scientific `--executor chemical.xtb`
  selects a recipe; it does not select the scheduler. Process variables use only `environment`.
- `job_start` checks selection, software evidence, input hashes, resources and task admission budgets.
  Prepared requests cannot override their pinned execution fields. Status/cancel/collect/reconcile use
  the submitted Job's recorded route even after configuration changes.
- Ordinary bash continues to execute on the controller. Platform selection does not SSH arbitrary bash.

Ordinary research tasks do not require a calculation platform. `task_begin` without execution fields
persists `execution_target`, `execution_selection` and `execution_policy` as null. Workspace, research
records, context management and local bash remain available. Platform diagnostics do not bind a Task.

Before preparing or directly submitting the first calculation, read `task_read` and bind an unbound Task:

```json
{
  "action": "bind_execution",
  "expected_revision": 1,
  "execution_target": {"platform": "Com30", "scheduler_entry": "qrun"}
}
```

Send this to `task_update` using the actual current revision. The existing task sources constrain the
selection; use `execution_intent` to quote an explicit scheduler instruction. Omitting the target resolves
the configured default under those constraints. Missing configuration fails this calculation operation
without altering the Task. If calculation is already intended, `task_begin` may instead receive execution
fields and bind immediately. A bound destination cannot be replaced by another `bind_execution`: changing
user requirements uses `refine` with a new source, while correcting a misread original instruction uses
`correct_execution` with that instruction and an audit reason.

A Task can contain a durable execution plan with independently placed work items. `task_update`
`set_execution_plan` binds an unbound Task atomically with its first plan, optionally accepting the same
execution fields. An existing binding supplies the plan policy; an existing plan pins that policy.
Then use `select_execution_item` and `complete_execution_item`.
See the [plan contract and examples](../skills/core/execution-platforms/references/plans.md).
Job Manager remains the sole authority for actual execution state; `task_read.execution_progress`
projects ready/blocked, native Job states, collecting and validating from those records.

Task limits are optional: omitted/null `max_in_flight`, `max_attempts`, and `max_retries_per_work`
impose no task concurrency, cumulative Job count, or per-work retry cap, respectively. The legacy name
`max_attempts` means total Jobs, including successes; it is not a failed-Job retry allowance. A retry cap
requires a stable `work_id`; zero permits the initial Job only. Existing numeric policies retain their limits.
Task and per-entry limits are checked under the workspace transaction lock. Entry limits cover that
workspace; Qrun/schedulers enforce shared pools across workspaces. Unknown/conflicting Jobs retain slots.
Capacity responses are `accepted:false`, with `execution_task_capacity_reached` or
`execution_entry_capacity_reached`, counts and occupying Job IDs. They do not create or enqueue a Job.
Continue independent work; otherwise wait for owned Jobs with `task_update action=wait`, then resume
the same request. Reconcile unknown/conflicting Jobs first. Explicit cumulative/retry caps return
`execution_task_job_limit_reached` / `execution_work_retry_limit_reached`, never a generic budget error.
`task_read.execution_usage` exposes limits, cumulative usage and occupying Jobs.

Use `task_update action=set_execution_limits` with `execution_limits`, a reason, current revision and
new user `source_submission_ids` to adjust limits even with an existing plan. Omitted fields stay unchanged;
null removes a cap. The audit retains old/new limits and sources; Jobs, artifacts and placements are preserved.
A task blocked for `budget_exhausted` resumes after the adjustment; other blockers and pauses remain in force.
A settled failed/timed-out/cancelled item can be retried with the same item/work ID and a new request identity.
Identical computation still requires the `repeat` predecessor/reason/budget declaration. Successful or
uncertain items cannot be retried this way; submitted plan definitions remain immutable.
For prepared files/references, `repeat` derives a stable attempt identity without changing the request
bytes or work ID. Repeating the same declaration reuses that attempt; another retry cites its predecessor.

Optional `automatic_placement=true` permits selection only among an item's explicit `candidates` inside
the task's authorized placements. The item declares `backend` and CPU/memory requirements. Selection
requires a configured binding and known sufficient free capacity, excludes paused/stale observations,
and accounts for other items placed in that plan. The selected route and observation reason are recorded.
Software is verified during preparation. GPU capacity and non-Qrun capacity are currently unknown, so
these cannot justify automatic placement; explicitly selected PBS/Torque/Slurm/TRI entries remain usable.
Resource snapshots are estimates, not reservations or guarantees of immediate execution.

Dependencies are released only after a successful Job is collected and a current scientific Result cites
every selected output Artifact. The preparer stages these immutable payloads at
`inputs/artifacts/<artifact_id>/payload`, verifies their hashes and records existing Artifact provenance.
The controller relays inputs and collected outputs; equal remote path strings do not imply shared storage.
Rsync uses checksums, partial transfer files and delayed publication. Retry collection after transfer failure;
do not rerun completed science. Scientific interpretation remains the responsibility of domain methods.

## Installation and operation

Publish the complete configuration through the main installer (`--config`, or explicit `--job-config`
import). Scientific environments are prepared independently and referenced by platform/entry bindings.
Existing PBS/Torque/Slurm/TRI services remain externally operated. Qrun installation and removal use the
main installer's ownership registry for both local and SSH hosts; see [Qrun operations](QRUN.md).

Installer options identify entries as `PLATFORM/ENTRY`, for example:

```sh
./install.sh --config /ABS/config.toml --manage-qrun Com30/qrun \
  --qrun-state-dir Com30/qrun=/home/agent/soft/Qrun/state \
  --qrun-cpus Com30/qrun=112 --qrun-memory-mb Com30/qrun=377221 \
  --qrun-runtime Com30/qrun=portable
```

Use this only to provision an installer-owned pool, not to take over an independently installed handler.
Uninstallation removes only owned services/environments; it does not stop external schedulers or delete
research work roots. Active Qrun Jobs prevent removal unless cancellation is explicitly requested.
Shared environment bindings refer to the same installed prefix; removing a configuration entry does not
uninstall that environment.

Flat target configuration and process/systemd executors are rejected. There is no automatic migration,
legacy selector alias, or second editable target table. The durable Task and dispatch-intent versions are
`coragent-user-task/6` and `job_intent/4`; deploy matching runtime/configuration together after settling
work under the previous version. New-version Jobs preserve original routes; this is not conversion of old receipts.

The [execution-platforms skill](../skills/core/execution-platforms/SKILL.md) owns selection, environments,
storage and handoff. [batch-schedulers](../skills/core/batch-schedulers/SKILL.md) owns scheduler commands.
TRI deployment/maintenance lives in [ordinary operations documentation](TRI_OPERATIONS.md).
On CentOS 7, Qrun portable mode still uses CPU affinity and RSS sampling, not cgroup hard isolation.
Its lifecycle remains independent of PBS. This source refactor does not register or redeploy production hosts.
