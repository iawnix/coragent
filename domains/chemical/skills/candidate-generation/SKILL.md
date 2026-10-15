---
name: candidate-generation
description: Generate candidate geometries for transition-state and reaction-path searches from mapped endpoints, bond changes, constraints and available structural evidence.
---

# CoRAgent TS Candidate Generation

[Chinese version](SKILL.zh-CN.md)

Use this Skill to produce candidate geometries for a proposed elementary step.
Candidate generation does not establish a transition state; validation belongs
to `validation`, and method or Backend choice belongs to
`method-selection`.
This is the scientific search-operation layer. Gaussian, xTB and other software
recipes remain backend concerns; their presence here only describes how a search
can be executed through the existing Job interface.

Start from explicit reactant/product identities, atom mapping, charge,
multiplicity, and relevant conformers. Choose chemically informed construction,
a relaxed scan, QST2/QST3, direct TS optimization, NEB, or fragment orientation
sampling according to the proposed bond changes and available evidence. Bind
all seeds and generated structures as Artifacts with recorded production provenance and preserve the
method, constraints, frame selection, and provenance.

When an existing candidate needs a new approach orientation, reaction-center distance, or
evidence-supported local distortion, use the [reactive-geometry](../reactive-geometry/SKILL.md) Skill first and pass its
provenance-preserving candidates to QST, scans, or NEB.

Do not promote a scan maximum, NEB image, interpolation, or constrained
structure as a verified saddle point. Record useful candidates as facts about
the generated structure and failed or distorted searches as issues only when
they inform the research question.

Describe each proposed step through mapped endpoints, bond changes and relevant
coordinates or constraints. Choose a candidate-generation method from those inputs;
reaction names do not select a mandatory script or validator. New reaction classes
do not require new tools or Skill sections. Use explicit solver inputs or a bounded
task script through the existing Job interface, preserving atom correspondence and
checking each method's prerequisites. For Gaussian QST/TS inputs, use the
[Gaussian Skill](../gaussian/SKILL.md).

The [mapped path preparer](references/path_preparation.md) accepts explicit bond
changes and either automatically embedded single-fragment endpoints or supplied
mapped geometries. It writes QST2 inputs through the existing Job recipes. Its
optional geometry strategies do not define the scientific verdict.
Check the input and validation scope before reuse; an unsupported preparation case
does not make the research method unavailable. Other methods can use shared runners,
explicit solver inputs or task scripts.

See [script layout](references/script_layout.md) for the implementation boundaries and compatibility entrypoints.

Read [candidate_generation.md](references/candidate_generation.md) for method
criteria and [ase_neb_executor.md](references/ase_neb_executor.md) for NEB availability and prerequisites.
Use the shared [reaction-search task interface](references/reaction_task_interface.md)
when handing a candidate to IRC or validation.

Read [specialized path preparation](references/gaussian_path.md) only when using
that optional compatibility recipe; its local contract does not define the scope
of candidate generation as a whole. Pass a selected candidate to `validation` for
saddle evidence and bidirectional IRC connectivity; preserve endpoint and solver
metadata when that validation prepares IRC inputs.

For supplied material endpoints, use `chemical.qst-prepare@1` for QST2/QST3.
For bounded 1D/2D grids use `chemical.scan-xtb@1` or `chemical.scan-gaussian@1`;
for xTB gradients/NEB use `chemical.gradient-xtb@1` and `chemical.neb-xtb@2`.
Read [material-based path operations](references/path_search.md) for schemas,
optional path environment bindings, resume rules and actual calculator limits.

Ground-spin Gaussian gradients and NEB are also available as `chemical.gradient-gaussian@1`
and `chemical.neb-gaussian@2`; their separate electronic settings and scope are in
[path operations](references/path_search.md).

Use [ASE NEB v2](references/ase_neb_executor.md) for new xTB/Gaussian band searches. Diagnose failed or distorted searches with [search recovery](../method-selection/references/search_recovery.md); inspect [local geometry](../chemical-input/references/local_diagnostics.md) and [trajectories](../report/references/research_tools.md) before choosing a restart frame.
