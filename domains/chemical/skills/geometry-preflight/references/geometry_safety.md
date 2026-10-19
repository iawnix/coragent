# Geometry preflight contract

The checker returns `chemical-geometry-safety/1`-compatible JSON. Its hard
scope is finite Cartesian coordinates, atom identity/order, catastrophic
collapse, and severe contacts outside explicitly supplied reaction pairs. It
does not infer bonds from coordinates and does not certify a transition state.

`bonded_pairs` and `reaction_pairs` are zero-based index pairs. A reaction pair
may be longer or shorter than an equilibrium bond, but distances below the
absolute collapse floor are still rejected. Non-reaction unbonded contacts are
checked against an element-aware covalent-radius scale. A warning about
reaction-center non-equilibrium is expected for many valid TS candidates.

The standalone executor accepts an input JSON object:

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

It writes one JSON result. Gaussian integration uses the same parser and checks
all explicit coordinate blocks before launching the executable. Path contracts
reuse the same geometry function for endpoints and every NEB image.
