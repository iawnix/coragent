# Changelog

This file records user-visible changes. Current architecture is documented in
[the architecture guide](docs/ARCHITECTURE.md); earlier designs remain in Git history.

## Unreleased

- Consolidate job execution, background tracking and event delivery under Job Manager.
  Monitor names the management interface; Task Controller owns continuation policy.
  Execution records distinguish authenticated producer from execution reason.
- Replace the research Review lifecycle with research-brief/1. Refresh context when
  scoped facts change, independently of input producer. Track projection completeness
  and optional model synthesis separately; remove review_pending.
- Breaking contracts: coragent-host/3, coragent-user-task/3 and
  chemical-research-report-input/2, with execution-observation/2 for Job observations. Retired input producers and Review interfaces are
  rejected without compatibility aliases. Upgrade clients and explicitly bind retained
  research records in a new session for older Tasks.

- Remove optional model icon font installation, bundled font assets and launcher
  activation. Terminal icons use existing fonts; previously installed fonts are untouched.

- Persist natural-language user pause/resume/cancel instructions in the Task Controller,
  preventing automatic continuation after research stops. Cancel task scheduling before
  contacting Job backends; retry pending cleanup without waking the model.

- Add ASE NEB v2 with Gaussian/xTB calculators, FIRE/BFGS, optional IDPP,
  evaluation budgets and preserved partial paths; remove the former NumPy NEB
  implementation and v1 entries. Old requests require preparation with v2 units.
- Add independent local geometry diagnostics, trajectory/mode illustrations and
  evidence-bound illustrated reports, plus practical search and failure-recovery guidance.

- Add authenticated Host `files/list`, `files/stat`, `files/read` and `files/pin`
  capabilities for CoRHub 0.20.0+64: bounded material browsing and version-checked
  file snapshots over the existing Link, without waking Pi or exposing state files.

- **0.19.0 breaking rename:** the product and repository are CoRAgent / `coragent`.
  Commands, package identities, services, installation metadata and environment
  variables use `coragent` / `CORAGENT_`; no legacy aliases or fallback readers.
  The internal Python import namespace remains `research_agent`.
- Host/Relay use `coragent-host/2`, `coragent-link.v1`, `cah_` and `cad_`.

- Updated the pinned Pi runtime and SDK packages to 1.1.0, retaining protocol 8
  and request admission with the new context API and token estimator.
- Research tool cards display recorded execution time, including after reconnect;
  Job submission time remains distinct from the background computation duration.
- Added general chemistry materials, mapping/conformer comparison, CREST ensembles,
  complex sampling, xTB/Gaussian scans and ASE NEB, QST2/QST3 preparation, and
  reaction-independent stationary-point/mode/IRC checks.
- Added thermochemistry and conformer free energies, multistep pathway checks,
  conditional TST/branching, and mass-action kinetic networks.
- Added bounded Gaussian TD/TDA calculations, supplied-tensor state tracking, and
  local different-spin crossing searches with independent numerical checks.
  Deterministic acceptance does not substitute for real-solver scientific benchmarks;
  see the [capability inventory](skills/chemical/method-selection/references/capabilities.md).
- Improved terminal slash completion, focus/draft preservation, semantic field colors,
  system-prompt rendering, and task/connection status in the Monitor row.
- Removed the retired ordinary-Pi runtime from the supported package surface;
  Native Pi Harness is the only runtime entrypoint.
- Clarified the Research Memory, bounded turn context, capability catalog, and
  Monitor wake-up boundaries.
- Added repository governance documents and automated Skill contract checks.
- Added the Apache-2.0 license and SPDX metadata for project-owned source.

There is no published release tag for this entry yet. Release notes must include
the package version, pinned Pi revision, migration notes, and the test lanes run.
