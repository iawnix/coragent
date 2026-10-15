---
name: method-selection
description: Coordinate scientific method and backend selection with a named compute environment, including execution preparation when the method is already fixed.
---

# CoRAgent Method Selection

[Chinese version](SKILL.zh-CN.md)

Use this Skill when selecting a method or preparing execution for an already specified method. Read the relevant method Skill using its listed path. Installation configuration and method checks are Agent work; unavailable evidence is not automatically a request for user input.
This is a cross-task coordination layer. It does not implement a solver and does
not replace the scientific operation, backend adapter, or evidence validator.

Read the [implemented capabilities and boundaries](references/capabilities.md) when determining what is bundled, what requires a native command/script, and which checks are specialized. A Skill description or installed executable alone does not establish complete support.
Use the [scientific operation and backend map](references/operation_backend_map.md) to keep
operation ownership, backend ownership and evidence ownership separate.
Use the [complete operation/backend registry](references/operation_backend_registry.md)
when checking the registered executor and validator owner for an operation.

Start from the requested observable or the scientific question to resolve. Consider
system size, charge, spin, electronic state, metals or multireference risk,
solvent, constraints, target observable, expected uncertainty, candidate
quality, and cost. Use the method Skill to choose the input, command or script,
then select its software binding and a named local or remote environment in
`job.toml`. `job_probe` checks the platform; request preparation checks the selected
software and declared dependencies. For diagnosis or a native command, use the
[targeted environment check](references/runtime_environment.md).

Use inexpensive exploration only when it answers a declared question. State
when a higher-level calculation, alternate method, or robustness check is
needed. Preserve the selected method and rationale in the research Node and immutable
calculation intent.

For a requested optimization/single-point multi-method or multi-environment comparison, expand a complete
`method × environment × {opt, sp}` matrix before launching work, then probe
each environment and record independent failures for individual cells. The
method Skill guides execution through a predefined recipe, native command, or
task-specific script. A missing recipe does not imply missing software.
In this comparison, each `sp` depends on the `opt` output for the same method and
environment. Other studies may use explicitly chosen fixed geometries and TS/Freq/IRC/scan inputs; the Agent defines their dependencies. If one matrix
cell is unavailable, block that cell explicitly; do not silently substitute a
method or stop independent cells.

For a custom Python script that imports scientific libraries, use the
[script preparation example](references/request_preparation.md) to select its backend.
`job_start.platform` selects the execution target; it does not activate a scientific
Python environment. After an import failure, diagnose the selected binding before
retrying or declaring the method unavailable.

## References

- [method_selection.md](references/method_selection.md): scientific criteria.
- [backend_contract.md](references/backend_contract.md): scientific Job contract
  and execution boundary.
- [job_probes.md](references/job_probes.md): named local and
  remote environments, including remote Platform details.
- [runtime_environment.md](references/runtime_environment.md): installation-owned
  scientific runtime diagnosis.

- [Request preparation](references/request_preparation.md): installed executors, explicit inputs and recovery.
- [Runner results, units and electronic state](references/runner_results.md)
- [xTB operation recipes](references/xtb_operation_recipes.md): native task examples and operation-level evidence boundaries.
- [Operation/backend registry](references/operation_backend_registry.md): exhaustive registered runtime ownership.

When a search fails or repeats the same outcome, use [search diagnosis and recovery](references/search_recovery.md) to separate execution, numerical and hypothesis problems before changing settings or seeds.
