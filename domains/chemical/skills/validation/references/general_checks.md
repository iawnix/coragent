# Reaction-independent evidence checks

[中文](general_checks.zh-CN.md). These version-1 executors run independently on the
`structure` backend through ordinary Jobs. They produce `results/result.json`,
preserve input digests and never alter Node state or make a search conditional on
passing validation. They do not import the DA topology or its acceptance profile.

## Contents

- [Operations and verdicts](#operations-and-verdicts)
- [Stationary evidence](#stationary-evidence)
- [Mode character](#mode-character)
- [IRC evidence and assignment](#irc-evidence-and-assignment)
- [Gaussian adapter](#gaussian-adapter)
- [Execution](#execution)

## Operations and verdicts

| Executor | Inputs | Assessed property |
| --- | --- | --- |
| `chemical.stationary-check` | material, evidence | Optimization and complete vibrational signature of a minimum or first-order saddle |
| `chemical.mode-check` | material, evidence, coordinates | Stationarity plus response of the imaginary mode to declared internal coordinates |
| `chemical.irc-check` | material, evidence, forward, reverse, reactant, product | Source saddle evidence, path completeness and opposite endpoint basins |
| `chemical.gaussian-evidence` | material, evidence (raw log) | Converts one Gaussian section into stationary or IRC evidence; not a validation verdict |

`material` is `chemical-material/1`; the IRC material/evidence pair refers to the
source saddle. Each check returns `chemical-evidence-check/1`: individual `checks`,
`verdict=pass/fail/inconclusive`, scope and source file digests. A pass applies only
to that property's stated criteria. A mode pass does not establish IRC connection;
an IRC pass does not establish intended mode character. Assess both dimensions
before interpreting a candidate as the proposed classical TS.
Combine only reports with the same `sources.material` and `sources.evidence`
digests; passing checks from different structures or calculations are not one TS assessment.

Malformed inputs fail execution; missing scientific evidence is inconclusive;
contradictory evidence fails its check. Classical checks currently require an
explicit unconstrained ground-state single surface. Unknown constraints, excited
or broken-symmetry state kinds, barrierless models and crossings remain unassessed
(`scientific_verdict=not_assessed` for an unsupported source). Charge/multiplicity
and state declarations must agree with the material. This does not prove ground
state, SCF stability, spin purity or continuous wavefunction identity.

## Stationary evidence

`chemical-stationary-evidence/1` is backend-independent normalized evidence. A
source digest attributes a record; it does not certify extraction or computation.
Retain and cite primary outputs and their actual Job/Artifact derivation. Other
backends can supply the contract with a verified adapter/task script; do not fill
missing facts with passing defaults. CF22D's existing frequency JSON does not
contain mode vectors and is not by itself complete evidence for a mode check.

| Field | Contract |
| --- | --- |
| `material_sha256` | SHA256 of the exact supplied material file bytes, prefixed `sha256:` |
| `atom_ids` | Exact current atom-ID sequence of the material |
| `coordinates`, `coordinate_unit` | N × 3 finite values, angstrom; match the material in the same frame within 1e-5 angstrom, without fitting |
| `sources` | Nonempty list of `{kind, sha256}` records, with optional extraction metadata |
| `calculation` | method, basis, charge, multiplicity, electronic_state, constraints and surface; see below |
| `termination` | normal/error/unknown |
| `optimization` | converged (boolean/null), criteria list; optional start_coordinates for endpoint relaxation |
| `frequencies_cm-1` | Full signed vibrational spectrum, finite numbers; null if absent |
| `normal_modes` | K × N × 3 in the same atom/frame order and frequency order; null if absent |
| `mode_representation` | cartesian; mass-weighted vectors require an explicit prior conversion |

`calculation` requires known method/basis, integer charge and positive integer
multiplicity to pass. `electronic_state` uses the material's state description.
`constraints=[]` explicitly declares no constraints; null means unknown.
`surface=single_surface` is the supported model. These are recorded assumptions,
not a license to replace unknown settings with ground-state defaults.

Each optimization criterion has `name`, nonnegative `value`, positive `threshold`
and `unit`. Supported names are max_gradient/rms_gradient (hartree/bohr) and
max_displacement/rms_displacement (bohr). Passing requires converged=true,
both gradient criteria and every supplied criterion numerically satisfied. A
reported convergence flag alone is insufficient. Preserve the solver thresholds.

`--kind minimum|saddle` defaults to saddle. Coordinates determine vibrational
degrees of freedom: 3N−6 nonlinear, 3N−5 linear, zero for an atom. The centered
coordinate SVD uses a second/first singular-value ratio below 1e-7 for linear;
ratios from 1e-7 to 1e-4 are near-linear and remain unresolved. Degenerate geometry
also remains unresolved. Supply vibrational modes with overall translation and
rotation projected out, not a raw 3N Cartesian eigenvalue table.

`--negative-threshold` defaults to 20 cm−1 (positive magnitude); a significant
negative frequency is below its negative. Minimum/saddle requires zero/one such
modes. Every smaller negative stays visible and blocks a pass as unresolved.
`--near-zero` defaults to 10 cm−1 and cannot exceed the negative threshold;
absolute frequencies at/below it also remain unresolved. Saddle checks require
an available nonzero imaginary Cartesian vector. This availability check does
not determine its chemical character.

## Mode character

Supply `chemical-mode-coordinates/1` as the `coordinates` input. One coordinate
can be a distance, angle, signed dihedral or a weighted combination. Use local
atom IDs from the supplied material, not indexes or map labels.

```json
{
  "schema_version": "chemical-mode-coordinates/1",
  "coordinates": [
    {"name": "proton transfer", "direction": 1,
     "minimum_response": 0.02, "minimum_projection": 0.05,
     "terms": [
       {"atoms": ["donor", "H"], "weight": 1, "scale": 1},
       {"atoms": ["H", "acceptor"], "weight": -1, "scale": 1}
     ]}
  ]
}
```

Two/three/four IDs select angstrom distance/degree angle/degree dihedral. Terms
use nonzero finite weight and positive scale in the term's native unit; scale
defaults to 1. Scaling lets a declared combination include different units.
`direction` is +1 or −1 relative to the other declared coordinates. No universal
number of forming bonds or equal-amplitude condition is imposed.

The sole significant imaginary vector is normalized by its Cartesian Euclidean
norm. `--step` (default 0.05, maximum 0.5 angstrom) generates both signs of a
local displacement. Output retains both geometries, individual coordinate values,
combined central-difference response per angstrom and projection cosine onto the
numerical coordinate gradient. Dihedral differences wrap at 360 degrees.
The coordinate gradient uses a 1e-5 angstrom Cartesian difference step.

Each declared coordinate must exceed its minimum absolute response/projection
(defaults 0.02 and 0.05), and all responses must agree with the expected relative
directions up to one common sign. Reversing/scaling a mode cannot change the
conclusion. Degenerate coordinates/gradients are unresolved. Thresholds and
coordinate choices are study assumptions; inspect sensitivity. Perturbed
structures are not optimized minima and do not substitute for IRC calculations.

## IRC evidence and assignment

`forward` and `reverse` are `chemical-irc-evidence/1`. The slots may be exchanged;
their recorded `direction` must supply one forward and one reverse path. Each
record has the same binding, calculation, sources and coordinate unit fields as
stationary evidence, plus:

- `origin_coordinates`: N × 3 source coordinates in fixed atom-ID order. One
  proper rotation/translation is allowed against the source saddle (default
  `--origin-rmsd 0.01` angstrom); no symmetry relabeling or reflection.
- `complete` and `max_points_reached`: boolean/null. Only explicit completion
  without hitting the limit and normal termination passes completeness.
- `points`: at least two `{index, coordinates, energy_hartree?}` records, indexed
  contiguously from 1. Energies are optional finite numbers; no reference SCF is
  silently promoted to a different method's target energy.
- `endpoint`: null until basin evidence is available; otherwise an object with
  a material and `minimum_evidence` in the stationary contract.

Embed an existing endpoint material as `endpoint.material_json`, its exact UTF-8
file text (including line endings). Existing minimum_evidence then keeps its
original file digest. Alternatively `endpoint.material` accepts an object; its
binding digest uses canonical JSON: sorted keys, compact comma/colon separators,
UTF-8, unescaped Unicode, no NaN and no trailing newline. Supply exactly one form.
The common `material_sha256` on the path still binds the source saddle, not the endpoint.

The endpoint uses the source atom IDs, elements and isotopes and must equal the
last path point within 1e-5 angstrom in the same frame. If separately optimized,
minimum_evidence.optimization.start_coordinates must equal that last point;
its final geometry remains bound to the endpoint material. Preserve the actual
optimization output and its provenance; declaring a start coordinate is not
independent proof that an optimization ran. Require a passing unconstrained
minimum check at the same method/basis and compatible source state.

`reactant`/`product` are explicit reference materials with graphs, geometries
and compatible declared states. Assignment reuses the bounded conformer comparator
(default `--endpoint-rmsd 0.2` angstrom, `--max-search 20000`, `--max-candidates 64`).
One target must match and the other must be explicitly excluded. Ambiguous,
unexplored or unexpected basins retain the actual endpoint and remain unresolved.
Both directions must reach opposite target indexes; direction exchange is allowed.
This assesses the selected reference conformers, not every conformer of a species.
Missing minima call for continuation/endpoint optimization, not target fabrication.

## Gaussian adapter

`chemical.gaussian-evidence@1 --kind stationary|irc` reads a raw log and a material
in its output atom/frame order. `--section-index` explicitly selects a zero-based
section; otherwise existing final-section selection applies. It reuses Gaussian
frequency/mode/IRC parsing, records the log digest/section, extracts charge and
multiplicity, checks mode atomic numbers and retains coordinate-bearing points.

`--constraints none` is an explicit declaration based on the actual calculation
input, not inferred from a normal termination. Default unknown blocks classical
acceptance; recognized restriction markers veto the declaration. The adapter
supports the current HF/DFT SCF energy scope; other target methods/states and
explicit isotope masses remain unassessed. Local atom IDs and ground-state kind
are material declarations, not inferred atom trajectories or state tracking.
IRC extraction leaves endpoint null; a completion marker never fabricates a
minimum or target assignment. Raw CF22D or other backend payloads require an
appropriate normalization adapter; they are not accepted as this schema unchanged.

## Execution

Use absolute paths beneath the research work_dir. Submit the prepared request's
request_file/request_sha256 plus node_id through `job_start`, then `job_collect`.

```text
"$CORAGENT_PYTHON" -m research_agent.application.executors --config "$CORAGENT_JOB_CONFIG" --environment local --executor chemical.gaussian-evidence --version 1 --input material=<work_dir>/saddle/material.json --input evidence=<work_dir>/saddle.log --output <work_dir>/prepared/extract.json -- --kind stationary --constraints none
"$CORAGENT_PYTHON" -m research_agent.application.executors --config "$CORAGENT_JOB_CONFIG" --environment local --executor chemical.stationary-check --version 1 --input material=<work_dir>/saddle/material.json --input evidence=<work_dir>/stationary-evidence.json --output <work_dir>/prepared/stationary.json -- --kind saddle
"$CORAGENT_PYTHON" -m research_agent.application.executors --config "$CORAGENT_JOB_CONFIG" --environment local --executor chemical.mode-check --version 1 --input material=<work_dir>/saddle/material.json --input evidence=<work_dir>/stationary-evidence.json --input coordinates=<work_dir>/coordinates.json --output <work_dir>/prepared/mode.json
"$CORAGENT_PYTHON" -m research_agent.application.executors --config "$CORAGENT_JOB_CONFIG" --environment local --executor chemical.irc-check --version 1 --input material=<work_dir>/saddle/material.json --input evidence=<work_dir>/stationary-evidence.json --input forward=<work_dir>/forward.json --input reverse=<work_dir>/reverse.json --input reactant=<work_dir>/reactant/material.json --input product=<work_dir>/product/material.json --output <work_dir>/prepared/irc.json
```
