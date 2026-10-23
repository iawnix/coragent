# Operation entrypoints

Prepare requests through the generic executor and submit with `job_start`. Entry and CLI paths below are relative to this Skill directory; outputs are relative to the Job work directory.

| Executor | Entry | CLI | Input roles | Primary outputs |
| --- | --- | --- | --- | --- |
| `chemical.path-candidates@1` | `scripts/path/prepare_path.py` | `scripts/path/cli.py` | `spec` | `results/candidates.json` |
| `chemical.qst-prepare@1` | `scripts/search/search.py` | `scripts/search/search_cli.py` | `input` | `results/result.json`, `results/ts.gjf` |
| `chemical.search-recovery@1` | `scripts/search/recovery.py` | `scripts/search/recovery_cli.py` | `input` | `results/result.json` |
| `chemical.scan-xtb@1` | `scripts/search/search.py` | `scripts/search/search_cli.py` | `input` | `results/result.json` |
| `chemical.scan-gaussian@1` | `scripts/search/search.py` | `scripts/search/search_cli.py` | `input` | `results/result.json` |
| `chemical.gradient-xtb@1` | `scripts/search/search.py` | `scripts/search/search_cli.py` | `input` | `results/result.json` |
| `chemical.gradient-gaussian@1` | `scripts/backends/gaussian_path.py` | `scripts/search/search_cli.py` | `input` | `results/result.json` |
| `chemical.neb-xtb@2` | `scripts/neb/ase_search.py` | `scripts/neb/ase_cli.py` | `input` | `results/result.json` |
| `chemical.neb-gaussian@2` | `scripts/neb/ase_search.py` | `scripts/neb/ase_cli.py` | `input` | `results/result.json` |

Read the applicable operation contract below for input formats, required arguments, scientific checks and recovery:

- [ase neb executor](ase_neb_executor.md)
- [candidate generation](candidate_generation.md)
- [path preparation](path_preparation.md)
- [path search](path_search.md)
- [reaction task interface](reaction_task_interface.md)
- [script layout](script_layout.md)

Use the table’s executor ID and version for `--executor` and `--version`, and actual roles for `--input role=path`. The execution target is inherited from the task; domain Skills omit `--platform` / `--scheduler-entry`. Consult that executor’s `--help` only for options absent from its contract.

For preparation failures, correct inputs, arguments or software bindings first; successful preparation has not executed the calculation. Reconcile the existing Job and receipt after an uncertain submission. Collect available outputs after calculation failure and use the operation contract to decide whether to retry; failed outputs are not validated results.
