# Connect TRI to CoRAgent Jobs

## Contents

- [Handler environment](#handler-environment)
- [Resource and state handling](#resource-and-state-handling)
- [Submission and diagnostics](#submission-and-diagnostics)
- [Verify each compute node and backend](#verify-each-compute-node-and-backend)

Use the bundled [tri.py](../scripts/tri.py) as the handler for a scheduler entry
with `executor="tri"`. It needs Python 3 and the native `tri_sub`, `tri_stat`, `tri_del`
commands on the submission host. It reads one JSON request from stdin and writes
one normalized JSON response to stdout. Supported actions are `probe`, `submit`,
`status`, `cancel` and `recover`.

For CoRAgent and TRI on the same login node, set the platform's `transport="local"`
and `storage.work_root` to a persistent directory shared with compute nodes.
Set the scheduler entry's `handler` to the submission host's Python and this
script's installed absolute path.
See [target configuration and protocol](../../../../docs/EXTERNAL_JOBS.md) for a full
configuration. Research calculations continue through `job_start`, `job_status`,
`job_reconcile` and `job_collect`.

For native task states, cancellation confirmation and log inspection, read [TRI task diagnosis](tri-diagnosis.md). For server or node deployment, use [TRI operations](../../../../docs/TRI_OPERATIONS.md).

## Handler environment

Set these in the scheduler entry's `handler_environment` as needed:

| Variable | Use |
| --- | --- |
| `TRI_SOCKET` | Login host's queue socket |
| `TRI_SERVER_ADDR` | TCP endpoint when using TCP instead of a local socket |
| `TRI_AUTH_TOKEN` | TCP authentication; use the installation's protected credential configuration |
| `CORAGENT_TRI_SUB`, `CORAGENT_TRI_STAT`, `CORAGENT_TRI_DEL` | Absolute paths when the native commands are not on PATH |
| `CORAGENT_TRI_NODE` | Optional fixed compute-node name; otherwise TRI selects a node |

For SSH submission, install the same handler on the login host and configure its
paths and connection environment there. The Job protocol and helper are identical.

## Resource and state handling

`resources.cpus`, `memory_mb` and `gpus` become `--cpu`, `--mem` and `--gpu`.
The effective Job timeout becomes `--timeout`. TRI selects nodes and resources
without a PBS/Slurm queue selector. The wrapper executes in the shared work
directory and writes the scientific process's logs to `logs/stdout.log` and
`logs/stderr.log`; TRI's own task logs go to `logs/scheduler.stdout` and
`logs/scheduler.stderr`.

For new submissions, the handler hashes the staged wrapper on the submission
host and carries the expected digest and verification command in TRI's task argv.
On the allocated node, missing or different wrapper bytes fail with exit 125 and
`CORAGENT_EXECUTION_ERROR=execution_script_changed`, before that file can execute.
The wrapper then checks the declared input files before starting the calculation;
changed or missing input bytes fail with `CORAGENT_INPUT_ERROR=staged_input_changed`.
This prevents an old file at the same absolute path from silently running another
calculation. It does not repair mismatched mounts or transfer files between TRI nodes.

Submission uses the Job's stable request identity as both `--request-id` and
`--external-id`. Recovery queries `tri_stat --external-id` for the original task.
The helper reports `wait` as queued, `run` as running, and `lost` as unknown.
Running cancellations remain pending until TRI reports completion; a cancellation
closed by lease expiry without a process exit remains unknown. This keeps
recovery focused on the original attempt.

To check the handler's endpoint without submitting a calculation, set
`TRI_JOB_HANDLER` to this installed script and run in the configured environment:

```bash
python3 "$TRI_JOB_HANDLER" <<'JSON'
{"schema_version":"coragent-external-job/1","action":"probe"}
JSON
```

Use `storage.file_mode="shared"` and set `storage.work_root` to the shared workspace parent to run
directly in each workspace Job directory. Both local and SSH submission support
this mode. The default `storage.file_mode="staged"` retains input/output transfers.
Storage probes and compute-node guards belong to the generic runtime; the TRI
handler adds the wrapper check to its native command. Both modes use the same
external Job protocol.

## Submission and diagnostics

A successful TRI submission receipt must contain `driver="external"` and a non-empty `scheduler_id`; successful local handler execution alone does not prove admission to the TRI queue.

An explicit native `invalid_request` is recorded as a failed Job with
`action_outcome=not_submitted`. A lost response, `request_id_reused` or
`external_id_conflict` remains ambiguous: reconcile the existing Job before
considering replacement work. Native error code and retryability remain available;
retryability alone is not permission to submit again.

Submit/recovery responses must match the stable external identity. Status and
cancellation also check the original numeric ID. A mismatch remains unknown and
blocks cancellation. TRI currently cancels by numeric ID only, so the helper's
lookup and cancellation are not an atomic operation; do not reset/replace a queue
while operations are in flight.

Diagnostics show the observed node, requested CPU/memory/GPU resources, effective
memory and swap limits, and assigned CPU/GPU sets separately. A request is not
evidence of allocation. `resource_failure` distinguishes `memory_limit` from
`resource_enforcement` failures, while ordinary command failures remain null.
When `CORAGENT_TRI_NODE` pins a target, `requested_node` and `node_match` make the
actual assignment explicit. While queued or held, `wait_seconds` is the age since
TRI's `created_at`; missing timestamps remain unknown. This feeds the existing
`queue_wait_seconds` Monitor threshold, with one queue-delay event per Job. Normal
queue/running changes do not wake the Agent. Running cancellation is terminal only
with completion evidence and `cancel_confirmed=true`; `completion_reason=lease_expired`
is not stop proof.

## Verify each compute node and backend

A successful login-host environment probe or one arbitrarily placed Job does not
verify every compute node. Use the explicit acceptance entrypoint for a target
configured with this TRI handler. Set `CORAGENT_PYTHON` to the installed CoRAgent
runtime Python and `CORAGENT_PACKAGE_ROOT` to its package directory; select a fresh
private `TRI_ACCEPTANCE_DIR` (repository tests must use `local_debug/`):

```bash
"$CORAGENT_PYTHON" "$CORAGENT_PACKAGE_ROOT/packaging/coragent_packaging/installer/verify_tri_nodes.py" \
  --config "$HOME/.config/coragent/config.toml" \
  --package-root "$CORAGENT_PACKAGE_ROOT" --directory "$TRI_ACCEPTANCE_DIR" \
  --platform compute --scheduler-entry main --nodes '["fed1","fed2"]' --timeout 180
```

Replace the target and node names with the deployment's exact names. This submits
bounded acceptance Jobs, using private per-node configurations with
`CORAGENT_TRI_NODE`; the active configuration is unchanged. For every backend with
a packaged acceptance check, verify outputs and require the observed node to match.
`report.json` records each node's tested and untested backends, actual execution
node and resource diagnostics. Unselected nodes remain unverified. A missing check,
failed check or missing/mismatched node cannot produce a full success exit code.
These checks establish environment readiness, not scientific accuracy or performance.

Successful shared acceptance workspaces and private configuration copies are removed.
Failures retain the workspace/configuration needed for diagnosis and reconciliation;
bounded cancellation waits for confirmation, and pending cancellation retains evidence.
Keep these files private because configurations can contain connection credentials.
The core installer does not automatically run this cluster acceptance.
