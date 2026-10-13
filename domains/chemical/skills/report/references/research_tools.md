# Trajectory and illustrated research report Jobs

[中文](research_tools.zh-CN.md)

`chemical.trajectory@1` and `chemical.research-report@1` are independent `structure`
Jobs using RDKit/NumPy, Matplotlib and Pillow already present in structure.lock.
They do not launch a solver or need a TS workflow. Prepare with one `input` JSON,
submit returned request/digest with node_id, and collect the recursive results:

```text
"$CORAGENT_PYTHON" -m research_agent.application.executors --config "$CORAGENT_JOB_CONFIG" --environment local --executor chemical.trajectory --version 1 --input input=<work_dir>/trajectory.json --input-artifact <input-ref> --output <work_dir>/trajectory-request.json
"$CORAGENT_PYTHON" -m research_agent.application.executors --config "$CORAGENT_JOB_CONFIG" --environment local --executor chemical.research-report --version 1 --input input=<work_dir>/report.json --input-artifact <input-ref> --output <work_dir>/report-request.json
```

Use real absolute paths and Artifact references. Bind original logs/materials as
Artifacts too; a hash of supplied data alone does not verify its scientific origin.
JSON canonical digests use `sha256:` plus SHA-256 of sorted-key, compact UTF-8 JSON
(`json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)`).
They differ from byte-for-byte file digests.

## Trajectory input

`chemical-trajectory-input/1` requires `material` (chemical-material/1, 1–128 atoms
with coordinates) and `kind`: irc, neb, optimization, mode or other. Supply exactly one:

- `frames`: 2–512 ordered objects with `coordinates` (atom × xyz in Å) and optional
  `energy_hartree` (finite number or null). Atom order is exactly material order.
  Require `source_sha256`; if any energy is present also supply a common `model`
  object. Preserve the original source frame order; this is not a log parser.
- `neb_result`: a terminal chemical-neb-result/2 with matching atom IDs and
  complete paired images/energies; kind must be neb. Model, source digest and
  converged/step_limit/failed status are retained. Any explicit digest/model must
  agree. Pending images are not substituted for evaluated geometry/energy pairs.
- `mode`: `{ "vectors": [[...]], "representation": "cartesian_displacement",
  "frequency_cm1": -500.0 }` plus source_sha256 and kind=mode. Vectors are atom × xyz;
  convert mass-weighted modes correctly before submission. A 33-frame sinusoidal
  illustration uses `amplitude_angstrom` (default .15, positive and <=1) as maximum
  per-atom displacement. No computed energies, dynamics or IRC are implied.

Optional `coordinates` use the [local diagnostic contract](../../chemical-input/references/local_diagnostics.md).
`display_bonds` are explicit ID pairs (at most 512); no bonds are inferred.
`animation_frames` (2–128, default64) bounds sampled GIF frames and records source
indices; result JSON, XYZ and CSV retain all frames. `fps` is 1–30, default8.
The camera, axes and scale remain fixed across frames, with no per-frame alignment.

Outputs: result.json, trajectory.xyz, trajectory.gif, profile.csv, profile.svg and
profile.png. Profile panels separate energy, distances and angles; missing energies
remain gaps, with no interpolation or zero fill. Relative energy uses the lowest
available frame as reference, not an activation barrier. Frame index is not time;
a mode animation is not evidence of trajectory completion or reaction connectivity.

## Research report input

`chemical-research-report-input/1` requires title, question, assessment (nonempty
strings) and an explicit limitations list (may be empty). Assessment is **author
interpretation**, not an automatically accepted scientific verdict. Evidence contains
1–128 rows:

```json
{"id":"candidate-check","label":"Candidate geometry","result":{"schema_version":"example-result/1","status":"not_assessed"},"source_sha256":"sha256:<canonical result digest>","artifact_id":"<actual source Artifact>"}
```

IDs must be unique; result must declare its schema; the digest must match its
canonical content. artifact_id is optional attribution, not an Artifact-store lookup.
Full results, reported status and limitations remain in result.json; the generator
does not promote their reported status to a new scientific certification.

The optional `research_review` field accepts a complete `research-review/1`
projection. Its `review_digest` is recomputed over the projection excluding the
digest field. The generated `result.json` and `report.md` preserve the Review's
ID, state digest, source references, contradictions and uncertainties. A Review
does not replace the required source Result/Artifact evidence or certify a
transition state.

Optional `structures` has at most12 `{label, material, display_bonds}` rows (1–128
coordinate atoms each). Optional `trajectory` is a complete input as above.
Optional `energy_profile` is a chemical-energy-profile-input/1 object, recomputed
by the existing [energy module](../../energetics/references/energy_execution.md):
consistent quantities/models/conditions and balanced stoichiometry are required.
A supplied untyped energy table cannot become a barrier plot. Missing requested
quantities are rejected; omit energy_profile and report missing evidence explicitly.

Outputs include report.md, result.json, optional structures.png, energy.json/CSV/
SVG/PNG and trajectory/ files. Energy figures are discrete state levels; they do
not invent a continuous PES. Markdown embeds the actual figures and labels supplied
assessment, incomplete paths and missing energy data. HTML/PDF export and scientific
interpretation remain separate tasks. Review figures, units, references, source
coverage and limitations before registering and delivering the report.
