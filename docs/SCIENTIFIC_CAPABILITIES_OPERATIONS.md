# Scientific execution and operations

[简体中文](SCIENTIFIC_CAPABILITIES_OPERATIONS.zh-CN.md)

`skills/chemical/execution.json` declares bundled convenience executors and validators. Skills explain method selection, scientific limitations and interpretation. Research Memory records original requirements, research questions and results; adding an executor does not require method-specific research fields.

These entries are not a workflow or a capability allowlist. The Agent can prepare
native commands or task scripts and execute generic Jobs without registering a
new entry for each calculation. See [Skills and the execution catalog](EXTENSIONS.md).

## Prepare and execute

Start from the relevant Skill, then choose its recipe, native command or task script and a target binding from `config.toml` under `execution.platforms.<platform>.schedulers.<entry>.bindings`. A recipe supplies its backend key, pinned scripts, pure CLI parser, input roles and outputs. Native commands need no Python binding; Python scripts use the selected target's configured interpreter.

`"$CORAGENT_PYTHON" -m research_agent.application.executors --list` returns a compact recipe index, with optional `--skill`, `--backend`, or `--executor`/`--version` filters. `--details` returns full descriptors. Adding `--config … --platform …` shows binding presence without probing software. For actual runner options, use `executors --executor <id> --version <version> --help`; this loads only the pinned CLI parser, without executing the scientific program.

The preparation command writes a request and returns `request_file` and `request_sha256`. Submit these to `job_start`, supplying `node_id` when associating a research question. Runtime checks the file and inputs and fixes the selected Node association and content revision, `prepared_ref` and dispatch intent. Preparation alone dispatches no Job and proves no scientific outcome.

A task-specific Python method can use `--script <file.py> --backend <binding>` instead of executor/version. Declare staged dependencies and collected outputs. For registered input evidence, pass `--input-artifact <id-or-ref>` so Runtime verifies its actual staged bytes and preserves lineage.

Recover a lost response with the original request identity. Use `job_status`, `job_reconcile` and `job_collect`; a timeout or disconnected client does not authorize another submission. Intentional repetition needs a new identity and the predecessor/reason/budget declaration.

## Platform checks

Use `job_probe` in a session to inspect a configured execution target. Check software
for a selected recipe from the installed control environment:

```bash
"$CORAGENT_PYTHON" -m research_agent.application.environment_check --config "$CORAGENT_JOB_CONFIG" --platform <name> --executor <id> --version <version>
```

This contacts only the selected environment. For a program or task script without
a recipe, replace executor/version with `--backend <binding>`; optionally select
`--runtime native` or `--runtime python`. `--details` includes the observation.
Missing recipes, missing configuration, and failed checks return `recipe_not_found`,
`not_configured`, and `check_failed`, respectively. `verified` means that the
selected environment prerequisites passed.

For installation maintenance, omit the target and recipe/backend selection
to check all configured targets, including SSH targets. Platform observations
from `job_probe` and software dependency checks are distinct.

## Environments and ownership

The generated component job.toml, selected by `CORAGENT_JOB_CONFIG`, provides the command, Python binding, activation and resource defaults. Structure/material analysis and the general scientific-check executors use the chemical extension's `structure` backend; registered validator recipes use `validation`. Executors and validators can declare `requirements`: Python version specifiers in `python` and `packages`, and modules to actually import in `imports`. Native entries do not declare Python dependencies.

Preparation probes the selected local or SSH target: interpreter prefix, explicit Conda lock, pinned pip versions, installation receipt, package inventory, executable and activation file digests. This observation contributes to request identity. New submissions recheck it, and the staged, digest-pinned guard checks again when execution begins. Activation is verified before sourcing. Drift prevents execution; retries of an existing Job still return its original identity. Environment agreement does not itself prove a scientific method works.

Installation receipts record `inventory_sha256` from actual environment preparation and inspection.
Prepare scientific environments separately and reference their bindings in the platform configuration.
For target-local maintenance, run from a verified CoRAgent source or package root
on the execution host, using a copy of the execution document generated from
the main configuration and made available on that host:

```sh
python3 -B packaging/coragent_packaging/installer/install_job_environment.py \
  --config /ABS/execution.toml --platform PLATFORM --scheduler-entry ENTRY --backend BACKEND
```

`/ABS/execution.toml` is that generated document's target-side copy, not another
manually maintained configuration source. It contains the selected platform/entry's
environment bindings and target-local paths. A controller's `CORAGENT_JOB_CONFIG` path is usable only where that file is
actually available. `--adopt` verifies an existing prefix and publishes its receipt.
The main installer validates selected bindings;
`--verify-job-target PLATFORM/ENTRY` also submits bounded acceptance Jobs on that entry. Reports distinguish
configuration, environment and actual execution verification. `job_probe` checks infrastructure only;
PubChem/OPSIN network availability is separate from offline acceptance.

Local/SSH transport and the scheduler are selected independently. Qrun provides a persistent CPU/memory pool for a bare execution host, and its Jobs run independently of CoRAgent Host restarts. Its systemd mode uses cgroup v2 resource controls; portable mode uses CPU affinity and sampled process-tree RSS termination, which is not a kernel memory hard limit. See [Qrun operations](QRUN.md). Jobs receive a minimal environment plus explicit variables. Runtime creates a private scratch directory inside the Job or below the configured scratch_root; explicit environment values can reference `{scratch}`. Execution receipts remain in the workspace after scheduler cleanup.

Resource defaults merge once at preparation or submission, in target, backend, then explicit-request order. Prepared entries keep their resolved resources; submission cannot override them. The Job receipt and execution fingerprint record the actual values. `allowed_queues` is a permission boundary, not a default for `submission.queue`. Qrun has no named queues; other scheduler entries use their declared queue semantics with either local or SSH transport. Torque translates cpus/memory_mb to nodes/ppn and mem; PBS uses select (which cannot be combined with cpus/memory_mb). When both walltime and program timeout_seconds are present, the shorter limit applies.

External Jobs use their configured local/SSH transport and queue handler and share the local minimal process environment, thread defaults and scratch rules. They do not inherit scientific settings from the login shell: required paths and activation scripts belong in the binding. Remote directory names include a digest of the local Job path, keeping same-name Jobs in different workspaces separate. Recovery uses the saved request identity and the handler’s read-only lookup. See [external Jobs](EXTERNAL_JOBS.md).

`command_timeout_seconds` limits local or SSH control commands (60 seconds by default); `transfer_timeout_seconds` separately limits each rsync operation (3600 seconds by default). Neither is the scientific program's execution deadline. Collection excludes the local spec, receipt, status and other control files so calculation outputs cannot overwrite them. Solver completion and successful output collection remain separate observations.

Submission disables scheduler mail and automatic reruns; the research workflow owns notifications and intentional repeats. Successful `qdel` records a cancellation request. The Job becomes cancelled after execution termination is confirmed; a missing record remains unknown. Connection failures during cancellation remain unknown; a program that finishes first retains its actual exit result.

## Evidence and support boundaries

Job files live below `runs/jobs/<job_id>`. Collection registers declared files as Artifacts belonging to their producing Job, including all files in an explicitly declared recursive output directory. The Agent applies domain methods, records interpretation in the corresponding Node and publishes useful Results. Exit zero or a formatted report alone does not establish scientific success.

The [current capability inventory](../skills/chemical/method-selection/references/capabilities.md)
lists independent executors, their backends and scientific limits. Bundled modules cover:

- Name/SMILES/XYZ materials, mapping candidates, tensor reordering and conformer comparison.
- CF22D, xTB and Gaussian calculations; bounded CREST ensembles and rigid-fragment complex sampling.
- [Reactive geometry editing](../skills/chemical/reactive-geometry/SKILL.md): directed fragment placement, local edits and evidence-bound mode displacements; geometry screening only, followed by separate solver refinement.
- xTB/Gaussian relaxed scans, QST2/QST3 preparation, gradients and ASE NEB v2 candidate searches.
- General stationary-point, mode and IRC checks; thermochemistry, conformer free energies and energy profiles.
- Multistep pathway checks, conditional TST, common-precursor branching and mass-action networks.
- Limited Gaussian ground-spin and singlet TD/TDA calculations, supplied-tensor state tracking, and local different-spin crossing searches/checks.

The xTB convenience wrapper still accepts `sp/opt/opt-sp`; bounded scans and NEB
have separate executors. Frequencies and dynamics use native commands through
generic Jobs. See the [xTB Skill](../skills/chemical/xtb/SKILL.md).
The optional `path` environment profile binds `path_xtb` / `path_gaussian` and
uses path.lock with RDKit/NumPy, ASE and SciPy; it does not install native solvers or run a default scientific
smoke calculation. See [environment setup](../skills/chemical/environments/README.md).

NEB uses ASE with Gaussian/xTB calculators through version-2 entries; the former NumPy implementation has been removed. QBICS remains an external, explicitly
verified command/script route; the bundled crossing search uses Gaussian and a
local NumPy algorithm. State tracking requires supplied AO density/overlap tensors;
automatic extraction from Gaussian checkpoints is not implemented. Classical
TS/IRC checks do not certify crossings or excited-state continuity. Use the
[general checks](../skills/chemical/validation/references/general_checks.md).
See the [chemical-report Skill](../skills/chemical/chemical-report/SKILL.md) for molecular images,
data tables, energy plots, standalone trajectory/report Jobs and their evidence requirements. Local geometry diagnostics and practical search-recovery guidance are linked from the input and method-selection Skills.

## Validation

Use `tools/test/runner.py` to select the source, Native and package lanes. Real solver and remote acceptance use isolated workspaces and configured bindings. Synthetic logs, analytic potentials and deterministic solver substitutes verify contracts, numerical algorithms, parsing and local Job lifecycles. They do not establish real solver accuracy or autonomous mechanism discovery. Use the report for the tested source to establish a pass; this guide does not certify real-solver benchmarks or real-model research performance.

A native prerequisite probe resolves and hashes the configured executable; it
does not run the solver or verify a license, convergence, or a scientific result.
`environment_executable_missing` means the selected command cannot be executed;
`environment_activation_missing` identifies its missing activation script;
`environment_dependency_missing` identifies a required package or module that is
absent. `environment_import_failed` means importing a present dependency failed
during initialization. Report the exact observation and selected target; an
unconfigured binding or absent recipe does not prove the software is absent
from every environment. Changed binding or executable evidence requires preparing
a new request before dispatch, not running an old prepared command.

## Resource contracts for extension authors

Preparation accepts `submission={"resources": {"cpus": 12, "memory_mb": 16384}}`
for registered executors, Python scripts and validators. See [per-job resource rules](EXTERNAL_JOBS.md#per-job-resources).

An executor may declare `resource_contract` as a path in its hashed `resources` closure.
It is a pure standard-library-only Python module, loaded without scientific dependencies,
with three functions: `defaults(descriptor)` returns last-resort resource values;
`requirements(descriptor, arguments, inputs)` returns explicit input requirements;
`prepare(descriptor, arguments, inputs, resources)` returns `(normalized_arguments, report)`.
Arguments are forwarded arguments only; inputs map roles to absolute source paths.
Normalization must be deterministic and idempotent. Raise an actionable `ValueError` for
conflicts, never rewrite user input files, and do not probe capacity or execute programs.
Submission repeats the contract against the pinned inputs, final allocation and arguments.
Executors without this contract and arbitrary scripts report internal resource use as unverified.

`configuration_sha256` pins configured defaults/software; `execution_binding.submission`
contains the effective Job allocation, recomputed from `submission_request`. They need not
equal configuration defaults. Final allocations also participate in execution fingerprints.
`CORAGENT_JOB_CPUS` and `CORAGENT_JOB_MEMORY_MB` expose the resolved allocation at runtime;
thread defaults are reasserted after activation so activation scripts cannot restore a stale
fixed thread count. These variables describe requested limits, not measured use or node capacity.
