# Operation entrypoints

Prepare requests through the generic executor and submit with `job_start`. Entry and CLI paths below are relative to this Skill directory; outputs are relative to the Job work directory.

| Executor | Entry | CLI | Input roles | Primary outputs |
| --- | --- | --- | --- | --- |
| `chemical.resolve@1` | `scripts/reaction/prepare.py` | `scripts/reaction/cli.py` | — | `results/resolve.json` |
| `chemical.resolve-candidates@1` | `scripts/reaction/prepare.py` | `scripts/reaction/cli.py` | `candidates` | `results/resolve.json` |
| `chemical.inspect@1` | `scripts/reaction/prepare.py` | `scripts/reaction/cli.py` | — | `results/inspect.json` |
| `chemical.seed@1` | `scripts/reaction/prepare.py` | `scripts/reaction/cli.py` | — | `results/seed.json` |
| `chemical.reaction@1` | `scripts/reaction/prepare.py` | `scripts/reaction/cli.py` | — | `results/reaction.json` |
| `chemical.compare@1` | `scripts/reaction/prepare.py` | `scripts/reaction/cli.py` | `target`, `actual` | `results/comparison.json` |
| `chemical.material@1` | `scripts/materials/material.py` | `scripts/materials/material_cli.py` | `material` | `results/material.json`, `results/atom_order.json`, `results/source.txt`, `results/geometry.xyz` |
| `chemical.map-candidates@1` | `scripts/geometry/analysis.py` | `scripts/geometry/analysis_cli.py` | `left`, `right` | `results/result.json` |
| `chemical.conformer-compare@1` | `scripts/geometry/analysis.py` | `scripts/geometry/analysis_cli.py` | `left`, `right` | `results/result.json` |
| `chemical.reorder-tensors@1` | `scripts/geometry/analysis.py` | `scripts/geometry/analysis_cli.py` | `tensors`, `order` | `results/result.json` |
| `chemical.local-diagnostics@1` | `scripts/diagnostics/diagnostics_job.py` | `scripts/diagnostics/diagnostics_cli.py` | `input` | `results/result.json` |

Read the applicable operation contract below for input formats, required arguments, scientific checks and recovery:

- [local diagnostics](local_diagnostics.md)
- [material input](material_input.md)
- [name resolution](name_resolution.md)
- [reaction mapping](reaction_mapping.md)
- [script layout](script_layout.md)
- [structure analysis](structure_analysis.md)
- [structure input](structure_input.md)

Use the table’s executor ID and version for `--executor` and `--version`, and actual roles for `--input role=path`. The execution target is inherited from the task; domain Skills omit `--platform` / `--scheduler-entry`. Consult that executor’s `--help` only for options absent from its contract.

For preparation failures, correct inputs, arguments or software bindings first; successful preparation has not executed the calculation. Reconcile the existing Job and receipt after an uncertain submission. Collect available outputs after calculation failure and use the operation contract to decide whether to retry; failed outputs are not validated results.
