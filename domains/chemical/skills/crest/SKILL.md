---
name: crest
description: Adapt declared CREST conformer and rigid-fragment ensemble jobs, preserving member identity, records and provenance.
---

# CREST backend

This Skill owns the CREST executable binding, versioned input staging, ensemble
receipt parsing and member-level provenance. It does not choose a reaction
mechanism, rank a research hypothesis, certify a minimum or transition state, or
interpret ensemble energies as free energies. Use `material-preparation`,
`candidate-generation`, `energetics` or `method-selection` for those decisions.

Registered adapters:

- `chemical.crest@1` stages an explicit ground-state material for the configured
  CREST 3.0.2 GFN1/GFN2 binding.
- `chemical.crest-ensemble@1` imports a receipt and exact source material.
- `chemical.ensemble-select@1` and `chemical.complex-sample@1` use the
  structure binding for deterministic record operations around the CREST data.

The adapter preserves source material, member IDs, coordinates, method/solvent
metadata, energy fields, selection decisions and partial-result status. Unknown
identity or state remains an explicit record field. Other CREST versions and
native options require a generic Job with declared inputs and outputs; this
registered adapter does not claim compatibility for them.

Prepare and submit through the normal Job lifecycle. The detailed schemas and
staging boundaries are in the [backend contract](references/crest_backend_contract.md); ensemble operations are documented in [the ensemble contract](references/crest_ensemble.md).
