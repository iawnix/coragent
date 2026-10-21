# Execution target selection

Scientific Skills declare executors, software backends, resources and input/output contracts. They do not choose `local`, `tri`, `slurm` or another execution target.

The task layer resolves the user's execution requirement and stores the resolved target:

- An explicit TRI request selects a target with `scheduler = "tri"`.
- “local (TRI queue)” and “TRI queue” request TRI even when the handler runs locally. “local” by itself, when used as the execution destination, requests direct controller execution (`scheduler="none"`, `location="controller"`).
- An explicit Slurm request selects a target with `scheduler = "slurm"`.
- With no platform request, use `execution.default_target` from the installation.
- An unknown or ambiguous scheduler fails before preparation; it never falls back to direct local execution.

The task stores the concrete name, such as `execution_target = "tri"`. Preparation, submission, status, recovery and collection reuse that target. Changing the installation default does not reroute an existing task.

`transport = "local"` only means that CoRAgent invokes an external handler on the current host. It does not mean that the scientific process runs directly on that host. The target's `driver` and `scheduler` determine routing:

| Target properties | Meaning |
| --- | --- |
| `driver = "systemd"`, `scheduler = "none"` | Direct execution on the controller |
| `driver = "external"`, `scheduler = "tri"` | Submit through TRI |
| `driver = "external"`, `scheduler = "slurm"` | Submit through Slurm |

Executor preparation should omit `--target` in a domain Skill. For an active task, the runtime injects its pinned selection through `CORAGENT_TASK_EXECUTION` into bash, and the executor inherits it. Outside a task, the executor resolves the installation `execution.default_target`:

```text
"$CORAGENT_PYTHON" -m research_agent.application.executors \
  --config "$CORAGENT_JOB_CONFIG" \
  --executor <selected-executor-id> --version <selected-version> \
  --input <role>=<input-path> \
  --output prepared/request.json
```

Before submission, the prepared request target must match the task target. A TRI receipt must contain `driver = "external"` and a non-empty `scheduler_id`; a receipt without scheduler identity does not prove TRI submission.

## Source-bound selection and correction

`task_begin` calls the shared Jobs resolver and retains the target name, scheduler, location, routing digest and verified source excerpt. Omit `execution_target` when no platform was specified; the controller pins the configured default. When the user specifies a scheduler, provide `execution_intent`, for example:

```json
{"execution_intent":{"source_submission_id":"24","source_text":"local（Tri队列）","scheduler":"tri"}}
```

The excerpt must occur exactly in a cited actual user submission. Select the affirmative execution instruction, excluding negated alternatives or quoted history; the resolver is a configuration matcher, not a general language parser. It detects configured scheduler names in sources and rejects contradictory selectors. If several matching targets exist, use a concrete configured `execution_target` consistent with the user's constraints or clarify the missing choice. Do not resolve ambiguity with the default. For direct controller execution specify `scheduler="none"`, `location="controller"`.

A mistaken registration is repaired with `task_update action=correct_execution`, the current `expected_revision`, `execution_intent` quoting the original explicit instruction, the corrected `execution_target` if needed, and `reason`. This cannot change the user's objective or criteria, and does not authorize migration or cancellation of existing Jobs. It retains a new selection version and audit entry; an unrelated blocker remains blocked.

A new user destination request uses `refine` with a new `source_submission_ids` and selection. If an installation route changes under the same name, preparation and new submission fail with `execution_target_changed`; after reviewing the change, an actual new user instruction can re-pin it through `refine`. Changes to resource defaults alone do not change routing identity. Job submission independently checks the trusted task target and digest, including requests loaded from files; editing bash context cannot bypass that check. Existing Jobs keep their recorded identities; inspect/reconcile/collect them, never resubmit them merely to change destination.
