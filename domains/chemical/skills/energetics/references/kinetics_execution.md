# Elementary TST, branching and explicit kinetic networks

All three version-1 executors use the existing `structure` binding, input role
`input`, normal Job preparation/start/collection and JSON/CSV output. Read both
files; CSV alone omits evidence, assumptions and numerical diagnostics. Their
standalone energy.py operations are `tst`, `branching` and `network`.

`chemical.tst@1` consumes chemical-tst-input/1: `profile` is a Gibbs
[energy-profile input](energy_execution.md), with `reactant_state`,
`transition_state`, `active_reactants` (species→integer count),
`transmission_coefficient`, and nonempty `evidence` references (source_sha256,note).
Optional concentrations_mol_l specifies exactly the active reactants.
Reactants need minimum/ensemble thermochemistry; the activated side contains one
TS thermal source and unchanged explicit spectators. Molecularity m is 1–3.
An active coefficient must equal its reactant-state coefficient. Do not cancel a
catalyst that participates in the activated complex as though it were a spectator.

`k_m = κ k_B T/h (c°)^(1−m) exp(−ΔG‡/RT)`; units are s^-1, L mol^-1 s^-1
or L² mol^-2 s^-1. Pressure standards are converted to mol/L using p/(1000 RT).
Changing the common standard state changes ΔG‡ and its concentration prefactor
consistently; it does not change the physical rate. Actual initial flux is
`k_m Π c_i^ν_i`, in mol L^-1 s^-1. Zero concentrations give zero flux. Log-rate
values remain available when the floating-point rate underflows. κ is explicit
and restricted to (0,1]; no tunnelling enhancement, diffusion or automatic
recrossing model is inferred. Negative barriers and E-only profiles are refused.
Evidence citations are retained, but `elementary_step_certified:false`: audit
actual mode/IRC evidence before treating the conditional rate as physically valid.

`chemical.branching@1` consumes chemical-branching-input/1 with `channels`
(mapping 2–32 IDs to TST inputs) and exactly these true assumptions:
equilibrated_common_precursor, irreversible_products, no_product_interconversion.
The precursor stoichiometry, active species, source records, conditions and
models must match exactly. Supplied actual concentrations must also match and
be positive; zero-precursor initial branching is undefined. Reusing one activated
complex under different labels/notes is rejected. Stable
log-rate normalization yields initial_branch_fraction, not time-dependent yields.
Different precursors, reversible products, depletion, cycles and interconversion
require a network. Product free-energy ordering is distinct from kinetic ordering.

`chemical.kinetic-network@1` consumes chemical-kinetic-network-input/1:

- species: 1–64 IDs mapped to ground-state chemical-material/1 structures.
- reactions: 1–128 records with unique id, reactants, products, forward and
  optional reverse. Sides map species IDs to positive integer coefficients; total
  order ≤8. Catalysts appear explicitly on both sides and in the rate law.
- A rate is a TST input, or `{value,order,unit,source_sha256,note}`. For order m,
  unit must be the literal `(mol/L)^{1-m}/s`, e.g. `(mol/L)^0/s` for first order
  or `(mol/L)^-1/s` for second order. TST sources must also bind the network's
  species materials, active counts and temperature; ground-state ensemble inputs
  use the explicitly bound representative material.
- temperature_k is positive; initial_mol_l explicitly includes every species,
  including zero values. times_s contains 2–1001 increasing times starting at 0.
- Optional solver contains rtol (default 1e-7), atol_mol_l (1e-12), max_steps
  (100000, maximum 1000000). Loose tolerances above 1e-2/1e-3 are refused.

The model is closed, constant-volume, well-mixed mass action:
`dc/dt = S v`, `v_j = k_j Π c_i^νij`; reverses are separate channels.
Each reaction balances atoms, isotopes and charge. Every left-nullspace
stoichiometric invariant is monitored, including hidden moieties and catalysts.
Adaptive step-doubled RK4 uses a Richardson correction and an explicit local
error estimate. Negative stages/results are rejected and retried at a smaller
step, never clipped to zero. Observed states, last evaluated state, step counts,
rejections, local errors and invariant drift are retained.

This explicit solver is not a general stiff solver. Exhausted budgets, time-step
underflow or conservation failure produce a failed Job with partial results;
inspect status before plotting or reporting. Supplied forward/reverse rates are
not automatically guaranteed to satisfy thermodynamic detailed balance; this
is reported as not_assessed. No chemostats, transport, stochastic chemistry or
automatic reaction discovery is provided. Compare conditions and alternate
models with separate explicit Jobs, retaining their input digests and limits.
