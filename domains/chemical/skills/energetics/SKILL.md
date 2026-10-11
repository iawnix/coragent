---
name: energetics
description: Evaluate electronic energies, ZPE and thermal corrections, free and reaction energies, barriers, bounded TST rates, and energy profiles.
---

# CoRAgent Energetics

[Chinese version](SKILL.zh-CN.md)

Use this Skill for `E`, `E+ZPE`, `H`, `G`, reaction and activation energies,
standard-state corrections, bounded transition-state-theory rates, and energy
profiles. Keep quantity, units, temperature, pressure or concentration,
standard state, phase, solvent, method, electronic state, stoichiometry, and
frequency treatment explicit.

Do not combine electronic and thermal results unless structures, atom order,
methods, and declared composite treatment are compatible. Do not use an
electronic barrier as a Gibbs barrier, infer unsupported isotope corrections,
or treat a qualitative pathway enumeration as kinetics. Record values and
limitations as separate research notes with source Artifacts.

Use `chemical.thermochemistry@1`, `chemical.ensemble-free-energy@1`,
`chemical.energy-profile@1` and `chemical.scan-slice@1` through ordinary Jobs,
with input role `input` and the `structure` environment binding. Read
[execution contracts and numerical scope](references/energy_execution.md) before
preparing inputs. They produce traceable JSON and CSV, preserve missing values,
and reject inconsistent sources, conditions and stoichiometry. Only declared
ground states are currently supported by these analysis executors.

Read [scientific checks](references/energetics.md) for interpreting results.
Use `chemical.tst@1`, `chemical.branching@1` and `chemical.kinetic-network@1` for
[conditional rates, branching and explicit mass-action networks](references/kinetics_execution.md).
Read their assumptions before comparing pathways. Discrete
profiles and scan slices do not establish a complete PES, TS connectivity or
free-energy sampling. No real-solver accuracy benchmark is implied by the
local deterministic contract and Job tests.
