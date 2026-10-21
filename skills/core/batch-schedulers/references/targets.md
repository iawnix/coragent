# Target configuration and recovery

```toml
[execution]
default_target = "batch"

[execution.targets.batch]
scheduler = "pbs"
location = "cluster"
driver = "external"
transport = "local"
work_root = "/shared/coragent/jobs"
handler = ["/usr/bin/python3", "/opt/coragent/skills/core/batch-schedulers/scripts/batch.py", "pbs"]
command_timeout_seconds = 180
allowed_queues = ["batch"]

[execution.targets.batch.submission]
queue = "batch"
queue_wait_seconds = 900

[execution.targets.batch.submission.resources]
cpus = 4
memory_mb = 4096
walltime = "01:00:00"
```

Replace paths and queue names with site values. Select `slurm` or `torque` in the
handler argv as appropriate, and set `scheduler` to the same value. For SSH, set `transport = "ssh"`, add `ssh_host`, and
install the Skill scripts on that host. The handler runs on the submission host;
the scheduler runs the staged wrapper on a compute node. The handler is distributed with the Skill.

Override executable paths under `handler_environment` using `CORAGENT_QSUB`,
`CORAGENT_QSTAT`, `CORAGENT_QDEL`, or `CORAGENT_SBATCH`, `CORAGENT_SQUEUE`,
`CORAGENT_SACCT`, `CORAGENT_SCANCEL`. These values name single executables.
Backend bindings go under `execution.targets.batch.bindings`.

PBS mode expects OpenPBS/PBS Pro `qstat -x -f -F json`, including retained
history. Enable job history and choose retention longer than controller outages.
Torque mode reads `qstat -x` XML; recovery is limited to records retained by that
installation. Slurm needs `squeue` and `sacct`; preserve the submission comment in
accounting (`AccountingStoreFlags=job_comment`). Test these queries under the
actual submission account before running production Jobs.

The handler writes a durable submission intent and locks its journal before
calling the submit command. The full request identity goes into PBS's
`CORAGENT_REQUEST_ID` job variable or Slurm's comment. `recover` looks up the
saved scheduler ID or matches that identity in live/history records. It is read
only. The script refuses another submission while an earlier intent remains
unresolved. After accounting history expires, an absent record cannot establish
that submission never happened; inspect the scheduler history before creating a
replacement Job. Preserve the execution directory until collection and recovery
are complete.

The generic protocol is documented in [external Jobs](../../../../docs/EXTERNAL_JOBS.md).

For direct workspace execution, add `file_mode="shared"` and set `work_root` to
the shared workspace parent. Controller, submission host and compute nodes must
see the same resolved Job path. This applies to all three schedulers and both
local and SSH transports; `staged` remains the default. See the shared-storage
checks in [external Jobs](../../../../docs/EXTERNAL_JOBS.md).
