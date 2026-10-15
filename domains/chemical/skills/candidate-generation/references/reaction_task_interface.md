# Reaction-search task interface

Candidate generation and transition-state validation exchange one declared
elementary-step interface. The interface is a research contract, not a
reaction-name registry.

## Input contract

Every operation receives a declared step containing:

- mapped reactant and product identities, including fragments and atom order;
- charge, multiplicity and electronic-state declaration;
- explicit bond changes, and explicit mapped hydrogen changes when a hydrogen
  trajectory matters;
- a candidate or saddle geometry with its source Artifact and method metadata;
- the requested operation and its evidence limits.

The input may be incomplete. An unresolved reaction center is recorded as
unresolved and is not silently inferred from a geometry.

## Operation boundaries

| Operation | Owns | Does not own |
| --- | --- | --- |
| Candidate generation | Constructing bounded geometries, scans, QST, NEB or orientation samples and recording provenance | Saddle-point certification, endpoint basin assignment or mechanism conclusions |
| Validation, including IRC | Checking stationary-point, mode, state, geometry, stereochemical and bidirectional connectivity evidence | Generating a candidate or choosing a method |

`candidate-generation` may call a Gaussian, xTB or ASE backend through a Job.
`validation` may prepare and run IRC through a Gaussian backend or another
justified runner, and consume normalized evidence from any supported backend. The backend determines
input and parser limits; the operation Skill determines the scientific question.

## Output contract

Each operation emits a provenance-bound Artifact or Result that records the
declared step, source identities, method/backend, settings, status, evidence
observed and limitations. A generated geometry is a candidate fact. A successful
calculation is execution evidence. A scientific verdict is emitted only by the
operation's documented evidence checks.

