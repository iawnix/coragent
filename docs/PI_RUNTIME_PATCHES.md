# Managed Pi runtime patches

CoRAgent pins Pi v1.1.0 at `abe508e1b89912adde45528136c3221eb69acdd7`
in `packaging/coragent_packaging/pi/source.json`. The experimental transport protocol remains version 8.
Terminal presentation uses Pi's experimental client, separately from ordinary
`InteractiveMode`.

The [Pi 1.3.0 migration audit](PI_1_3_MIGRATION.zh-CN.md) records upstream
coverage and migration work for the fourteen patches present at the time of that audit and the installer model
type workaround. Pi 1.2.0 removed the experimental server/client stack; 1.3.0
requires replacing that integration before changing the active pin.

`packaging/coragent_packaging/pi/prepare.py` checks and applies the patches in
`packaging/coragent_packaging/pi/patches/` in order, skips completely applied groups, and rejects a
partial or incompatible group before applying that group. Later patches can
depend on earlier ones. Verification checks that
Git can reverse every patch; comments or version strings alone are insufficient.
A mismatched upstream commit is rejected. Verify the complete ordered stack in
a separate checkout before installing it.

The authoritative patch ownership, regression coverage and removal conditions are maintained in the [Pi integration registry](../packaging/coragent_packaging/pi/README.md).

There is also a source modification outside the patch directory:
`hydrate_model_data()` in `packaging/coragent_packaging/pi/prepare.py` adds an `as any` cast to
the OpenCode Go model list. Include it in every upgrade audit. Pi 1.3.0 adds
the Google API type and implementation missing from 1.1.0's provider; the
migration should remove the cast and validate the hydrated catalog build.

Application integration lives outside these patches. The worker publishes the
`coragent.client-queries` service, bound to its workspace, session, kernel bridge, and
prompt manifest. The terminal consumes it through Pi's attached session service
source, including over SSH. No client-side Python process reads research state.
The slash registry is defined in `command_catalog.json`; Pi owns its editor,
selectors, transcript, model commands, and input loop.

`/resume` asks the Host for an available session in the current workspace, then
closes and recreates only the terminal presentation. `/quit` disconnects only the
terminal. SSH connections proxy both the Host and Pi sockets; proxies and their
SSH children are closed when the terminal exits.

## Updating Pi

Prepare a separate checkout under the configured test environment. Validate the
patch groups, real worker queries, presentation, session recovery, Host/Phone/
Monitor contracts, and packaging before updating the source pin and npm lock.
Source pin and Pi package versions must move together. Use a new managed runtime
directory for a new commit; existing session directories retain their layout.

Pi 1.1.0 takes the historical cutoff as `runtime.context(id, context, { at })`;
patch 008 preserves request admission on this API. The upstream context cache
uses its default idle retention (ten minutes). Patch 010 persists research orientation
with the request cutoff and carries historical scope metadata through native
compaction. Only current control data remains request-only. The estimator
now uses 3.5 characters per token, so budget admission may compact earlier.

Research tool cards show Pi's recorded `durationMs` for final results, including
after reconnect, and omit it for older or untimed results. For `job_start` this
is the tool's submission time; scientific Job duration remains owned by Job
Manager. Expanded cards preserve the full result and label the tool duration.

The pinned runtime uses `azure` as the Azure provider identity. Configure providers
and credentials through the installation configuration described in
[Model configuration](MODEL_COMPATIBILITY.md). The experimental TUI exposes only
its supported commands, not the ordinary Pi command set.

Job event admission is implemented in CoRAgent's worker service rather than another
Pi source patch. `apps/agent/runtime/admission/jobs.mjs` uses the pinned
`packages/durable/src/harness/submissions.ts` transaction primitive
`admitSubmission`: run/inbox checks, immutable input provenance and placement
share one short Pi commit. All State/Python assessment runs outside that commit.
The Worker reassesses internal input before its first model consumption and
records the State basis against the submission, across generation task changes.
An authenticated producer submits structured event IDs; message text and ID
prefixes never establish provenance. Job Manager acknowledges consumption, retaining
pending or deferred events and earlier identities when State supersedes an input.
Native tests cover busy rejection, batch idempotency, a slow bridge racing native
input, consumption reassessment, and real Worker/Host restart recovery. Recheck
the internal Pi API on every pin update.

The CoRAgent footer shows model, thinking level, workspace/session, estimated context
and cumulative model tokens. `/usage` opens provider-reported input/output/cache
counters; reasoning is not added again to output. `pi.usage` preserves totals
across compaction. The worker telemetry query uses Pi's internal
`harness/compaction.ts:estimateContext` with the conversation's canonical context
and the selected model's configured capacity. Recheck that estimate API when
updating Pi; it is not a tokenizer or a billing measurement. Changed context or
model identity invalidates an old estimate until refreshed. Set `CORAGENT_TUI_RING=0`
for a numeric-only context display on fonts without suitable circle glyphs.

The presentation subscribes to Host Monitor events and refreshes read-only
snapshots on reconnect and every five seconds. Monitor status includes an
observational pending-delivery summary; reading it never claims or batches an
outbox entry. Counts are scoped to the attached session, while worker health is
shared. Host `next_run` is not a Pi inbox enum: accepted queued messages use
`followUp`. User input retains Pi's own queue display. Job Manager waits
for idle admission, so busy-session wakes normally remain pending delivery.
