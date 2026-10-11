# Current chemical capabilities and boundaries

[中文](capabilities.zh-CN.md). This inventory describes bundled implementation, not readiness of a local/remote installation or real-solver search success. Distinguish software features, implemented execution/parsing, and the selected environment. Platform probes, environment checks, synthetic tests and scientific validation provide different evidence.

## Independent operations

| Operation | Implemented entry | Scope and gaps |
| --- | --- | --- |
| Original structure materials | `chemical.material` | Preserves name/SMILES/XYZ, fragments, unknown settings and state declarations; explicit row permutation/inverse; no XYZ graph inference, state certification or reaction-map search |
| Names and candidate checking | `chemical.resolve`, `chemical.resolve-candidates` | PubChem/OPSIN and attributed Agent candidates; lookup failure permits inference, not automatic identity confirmation |
| Graphs and seed geometry | `chemical.inspect`, `chemical.seed` | SMILES, stereochemistry and explicit-H seeds; embedding is neither optimization nor adequate conformer sampling |
| Mapping checks | `chemical.reaction` | Checks supplied correspondence, balance and declared bond changes; does not discover mechanisms or prove atom trajectories |
| Mapping candidates | `chemical.map-candidates` | Bounded explicit-graph element/isotope correspondences; identity or minimum-edit reaction mode; ambiguity and truncation retained, not mechanism inference |
| Conformer comparison | `chemical.conformer-compare` | Supplied geometries, graph symmetry, proper rotation and optional internal coordinates; one alignment for complexes; finite mapping coverage, state declarations separate |
| Tensor order | `chemical.reorder-tensors` | Reversible Cartesian coordinate/gradient/Hessian/mode permutation with IDs and units; no spatial rotation, mass weighting or unit conversion |
| Structure identity | `chemical.compare` | Graph, charge, isotopes and specified stereochemistry; XYZ bond orders are inferred; not full conformer/state comparison |
| Stationary/mode/IRC checks | `chemical.stationary-check`, `chemical.mode-check`, `chemical.irc-check` | Independent normalized evidence checks for unconstrained ground-state single surfaces; retain small modes, truncation and ambiguous endpoint conformers; no wavefunction continuity or mechanism uniqueness proof |
| Gaussian evidence adapter | `chemical.gaussian-evidence` | Selected raw section to bound stationary/IRC evidence in current HF/DFT SCF scope; constraints require declaration, explicit isotope masses unassessed; no fabricated endpoint minima |
| xTB SP/optimization | `chemical.xtb` | Bundled GFN2-xTB sp/opt/opt-sp; Hessian/MD uses generic Jobs; bounded scan/gradient/NEB has separate entries below |
| Gaussian SP/optimization | `chemical.gaussian` | XYZ sp/opt/opt-sp; target energy interpretation has the HF/DFT SCF boundary below |
| Gaussian TS/frequency/QST/IRC/scan | `chemical.gaussian-input` | Explicit GJF execution and limited checks; termination/frequency count does not prove the target path; no complete scan validator |
| CF22D | `chemical.cf22d`, `chemical.cf22d-doctor` | PySCF sp/opt/opt-sp/ts/freq/thermo/opt_freq/ts_freq and diagnostics; includes RRHO, not IRC/NEB/crossings |
| Mapped endpoints and IRC inputs | `chemical.path-candidates`, `chemical.path-irc` | Explicit transformations, compatible single-fragment embedding or provided mapped geometries; optional DA geometry; preparation does not run Gaussian |
| CREST ensembles | `chemical.crest`, `chemical.crest-ensemble`, `chemical.ensemble-select` | Bounded 3.0.2 GFN1/GFN2 ground-state search, primary consistency, inferred identity and geometric/electronic-energy screening; partial results retained; no exhaustive coverage or free energies |
| Complex placements | `chemical.complex-sample` | Seeded rigid-fragment assembly/perturbation, collision/distance checks and lineage; supplied coordinates required, unknown total spin preserved; no optimization |
| Material QST2/QST3 | `chemical.qst-prepare` | Supplied mapped endpoint/guess geometries, explicit compatible states, permutation and GJF export; no minimum or elementary-step certification |
| Relaxed scan grids | `chemical.scan-xtb`, `chemical.scan-gaussian` | Bounded independent-point 1D/2D grids; native constraints, actual deviations, physical energies, failures and terminal-result continuation; no automatic path continuity |
| Gradients and NEB | `chemical.gradient-xtb`, `chemical.neb-xtb` | xTB 6.7.1 GFN1/GFN2 gradients, explicit unit/sign checks, NumPy improved-tangent/climbing NEB and finite force relaxation; partial paths retained; Gaussian ground-spin calculator is available through the separate electronic adapter; no ASE adapter |
| Energy analysis | `chemical.thermochemistry`, `chemical.ensemble-free-energy`, `chemical.energy-profile`, `chemical.scan-slice` | Ground-state source combinations, standard states, entropy-only frequency floor, finite conformer G, balanced energy differences and successful scan slices; separate bounded kinetic executors below |
| Pathway audit | `chemical.pathway-check` | Explicit hypotheses, atom/stoichiometric/shared-intermediate continuity, missing steps and optional recomputed classical mode/IRC evidence; no exhaustive generator |
| Conditional kinetics | `chemical.tst`, `chemical.branching`, `chemical.kinetic-network` | Classical TST, common-precursor initial branches, closed mass-action integration with conservation/error checks; no stiff-solver guarantee |
| Gaussian state calculations | `chemical.electronic-gaussian`, `chemical.state-tracking` | Ground-spin HF/DFT and singlet TDDFT/TDHF/TDA SP/opt; target energy/gradient/spin parsing; AO transition-character overlap requires supplied density/cross-metric tensors |
| Gaussian gradients/NEB | `chemical.gradient-gaussian`, `chemical.neb-gaussian` | Gas-phase ground-spin gradient calculator; same bounded NumPy NEB, no automatic wavefunction branch proof |
| Different-spin crossings | `chemical.mecp-gaussian`, `chemical.crossing-check` | Projected local search and independent gap/gradient/optional seam-Hessian checks; no global MECP, SOC, same-spin CI or nonadiabatic dynamics; not QBICS |
| Rendering and reports | `chemical.render`, report Skill | Structure rendering exists; reports cite actual materials, not execution flags as scientific conclusions |

All registered entries above currently use version `1`; consult their Skill, CLI and execution descriptor for arguments/dependencies. This is not an execution whitelist: justified, verified native commands or task scripts remain usable. Independent molecular SP/optimization needs no R/P, mapping or TS.

## Validator scope

| Registered validator / profile | Actual scope |
| --- | --- |
| `chemical.gaussian_frequency@1` | Normal termination and exactly one negative value in a finite frequency table; excludes mode identity, full stationary-point evidence and IRC identity |
| `chemical.reaction_mapping@1` | **DA-specific** mapping, topology and per-atom H correspondence; distinct from generic `chemical.reaction` input checks |
| `chemical.gaussian_saddle@1` | **DA-specific** input binding, stationary point, frequency table and two forming-bond displacements; not the default for other reactions |
| `chemical.gaussian_irc_connectivity@1` | **DA-specific** source saddle, bidirectional paths and mapped endpoints |
| `chemical.diels_alder_path@1` | Combines DA path checks; does not establish exhaustive mechanism/conformer coverage |
| `chemical.reaction_mapping@1` profile | DA mapping checks only, not generic TS acceptance |

Outside the specialized scope, `verdict=inconclusive`, `scientific_verdict=not_assessed` and `method_scope` explain what was not assessed. Invalid inputs, binding errors and in-scope scientific failures remain distinguishable. Analyze other reactions using their actual coordinates, modes and endpoints; neither a validator per reaction name nor a fabricated DA spec is required.

## Gaussian energy interpretation

`SCF Done` is retained as `reference_scf_energy_hartree`. It becomes `electronic_energy_hartree` only when an explicit output-route method matches the SCF label and no recognized excited-state, correlated, composite-energy or custom IOp evidence is present. `energy_evidence` records source, status and reason; this does not certify electronic-state identity or convergence.

The generic SCF parser does not certify TD/TDA, CIS, MP2/CCSD(T), double-hybrid, ONIOM or Counterpoise target energies. Missing methods, mismatched labels and unreadable final values do not fall back to earlier SCF values. Runners retain inputs, raw logs and parsed materials but fail the target-energy check. `--validation none` does not bypass energy typing.

When target energy is unassessed, logged thermal totals remain only in `reported_thermochemical_totals`, not target-method E+ZPE/H/G. IRC/scan points also distinguish reference SCF and target energy. Use method-specific parsing through generic Jobs for other quantities, preserving method/state evidence instead of substituting the requested method. Historical materials without energy typing require primary-output review; missing fields neither certify nor refute old scientific conclusions.
