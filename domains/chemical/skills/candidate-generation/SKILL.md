---
name: candidate-generation
description: Generate transition-state candidate geometries with chemically informed construction, scans, QST, NEB, or conformer and orientation sampling.
---

# CoRAgent TS Candidate Generation

[Chinese version](SKILL.zh-CN.md)

Use this Skill to produce candidate geometries for a proposed elementary step.
Candidate generation does not establish a transition state; validation belongs
to `validation`, and method or Backend choice belongs to
`method-selection`.

Start from explicit reactant/product identities, atom mapping, charge,
multiplicity, and relevant conformers. Choose chemically informed construction,
a relaxed scan, QST2/QST3, direct TS optimization, NEB, or fragment orientation
sampling according to the proposed bond changes and available evidence. Bind
all seeds and generated structures as Artifacts with recorded production provenance and preserve the
method, constraints, frame selection, and provenance.

Do not promote a scan maximum, NEB image, interpolation, or constrained
structure as a verified saddle point. Record useful candidates as facts about
the generated structure and failed or distorted searches as issues only when
they inform the research question.

Describe each proposed step through mapped endpoints, bond changes and relevant
coordinates or constraints. Choose a candidate-generation method from those inputs;
reaction names do not select a mandatory script or validator. New reaction classes
do not require new tools or Skill sections. Use explicit solver inputs or a bounded
task script through the existing Job interface, preserving atom correspondence and
checking each method's prerequisites. For Gaussian QST/TS and IRC inputs, use the
[Gaussian Skill](../gaussian/SKILL.md).

The [mapped path preparer](references/path_preparation.md) accepts explicit bond
changes and either automatically embedded single-fragment endpoints or supplied
mapped geometries. It writes QST2 and bidirectional IRC inputs through the existing
Job recipes. Its optional geometry strategies do not define the scientific verdict.
Check the input and validation scope before reuse; an unsupported preparation case
does not make the research method unavailable. Other methods can use shared runners,
explicit solver inputs or task scripts.
Read [candidate_generation.md](references/candidate_generation.md) for method
criteria and [ase_neb_executor.md](references/ase_neb_executor.md) for NEB availability and prerequisites.

Read [Gaussian path preparation](references/gaussian_path.md) for checkpoint, atom mapping and IRC input conventions.

The bundled DA path supports six neutral, non-aromatic carbon reaction centers. Aromatic, charged or heteroatom centers outside that scope are unassessed, not evidence against the proposed chemistry. RDKit perceives aromaticity again when parsing Kekule SMILES; rewriting the same graph cannot extend this helper. Use explicit bond-change checks and independently prepared candidates or another justified method. Generated IRC inputs use CalcFC to recompute the Hessian at the checkpoint geometry; include that cost in the budget.

For supplied material endpoints, use `chemical.qst-prepare@1` for QST2/QST3.
For bounded 1D/2D grids use `chemical.scan-xtb@1` or `chemical.scan-gaussian@1`;
for xTB gradients/NEB use `chemical.gradient-xtb@1` and `chemical.neb-xtb@1`.
Read [material-based path operations](references/path_search.md) for schemas,
optional path environment bindings, resume rules and actual calculator limits.

Ground-spin Gaussian gradients and NEB are also available as `chemical.gradient-gaussian@1`
and `chemical.neb-gaussian@1`; their separate electronic settings and scope are in
[path operations](references/path_search.md).
