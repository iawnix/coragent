---
name: structure-assessment
description: Build an evidence-bound structural interpretation of molecular or reaction-candidate geometries, separating role, reaction-center changes, geometry observations, and uncertainty without certifying a transition state.
---

# Structure assessment

Use this Skill when the Agent needs a shared structural description before
choosing or revising a calculation. It organizes what is known about a
material, its graph, coordinates, reaction-center hypothesis, and optional
reference structure. It is useful for reactants, products, intermediates,
reactive complexes, optimized structures, and TS candidates.

The report is a cognition aid, not a workflow gate. It may say that a role or
reaction center is unresolved. Do not infer a reaction mechanism, trajectory,
electronic state, minimum, saddle point, or TS identity from a geometry alone.
Use explicit `role_hint`, `reaction_center`, and `bond_changes` when they are
known. Preserve competing hypotheses in separate context inputs rather than
merging them into one conclusion.

The deterministic executor reports:

- structure identity, graph availability, atom order, fragments and electronic
  declarations;
- geometry safety and observations of compression, elongation, collapse or
  fragment separation;
- local distances around the declared reaction center and the geometric effect
  of each proposed bond change;
- optional same-atom-order comparison with a reference material;
- unresolved inputs, evidence limitations and suggested follow-up Skills.

`safe` means only that the coordinates are not obviously unusable. A declared
forming or breaking bond can be geometrically non-equilibrium. Severe overlap
and non-finite coordinates remain observations from `geometry-preflight` and are
not reinterpreted as a valid TS geometry.

For the input and output contract, read
[structure_assessment.md](references/structure_assessment.md). The standalone
executor is `chemical.structure-cognition@1`; it accepts a material JSON and a
small context JSON and always emits a report unless the input contract itself
is malformed.
