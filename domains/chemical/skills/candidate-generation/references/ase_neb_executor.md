# ASE NEB candidate search

[中文](ase_neb_executor.zh-CN.md)

New searches use `chemical.neb-xtb@2` or `chemical.neb-gaussian@2`. ASE 3.29.0
provides improved-tangent NEB, climbing images and FIRE (default) or BFGS.
The calculators run the existing checked native adapters: xTB 6.7.1 GFN1/GFN2
(gas/ALPB) or Gaussian ground-spin HF/DFT (gas). This is a nonperiodic,
single-surface molecular search, not excited-state NEB or a crossing search.
ASE is the sole NEB implementation. Version-1 NEB entries have been removed;
old requests must be prepared again with the version-2 fields and units.

## Preparation and independent execution

Supply optimized, conformationally compatible endpoints for the hypothesized
single step. Record any remaining endpoint uncertainty. Missing products require
mechanism/candidate work first; distant multistep R/P should be split into plausible
steps. Check explicit-H mapping, charge, multiplicity and unwanted fragment motion.
The executor fixes supplied endpoints; it neither optimizes nor certifies them.

Configure native `path_xtb` or `path_gaussian`, then provision `--job-profile local:path`.
The separate `path.lock` includes ASE, SciPy, RDKit and NumPy. Existing wrapper and
structure environments do not automatically acquire ASE. Check the selected
executor/version in the chosen environment before dispatch.

```text
"$CORAGENT_PYTHON" -m research_agent.application.executors --config "$CORAGENT_JOB_CONFIG" --environment local --executor chemical.neb-xtb --version 2 --input input=<work_dir>/neb.json --input-artifact <input-ref> --output <work_dir>/neb-request.json
```

Replace placeholders with actual absolute paths/Artifact references. Submit returned
request_file/request_sha256 and node_id through job_start, then job_collect even
for failed or limited searches. For Gaussian change the executor and settings;
there is no separate ASE server and no change to Task/Node/Job/Artifact.

## Input contract

`chemical-neb-input/2` embeds `reactant`, `product` (`chemical-material/1`), complete
`mapping` pairs from reactant IDs to product IDs, and native `settings`.
Coordinates are Å, with 2–256 ordinary-mass atoms, known charge/multiplicity and
explicit compatible ground-state declarations. Product rows are reordered to
reactant IDs. See [path contracts](path_search.md) for materials/xTB settings and
[Gaussian electronic settings](../../gaussian/references/electronic_states.md)
for `theory: "ground"`, functional/basis, spin policy and resource limits.
No name lookup, automatic mapping, fragment alignment or graph inference occurs.

Optional fields (all bounds are enforced):

| Field | Default | Meaning |
| --- | --- | --- |
| image_count | 7 | 3–32 images including endpoints |
| images | absent | Explicit image × atom × xyz array in reactant order; endpoints must match |
| interpolation | linear | linear or idpp; supplied images cannot request reinterpolation |
| idpp_steps | 100 | 1–1000 bounded IDPP steps before native calculators; not chemical optimization |
| optimizer | FIRE | FIRE or BFGS |
| max_steps | 200 | 0–2000 updates; initial band evaluated even at zero |
| max_evaluations | 10000 | 1–100000 native attempts across all images; includes failures |
| fmax_ev_per_angstrom | 0.05 | Positive maximum internal-image atom NEB-force norm |
| spring_ev_per_angstrom2 | 0.1 | Positive spring constant |
| max_step_angstrom | 0.05 | Positive optimizer step cap, at most 1 Å |
| climb_after | 5 | Zero-based activation iteration, 0–2000; null disables climbing |

If the ordinary band converges early, requested climbing activates immediately
and remains active; convergence is rechecked with climbing forces. The optimizer
is restarted when climbing activates. The bound applies to the numerical path,
not to a physical TS validation. `idpp_steps` bounds initialization; reaching its
limit does not certify an optimal IDPP path. Initial collisions and duplicate
adjacent images are rejected; supply a physically plausible path when needed.

Each image owns an ASE Calculator; native evaluations are serial (each solver may
use configured threads). Geometry, atom order, method and convergence bind the
energy/gradient evidence. Hartree energy and negative dE/dR in hartree/Å convert to
ASE eV and eV/Å. Caching avoids rerunning unchanged endpoints/images. Budget the
native timeout, evaluation count and outer Job walltime together. Old `fmax`,
`spring`, `step_size` and `max_displacement` fields are not accepted by v2.

## Output and follow-up

`chemical-neb-result/2` records ASE/version, settings, mapping, model, per-iteration
energy/NEB force/climbing history, and evaluation count. Outputs include
`evaluations.json`, per-iteration `path.traj` and `path.xyz`, the final complete
`path.xyz`, `candidate.xyz` and `candidate.material.json` when available.
Native inputs, logs and calculation evidence remain in evaluation directories.
The ledger is written before each native call, including failed attempts.

Only `status=converged` exits zero. `step_limit` and `failed` retain partial evidence
and the last **fully evaluated** geometry/energy pair; proposed unfinished images
remain separate. A hard-killed running receipt is not a terminal result. Reconcile
its Job first. There is no automatic optimizer/checkpoint restart: a reviewed,
collected complete path may seed a new Job with explicit `images`.

The highest internal image is labeled `validated_ts: false`. Refine it as a saddle,
check the imaginary mode against intended coordinates, and establish bidirectional
IRC endpoints/minima with the validation tools. Multiple peaks, intermediates or
same-basin IRC may require revised hypotheses and separate step searches.
Use [failure diagnosis](../../method-selection/references/search_recovery.md),
[local diagnostics](../../material-preparation/references/local_diagnostics.md) and
[trajectory/report tools](../../report/references/research_tools.md) to inspect evidence.
