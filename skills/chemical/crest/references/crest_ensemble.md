# Ensemble execution and selection

[中文](crest_ensemble.zh-CN.md)

## Contents

- [Independent Jobs](#independent-jobs)
- [Native profile and evidence](#native-profile-and-evidence)
- [Reparse retained outputs](#reparse-retained-outputs)
- [Member identity, selection and refinement](#member-identity-selection-and-refinement)
- [Rigid complex inputs](#rigid-complex-inputs)

## Independent Jobs

All executors use version `1`. Register inputs as Artifacts and prepare with the
installed control interpreter; paths below stand for actual absolute work paths:

```text
"$CORAGENT_PYTHON" -m research_agent.application.executors --config "$CORAGENT_JOB_CONFIG" --executor chemical.crest --version 1 --input material=<material.json> --input-artifact <material-ref> --output <request.json> -- --method gfn2 --threads 2 --timeout 3600 --energy-window 6
```

Submit returned request_file/request_sha256 plus node_id with job_start, then
collect the terminal Job. Use the same preparer for these independent recipes:

| Executor | Input roles | Forwarded arguments |
| --- | --- | --- |
| `chemical.crest` | `material` | `--method gfn1\|gfn2`, `--search-level normal\|quick\|squick\|mquick`, `--opt-level normal\|tight\|vtight`, `--threads`, `--timeout`, `--energy-window`, optional `--solvent`, `--max-members` |
| `chemical.crest-ensemble` | `material`, `run` (collected result.json) | none |
| `chemical.ensemble-select` | `ensemble` (chemical-ensemble/1) | `--energy-window 6 --rmsd .1 --max-selected 32 --max-pairs 1024 --max-candidates 64 --max-search 20000` |
| `chemical.complex-sample` | `input` (chemical-complex-input/1) | required `--mode assemble\|perturb`; `--samples 16 --max-attempts 256 --seed 0 --min-separation 3 --max-separation 6 --translation .5 --rotation-degrees 30 --clash-scale 1.2` |

CREST requires target-local `crest` command plus a Python wrapper binding;
`wrapper.lock` supports an explicitly configured backend, without installing the
native solver. Its activation script must expose compatible native dependencies.
Check runtime `python`, then execute a bounded scientific Job. Profile installation
has no default CREST calculation smoke check. Environment/import checks alone do
not verify a native search. The other recipes use `structure.lock`.

## Native profile and evidence

The bundled profile pins CREST **3.0.2** command/output semantics, GFN1/GFN2,
explicit ground-state declaration, charge/multiplicity and ordinary isotope
masses. `--uhf` is multiplicity minus one; parity is checked. Omitted solvent is
explicit gas phase; `--solvent water` selects ALPB. No native constraints or
excited-state tracking are supplied. Native sampling randomness is uncontrolled.

Input is chemical-material/1 with supplied angstrom coordinates in current atom
order (1–256 atoms). Defaults: GFN2, normal search, vtight optimization, one thread,
3600 seconds, 6 kcal/mol window and a 256-member parsing budget (maximum 1024). Unsupported
version, missing outputs, timeout, nonzero exit or inconsistent primary evidence
fail the Job; result.json and available primary files remain collectable.
Descendant processes are terminated when the wrapper attempt ends.

Required primary files are crest.out, crest_conformers.xyz, crest_best.xyz and
crest.energies, at most 64 MiB each. XYZ comments contain absolute hartree energies;
crest.energies contains consecutive 1-based indexes and relative kcal/mol.
Counts, element row order and relative differences must agree (0.002 kcal/mol
tolerance); best geometry must match a minimum-energy member in fixed order
(1e-6 Å and 1e-7 hartree) when the full ensemble is read. Observed malformed tails
retain the valid frame prefix and mark parsing invalid. No silent row skipping or
missing-energy zero fill.

`--max-members` limits structured member and energy-row reading; it is not a CREST
sampling control or a selection count. `primary.parsing_status` is `complete`,
`limited` or `invalid`. Reaching only this read budget leaves the native run
`status=completed` and the wrapper exit code zero, while `primary.complete=false`.
`read_budget` reports the requested maximum, `members_read`, `energy_rows_read`,
and `has_unread_members` / `has_unread_energy_rows`. The unread tail is unvalidated;
no total member count is inferred. A best geometry outside that prefix has
`best_membership_verified=false` until it can be matched in a fuller read.
Observed missing, malformed or inconsistent data still fails even when a read
limit is also reached. All four original files and their full-file digests remain
available; a partial import remains `complete=false`.

For example, native output containing 138 conformers and `--max-members 64` produces
64 parsed members and an explicit unread tail. This calls for reparsing retained
files when more coverage is needed, not repeating the search. To restrict later
refinement, use `--max-selected`; `--max-pairs`, `--max-candidates` and `--max-search`
bound comparison work. `--max-candidates 64` concerns graph mappings per comparison,
not the number of conformers in the source ensemble.

Upstream contract: [options](https://github.com/crest-lab/crest/blob/v3.0.2/src/confparse.f90),
[energy table writer](https://github.com/crest-lab/crest/blob/v3.0.2/src/cregen.f90).

## Reparse retained outputs

Use the installed Skill's `scripts/crest_io.py` with the control interpreter. This
command performs no native calculation and needs no new executor. Supply the
original material, original run receipt and a directory containing the four
unchanged primary files. The output parent directory must already exist:

```text
"$CORAGENT_PYTHON" <installed-crest-skill>/scripts/crest_io.py --directory <collected-primary-directory> --material <original-material.json> --run <original-result.json> --max-members 256 --output <new-work-directory>/crest-reparsed.json
```

The command checks the material digest and all four primary digests against the
original receipt, then invokes the same bounded parser. Existing output files
are rejected. The new `chemical-crest-run/1` receipt retains the native command,
settings and exit code, updates only parsing and its resulting wrapper status,
and records `reparse_of` with the original receipt and primary digests. Native
nonzero exits cannot become successful through reparsing. Historical Job state
and collected Artifacts are unchanged.

Register the new receipt as derived material with its source references; it can
be passed as the `run` input to `chemical.crest-ensemble@1`. Inspect its new
`primary.parsing_status` before claiming full coverage. A larger budget is an
explicit reading choice within 1–1024, not an automatic increase or silent crop.

## Member identity, selection and refinement

Import binds the exact material-file digest to the self-contained run receipt;
primary hashes remain in derivation, alongside Job Artifact provenance. Each
member keeps local IDs, isotope/graph correspondence, state and source geometry.
RDKit infers coordinate bonds, formal charges/radicals and specified stereo in
fixed atom order for H/B/C/N/O/F/Si/P/S/Cl/Br/I. Missing graph/charge or unresolved
bond assignment is not_assessed; unsupported metals are not certified by guessing.
Inference is not electronic-state or atom-trajectory proof.

Selection uses proper-rotation all-atom RMSD with one alignment for the entire
complex and bounded graph symmetry matching. Only identity/state-compatible
members may merge; incomplete comparisons are retained or explicitly deferred.
Every member has a selected/duplicate/deferred/outside_energy_window/excluded/
unusable decision. Pair exhaustion and selection caps are reported separately.
Energy ranking requires the same reference species and one explicit electronic
energy model (including method, solvent and constraints). Mixed models disable
ranking; duplicates may still be geometric representatives, not lowest-energy
representatives. Unknown energies/identity remain unranked. No free-energy,
population or global-minimum claim follows. Keep the original ensemble.

Import/sample/selection export result.json, refinement.json and generated
members/NNNN/{material.json,geometry.xyz} paths. Use these XYZ files independently
with compatible xTB/Gaussian/CF22D SP or optimization Jobs, preserving state and
solvent explicitly. The xTB shortcut currently cannot express solvent; use an
appropriate verified command for solvated refinement instead of switching to gas.
No optimization is submitted by the ensemble operations. Ordinary XYZ does not
encode isotope masses, charge or electronic state; consult the full material
and use isotope-aware solver input for explicitly isotopic members.

## Rigid complex inputs

chemical-complex-input/1 contains `materials: [<embedded chemical-material/1>, ...]`.
Each source needs coordinates and explicit graph-derived or declared fragments.
One source preserves its state/IDs; several sources concatenate IDs as
part1_atom1, etc., and record atom_lineage. Charges sum only when known; total
`multiplicity` and `electronic_state` must be supplied explicitly or remain unknown.
Duplicate graph atom-map labels require explicit resolution. Maximum 16 sources,
2–16 fragments, 256 atoms. First fragment is always fixed; optional
`fixed_fragments: [0,2]` fixes additional zero-based indexes. At least one must move.

Optional `distance_constraints: [{"atoms":["part1_atom1","part2_atom1"],"minimum":3,"maximum":5}]`
uses combined IDs and angstrom. Assemble draws proper random rotations and centroid
separations around fragment zero. Perturb retains the original if constraints and
collision checks permit, then bounds centroid translation and rotation. PCG64 seed,
transforms, rejections and finite attempt budget are recorded. Reject interfragment
distances below clash_scale times summed covalent radii. These are rigid candidate
placements, not binding energies or optimized complexes; constraints do not carry
to later optimization and internal conformers must be searched separately.
