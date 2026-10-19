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

For reaction investigations, return accepted poses and rejected-candidate reasons to
the [mechanism-reasoning loop](../mechanism-reasoning/references/reaction_investigation.md).
An accepted pose is a handoff to constrained refinement or candidate generation, not
a reason to stop. Preserve the source material, fragment-internal geometry, mapping,
bond changes and actual local contacts in that handoff.

Treat this Skill as a tool kit and decision aid. The Agent chooses and combines
the tools from the evidence; the tools enforce input, coordinate and provenance
invariants but do not impose a fixed research sequence. Read the [capability map](references/capability_map.md)
and [call cards](references/call_cards.md) when choosing a tool, and use the
[recovery playbook](references/recovery_playbook.md) after a rejected geometry or
failed path.

When product mapping and explicit bond changes are available, call
`chemical.reactive-sites@1` first. It turns mapped changes into reaction-center
roles, local frames, alternative faces and family-specific starting hypotheses.
It does not invent a product or select a mechanism. Pass one or more returned
hypotheses to `chemical.reactive-pose@1`; keep alternatives when the evidence
does not distinguish them.

For SMILES-derived reactants with separate fragments, use
`chemical.reactive-pose@1` before QST/NEB. It consumes a material with explicit
coordinates and a mapped `bond_changes` list, derives local outward directions
from reaction-center neighborhoods, and samples fragment distance, approach
cone and twist. It returns several rigid poses after non-reaction contact
screening. This is a pose ensemble, not a mechanism guess or TS validation.

Express the hypothesis with atom IDs and explicit `bond_changes`. Choose local
approach axes/planes, movable groups and distances from the molecular graph,
geometry and available chemical evidence. Names do not select reaction recipes.
When multiple sites, faces, proton relays or conformers are plausible, retain
separate hypotheses instead of treating one geometrically valid seed as decisive.

The automatic pose executor does not replace explicit chemical hypotheses: its
local outward directions are geometry-derived starting hypotheses. Review the
returned transforms and retain multiple sites/faces when the reaction evidence
does not distinguish them.

After pose generation, use the existing `chemical.scan-xtb@1` recipe as a
constrained preoptimization by supplying a one-point distance/angle/dihedral
scan around the selected reaction coordinates. This applies a restrained xTB
potential, checks the actual final coordinates, and performs an unrestrained
physical energy evaluation at the optimized geometry. It is a candidate
preparation operation, not a TS search; do not replace it with unconstrained
`chemical.xtb@1` when the starting pose would otherwise collapse.

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
