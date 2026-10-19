# Connect TRI to CoRAgent Jobs

Use the bundled [queue.py](../scripts/queue.py) as the handler for a generic
external target. It needs Python 3 and the native `tri_sub`, `tri_stat`, `tri_del`
commands on the submission host. It reads one JSON request from stdin and writes
one normalized JSON response to stdout. Supported actions are `probe`, `submit`,
`status`, `cancel` and `recover`.

For CoRAgent and TRI on the same login node, use `driver="external"` and
`transport="local"`. Set `work_root` to a persistent directory shared with compute
nodes; set `handler` to the installed Python and this script's absolute path.
See [target configuration and protocol](../../../docs/EXTERNAL_JOBS.md) for a full
configuration. Research calculations continue through `job_start`, `job_status`,
`job_reconcile` and `job_collect`.

## Handler environment

Set these in the target's `handler_environment` as needed:

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
