# IRC input preparation

IRC input preparation belongs to transition-state validation: it prepares forward and reverse inputs from a validated saddle checkpoint; it does not generate candidates or certify the saddle.

Run a selected ts.gjf with `chemical.gaussian-input@1`, collecting `results/ts.chk`;
use the same method/basis/state/resources and `--validation saddle`. Inspect the raw
output and mode evidence before preparing IRC from the collected checkpoint:

```text
"$CORAGENT_PYTHON" -m research_agent.application.executors --config "$CORAGENT_JOB_CONFIG" --executor chemical.path-irc --version 1 --input spec=<branch-spec.json> --input checkpoint=<collected-ts.chk> --input-artifact <branch-spec-ref> --input-artifact <checkpoint-ref> --output <work_dir>/irc-request.json -- --max-points 80
```

IRC preparation supports the same explicit transformation contract regardless of
endpoint geometry strategy. It retains checkpoint bytes and digest and writes
forward.gjf/reverse.gjf with CalcFC and Geom=AllCheck, recalculating the Hessian at
the checkpoint geometry. It does not parse the binary checkpoint: verify its atom
order, method, charge/spin and producer evidence; it does not reuse a stored Hessian.
Submit and collect the preparation Job, then run each generated input using the
Gaussian Skill, staging ts.chk and selecting `--validation irc`.

Analyze the collected paths with `chemical.gaussian-evidence@1` and `chemical.irc-check@1`, using the selected source saddle and mapped endpoint materials. See [general checks](general_checks.md).
