# Call cards

These cards describe tool selection and interpretation. Replace paths with the
absolute `work_dir` returned by `research_create` or `research_read`, and bind
the input Artifact when submitting the request.

## Analyze mapped reaction sites

Use when a `chemical-material/1` and explicit mapped bond changes exist.

```text
chemical.reactive-sites@1
input=input.json
```

The input has this shape:

```json
{
  "schema_version": "chemical-reactive-sites/1",
  "material": {"schema_version": "chemical-material/1"},
  "bond_changes": [
    {"atoms": ["C", "F"], "before": 0, "after": 1},
    {"atoms": ["C", "Cl"], "before": 1, "after": 0}
  ],
  "reaction_family": "sn2"
}
```

Use the returned `sites[*].hypotheses` as explicit alternatives for pose
generation. `opposite_face` is an exploration alternative, not a claim that the
reaction is stereochemically ambiguous.

## Generate poses

Use `chemical.reactive-pose@1` for each selected site or for a bounded combined
sample. Copy the explicit pair and distance hint into `bond_changes` and
`sampling`; preserve the returned transform and rejection diagnostics. Add
conformer IDs to the provenance when the same pose search is run for multiple
conformers.

## Constrained preoptimization

Use `chemical.scan-xtb@1` with one scan axis and one target value to relax a
pose while retaining its reaction coordinate. The axis uses local atom IDs:

```json
{
  "schema_version": "chemical-scan-input/1",
  "material": {"schema_version": "chemical-material/1"},
  "settings": {
    "method": "gfn2", "threads": 2, "timeout_seconds": 600,
    "solvent_model": "gas", "solvent": null, "opt_level": "tight",
    "force_constant": 1.0
  },
  "axes": [{
    "kind": "distance", "atoms": ["C", "F"],
    "values": [2.2], "unit": "angstrom", "tolerance": 0.08
  }]
}
```

Read `points[*].actual`, `deviations`, `status`, `energy_hartree` and
`evidence`. A failed or collapsed point is a reason to change the pose,
conformer or constraint hypothesis; it is not evidence that the reaction is
impossible. Keep the constrained geometry's candidate lineage when handing it
to QST or NEB.

## Continue to a path search

Use QST when mapped product and guess correspondence are explicit. Use a
relaxed scan when one or two coordinates are the main uncertainty. Use NEB/GSM
only after endpoints are compatible and the initial images preserve the intended
reaction-center changes. Read the candidate-generation path reference for the
selected recipe's exact contract.

## Generic Job invocation

Prepare each declared executor with the generic executor CLI, then submit its
`request_file` and `request_sha256` with `node_id` to `job_start`. Do not call
scientific scripts with the control-plane Python. Collect the terminal result
and inspect it before choosing the next hypothesis.
