# Operation entrypoints

Prepare requests through the generic executor and submit with `job_start`. Entry and CLI paths below are relative to this Skill directory; outputs are relative to the Job work directory.

| Executor | Entry | CLI | Input roles | Primary outputs |
| --- | --- | --- | --- | --- |
| `chemical.thermochemistry@1` | `scripts/energy.py` | `scripts/energy_cli.py` | `input` | `results/result.json`, `results/table.csv` |
| `chemical.ensemble-free-energy@1` | `scripts/energy.py` | `scripts/energy_cli.py` | `input` | `results/result.json`, `results/table.csv` |
| `chemical.energy-profile@1` | `scripts/energy.py` | `scripts/energy_cli.py` | `input` | `results/result.json`, `results/table.csv` |
| `chemical.scan-slice@1` | `scripts/energy.py` | `scripts/energy_cli.py` | `input` | `results/result.json`, `results/table.csv` |
| `chemical.tst@1` | `scripts/energy.py` | `scripts/energy_cli.py` | `input` | `results/result.json`, `results/table.csv` |
| `chemical.branching@1` | `scripts/energy.py` | `scripts/energy_cli.py` | `input` | `results/result.json`, `results/table.csv` |
| `chemical.kinetic-network@1` | `scripts/energy.py` | `scripts/energy_cli.py` | `input` | `results/result.json`, `results/table.csv` |

Read the applicable operation contract below for input formats, required arguments, scientific checks and recovery:

- [energetics](energetics.md)
- [energy execution](energy_execution.md)
- [kinetics execution](kinetics_execution.md)

Use the table’s executor ID and version for `--executor` and `--version`, and actual roles for `--input role=path`. The execution target is inherited from the task; domain Skills omit `--target`. Consult that executor’s `--help` only for options absent from its contract.

For preparation failures, correct inputs, arguments or software bindings first; successful preparation has not executed the calculation. Reconcile the existing Job and receipt after an uncertain submission. Collect available outputs after calculation failure and use the operation contract to decide whether to retry; failed outputs are not validated results.
