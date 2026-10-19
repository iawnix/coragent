---
name: mechanism-reasoning
description: Coordinate reaction-path and transition-state investigations from input and mechanism hypotheses through candidate searches, validation, recovery, and evidence-based conclusions.
---

# CoRAgent Mechanism Reasoning

[Chinese version](SKILL.zh-CN.md)

Use this Skill for a reaction-mechanism or transition-state investigation, including
resuming an unfinished search. It owns the scientific plan across operation Skills:
identify the next unresolved question, choose a discriminating calculation, inspect
its evidence, and carry the result into the next decision. It also supports standalone
mechanism reasoning; a conceptual question does not require running calculations.

For a calculation task, read the [reaction investigation loop](references/reaction_investigation.md).
Keep responsibility for the next action when handing work to chemical-input,
reactive-geometry, candidate-generation, validation, energetics or report. These
are instructions used by the same Agent, not separate agents or automatic workflows.
The generic runtime stores tasks, Jobs and evidence; it does not choose chemical
prerequisites or decide when a mechanism is established.

Define species, composition, charge, spin or electronic state, atom mapping,
bond changes, environment, and reversibility explicitly. Put the current mechanism hypothesis in the Node proposal and predictions/falsifying observations in its plan. Explain support or conflict in Result conclusions with evidence. Independently compared approaches can use alternative_to. Research dependencies do not define chemical connectivity.

Record the observations, scientific criteria, unresolved questions and next steps with research_update using the existing node_id and a note. Publish a reusable conclusion with research_result, citing collected materials and stating limitations. A completed computation does not establish a scientific conclusion.

Separate species identity, elementary-step connectivity, saddle evidence,
energetics, kinetics, and robustness into questions that can fail independently.
Preserve competing mechanisms and unexpected results. When evidence challenges
the framing, revise the current proposal or create a related Node for an independent new question, preserving earlier results.

## References

- [reaction_mapping.md](../chemical-input/references/reaction_mapping.md) and
  [molecular_preparation.md](references/molecular_preparation.md): species,
  mapping, and input preparation.
- [pathway_model.md](references/pathway_model.md): pathway hypotheses and chemical
  connectivity.
- [mechanism_reflection.md](references/mechanism_reflection.md): distinguishable
  hypotheses and falsifiers.
- [strategy_reflection.md](references/strategy_reflection.md): reframing after
  repeated or unexpected results.

For conditional exploration decisions and explicit multistep materials, read
[pathway audit contracts](references/pathway_execution.md). `chemical.pathway-check@1`
uses the structure binding and input role input to retain hypotheses, guesses,
observations, atom/stoichiometric continuity and missing steps. Optional bound
classical mode/IRC checks are recomputed; missing evidence never becomes a pass.
For competing products, use the energetics Skill to separate thermodynamic
ordering, conditional TST branching and explicit reversible network predictions.
