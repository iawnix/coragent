# Platform configuration

The only configuration format is `execution.schema_version = 2`, with `default_platform` and `platforms`.
Flat `execution.targets` configuration is rejected. Use the main installer to publish a reviewed complete
configuration; it does not install complete CoRAgent on every submission host.

Each enabled platform defines `transport`, `storage.work_root`, `default_scheduler` and `schedulers`.
SSH platforms also define `ssh_host` using an existing SSH host configuration. An unfinished platform may
be registered with `enabled = false`; it cannot be the default or receive submissions.

Platform `python`, `bindings`, `storage`, `submission` and `allowed_queues` are shared by its entries.
Entry `executor`, `handler`, `handler_environment` and optional `cluster_name` describe its queue.
Entries can override software/storage and submission defaults, but cannot change platform connectivity.
Software overrides replace an entire binding. Resource defaults merge by field, subject to entry `limits`
and queue permissions. Limits include cpus, memory_mb, gpus, walltime and max_in_flight.

CPU counts are logical CPUs; memory_mb is MiB. A Python binding specifies manager=conda, the absolute
conda_executable, prefix and lock_ref. Native bindings use command and optionally activation_script and
environment. Scratch inherits from platform storage unless overridden for that software.

Use staged storage unless controller, submission host and compute nodes genuinely share the same physical
paths. work_root holds Job directories; scratch_root holds temporary data. Collect declared outputs into
immutable artifacts before using them on another platform. Never assume a remote path exists locally.

Basic handler readiness, software readiness and compute-node readiness are distinct observations.
Check software with `python -m research_agent.application.environment_check --config "$CORAGENT_JOB_CONFIG"
--platform Com30 --scheduler-entry qrun --backend gaussian`. A successful login-host probe does not
establish node visibility or license availability.

Changing defaults does not retarget submitted Jobs. Prepared requests must be prepared again after relevant
configuration changes. Removing an entry must not delete shared environments or unfinished Job data.
Qrun may be installer-owned; existing PBS/Slurm/TRI services remain external services.
