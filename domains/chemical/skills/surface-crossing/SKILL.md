---
name: surface-crossing
description: Search and check distinct-spin Gaussian crossing candidates using energy-gap, projected-gradient, and seam-curvature evidence.
---

# Distinct-spin surface crossings

[Chinese version](SKILL.zh-CN.md)

## Script routing

Use the registered executor ID and the [script routing map](../../../../docs/skill-script-routing.md#surface-crossing) to choose the entrypoint, CLI, inputs, and primary outputs. The map is authoritative for routing; implementation helpers under `scripts/` are not standalone commands. Do not inspect source code to discover invocation details; read the linked operation contract and use executor `--help` only for unspecified options.

**Entrypoints:** `chemical.mecp-gaussian@1` → `skills/surface-crossing/scripts/crossing.py`; `chemical.crossing-check@1` → `skills/surface-crossing/scripts/crossing.py`.

Use this Skill for a crossing between two Gaussian HF/DFT surfaces with different spin multiplicities. The native search is `chemical.mecp-gaussian@1`; independent numerical evidence is `chemical.crossing-check@1`.

## Workflow

1. Prepare an input containing the two state definitions, charge, multiplicities, starting geometry, Gaussian method/basis, and convergence settings.
2. Run `chemical.mecp-gaussian@1` through the path_gaussian environment and retain the candidate geometry, state energies, gradients, projected-gradient norm, gap, and convergence record.
3. Run `chemical.crossing-check@1` on the collected candidate. Inspect energy gap, projected gradient, and optional constrained seam curvature together.
4. Compare state-character continuity and SCF stability with the numerical seam evidence. Feed a geometry with a useful crossing direction to `candidate-generation` or `validation` only with its crossing context attached.

The registered checker uses the `structure` binding and ordinary Jobs. Read [crossing execution](references/crossing_execution.md) for schema and thresholds. A small gap is a screening signal; the crossing decision uses the gradient/curvature and state records as a package.
