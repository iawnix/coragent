# Preparing a scientific Job request

Start from the method Skill's instructions and selected software binding. When it supplies a predefined recipe, prepare it with `--config "$CORAGENT_JOB_CONFIG" --target <name> --executor <id> --version <version> --input <role>=<file>`, followed by `--` and runner arguments. The generic preparer stages declared resources with their module paths intact. Target Python comes from the backend or environment binding in job.toml.

For runner parameters, use `"$CORAGENT_PYTHON" -m research_agent.application.executors --executor <id> --version <version> --help`. This reads the pinned CLI contract without running science or contacting a compute target. Fixed input/output/executable flags are supplied by the preparer.

If the recipe id is unknown, `executors --list --skill <name>` or `--list --backend <binding>` gives a concise index; `--details` includes full descriptors for diagnostics. This index covers predefined recipes, not all available methods or software. Optional `--config … --target …` reports whether each recipe's binding is configured, without probing it. Check actual software with the [targeted environment check](runtime_environment.md). An absent recipe can use the task-specific script path below or a native command through a generic Job.

Preserve the prepared request_id when recovering the same submission. A lost tool response does not authorize a new ID; intentional recalculation uses a new request.

For XYZ calculations use `chemical.cf22d`, `chemical.xtb` or `chemical.gaussian`, version `1`, with `--input geometry=<file>`. For explicit Gaussian input use `chemical.gaussian-input`, version `1`, with `--input input=<file>`.
Use `--dependency /absolute/source.chk=previous.chk` for each input checkpoint or
included file; the destination must match the relative reference in the `.gjf`.
Use `--collect results/ts.chk` to require a reusable checkpoint in the collected results.
These options precede `--`; runner options such as `--validation saddle` or
`--validation irc` follow it, without `--task`. Input format, dependency contents,
collected outputs and runner resources participate in the generated request identity.
This helper only packages the requested calculation; the Agent selects the sequence
and interprets numerical checks using the Gaussian Skill.

Python dependencies are installation-owned Conda environments configured in job.toml. Run preparation helpers with "$CORAGENT_PYTHON"; target runners use the resolved Conda binding. Missing environments require installation maintenance, not ad-hoc pip installs during a research turn.


Use the research Node’s returned `work_dir` for task scripts and prepared requests.
Save helper output with `--output <work_dir>/<cell>.json` (before `--`).
The helper prints `request_file` and `request_sha256`; pass these unchanged to
`job_start`, adding only optional `timeout_seconds`. Do not copy
individual command/input fields. Inspect the file if needed; changing it requires
recomputing its digest. Repeated preparation of identical inputs/configuration
preserves work_id/request_id. Use `--work-id` only for intentional new work.

For a task-specific Python method, use `--script <file.py> --backend <binding>`
instead of executor/version, with `--dependency <source>=<destination>` and
`--collect <relative-output>` as needed. The script and dependencies are pinned
and execute in the selected Python binding. Use `--input-artifact <id-or-ref>`
for registered inputs: Runtime checks that their exact bytes are actually staged
and carries their provenance into collected outputs.

For example, a local RDKit script uses the configured `structure` backend:

```bash
"$CORAGENT_PYTHON" -m research_agent.application.executors \
  --config "$CORAGENT_JOB_CONFIG" \
  --script <work_dir>/analysis.py --backend structure \
  --collect analysis.json --output <work_dir>/analysis-request.json
```

The script must actually write `analysis.json` relative to its Job cwd. Submit the
returned `request_file` and `request_sha256` with the intended `node_id` to
`job_start`. `--collect`/`outputs` declare collection; they do not create files or
redirect stdout. `print()` is captured in `logs/stdout.log`, not `stdout.txt`.
`platform=local` selects the target only; a direct `bash -lc "python ..."` command
does not resolve the `structure` backend. For other libraries or remote execution,
choose the corresponding configured backend and environment.

Remote preparation requires an explicit `submission.queue` in the environment
or backend's job.toml table. `submission.resources` supplies CPU/memory/walltime;
backend fields override environment defaults. An allowlist does not choose a
queue. Missing queue configuration needs installation maintenance. Inspect
job_status diagnostics when a queue-wait event arrives; no exit receipt while
queued/running is normal. Do not resubmit or change queues without reconciling
the original Job. An optional `submission.queue_wait_seconds` causes one Monitor
notification when that waiting threshold is exceeded.

The preparation helper validates forwarded arguments against the same pure CLI parser used by the selected runner, before writing a request. Unknown arguments and attempts to override managed input/output/executable paths are rejected. GFN2-xTB is fixed by its runner; do not add --method. Preparation checks the declared arguments and target dependencies. A completed scientific Job is still needed to establish that the method works on the requested input.
