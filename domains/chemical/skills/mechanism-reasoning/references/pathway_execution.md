# Conditional mechanism exploration and pathway audit

For R-only input, retain unknown products. Enumerate testable bond/proton/electron
transfer hypotheses from functional groups, charge/spin, orbital accessibility,
acid/base/redox conditions, geometry, solvent/catalyst participation and competing
regio/stereo/conformational channels. Allocate explicit candidate/Job budgets and
falsifiers; do not insert a favored reaction-name template as the mechanism.
For supplied R/P, inspect whether intermediates are necessary before choosing
QST2/3. Separate fragments require conformer/complex preparation; a supplied complex
retains its relative placement. Optimize/characterize candidate basins when needed,
and expand the path when scans or IRC reveal intermediates/unexpected exits.
Spin changes route to specialized crossing evidence, not ordinary TS certification.

When a failed or partial calculation provides usable mode, gradient, path or electronic evidence, turn it into an explicit edit hypothesis for [reactive-geometry](../../reactive-geometry/SKILL.md). Generated candidates still need appropriate refinement, TS optimization, frequencies and IRC.

`chemical.pathway-check@1` uses the structure binding, input role input and
chemical-pathway-input/1. It audits explicit material, hypothesis and evidence
relations without mutating Nodes or declaring the user task complete.

Input fields:

- species: 1–128 IDs, each with material and origin. Origin has kind
  provided/hypothesis/calculated, source_sha256, and hypothesis_id for guessed
  species. Unknown names must first become explicit structures for atom accounting.
- hypotheses: 1–64 IDs, each with statement, falsifier and source_sha256.
- reactants and optional products: species→positive integer coefficients.
  Null products preserve an R-only task's unresolved target.
- budget: positive max_jobs and max_candidates (≤10000 each); unexplored: list
  of remaining questions, possibly empty. These are declared research budgets,
  not an autonomous mechanism generator or automatic dispatch loop.
- steps: at most 256 records with id, hypothesis_id, kind
  elementary/unresolved/crossing, reactants, products, mapping, observations and
  optional validation. Sides have total order ≤8, expanded states ≤1024 atoms.
- A mapping is a complete list of pairs of [species_id, zero-based instance,
  local_atom_id]. Explicit instance identities handle stoichiometric duplicates.
  Element/isotope identity and atom/charge balance are checked. Missing mapping
  remains incomplete; it does not trigger an invented correspondence.
- Observations have source_sha256, interpretation supports/conflicts/unresolved,
  and note. Earlier guesses, actual observations, conflicts and unexamined
  alternatives stay distinct.
- routes: at most 64 named ordered lists of step IDs. Every shared intermediate
  and spectator inventory must match exactly. Missing IDs, broken continuity,
  unknown products and failure to reach the target produce explicit gaps.

Optional elementary-step validation contains saddle_material, saddle_evidence,
mode_coordinates and two paths, using the existing generic mode/IRC contracts.
The checker reruns those numerical checks against the pathway's exact endpoint
materials; it does not accept a caller-supplied pass boolean. This integration
currently requires each endpoint side to be one complete material. Associate
separate fragments first when supplying IRC basin evidence. Crossing/unresolved
steps retain not_assessed and need their separate physical evidence.

The output separates balances, mapping, declared-state continuity, observations,
recomputed step evidence and route gaps. Fragment spin coupling is not inferred
by adding multiplicities. supported_within_scope means all supplied classical
step checks and endpoint continuity passed, not exhaustive mechanism discovery,
kinetic superiority, or fulfillment of the original research request.

Use the same research Node for attempts at one question. Preserve negative
Results, collect failed Jobs and inspect receipts before changing method. Resume
from durable Task/Node/Artifact state after waits or context recovery; do not
resubmit unknown jobs. Report thermodynamic ordering, conditional kinetic
predictions and unexplored alternatives separately. Only independent scientific
questions need separate Nodes; a two-step chemical path is not automatically a
two-Node research workflow.
