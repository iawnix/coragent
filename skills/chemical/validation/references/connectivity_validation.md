# Connectivity Validation

Connectivity asks whether a candidate path reaches the reactant and product
basins declared by a hypothesis. It is distinct from stationary-point and
imaginary-mode checks.

`chemical.irc-check@1` implements independent checks against mapped chemical endpoint identities, with reference-conformer differences reported separately; read [general_checks.md](general_checks.md) for path/endpoint contracts
and ambiguity handling. Its connectivity result does not replace mode character.

## Checklist

For each direction, inspect normal program termination, path completion, the
last geometry and gradient, endpoint optimization when needed, and endpoint
assignment against the declared reactant or product Artifact. Keep direction,
source path, endpoint optimization, and digest references explicit.

Verify atom mapping, element counts, charge, multiplicity/state, relevant
isotopes, bond changes, internal coordinates, stereochemistry, and any
short-path or maximum-step limitation. Execute geometry and stereochemical checks
with an available analysis tool or explicit Job and register its actual outputs.
`artifact_derive` records a descriptor only; it does not perform these checks.

## Recording And Evaluation

Record verified assignments, mapping, RMSD, coordinates, and source references
as `research note`. Missing direction, endpoints, path completion, or identity
evidence becomes an `research note`. Conflicting assignments are also an
research note with both source refs. research notes inform, but do not automatically
change, research Node state or hypothesis status.

Record the observations, scientific criteria, unresolved questions and next steps with research_update using the existing node_id and a note. Publish a reusable conclusion with research_result, citing collected materials and stating limitations. A completed computation does not establish a scientific conclusion.

An optimized IRC endpoint need not recover a selected Cartesian conformer. Compare
chemical graph/state/stereo before conformer similarity, and compare separated
fragments independently when diagnosing geometric differences. An unconstrained
Opt+Freq gives a local minimum, not necessarily the lowest conformer. A different
conformer matters when the research question explicitly distinguishes conformer
basins; record that difference without calling the species identity a mismatch.

For a truncated branch, extend it when the endpoint or subsequent relaxation is
ambiguous. Preserve the actual endpoint-to-optimization provenance. Extra
optimization or lower energy alone does not prove connection. A constrained scan
or path calculation may resolve a remaining ambiguity; reverse IRC from a
minimum is not a mandatory closure procedure.
