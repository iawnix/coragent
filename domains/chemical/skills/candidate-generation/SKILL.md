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

For an explicit DA hypothesis, [prepare_path.py](scripts/prepare_path.py) generates
QST2 candidates and IRC inputs with stable atom order. Follow [gaussian_path.md](references/gaussian_path.md)
for the executable path and registered validators; it does not establish exhaustive mechanism coverage. A Skill without local scripts may use another Skill's runner
or installed software; check those routes before declaring the method unavailable.
Read [candidate_generation.md](references/candidate_generation.md) for method
criteria and [ase_neb_executor.md](references/ase_neb_executor.md) for NEB availability and prerequisites.

The bundled DA path supports six neutral, non-aromatic carbon reaction centers. Aromatic, charged or heteroatom centers outside that scope are unassessed, not evidence against the proposed chemistry. RDKit perceives aromaticity again when parsing Kekule SMILES; rewriting the same graph cannot extend this helper. Use explicit bond-change checks and independently prepared candidates or another justified method. Generated IRC inputs use CalcFC to recompute the Hessian at the checkpoint geometry; include that cost in the budget.
