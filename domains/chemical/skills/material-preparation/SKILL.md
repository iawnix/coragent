---
name: material-preparation
description: Prepare molecular materials and explicit reaction definitions from names, SMILES, or coordinates while preserving identity, state, mapping, and provenance.
---

# Material preparation

[Chinese version](SKILL.zh-CN.md)

Use this Skill at the start of a calculation or reaction study. It converts names, SMILES, supplied XYZ, and reaction descriptions into material records that downstream geometry and electronic-structure Jobs can consume.

## Preparation workflow

1. Preserve the user's original text or coordinates as the source record.
2. For a name, use `chemical.resolve@1` with the configured resolver preference. For a SMILES or XYZ, use `chemical.material@1` directly. Keep fragments, charge, multiplicity, explicit-H order, stereochemistry, and source metadata.
3. If a name cannot be resolved, write one or more candidate SMILES with a rationale and use `chemical.resolve-candidates@1`; inspect valence, charge, stereochemistry, and formula before selecting a working branch.
4. Use `chemical.inspect@1` for graph and valence checks. Use `chemical.seed@1` to generate a missing 3D geometry; preserve and inspect supplied coordinates; use a new embedding when a 3D geometry is missing.
5. For reactions, use `chemical.reaction@1` with explicit reactant/product mapping and `--transformation`. Add `chemical.map-candidates@1` when several atom correspondences are possible.
6. Compare calculated and target structures with `chemical.compare@1`; use `chemical.conformer-compare@1` for symmetry-aware geometry comparison and `chemical.reorder-tensors@1` for gradients, Hessians, and modes.
7. Use `chemical.local-diagnostics@1` for reaction-center distances, contacts, and local alignment, then hand a complete material and mapping record to `reaction-investigation`.

## Registered operations and examples

```text
chemical.resolve@1                 name -> resolved structure
chemical.resolve-candidates@1      candidate SMILES -> checked alternatives
chemical.material@1                SMILES/XYZ -> material record
chemical.inspect@1                 graph/valence inspection
chemical.seed@1                    SMILES -> initial 3D geometry
chemical.reaction@1                mapped reaction definition
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
