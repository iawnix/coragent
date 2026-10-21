---
name: crest
description: Explore conformers and rigid-fragment arrangements with CREST, then select traceable ensemble members for downstream reaction calculations.
---

# CREST conformer and complex sampling

[Chinese version](SKILL.zh-CN.md)

## Script routing

Select the executor in [Operation entrypoints](references/commands.md), then read the matching input and validation contract in this Skill. Ordinary invocation does not require source inspection; unlisted files under `scripts/` are internal helpers.

Use CREST when uncertainty in conformation, fragment orientation, or weak-complex packing is likely to change a reaction search. It is useful for flexible reactants, catalysts with several rotamers, pre-reactive complexes, and rigid fragments whose relative pose must be sampled before transition-state work.

## What to prepare

Start from a material with explicit coordinates, charge, multiplicity, fragments, and the solvent model used by the study. Choose GFN2 for the normal search and GFN1 when a cheaper broad screen is useful. Set an energy window large enough to retain chemically distinct conformers; the adapter default is 6 kcal/mol and the maximum retained member count is 256.

CREST can produce a conformer ensemble for one molecule, a rigid-fragment complex ensemble, a deterministic subset selected by energy/diversity/record ID, or perturbed and assembled complex samples for a reaction-center search.

## Recommended workflow

1. Prepare the parent material and keep its source digest as the ensemble parent.
2. Run `chemical.crest@1` with the chosen GFN method, search/optimization level, solvent, thread count, timeout, and energy window.
3. Import the run with `chemical.crest-ensemble@1` when the ensemble will be reused in a later Job.
4. Use `chemical.ensemble-select@1` to retain members by a declared selection rule. Keep several low-energy members when their reactive torsions or faces differ.
5. For separate reactants, use `chemical.complex-sample@1` in `assemble` or `perturb` mode, inspect contacts, and pass accepted poses to `reactive-geometry` or `candidate-generation`.
6. Optimize or evaluate selected members at the study method, then compare reaction candidates with the same method and state.

The run keeps member IDs, coordinates, source material, solvent, method, energies, selection decisions, and partial-run status. Use those IDs when a later calculation refers to a named conformer or complex pose.

## Registered operations and scripts

- `chemical.crest@1` -> `skills/chemical/crest/scripts/crest_run.py`; options include `--method gfn1|gfn2`, `--search-level normal|quick|squick|mquick`, `--opt-level normal|tight|vtight`, `--solvent`, `--energy-window`, `--max-members`, `--threads`, and `--timeout`.
- `chemical.crest-ensemble@1` -> `ensemble.py`; imports a material and a CREST run.
- `chemical.ensemble-select@1` -> `ensemble.py`; applies a declared selection to an ensemble.
- `chemical.complex-sample@1` -> `ensemble.py`; assembles or perturbs rigid fragments.

Prepare these through the standard executor and Job lifecycle. Read [the backend contract](references/crest_backend_contract.md) for input schema and [the ensemble contract](references/crest_ensemble.md) for selection and complex records.

## Choosing the handoff

Use the lowest few members for a low-energy population. Use a broader member set when the reaction center has several torsions, faces, or approach directions. Treat ensemble members as starting geometries; frequency, TS, IRC, and free-energy interpretation belong to the corresponding operation Skills.
