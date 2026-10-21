# CREST backend contract

This reference contains only the registered backend boundary. `chemical.crest@1`
stages a chemical-material/1 input, invokes the configured CREST 3.0.2 binding,
and records the native output files and source digests. The adapter preserves
method, solvent, charge, multiplicity, member IDs, coordinates and partial-run
status. Unsupported versions and native options must use a generic Job with an
explicit declaration.

`chemical.crest-ensemble@1`, `chemical.ensemble-select@1` and
`chemical.complex-sample@1` consume or transform these records through the
structure binding. Their member selection and rigid-placement semantics are
operation contracts, documented separately in [ensemble operations](crest_ensemble.md).

A backend receipt is execution evidence. It does not claim exhaustive sampling,
minimum certification, reaction identity, free energy or transition-state
validity. Those questions belong to the operation and validation Skills.
