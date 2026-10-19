# Mapped QST2 preparation

`scripts/path/prepare_path.py` prepares Gaussian inputs from a declared elementary step.
It does not infer a product, select a mechanism, execute Gaussian or certify a saddle.
Use `chemical.path-candidates@1` for explicit transformations; a reaction name does
not require a new tool. IRC input preparation is a separate validation implementation; candidate generation does not provide or import it.

## Contents

- [Specification](#specification)
- [Geometry strategies](#geometry-strategies)
- [Execute and retain provenance](#execute-and-retain-provenance)

## Specification

Register a `chemical-path-spec/1` JSON Artifact. Supply mapped reactants and products,
the complete proposed bond changes and explicit Gaussian settings:

| Field | Preparation |
| --- | --- |
| `schema_version` | `chemical-path-spec/1` |
| `mapped_smiles` | Mapped reactants and products for the current hypothesis, joined with `>>` |
| `transformation` | `kind: "explicit"` and complete `bond_changes`; each entry gives mapped `atoms`, `before` and `after` bond orders |
| `candidate_strategy` | Select the geometry source below |
| `method`, `basis` | Method and basis chosen for this calculation |
| `charge`, `multiplicity` | System charge and spin multiplicity |
| `threads`, `memory_mb` | Allocated Job resources |

Atom-map IDs must be unique and consistent across both sides. Bond order 0 means
no bond. Optional `hydrogen_changes` uses `{atom, before, after}` counts. Map each
transferred H explicitly in the SMILES: counts alone cannot preserve its trajectory.
The preparer checks atom correspondence, element/isotope and charge balance, declared
changes, total charge and electron-count/multiplicity parity. One specified charge/spin
surface is used throughout; spin crossings are outside this workflow. The element-only
Gaussian writer rejects isotope-specific masses; use explicit solver inputs for those.

## Geometry strategies

| candidate_strategy | Inputs and behavior |
| --- | --- |
| `mapped_endpoints` | Default for explicit specs without endpoints. Each side must contain one connected fragment. Deterministic RDKit embedding, optional UFF relaxation and rigid alignment generate QST2 seeds. No reaction-specific geometry rule is imposed. |
| `provided_endpoints` | Default when `endpoints` is supplied. Preserves supplied coordinates, including multi-fragment placement. Requires `--conformers 1` and no `--enumerate-stereo`; submit each geometry pair separately. |

For supplied geometries, `endpoints` has exactly `reactants` and `product`. Each
contains one row per atom, including H; row order may differ between endpoints.
Each row is `{"atom":[0,1,0],"element":"C","xyz":[0.0,0.0,0.0]}` with:

- `atom: [0, map_id, 0]` for every explicitly mapped atom, including explicit H;
- `atom: [1, parent_map_id, ordinal]` for automatically added H, with ordinal starting
  at 1 for each parent. Prefer mapping every H explicitly when supplying geometries;
- `element` matching the mapped graph and three finite `xyz` coordinates in angstrom.

Both sides must have the same atom keys. Unknown, duplicate or missing keys, incorrect
elements and coincident atoms are rejected before writing output. Supplied coordinates
are not optimized or automatically verified against graph/stereochemical identity.
Check those separately. Multi-fragment orientation is never inferred by the generic
embedding strategy; supply it explicitly instead. These are endpoint seeds, not a
general constraint optimizer; scans and other constraints use explicit solver inputs.

Automatic generation accepts `--conformers 1..8`. Reactant stereochemistry must be
specified. `--enumerate-stereo` can enumerate unspecified product stereochemistry,
up to 16 variants; that cap is reported and does not establish complete coverage.
Malformed inputs fail before output creation; per-branch embedding failures remain
in `candidates.json` for review.

## Execute and retain provenance

Use the Node's returned work_dir (workspace research/work/ before association).
The placeholders below represent actual absolute paths and returned Artifact refs:

```text
"$CORAGENT_PYTHON" -m research_agent.application.executors --config "$CORAGENT_JOB_CONFIG" --environment local --executor chemical.path-candidates --version 1 --input spec=<work_dir>/spec.json --input-artifact <spec-ref> --output <work_dir>/candidates-request.json -- --conformers 1
```

Submit its returned request_file/request_sha256 with node_id through job_start and
collect the terminal Job. Each successful branch contains spec.json, atom_order.json,
reactants.xyz, product.xyz and ts.gjf, with digests. The branch spec binds the input
title through CoRAgentSpec; retain its collected Artifact identity. The Job stages
and pins all helper modules. Generated geometry is not a verified transition state.
For independent fragment assembly or perturbation of a supplied complex, use
`chemical.complex-sample@1`; for CREST and ensemble screening use the
[ensemble contract](../../crest/references/crest_ensemble.md). Exported seeds
need explicit mapping to the endpoint atom keys above and separate refinement;
complex sampling does not establish an elementary step or a TS.
