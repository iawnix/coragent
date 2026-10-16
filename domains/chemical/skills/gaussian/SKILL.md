---
name: gaussian
description: Adapt declared Gaussian inputs and executions to the registered Gaussian binding, preserving route, state, parser and provenance contracts.
---

# Gaussian backend

This Skill owns Gaussian route construction, staged input execution, raw-log
parsing and supported energy/gradient evidence. It does not choose the
scientific operation, select a method for a research question, assign an IRC
basin, or certify a transition state. Use `candidate-generation`, `validation`
or `method-selection` for those decisions.

Registered adapters:

- `chemical.gaussian@1` accepts XYZ material input for `sp`, `opt` and
  `opt-sp` runner tasks.
- `chemical.gaussian-input@1` accepts a complete `.gjf` and checks its declared
  route with `--validation opt/sp/frequency/minimum/saddle/irc/none`.
- `chemical.electronic-gaussian@1` and `chemical.state-tracking@1` expose the
  bounded electronic-state contracts described in
  [electronic states](references/electronic_states.md).
- `chemical.gaussian-evidence@1` normalizes selected raw-log sections for the
  independent validation and IRC checks.

Both execution adapters use the target `gaussian` binding. The adapter stages
inputs and dependencies, preserves charge/multiplicity and method metadata,
records raw outputs and returns parser evidence. It does not add scientific
claims to a successful Job.

For an XYZ adapter request, prepare the Job through the executor interface:

```bash
"$CORAGENT_PYTHON" -m research_agent.application.executors --config "$CORAGENT_JOB_CONFIG" --environment local --executor chemical.gaussian --version 1 --input geometry=input.xyz --output prepared/gaussian.json -- --task opt-sp --charge 0 --multiplicity 1
```

For an explicit input, stage checkpoint dependencies with relative names inside
the Job and preserve blank section terminators:

```bash
"$CORAGENT_PYTHON" -m research_agent.application.executors --config "$CORAGENT_JOB_CONFIG" --environment local --executor chemical.gaussian-input --version 1 --input input=ts.gjf --collect results/ts.chk --output prepared/ts.json -- --method M062X --basis '6-31G**' --charge 0 --multiplicity 1 --threads 12 --memory-mb 4000 --validation none
```

These commands prepare requests; start the Job with `job_start`, then submission and collection follow the shared
[runner contract](../method-selection/references/runner_results.md). Do not
invoke Gaussian directly for a research Job. The explicit-input parser requires
complete Link1 metadata, relative staged dependencies and a final blank input
section. L101-specific parsing failures are documented in the [L101 input
guide](references/l101_input_guide.md).

The parser distinguishes supported reference SCF energies and records unsupported
or incomplete evidence as such. `--validation none` only disables the runner
check; it does not broaden parser support. Use the operation Skill's evidence
checks for any scientific conclusion. Gaussian path gradients and NEB use the
separate `path_gaussian` adapter under `candidate-generation`. Use the
Gaussian validation and scan references directly: see
[validation-owned Gaussian checks](references/gaussian_validation.md) and
[Gaussian scan recipes](references/relaxed_scans.md).
