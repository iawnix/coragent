# Structure preparation

Use `chemical.inspect@1` to check the SMILES graph, formula, charge, and unspecified
stereochemistry. Select a stereoisomer for the study or enumerate alternatives
with `--enumerate-stereo`.

For a reaction study, first prepare atom identities and correspondence using the
[mapping procedure](reaction_mapping.md). `chemical.reaction@1` accepts mapped
`reactants>>products`, checks element/charge balance and atom correspondence, and
reports bond changes. Supply `--transformation <file.json>` with `kind: "explicit"`,
`bond_changes`, and optional `hydrogen_changes` to compare the current hypothesis
with those graphs. Results use `chemical-reaction/2`.

Use `chemical.seed@1` with `--smiles`, `--charge`, `--multiplicity`, and an empty
`--output-dir` to generate explicit-H XYZ with a fixed ETKDG seed. Choose charge
and multiplicity consistent with the graph and electron count. Each seed records
its SHA256, isomer provenance, and atom table for subsequent calculations.

## Compare structures

inspect and seed include a `chemical-identity/1` object with canonical isomeric SMILES,
charge, RDKit version and content identity. Register the chosen target as an Artifact
and reference it through the Node's `subjects.target`.
Prepare `chemical.compare@1` with `--input target=<inspect.json>` and
`--input actual=<structure.json-or-geometry.xyz>`. For XYZ add
`-- --actual-format xyz --charge <actual-charge>`; structure JSON is the default.
Collect `results/comparison.json`, which reports match, mismatch or indeterminate,
the compared structures and the scope of the checks. XYZ bond orders are inferred.
Record the findings with `check_refs` and distinguish target/calculated `subjects`.
Use differences to guide the research; checks do not gate publication or further work.

## Atom identity through seed generation

For reaction studies, follow [mapping preparation](reaction_mapping.md) before
embedding. `chemical.seed@1` preserves supplied explicit-H map labels and records
the exact `source_smiles`. Each seed includes `atom_index_base: 0` and an `atoms`
table in XYZ row order, with `xyz_index`, `element`, `atom_map`, `isotope`, `origin`,
and `parent_atom_index` (for singly bonded H). Save this table with the XYZ and its
SHA256. Row indexes refer to that seed, not to canonical SMILES traversal order.

Use fully mapped explicit-H SMILES when preparing a reaction. If the input uses
implicit H, seed adds their coordinates and records their parent rows with
`origin: "added_hydrogen"` and `atom_map: null`. Assign shared reaction labels on
the graphs before seeding so independently prepared fragments retain one common
label space. Subsequent conformer and optimization outputs inherit the table;
record explicit row permutations whenever order changes.
