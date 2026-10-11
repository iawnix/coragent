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

Bundled helpers can encode narrower chemical assumptions. Check their
[documented scope](references/gaussian_path.md) before reuse; a helper's unsupported
input does not make the research method unavailable. A Skill without local scripts
may use shared runners or installed software.
Read [candidate_generation.md](references/candidate_generation.md) for method
criteria and [ase_neb_executor.md](references/ase_neb_executor.md) for NEB availability and prerequisites.
