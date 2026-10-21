# Skill catalog and loading language

[English](README.md) | [简体中文](README.zh-CN.md)

**English `SKILL.md` is the default entrypoint.** Pi discovers names, descriptions,
and paths; the Agent reads bodies and references on demand. `SKILL.zh-CN.md` is
a Chinese translation, not an automatic locale switch or duplicate skill.
The Agent can explicitly read it when needed and respond or write reports in
the user's requested language. See [Skills and the execution catalog](../docs/EXTENSIONS.md)
for implementation and resource maintenance.

Skills guide scientific operations, method/backend adapters, and research
coordination using bundled helpers or task-specific inputs and scripts.
The catalog intentionally distinguishes those roles. A catalog classification
uses categorized executor paths as the canonical interfaces. Convenience entries in
`execution.json` do not set a capability ceiling.

`core/` groups domain-independent workflow, memory, queue management and email Skills. `chemical/` groups chemistry methods, software adapters, validation and reports, with their executor catalog, environment profiles and shared code. Both groups use the same discovery mechanism. Core has no chemical dependency; chemical Skills consume the generic workflow and task-selected execution target.

### Scientific operations and evidence

These Skills describe the scientific object or question being handled. They may
delegate execution to one of the backend adapters below.

| Skill | Purpose |
| --- | --- |
| [candidate-generation](chemical/candidate-generation/SKILL.md) | Generate candidate geometries for transition-state and reaction-path searches from mapped endpoints, bond changes, constraints and structural evidence. |
| [material-preparation](chemical/material-preparation/SKILL.md) | Prepare molecular materials and explicit reaction definitions while preserving identity, state and provenance for later scientific operations. |
| [energetics](chemical/energetics/SKILL.md) | Evaluate electronic energies, ZPE and thermal corrections, free and reaction energies, barriers, conformer ensembles, TST rates, competitive branches, mass-action networks, and energy profiles. |
| [reaction-investigation](chemical/reaction-investigation/SKILL.md) | Form, compare, and revise reaction-mechanism hypotheses using explicit species identities, atom mappings, elementary steps, alternatives, and falsifiers. |
| [reactive-geometry](chemical/reactive-geometry/SKILL.md) | Construct and revise reactive orientations and local candidate geometries from explicit reaction-center evidence. |
| [structure-assessment](chemical/structure-assessment/SKILL.md) | Build evidence-bound structural descriptions of materials and reaction candidates without certifying a mechanism or transition state. |
| [surface-crossing](chemical/surface-crossing/SKILL.md) | Search local different-spin crossing candidates with Gaussian and check the energy gap, projected gradient and optional seam curvature. |
| [validation](chemical/validation/SKILL.md) | Validate transition-state candidates as saddles with intended modes, structures, electronic states, stereochemistry, and bidirectional IRC connectivity. |

### Method and backend adapters

These Skills describe a calculation method or software binding. They supply
recipes and parser limits to the scientific operations above; they do not define
the research question by themselves.

| Skill | Purpose |
| --- | --- |
| [cf22d](chemical/cf22d/SKILL.md) | Adapt declared CF22D/PySCF inputs, execution and parser evidence to the registered pyscf binding. |
| [crest](chemical/crest/SKILL.md) | Adapt CREST for bounded conformer and rigid-fragment ensemble operations while preserving identity, evidence and provenance. |
| [gaussian](chemical/gaussian/SKILL.md) | Adapt Gaussian for declared quantum-chemical calculations and inspect its supported input and parser boundaries. |
| [qbics](chemical/qbics/SKILL.md) | Assess QBICS applicability and verify an installed command, its inputs and validation needs before running a bounded research Job. |
| [xtb](chemical/xtb/SKILL.md) | Adapt declared xTB inputs, native bindings and parser evidence without choosing the scientific operation. |

### Coordination, controls and delivery

These Skills coordinate choices, apply cross-cutting input controls, and deliver
persistent evidence and presentation across scientific operations and backend
adapters.

| Skill | Purpose |
| --- | --- |
| [email](core/email/SKILL.md) | Provide generic SMTP email delivery with durable idempotent receipts. |
| [geometry-preflight](chemical/geometry-preflight/SKILL.md) | Apply a cross-task coordinate safety screen before electronic-structure jobs while allowing declared reaction-center non-equilibrium geometry. |
| [method-selection](chemical/method-selection/SKILL.md) | Coordinate scientific method and backend selection with a named compute environment, including fixed-method execution preparation. |
| [chemical-report](chemical/chemical-report/SKILL.md) | Write illustrated research reports from evidence, with molecular structures, energy plots, data tables, methods, conclusions, and traceable sources. |
| [research-memory](core/research-memory/SKILL.md) | Resume research through persistent problem Nodes, explicit relations, execution observations and immutable Results. |
| [research-workflow](core/research-workflow/SKILL.md) | Coordinate research problems, domain Skills, durable Jobs, materials and evidence-based Results through the native Pi loop. |

### Compute infrastructure

| Skill | Purpose |
| --- | --- |
| [tri-operations](core/tri-operations/SKILL.md) | Deploy and maintain TRI server and compute-node services, configure resources, and diagnose task scheduling, execution and recovery. |
| [batch-schedulers](core/batch-schedulers/SKILL.md) | Configure TRI, PBS, Torque and Slurm targets, select resources and diagnose native queue/accounting results. |
