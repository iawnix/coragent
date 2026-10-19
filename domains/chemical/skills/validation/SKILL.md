---
name: validation
description: Establish saddle, mode, electronic-state, structure, and IRC evidence for transition-state candidates.
---

# Transition-state validation

[Chinese version](SKILL.zh-CN.md)

Use this Skill after candidate generation and an actual TS optimization or path search. It assembles independent evidence into a decision for one candidate: validated saddle, candidate needing a specified check, or a failure with the next search action.

## Validation sequence

1. **Solver evidence**: read the primary output, confirm normal termination, optimization convergence, charge/multiplicity, method, and geometry digest.
2. **Stationarity**: use `chemical.stationary-check@1` or `chemical.gaussian-evidence@1` to confirm the final gradient/Hessian fields and the expected stationary-point record.
3. **Mode**: use `chemical.mode-check@1` and inspect the frequency vector. A classical first-order saddle has one relevant imaginary mode whose displacement follows the proposed forming/breaking bonds, atom transfer, or torsion.
4. **Structure and state**: compare atom mapping, composition, stereochemistry, key distances, spin/electronic-state declaration, and mode orientation with the reaction hypothesis.
5. **Connectivity**: prepare forward and reverse paths with `chemical.path-irc@1`, execute the declared IRC calculation, and check each endpoint with `chemical.irc-check@1` against the selected reactant/product artifacts.
6. **Decision**: record satisfied criteria, unresolved evidence, source artifacts, and a changed next operation. A candidate that has the right mode but reaches the wrong basin returns to candidate generation with revised endpoints or geometry.

## Registered checks

- `chemical.stationary-check@1`: numerical stationary-point and termination fields.
- `chemical.mode-check@1`: frequency count, magnitude, and mode/reaction-coordinate alignment.
- `chemical.gaussian-evidence@1`: normalize selected Gaussian output sections.
- `chemical.path-irc@1`: prepare bounded forward/reverse IRC inputs from a checkpoint.
- `chemical.irc-check@1`: inspect path completeness and endpoint comparison.
- `chemical.gaussian_saddle` and `chemical.gaussian_irc_connectivity`: specialized Gaussian evidence checks for their supported topology.

Use the independent checks as evidence records, not as a substitute for reading the primary output. Keep execution failure, unreadable evidence, and a completed check that fails a criterion as separate statuses. Preserve the source saddle, direction, path artifact, endpoint artifact, and digest for each IRC branch.

Read [transition-state validation](references/transition_state_validation.md), [IRC validation](references/irc_validation.md), [connectivity validation](references/connectivity_validation.md), and [structure validation](references/structure_validation.md). The shared candidate/validation handoff is in [reaction task interface](../candidate-generation/references/reaction_task_interface.md).

## Further references

- [gaussian validation](references/gaussian_validation.md)
- [general checks](references/general_checks.md)
- [irc preparation](references/irc_preparation.md)
