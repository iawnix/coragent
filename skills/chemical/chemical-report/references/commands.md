# Operation entrypoints

Prepare requests through the generic executor and submit with `job_start`. Entry and CLI paths below are relative to this Skill directory; outputs are relative to the Job work directory.

| Executor | Entry | CLI | Input roles | Primary outputs |
| --- | --- | --- | --- | --- |
| `chemical.render@1` | `scripts/render.py` | `scripts/render_cli.py` | `geometry` | `results/render/geometry.svg`, `results/render/geometry.png`, `results/render/render.json` |
| `chemical.trajectory@1` | `scripts/research_job.py` | `scripts/research_cli.py` | `input` | `results/result.json` |
| `chemical.research-report@1` | `scripts/research_job.py` | `scripts/research_cli.py` | `input` | `results/result.json` |

Read the applicable operation contract below for input formats, required arguments, scientific checks and recovery:

- [illustrated report](illustrated_report.md)
- [report email delivery](report_email_delivery.md)
- [research tools](research_tools.md)

Use the table’s executor ID and version for `--executor` and `--version`, and actual roles for `--input role=path`. The execution target is inherited from the task; domain Skills omit `--platform` / `--scheduler-entry`. Consult that executor’s `--help` only for options absent from its contract.

For preparation failures, correct inputs, arguments or software bindings first; successful preparation has not executed the calculation. Reconcile the existing Job and receipt after an uncertain submission. Collect available outputs after calculation failure and use the operation contract to decide whether to retry; failed outputs are not validated results.
