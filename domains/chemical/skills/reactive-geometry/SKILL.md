---
name: reactive-geometry
description: Construct reactive complexes and revise failed TS guesses using local reaction-center frames, explicit geometry edits, and evidence-bound mode displacements.
---

# Reactive geometry editing

[中文](SKILL.zh-CN.md)

Use this Skill to place separate reactants in a proposed reactive orientation or
revise an existing scan, NEB, optimization or IRC geometry for another search.
`chemical.reactive-geometry@1` edits existing coordinates through the ordinary Job
lifecycle; it does not determine a mechanism or run a quantum solver.

Express the hypothesis with atom IDs and explicit `bond_changes`. Choose local
approach axes/planes, movable groups and distances from the molecular graph,
geometry and available chemical evidence. Names do not select reaction recipes.
When multiple sites, faces, proton relays or conformers are plausible, retain
separate hypotheses instead of treating one geometrically valid seed as decisive.

For construction/editing and executable examples, read the
[input and execution contract](references/reactive_geometry.md).
It supports directed rigid placement, group distance/angle/dihedral edits and
Cartesian mode displacements. It rejects clashes, protected-bond distortion and
unmet final constraints, exporting accepted and rejected geometries with provenance.

For recovery from a previous calculation:

- Select the exact source frame using geometry, gradient, mode and path evidence;
  the lowest-energy failed TS frame is often just a stable basin. Use
  [search recovery](../method-selection/references/search_recovery.md).
- Bind mode vectors to that material's digest, full atom order and coordinate axes.
  Reordering XYZ alone does not rotate or reorder tensors. Convert mass-weighted
  modes or gradients explicitly; never normalize each atom separately.
- Interpret actual charge, bond-order, spin or orbital evidence as a hypothesis,
  then translate it into explicit geometric edits. Request missing analyses through
  a suitable solver; this executor does not extract or invent electronic evidence.
- Inspect final reaction-center coordinates and rejected candidates. Revise the
  direction, group selection, conformer or mechanism if checks fail; repeated
  identical edits are not new evidence. Respect the research scope and Job budget.

Use [CREST](../crest/SKILL.md) for internal conformer exploration where appropriate.
Use existing Gaussian/xTB Jobs for method/state/solvent-compatible constrained
preoptimization when needed, carrying constraints explicitly. Unconstrained
minimization can destroy a TS-directed guess; classical reactant force fields can
bias forming/breaking bonds. Recheck the refined geometry and retain its original
candidate lineage. Geometry scores are neither energy nor predicted TS quality.

Pass selected material/XYZ to [candidate generation](../candidate-generation/SKILL.md):
QST3 needs explicit guess mapping; QST2/ASE NEB need independently prepared,
compatible endpoints. For a classical TS, inspect the imaginary mode and
bidirectional IRC with [validation](../validation/SKILL.md). Missing optimization,
electronic-state evidence or connectivity verification remains unresolved.
