# Evidence and conclusions

Inspect actual materials before recording scientific observations. Use `observation` for measured facts, `conclusion` for interpretation and `limitations` for unresolved conditions. Failed, negative and uncertain outcomes can be published; a user requirement does not prove a scientific claim.

Choose reference fields by purpose, using exact returned IDs:

| Field | Purpose and accepted references |
| --- | --- |
| research_create.source_refs | Original user requirements; user_* messages only. |
| research_create.input_refs | Background citations; existing Nodes, Results, user messages, notes, runtime records, Jobs, collection receipts and verified Artifacts. |
| research_result.inputs | Fixed materials actually used to derive the conclusion; existing Results and verified Artifacts only. Omit when none apply. |
| research_result.evidence_refs | Supporting citations; the same reference types as Node input_refs, including user messages and execution records. A requirement citation is not scientific proof. |
| research_result.files[].artifact_ref | Delivered file; a verified Artifact reference, never a mutable path, Job ID or receipt. |
| research_result.check_refs | Scoped check evidence; verified Artifacts or collection receipts, not Job IDs. Inconclusive checks are allowed. |
| subjects on create/update/result | Named roles mapped to existing Results or verified Artifacts only. |
| research_update.assessment_ref | An existing Result or agent-authored note/record belonging to the same Node. |
| research_result.supersedes | An older Result on the same Node being explicitly corrected. |

For a candidate structure resolved from a user request, cite the structure Artifact and original user message in evidence_refs. Do not put the user message in inputs. For example (replace every example ID with its actual returned reference):

```json
{"node_id":"node_...","conclusion":"A candidate structure was resolved; the reaction mechanism remains undetermined.","evidence_refs":["art_...","user_..."]}
```

## Corrections and review

Published Results cannot be overwritten. Publish a correction with `supersedes` pointing to the older same-Node Result and explain the changed evidence or interpretation. Publication does not automatically replace the current synthesis; use `as_assessment` when appropriate. Inspect `result_saved` and `assessment_selected` separately. Follow dependency references to review downstream conclusions while preserving valid materials and competing interpretations.

Collect Job outputs through `job_collect` to retain producer provenance; do not recreate raw outputs as unattributed text. See [Job and material workflow](../../research-workflow/references/jobs-and-artifacts.md) for preparation, submission and collection.
