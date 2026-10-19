# Prepare atom mapping before geometry

[中文](reaction_mapping.zh-CN.md)

Prepare correspondence on molecular graphs before generating 3D seeds, searching
conformers, or optimizing species. Carry the selected identities through candidate
construction, calculations, and IRC analysis.

## Working procedure

1. Preserve the original SMILES and import each complete reaction side with
   `chemical.material@1`. Include participating protons, counterions, and other
   species needed for the proposed step's composition. Inspect formula, charge,
   isotopes, stereo, and explicit-H rows. SMILES import needs no coordinates.
2. Establish persistent reactant labels across all fragments, including every H.
   Retain supplied maps and allocate unused positive integers to remaining atoms.
   Expand H into graph atoms before writing mapped SMILES: `[CH3:8]` labels only
   carbon; `[H:31][C:8]([H:32])([H:33])…` also labels its three H atoms. Save the
   correspondence from source material IDs to these labels.
3. For a proposed product graph, use `chemical.map-candidates@1 --mode reaction`
   on the two materials. Fix known pairs with `--fixed-pairs` using local atom IDs.
   Review candidate `pairs`, `left_to_right`, and bond changes against the proposed
   chemistry. The search ranks by bond-order edits; combine that score with the
   elementary-step hypothesis. See [structure analysis](structure_analysis.md)
   for execution examples and search coverage fields.
4. Transfer each reactant label to its selected product partner. Save the complete
   pair table, selected candidate, and mapped SMILES for both sides. For a hypothesis
   with no H transfer, H follows its mapped parent atom. For H/proton transfer,
   identify the moving H and its old and new attachment explicitly. Keep relevant
   symmetry-equivalent alternatives and record search coverage.
5. Use `chemical.reaction@1` to **check the supplied mapping** and declared changes.
   Prepare its request through the generic executor, submit with `job_start`, and
   collect results for map coverage, element/charge balance, and bond changes.
   Resolve discrepancies in the selected hypothesis before preparing its geometry.
6. Generate each connected species with `chemical.seed@1` from fully mapped SMILES.
   Save its `atoms` table alongside the XYZ: it binds zero-based coordinate rows to
   map labels, elements, isotopes, and H parents. Conformer search, assembly, and
   optimization inherit that table. When software changes row order, record and
   apply the permutation to coordinates and associated tensors. Arrange path
   endpoints in the same map-label order; equal element sequences are insufficient.

If products are still under investigation, complete steps 1–2 first and generate
reactant geometry using those identities. Map each later intermediate/product
hypothesis onto the same identities when its graph is proposed. Geometric comparison
can refine equivalent assignments while preserving the original mapping and branch
history.

## Declaring a transformation

Use `--transformation <file.json>` with `kind: "explicit"` and the complete
`bond_changes` list. Each entry has mapped `atoms`, `before` and `after` bond orders
(0 means no bond). Optional `hydrogen_changes` entries use `atom`, `before` and
`after` for per-atom H counts. Explicit mapped H bond changes describe individual
transfers; counts describe their net effect. This declaration works for any
reaction class.

Register the mapping, transformation, and checked results as Artifacts in the
step record. Use these labels for reactive pairs, constraints, mode interpretation,
and both IRC endpoint comparisons.

## Recording a hydrogen transfer

For a hypothesis where H with map label 3 moves from atom 1 to atom 2, record
its two bond changes in the transformation file:

```json
{
  "kind": "explicit",
  "bond_changes": [
    {"atoms": [1, 3], "before": 1, "after": 0},
    {"atoms": [2, 3], "before": 0, "after": 1}
  ]
}
```

Use actual map labels from the selected correspondence and include all other
bond-order changes in that step. Generate this file from the current hypothesis
and compare it with the graphs through `chemical.reaction@1`. The Agent prepares
this record from the research task and its mechanism reasoning.
