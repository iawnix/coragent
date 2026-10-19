# Material-based QST, scans and NEB

[中文](path_search.zh-CN.md)

NEB uses [ASE](ase_neb_executor.md), with version-2 inputs and executors.

## Contents

- [Independent execution and environments](#independent-execution-and-environments)
- [QST2 and QST3](#qst2-and-qst3)
- [One- and two-dimensional relaxed grids](#one--and-two-dimensional-relaxed-grids)
- [Gradient calculator and NEB](#gradient-calculator-and-neb)
- [Evidence and limits](#evidence-and-limits)

## Independent execution and environments

The recipes below each take one `input` JSON Artifact; QST/scans/gradients use version 1 and NEB uses version 2. They do not
require a reaction name or a complete research workflow. Prepare via
`research_agent.application.executors`, submit returned request_file/request_sha256
with node_id to job_start and collect the terminal Job. Example (replace absolute
paths and Artifact refs with the real returned values):

```text
"$CORAGENT_PYTHON" -m research_agent.application.executors --config "$CORAGENT_JOB_CONFIG" --environment local --executor chemical.scan-xtb --version 1 --input input=<work_dir>/scan.json --input-artifact <scan-ref> --output <work_dir>/scan-request.json -- --max-points 16
```

| Recipe | Backend binding | Result |
| --- | --- | --- |
| `chemical.qst-prepare` | `structure` | QST2/QST3 ts.gjf and mapping/setting manifest |
| `chemical.scan-xtb` | `path_xtb` | Per-point restrained optimization, unrestrained energy, actual coordinate and failures |
| `chemical.scan-gaussian` | `path_gaussian` | Per-point ModRedundant optimization, typed energy and convergence evidence |
| `chemical.gradient-xtb` | `path_xtb` | Bound Cartesian electronic energy and gradient |
| `chemical.neb-xtb` | `path_xtb` | Full path, per-image energy/gradient evidence, NEB-force history and candidate |

Native path operations need **RDKit/NumPy plus the configured solver**, unlike the
standard-library-only Gaussian/xTB wrappers. Configure path_xtb/path_gaussian with
the appropriate native command/activation script. `--job-profile local:path`
binds only those explicitly configured backends to path.lock (RDKit/NumPy, ASE and SciPy);
it does not install solvers or run default native scientific acceptance jobs.
Check the selected recipe using environment_check with --executor and --version,
then run a bounded scientific case. The existing wrapper profile stays unchanged.
ASE is required by NEB. No new native binding is inferred from PATH.

All embedded materials use chemical-material/1, supplied angstrom coordinates,
2–256 atoms, known charge/multiplicity and an explicit ground-state declaration.
Explicit isotope masses and excited/crossing surfaces need other verified inputs.
All operations preserve source materials; geometries are never implicitly optimized
before preparation, aligned as independent fragments or inferred from names.

## QST2 and QST3

`chemical-qst-input/1` contains `reactant`, `product`, `mapping` and `settings`.
Materials are embedded objects; mapping is a complete bijection of local IDs,
e.g. `[["atom_1","product_atom_4"], ...]`. Map explicit H as well. Product rows are
reordered to reactant order with element/state checks and a recorded permutation.
For QST3 also supply `guess` and a separate complete `guess_mapping` from reactant
IDs to guess IDs. An intermediate TS guess need not have a certified minimum graph.

Gaussian settings require method, basis, threads, memory_mb, timeout_seconds,
solvent and solvent_model (`gas` with null solvent, or `SMD` with a solvent name).
Optional max_cycles defaults to 200 (1–2000). No extra route/basis text is injected;
Gen/GenECP/ChkBasis need explicit inputs through the existing generic path.
Example settings: `{"method":"HF","basis":"STO-3G","threads":1,"memory_mb":512,"timeout_seconds":600,"solvent_model":"gas","solvent":null}`.

The preparer emits Opt=(QST2 or QST3,CalcFC,MaxCycles=...) Freq, SCF=Tight,
Int=UltraFine and NoSymm. Execute ts.gjf separately with chemical.gaussian-input,
passing the same method/basis/state/resources. Preparation proves neither endpoint
minima nor an elementary step; endpoints spanning several steps may need a network.

## One- and two-dimensional relaxed grids

`chemical-scan-input/1` contains `material`, `settings`, and one or two `axes`:

```json
{"kind":"distance","atoms":["atom_1","atom_2"],"values":[1.5,1.8,2.1],"unit":"angstrom","tolerance":0.03}
```

An angle uses 3 IDs, degree and values strictly between 0 and 180. A dihedral uses
4 IDs and values between -180 and 180; tolerance comparisons wrap periodically.
Axes require distinct existing IDs, explicit finite values and positive tolerances;
the Cartesian product has at most 256 points. Second axis varies fastest. Each
point starts from the **original geometry** independently, not a previous optimized
point; this avoids hidden dependence on a failed neighbor but does not trace a
unique conformational branch. Target constraints may lead to different basins.

xTB settings require method (`gfn1`/`gfn2`), threads, timeout_seconds, solvent_model
(`gas`/`ALPB`) and solvent (null/name). Optional opt_level is normal/tight/verytight,
default tight; force_constant defaults to 1 in native xcontrol convention.
The profile fixes native accuracy=1 and electronic temperature=300 K.
Gaussian uses the settings above and native ModRedundant frozen coordinates.

xTB applies added restraint potentials, not exact frozen internal coordinates.
After native optimization, a fresh **unrestrained** energy/gradient evaluation at
the same geometry provides the physical electronic energy. The restrained energy
stays labeled in raw optimization evidence. Actual values and tolerance deviations
are checked independently. A normal exit, a printed convergence flag or a matching
energy count alone cannot mark a scan point successful.

`--max-points` bounds new attempts (1–256). All pending/succeeded/failed rows stay
in result.json with targets, actuals, geometries, energies, evidence and hashes.
A budget stop is partial and exits nonzero; collect its materials. Continue in a
new Job by embedding its terminal collected result as `previous` in the unchanged
spec. Plan/point digests must match; successful points are reused, pending points
execute, failures remain unless `retry_failed: true` is explicit. Reused primary
hash paths refer to that previous result's collected artifacts. A running/unknown
receipt is not replayable: reconcile Job status and collected evidence first.
Hard kills may leave only a running receipt; do not manufacture terminal success.

`candidate.xyz` and candidate.material.json identify the highest successful sampled
point. This is not necessarily an interior peak, converged saddle or reaction barrier.

## Gradient calculator and NEB

`chemical-gradient-input/1` contains `material` and xTB `settings`. The adapter
pins xTB 6.7.1 GFN1/GFN2 CLI semantics and reads the complete single-cycle Turbomole
`gradient` file. Coordinates are bohr there; energies are hartree and gradients
hartree/bohr. Verify element order, coordinates, energy against the log, version,
SCC and termination before constructing chemical-calculation/1. Output states are
checked when printed; explicit input declarations do not prove wavefunction identity.

The calculator contract binds atom_ids, coordinates + digest, model, convergence
and primary sources. It requires electronic energy and Cartesian **dE/dR**;
energy-only outputs cannot drive NEB. The engine explicitly converts gradients to
negative forces in hartree/angstrom using 1 bohr = 0.529177210903 Å. Core algorithms
accept independent calculators; xTB and Gaussian have separate native adapters.
See the Gaussian settings/scope at the end of this reference.

`chemical.neb-xtb@2` and `chemical.neb-gaussian@2` use ASE NEB with
chemical-neb-input/2. See the [ASE contract](ase_neb_executor.md) for FIRE/BFGS,
linear/IDPP interpolation, explicit eV/Å force units, evaluation budgets and
partial-output handling. Endpoints remain fixed and candidates require separate
TS validation. The former NumPy NEB implementation and version-1 entries have
been removed; rebuild old requests with the new contract rather than renaming
the schema or reusing legacy numerical parameters.

## Evidence and limits

Path candidates retain local IDs and source graph/fragments/map tags in derivation;
their own graph/fragment identity is unassigned because bonds may change along a
path. Assess candidate connectivity separately before identity-sensitive reuse.

Raw inputs/logs, evaluation evidence, full paths/grids and result.json are collected
recursively. Native child process groups are cleaned up on completion/timeout.
NEB step limits or calculator failures retain partial evaluations and the last
fully evaluated path. Its candidate always comes from a fully evaluated internal
image, never the next unevaluated iterate. NEB does not automatically resume a
running job; a reviewed previous path can be supplied as new initial images.

Neither native search accuracy nor real solver interoperability is established by
deterministic fixture tests alone. Inspect identity, endpoint preparation, mode and
IRC evidence through the separate validation modules before calling a candidate a
TS. Multiple peaks/basins, competing paths, free energies and state continuity need
the corresponding additional work. Avoid interpreting the legacy Gaussian raw SCF
scan fallback as a completed relaxed grid; these recipes retain per-point evidence.

## Gaussian ground-spin gradients and NEB

`chemical.gradient-gaussian@1` and `chemical.neb-gaussian@2` use
chemical-gradient-input/1 and chemical-neb-input/2 respectively. Their settings are the [electronic adapter settings](../../gaussian/references/electronic_states.md),
with theory=ground and a supported gas-phase functional/basis. Use path_gaussian.
Original-axis forces are negated and converted to dE/dR in Eh/Å. Printed coordinate
precision (2e-6 Å) is recorded in calculator evidence. Independent finite-difference
and deterministic native Job tests cover units/sign/staging; no physical Gaussian
NEB benchmark is implied. ASE NEB retains unvalidated candidate semantics; declared spins/S² do not prove wavefunction branch continuity.
