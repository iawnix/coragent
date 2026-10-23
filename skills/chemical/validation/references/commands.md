# Operation entrypoints

Prepare requests through the generic executor and submit with `job_start`. Entry and CLI paths below are relative to this Skill directory; outputs are relative to the Job work directory.

| Executor | Entry | CLI | Input roles | Primary outputs |
| --- | --- | --- | --- | --- |
| `chemical.path-irc@1` | `scripts/irc_preparation.py` | `scripts/irc_preparation_cli.py` | `spec`, `checkpoint` | `results/irc_inputs.json` |
| `chemical.stationary-check@1` | `scripts/evidence_check.py` | `scripts/check_cli.py` | `material`, `evidence` | `results/result.json` |
| `chemical.mode-check@1` | `scripts/evidence_check.py` | `scripts/check_cli.py` | `material`, `evidence`, `coordinates` | `results/result.json` |
| `chemical.irc-check@1` | `scripts/evidence_check.py` | `scripts/check_cli.py` | `material`, `evidence`, `forward`, `reverse`, `reactant`, `product` | `results/result.json` |
| `chemical.ts-connectivity-inputs@1` | `scripts/connectivity.py` | `scripts/connectivity_cli.py` | `material`, `log`, `coordinates` | `results/connectivity_inputs.json`, `results/ts_source.json`, `results/*.gjf` |
| `chemical.displacement-check@1` | `scripts/connectivity.py` | `scripts/connectivity_cli.py` | `material`, `evidence`, `coordinates`, `study`, `reactant`, `product` | `results/result.json` |
| `chemical.gaussian-evidence@1` | `scripts/evidence_check.py` | `scripts/check_cli.py` | `material`, `evidence` | `results/result.json` |

Read the applicable operation contract below for input formats, required arguments, scientific checks and recovery:

- [connectivity validation](connectivity_validation.md)
- [gaussian validation](gaussian_validation.md)
- [general checks](general_checks.md)
- [irc preparation](irc_preparation.md)
- [irc validation](irc_validation.md)
- [structure validation](structure_validation.md)
- [transition state validation](transition_state_validation.md)

Use the table’s executor ID and version for `--executor` and `--version`, and actual roles for `--input role=path`. The execution target is inherited from the task; domain Skills omit `--platform` / `--scheduler-entry`. Consult that executor’s `--help` only for options absent from its contract.

For preparation failures, correct inputs, arguments or software bindings first; successful preparation has not executed the calculation. Reconcile the existing Job and receipt after an uncertain submission. Collect available outputs after calculation failure and use the operation contract to decide whether to retry; failed outputs are not validated results.

- [TS connectivity probes](ts_connectivity.md)
