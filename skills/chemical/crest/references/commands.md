# Operation entrypoints

Prepare requests through the generic executor and submit with `job_start`. Entry and CLI paths below are relative to this Skill directory; outputs are relative to the Job work directory.

| Executor | Entry | CLI | Input roles | Primary outputs |
| --- | --- | --- | --- | --- |
| `chemical.crest-ensemble@1` | `scripts/ensemble.py` | `scripts/ensemble_cli.py` | `material`, `run` | `results/result.json`, `results/refinement.json` |
| `chemical.ensemble-select@1` | `scripts/ensemble.py` | `scripts/ensemble_cli.py` | `ensemble` | `results/result.json`, `results/refinement.json` |
| `chemical.complex-sample@1` | `scripts/ensemble.py` | `scripts/ensemble_cli.py` | `input` | `results/result.json`, `results/refinement.json` |
| `chemical.crest@1` | `scripts/crest_run.py` | `scripts/crest_cli.py` | `material` | `results/result.json`, `results/crest.out`, `results/crest_conformers.xyz`, `results/crest_best.xyz`, `results/crest.energies` |

Read the applicable operation contract below for input formats, required arguments, scientific checks and recovery:

- [crest backend contract](crest_backend_contract.md)
- [crest ensemble](crest_ensemble.md)

Use the table’s executor ID and version for `--executor` and `--version`, and actual roles for `--input role=path`. The execution target is inherited from the task; domain Skills omit `--platform` / `--scheduler-entry`. Consult that executor’s `--help` only for options absent from its contract.

For preparation failures, correct inputs, arguments or software bindings first; successful preparation has not executed the calculation. Reconcile the existing Job and receipt after an uncertain submission. Collect available outputs after calculation failure and use the operation contract to decide whether to retry; failed outputs are not validated results.

For `primary.parsing_status=limited`, use `scripts/crest_io.py` with `--directory`,
`--material`, `--run`, `--max-members` and a new `--output` file, as described in
[reparse retained outputs](crest_ensemble.md#reparse-retained-outputs). This is pure
parsing of collected evidence, not a new executor or another native search.
