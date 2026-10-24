---
name: candidate-generation
description: Build and search transition-state and reaction-path candidate geometries from mapped endpoints, reaction coordinates, and structural evidence.
---

# Transition-state candidate generation

[Chinese version](SKILL.zh-CN.md)

## Script routing

Select the executor in [Operation entrypoints](references/commands.md), then read the matching input and validation contract in this Skill. Ordinary invocation does not require source inspection; unlisted files under `scripts/` are internal helpers.

Use this Skill to turn a reaction hypothesis into one or more geometries that a TS or path solver can search. The input is a mapped elementary step: reactants/products or fragments, bond changes, charge, multiplicity, relevant conformers, and any evidence about approach, proton transfer, or stereochemistry. The output is a candidate set with method, constraints, source frame, and the next validation action.

Before selecting a costly search, read [method selection](../method-selection/SKILL.md) and identify the exploration/refinement levels. Reuse verified structures and failed-search evidence; compare actual mapped geometry, torsions and stereochemistry before treating filenames or random embeddings as distinct candidates.

## Choose a construction method

- **QST2**: use when mapped reactant and product geometries are available and the step is a single, smooth rearrangement. Keep atom order and charge/spin aligned.
- **QST3**: use when the endpoints are reliable but the reaction-center structure needs a chemically informed middle guess. Supply an explicit mapped TS-like geometry so the intended reaction-center structure controls the middle guess.
- **Reactive pose + restrained scan**: use for separate fragments, association, substitution, cycloaddition, proton transfer, or unclear approach direction. Generate several faces/distances, then relax a forming/breaking coordinate with `chemical.scan-xtb@1` or `chemical.scan-gaussian@1`.
- **Relaxed 1D/2D scan**: use when one or two bond distances, angles, or dihedrals control the event and endpoints are not enough to locate the ridge. Select high-energy or curvature-changing frames as TS seeds.
- **NEB**: use when both endpoint minima are known and the path has several coupled coordinates. Start with compatible mapped endpoints; use `chemical.neb-xtb@2` or `chemical.neb-gaussian@2`, then refine the highest path region with a TS optimizer.
- **Direct TS optimization**: use when an imaginary mode, previous TS, literature geometry, or a good QST/scan frame already identifies the reaction direction. Use `chemical.gaussian-input@1` or `chemical.cf22d@1` with the TS task.
- **Conformer/pose enumeration**: use CREST or `reactive-geometry` before any of the above when torsion, face, or fragment orientation is the dominant uncertainty.

Keep multiple site, face, conformer, and mechanism hypotheses until validation or energetics gives a reason to reduce them. A scan maximum, NEB image, or QST interpolation is a candidate record and a useful restart frame; it becomes a TS claim only after `validation`.

Do not average the Cartesian coordinates of unaligned endpoints to make a TS guess. Establish atom mapping and a common frame first; even an aligned midpoint can collapse bonds or rotate fragments through one another. Use the mapped QST preparer or a justified reactive pose/path method, then inspect contacts and fragment geometry before Gaussian refinement.

## Recommended loop

1. State the atom mapping, forming/breaking bonds, transfer coordinates, and electronic state.
2. Prepare compatible endpoint geometries with `chemical.path-candidates@1` (`chemical.qst-prepare@1`) or supply a path specification.
3. Generate or edit reactive poses with `chemical.reactive-sites@1` and `chemical.reactive-pose@1` when fragments or faces are uncertain.
4. Run the bounded scan, gradient, QST, or NEB executor and inspect convergence, reaction-center distances, and path frames.
5. When a route fails, run `chemical.search-recovery@1` with the collected Attempt diagnosis and verified endpoint/geometry context. Follow an `auto_continue` decision only when its listed preconditions are present; a `needs_review` decision requires a revised hypothesis or repaired input.
6. Keep the best few chemically distinct frames, attach their source digests, and send them to a TS optimizer and `validation`.
7. If a search collapses to a minimum or distorts, use the failure geometry to change the pose, coordinate, endpoint pair, or method before retrying.

Do not require one independent TS for every starting conformer by default. A
conformer may first relax to another conformer and then enter the same reactive
basin. Distinguish a conformational-access path from a distinct reaction
saddle, and state which one the calculation tests. Promote only chemically
distinct, geometry-checked candidates to an expensive Gaussian refinement.

## Registered operations

- `chemical.path-candidates@1`: mapped QST/path input preparation.
- `chemical.qst-prepare@1`: QST2/QST3 request preparation.
- `chemical.scan-xtb@1`, `chemical.scan-gaussian@1`: bounded relaxed scans.
- `chemical.gradient-xtb@1`, `chemical.gradient-gaussian@1`: gradient/path calculators.
- `chemical.neb-xtb@2`, `chemical.neb-gaussian@2`: ASE NEB v2 searches.
- `chemical.search-recovery@1`: evidence-directed next-route decisions after a failed search.

Both QST preparers use the shared Cartesian serializer in `skills/chemical/_shared/gaussian_input.py`. It reads generated blocks back and checks their state, ordered elements and coordinates against the mapped request before producing the input. Supply the explicit atom mapping to the preparer; coordinate serialization preserves that ordering. Pass the generated `.gjf` to `chemical.gaussian-input@1` for checked preparation and submit its prepared request with `job_start`.

Read [candidate-generation criteria](references/candidate_generation.md), [path operations](references/path_search.md), [QST preparation](references/path_preparation.md), and [NEB executor details](references/ase_neb_executor.md). Use [reactive geometry](../reactive-geometry/SKILL.md) for pose construction and [validation](../validation/SKILL.md) for saddle/IRC evidence.

## Further references

- [reaction task interface](references/reaction_task_interface.md)
- [script layout](references/script_layout.md)
