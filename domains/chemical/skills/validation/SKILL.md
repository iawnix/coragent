---
name: validation
description: Validate transition-state candidates as saddles with intended modes, structures, electronic states, stereochemistry, and bidirectional IRC connectivity.
---

# CoRAgent Transition-State Validation

[Chinese version](SKILL.zh-CN.md)

Use this Skill to decide whether a candidate is a defensible transition-state
structure. Candidate generation supplies the candidate; bidirectional IRC
connectivity is a validation dimension that tests its connection to declared
reactant and product basins.

For a reaction investigation, validation must return a decision to the
[reaction-investigation loop](../reaction-investigation/references/reaction_investigation.md):
validated saddle, candidate requiring another check, or a diagnosed failure with
the next construction/search operation. A missing criterion is unresolved evidence;
it is not a task blocker when a justified candidate or diagnostic next experiment
can still be generated. Validation closes one candidate's evidence loop, not the
whole reaction study.

Use `chemical.stationary-check@1`, `chemical.mode-check@1` and
`chemical.irc-check@1` for independent, reaction-independent checks on normalized
evidence. `chemical.gaussian-evidence@1` adapts a selected raw Gaussian log section.
Read [general_checks.md](references/general_checks.md) for contracts, executable
examples, thresholds and scope. These are executor Jobs, not a new acceptance gate.
Use `chemical.path-irc@1` to prepare bounded forward and reverse IRC inputs from
a validated saddle checkpoint, then execute them with the declared Gaussian or
other justified backend before collecting evidence.
Read [IRC input preparation](references/irc_preparation.md) for the preparation
contract and provenance requirements.

Verify optimization and stationary-point evidence, exactly one relevant
imaginary mode for a classical first-order saddle, displacement along the
proposed bond changes, charge/multiplicity and electronic-state consistency,
atom mapping, geometry, and stereochemistry. Inspect the primary output and
mode vectors; normal termination or one negative frequency alone is
insufficient.

Record the observations, scientific criteria, unresolved questions and next steps with research_update using the existing node_id and a note. Publish a reusable conclusion with research_result, citing collected materials and stating limitations. A completed computation does not establish a scientific conclusion.

Read [transition_state_validation.md](references/transition_state_validation.md)
for saddle and mode evidence,
[connectivity_validation.md](references/connectivity_validation.md) for basin
identity criteria used after path calculations, and
[structure_validation.md](references/structure_validation.md) for mapping,
alignment, and stereochemical comparisons.
The Gaussian-specific validation reference is owned here at [gaussian_validation.md](references/gaussian_validation.md).
The shared [reaction-search task interface](../candidate-generation/references/reaction_task_interface.md)
defines what validation consumes from candidate generation.


Registered validator: `job_start` with `validator_id="chemical.gaussian_frequency"`, a new `request_id`, and `input_artifact_ids=[<collected parsed.json artifact>]`. Its version is `1`. The runtime records actual execution and input digests. This checks normal termination and exactly one negative frequency only; mode character, geometry and IRC connectivity still require separate criteria.

Define forming/breaking bonds, atom transfers, or other coordinates from the
actual reaction hypothesis. Analyze collected primary outputs with suitable
scripts or the independent checks above through Jobs; reaction-specific validator registration is not
required. Before selecting the bundled [specialized path validators](../candidate-generation/references/gaussian_path.md),
check their topology and input scope. Their criteria are not a universal
definition of a transition state.

In particular, `chemical.reaction_mapping`, `chemical.gaussian_saddle` and
`chemical.gaussian_irc_connectivity` version 1 use the DA contract despite their
generic names. They return unassessed scope for other transformations; do not
interpret that as a failed reaction. See the [capability inventory](../method-selection/references/capabilities.md).

Checks are scoped evidence, not a universal research gate. Distinguish tool execution failure, unreadable evidence and a completed check that did not satisfy its criterion. `parsing.status`, `scientific_verdict` (when supplied), and receipt `provenance` keep these separate. Job input/output digests establish recorded provenance; a solver title marker is an additional cross-check, not the sole provenance record. Unknown evidence does not prohibit a reasoned next experiment. Record the uncertainty and chosen method without claiming a pass.

For each IRC direction, preserve the source saddle, direction, path Artifact,
endpoint Artifact and digest. Check agreement with the validated saddle,
termination, path completeness, final geometry and gradient when available.
Compare each endpoint with an explicitly selected reactant or product Artifact
using mapping, charge, electronic state, bond changes, key coordinates,
conformation and stereochemistry. Read [IRC validation](references/irc_validation.md)
for the detailed criteria; partial paths and unresolved endpoint identity remain
unresolved evidence.
