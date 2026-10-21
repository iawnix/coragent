# Reaction investigation loop

[中文](reaction_investigation.zh-CN.md)

Use this loop to answer a requested reaction/path question, not as a mandatory
sequence for every chemistry calculation. Start from existing evidence and perform
only the missing operations. A Skill handoff changes the operation being performed;
the Agent retains responsibility for interpreting the result and continuing.

## Keep a working scientific decision

In the existing Node proposal/plan/note, retain the current elementary-step hypothesis,
mapped species and electronic state, source materials, alternatives, observed evidence,
and the next calculation with its purpose and bounded settings. For each attempt,
record what changed from the previous attempt and which observation would select the
next action. Use existing Jobs, Artifacts and Results; no new runtime schema or
per-turn checklist is required. Read current assessments before repeating old work.

## Operation handoffs

| Unresolved question | Operation and usable output | Decision after inspection |
| --- | --- | --- |
| What structures were requested? | [material-preparation](../../material-preparation/SKILL.md): original identity, graph/state, explicit-H order, mapped materials and source geometries | Establish graph identities and full atom correspondence before seed generation or optimization; carry them through calculations and reuse suitable existing geometries |
| What elementary step is being tested? | reaction-investigation: proposed bond changes, conformers/sites/states, alternatives and falsifiers | If endpoints span multiple steps, investigate intermediates; a failed input is not a falsifier of the reaction |
| How can the reacting atoms approach? | [reactive-geometry](../../reactive-geometry/SKILL.md): source-preserving poses, contact/protected-bond checks and rejected alternatives | Inspect actual local geometry, then select a constrained refinement or path search; revise the pose if it clashes |
| Where is a saddle candidate? | [candidate-generation](../../candidate-generation/SKILL.md): QST/TS optimization, scan or NEB outputs, selected frame and constraints | Refine a plausible peak as a saddle; classify a failed calculation and change the diagnosed cause |
| Is it the intended saddle and connection? | [validation](../../validation/SKILL.md): stationary evidence, mode assignment, both IRC directions and endpoint comparisons | Missing evidence requests a calculation; failed evidence returns a concrete diagnosis to construction/search or revises the hypothesis |
| What mechanism does the evidence support? | reaction-investigation plus [energetics](../../energetics/SKILL.md): connected steps, competing pathways and comparable energies | Identify remaining alternatives and missing steps; one validated TS does not establish an entire mechanism or selectivity |
| Are the requested conclusions deliverable? | [chemical-report](../../chemical-report/SKILL.md): claims tied to primary materials, conditions and limitations | Close only the agreed scope; unfinished calculations remain work, not a successful mechanism report |

Use the [candidate/validation handoff](../../candidate-generation/references/reaction_task_interface.md)
to keep candidate identity and the requested next operation explicit. Attach actual
evidence, not a list of boxes marked complete. Unknown, contradicted and supported
claims remain distinct.

## Match prerequisites to the operation

A source structure may be suitable for the next exploratory operation without being
a verified minimum or saddle. Label generated, constrained and unconverged geometries
as such and inspect their identity, mapping, local geometry and state. A catastrophic
overlap check alone does not verify the molecular graph or intrafragment geometry.

For association reactions, a frequency-verified minimum of the complete reactant
complex is not a universal prerequisite for TS exploration. Prepare reliable monomers,
assemble mapped poses with intact fragments, and select constrained refinement,
scans, QST, NEB or direct saddle optimization according to the available evidence.
QST needs compatible ordered structures; a particular NEB method may need relaxed
endpoints. Check the selected method's requirements instead of imposing one method's
prerequisites on all alternatives. Preserve constraints in the evidence; final saddle
and connectivity claims still require their own validation.

A forward/reverse IRC endpoint may need further integration or basin optimization.
An incomplete path is not evidence of the wrong product. A complete path to a different
basin, or an unrelated imaginary mode, is information for revising the candidate or
mechanism. Do not keep requesting the same missing evidence from an unsuitable seed.

## Recovery and stopping

After each failed attempt, use [search recovery](../../method-selection/references/search_recovery.md):
separate invalid inputs, execution failures, numerical stalls and chemical contradictions.
Preserve the failed branch, select a changed input or method justified by that diagnosis,
and perform the next authorized operation. Reading the same instructions again or
publishing another failure summary is not a substitute for making that change.

If mapped geometries are missing but can be constructed from the supplied species,
construct them. A repeated unsafe interpolation calls for different geometry construction,
not a demand that the user provide the finished endpoint. Use an existing serializer
for fragile solver formats; verify each structure block before submission.

Bound attempts by conformers/poses, optimizer steps and an explicit resource allowance.
Distinguish a chosen attempt limit from a user or installation limit: exhausting one
attempt calls for replanning within the authorized scope, not an invented requirement
for renewed permission. If the total cost cannot reasonably be bounded, establish a
concrete budget with the user. Stop for an actual exhausted limit, unavailable required
resource, unresolved user-dependent ambiguity or user stop; explain the alternatives
considered and the specific missing condition. Respect existing blocked/paused task
controls when resuming; this Skill does not override them.

While Jobs run, work on independent questions. When only their results remain, record
the explicit wait and end the turn so Monitor can resume it. At resume, read the pending
decision, inspect newly collected evidence, and continue from that point.
