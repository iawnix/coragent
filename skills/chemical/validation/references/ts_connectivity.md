# Bound TS probes and short IRC

Use `chemical.ts-connectivity-inputs@1` with `material` (the **optimized saddle**, fixed atom order), `log` (its Gaussian Opt+Freq output), and `coordinates` (`chemical-mode-coordinates/1`, as in general checks). The generator recomputes stationary and target-mode checks. A guessed TS, unsupported electronic surface, parser conflict, or wrong geometry cannot generate a certified source bundle.

The default output is four `Opt=(Tight,MaxCycles=100) Freq` inputs: ±0.05 and ±0.10 Å, normalized by **maximum atom displacement**, plus forward/reverse `IRC=(...,CalcFC,MaxPoints=20,StepSize=5)` inputs at the original optimized TS. `--amplitudes`, `--max-points`, `--step-size`, `--threads` and `--memory-mb` are configurable. Gaussian StepSize must be a nonzero integer, including its documented signed unit convention; 0.5 is invalid. Prepare inputs only; no calculations are submitted automatically.

Submit selected GJFs using `chemical.gaussian-input@1` explicit input mode and matching method/basis/state/resources. Stage `ts_source.json` beside each GJF using `--dependency /absolute/ts_source.json=ts_source.json`. Use the exact per-input `collect` paths from `connectivity_inputs.json`; these are derived from the same `%chk` declaration. The runner verifies the bundle digest and input bytes before launch and checks the first output geometry afterwards. Editing a bound input requires regeneration. Generic unbound Gaussian inputs remain available, but carry no TS source certification.

Run the displacement optimizations first. Adapt their logs to minimum evidence with `chemical.gaussian-evidence`, using each optimized endpoint's material and an explicit unconstrained declaration. Pass `material`, source `evidence`, mode `coordinates`, `reactant`, `product` and a `study` to `chemical.displacement-check@1`. The study has this shape (endpoint contracts are identical to general IRC checks):

```json
{
  "schema_version": "chemical-displacement-study/1",
  "branches": [
    {"direction": "plus", "amplitude_angstrom": 0.05,
     "endpoint": {"material": {}, "minimum_evidence": {}}},
    {"direction": "minus", "amplitude_angstrom": 0.05,
     "endpoint": {"material": {}, "minimum_evidence": {}}}
  ]
}
```

Supply both signs for each amplitude. Each minimum must have bound `optimization.start_coordinates` matching its recomputed displacement. Atom order, electronic state, method/basis, unconstrained minimum convergence, frequency signature and geometry-derived chemical identity are checked. Direction labels may swap R/P. Multiple amplitudes must agree; same-basin or amplitude-sensitive results are inconclusive. One amplitude is allowed but reports that amplitude sensitivity was not assessed.

For important paths or ambiguous displacement outcomes, run the two prepared short IRC inputs. Optimize each **last accepted IRC point**, not the TS seed or a failed corrector's trial geometry. Adapt each optimization and attach it to that IRC evidence's `endpoint`. Run `chemical.irc-check@1 --policy endpoint_relaxation`. This permits a normally terminated MaxPoints-limited path only when both paths descend from the bound saddle and exact endpoint-start linkage and opposite R/P minimum assignments pass. Default `--policy strict` still requires completed paths without hitting MaxPoints. Error-terminated paths retain points for diagnosis and recovery but cannot pass these policies. A restart segment alone cannot prove TS origin: provide a properly stitched and reviewed path.

Evidence levels are `mode_displacement_endpoint_support`, `short_irc_with_endpoint_optimization`, and `complete_irc`. A successful numerical parse, cclib `optdone`, or Gaussian normal termination proves none of these by itself. Ordinary minimization can bypass shallow intermediates; displacement support is not an IRC or mechanism-uniqueness proof.

The generator currently supports self-contained method/basis inputs and uses CalcFC at explicit verified coordinates. Additional solvent, dispersion, external basis/ECP or other model settings require explicit support; detected unsupported settings are rejected rather than dropped. Binary checkpoint Hessian reuse is not certified by this workflow. Existing checkpoint-based helpers do not gain source certification automatically.

Recovery is bounded workflow guidance, not an automatic retry scheduler: inspect endpoints at the first MaxPoints limit, allow at most three reasoned attempts per branch, and record the changed parameter/evidence. Do not repeat identical input except after a documented external execution failure. Fix syntax before submission; review parser conflicts against raw output before deciding whether any calculation is needed. Reconcile an uncertain Job receipt before resubmitting. Extend IRC only if endpoint inspection/optimization remains insufficient.
