---
name: gaussian
description: Prepare, run, and inspect Gaussian calculations, including single-point, optimization, frequency, transition-state, IRC, QST, and explicit scan inputs.
---

# Gaussian calculations

Use `chemical.gaussian@1` for XYZ `sp`, `opt`, or `opt-sp` calculations. Its
defaults are M062X/6-31G**, Opt=Tight or SP, SCF=Tight, and Int=UltraFine.
Use `chemical.gaussian-input@1` for a complete explicit Gaussian input.
Both use the target's `gaussian` binding.

Choose the input mode before preparing arguments:

| Executor | Preparer input | Arguments after `--` |
| --- | --- | --- |
| `chemical.gaussian@1` | `--input geometry=input.xyz` | `--task opt/sp/opt-sp`; task selects calculation and checks. Omit `--validation`. |
| `chemical.gaussian-input@1` | `--input input=input.gjf` | `--validation opt/sp/frequency/minimum/saddle/irc/none`; checks the supplied GJF route. Omit `--task`. |

Neither mode accepts `--task-validation`. With XYZ, delete that option and its value; keep `--task opt` for an optimization. Do not replace it with `--validation opt`. Frequency/minimum/saddle/IRC checks require an explicit GJF with the appropriate route.

Read help for the selected executor, using either `chemical.gaussian` or `chemical.gaussian-input`:
`"$CORAGENT_PYTHON" -m research_agent.application.executors --executor chemical.gaussian --version 1 --help`.
For software diagnosis, use the [targeted environment check](../method-selection/references/runtime_environment.md)
with this recipe and the chosen environment.

Before generating files, explicitly cd in the command to the work_dir returned by research_create/research_read, or use absolute output paths beneath it; before Node association, use workspace research/work/. work_dir is returned guidance, not a bash parameter. The relative paths below assume that directory was selected in the same command; use absolute paths for inputs stored elsewhere. Put reports in reports/; avoid loose files in the workspace root and leave historical requests in place.

```bash
"$CORAGENT_PYTHON" -m research_agent.application.executors --config "$CORAGENT_JOB_CONFIG" --environment local --executor chemical.gaussian --version 1 --input geometry=input.xyz --output prepared/gaussian.json -- --task opt-sp --charge 0 --multiplicity 1
```

The bash command prepares and validates a Job request; `prepared/gaussian.json` is not a calculation result and Gaussian has not been launched. On a parameter error, correct the arguments and prepare again. After success, inspect the request and submit its returned file/digest with `job_start` and the intended node_id, even for a brief calculation (replace placeholders with actual returned values):

```json
{"node_id":"<returned node_id>","request_file":"<returned request_file>","request_sha256":"<returned request_sha256>"}
```

Do not add command, inputs, outputs or platform overrides to this prepared submission. Use the returned job_id in `job_status`, then `job_collect` to preserve terminal outputs and their provenance. Cite the collected Artifacts in `research_result`; a collection receipt is evidence_refs/check_refs, not a file Artifact.
Read the [runner contract](../method-selection/references/runner_results.md)
for shared output and electronic-state semantics. Check the route readback,
normal termination and convergence. An optimized structure without frequency
evidence is not a verified minimum.

## Explicit Gaussian inputs

Prepare a complete .gjf for TS/Freq/IRC/QST/scan. Each Link1 section must match
`--method`, `--basis`, `--threads`, `--memory-mb`, `--charge`, and `--multiplicity`.
For Geom=AllCheck, verify the checkpoint's electronic state. Stage dependencies
with `--dependency /absolute/source.chk=previous.chk`; input references must
be relative staged paths. Collect checkpoints needed by subsequent calculations.

```bash
"$CORAGENT_PYTHON" -m research_agent.application.executors --config "$CORAGENT_JOB_CONFIG" --environment local --executor chemical.gaussian-input --version 1 --input input=ts.gjf --collect results/ts.chk --output prepared/ts.json -- --method M062X --basis '6-31G**' --charge 0 --multiplicity 1 --threads 12 --memory-mb 4000 --validation saddle
```

`--validation opt/sp/frequency/minimum/saddle/irc/none` selects runner checks only for this explicit GJF mode; it does not add calculation keywords to the GJF route.
`saddle` requires stationary-point convergence and one imaginary frequency;
inspect its mode direction and use the registered saddle validator for the
specified transformation. IRC produces path and endpoint artifacts; establish
endpoint identities with the connectivity validator and supporting evidence.
A scan input can execute, but scan-specific completeness has no bundled validator.

See [Gaussian scientific validation](references/gaussian_validation.md).
