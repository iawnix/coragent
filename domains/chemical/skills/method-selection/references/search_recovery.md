# Search diagnosis and recovery

[中文](search_recovery.zh-CN.md)

Use collected primary evidence to distinguish execution, numerical and chemical
failures. Preserve the original request/log/checkpoint and explain the changed
hypothesis or setting in a new immutable Job. Reconcile running/unknown jobs before
resubmission. Independent hypotheses may run in parallel within the budget; no
fixed failure count, mandatory phase sequence or reaction-specific state machine
is needed. Record observations and next decisions in the existing research Node.

| Observation | Inspect first | Evidence-directed response |
| --- | --- | --- |
| Import/executable/license/queue/transport failure | Selected binding, activation, paths, stderr, scheduler and Job state | Repair that execution route; do not infer a chemical failure or silently change method |
| Route/output mismatch | Actual staged input and echoed route, linked sections, checkpoint state, effective method/basis | Correct preparation/parser scope; random coordinate perturbation cannot repair a route mismatch |
| SCF nonconvergence or unstable state | Short contacts, charge/spin, orbital occupation, energy/S² trend and available stability/character diagnostics | Use suitable initial orbitals, damping or solver options, or revise electronic method with reasons; convergence alone is not state continuity |
| Geometry/TS optimizer stalls | Last accepted coordinates, force/displacement trends, trust radius, Hessian age and reaction-center distortion | Consider a fresh Hessian, smaller trust radius, alternate internal/Cartesian coordinates or a justified integration grid; change a diagnosed cause, not every setting at once |
| Extra/small imaginary modes | Actual displacement vectors, optimization thresholds, loose fragments/torsions, grid and rotational/translational contamination | Tighten/recompute when numerical; sample conformers or revise the seed when chemically different; do not delete modes to satisfy a count |
| NEB spikes, bunching or severe bends | Per-image energies/forces, collisions, mapping, endpoints, spectator motion and multiple basins | Revise images/IDPP, image density or conformer/step hypothesis; more steps cannot fix a wrong map |
| IRC stops early | Integration termination, point budget, step size, force trend and final geometry | Continue/recompute with a justified step/Hessian policy; optimize endpoints before calling a finite path disconnected |
| Both IRC directions reach one basin | Confirm sufficient paths, mode displacement and TS identity first | Inspect displacement direction/size and candidate character; repeated complete same-basin evidence should revise the candidate or elementary-step hypothesis |
| Parser rejects a terminated run | Raw method/section, units, atom order, final geometry and unsupported quantities | Preserve raw data and use a verified adapter; normal termination does not make an earlier SCF value the target energy |

## Reusing interrupted calculations

A checkpoint can contain geometry, orbitals and force constants, but its existence
does not prove compatibility or completion. Check its atom order, charge/spin,
method and producing section before staged reuse. Fresh Hessians cost evaluations;
include them in the budget. Do not run unknown duplicate jobs or overwrite history.

Choose a failed-search frame using finite forces, plausible local geometry,
reaction-coordinate progress and electronic consistency. A TS optimizer is a
saddle search: its lowest-energy frame may have fallen into a minimum and is not
a default restart choice. Keep frame identity and the reason for selection.
NEB restart images must come from collected, reviewed paired geometry/energy
records; v2 does not automatically restore FIRE/BFGS state.

## Local chemical diagnosis

Inspect desired and undesired proton transfer, short contacts, fragment collapse,
steric approach, spectator participation, and angle/torsion changes. Use explicit
atom IDs and an appropriate local alignment; global RMSD can hide a moved reaction
center, while a local alignment may expose displaced spectators. The
[local diagnostics](../../chemical-input/references/local_diagnostics.md) report
geometry only. Bond orders, charges, spin density and orbital character require
separate electronic evidence; covalent-radius thresholds are not bond or mechanism
proof. Watch trajectories with the [report tools](../../report/references/research_tools.md).

When evidence repeatedly challenges a route, revisit concerted/stepwise hypotheses,
proton shuttles, solvent/catalyst participation, orientation/conformers, atom mapping,
spin and competing sites. Use discriminating calculations and revise the plan;
small seed variations are useful only when they test a specific remaining uncertainty.
Final classical TS claims still require stationarity, appropriate mode and endpoint
connectivity; excited/crossing problems need their own criteria.
