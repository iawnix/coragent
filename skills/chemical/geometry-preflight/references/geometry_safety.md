# Geometry preflight contract

The standalone executor consumes one `chemical-geometry-safety-input/1` JSON
object and returns a `chemical-geometry-safety/1` JSON report. Its hard scope is
finite Cartesian coordinates, matching element/coordinate counts, catastrophic
collapse, and severe contacts outside explicitly supplied reaction pairs. It
does not infer bonds from coordinates, establish molecular identity, or certify
a transition state. Elements and all supplied context must use the same atom
order.

`bonded_pairs` and `reaction_pairs` are zero-based index pairs. A reaction pair
may be longer or shorter than an equilibrium bond, but distances below the
absolute collapse floor are still rejected. Non-reaction unbonded contacts are
checked against an element-aware covalent-radius scale. A warning about
reaction-center non-equilibrium is expected for many valid TS candidates.

Supply `bonded_pairs` from the molecular graph; omitting it means connectivity is
unknown, while an empty list declares no bonds. Declared nonbonded H–H contacts
below 1.20 Å are rejected; bonded H₂ and declared reaction pairs use their own
context. With unknown connectivity, contacts below 0.70 Å are rejected and
0.70–1.20 Å contacts request a connectivity check in the warnings.

Optional `fragment_groups` partitions all zero-based atom indexes and identifies
interfragment contacts. Optional `reference_coordinates` uses the same atom order
to report changes to nonreaction bonded distances. Changes exceeding 0.20 Å or
20% of the reference length, whichever is larger, produce a diagnostic warning.
Without a reference, bond lengths outside 0.65–1.6 times the covalent-radius sum
produce a warning. Review these observations when selecting or refining poses.

With both `bonded_pairs` and `reference_coordinates`, angles along the supplied
bond graph are also compared. An absolute change greater than 30° produces a
`bond_angle_change` warning and sets `checks.bond_angles` to `warning`. Each
entry in `angles` records the three atom indexes, `angle_degrees`,
`reference_angle_degrees`, `delta_degrees`, and any adjacent declared
`reaction_pairs`. These changes are reported even at reacting bonds so that
straightening an originally bent fragment remains visible. They never cause a
hard rejection: the reaction context determines whether the change is intended.
Without the graph or reference, `checks.bond_angles` is `not_assessed`. An
unchanged linear fragment passes this comparison; linearity alone is not a
geometry error.

Required fields are `schema_version`, `elements`, and `coordinates` (one
three-number Cartesian row per element, in angstrom). `profile` defaults to
`general`; the other profiles are `reaction_seed`, `ts_candidate`, and
`path_image`. Optional `clash_scale` overrides the default nonreaction-contact
radius multiplier (respectively 0.75, 0.72, 0.70, and 0.72); it must be between
0.1 and 1.5 and never overrides the collapse check. Do not lower it to silence an
unexplained contact.

For example, a deliberate forming C–C pair can be checked with:

```json
{
  "schema_version": "chemical-geometry-safety-input/1",
  "elements": ["C", "C"],
  "coordinates": [[0, 0, 0], [1.8, 0, 0]],
  "bonded_pairs": [],
  "reaction_pairs": [[0, 1]],
  "profile": "ts_candidate"
}
```

Pass this file through the preparer's `--input input=<path>` role as shown in
[the Skill](../SKILL.md). The preparer owns the runner's `--input` and `--output`
arguments; do not pass them again after `--`. The prepared request is not a
geometry report. Submit it with `job_start` and read `results/result.json` after
completion. An `unsafe` report is a successful diagnostic result, not a reason
to submit the candidate unchanged.

The report contains the overall `verdict` (`safe` or `unsafe`), `hard_failures`,
`warnings`, per-check statuses in `checks`, the atom count, and the minimum pair
distance when assessed. `not_assessed` is a per-check status, not a standalone
verdict. Preserve the report with the exact candidate coordinates; editing the
geometry invalidates the old assessment. A `safe` verdict only clears covered
hard checks. Review warnings and the chemistry before proceeding.

For raw XYZ or GJF/COM inputs, use the corresponding registered Gaussian
executor described in [Gaussian](../../gaussian/SKILL.md). The explicit-input
executor `chemical.gaussian-input@1` checks Cartesian blocks during request
preparation and again before launch using the shared geometry function. A
checkpoint-only `Geom=AllCheck` section cannot be screened from its
input text. Generic Bash execution does not invoke those checks. Path contracts
reuse the same geometry function for endpoints and every NEB image.
