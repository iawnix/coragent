---
name: batch-schedulers
description: Configure PBS, Torque and Slurm execution targets, choose batch resources, submit through their native commands, and diagnose queue and accounting results.
---

# PBS, Torque and Slurm operations

## Script routing

Use the [script routing map](../../docs/skill-script-routing.md#batch-schedulers) before invoking a bundled script. It identifies the supported entrypoint and interface; helper files under `scripts/` are not standalone commands. Do not inspect source code to discover invocation details.

**Entrypoint:** `skills/batch-schedulers/scripts/queue.py` (see the map for its stdin/subcommand contract).

Use this Skill when connecting CoRAgent to an existing batch cluster or diagnosing
submission, queue waits, cancellation and completed jobs.

## Select the submission host and resources

Identify the installed scheduler, submission account, queue/partition, shared work
root and application environment. Use local transport when CoRAgent runs on the
login host; use SSH when it runs elsewhere. Compute nodes need the same absolute
work path and application paths as the submitted wrapper.

Choose CPUs from the application's parallelism, memory from its working set, and
walltime from a representative run. Check the queue's limits and current reason
for waiting before changing the request. PBS uses `select`; Torque uses
`nodes:ppn`; Slurm uses CPU, memory and GPU flags.

## Connect the bundled script

[Target configuration and recovery](references/targets.md) gives complete
configuration and deployment checks. The stdlib-only [queue.py](scripts/queue.py)
accepts `pbs`, `torque` or `slurm` as its first argument, reads one external-Job
request on stdin and emits its receipt/status as JSON on stdout.

It implements `probe`, `submit`, `status`, `cancel` and `recover`. Its submission
journal lives under the execution directory's `.coragent/`. CoRAgent stages the
wrapper, persists Job receipts and collects declared outputs through the selected
transport. Invoke ordinary calculations through the configured Job target.

## Inspect native evidence

Use [scheduler commands and diagnosis](references/commands.md) for resource
syntax, native queries and history requirements. For a waiting Job, inspect the
scheduler's reason and resource limits. For a failed Job, combine accounting exit
status, scheduler logs and calculation logs. For a lost submission response,
reconcile the recorded Job using its stable request identity.

Adapt site-specific resource flags in the script alongside the site's documented
queue policy. Exercise submission, terminal accounting, cancellation and lost
responses against a test queue when deploying an adaptation.
