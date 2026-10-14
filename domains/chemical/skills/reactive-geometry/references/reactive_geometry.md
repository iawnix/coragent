# Reactive geometry contract

[中文](reactive_geometry.zh-CN.md)

`chemical.reactive-geometry@1` uses the `structure` binding (RDKit/NumPy). It edits
coordinates only. Solver preoptimization and TS searches are separate Jobs.

## Contents

- [Input](#input)
- [Operations](#operations)
- [Checks, output and handoff](#checks-output-and-handoff)

## Input

### Agent tool selection

Use `chemical.reactive-sites@1` when explicit mapped bond changes need to be
translated into fixed/mobile roles and local approach hypotheses. Use
`chemical.reactive-pose@1` to sample those hypotheses. Use a one-point
`chemical.scan-xtb@1` axis to perform restrained preoptimization before QST or
NEB. The [capability map](capability_map.md), [call cards](call_cards.md) and
[recovery playbook](recovery_playbook.md) describe how to interpret and combine
these results; none of them turns a geometry into a TS verdict.

### Automatic fragment poses

`chemical.reactive-pose@1` accepts `chemical-reactive-pose/1`. The request
embeds a `chemical-material/1` object:

```json
{
  "schema_version": "chemical-reactive-pose/1",
  "material": {"schema_version": "chemical-material/1"},
  "bond_changes": [{"atoms": ["C", "F"], "before": 0, "after": 1}],
  "sampling": {"count": 32, "direction_count": 7, "cone_degrees": 35}
}
```

At least one declared forming bond must connect separate graph fragments. The
executor chooses the larger fragment as the fixed reference, aligns the other
fragment's local reaction atom toward the fixed atom, and samples distances and
twists. For a multi-contact pose it fits the mobile fragment rigidly to all
requested targets; poses whose fit residual exceeds `pair_tolerance` are
rejected. Defaults are bounded and deterministic under `seed`; `distances` can
override the generated covalent-radius-based distances per forming pair, and
`twists` defaults to `[0, 120, -120]` degrees.

Every result records local directions, rigid transforms, reaction-pair distances
and the geometry-safety report. The executor never embeds SMILES, ranks
electronic energies or claims that an accepted pose is a TS. Use `chemical.seed`
or CREST first, inspect the pose ensemble, then run a separate constrained
preoptimization, QST, scan or NEB.

`chemical-reactive-geometry/1` contains an embedded `material` with 2–256 atoms in Å,
`bond_changes`, `edit_hypotheses`, and optional `sampling`. Product input is not
required. Import/assemble materials first using chemical-input/CREST; this executor
neither embeds SMILES nor optimizes monomers.

The material must have a reference molecular graph. For a graphless previous TS/path
candidate, provide `reference_material` with the same atom IDs/order/elements/isotopes
and state declaration. It supplies protected bonds and fragment groups, not proof of
current connectivity. Explicitly map/reorder independent materials first. Graph
`before` bond orders must match the declared changes; `after` differs. Reactive bonds
may stretch; all other bonds are checked against their source lengths.

A hypothesis has `id`, `note`, `source_refs` (empty for an initial chemical hypothesis),
`operations` and optional final `checks`. Use collected Artifact IDs as evidence refs;
strings are attribution, not a substitute for Job input-artifact bindings. Example
builds a request from a full imported material whose IDs are C, Cl, F and explicit H:

```python
import json
material = json.load(open("material.json"))
spec = {
    "schema_version": "chemical-reactive-geometry/1", "material": material,
    "bond_changes": [
        {"atoms": ["C", "F"], "before": 0, "after": 1},
        {"atoms": ["C", "Cl"], "before": 1, "after": 0}],
    "edit_hypotheses": [{"id": "backside", "note": "Test approach opposite C-Cl",
        "source_refs": [], "operations": [{"kind": "place", "atoms": ["C", "F"],
            "mobile_atoms": ["F"], "direction": {"kind": "away", "atoms": ["C", "Cl"]},
            "values": [2.4, 2.6], "cone_degrees": 15}],
        "checks": [{"atoms": ["Cl", "C", "F"], "minimum": 150, "maximum": 180}]}],
    "sampling": {"count": 16, "seed": 0}}
json.dump(spec, open("edits.json", "w"), indent=2)
```

Distances here are illustrative hypotheses, not universal TS bond lengths.

## Operations

| kind | Fields and interpretation |
| --- | --- |
| `place` | `atoms: [fixed, mobile]`, full separate reference fragment in `mobile_atoms`, `values` distances, required `direction`, optional `mobile_direction`, `twists` (degrees, default `[0]`), `cone_degrees` (default 0, at most 90). Pair must be a declared forming bond. |
| `distance` | Two `atoms`, `mobile_atoms` containing the second but not the first atom, `values` distances. Translate the selected group along the existing bond axis. |
| `angle` | Three `atoms`, middle atom is pivot; move the third atom and its group, keeping earlier anchors fixed. `values` in (0,180) degrees. |
| `dihedral` | Four `atoms`; rotate the fourth atom/group about the second–third axis. `values` in [-180,180] degrees. Ring edits that strain other bonds are rejected. |
| `displace` | Full `atom_ids`, exact canonical `material_sha256`, full N×3 `vectors`, `representation: "cartesian_direction"`, `source_ref` listed in the hypothesis and `values` signed amplitudes in Å. |

Placement frames are `{"kind":"away","atoms":[center,neighbor,...]}` (away from neighbor
centroid), `{"kind":"normal","atoms":[center,neighbor1,neighbor2]}` (plane normal), or
`{"kind":"vector","vector":[x,y,z]}` in the source Cartesian axes. Local frames may
use `sign: -1` for the opposite direction/face. The fixed frame stays outside the moving
group; the mobile frame belongs to that group. `mobile_direction` is aligned towards
the fixed reactive center with a proper rotation; twists explore rotations about the
approach axis. These are explicit geometric hypotheses, not computed orbital lobes.

Mode vectors preserve relative magnitudes and zeros. Scale the **whole mode** so its
maximum atom norm is at most 1; amplitudes then bound each atom's displacement.
Do not pass raw gradients or mass-weighted vectors. Use a frame that matches the
calculation: a material digest binds geometry/order but does not certify tensor axes.
The canonical digest is `sha256:` plus SHA256 of UTF-8 JSON with `sort_keys=True`,
`separators=(",", ":")`, `ensure_ascii=False`, `allow_nan=False`.

Operations run sequentially from the original material for each candidate. A Cartesian
product enumerates values/twists; hypotheses are interleaved. Nonzero cones permit
seeded directional resampling. `count` bounds total attempts (1–256), not accepted
structures. There are no unlimited retries; rejection can leave zero candidates.

## Checks, output and handoff

Every edit target is remeasured on the final geometry, with `tolerance` defaults
0.03 Å / 3 degrees. Placement also rechecks the actual approach and optional mobile
axis against `direction_tolerance_degrees` (default 3). Optional `checks` give 2/3/4 atom IDs plus ordered `minimum` and
`maximum` bounds; split wrapped dihedral intervals across hypotheses. Multiple
placements are sequential, not a simultaneous constraint solver: incompatible
multi-contact targets are rejected, requiring new hypotheses or constrained optimization.

All atom pairs are checked for collapse; nonbonded contacts use covalent radii with
`clash_scale` default .85. Protected bonds may change by at most
`protected_bond_tolerance` (default .15 Å). Specified tetrahedral handedness outside
the reaction center is checked relative to the source; this is not full stereo identity.
`max_local_displacement` (default .75 Å) limits accumulated local edits per atom;
rigid assembly translation is excluded. It is not an energy or gradient criterion.

Output contains `input.json`, `result.json` and accepted/rejected XYZs. Accepted
candidates also contain reusable `material.json`, with current connectivity unassigned
and reference graph/map tags retained in derivation, including across repeated edits. Charge/state and local atom IDs are
preserved. `source_refs`, actual transforms, diagnostics and refusal reasons remain
attached. Ranking is only normalized geometric target error; it does not prefer the
lowest-energy basin or estimate a barrier. Duplicate coordinates are reported separately.
Zero accepted candidates exits nonzero but retains reports. `enumeration_complete`
means the finite configured list was visited, not exhaustive conformational sampling.

```text
"$CORAGENT_PYTHON" -m research_agent.application.executors --config "$CORAGENT_JOB_CONFIG" --environment local --executor chemical.reactive-geometry --version 1 --input input=<work_dir>/edits.json --input-artifact <source-ref> --output <work_dir>/edit-request.json
```

Use absolute work_dir paths from research_create/read. Submit request_file/request_sha256
with node_id to job_start; after termination job_collect also collects rejected/failed
results. Review candidates, run appropriate constrained preoptimization as separate
Jobs, remeasure constraints and inspect energy/gradient evidence. Use explicit compatible
settings and supported solver inputs; this executor launches no preoptimization itself.
Exported guesses can feed chemical.qst-prepare (QST3 with complete guess_mapping), scans,
or explicitly prepared ASE images. A single guess does not supply missing NEB endpoints.
