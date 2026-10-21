# Independent energy analysis Jobs

## Contents

- [Execution and evidence](#execution-and-evidence)
- [Thermochemistry input](#thermochemistry-input)
- [Thermal adapters and composite rules](#thermal-adapters-and-composite-rules)
- [Low-frequency treatment](#low-frequency-treatment)
- [Conformer free energies](#conformer-free-energies)
- [Stoichiometric profiles](#stoichiometric-profiles)
- [Scan slices and reporting](#scan-slices-and-reporting)

## Execution and evidence

Four version-1 executors use the existing `structure` Python binding (NumPy/RDKit),
without a native solver, new service or reaction-specific rule:

| Executor | Input role | Input schema |
| --- | --- | --- |
| `chemical.thermochemistry` | `input` | `chemical-thermochemistry-input/1` |
| `chemical.ensemble-free-energy` | `input` | `chemical-free-energy-ensemble-input/1` |
| `chemical.energy-profile` | `input` | `chemical-energy-profile-input/1` |
| `chemical.scan-slice` | `input` | `chemical-scan-slice-input/1` |

Prepare/start/wait/collect through the ordinary Job manager. Each produces
`results/result.json` and `results/table.csv`; register these as analysis materials.
The standalone entry is `scripts/energy.py --output-dir NEW_DIR OP --input FILE`,
where OP is `thermochemistry`, `ensemble`, `profile` or `scan-slice`.
It refuses an existing output directory. An invalid input fails the Job without
publishing a successful result. No R/P pair, TS or IRC is required for independent
thermochemistry. Ground-state declarations only; excited/broken-symmetry states
need dedicated identity evidence and are currently rejected here.

Calculations are deterministic analyses of supplied evidence, not new RRHO
calculations or source authentication. Bind each source digest to its collected
Artifact and bind the supplied geometry, model and frequencies to that source.
Digests and equal labels do not establish actual convergence, wavefunction
identity or stationary-point validity. Use the independent validation Skill.
Resource/Job integration and analytic numerical tests do not establish accuracy
of a real Gaussian/CF22D calculation.

## Thermochemistry input

Top-level fields are `schema_version`, `electronic`, `conditions`, optional
`thermal`, `composite` (boolean, default false), and `low_frequency_cutoff_cm1`.
Unknown fields are rejected, including additional ZPE/solvation corrections.

`electronic` contains:

- `material`: embedded `chemical-material/1`, with explicit charge, multiplicity
  and ground electronic state; 1–512 atoms.
- `energy_hartree`: finite electronic E only, never E+ZPE, H or G.
- `model`: `{ "method": "HF", "basis": "STO-3G", "solvent": null }`.
  Basis can be null for methods without a basis. A solvent is
  `{ "name": "water", "model": "SMD" }`; both fields are required.
- `source_sha256`: `sha256:` followed by the 64 lowercase hexadecimal digest
  characters of the source Artifact bytes.

`conditions` is, for example:

```json
{"temperature_k":298.15,"phase":"gas","standard_state":{"kind":"pressure_pa","value":101325.0}}
```

Solution phase requires an electronic solvent model. A concentration standard
state is, for example, `{"kind":"concentration_mol_l","value":1.0}`. Gas requires null
solvent. Pressure/concentration standards are recorded independently of phase;
choosing 1 M alone does not imply solution or add solvation. These are standard
states, not actual reactant concentrations. Units are fixed, explicit and not guessed.

Without `thermal`, only E is populated. Other quantities remain null; missing
corrections are never replaced by zero. An explicit zero correction is valid.

## Thermal adapters and composite rules

`thermal` contains `material`, `model`, `source_sha256`, `temperature_k`,
`standard_state`, `format`, `data`, and `rrho`. The source and requested
temperatures must agree: one-temperature totals cannot establish another
temperature. Rerun the original RRHO calculator at a new temperature first.

`rrho` declares `stationary_type` (`minimum` or `transition_state`),
`geometry_class` (`atom`, `linear`, `nonlinear`), positive integer
`symmetry_number`, positive `frequency_scale`, and the full **unscaled** vibrational
`frequencies_cm1`. Data must be unmodified RRHO at the declared scale and symmetry
number. Translation/rotation must already be projected out. Geometry class and
3N−5/3N−6 mode count are checked (atoms: zero); zero frequencies are rejected.
Minima require zero negative modes; first-order TSs require exactly one negative
mode. The check is bookkeeping, not Hessian/stationarity certification.

Accepted data formats:

| format | data |
| --- | --- |
| `corrections` | Only `E_hartree`, `ZPE_hartree`, `H_correction_hartree`, `G_correction_hartree`; missing/null corrections retained |
| `gaussian` | The existing `parse_thermochemistry` dictionary; requires supported target-energy evidence, matching logged temperature and pressure |
| `cf22d` | Existing `pyscf-thermo/1`; requires matching `temperature_K` and `pressure_Pa` |

For normalized `corrections`, preserve dedicated target-energy parsing evidence
with the source Artifact. Do not relabel an unsupported Gaussian reference SCF
energy as the requested correlated energy. The Gaussian adapter refuses
unsupported targets and never uses `reported_thermochemical_totals`. CF22D's legacy
`entropy` field has no explicit units and is deliberately not consumed. Both
adapters check available totals against E plus their corrections (2e-6 Eh tolerance
for printed precision). Missing corrections are not reconstructed from totals.

H/G corrections are **relative to electronic E and already include ZPE**:
`E+ZPE = E + ZPE`, `H = E + Hcorr`, `G = E + Gcorr`.
Never add ZPE again to H or G. No separate solvation delta is accepted: electronic
solvation is already represented by the electronic source/model. This release
does not implement a gas-electronic + separate-solvation thermodynamic cycle.

Different source digests or models require explicit `composite:true`. Electronic
and thermal geometries need compatible state declarations and graph-preserving
proper alignment with all-atom RMSD ≤0.01 Å (mapping limited to 256 atoms,
20,000 search assignments and 64 retained candidates). With missing graphs (e.g. TS), both
ordered geometries, atom IDs, elements and isotopes must match exactly within
1e-8 Å. Reordered graphless sources must be explicitly reconciled first. Composite
results preserve both models; a low-level gas RRHO correction can be combined
with a declared solvent high-level electronic source. No source substitution is
performed automatically.

Only G receives a standard-state conversion. With R in J mol−1 K−1,
`c_gas = p/(1000 RT)` in mol/L and `delta_G = RT ln(c_target/c_source)`.
At 298.15 K, 1 atm → 1 M gives +1.89432845 kcal/mol per species. The stoichiometric
sum therefore includes the Δn correction for association/dissociation. E, ZPE and
H are unchanged. This is a standard-state conversion, not a solvation free energy.

## Low-frequency treatment

An optional positive `low_frequency_cutoff_cm1` enables **entropy-only harmonic
frequency flooring**, not Grimme free-rotor interpolation or full quasi-RRHO.
For each stable scaled frequency ν below νcut, replace its oscillator entropy
by the entropy at νcut:

`S(ν) = R [x/(exp(x)−1) − ln(1−exp(−x))]`, `x = hcν/(k_B T)`;
`delta_G = T Σ[S(ν)−S(max(ν,νcut))]`.

Add this delta once to the existing RRHO G. ZPE and H retain the source RRHO
values. The TS's negative mode is excluded and listed separately. Modes above
the cutoff are unchanged. Frequency scale, cutoff, temperature and deltas are
recorded. Missing G prevents this operation. Do not submit a previously corrected
G as raw RRHO. The method is an explicit approximation; sensitivity to cutoff and
large-amplitude/hindered rotations remains a separate investigation.

## Conformer free energies

Input has `members` (1–64), nonempty `coverage`, and
`degeneracy_convention:"additional_unrepresented_basins"`. Each member contains
`id`, `thermochemistry` (the input contract above), positive integer `degeneracy`,
and nonempty `degeneracy_evidence`.

Here degeneracy g is the total number of equivalent basins represented by that
member, including itself (g=1 by default scientifically, but the field is required).
Additional basins must not be separately listed, rotational symmetry or spin
multiplicity already counted by RRHO. The convention label refers to the origin
of g>1. Repeated IDs or geometry matches at 0.05 Å are rejected. Incomplete mapping
cannot certify distinctness. Members need the same graph/isotopes/declared state,
minimum RRHO, electronic/thermal methods, frequency treatment, conditions and G.
Do not use this operation for competing products or different spin states.

`Gensemble = Gmin − RT ln Σ[g_i exp(−(G_i−Gmin)/RT)]`.
The implementation uses shifted logarithms; it exports normalized populations,
G and coverage. It does not invent ensemble H/E values. The result assumes
interconverting, equilibrated, distinct supplied basins. Finite search coverage
and declared degeneracies cannot establish a globally complete partition sum.

## Stoichiometric profiles

Input contains a `species` object mapping IDs to thermochemistry inputs or
free-energy-ensemble inputs. Reuse a collected result's `request` field, with its
Artifact linkage; the profile recalculates from those inputs rather than trusting
editable derived G values. A `states` list contains
`{"id":"R","stoichiometry":{"A":2,"catalyst":1}}` objects. All coefficients
are explicit positive integers (≤1000); state IDs are unique. Limits are 128
species and 256 states. Include every spectator/catalyst in each relevant state.

Set `reference` to one state ID, `quantity` to E/E+ZPE/H/G, and `unit` to
`hartree`, `kJ/mol` or `kcal/mol`. Optional `comparisons` entries have `from`, `to`,
and `kind` (`reaction` or `activation`). Each difference is final minus initial;
reverse barriers require an explicit reverse comparison. For an activation
comparison, the caller must supply the TS state's evidence; the energy operation
labels it `validated_elementary_step:false` and does not certify it as a TS.

All states must balance elements, isotopes and total charge. Unused species and
missing quantities are rejected. Methods/conditions must match; thermal
comparisons additionally require matching thermal models/frequency treatment.
Atomic symmetry numbers, geometry classes and minimum/TS labels can differ.
Multiplicity declarations are exported per species; total spin coupling and
surface continuity remain **not assessed**, especially for separated fragments.
A low local barrier alone is not a network rate or selectivity prediction.

## Scan slices and reporting

Input contains `scan` (a collected terminal `chemical-scan-result/1`) and `unit`.
Exports 1D/2D successful rows with targets, actual coordinates, physical E and
energy relative to the lowest successful sample. Retains excluded failed/pending
indices even when those records contain numbers. Checks row digests, shape,
stored tolerances and source-evidence presence; this does not independently rerun
the constraint measurement or solver. All-failed scans yield an empty table and
null reference, never a fabricated energy. Running/unknown states are refused.

Read result JSON together with CSV: CSV alone lacks the complete scientific
conditions, source bindings and limitations. Report axes must name the quantity,
units, reference and conditions. Plot discrete profiles as discrete state data;
label scans as sampled potential slices, keep failed regions as gaps, and do not
call either a complete PES or a free-energy surface. No TST, branching or kinetic
network solver is provided by these four operations.
