---
name: reaction-investigation
description: Run a closed-loop reaction investigation from species and mechanism hypotheses through candidate search, validation, energetics, recovery, and evidence-based conclusions.
---

# Reaction investigation

[Chinese version](SKILL.zh-CN.md)

## Script routing

Select the executor in [Operation entrypoints](references/commands.md), then read the matching input and validation contract in this Skill. Ordinary invocation does not require source inspection; unlisted files under `scripts/` are internal helpers.

Use this Skill for a reaction mechanism or transition-state study. It coordinates the domain Skills while keeping the chemistry decision in one loop: define the hypothesis, prepare materials, construct candidates, run calculations, validate evidence, compare energetics, and choose the next discriminating experiment.

## Workflow contract

The workflow contract is [references/reaction_investigation.md](references/reaction_investigation.md). It belongs inside this Skill because it describes the state machine and handoffs for a reaction study; the generic CoRAgent runtime only stores Nodes, Jobs, Artifacts, and evidence.

Within the owning question's existing plan, notes and Results, retain each relevant elementary step's species identity, atom mapping, charge, multiplicity/electronic state, environment, proposed bond changes, candidate geometries, validation status, energetic status, and next unresolved investigation. Elementary steps, candidates and validation stages do not automatically require separate Nodes. Inspect calculation outputs and retain useful observations or decisions as notes, or reusable conclusions as Results; the same finding need not be written twice.

## Closed loop

1. **Define**: state reactants/products, plausible intermediates, bond changes, stereochemical outcome, and competing mechanisms. Write predictions and observations that would distinguish them.
2. **Prepare**: use `material-preparation` to resolve names/SMILES and establish atom identities and reaction mapping on graphs before generating seeds or optimizing species. Preserve supplied coordinates and carry the mapping through subsequent calculations.
3. **Assess**: use `structure-assessment` and `geometry-preflight` to inspect graph, fragments, state, contacts, and reaction-center geometry.
4. **Construct**: use `reactive-geometry` for approach poses and `candidate-generation` for QST, scans, direct TS, or NEB. Keep multiple hypotheses when site/face/conformer evidence is unresolved.
5. **Run and validate**: choose a backend with `method-selection`, execute Gaussian/xTB/CF22D, then use `validation` for mode and IRC evidence.
6. **Compare**: use `energetics` for compatible E/ZPE/H/G values, barriers, ensemble populations, TST, branching, or kinetic networks.
7. **Recover or conclude**: on failure, change the construction/search action using the observed failure mode. On success, publish a result citing all source Artifacts, competing explanations, uncertainty, and the next experiment.
8. **Deliver**: use `chemical-report` to build tables, figures, trajectories, and a readable evidence package.

Use `chemical.pathway-check@1` for an independent audit of an explicit multistep pathway. The pathway script is `skills/chemical/reaction-investigation/scripts/pathway_job.py`; the scientific loop itself remains the coordinating Skill.

## Decision habits

Distinguish species identity, elementary-step connectivity, saddle evidence, energetics, kinetics, and robustness within the evidence for the current question. This distinction does not prescribe separate Nodes or Results for each check. Preserve failed searches when they reveal a wrong pose, endpoint, electronic state, or reaction hypothesis. Convergent evidence across these records supports the mechanism conclusion.

Read [pathway model](references/pathway_model.md), [molecular preparation](references/molecular_preparation.md), [pathway execution](references/pathway_execution.md), and [mechanism reflection](references/mechanism_reflection.md) when the study contains several steps or competing explanations.

## Further references

- [strategy reflection](references/strategy_reflection.md)
