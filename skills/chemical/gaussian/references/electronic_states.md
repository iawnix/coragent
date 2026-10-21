# Gaussian state calculations and transition-character tracking

`chemical.electronic-gaussian@1` uses input role `input`, optional `path_gaussian`
binding and schema `chemical-electronic-input/1`. Required fields: `material`
(embedded chemical-material/1 with coordinates, 1–128 atoms), `task` (`sp` or
`opt`), and `settings`. Explicit isotope masses, implicit solvent, arbitrary route
extensions, external basis files and multireference methods are outside this adapter.

Settings include `theory` (`ground`, `td`, `tda`), `functional` (HF, B3LYP,
PBE1PBE, CAM-B3LYP, wB97XD or APFD), and one explicit `basis` token.
Optional resources: threads (default 1), memory_mb (2000), timeout_seconds (600,
maximum 86400), max_cycles (100, maximum 1000), spin_tolerance (0.1, maximum 0.5).
TD/TDA require integer `root` and `nstates`, 1 ≤ root ≤ nstates ≤ 32.

Ground calculations need a declared ground state within the requested valid
multiplicity; singlets use restricted SCF and other multiplicities unrestricted
SCF. TD/TDA currently support singlet excitations of a closed-shell singlet
reference only. The material must declare multiplicity=1 and
`electronic_state:{kind:"excited",method:"TDDFT",root:1}` for TDDFT;
use method=TDHF when functional=HF and theory=td, or method=TDA for theory=tda.
Root is local to the selected method and geometry. Do not route open-shell TD,
triplet-from-singlet TD or broken-symmetry requests through this narrow adapter.

Generated routes use TD/TDA(Singlets,NStates,Root), Force for sp, Cartesian Opt
for opt, NoSymm and tight SCF. Gas-phase treatment is explicit. The adapter checks
Gaussian 16 revision readback, route, charge/reference multiplicity, termination,
each SCF/selected-state block, complete requested root lists, input-orientation
geometry and original-axis force tables. Forces are negated and converted from
Eh/bohr to Cartesian dE/dR in Eh/Å. SP coordinates agree within printed precision
(2e-6 Å). Opt uses the shared Gaussian completion parser: four passing criteria
or explicit negligible-force completion with passing force criteria. The raw
four-row table and completion reason remain in the result. Use a new output
directory for each attempt.

Excited energy is parsed from `Total Energy, E(TD-HF/TD-DFT)` or
`Total Energy, E(CIS/TDA)` **bound to the requested selected-state marker**.
It must agree with reference SCF plus the selected excitation (1e-4 eV tolerance).
The reference SCF energy remains separate. The legacy Gaussian parser still
rejects unsupported target energies; this adapter does not bypass that guard.
Pre-annihilation unrestricted S² or selected-excited-state S² is checked against
the declared spin tolerance. Restricted singlet S² follows from its determinant.
No S² diagnostic proves stable or globally lowest SCF solutions.

Outputs include result.json, raw calculation files, evaluation.json and, on
success, material.json. Optimized material preserves atom lineage/state but does
not inherit an asserted unchanged graph. Timeouts kill the process group;
Gaussian scratch is local to the attempt and removed. Failures retain logs and
a failed result. No checkpoint-based branch continuation is silently applied.

Every geometry's printed configurations/root spectrum is retained, but
`state_continuity.status=not_assessed`: orbital labels and root numbers are not
inter-geometry state overlap. Consequently a converged fixed-root optimization
is not automatically a verified optimization of the initially intended state.
Inspect near degeneracy and supply the independent character analysis below;
ambiguous character requires revised calculations rather than a passed label.

`chemical.state-tracking@1` uses `structure`, input role `input`, and
`chemical-state-tracking-input/1`. Supply 2–32 `frames`, adjacent `links`, and
`initial_root`. Each frame has material (bound geometry/atom order), source_sha256,
basis_definition_sha256, ao_overlap (positive-definite intra-frame AO metric),
and 1–32 states with root, energy_hartree, multiplicity and transition_density
(square AO transition-density matrix, maximum 128 AOs). Each link has
from_source_sha256, to_source_sha256, source_sha256 and ao_cross_overlap.
The combined intra/cross metric must be positive semidefinite.

The character score is
`abs(tr(Da.T Sab Db Sab.T))/sqrt(tr(Da.T Saa Da Saa) tr(Db.T Sbb Db Sbb))`.
This is phase-insensitive and invariant to consistent AO basis transformations.
Default minimum_overlap=0.8, minimum_margin=0.1 and degeneracy_hartree=1e-4
are explicit screening thresholds, not universal physical constants. Low overlap,
competing matches or near-degenerate same-spin levels at either frame produce
inconclusive and stop assignment. A different matched root produces root_changed;
it is not silently accepted as fixed-root continuity. This tracks transition
character, not exact many-electron wavefunction fidelity or a diabatic Hamiltonian.

Gaussian's printed MO configurations do not provide these AO tensors or cross
metrics. Obtain them from an explicitly documented density/overlap export and
bind their source Artifacts; do not invent overlaps or substitute matching root
numbers. Automatic Gaussian checkpoint→AO transition-density extraction is not
bundled. This missing evidence is visible in every native calculation result.

Numerical tests use synthetic logs, transformed tensors and deterministic native
fixtures. Syntax was checked against [Gaussian TD documentation](https://gaussian.com/td/)
and local Gaussian 16 A.03 distributed output, including the separate TDA total
label. No real excited-state optimization accuracy benchmark has been performed.
