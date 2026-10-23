# Scientific Job contract

A domain extension owns scientific inputs, argv, parsing and validation. Its execution catalog declares convenience entries; its Skills explain when to use them and how to interpret results.

## Submission

Use `"$CORAGENT_PYTHON" -m research_agent.application.executors` to combine an installed executor with the Task's bound platform and scheduler entry. Configure software under `execution.platforms.<platform>.bindings` or its scheduler entry's `bindings` in the main `config.toml`; `CORAGENT_JOB_CONFIG` points to the generated execution input. The preparer writes argv, `execution_target`, process environment, pinned inputs and required outputs. Inspect the file, then pass its returned request_file/request_sha256 with optional timeout_seconds to job_start. Configure submission defaults in the main configuration before preparing. Runtime registers prepared_ref together with the dispatch intent and Job; the preparation command does not write Research Memory.

Inputs are snapshotted with paths and digests. Keep script module layout intact. Runtime owns local/remote process control; Skill scripts may synchronously launch the scientific executable inside the Job but must not detach or submit their own scheduler jobs.

## Environment

job_probe checks the selected platform, not scientific readiness. The configured command and activation_script determine the actual executable. Prepare the declared `chemical.cf22d-doctor` executor as a Job for CF22D dependency/method checks in each selected environment. Remote wrapper Python must be explicitly bound. Do not substitute system Python or change the scientific method when dependencies are missing.

## Evidence

Use the existing node_id. Record observations, scientific criteria and next-step decisions in a research_update note, or publish a reusable conclusion with research_result, citing collected materials and limitations. Do not duplicate the same finding in both records or task progress. A completed computation does not establish a scientific conclusion or require a new Node or Result.

artifact_derive records a derivation descriptor; it does not execute analysis. Run a Skill script then register its actual output. artifact_link persists evidence relations. Changed scientific inputs/settings create a new Job; recovery of an uncertain submission uses job_reconcile, not automatic resubmission.

The catalog constrains selected registered helpers only. Generic `job_start` also accepts explicit command, inputs, outputs, and `execution_target: {platform, scheduler_entry}` consistent with the Task binding; task-specific Python methods can use the preparer's `--script` and `--backend` without a new catalog entry.
