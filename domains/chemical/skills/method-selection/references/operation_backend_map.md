# Scientific operation and backend map

This map separates the scientific operation from the method/backend that runs
it. The `skill` field in `execution.json` identifies the primary owner of an
executor; `backend` identifies the implementation binding. A backend entry does
not by itself establish the scientific conclusion listed in the last column.

| Scientific operation | Primary Skill | Backend or adapter | Executor entries | Independent evidence or validator |
| --- | --- | --- | --- | --- |
| Material import, structure inspection and reaction mapping | `chemical-input` | structure | `chemical.material`, `chemical.resolve`, `chemical.inspect`, `chemical.reaction`, `chemical.map-candidates` | structure identity, mapping and explicit bond-change checks |
| Conformer/complex preparation | `chemical-input` plus `crest` | structure, CREST | `chemical.seed`, `chemical.crest`, `chemical.crest-ensemble`, `chemical.complex-sample` | ensemble identity, source geometry and selection evidence |
| Reactive pose construction | `reactive-geometry` | structure | `chemical.reactive-sites`, `chemical.reactive-pose`, `chemical.reactive-geometry` | geometry safety and explicit reaction-center observations |
| TS/path candidate generation | `candidate-generation` | Gaussian, xTB, ASE | `chemical.qst-prepare`, `chemical.scan-*`, `chemical.path-candidates`, `chemical.gradient-*`, `chemical.neb-*` | candidate provenance; no saddle conclusion |
| TS saddle evidence | `validation` | Gaussian evidence parser or normalized evidence | `chemical.gaussian-evidence`, `chemical.stationary-check`, `chemical.mode-check` | stationary point, mode direction, state and geometry checks |
| TS IRC connectivity validation and basin assignment | `validation` | Gaussian or generic Job | `chemical.path-irc`, `chemical.irc-check` | bidirectional path completeness and endpoint basin identity |
| Scoped legacy Diels–Alder evidence | `validation` | structure/Gaussian evidence | `chemical.reaction_mapping`, `chemical.gaussian_saddle`, `chemical.gaussian_irc_connectivity`; profiles `chemical.diels_alder_path`, `chemical.reaction_mapping` | DA-only topology, saddle and endpoint checks; unassessed outside declared DA scope |
| Energies and thermochemistry | `energetics` | structure plus declared method outputs | `chemical.thermochemistry`, `chemical.energy-profile`, `chemical.ensemble-free-energy`, `chemical.scan-slice` | units, state, stoichiometry and condition compatibility |
| Different-spin surface crossing | `surface-crossing` | Gaussian | `chemical.mecp-gaussian`, `chemical.crossing-check` | gap, projected gradient, state identity and optional curvature |
| Gaussian calculation backend | `gaussian` | Gaussian binding | `chemical.gaussian`, `chemical.gaussian-input`, `chemical.electronic-gaussian`, `chemical.state-tracking` | raw output and operation-specific evidence |
| xTB calculation backend | `xtb` | xTB binding or native command | `chemical.xtb`, `chemical.scan-xtb`, `chemical.gradient-xtb`, `chemical.neb-xtb` | raw output and operation-specific evidence |
| CF22D calculation backend | `cf22d` | PySCF binding | `chemical.cf22d` | convergence, frequencies and thermochemistry scope |
| CREST calculation backend | `crest` | CREST binding | `chemical.crest` and ensemble entries | ensemble receipt and member-level evidence |

`method-selection` coordinates these layers and chooses a named environment. It
does not replace the operation Skill or turn a successful Job into a scientific
verdict. `geometry-safety` is a cross-cutting preflight control used whenever a
coordinate set is about to enter an electronic-structure calculation.



See the [complete runtime registry](operation_backend_registry.md) for exact executor and validator paths.
