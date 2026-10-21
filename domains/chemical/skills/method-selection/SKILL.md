---
name: method-selection
description: Choose exploration and refinement methods before costly searches, or revise the method after repeated search failures.
---

# Method and backend selection

[Chinese version](SKILL.zh-CN.md)

## Script routing

Use the registered executor ID and the [script routing map](../../../../docs/skill-script-routing.md#method-selection) to choose the entrypoint, CLI, inputs, and primary outputs. The map is authoritative for routing; implementation helpers under `scripts/` are not standalone commands. Do not inspect source code to discover invocation details; read the linked operation contract and use executor `--help` only for unspecified options.

**Entrypoint:** none bundled; use the documented runtime or generic Job route.

Use this Skill when a study must choose a method, compare methods, or prepare a fixed method in a named compute environment. Start with the quantity the study needs, then make the method choice explicit in the research Node and Job intent.

## Selection workflow

1. State the target observable: geometry, relative energy, barrier, frequency, IRC, spin crossing, or kinetics.
2. Record system size, charge, multiplicity, solvent, constraints, flexibility, metal/multireference indicators, and the uncertainty and cost budget.
3. Choose an exploration level and a refinement level. Typical paths are CREST/xTB for conformers and poses, xTB/CF22D for screening and gradients, and Gaussian or another declared high-level method for final TS/frequency evidence.
4. Map the operation to a backend using [the operation/backend map](references/operation_backend_map.md) and [registry](references/operation_backend_registry.md). Keep operation ownership, backend ownership, and evidence ownership separate.
5. Probe the named environment with `job_probe`; prepare the executor request with the method Skill; start, submit, and collect the Job.
6. For a method matrix, expand every requested method x environment x operation cell before launching. Record each unavailable cell independently and keep successful cells comparable.
7. When a search fails, classify the failure as environment, input, numerical, or hypothesis; use [search recovery](references/search_recovery.md) to change the next action.

Before launching a costly TS, IRC, or multi-point Gaussian search, record the
exploration method and the decision that promotes a candidate to refinement.
For flexible molecules or separate fragments, prefer an applicable registered xTB/CREST
operation when available; if it is deliberately skipped, record the reason and
the bounded alternative. A final DFT requirement does not force exploratory
geometry generation to use DFT.

## Practical choices

Use xTB or CREST to explore conformers, fragment poses, scans, and broad path candidates. Use CF22D when a consistent PySCF method is needed for screening, optimization, frequencies, or a bounded TS search. Use Gaussian for explicit route sections, QST/TS/frequency/IRC inputs, and parser evidence from native logs. Use a task-specific generic Job for software that has no registered adapter, with declared inputs and outputs.

A method choice is part of the scientific result: record basis, dispersion, solvent, state, temperature, constraints, executable version, and environment. Match endpoint and TS settings before comparing energies or frequencies. Use the operation Skill (`candidate-generation`, `validation`, or `energetics`) to decide what evidence the chosen method must produce.

Read [scientific criteria](references/method_selection.md), [backend contract](references/backend_contract.md), [runtime diagnosis](references/runtime_environment.md), and [request preparation](references/request_preparation.md).

## Further references

- [capabilities](references/capabilities.md)
- [job probes](references/job_probes.md)
- [runner results](references/runner_results.md)
- [xtb operation recipes](references/xtb_operation_recipes.md)
