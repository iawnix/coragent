---
name: cf22d
description: Adapt declared CF22D/PySCF inputs and parser evidence to the registered pyscf binding without selecting or validating a scientific task.
---

# CF22D backend

This Skill owns the CF22D/PySCF binding, task argument translation, staged
inputs, units and parser evidence. It does not choose a basis or scientific
operation for a research question and does not certify stationary points,
transition states or thermochemistry. Use `method-selection`, `candidate-generation`,
`energetics` and `validation` for those decisions.

`chemical.cf22d@1` accepts the registered task vocabulary `sp`, `opt`, `opt-sp`,
`ts`, `freq`, `thermo`, `opt_freq` and `ts_freq`. The target `pyscf` environment
must provide CF22D and its declared dispersion implementation. The adapter
records basis, charge, multiplicity, task, convergence fields, units and raw
provenance according to the shared [runner contract](../method-selection/references/runner_results.md).

Prepare a request through the executor interface:

```bash
"$CORAGENT_PYTHON" -m research_agent.application.executors --config "$CORAGENT_JOB_CONFIG" --environment local --executor chemical.cf22d --version 1 --input geometry=input.xyz --output prepared/cf22d.json -- --task opt-sp --basis def2-tzvp --charge 0 --multiplicity 1
```

The request file is not a result. Start a Job with `job_start`, then submit and
collect it through the normal Job lifecycle. Environment prerequisites and parser-specific fields are documented
in [CF22D workflow](references/cf22d_workflow.md) and [environment diagnosis](references/environment_doctor.md).
