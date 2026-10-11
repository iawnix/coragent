---
name: xtb
description: Use xTB for inexpensive structure screening, single points, optimization, frequencies, constrained scans, and molecular dynamics; interpret the raw outputs.
---

# xTB calculations

Choose single points, optimization, frequencies, constrained scans, or molecular
dynamics for the question; specify method, charge, electronic state, and solvent.

For single points and optimization, `chemical.xtb@1` provides a GFN2-xTB wrapper
with `sp`, `opt`, and `opt-sp` tasks:

Before generating files, explicitly cd in the command to the work_dir returned by research_create/research_read, or use absolute output paths beneath it; before Node association, use workspace research/work/. work_dir is returned guidance, not a bash parameter. The relative paths below assume that directory was selected in the same command; use absolute paths for inputs stored elsewhere. Put reports in reports/; avoid loose files in the workspace root and leave historical requests in place.

```bash
"$CORAGENT_PYTHON" -m research_agent.application.executors --config "$CORAGENT_JOB_CONFIG" --environment local --executor chemical.xtb --version 1 --input geometry=input.xyz --output prepared/xtb.json -- --task opt-sp --charge 0 --multiplicity 1
```

Submit the returned request file and digest with `job_start`; supply node_id when
associating the calculation with a research question. See the [runner contract](../method-selection/references/runner_results.md)
for output and electronic-state semantics. This wrapper converts multiplicity
to xTB's unpaired-electron parameter.

Run frequencies, scans, and dynamics as native xTB commands through generic Jobs,
preparing control files and declaring collected outputs. No executor registration
is required. Native options are not values for the wrapper's `--task` argument.
See [xTB execution and interpretation](references/xtb_executor.md) for commands,
inputs, and the actual parser coverage.

Check SCC where applicable, optimization convergence, and structure identity;
inspect vibrational modes, scan constraints and point convergence, or integration
stability and trajectories as appropriate. Compare energies with consistent methods,
electronic states, and energy definitions; absolute xTB–DFT energy differences do
not measure accuracy.

For material-based 1D/2D scans and bound Cartesian gradients, use
`chemical.scan-xtb@1` and `chemical.gradient-xtb@1` with the optional path_xtb
scientific environment; [path operations](../candidate-generation/references/path_search.md)
explain native restraint potentials, separate physical energies, and the xTB NEB adapter.
