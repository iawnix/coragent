---
name: batch-schedulers
description: Configure TRI, PBS, Torque and Slurm execution targets, translate resource requests, and diagnose submission, queueing, cancellation, accounting and recovery.
---

# Batch scheduler integration

## Script routing

Use the [script routing map](../../docs/skill-script-routing.md#batch-schedulers) for supported entrypoints and interfaces. Both handlers use only Python's standard library; request JSON goes on stdin and receipt/status JSON comes from stdout.

| Scheduler | Entrypoint | Reference |
| --- | --- | --- |
| TRI | `skills/batch-schedulers/scripts/tri.py` | [TRI](references/tri.md) |
| PBS | `skills/batch-schedulers/scripts/batch.py pbs` | [PBS](references/pbs.md) |
| Torque | `skills/batch-schedulers/scripts/batch.py torque` | [Torque](references/torque.md) |
| Slurm | `skills/batch-schedulers/scripts/batch.py slurm` | [Slurm](references/slurm.md) |

All implement `probe`, `submit`, `status`, `cancel` and `recover` through the same external-Job protocol. The installation selects the handler with `execution.targets.<name>.handler` and declares the matching `scheduler` value. Scientific Skills choose methods and software backends; [research-workflow](../research-workflow/SKILL.md) resolves and pins the execution target. Ordinary calculations use `job_start`, `job_status`, `job_reconcile`, `job_cancel` and `job_collect`.

## Configure the submission host and resources

Identify the submission account, shared work root and software paths. Use `transport="local"` on the submission host or `transport="ssh"` from another host; this selects where the handler runs. The scheduler chooses the compute node. See [target configuration](references/targets.md) for the configuration structure and file modes; follow the selected scheduler's reference for native commands and recovery evidence.

Choose CPUs from program parallelism, memory from the working set and walltime from a representative calculation. TRI allocates nodes and resources without a PBS/Slurm queue selector. PBS uses `select`, Torque uses `nodes:ppn`, and Slurm uses CPU/memory/GPU flags. Inspect waiting reasons and site limits before adjusting resources. Keep scheduler connection settings in `handler_environment` and scientific program settings in the selected backend binding.

## Observe and recover

Use the Job receipt's target and `scheduler_id` to identify native evidence. Distinguish submission acceptance, queueing, execution, terminal accounting and collected outputs. An uncertain submit response requires recovery of the original request identity; absence from a transient query is not evidence that no job was submitted. Cancellation requires confirmation that execution stopped.

For failures, combine scheduler accounting and `logs/scheduler.stdout`/`logs/scheduler.stderr` with calculation logs. [TRI diagnosis](references/tri-diagnosis.md) and [PBS/Torque/Slurm commands](references/commands.md) describe native evidence. Exercise submission, terminal accounting, cancellation and lost responses against deterministic fixtures or an authorized test queue when changing a handler.

TRI server installation, client registration, capacity configuration, database maintenance and upgrades belong to [TRI operations](../tri-operations/SKILL.md). Per-node software acceptance belongs to the [TRI integration reference](references/tri.md#verify-each-compute-node-and-backend).
