# External tasks through documented commands

[简体中文](EXTERNAL_JOBS.zh-CN.md)

An external execution target lets a Skill or installation supply the small command
bridge needed for a queue. CoRAgent manages Job identities, durable receipts,
staging, restart recovery and collection. The bridge owns native submission
syntax and state interpretation. It is an executable program, not a Python plugin
imported into the CoRAgent process.

## Configure a target

On a login node running both CoRAgent and the queue CLI:

```toml
[execution]
default_target = "compute"

[execution.targets.compute]
scheduler = "tri"
location = "cluster"
driver = "external"
transport = "local"
cluster_name = "compute"
work_root = "/absolute/shared/coragent-jobs"
handler = ["/usr/bin/python3", "/absolute/coragent/skills/core/batch-schedulers/scripts/tri.py"]

[execution.targets.compute.handler_environment]
TRI_SOCKET = "/absolute/runtime/tri/server.sock"

[execution.targets.compute.submission.resources]
cpus = 4
memory_mb = 4096
```

Replace example paths with this installation's paths and create `work_root`.
Add scientific software bindings under `execution.targets.compute.bindings` as
for other execution targets. `transport = "local"` means commands run on the
CoRAgent host; the queue chooses the compute node. Multiple local command targets
can coexist with a direct process/systemd target and carry distinct cluster names.

For submission from another host, change `transport` to `ssh` and set `ssh_host`
and optionally `ssh_config`. `handler` and `work_root` are paths on that host.
By default, SSH targets use rsync to stage and collect files. Local targets copy between the
controller Job directory and `work_root`; this directory must be visible at the
same path on compute nodes. The generic runtime does not provision shared mounts.
Local process/systemd targets use their built-in drivers. Batch schedulers use
external handlers.

`handler_environment` configures the submission CLI separately from the
calculation environment. Prefer existing protected service/connection
configuration for credentials. The target configuration digest is saved with the
Job; changing its endpoint or handler prevents old Jobs from being silently routed
to the replacement target. Restore the original target to reconcile them.

## Shared workspace execution

File handling is independent of command transport and scheduler. `file_mode`
defaults to `"staged"`, preserving the copying behavior above. If the controller,
submission host and compute nodes share the workspace filesystem, configure:

```toml
[execution.targets.compute]
scheduler = "tri"
location = "cluster"
driver = "external"
transport = "local"
file_mode = "shared"
work_root = "/home/iaw/DATA/coragent/workspaces"
handler = ["/usr/bin/python3", "/absolute/coragent/skills/core/batch-schedulers/scripts/tri.py"]
```

Merge this target into `config.toml`; retain the required connection environment
and scientific bindings. PBS, Torque, Slurm and custom handlers use the same
option. `transport="ssh"` is also supported when that submission host shares
the workspace. In shared mode `work_root` is an allowed workspace parent, not a
second execution store. Each Job runs directly in its workspace's
`runs/jobs/<job-id>/` directory (or its requested subdirectory).

Mount aliases such as `~/DATA` are resolved on the controller; the resulting
absolute Job path must be valid on every participating node. Different mount
paths are not translated. Before submission, a temporary file round-trip checks
that the command host sees the same writable storage. The wrapper checks its
per-Job marker on the allocated compute node before starting the calculation.
Success requires the compute node's start and exit evidence to be visible to
the controller as well as scheduler success. Missing evidence remains unknown.
There is no automatic fallback to staging when these checks fail.

The ordinary Job API still snapshots declared inputs into the Job directory;
shared execution skips the second transfer to an execution store. Direct
`JobSpec` callers must place inputs and stdin in that directory first. Collection
checks required files, sizes and hashes in place and rejects control-file outputs
and symlink escapes. It neither copies results onto themselves nor deletes the
workspace. Existing backend `scratch_root` and `{scratch}` settings can keep
temporary calculation data on node-local storage; preserve results in the Job
directory. This option does not add automatic scratch deletion.

Receipts retain the file mode and execution directory. Keep the original target
configuration and shared directory available for status, cancellation, recovery
and collection. Installation acceptance uses its own temporary workspace under
the shared root, deletes it after successful checks, and retains failed or
unresolved runs for diagnosis and recovery.

## Handler protocol

CoRAgent executes `handler` as an argv, sends one JSON object on stdin and expects
one JSON object on stdout with exit code zero. Diagnostics go to stderr. Both
objects contain `schema_version: "coragent-external-job/1"`. The same executable
handles these `action` values:

| Action | Input | Required response |
| --- | --- | --- |
| `probe` | Protocol and action | `available` boolean; optional `error` |
| `submit` | Stable `request_id`, `job_id`, execution `cwd`, absolute `script`, `resources`, optional `queue`, effective `timeout_seconds` | Nonempty string `scheduler_id` |
| `status` | Original submission fields plus `scheduler_id` | Matching `scheduler_id`, normalized `state`, exit/finish evidence |
| `cancel` | Original submission fields plus `scheduler_id` | Matching `scheduler_id`, `accepted` boolean |
| `recover` | Original submission fields and stable `request_id` | Existing `scheduler_id`, or `found: false` after a conclusive lookup |

The wrapper already contains the calculation argv, environment, stdin, timeout
and stdout/stderr redirection. Submit that wrapper in the supplied `cwd`. It
writes calculation logs under `logs/` and exit evidence in the execution
directory. GPU visibility assigned by the scheduler is preserved for external
Jobs. The Job runtime uses handler observations to determine completion.

States are `submitted`, `queued`, `held`, `running`, `succeeded`, `failed`,
`cancelled`, `timed_out`, and `unknown`. A terminal response requires
`execution_finished: true`; success also requires integer `exit_code: 0`.
Optional fields are `started_at`, `finished_at`, `error`, and a `diagnostics`
object. A cancellation acknowledgment is followed by status observation. Report
pending cancellation as a nonterminal state until execution has ended.

```json
{"schema_version":"coragent-external-job/1","scheduler_id":"42","state":"succeeded","exit_code":0,"execution_finished":true,"diagnostics":{"node":"compute-a"}}
```

`recover` is a lookup, using the stable identity recorded before submission.
After a lost submission response, `job_reconcile` calls it without resubmitting.
An unavailable service, malformed response, or ambiguous result remains unknown.
Scope native idempotency/workflow identifiers to the supplied `request_id`, which
distinguishes equal Job numbers in different workspaces and targets.


A handler may return a structured error with exit code zero:

```json
{"schema_version":"coragent-external-job/1","error":{"code":"invalid_request","message":"invalid resource request","retryable":false,"action_outcome":"not_submitted"}}
```

Use `action_outcome: "not_submitted"` only with proof that no task was accepted.
CoRAgent persists this as a failed Job with no scheduler ID; `job_start` immediately
returns `state: "failed"`, `action_outcome: "not_submitted"` and an error. The full
error remains in `metadata.submission_error`. Replays, Monitor and collection use
that durable result without submitting again. Corrected work needs a new request
identity and the ordinary repeat policy when applicable.
Use `action_outcome: "unknown"` for transport loss, identity conflicts or uncertain
acceptance. `retryable` preserves the native diagnostic; it never authorizes an
automatic resubmission. Unstructured exceptions also require reconciliation.
Handlers must validate both workflow identity and scheduler ID before operating
on a task; a numeric ID alone is not sufficient after queue replacement.

## Skills and extension authors

Describe resource selection, job-script conventions and native CLI usage in the
Skill. Use a small helper only where persistent observation requires conversion
to this protocol. A helper can be written in any executable language.

The bundled [TRI helper](../skills/core/batch-schedulers/scripts/tri.py) calls
`tri_sub`, `tri_stat` and `tri_del` and uses TRI's external identity for recovery.
Its [usage reference](../skills/core/batch-schedulers/references/tri.md)
documents command overrides and node selection.

The [batch scheduler Skill](../skills/core/batch-schedulers/SKILL.md) owns both the TRI
handler and the PBS/Torque/Slurm handler. Its [target reference](../skills/core/batch-schedulers/references/targets.md)
covers native commands, retained accounting and durable submission recovery.
Scheduler-specific changes belong in these scripts and their documentation.

Validate a new helper with queued, running, successful, failed, timeout and
cancellation cases, plus a controller restart and a lost submit response. Check
declared output collection from a separate execution directory. Use an isolated
queue or deterministic command fixtures, and keep this repository's test state
under `local_debug/`.

## Per-job resources

Configured target and backend resources are fallback defaults, not capacity limits.
Prepare executors and scripts with `--cpus 12 --job-memory-mb 16384 --walltime 02:00:00`
before the `--` separator. Optional `--gpus`, `--queue` and `--queue-wait-seconds`
use the same submission resolver; each target still enforces supported fields and queue permissions.
TRI supports CPU/memory/GPU requests, not `queue` or PBS `select`.

Resolution is per field: target defaults → backend defaults → explicit program input
requirements → this Job's request. Registered program contracts validate contradictions
before probing/submitting; an explicit request cannot silently rewrite an explicit input.
Direct Jobs and validators accept `submission: {"resources": {"cpus": 12, "memory_mb": 16384}}`.
Python callers use the same `submission=` argument on `prepare` and `prepare_script`.
Do not combine direct `submission` with resource fields in metadata.

Gaussian/PySCF reserve at least 256 MiB and 10% of total memory for process overhead.
This is a default budget, not a peak-memory guarantee. Explicit Gaussian files remain
unchanged. JSON path/electronic settings may omit threads and Gaussian memory; runners
then use the pinned Job allocation. Current scan, NEB and crossing evaluations are serial,
so image/surface counts do not multiply the CPU request. Unsupported parallel settings
are rejected. xTB and CREST threads follow the same allocation.

Prepared resources participate in work identity, execution fingerprints and receipts.
Changing them requires a new preparation; `job_start` rejects overrides of request files
or prepared references. Software, input hashes and configuration drift remain checked.
Scripts receive thread environment defaults, but their internal parallelism is explicitly
unverified. Memory and CPU enforcement depend on the selected runtime/scheduler.

TRI owns node capacity, queueing and allocation. CoRAgent does not treat a busy node or a
4-CPU default as a 4-CPU hardware limit. A 12-thread shared-memory job needs one eligible
node with sufficient capacity; capacities on separate nodes are not added together.

Failures during validation, probing or staging, before invoking the submit handler,
are also recorded as `not_submitted` with `submission_error.phase: "preparation"`.
Their recovery and collection use local failure evidence without contacting the
unavailable queue or storage. Once submission has been invoked, transport errors
remain ambiguous. Existing execution evidence is never classified as a fresh
preparation failure.
