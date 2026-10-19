---
name: reactive-geometry
description: Construct reactive complexes and revise TS guesses with local reaction-center frames, explicit edits, and evidence-bound mode displacements.
---

# Reactive geometry construction

[Chinese version](SKILL.zh-CN.md)

Use this Skill when separate reactants need a chemically plausible encounter geometry or when a failed scan, NEB, optimization, or IRC frame needs a targeted revision. It edits coordinates and records provenance; the resulting pose is handed to candidate generation or constrained refinement.

## Build a reactive pose

Start with explicit atom IDs and `bond_changes`. `chemical.reactive-sites@1` derives reaction-center roles, local frames, alternative faces, and approach hypotheses from mapped structures. Pass each plausible hypothesis to `chemical.reactive-pose@1`, which samples fragment distance, approach cone, twist, and contact-safe rigid placements.

Use several poses when the reaction has competing nucleophilic sites, electrophilic faces, catalyst orientations, proton relays, or conformers. Select approach axes from local substituent directions and steric accessibility; set distances from the expected bond order and the intended scan range. Keep fragment-internal geometry fixed during pose generation.

## Refine and revise

Use `chemical.scan-xtb@1` or `chemical.scan-gaussian@1` for a restrained preoptimization around a forming/breaking distance, angle, or dihedral. One-point or short relaxed scans are useful for removing clashes while retaining reaction-center strain. Feed the resulting frames to `candidate-generation` rather than treating the relaxed structure as a TS.

For recovery, choose the source frame using gradient, imaginary-mode, path, and reaction-center evidence. `chemical.reactive-geometry@1` supports directed rigid placement, group distance/angle/dihedral edits, and Cartesian mode displacements. Bind a mode or gradient to the exact material digest, atom order, and coordinate axes before applying it. Reuse the same operation with changed direction, group selection, conformer, or mechanism when the first search collapses.

## Registered operations and handoff

- `chemical.reactive-sites@1` -> local site/frame analysis.
- `chemical.reactive-pose@1` -> fragment pose ensemble.
- `chemical.reactive-geometry@1` -> explicit geometry edits and mode displacements.
- `chemical.scan-xtb@1` / `chemical.scan-gaussian@1` -> constrained refinement.

Read [capability map](references/capability_map.md), [call cards](references/call_cards.md), and [recovery playbook](references/recovery_playbook.md) for schemas and examples. Run `geometry-preflight` after edits and before electronic-structure Jobs. Pass accepted geometries with their parent digest, bond changes, pose hypothesis, constraints, and rejected-candidate reasons to `candidate-generation`.

## Further references

- [reactive geometry](references/reactive_geometry.md)
