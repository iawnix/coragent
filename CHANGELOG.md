# Changelog

This file records user-visible changes. Current architecture is documented in
[the architecture guide](docs/ARCHITECTURE.md); earlier designs remain in Git history.

## Unreleased

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
  complex sampling, xTB/Gaussian scans and NumPy NEB, QST2/QST3 preparation, and
  reaction-independent stationary-point/mode/IRC checks.
- Added thermochemistry and conformer free energies, multistep pathway checks,
  conditional TST/branching, and mass-action kinetic networks.
- Added bounded Gaussian TD/TDA calculations, supplied-tensor state tracking, and
  local different-spin crossing searches with independent numerical checks.
  Deterministic acceptance does not substitute for real-solver scientific benchmarks;
  see the [capability inventory](domains/chemical/skills/method-selection/references/capabilities.md).
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
