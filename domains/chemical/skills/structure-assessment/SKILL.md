---
name: structure-assessment
description: Turn a molecular or reaction-candidate geometry into an evidence-bound structural description for the next calculation.
---

# Structure assessment

[Chinese version](SKILL.zh-CN.md)

## Script routing

Use the registered executor ID and the [script routing map](../../../../docs/skill-script-routing.md#structure-assessment) to choose the entrypoint, CLI, inputs, and primary outputs. The map is authoritative for routing; implementation helpers under `scripts/` are not standalone commands. Do not inspect source code to discover invocation details; read the linked operation contract and use executor `--help` only for unspecified options.

**Entrypoints:** `chemical.structure-cognition@1` → `skills/structure-assessment/scripts/run.py`.

Use this Skill before choosing or revising a calculation when the Agent needs a common description of a material: identity, graph, fragments, electronic declaration, reaction-center geometry, and comparison with a reference structure.

## What to inspect

Provide a material JSON and a context JSON containing `role_hint`, `reaction_center`, `bond_changes`, and an optional same-atom-order reference. The executor reports atom order, graph availability, fragments, charge/multiplicity, local distances, compression/elongation, fragment separation, and geometry observations. It also lists unresolved inputs and useful follow-up operations.

Use the report to decide whether to generate a seed, sample conformers, change a reactive pose, prepare a path, or proceed to an electronic calculation. Compare the actual reaction-center distances and fragment contacts with the intended bond changes; a non-equilibrium distance can be a deliberate TS seed.

## Registered executor

`chemical.structure-cognition@1` is implemented by `skills/structure-assessment/scripts/run.py` and accepts `--material`, `--context`, and `--output`. Run it through a Job and attach the report to the material or candidate Artifact. Pair it with `geometry-preflight` for coordinate screening and `material-preparation` for graph/mapping repairs.

Read [structure assessment](references/structure_assessment.md) for the context schema and output fields. The report is an observation record; mechanism, TS, and energetics decisions are made by the corresponding Skills using this record.
