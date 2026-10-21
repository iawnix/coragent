# Skill script routing

This is the script map for registered Skills. It is derived from
`domains/chemical/execution.json`; the executor ID and version are the public
interface. Invoke an operation through the standard executor and Job lifecycle.
The `entry` column is the implementation entrypoint and `cli` is its argument
parser. Files imported by an entrypoint are implementation helpers, not
separate commands.

Do not read a script to discover how to call a registered operation. Use the
operation's Skill reference for its input contract, this map for routing, and
the executor's `--help` only when a contract leaves an option unspecified.
Direct script execution is for local diagnostics or development; it does not
replace `job_start`/submission/collection for a research Job.

Paths below are relative to `domains/chemical/`.

## cf22d

| Operation | Entry | CLI | Inputs | Primary outputs |
| --- | --- | --- | --- | --- |
| `chemical.cf22d@1` | `skills/cf22d/scripts/run.py` | `skills/cf22d/scripts/cli.py` | `geometry` | `results/result.json`, `results/geometry.xyz` |
| `chemical.cf22d-doctor@1` | `skills/cf22d/scripts/doctor.py` | — | environment | diagnostic JSON/stdout |

`run.py` handles `sp`, `opt`, `opt-sp`, `ts`, `freq`, `thermo`, `opt_freq`, and
`ts_freq`. `doctor.py` checks the configured PySCF/CF22D installation and does
not perform a scientific calculation.

## xtb

| Operation | Entry | CLI | Inputs | Primary outputs |
| --- | --- | --- | --- | --- |
| `chemical.xtb@1` | `skills/xtb/scripts/run.py` | `skills/xtb/scripts/cli.py` | `geometry` | `results/result.json`, `results/geometry.xyz` |

`run.py` handles the registered `sp`, `opt`, and `opt-sp` wrapper. Scan,
gradient, and NEB operations are routed under `candidate-generation` below;
`parser.py` is an internal native-output parser.

## gaussian

| Operation | Entry | CLI | Inputs | Primary outputs |
| --- | --- | --- | --- | --- |
| `chemical.gaussian@1` | `skills/gaussian/scripts/run.py` | `skills/gaussian/scripts/cli.py` | `geometry` | `results/result.json`, `results/geometry.xyz` |
| `chemical.gaussian-input@1` | `skills/gaussian/scripts/run.py` | `skills/gaussian/scripts/cli.py` | `input` | `results/result.json`, `results/gaussian.out`, `results/parsed.json` |
| `chemical.electronic-gaussian@1` | `skills/gaussian/scripts/electronic.py` | `skills/gaussian/scripts/electronic_cli.py` | `input` | `results/result.json` |
| `chemical.state-tracking@1` | `skills/gaussian/scripts/electronic.py` | `skills/gaussian/scripts/electronic_cli.py` | `input` | `results/result.json` |

`run.py` is selected by input kind: XYZ uses `--xyz`, complete Gaussian input
uses `--input-gjf`. `electronic.py` serves bound-state electronic and
state-tracking operations. Path gradients/NEB and validation evidence have
separate entries in their owning Skills.

## material-preparation

| Operations | Entry | CLI | Inputs | Primary outputs |
| --- | --- | --- | --- | --- |
| `chemical.resolve@1`, `chemical.resolve-candidates@1`, `chemical.inspect@1`, `chemical.seed@1`, `chemical.reaction@1`, `chemical.compare@1` | `skills/material-preparation/scripts/reaction/prepare.py` | `skills/material-preparation/scripts/reaction/cli.py` | operation-specific | `results/<operation>.json` |
| `material` | `skills/material-preparation/scripts/materials/material.py` | `skills/material-preparation/scripts/materials/material_cli.py` | `material` | `results/material.json`, `results/atom_order.json` |
| `chemical.map-candidates@1`, `chemical.conformer-compare@1`, `chemical.reorder-tensors@1` | `skills/material-preparation/scripts/geometry/analysis.py` | `skills/material-preparation/scripts/geometry/analysis_cli.py` | operation-specific | `results/result.json` |
| `local-diagnostics` | `skills/material-preparation/scripts/diagnostics/diagnostics_job.py` | `skills/material-preparation/scripts/diagnostics/diagnostics_cli.py` | `input` | `results/result.json` |

Use the executor ID to select the sub-operation; do not call helper modules such
as `correspondence.py`, `conformers.py`, or `analysis_material.py` directly.

## reactive-geometry

| Operation | Entry | CLI | Inputs | Primary outputs |
| --- | --- | --- | --- | --- |
| `chemical.reactive-geometry@1` | `skills/reactive-geometry/scripts/reactive_geometry.py` | `skills/reactive-geometry/scripts/reactive_cli.py` | `input` | `results/result.json` |
| `chemical.reactive-sites@1` | `skills/reactive-geometry/scripts/reactive_sites.py` | `skills/reactive-geometry/scripts/reactive_sites_cli.py` | `input` | `results/result.json` |
| `chemical.reactive-pose@1` | `skills/reactive-geometry/scripts/reactive_pose.py` | `skills/reactive-geometry/scripts/pose_cli.py` | `input` | `results/result.json` |

The three entries respectively edit coordinates, analyze sites/frames, and
generate rigid fragment poses. `geometry_contract.py` and `geometry_ops.py`
are internal helpers.

## candidate-generation

| Operations | Entry | CLI | Inputs | Primary outputs |
| --- | --- | --- | --- | --- |
| `path-candidates` | `skills/candidate-generation/scripts/path/prepare_path.py` | `skills/candidate-generation/scripts/path/cli.py` | `spec` | `results/candidates.json` |
| `chemical.qst-prepare@1`, `chemical.scan-xtb@1`, `chemical.scan-gaussian@1`, `chemical.gradient-xtb@1` | `skills/candidate-generation/scripts/search/search.py` | `skills/candidate-generation/scripts/search/search_cli.py` | `input` | `results/result.json` |
| `search-recovery` | `skills/candidate-generation/scripts/search/recovery.py` | `skills/candidate-generation/scripts/search/recovery_cli.py` | `input` | `results/result.json` |
| `gradient-gaussian` | `skills/candidate-generation/scripts/backends/gaussian_path.py` | `skills/candidate-generation/scripts/search/search_cli.py` | `input` | `results/result.json` |
| `chemical.neb-xtb@2`, `chemical.neb-gaussian@2` | `skills/candidate-generation/scripts/neb/ase_search.py` | `skills/candidate-generation/scripts/neb/ase_cli.py` | `input` | `results/result.json` |

The operation ID chooses the backend and search mode. `path_contract.py`,
`scan_engine.py`, backend calculators, and ASE helpers are internal modules.

## validation

| Operations | Entry | CLI | Inputs | Primary outputs |
| --- | --- | --- | --- | --- |
| `path-irc` | `skills/validation/scripts/irc_preparation.py` | `skills/validation/scripts/irc_preparation_cli.py` | `spec`, `checkpoint` | `results/irc_inputs.json` |
| `stationary-check`, `mode-check`, `irc-check`, `gaussian-evidence` | `skills/validation/scripts/evidence_check.py` | `skills/validation/scripts/check_cli.py` | operation-specific evidence | `results/result.json` |

`evidence_check.py` is one entry with independent public operation IDs. Other
parser and numerical files under this directory are helpers.

## crest

| Operations | Entry | CLI | Inputs | Primary outputs |
| --- | --- | --- | --- | --- |
| `chemical.crest@1` | `skills/crest/scripts/crest_run.py` | `skills/crest/scripts/crest_cli.py` | `material` | `results/result.json`, `results/crest.out` |
| `chemical.crest-ensemble@1`, `chemical.ensemble-select@1`, `chemical.complex-sample@1` | `skills/crest/scripts/ensemble.py` | `skills/crest/scripts/ensemble_cli.py` | operation-specific | `results/result.json` |

## energetics

| Operations | Entry | CLI | Inputs | Primary outputs |
| --- | --- | --- | --- | --- |
| `chemical.thermochemistry@1`, `chemical.ensemble-free-energy@1`, `chemical.energy-profile@1`, `chemical.scan-slice@1`, `chemical.tst@1`, `chemical.branching@1`, `chemical.kinetic-network@1` | `skills/energetics/scripts/energy.py` | `skills/energetics/scripts/energy_cli.py` | `input` | `results/result.json`, `results/table.csv` |

## reaction-investigation

| Operation | Entry | CLI | Inputs | Primary outputs |
| --- | --- | --- | --- | --- |
| `chemical.pathway-check@1` | `skills/reaction-investigation/scripts/pathway_job.py` | `skills/reaction-investigation/scripts/pathway_cli.py` | `input` | `results/result.json` |

## surface-crossing

| Operations | Entry | CLI | Inputs | Primary outputs |
| --- | --- | --- | --- | --- |
| `chemical.mecp-gaussian@1`, `chemical.crossing-check@1` | `skills/surface-crossing/scripts/crossing.py` | `skills/surface-crossing/scripts/crossing_cli.py` | `input` | `results/result.json` |

## geometry-preflight

| Operation | Entry | CLI | Inputs | Primary outputs |
| --- | --- | --- | --- | --- |
| `chemical.geometry-safety@1` | `skills/geometry-preflight/scripts/run.py` | `skills/geometry-preflight/scripts/cli.py` | `input` | `results/result.json` |

## structure-assessment

| Operation | Entry | CLI | Inputs | Primary outputs |
| --- | --- | --- | --- | --- |
| `chemical.structure-cognition@1` | `skills/structure-assessment/scripts/run.py` | `skills/structure-assessment/scripts/cli.py` | `material`, `context` | `results/result.json` |

## report

| Operations | Entry | CLI | Inputs | Primary outputs |
| --- | --- | --- | --- | --- |
| `chemical.render@1` | `skills/report/scripts/render.py` | `skills/report/scripts/render_cli.py` | `geometry` | `results/render/geometry.svg`, `results/render/geometry.png` |
| `chemical.trajectory@1`, `chemical.research-report@1` | `skills/report/scripts/research_job.py` | `skills/report/scripts/research_cli.py` | `input` | `results/result.json` |

## method-selection

No bundled executor; method-selection routes to the selected backend Skill.

## qbics

No bundled executor; QBICS uses an explicitly declared generic Job.

## Skills without a bundled executor

`method-selection` and `qbics` intentionally have no repository-owned script
entry. Use their documented generic Job or installed-program route. A generic
Job must declare its script, backend, inputs, outputs, and parser explicitly.

## research-memory

No bundled script; use runtime research-memory tools.

## research-workflow

No bundled script; use runtime task and Job tools.

## Non-chemical operational scripts

The following three paths are relative to the repository root.

### batch-schedulers

| Skill | Script | Interface |
| --- | --- | --- |
| `batch-schedulers` | `skills/batch-schedulers/scripts/queue.py` | first argument `pbs`, `torque`, or `slurm`; JSON request on stdin; `probe`, `submit`, `status`, `cancel`, `recover`; JSON receipt/status on stdout |

### email

| `email` | `skills/email/scripts/email_cli.py` | subcommands `check`, `prepare`, `send`; request and result JSON files; use only after authorization |

### tri-operations

| `tri-operations` | `skills/tri-operations/scripts/queue.py` | external-Job JSON request on stdin; stable submit/status/cancel/recover receipts |

### research-memory and research-workflow

`research-memory` and `research-workflow` use runtime tools and Job APIs; they
do not have a bundled script entrypoint.
