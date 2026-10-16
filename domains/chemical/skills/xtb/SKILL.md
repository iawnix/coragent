---
name: xtb
description: Adapt declared xTB inputs, native commands and parser evidence to the registered xTB bindings without choosing the scientific operation.
---

# xTB backend

This Skill owns xTB command binding, input staging, electronic-state/solvent
field translation and supported output parsing. It does not choose between
screening, optimization, scan, dynamics or path operations and does not certify
transition states or interpret a research result. Use the operation Skill and
`method-selection` for those decisions.

`chemical.xtb@1` is the registered wrapper for GFN2-xTB `sp`, `opt` and
`opt-sp` tasks. It translates charge and multiplicity to the native command,
records the requested solvent/state fields and returns raw-output provenance.
Prepare it through the Job interface:

```bash
"$CORAGENT_PYTHON" -m research_agent.application.executors --config "$CORAGENT_JOB_CONFIG" --environment local --executor chemical.xtb --version 1 --input geometry=input.xyz --output prepared/xtb.json -- --task opt-sp --charge 0 --multiplicity 1
```

Other native xTB commands are run through a generic Job with explicit control
files and collected outputs. Start those Jobs with `job_start`; their native options are not wrapper `--task`
values. The parser and receipt fields are defined in [xTB backend contract](references/xtb_backend_contract.md)
and the shared [runner contract](../method-selection/references/runner_results.md).

Material-based bounded scans and Cartesian gradient calculators are registered
under `candidate-generation` as `chemical.scan-xtb@1` and
`chemical.gradient-xtb@1`; the optional `path_xtb` binding also serves
`chemical.neb-xtb@2`. Those entries own operation-specific restraint, gradient
and NEB evidence. This backend Skill only supplies the xTB adapter and its
parser boundary. Use the [xTB execution reference](references/xtb_executor.md) for the canonical execution contract.
