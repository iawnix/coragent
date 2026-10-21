---
name: xtb
description: Run GFN2-xTB single points and optimizations, and provide xTB calculators for scans, gradients, and path searches.
---

# xTB backend

[Chinese version](SKILL.zh-CN.md)

## Script routing

Use the registered executor ID and the [script routing map](../../../../docs/skill-script-routing.md#xtb) to choose the entrypoint, CLI, inputs, and primary outputs. The map is authoritative for routing; implementation helpers under `scripts/` are not standalone commands. Do not inspect source code to discover invocation details; read the linked operation contract and use executor `--help` only for unspecified options.

**Entrypoints:** `chemical.xtb@1` → `skills/xtb/scripts/run.py`.

Use xTB for fast conformer refinement, fixed-geometry energy screening, constrained scans, gradient evaluation, and early reaction-path exploration. Keep charge, multiplicity, solvent, and optimization level explicit so results from different stages remain comparable.

## Registered wrapper

`chemical.xtb@1` runs GFN2-xTB `sp`, `opt`, or `opt-sp` from XYZ input. The main options are `--charge`, `--multiplicity`, `--opt-level normal|tight|verytight`, `--executable`, and `--output-dir`.

```bash
"$CORAGENT_PYTHON" -m research_agent.application.executors --config "$CORAGENT_JOB_CONFIG" --executor chemical.xtb --version 1 --input geometry=input.xyz --output prepared/xtb.json -- --task opt-sp --charge 0 --multiplicity 1 --opt-level tight
```

The result contains the optimized geometry when requested, energy and convergence summary, native output, state/solvent fields, and source digests. Prepare and start the request with the standard `job_start` lifecycle, then inspect the parser summary before handing a geometry onward.

## Reaction-path operations

`chemical.scan-xtb@1` is the constrained scan/preoptimization calculator used by `candidate-generation` and `reactive-geometry`; `chemical.gradient-xtb@1` supplies gradients; `chemical.neb-xtb@2` runs the optional path_xTB calculator through ASE NEB v2. These operations accept their own path specifications and preserve restraint, frame, and endpoint metadata. Use them for broad searches, then refine promising frames with CF22D or Gaussian when the study requires higher-level evidence.

Read [xTB executor](references/xtb_executor.md) and [backend contract](references/xtb_backend_contract.md) for fields and native output parsing. Other native xTB features can run in a generic Job with explicit control files and collected outputs.
