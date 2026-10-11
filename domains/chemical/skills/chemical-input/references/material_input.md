# Preserve original structure materials

[中文](material_input.zh-CN.md). `chemical.material@1` imports SMILES, a name or one
XYZ frame into `chemical-material/1`. It checks input consistency without network
access, embedding, optimization, XYZ bond inference or electronic-state validation.
It is independent of products, reaction mapping and transition-state searches.

## Input

Supply `chemical-material-input/1` JSON with required `schema_version`, `format`
and nonempty `text`. Formats are `smiles`, `name` and `xyz`. Preserve the user's
original text instead of converting it first. The file limit is 4 MiB; unsupported
or misspelled fields are rejected rather than silently discarded.

```json
{
  "schema_version": "chemical-material-input/1",
  "format": "xyz",
  "text": "6\nUser supplied complex\nO 0 0 0\nH 0 0 0.96\nH 0 0.93 -0.24\nO 5 2 1\nH 5 2 1.96\nH 5 2.93 0.76\n",
  "arrangement": "complex",
  "fragments": [[0, 1, 2], [3, 4, 5]]
}
```

Charge, multiplicity and electronic state remain unknown in this example. Import
does not silently choose a neutral singlet.

| Optional field | Meaning |
| --- | --- |
| `charge` | Integer or null; a supplied molecular graph determines charge and must agree with an explicit value. XYZ alone does not provide charge |
| `multiplicity` | Positive integer or null; no singlet default. Check electron-count parity when atoms and charge are known |
| `electronic_state` | Object with kind unspecified/ground/excited/broken_symmetry and optional label/method/note; an excited root requires a positive integer and method. A declaration, not wavefunction evidence |
| `arrangement` | unspecified/isolated_species/separate_reactants/complex; defaults to unspecified. Disconnected graphs do not establish association |
| `fragments` | Partition of all input atom indexes, zero-based. Checked against graph components if supplied; XYZ-only groups are declarations |
| `atom_ids` | Unique local IDs for all input atoms; defaults atom_1, atom_2, etc. Matching names across materials do not establish correspondence |
| `new_to_old` | Complete zero-based permutation: output atom i takes the indicated input row. Default preserves input order |
| `graph` | Optional selected graph for name/xyz: smiles, source (user/lookup/agent) and required provenance note. Use existing resolve/resolve-candidates for names; import does not certify name/graph correspondence |
| `graph_to_input` | Required with XYZ plus graph: each explicit-H graph atom maps to an input XYZ row. Complete zero-based permutation checked for count/elements, not geometric/stereochemical identity |
| `coordinate_unit` | Currently only angstrom for XYZ; omission uses and records the standard XYZ convention. Explicitly convert other units while retaining source materials |

SMILES preserves explicit H, isotopes and atom-map labels, adds implicit H to the
atom table and does not embed coordinates. Order is RDKit parsed explicit atoms
followed by added H, with RDKit version and per-atom origin recorded. Atom IDs,
fragments and permutations use this complete order. Partial map labels are retained;
duplicates are rejected. Local atom identifiers are not reaction mapping.
Supply one plain molecular SMILES; trailing names, additional records, CXSMILES
extensions and wildcard atoms require explicit handling rather than silent removal.

XYZ accepts exactly one frame with element symbols and three finite coordinates.
Multiple frames, extra columns, isotope-specific symbols and other units require
explicit handling; none are silently dropped. Coordinates are not embedded,
aligned or optimized. A graph can record isotopes, but subsequent solver inputs
still need explicit support for isotope masses beyond plain XYZ symbols.

A name without a selected graph can still be recorded; `unknown_fields` identifies
the missing structure and other information. Continue existing name resolution or
attributed candidate inference, then create a new material citing the prior source.
Do not fabricate a product or mapping just to import a name.

## Execution and outputs

```text
"$CORAGENT_PYTHON" -m research_agent.application.executors --config "$CORAGENT_JOB_CONFIG" --environment local --executor chemical.material --version 1 --input material=<work_dir>/material-input.json --output <work_dir>/material-request.json
```

Submit the returned request_file/request_sha256 with node_id to `job_start`, then
`job_collect`. The Job pins the input JSON digest. Link source evidence through
existing input-artifact and Result references; graph source/note attributes do
not replace execution provenance or evidence references.

| Output | Content |
| --- | --- |
| `results/material.json` | Original input/digests, optional graph identity, atoms, fragments, state declarations, unknown fields and check scope |
| `results/source.txt` | Exact UTF-8 bytes of text, retaining numeric precision, line endings and comments |
| `results/atom_order.json` | chemical-material-order/1 with input/output IDs, new_to_old, inverse old_to_new, index_base=0 |
| `results/geometry.xyz` | XYZ only; identical to source.txt by default; an explicit permutation only reorders rows, retaining coordinates and relative orientation |

`geometry.status=supplied_not_assessed` neither refutes an existing optimization
nor certifies convergence. Parity compatibility does not verify electronic state;
an excited/root declaration does not expand backend capabilities. Graph identity
works with existing `chemical.compare`, but does not certify conformer, state or name.

Use collected geometry.xyz for independent SP/optimization with explicitly chosen
charge, multiplicity and method. Resolve required calculation settings using
evidence or branches; importing material does not require resolving all unknowns.

This entry only permutes atom rows, not gradients, Hessians or mode vectors, and
does not find reaction mappings. Reordering XYZ alone cannot authorize reuse of
existing tensors. Use the independent [mapping, conformer comparison and tensor
permutation entries](structure_analysis.md) for those operations, with explicit
search coverage and tensor representation.
