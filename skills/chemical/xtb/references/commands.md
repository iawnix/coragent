# Operation entrypoints

Prepare requests through the generic executor and submit with `job_start`. Entry and CLI paths below are relative to this Skill directory; outputs are relative to the Job work directory.

| Executor | Entry | CLI | Input roles | Primary outputs |
| --- | --- | --- | --- | --- |
| `chemical.xtb@1` | `scripts/run.py` | `scripts/cli.py` | `geometry` | `results/result.json`, `results/geometry.xyz` |

Read the applicable operation contract below for input formats, required arguments, scientific checks and recovery:

- [xtb backend contract](xtb_backend_contract.md)
- [xtb executor](xtb_executor.md)

Use the table’s executor ID and version for `--executor` and `--version`, and actual roles for `--input role=path`. The execution target is inherited from the task; domain Skills omit `--target`. Consult that executor’s `--help` only for options absent from its contract.

For preparation failures, correct inputs, arguments or software bindings first; successful preparation has not executed the calculation. Reconcile the existing Job and receipt after an uncertain submission. Collect available outputs after calculation failure and use the operation contract to decide whether to retry; failed outputs are not validated results.
