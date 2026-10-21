---
name: material-preparation
description: Prepare molecular materials and explicit reaction definitions from names, SMILES, or coordinates while preserving identity, state, mapping, and provenance.
---

# Material preparation

[Chinese version](SKILL.zh-CN.md)

## Script routing

Use the registered executor ID and the [script routing map](../../../../docs/skill-script-routing.md#material-preparation) to choose the entrypoint, CLI, inputs, and primary outputs. The map is authoritative for routing; implementation helpers under `scripts/` are not standalone commands. Do not inspect source code to discover invocation details; read the linked operation contract and use executor `--help` only for unspecified options.

**Entrypoints:** `chemical.resolve@1` → `skills/material-preparation/scripts/reaction/prepare.py`; `chemical.resolve-candidates@1` → `skills/material-preparation/scripts/reaction/prepare.py`; `chemical.inspect@1` → `skills/material-preparation/scripts/reaction/prepare.py`; `chemical.seed@1` → `skills/material-preparation/scripts/reaction/prepare.py`; `chemical.reaction@1` → `skills/material-preparation/scripts/reaction/prepare.py`; `chemical.compare@1` → `skills/material-preparation/scripts/reaction/prepare.py`; `chemical.material@1` → `skills/material-preparation/scripts/materials/material.py`; `chemical.map-candidates@1` → `skills/material-preparation/scripts/geometry/analysis.py`; `chemical.conformer-compare@1` → `skills/material-preparation/scripts/geometry/analysis.py`; `chemical.reorder-tensors@1` → `skills/material-preparation/scripts/geometry/analysis.py`; `chemical.local-diagnostics@1` → `skills/material-preparation/scripts/diagnostics/diagnostics_job.py`.

Use this Skill at the start of a calculation or reaction study. It converts names, SMILES, supplied XYZ, and reaction descriptions into material records that downstream geometry and electronic-structure Jobs can consume.

## Preparation workflow

1. Preserve the user's original text or coordinates as the source record.
2. For a name, use `chemical.resolve@1` with the configured resolver preference. For a SMILES or XYZ, use `chemical.material@1` directly. Keep fragments, charge, multiplicity, explicit-H order, stereochemistry, and source metadata.
3. If a name cannot be resolved, write one or more candidate SMILES with a rationale and use `chemical.resolve-candidates@1`; inspect valence, charge, stereochemistry, and formula before selecting a working branch.
4. Use `chemical.inspect@1` for graph and valence checks. For a reaction study, establish persistent atom identities, including explicit H, from these graphs before generating 3D seeds or starting optimization.
5. For each proposed elementary step, use `chemical.map-candidates@1 --mode reaction` to help select a correspondence, fixing known atom pairs. Save the full mapping and chosen bond changes; `chemical.reaction@1` checks the supplied mapped reaction with `--transformation`. Follow [mapping before geometry](references/reaction_mapping.md). When products are still being investigated, retain the reactant atom identities and attach each later hypothesis to them.
6. Generate missing 3D geometry from the selected mapped SMILES using `chemical.seed@1`. Preserve its per-row `atoms` table with the XYZ. Conformer generation and optimization inherit these identities; apply explicit row permutations when a tool changes order. Compare identities with `chemical.compare@1`, conformers with `chemical.conformer-compare@1`, and reorder associated tensors with `chemical.reorder-tensors@1`.
7. Use `chemical.local-diagnostics@1` for reaction-center distances, contacts, and local alignment, then hand a complete material and mapping record to `reaction-investigation`.

## Registered operations and examples

```text
chemical.resolve@1                 name -> resolved structure
chemical.resolve-candidates@1      candidate SMILES -> checked alternatives
chemical.material@1                SMILES/XYZ -> material record
chemical.inspect@1                 graph/valence inspection
chemical.seed@1                    SMILES -> initial 3D geometry
chemical.reaction@1                check supplied mapping and declared bond changes
chemical.map-candidates@1          correspondence candidates
chemical.conformer-compare@1       symmetry-aware geometry comparison
chemical.reorder-tensors@1         atom-order tensor transform
chemical.local-diagnostics@1       local geometry evidence
```

Prepare requests with the generic executor, submit with `job_start`, and collect the JSON/geometry Artifacts. Keep outputs under the research work directory and cite source digests when handing them to `reactive-geometry`, `candidate-generation`, or `method-selection`.

Read [material input](references/material_input.md), [name resolution](references/name_resolution.md), [reaction mapping](references/reaction_mapping.md), and [structure analysis](references/structure_analysis.md) for schemas and examples.

## Further references

- [local diagnostics](references/local_diagnostics.md)
- [script layout](references/script_layout.md)
- [structure input](references/structure_input.md)
