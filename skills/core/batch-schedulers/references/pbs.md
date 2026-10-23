# PBS / OpenPBS / PBS Pro integration

Use `executor="pbs"` and `handler=["/usr/bin/python3", "/opt/coragent/skills/core/batch-schedulers/scripts/batch.py", "pbs"]`. Configure `CORAGENT_QSUB`, `CORAGENT_QSTAT` and `CORAGENT_QDEL` when native commands are not on PATH.

CPU and memory requests become `select=1:ncpus=N:mem=Mmb`; GPU requests add `ngpus`. An explicit `resources.select` replaces individual CPU/memory/GPU fields. Observe retained history using `qstat -x -f -F json`; enable job history longer than expected controller outages. Recovery matches `CORAGENT_REQUEST_ID` in task variables. `Q/W` is queued, `H/S` held, `R/E` running/cleanup, and `F/C` with an exit code is terminal.

See [target configuration and recovery](targets.md) for transport, storage and submission journals, and [native commands](commands.md) for queries, logs and cancellation checks.
