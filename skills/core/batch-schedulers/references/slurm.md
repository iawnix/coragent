# Slurm integration

Use `scheduler="slurm"` and `handler=["/usr/bin/python3", "/opt/coragent/skills/core/batch-schedulers/scripts/batch.py", "slurm"]`. Configure `CORAGENT_SBATCH`, `CORAGENT_SQUEUE`, `CORAGENT_SACCT` and `CORAGENT_SCANCEL` for native command paths.

`submission.queue` selects the partition. CPU, memory and GPU requests become `--cpus-per-task`, `--mem` and `--gpus`. Inspect `squeue` for live state and waiting reasons and `sacct` for terminal accounting. Preserve submission comments with `AccountingStoreFlags=job_comment`; recovery matches the full request identity in that comment. `COMPLETING` still represents cleanup, and exit signals contribute to the normalized exit code.

See [target configuration and recovery](targets.md) for transport, storage and submission journals, and [native commands](commands.md) for queries, logs and cancellation checks.
