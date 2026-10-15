# Optional helper: mapped Diels–Alder seeds

This reference documents the optional DA geometry strategy and its existing
specialized validators. The general [mapped path preparer](path_preparation.md)
accepts explicit transformations and supplied endpoint geometries without a named
reaction recipe. DA construction is isolated in `../scripts/da_geometry.py`;
`prepare_path.py` selects it for legacy diels_alder specs. Its scientific acceptance
profile remains DA-specific and does not validate unrelated generic preparations.

This strategy implements bounded candidate preparation for explicit neutral-carbon
Diels–Alder topology, mapped reactant/product seeds and Gaussian QST2+Freq. IRC input
preparation and evidence are handled separately by `validation`. It supports closed-shell
singlets without isotope-specific masses. Specify reactant stereochemistry;
unspecified product stereochemistry can be enumerated, at most 16 variants.
This path does not implement NEB, exhaustive conformer search or complete mechanism discovery.

Create and register a `chemical-path-spec/1` JSON artifact, for example:

```json
{
  "schema_version": "chemical-path-spec/1",
  "mapped_smiles": "[CH2:1]=[CH:2][CH:3]=[CH2:4].[CH2:5]=[CH:6][CH3:7]>>[CH2:1]1[CH:2]=[CH:3][CH2:4][CH2:5][CH:6]1[CH3:7]",
  "transformation": {
    "kind": "diels_alder",
    "diene": [1, 2, 3, 4], "dienophile": [5, 6],
    "forming_bonds": [[1, 6], [4, 5]]
  },
  "method": "M062X", "basis": "6-31G**", "charge": 0,
  "multiplicity": 1, "threads": 12, "memory_mb": 4000
}
```

Use the actual listed Skill paths; replace <work_dir> with the Node draft directory returned by research_create/research_read (workspace research/work/ before association):

```text
"$CORAGENT_PYTHON" -m research_agent.application.executors --config "$CORAGENT_JOB_CONFIG" --environment local --executor chemical.path-candidates --version 1 --input spec=<work_dir>/spec.json --input-artifact <spec-ref> --output <work_dir>/candidates-request.json -- --enumerate-stereo --conformers 2
```

Submit the returned request_file/request_sha256 and collect the Job before inspecting candidates. The entry uses the target structure binding; all generated files are collected with Job provenance.

`candidates.json` lists every prepared or failed branch. Each successful branch
contains `spec.json`, `atom_order.json`, `reactants.xyz`, `product.xyz` and `ts.gjf`
with hashes. The helper embeds product conformers, constructs an s-cis diene and
aligns/separates reactant fragments while retaining atom correspondence. These
are unoptimized endpoint seeds. Keep failed branches and inspect the inputs;
QST2 convergence and completeness of the finite candidate set are not guaranteed.
Register each selected branch's spec and geometries. The branch spec is the subject
of the `chemical.diels_alder_path@1` acceptance profile; evidence for different
spec artifacts cannot be mixed to satisfy one path.
The generated `CoRAgentSpec` title binds the solver output to the branch spec digest.
Keep that title in the TS input and checkpoint; validation binds later evidence to the same branch artifact.

Prepare a TS request with the existing method-selection helper:

```text
"$CORAGENT_PYTHON" -m research_agent.application.executors --config <installation>/job.toml --environment local --executor chemical.gaussian-input --version 1 --input input=<branch>/ts.gjf --collect results/ts.chk --output <work_dir>/ts-request.json -- --method M062X --basis '6-31G**' --threads 12 --memory-mb 4000 --validation saddle
```

Submit the returned `request_file` and `request_sha256` through `job_start`.
Collect the terminal Job. A successful runner is not a scientific verdict:
validate the raw collected `gaussian.out` with the registered saddle validator.
Inspect the checks and their scope before choosing the next experiment.

IRC preparation and bidirectional path validation are owned by `validation`; see [IRC input preparation](../../validation/references/irc_preparation.md) and [IRC validation](../../validation/references/irc_validation.md).
