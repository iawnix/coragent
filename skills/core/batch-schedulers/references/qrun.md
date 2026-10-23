# Qrun local and SSH execution

Qrun is one persistent FIFO CPU/memory pool on an execution host. Use
`executor="qrun"` with either `transport="local"` or `transport="ssh"`.
Its installed standalone handler implements the same external-Job protocol as
the cluster adapters; no separate Skill script is needed.

## Configure and check the target

```toml
[execution.platforms.compute]
default_scheduler = "main"
schedulers.main.executor = "qrun"
transport = "ssh"
ssh_host = "YOUR_SSH_ALIAS"
storage.work_root = "/home/USER/DATA/qrun-jobs"
storage.file_mode = "staged"
schedulers.main.handler = ["/home/USER/soft/Qrun/qrun", "handler"]

[execution.platforms.compute.schedulers.main.submission.resources]
cpus = 4
memory_mb = 4096
walltime = "01:00:00"
```

Replace these paths with the installed pool's paths. This example assumes an
installed wrapper binding the state directory; otherwise use the exact handler
argv returned by the installer. For local execution change transport to local
and omit ssh_host. The work root must be allowed by that pool. Staged transport
requires rsync on both hosts; shared mode requires verified path visibility.
Configure scientific software bindings on the execution host independently.

Use CoRAgent `job_probe` for target reachability and its `queue` overview for pool
resources; verify software separately with the selected binding's environment check.
The main installer can provision a local Qrun pool for an explicitly configured
entry using the default handler. Without execution configuration it creates no
pool; SSH enrollment is explicit.
Installation and daemon maintenance are described in [Qrun operations](../../../../docs/QRUN.md).

## Submit, observe and recover

Use `job_start`, `job_status`, `job_reconcile`, `job_cancel` and `job_collect` for
ordinary CoRAgent calculations. Every submission must request positive CPUs and
memory within pool capacity. No named queue, GPU allocation or PBS select exists.

Qrun job IDs are increasing numbers within a pool, such as `12`; the receipt's
`scheduler_id` is the string `"12"`. Always retain its target/pool identity.
CoRAgent's workspace `job_id` is a separate identity: pass that to CoRAgent Job
commands, and the Qrun number to native commands. Do not generate a new request
after an uncertain submit: recover the original one. Never edit the ledger to
resolve unknown execution.

Run these commands on the target host using its installed wrapper (or program
with `--state-dir`). SSH uses the same commands after the configured host alias:

```sh
qrun resources --json
qrun jobs --json
qrun jobs --all --state failed --limit 20 --json
qrun show 12 --json
qrun logs 12 --stream stderr --follow
qrun watch
qrun cancel 12 --json
```

Budget, reserved and free are scheduler accounting; host availability and sampled
usage are different observations. Starting/running/stopping/unknown jobs retain
reservations. OFFLINE/stale output is saved evidence, not a current process check.
Inspect show's wait_reason: paused, insufficient_resources, fifo (blocked_by is
another numeric ID), exceeds_capacity or ready. Strict FIFO does not backfill.
Cancellation acceptance is not completion; confirm terminal state and cleanup.

Logs prefer staged application stdout/stderr and otherwise use captured direct
script output. Old jobs may have no retained log or metrics. Use job_collect to
recover declared calculation outputs and validate them separately from scheduler
success.

## Queue controls

Use `pause`/`resume` to control dispatch; running jobs and cleanup continue.
`config --cpus N --memory-mb M` resizes the live budget without killing running
jobs. Shrinkage can leave overcommitment or an oversized FIFO head; explain that
before changing a shared pool. `service stop` is temporary under portable cron.
Code upgrades require a drained queue; budget changes do not.

Portable uses CPU affinity and sampled process-tree RSS termination; this is not
a kernel memory hard limit. Modern systemd mode uses cgroup v2. A PBS reservation
may provide exclusive access to a host while Qrun remains independently managed;
do not infer PBS lifecycle coupling or cgroup protection from that reservation.
