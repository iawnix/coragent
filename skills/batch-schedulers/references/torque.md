# Torque integration

Use `scheduler="torque"` and `handler=["/usr/bin/python3", "/opt/coragent/skills/batch-schedulers/scripts/batch.py", "torque"]`. Native commands are `qsub`, `qstat` and `qdel`; override their paths with `CORAGENT_QSUB`, `CORAGENT_QSTAT` and `CORAGENT_QDEL`.

CPU requests become `nodes=1:ppn=N` and memory becomes `mem=Mmb`. GPU syntax depends on the site; adapt and test resource translation before requesting GPUs. The handler reads `qstat -x` XML, including records retained by that installation, and matches `CORAGENT_REQUEST_ID` for recovery. On Maui/Moab sites, `checkjob JOB_ID` can explain resource feasibility. A disappeared record remains unknown.

See [target configuration and recovery](targets.md) for transport, storage and submission journals, and [native commands](commands.md) for queries, logs and cancellation checks.
