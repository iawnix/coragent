# Local geometry diagnostics

[中文](local_diagnostics.zh-CN.md)

`chemical.local-diagnostics@1` runs independently on `structure` (RDKit/NumPy).
It requires no product, TS or workflow state. Use it for seeds, failed optimizer
frames, NEB images or conformer comparisons; electronic analysis remains separate.

The `chemical-local-diagnostics-input/1` object contains `material` (embedded
chemical-material/1 with 1–256 coordinate atoms) and `reaction_center` (distinct
local atom IDs). Optional `spectators` are disjoint IDs. Optional `reference`
requires a complete explicit `mapping` from **material IDs to reference IDs**,
matching elements and isotopes. IDs refer to materials, not zero-based XYZ rows.

Optional fields:

- `coordinates`: up to 256 objects like
  `{"id":"forming","atoms":["atom_1","atom_2"],"minimum":1.5,"maximum":2.5}`.
  Two/three/four atoms mean distance/angle/dihedral, in Å/degrees. Omit both bounds
  to observe only. Distances are nonnegative, angles 0–180°, dihedrals −180–180°;
  dihedral minimum > maximum denotes a wrapped interval. Degenerate values are null.
- `contact_scale`: 0.1–1.5, default 0.75 times the sum of RDKit covalent radii.
- `allowed_contacts`: up to 512 explicit ID pairs; flagged contacts remain visible.

Output `chemical-local-diagnostics-result/1` includes six nearest neighbors per
center atom, short-contact pairs involving the center, internal coordinates and
bound checks. With a reference it gives proper-rotation heavy-atom and center
Kabsch fits, per-atom displacements, plus spectator RMSD after center alignment
only when both centers are noncollinear. It does not reflect mirror images or
independently align fragments. Charge/spin/state declarations are reported
separately from geometry; equal declarations do not establish wavefunction identity.
Short contacts are a proximity heuristic, not inferred bonds/valence or evidence
that a TS/mechanism is valid. The scientific verdict remains `not_assessed`.

```text
"$CORAGENT_PYTHON" -m research_agent.application.executors --config "$CORAGENT_JOB_CONFIG" --environment local --executor chemical.local-diagnostics --version 1 --input input=<work_dir>/diagnostics.json --input-artifact <input-ref> --output <work_dir>/diagnostics-request.json
```

Replace placeholders, submit the returned request/digest with node_id, then collect
`results/result.json`. It retains canonical input/material digests and input-file
SHA-256. Compare selected frames with [trajectory tools](../../report/references/research_tools.md)
and interpret observations using [search diagnosis](../../method-selection/references/search_recovery.md).
