# Operation entrypoints

Prepare requests through the generic executor and submit with `job_start`. Entry and CLI paths below are relative to this Skill directory; outputs are relative to the Job work directory.

| Executor | Entry | CLI | Input roles | Primary outputs |
| --- | --- | --- | --- | --- |
| `chemical.cf22d@1` | `scripts/run.py` | `scripts/cli.py` | `geometry` | `results/result.json`, `results/geometry.xyz` |
| `chemical.cf22d-doctor@1` | `scripts/doctor.py` | — | — | stdout |

Read the applicable operation contract below for input formats, required arguments, scientific checks and recovery:

- [cf22d workflow](cf22d_workflow.md)
- [environment doctor](environment_doctor.md)

Use the table’s executor ID and version for `--executor` and `--version`, and actual roles for `--input role=path`. The execution target is inherited from the task; domain Skills omit `--target`. Consult that executor’s `--help` only for options absent from its contract.

For preparation failures, correct inputs, arguments or software bindings first; successful preparation has not executed the calculation. Reconcile the existing Job and receipt after an uncertain submission. Collect available outputs after calculation failure and use the operation contract to decide whether to retry; failed outputs are not validated results.
