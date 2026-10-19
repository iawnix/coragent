---
name: energetics
description: Compute electronic, thermal, free-energy, reaction, barrier, ensemble, and bounded kinetic quantities from compatible calculation results.
---

# Energetics and kinetics

[Chinese version](SKILL.zh-CN.md)

Use this Skill after structures and electronic-structure results have been collected. It turns compatible energies and frequencies into thermochemistry, reaction and activation profiles, conformer populations, conditional TST rates, branching estimates, and explicit kinetic-network trajectories.

## Quantities and workflow

1. For each species, collect the electronic energy and, when needed, a frequency/thermochemistry result from the same geometry, atom order, method, charge, multiplicity, solvent, and standard state.
2. Use `chemical.thermochemistry@1` to combine electronic energy, zero-point energy, thermal enthalpy, entropy, and Gibbs free energy. Record temperature, pressure or concentration standard state, and low-frequency treatment.
3. Use `chemical.ensemble-free-energy@1` for a conformer or complex ensemble. It applies the declared population model to member energies and reports ensemble free energy and member weights.
4. Use `chemical.energy-profile@1` for discrete reactant/intermediate/TS/product states and `chemical.scan-slice@1` for a coordinate grid. Keep stoichiometry and reference state explicit.
5. Use `chemical.tst@1` for a candidate with a declared frequency treatment and temperature; `chemical.branching@1` for rates sharing a stated precursor; and `chemical.kinetic-network@1` for mass-action propagation with initial concentrations and rate constants.

## Interpretation

Electronic reaction energy is dE; adding ZPE gives d(E+ZPE); thermal enthalpy gives dH; and standard-state Gibbs values give dG. Activation quantities use the same reference convention: Ea = E_TS - E_R and dG‡ = dG_TS - dG_R. Convert Hartree, kcal/mol, and kJ/mol only through recorded unit fields. Gas 1 atm, solution 1 M, and other standard states must be stated explicitly.

For a conformer set, compare population-weighted free energies rather than the minimum member alone when several members are populated. For TST and branching, report assumptions and precursor scope with the rates. A profile or scan slice is a sampled set of states; use IRC and validation records for connectivity and `report` for presentation.

## Registered scripts and contracts

The adapters are implemented by `skills/energetics/scripts/energy.py` and `thermochemistry.py`; the CLI takes an operation (`thermochemistry`, `ensemble`, `profile`, `scan-slice`, `tst`, `branching`, or `network`) and `--input`/`--output-dir`. Results include traceable JSON and CSV with missing values retained. Read [energy execution](references/energy_execution.md), [scientific checks](references/energetics.md), and [kinetics execution](references/kinetics_execution.md) before comparing pathways.
