# Structure cognition contract

The executor accepts two JSON files.

`material.json` must be a `chemical-material/1` object produced by the
chemical-input Skill. `context.json` must have this shape:

```json
{
  "schema_version": "chemical-structure-context/1",
  "role_hint": "ts_candidate",
  "reaction_center": ["atom_4", "atom_7"],
  "bond_changes": [
    {"atoms": ["atom_4", "atom_7"], "before": 0, "after": 1,
     "note": "proposed forming bond"}
  ],
  "reference_material": null,
  "notes": "A candidate for the proposed elementary step"
}
```

`role_hint` is one of `unknown`, `reactant`, `product`, `intermediate`,
`reactive_complex`, `optimized_structure`, or `ts_candidate`. It is a declared
interpretive role, not a computed verdict. `reaction_center` contains local atom
IDs. `bond_changes` uses bond orders from 0 through 3 and is a hypothesis; when a
graph is available, the report checks whether `before` agrees with that graph.
The optional `reference_material` must use the same atom IDs, elements, isotopes
and order and provides a geometry comparison. `notes` are provenance, not
evidence.

The result has `status=assessed`, `partial`, or `inconclusive`. It separates:

- `role_assessment`: declared role and whether it was supplied;
- `structure_summary`: graph, atom, fragment and electronic-state facts;
- `geometry_observations`: the shared safety result plus bounded geometric
  observations, including local angles reported without a normality verdict;
- `reaction_center`: local neighbors and bond-change measurements;
- `comparison`: optional reference deltas;
- `uncertainties` and `follow_up`: missing evidence and useful next Skills.

Distance labels are observations relative to the sum of covalent radii:
`collapsed`, `compressed`, `normal_like`, or `elongated`. They do not define
normality for a transition state. An elongated forming bond can be a useful
candidate observation; a collapsed pair is a geometry failure. Fragment
separation uses a conservative 8 angstrom centroid observation and is a warning,
not a chemical impossibility claim.

The scope is structural evidence only. It does not infer coordinate-derived
bonds, validate a wavefunction, certify a TS, prove a mechanism, or impose a
research sequence.
