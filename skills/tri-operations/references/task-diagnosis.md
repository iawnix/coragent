# Task diagnosis and recovery

## Inspect one identity

For a CoRAgent Job, obtain the TRI numeric task ID from its `scheduler_id` receipt field and run the commands on that target. For direct submissions, use the ID returned by `tri_sub --json`. Read `tri_stat --json "$TRI_TASK_ID"` for state, node, attempt, lease, exit code, error and log paths. Compare this with `tri_node --json` and the service logs for the same time window.

## Diagnose by observation

| Observation | Next checks and action |
| --- | --- |
| CLI cannot connect | Verify socket path, ownership and server unit. An existing stale socket is tried before TCP; check the selected server before changing the socket. For TCP check address, reachability and token configuration. |
| Protocol/Hello mismatch | Compare server, CLI and client build identities; deploy a compatible set, then repeat the query. |
| `wait` | Compare requested CPU, memory, GPU and node against online node capacity and allocations. Inspect prerequisite IDs and completion. Correct the request or restore the required node as appropriate. |
| `blocked` | Inspect `--after` dependencies; a failed, cancelled or lost prerequisite blocks dependent work. Resolve the prerequisite and inspect the dependent record before scheduling replacement work. |
| `run`, little output | Inspect the assigned node, attempt, task unit and program activity. Check stdout/stderr paths and application buffering; a quiet log alone does not locate the fault. |
| `fail` | Read exit code, TRI error and stderr. Inspect task-unit logs for launch, permission, executable or cgroup/OOM failures, then inspect the application's own log. |
| `timed_out` | Compare runtime with the native timeout, inspect partial outputs and checkpoints, and choose a suitable continuation or time limit. |
| `lost` | Check node reachability, client heartbeat/lease and the actual task unit. Reconnect the client and reconcile the attempt before deciding whether to rerun. |
| `done`, missing files | Compare `--chdir`, output paths, shared mounts and scratch copy-back. `tri_log` opens the reported path on the CLI host; that host must be able to read it. |

## Resources and task units

On the assigned compute node, task units are named `tri-task-<id>-<attempt>`. Use the returned ID/attempt and the compute service account:

```bash
systemctl --user status "$TRI_TASK_UNIT" --no-pager
journalctl --user -u "$TRI_TASK_UNIT" -n 100 --no-pager
```

CPU allocations use `AllowedCPUs`; GPU allocations use visibility variables and device rules. `--mem` sets `MemoryMax` and disables swap for the task. A memory-limit failure calls for comparing peak memory with the request and node capacity. `--timeout` uses `RuntimeMaxSec`; distinguish this from an application returning a nonzero exit code.

The node client reconciles task units on start/reconnect and can adopt an existing matching attempt. Lease expiry can trigger another attempt when `--max-attempts` allows one. The default is one attempt; select a larger value for tasks whose outputs and side effects support re-execution.

## Submission identity, cancellation and logs

Use an installation/workflow-scoped `--request-id` for a retriable submission and optionally `--external-id` for workflow lookup. The same identifier and task specification returns the existing task; changing the specification requires a new identity. To recover a known external identity:

```bash
tri_stat --json --external-id "$TRI_EXTERNAL_ID"
```

For CoRAgent-owned tasks, use `job_reconcile`, `job_cancel` and `job_collect` on the existing Job. For requested cancellation of a directly managed TRI task:

```bash
tri_del --json "$TRI_TASK_ID"
tri_stat --json "$TRI_TASK_ID"
```

A cancellation record can appear before a running process exits: the client receives it on heartbeat. Confirm the node task unit has stopped and its allocation has been released. If the node is unreachable, report cancellation recorded and execution still unverified.

`tri_log ID` reads stdout, `tri_log --stderr ID` reads stderr, and `--follow` follows output interactively. Without separate output options, both streams go to `tri-<id>.out` in the job directory. `%j` in output/error options expands to the task ID; relative paths resolve against `--chdir`.

## Scratch and retention

Tasks receive a node-local `TRI_SCRATCH`; `--scratch-cwd` starts the command there. The original directory is `TRI_JOB_CWD`. Stage inputs and the runnable script where the node can read them, and copy final outputs/checkpoints back to the persistent job directory before task exit. Client cleanup is best effort, so inspect residual scratch only after locating the task attempt and its final outputs.

For requested history maintenance, select a retention window and collect the needed Job outputs/receipts first. `tri_clean --json --older-than SECONDS` removes old terminal records; the default window is 30 days. Cleanup also removes idempotency receipts, so retrying a cleaned request can create a new task. Choose the retention window to cover outstanding workflow recovery and retry needs; use `--all` only for an explicitly selected complete terminal-history removal.
