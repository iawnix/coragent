# Execution platform contract

`job_start` owns the calculation lifecycle for both local and remote targets.
Local or SSH transport connects to the selected scheduler handler. Use `job_probe`
with `execution_target: {"platform": "Com30", "scheduler_entry": "qrun"}` for a
bounded availability check, substituting the Task's actual bound target.

## Installation-Owned Policy

The installation's main `config.toml` owns `[execution]` with `schema_version = 2`.
Each named `execution.platforms.<name>` declares `transport = "local"` or `"ssh"`,
storage, software `bindings` and scheduler entries under `schedulers`.
SSH platforms also declare `ssh_host` and optional `ssh_config`. A scheduler entry
selects its `executor`, handler, submission defaults and resource limits; it can
override shared bindings and storage. The generated `job.toml`, exposed through
`CORAGENT_JOB_CONFIG`, is an input for execution tools, not a file to maintain separately.

Bind a Task through the [execution-platforms Skill](../../../core/execution-platforms/SKILL.md)
before preparation. Its `{platform, scheduler_entry}` selection becomes the Job's
`execution_target`; science preparation inherits that selection. Resource requests
must fit the selected entry's limits. A missing scientific binding is reported by
the targeted check below; transport availability alone does not establish readiness.

`job_probe` checks platform availability, not scientific readiness. Inspect the
selected backend's command, activation script and Python binding with the
[targeted environment check](runtime_environment.md). Use the relevant
program's bounded help/version check or Skill-specific doctor when required.
For CF22D, [doctor.py](../../cf22d/scripts/doctor.py) checks the configured
PySCF environment and method construction. It does not establish readiness for
other programs. There is no bundled NEB readiness probe or workflow registry.
Do not install scientific dependencies into a research workspace.

## Isolation

With staged storage, remote directories are derived from the Job identity and
workspace path. The upload manifest binds files and digests; the request also fixes
command, environment, resources and expected outputs. Collection downloads declared
outputs into the local workspace. Shared storage uses the configured shared work
root and its directory identity checks instead of copying the execution directory.

## Control Lifecycle

Submit persists pre-effect staging state before calling the configured scheduler. Once the
scheduler request begins, transport failure may be ambiguous. Preserve any
known job ID and durable submission record even if later queue/history lookup
fails.

Cancel similarly distinguishes known no-effect, known cancellation, and
ambiguous effect. When a job disappears from the queue, inspect its receipt
and declared outputs to establish what happened.

Inspect may combine durable receipt, scheduler state, program status, and a
bounded declared artifact tail. Collection follows the immutable artifact
manifest and works even when scheduler history is unavailable.

## Verify Results

- Reconcile an unknown submit or cancel result before another control action.
- Resolve new submissions from the selected platform; existing Jobs use their persisted route and intent.
- Check the selected platform and scientific command separately; SSH alone is insufficient.
- Check program termination and required outputs after scheduler completion.
- Collect outputs, verify them locally, and parse them before recording research notes.
