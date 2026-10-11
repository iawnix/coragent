---
name: crest
description: Run bounded CREST conformer searches, import and screen ensembles, sample rigid-fragment complexes, and export members for independent refinement.
---

# CoRAgent CREST and ensembles

[Chinese version](SKILL.zh-CN.md)

Use this Skill for independent conformer or complex preparation; R/P and a
reaction name are not required. Read [the ensemble contract](references/crest_ensemble.md)
for input schemas, Job examples, limits and interpretation.

Choose the operation that matches the available evidence:

- `chemical.crest@1`: bounded CREST 3.0.2 GFN1/GFN2 search of an explicit
  ground-state material with known charge, multiplicity and coordinates.
- `chemical.crest-ensemble@1`: import the run receipt and exact source material;
  retain member identity inference, energy consistency and partial-result status.
- `chemical.ensemble-select@1`: bounded symmetry-aware geometric clustering and
  comparable electronic-energy screening, recording every member's decision.
- `chemical.complex-sample@1`: sample rigid orientations/placements from separate
  materials or perturb a supplied complex; preserve original coordinates and lineage.

Prepare and submit each operation through the existing Job lifecycle. CREST uses
the `crest` backend with a configured native executable and Python wrapper
binding. Import, selection and complex sampling use `structure` (RDKit/NumPy).
Other verified CREST versions/features remain available through generic Jobs;
this versioned wrapper does not establish their compatibility.

Inspect primary files and per-member evidence before reuse. A complete search
receipt is not an exhaustive search, minimum certification or verified identity.
Unknown identity/state stays unresolved; mixed methods/solvents are not ranked.
Retain the source ensemble, decisions, exported XYZ/materials and refinement
manifest. Submit selected members to explicit compatible SP/optimization Jobs;
do not silently change solvent, state or method. Sampling constraints do not
carry into subsequent optimization. CREST energies are not free energies.
