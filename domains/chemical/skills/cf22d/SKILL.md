---
name: cf22d
description: Run CF22D through the PySCF binding for single points, optimizations, frequencies, thermochemistry, and bounded transition-state searches.
---

# CF22D electronic-structure backend

[Chinese version](SKILL.zh-CN.md)

## Script routing

Use the registered executor ID and the [script routing map](../../../../docs/skill-script-routing.md#cf22d) to choose the entrypoint, CLI, inputs, and primary outputs. The map is authoritative for routing; implementation helpers under `scripts/` are not standalone commands. Do not inspect source code to discover invocation details; read the linked operation contract and use executor `--help` only for unspecified options.

**Entrypoints:** `chemical.cf22d@1` → `skills/cf22d/scripts/run.py`; `chemical.cf22d-doctor@1` → `skills/cf22d/scripts/doctor.py`.

Use this Skill when CF22D is the chosen electronic method. It translates an XYZ material and explicit electronic settings into the registered PySCF/CF22D runner, writes parser-readable evidence, and returns geometries, energies, gradients, frequencies, and thermochemistry fields when the task provides them.

## Task vocabulary

`chemical.cf22d@1` supports:

- `sp`: one energy/gradient evaluation at the supplied geometry;
- `opt`: geometry optimization;
- `opt-sp`: optimization followed by a single point on the optimized geometry;
- `ts`: transition-state optimization using the initial-Hessian TS setup;
- `freq`: frequency analysis at the supplied geometry;
- `thermo`: thermal quantities from a frequency result;
- `opt_freq` and `ts_freq`: optimization or TS optimization followed by frequencies.

Use `opt`/`opt_freq` for minima, `ts`/`ts_freq` for a TS candidate, `sp` for a fixed-geometry comparison, and `freq`/`thermo` after the geometry and state are the intended ones.

## Input choices

Provide an XYZ file in angstroms, a basis (default `def2-tzvp`), charge, multiplicity `2S+1`, exchange-correlation label, grid level, convergence tolerances, maximum cycles/steps, temperature, pressure, thread count, and memory. Keep charge and multiplicity identical across endpoint, candidate, and frequency jobs unless the reaction explicitly changes electronic state. Dispersion and CF22D settings are recorded in the result for energy comparisons.

## Typical request

```bash
"$CORAGENT_PYTHON" -m research_agent.application.executors --config "$CORAGENT_JOB_CONFIG" --executor chemical.cf22d --version 1 --input geometry=input.xyz --output prepared/cf22d.json -- --task opt-sp --basis def2-tzvp --charge 0 --multiplicity 1 --threads 8 --memory-mb 8000
```

Start the prepared request with `job_start`, then submit and collect the Job. The result contains `results/result.json`, `results/geometry.xyz`, task output, units, convergence fields, and raw provenance. Use `chemical.cf22d-doctor@1` when the PySCF/CF22D environment needs diagnosis.

## Practical method use

Use CF22D for consistent screening and geometry refinement when its basis, state, and convergence settings are controlled. For TS work, provide a chemically constructed candidate from `candidate-generation`, run the TS task, and send the output to `validation`. For barriers or free energies, pair compatible CF22D energies with frequencies and pass the collected results to `energetics`.

The detailed task schema and artifact names are in [CF22D workflow](references/cf22d_workflow.md), [environment diagnosis](references/environment_doctor.md), and the shared [runner result contract](../method-selection/references/runner_results.md).
