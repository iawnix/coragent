---
name: gaussian
description: Prepare and execute Gaussian XYZ or explicit input jobs, parse native logs, and preserve route, state, energy, gradient, and frequency evidence.
---

# Gaussian backend

[Chinese version](SKILL.zh-CN.md)

## Script routing

Select the executor in [Operation entrypoints](references/commands.md), then read the matching input and validation contract in this Skill. Ordinary invocation does not require source inspection; unlisted files under `scripts/` are internal helpers.

Use this Skill when Gaussian is the chosen backend for optimization, single point, QST/TS, frequency, IRC, relaxed scan, electronic-state tracking, or final log evidence. It handles route construction, staged files, native execution, and parsing; the operation Skill defines the scientific question and acceptance criteria.

## Registered adapters

- `chemical.gaussian@1`: XYZ shortcut for `sp`, `opt`, and `opt-sp`.
- `chemical.gaussian-input@1`: complete `.gjf`/`.com` input for QST, TS, frequency, IRC, scans, and Link1 jobs.
- `chemical.electronic-gaussian@1`: bound-state `sp`/`opt` and electronic evidence.
- `chemical.state-tracking@1`: state-character tracking from declared electronic inputs.
- `chemical.gaussian-evidence@1`: normalized raw-log sections used by validation.

The path-specific gradient and NEB adapters live in `candidate-generation`; Gaussian saddle and IRC checks live in `validation`.

## XYZ shortcut

```bash
"$CORAGENT_PYTHON" -m research_agent.application.executors --config "$CORAGENT_JOB_CONFIG" --executor chemical.gaussian --version 1 --input geometry=input.xyz --cpus 12 --job-memory-mb 16384 --output prepared/gaussian.json -- --task opt-sp --method M062X --basis '6-31G**' --charge 0 --multiplicity 1
```

Use `opt` for geometry, `sp` for a fixed geometry, and `opt-sp` for both. The wrapper records energies, convergence, optimized geometry, method/basis, state, raw log, and parser summary.

Read `summary.optimization_completed` with `optimization_completion_reason` for optimization status. The parser accepts Gaussian's explicit negligible-force completion while preserving the original four convergence rows and the stricter `final_convergence_satisfied` flag. After a failed attempt, use `result.json.last_attempt` and `last_geometry.xyz` to inspect the last structure and choose a restart; frequency, mode and IRC checks provide the subsequent evidence.

## Explicit input

Stage a complete input and relative checkpoint/dependency names inside the Job:

```bash
"$CORAGENT_PYTHON" -m research_agent.application.executors --config "$CORAGENT_JOB_CONFIG" --executor chemical.gaussian-input --version 1 --input input=ts.gjf --collect results/ts.chk --output prepared/ts.json -- --method M062X --basis '6-31G**' --charge 0 --multiplicity 1 --validation none
```

Use `--validation opt|sp|frequency|minimum|saddle|irc` when the input is intended for a parser check. Keep the final blank section terminator and complete Link1 metadata. Submit prepared requests with `job_start`, then inspect `gaussian.out`, `parsed.json`, checkpoint, geometry, and validation fields.

Read [L101 input guide](references/l101_input_guide.md), [electronic states](references/electronic_states.md), [relaxed scans](references/relaxed_scans.md), and [Gaussian validation](references/gaussian_validation.md) for route and parser details.

Resource settings belong to the Job: preparer `--cpus 12 --job-memory-mb 16384` requests 12 CPUs and 16 GiB total. Omitted runner threads follow that allocation; Gaussian `%mem` leaves the greater of 256 MiB or 10% for overhead (14745 MiB here). Explicit GJF `%nprocshared`/`%mem` are read at preparation and are never rewritten. Without job overrides they supply requirements; with overrides, conflicting threads or insufficient total memory fail before submission. Re-prepare to change resources. Defaults are not hardware limits.
