# Crossing execution contracts

`chemical.mecp-gaussian@1` consumes `chemical-mecp-input/1` with `material`,
`multiplicities` (two distinct valid integers), and `settings` from
[Gaussian electronic calculations](../../gaussian/references/electronic_states.md),
with `theory:ground`. Optional controls are `max_steps` (0–1000, default 100),
`max_evaluations` (1–10000, default 500), `step_size` (default 0.2 Å²/Eh),
`max_displacement_angstrom` (default 0.1, maximum 1),
`gap_tolerance_hartree` (default 1e-5), `gradient_tolerance` (default 1e-4 Eh/Å),
and `hessian_step_angstrom` (null by default; 1e-4–0.01 when requested).

The selected bundled NumPy algorithm is capped projected mean-energy descent
with a first-order Newton gap correction. For d=∇EA−∇EB, g=(∇EA+∇EB)/2,
λ=(g·d)/(d·d), use g_parallel=g−λd and
Δx=−αg_parallel−(EA−EB)d/(d·d), capped by maximum per-atom displacement.
A singular gradient difference is refused. Both surfaces use the same functional,
basis, gas-phase model, atom order and geometry. Each gradient comes from an
independent bounded Gaussian process. Budget includes Hessian evaluations.

Results retain evaluated iterations, source hashes, the latest fully evaluated
candidate pair, numerical checks and failures. Unknown jobs are not automatically
resubmitted or resumed. Iteration exhaustion, failed surfaces and Hessian budget
exhaustion fail the Job while retaining partial result JSON. Raw native outputs
are recursively collected. No frequency/IRC fallback is used.

`chemical.crossing-check@1` consumes `chemical-crossing-check-input/1` containing
`materials` and `surfaces` (two each), with the same optional gap/gradient
thresholds and optional `curvature_tolerance` (default 1e-5 Eh/Å²). Surface
contracts are `chemical-electronic-evaluation/1` from the electronic adapter,
with original-axis Cartesian dE/dR in Eh/Å. Spin, method, geometry (2e-6 Å printed
precision), atom order and units are checked before projection.

The checker separates energy-gap closure, projected-gradient stationarity and
curvature. Optional `final.hessian_hartree_per_angstrom2` matrices need
`hessian_provenance` on each surface. The Lagrangian Hessian is
(HA+HB)/2−λ(HA−HB). Its tangent-space spectrum excludes translations, rotations
and the regular seam normal. Negative curvature fails the constrained-minimum
check; unresolved flat modes remain inconclusive. Missing Hessians establish
only numerical stationarity. The search can obtain both Hessians by central
differences of Gaussian gradients at the requested step and preserves all
sample digests. Displacement-size sensitivity is not automatically assessed.

`status:converged` means the requested gap/projected-gradient thresholds were
met, with curvature reported separately. `numerical_mecp_conditions` is true
only with passing seam curvature; inspect it independently of Job success.
`validated_global_mecp` is always false. Acceptable S² and declared multiplicities
do not establish wavefunction stability, branch identity or the global lowest
crossing. The solver is a finite local search, without quasi-Newton trust-region
updates, automatic restarts, SOC or transition probabilities.

Selection evidence: local Gaussian 16 A.03 is available; no local QBICS/MECP
installation was found during implementation. A bundled, inspectable numerical
solver and Gaussian adapter were selected instead of inventing a QBICS CLI.
Validation consists of analytic crossing potentials, synthetic derivative/log
contracts and local Job tests, not a physical Gaussian crossing benchmark.
