# Mapping candidates, conformer comparison and tensor order

[中文](structure_analysis.zh-CN.md). These independent Jobs use the `structure`
backend (RDKit and NumPy). They require neither a TS task nor a product for tensor
reordering or comparison of two conformers. All emit `results/result.json`; inputs
and selected mapping candidates remain separate evidence, never overwritten.

## Contents

- [Mapping candidates](#mapping-candidates)
- [Conformer comparison](#conformer-comparison)
- [Tensor permutation](#tensor-permutation)
- [Execution](#execution)

## Mapping candidates

`chemical.map-candidates@1` takes `left` and `right` inputs in
`chemical-material/1` from [material import](material_input.md). Both need explicit
molecular graphs including their correspondence to any supplied XYZ. There is no
XYZ bond inference. Unresolved names/absent graphs return `not_assessed`.

`--mode reaction` (default) searches element/isotope-preserving bijections with
equal total charge. It ranks the best correspondences found by total absolute
bond-order changes, including explicit H. This is a graph-edit heuristic, not
mechanism inference, probability, a transition-state search or proof of atom
trajectories. Incomplete composition, missing counterions or different declared
charges produce `incompatible`; they do not establish chemical impossibility.

`--mode identity` additionally requires identical molecular graphs and specified
stereochemistry, preserving local charges, radicals and bond orders. Shared
explicit atom-map labels are fixed; different nonzero labels cannot match. Local
atom IDs are not maps. `--fixed-pairs '[["left-id","right-id"]]'` provides additional
one-to-one constraints. Contradictions with map labels are rejected.

Search is bounded: at most 256 atoms, `--max-search` 1..1000000 (default 20000
attempted assignments), `--max-candidates` 1..256 (default 64 retained equal-best
mappings). Large symmetric systems may exceed either bound. Inspect both
`search_complete` and `candidate_limit_reached`; a single stored candidate does
not imply uniqueness. `ambiguity` records multiple/unique/unknown/none among the
search evidence; `best_count_observed` counts equal-best leaves actually found.
An exhausted search with no candidate is `inconclusive`, not incompatibility.

The result is `chemical-correspondence/1`. Candidates contain `left_to_right`
zero-based indexes in the **current** material atom orders, local-ID `pairs`, bond
changes and `right_order`. The latter is a `chemical-material-order/1` permutation
of right rows into left correspondence order. It preserves right atom IDs; it does
not rename them to left IDs or certify that the candidate is physically correct.
Source file SHA256 digests bind both materials.

## Conformer comparison

`chemical.conformer-compare@1` takes the same inputs and mapping budgets. It uses
identity correspondences and supplied angstrom coordinates. No embedding,
optimization or individual fragment alignment occurs. For each retained mapping,
all-atom unweighted Kabsch alignment permits one translation and a proper rotation
(determinant +1) for the whole structure. It never aligns by reflection; supplied
stereochemical differences are incompatible even before geometry fitting.

`--rmsd-threshold` defaults to 0.1 angstrom. Optional
`--internal-coordinates '[["a","b"],["a","b","c"],["a","b","c","d"]]'`
selects distances, angles and signed dihedrals using **left local atom IDs**.
`--distance-tolerance` defaults to 0.1 angstrom and `--angle-tolerance` to 10 degrees;
dihedral differences wrap at 360 degrees. Undefined angles/dihedrals remain
unassessed. The same mapping must satisfy RMSD and every selected coordinate.
Choose thresholds for the study; this is not a universal conformer classifier.

`chemical-conformer-comparison/1` separates `geometry_status` from
`state_comparison`. A matching witness can establish `geometry_status=match`
despite incomplete coverage. A negative geometry conclusion requires complete
search and retention with all candidates failing; otherwise it is `inconclusive`.
`best` is the lowest-RMSD evaluated candidate, while `matching_candidate` is the
lowest-RMSD candidate satisfying all criteria, if one exists. Their
`candidate_index` indexes `correspondence.candidates`. The reported transform uses
row vectors: `aligned_right = right[mapping] @ rotation + translation`.

Conflicting known charge, multiplicity or state declarations give overall
`status=state_conflict`, even when geometry matches. Unknown settings remain
unknown; equal method/root/label declarations never prove wavefunction identity.
`status=geometry_match` is only geometric evidence. No material is automatically
merged, nor does a match prove convergence, energetic equivalence or state tracking.

## Tensor permutation

`chemical.reorder-tensors@1` takes `tensors` in `chemical-tensors/1` and `order` in
`chemical-material-order/1`. Use the importer's atom_order.json for tensors still
in original input order, or extract a selected mapping candidate's `right_order`
for tensors in the right material's current order. Do not apply either permutation
twice. `atom_ids` must exactly match `order.input_atom_ids`; never invent new IDs
to bypass a disagreement.

```json
{
  "schema_version": "chemical-tensors/1",
  "atom_ids": ["atom_1", "atom_2"],
  "axis_order": "atom-major-xyz",
  "representation": "cartesian",
  "units": {"gradient": "hartree/bohr"},
  "gradient": [[0.1, 0, 0], [-0.1, 0, 0]]
}
```

At least one tensor is required. Supply only non-mass-weighted Cartesian tensors,
with an explicit nonempty unit label for each provided tensor. Labels are preserved,
not converted or certified. Optional arrays are:

| Field | Shape / meaning |
| --- | --- |
| `coordinates`, `gradient` | N × 3; permute atom rows |
| `hessian` | 3N × 3N symmetric matrix; permute both axes with atom-major xyz indexes |
| `modes` | K × N × 3 Cartesian displacements; permute atom axis, retain mode order |
| `masses` | N positive atomic mass units; permute atom axis |
| `elements` | N chemical element symbols; permute atom axis |
| `frequencies_cm-1` | K finite signed wavenumbers; requires modes, retains mode order |

Nonfinite values, booleans, inconsistent shapes/IDs/inverses, asymmetric Hessians,
mass-weighted representations and unsupported fields are rejected. The output is
again `chemical-tensors/1`, with unchanged units, the permutation/inverse, source
digests and prior provenance, usable for an inverse round trip. No spatial rotation,
mass scaling or mode normalization occurs. Conformer alignment and tensor
permutation are distinct: reordering XYZ alone does not authorize reusing old
tensors, and the conformer rotation is not applied to them.

## Execution

Use absolute paths within the research work_dir; prepare the request, then submit
its request_file/request_sha256 and node_id through `job_start` and `job_collect`.

```text
"$CORAGENT_PYTHON" -m research_agent.application.executors --config "$CORAGENT_JOB_CONFIG" --environment local --executor chemical.map-candidates --version 1 --input left=<work_dir>/reactant/material.json --input right=<work_dir>/product/material.json --output <work_dir>/prepared/map.json -- --mode reaction --max-candidates 64
"$CORAGENT_PYTHON" -m research_agent.application.executors --config "$CORAGENT_JOB_CONFIG" --environment local --executor chemical.conformer-compare --version 1 --input left=<work_dir>/first/material.json --input right=<work_dir>/second/material.json --output <work_dir>/prepared/conformers.json -- --rmsd-threshold 0.1
"$CORAGENT_PYTHON" -m research_agent.application.executors --config "$CORAGENT_JOB_CONFIG" --environment local --executor chemical.reorder-tensors --version 1 --input tensors=<work_dir>/tensors.json --input order=<work_dir>/selected-order.json --output <work_dir>/prepared/reorder.json
```
