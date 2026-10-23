---
name: batch-schedulers
description: Use Qrun, TRI, PBS, Torque and Slurm scheduler entries, translate resource requests, and diagnose submission, queueing, cancellation, accounting and recovery.
---

# Batch scheduler integration

## Script routing

Select the handler below and read the matching scheduler reference. The handlers use only Python's standard library; request JSON goes on stdin and receipt/status JSON comes from stdout. Bundled script paths are relative to this Skill directory; Qrun uses the standalone program installed on the execution host.

| Scheduler | Entrypoint | Reference |
| --- | --- | --- |
| Qrun | Installed `qrun handler` | [Qrun](references/qrun.md) |
| TRI | `scripts/tri.py` | [TRI](references/tri.md) |
| PBS | `scripts/batch.py pbs` | [PBS](references/pbs.md) |
| Torque | `scripts/batch.py torque` | [Torque](references/torque.md) |
| Slurm | `scripts/batch.py slurm` | [Slurm](references/slurm.md) |

All implement `probe`, `submit`, `status`, `cancel` and `recover` through the same external-Job protocol. The installation selects the handler with `execution.platforms.<platform>.schedulers.<entry>.handler` and declares the matching `executor` value. Scientific Skills choose methods and software backends; [research-workflow](../research-workflow/SKILL.md) resolves and pins the execution target. Ordinary calculations use `job_start`, `job_status`, `job_reconcile`, `job_cancel` and `job_collect`.

## Configure the submission host and resources

Identify the submission account, shared work root and software paths. Use `transport="local"` on the submission host or `transport="ssh"` from another host; this selects where the handler runs. Qrun runs on that host; cluster schedulers choose the compute node. See [target configuration](references/targets.md) for the configuration structure and file modes; follow the selected scheduler's reference for native commands and recovery evidence.

Choose CPUs from program parallelism, memory from the working set and walltime from a representative calculation. Qrun reserves CPU and memory in one FIFO pool; use its numeric job ID and inspect budget versus live usage separately. TRI allocates nodes and resources without a PBS/Slurm queue selector. PBS uses `select`, Torque uses `nodes:ppn`, and Slurm uses CPU/memory/GPU flags. Inspect waiting reasons and site limits before adjusting resources. Keep scheduler connection settings in `handler_environment` and scientific program settings in the selected backend binding.

## Observe and recover

Use the Job receipt's target and `scheduler_id` to identify native evidence. Distinguish submission acceptance, queueing, execution, terminal accounting and collected outputs. An uncertain submit response requires recovery of the original request identity; absence from a transient query is not evidence that no job was submitted. Cancellation requires confirmation that execution stopped.

For failures, combine scheduler accounting and `logs/scheduler.stdout`/`logs/scheduler.stderr` with calculation logs. [Qrun resources and job diagnosis](references/qrun.md), [TRI diagnosis](references/tri-diagnosis.md) and [PBS/Torque/Slurm commands](references/commands.md) describe native evidence. Exercise submission, terminal accounting, cancellation and lost responses against deterministic fixtures or an authorized test queue when changing a handler.

TRI server installation, client registration, capacity configuration, database maintenance and upgrades are infrastructure administration, documented in [TRI operations](../../../docs/TRI_OPERATIONS.md). Per-node software acceptance belongs to the [TRI integration reference](references/tri.md#verify-each-compute-node-and-backend).

Platform, connection, environment and storage rules are defined in [execution-platforms](../execution-platforms/SKILL.md).
