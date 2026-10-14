# Capability map

Use the smallest tool that answers the current question. A tool result is a
research material and a hypothesis update; it is not a verdict that forces the
next tool.

| Question | Tool | What it returns | Boundary |
| --- | --- | --- | --- |
| Which mapped atoms and fragments define the proposed reaction center? | `chemical.reactive-sites@1` | Fixed/mobile roles, local frames, alternative faces and distance hints | Requires explicit material graph and `bond_changes`; does not infer a product or mechanism |
| How can separate fragments face one another? | `chemical.reactive-pose@1` | Deterministic pose ensemble with distance, cone, twist and safety diagnostics | No energy ranking, conformer search or TS validation |
| Which internal conformers should be tried? | `chemical.seed@1`, CREST | Seed geometries or a conformer ensemble | Does not decide the reaction center |
| Can a pose relax while retaining the proposed reaction coordinate? | `chemical.scan-xtb@1` | Restrained optimized geometries, actual coordinates and unrestrained physical energies | A one-point constrained relaxation is not a saddle search |
| Can a path connect compatible endpoints? | QST, relaxed scans, GSM/NEB tools | Path images and calculator evidence | Endpoints and atom correspondence must already be prepared |
| Is a candidate a TS? | Frequency and IRC validation | Imaginary-mode and downhill-path evidence | A geometry score, scan maximum or NEB image is not TS proof |

## Recommended selection

When the reaction center is mapped, analyze it first and then sample poses. If
the input came from one SMILES embedding, add conformers before expanding the
pose search. If a pose collapses during an unconstrained optimization, return to
a restrained xTB point rather than accepting the collapsed minimum. If multiple
sites or faces remain chemically plausible, run them as separate hypotheses and
compare their evidence later.

The hard-coded executor checks should remain limited to malformed input,
coordinate safety, declared constraints and provenance. Reaction-family priors
and the choice to broaden, retry or stop belong to the Agent's hypothesis
management.
