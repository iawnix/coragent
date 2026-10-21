---
name: qbics
description: Plan and execute a QBICS crossing-point study through a declared installation, with explicit electronic states, inputs, and evidence.
---

# QBICS crossing studies

[Chinese version](SKILL.zh-CN.md)

## Script routing

Use the registered executor ID and the [script routing map](../../../../docs/skill-script-routing.md#qbics) to choose the entrypoint, CLI, inputs, and primary outputs. The map is authoritative for routing; implementation helpers under `scripts/` are not standalone commands. Do not inspect source code to discover invocation details; read the linked operation contract and use executor `--help` only for unspecified options.

**Entrypoint:** none bundled; use the documented runtime or generic Job route.

Use QBICS when the study concerns a same-spin crossing or related crossing-point optimization supported by an installed QBICS program. This Skill supplies the scientific setup and generic Job handoff; the repository routes QBICS through an explicit installation and generic Job.

## Recommended workflow

1. Define the two electronic states, spin/electronic character, crossing coordinates, geometry input, charge, multiplicity, solvent, and expected outputs.
2. Inspect the selected environment's QBICS executable with its version/help output and read the installed program documentation. Record the executable digest and required files.
3. Prepare a generic Job with an explicit script/backend, staged input files, control parameters, and collected output paths. Use the [method-selection request pattern](../method-selection/references/request_preparation.md).
4. Run the crossing search, parse the native evidence with a declared script, and retain state energies, gradients, convergence, and seam/character diagnostics.
5. Compare the candidate with `surface-crossing` checks when its distinct-spin Gaussian crossing contract applies; use the installed QBICS documentation for QBICS-specific criteria.

A task-specific wrapper may be invoked through generic `job_start` with `--script` and `--backend`. Preserve the exact command, environment, inputs, outputs, and parser version in the research record. The repository's bundled projected-gradient implementation is described in [surface-crossing](../surface-crossing/SKILL.md) and is a separate operation.
