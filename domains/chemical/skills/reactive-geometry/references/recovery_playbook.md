# Recovery playbook

Use failure evidence to revise a hypothesis, not to silently retry the same
input. Each retry should change a declared variable or add evidence.

| Observation | First interpretation | Useful next action |
| --- | --- | --- |
| `atomic_clash` or catastrophic overlap | Rigid placement entered a nonreactive contact | Increase distance, sample another face/cone, or use another conformer |
| Mobile fragment is far away after pose generation | Fixed/mobile role or local frame is unsuitable | Inspect `reactive-sites`, reverse the fragment role hypothesis, and regenerate |
| `multi_pair_rigid_fit_residual` | Requested contacts cannot be made by one rigid pose | Split the hypothesis, change the distance set, or use a flexible constrained scan |
| Constrained xTB point collapses outside tolerance | Restraint is too weak or the pose is not chemically supported | Increase the restraint only within the declared budget, change the pose, or retain the point as rejected |
| Unconstrained optimization returns separated reactants | The TS-directed coordinate was released too early | Return to a constrained point or a short relaxed scan |
| QST/NEB immediately breaks or makes unrelated bonds | Endpoints or initial images are incompatible | Recheck mapping, reaction-center distances and endpoint conformers before another path run |
| One candidate succeeds while alternatives fail | Evidence favors one basin but does not prove uniqueness | Preserve failed alternatives and compare their diagnostics in the research report |
| No site is chemically supported | Explicit bond changes or product mapping are missing | Use `chemical.reaction@1`, ask for the missing mapping, or keep the center unresolved |

Never convert a tool's `safe` verdict into a TS claim. A safe pose is only a
candidate geometry suitable for the next calculation.
