# Candidate Generation

Candidate generation creates structures for transition-state optimization and
characterization.

## Root Choice

Choose among chemically informed construction, constrained scans, QST2/QST3,
direct TS optimization, NEB/path interpolation, conformer search, fragment
approach sampling, or another justified method. Select their order from the
current hypothesis and evidence.

Before QST2/QST3, verify atom count/order or an explicit map, charge/spin,
endpoint preparation/optimization status and conformational compatibility. Assess
whether the pair is a plausible elementary-step hypothesis; supplied R/P may span
several steps. Record why this interpolation tests the proposed step.

## Execution without a reaction-specific recipe

Express the hypothesis as mapped reactant/product structures, the complete proposed
bond changes, charge/spin and relevant geometric coordinates. Preserve atom identity
and order through endpoint preparation, candidate construction and solver input.
Reaction labels may explain the hypothesis but are not execution prerequisites.

For QST2/QST3, prepare explicit Gaussian inputs from compatible endpoints (and a
candidate TS geometry for QST3), then use chemical.gaussian-input through the existing
prepare/start/collect workflow. For scans, direct TS optimization or NEB, select the
appropriate solver interface and declare its actual inputs and outputs. If construction
or analysis needs custom code, use a bounded task script with the configured scientific
environment; registering a new executor for each reaction class is not required.

Choose mode-displacement and endpoint checks from the proposed transformation.
Do not apply a bundled helper's fixed bond count, topology or electronic-state rules
to unrelated reactions. Generic execution does not guarantee a successful search or
a valid scientific result; retain unsupported checks and failed attempts as evidence.

## Recording

Read and continue the existing Node for this question. Put candidate hypotheses and the investigation approach in its plan, and preserve changes in notes. Create another Node only for a new research objective needing its own continuing investigation and judgment, not for each candidate or calculation step.
Bind all seeds through logical artifact IDs. Link every immutable compute intent
and preserve method/parameters. After collection, record candidate coordinates,
energies, constraints, and provenance when useful; distinguish these evidence types within
the same note or Result rather than requiring a record for each item.

Use research notes for distorted geometry, atom-map ambiguity, fragment collapse,
unexpected bonding, electronic-state concern, or missing conformers.

## Follow-Up

A candidate still requires scientifically appropriate optimization and
characterization. For a classical TS, distinguish these evidence types:

- stationary-point/convergence evidence;
- imaginary-mode/reaction-coordinate assignment;
- bidirectional connectivity and endpoint identity;
- additional state, robustness, stereochemical, or thermochemical checks.

Use the existing node_id. Record observations, scientific criteria and next-step decisions in a research_update note, or publish a reusable conclusion with research_result, citing collected materials and limitations. Do not duplicate the same finding in both records or task progress. A completed computation does not establish a scientific conclusion or require a new Node or Result.

Supplied material endpoints can use `chemical.qst-prepare@1`; bounded scan and
xTB NEB recipes are documented in [path operations](path_search.md). These
interfaces do not certify that an endpoint pair describes one elementary step.

For new NEB paths, use [ASE v2](ase_neb_executor.md). Choose restart frames by geometry, force and reaction-coordinate evidence, not the lowest energy of a failed TS search; see [search recovery](../../method-selection/references/search_recovery.md).
