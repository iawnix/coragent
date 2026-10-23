# Planning and revisiting research questions

Use this reference for compound research or when evidence changes the next useful action. Node relations organize questions; the Node's plan holds current hypotheses and methods, while notes preserve observations and decisions. User Task control remains in the task tools.

## Choose a useful question size

First read the current task's research entries/focus and the relevant existing questions; search prior work when needed. Reuse the question that owns the intended investigation. Create a Node only when a new research objective needs its own continuing investigation and judgment. Being executable separately or producing a reusable intermediate Result is insufficient by itself. A different command, parameter, initial structure or platform is not a new question.

A useful check is whether the goal still holds after changing the program, geometry or next calculation. If so, continue the same Node. "Run frequencies" and "collect outputs" are actions in a plan or Job workflow. Expand the question graph as distinct research objectives emerge; do not prebuild a Node for every calculation step.

| Study | Initial question | Work within that question |
| --- | --- | --- |
| Molecular property | What property does this system have under the stated conditions? | Input preparation, convergence repair, repeat calculation |
| Competing reaction paths | Which path is favored under the stated conditions, and is the evidence sufficient? | Candidate structures, optimization, frequency/IRC checks, energies and retries |
| Periodic DFT | What physical difference does the comparison establish? | k-point/cutoff convergence and parameter tables |
| MD/free energy | What state difference or free-energy estimate is supported? | Equilibration, sampling checks, replicate trajectories and statistical windows |
| Model fitting | Which model supports the intended prediction? | Data checks, parameter searches and repeated fits |
| Theory/derivation | Does the proposed conclusion follow under the stated assumptions? | Lemmas, approximation checks and local revisions; Jobs are optional |

Split out a path mechanism or method-validity study when it becomes a distinct objective needing its own ongoing judgment. A bounded comparison may remain one Node with multiple Jobs and Results; neither one Node per Task nor one Node per path is mandatory.

A root question is optional. Several task entries can represent independent questions. Use `part_of` from a subquestion to its broader question; a shared question can have several parents. `requires` records an actual research dependency, not the order in which tool calls occurred. Use `alternative_to` when approaches really are alternatives. Comparisons cite exact input Results.

The first Node can supply an initial task binding. Later creations do not automatically enter the task scope. When an additional question is warranted, declare its actual relation and deliberately choose stable task entries and the current focus; do not add every new Node to both lists. Read the current task and replace the complete lists when they need to change:

```json
{
  "action": "set_research",
  "expected_revision": 3,
  "research": {
    "entry_node_ids": ["node_returned_for_the_study"],
    "focus_node_ids": ["node_returned_for_the_study"]
  }
}
```

Substitute actual returned IDs and revision. This replaces both navigation lists. Task focus is not a lock, ownership or permission to spend resources. A shared Node can remain open when one task finishes. Read-only browsing uses `research_read {ref}` or `{ref, field:"relations"}` and the returned pagination; it does not need a focus update.

## Let evidence change the plan

On recovery, relate the current findings and pending Jobs to the user's objective and delivery criteria. Continue a method when another attempt has a reason to be informative. If a method reaches its limit, assess the remaining authorized approaches. If a Job is running and independent work remains, pursue it; wait on the task only when those Job outcomes are needed before further useful work.

An execution error warrants diagnosis; it does not by itself refute the scientific idea. Update the existing question's method after inspecting the failure. A candidate-specific negative finding is useful evidence and need not terminate the broader question or assignment.

To revisit a closed question, read its current fields, reopen it with `research_update`, and record the reason and evidence in the note. Create another Node only for a distinct research objective needing its own continuing investigation and judgment. Preserve old Jobs, files and Results. Reuse exact prior evidence where applicable; repeating an external action requires checking its original receipt.

Correct a published conclusion with a new Result and `supersedes`. Select it as the current assessment when appropriate. Review affected comparisons and reports using the supplied notices. A notice requests scientific review; it does not automatically invalidate every downstream conclusion or launch recalculations.

## Retain progress and finish the assignment

Plans and notes explain decisions; a Result fixes a conclusion worth citing. Record a finding in the appropriate place without copying the same account into a note, Result and task progress. The runtime observes published evidence and actual Job milestones; the Agent still selects the task's next action and explicit waits. Editing a plan, making more Nodes or citing the same evidence in a different combination does not establish new substantive progress. The no-progress count is an advisory replanning signal, not a fixed stopping threshold; continue within the user's compute, cost, time and retry limits. For derivation or planning assignments, retain the useful derivation or plan itself as a Result/material.

Finish against the user's delivery criteria, with the relevant immutable evidence and limitations. A negative or inconclusive conclusion may satisfy the actual assignment; it does not authorize weakening a requested claim. Closed Nodes and successful processes are not completion evidence by themselves. Stop repeated uninformative attempts within the stated limits, and distinguish a local failed method from a task-wide blocker.
