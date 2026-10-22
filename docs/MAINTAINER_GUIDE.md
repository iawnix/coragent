# Maintainer Guide

CoRAgent uses native Pi Harness. Host owns workspace routing and authentication; the SessionWorker owns durable input and task progression; Python Research Memory stores original requirements, problem Nodes, immutable Results and relations. `runtime-bridge` only transports commands; CoRAgent Web consumes the same read-only queries. See [architecture](ARCHITECTURE.md) for the current ownership boundaries.

## Development Setup

Install the pinned Pi source and the separate test environment with
`python3 tools/test/runner.py prepare`. It uses `tools/test/environment.lock.txt`
under `/home/iaw/project/TSPi/local_debug`. `CORAGENT_TEST_ENV_ROOT` can select a
subdirectory of that private root; local runs reject paths outside it.
The root `environment.lock.txt` belongs to the minimal Host and does not include
scientific or pytest dependencies. Run the fast test suite before changing package layout:

```bash
python3 tools/test/runner.py fast -- -q
npm run lint:public
```

The full suite uses `python3 tools/test/runner.py source -- -q`. Use
`python3 tools/test/runner.py list` to inspect all lanes. The native lane
exercises the Harness Host, native Pi client, session-history isolation, Job Manager
delivery, CoRAgent Link, and the pinned Pi extension/provider boundaries. Use the pinned dependencies prepared in the private test root:

```bash
python3 tools/test/runner.py prepare
python3 tools/test/runner.py check --changed
python3 tools/test/runner.py native-pi
python3 tools/test/runner.py verify
```

The runner creates immutable source snapshots, isolated workspaces and process ledgers under `local_debug/`. It disables outbound networking for deterministic tests, preserves failure evidence locally, and terminates all owned services. Do not upload these files, logs or credentials. `replay --run <id> --failed` repeats the recorded bytes and dependencies; `gc --dry-run` previews eligible cleanup.

The Native Pi Harness path does not require tmux and is the only supported
runtime. Backend selection is not configurable. Do not
substitute an unpinned or modified Pi checkout to make the lane pass. The manifest currently marks `remote-smoke`, `live-eval` and `live-recovery`
as unavailable: remote smoke has no executable scenario, and the live scenarios
use retired contracts. Configuration alone does not enable them. A future real-model
or remote acceptance run needs a current scenario and explicit external-test authorization.

The authoritative lane and path definition is `tools/test/manifest.toml`,
dispatched by `tools/test/runner.py`. Python tests are grouped under
`tests/unit/`, `tests/contract/`, and `tests/integration/`; Node tests live under
`tests/node/`; shared fixtures are under `tests/support/`. External probes and
live scenarios belong to `tools/test/probes/` and `tests/scenarios/` and
must not be added to the default Python suite.

## Research Memory and Execution Boundaries

`workspace_manifest.json` uses `research_workspace/3`. `research_agent.research` is the sole namespace, without a legacy state or global-progress protocol. Original messages, Node content revisions and runtime facts retain distinct origins. Stable Node directories preserve repeated attempts; immutable Results pin their basis.

Agent tools are research_read / research_search / research_create / research_update / research_result. Creation needs goal; a note needs node_id and note; publication needs node_id and conclusion. The trusted adapter supplies identities, read basis, revisions and transactions. Background Jobs do not change Node content revision. Relations are stored once with generated reverse queries. Actual uses requires proven inputs; search is not evidence adoption.

Job Manager owns execution receipts; Artifact Store owns bytes and provenance. Job Manager next_run delivery depends on event and delivery identity, never Memory sequence or checkpoint. Email receipts own deduplication; Memory failure cannot trigger resending. Old workspaces are rejected without migration or mixed writes.

## Repair research views

Inspect the workspace, rebuild derived views when the diagnostic identifies a projection problem, then inspect again:

```bash
"$CORAGENT_PYTHON" apps/agent-cli/workspace.py doctor --root /absolute/workspace
"$CORAGENT_PYTHON" apps/agent-cli/workspace.py rebuild --root /absolute/workspace
"$CORAGENT_PYTHON" apps/agent-cli/workspace.py doctor --root /absolute/workspace
```

Rebuild uses immutable records and results to restore Node/map indexes, search and readable views. It does not invent scientific results, change execution/email receipts or migrate old workspace formats. Missing or inconsistent originals require repairing the actual source. Use public tools for research changes; the CLI has no expected-version / observed-sequence global-progress arguments.

## Deterministic Tool Contracts

Scientific command builders and parsers live in
`skills/chemical/<skill>/scripts/`, with shared helpers in
`skills/chemical/_shared/`. Generic local and remote execution lives
in `backend/src/research_agent/jobs/`; `backend/src/research_agent/application/` records Job facts and registers
collected materials in Artifact Store. Public command fields are declared in
`contracts/commands/`; generated Python and Node catalogs are checked at build time. Every Artifact needs
a content digest and a verified location. Preserve earlier evidence when
recording scheduler state, Job identity, commands, and collection results.

## Scientific Analysis Maintenance

Independent analyses run Skill scripts through generic Jobs. Registered
validators and acceptance profiles are declared in `skills/chemical/execution.json`;
`backend/src/research_agent/application/validators.py` verifies and stages the
declared validator and inputs. Python owns execution catalog validation independently of Pi Skill discovery. Pi loads product and domain Skills from `package.json.pi.skills`; `scripts/update_resources.py` generates resource digests. New scientific algorithms require
bounded inputs, explicit applicability, counterexamples, replayable candidates
and a version change when deterministic output semantics change. Keep domain
schemas out of the always-loaded tools. Do not add scientific successor routing.

Job state and recovery belong to Job Manager. Preserve the
workspace transaction boundary around dispatch intentions, execution observations,
and collected evidence; keep inspection, collection and cancellation available.
Test the Native Harness client and Pi resource and scientific execution contracts,
Job Manager retry/acknowledgement behavior, wheel
installation, Memory Node/Result Web queries and retrieval, and source-tampering rejection.
Use the stable operations guide and focused test suites as the current evidence;
superseded plans and one-off reports remain in Git history. Unimplemented proposals
are labeled and indexed separately from current operating instructions.

Maintain English `SKILL.md` and Chinese translations together: English is the discovery entrypoint. See [Skills and the execution catalog](EXTENSIONS.md).

## Documentation Ownership

- `docs/ARCHITECTURE.md` — runtime and scientific boundaries.
- `docs/INSTALLATION.md` — installer, services, upgrades, and recovery.
- `docs/TERMINAL.md` — Native Pi TUI, Host, Phone, and Monitor usage.
- `skills/` and `skills/chemical/` — user-facing scientific procedures and references.
- `contracts/coragent-web/` — optional browser transport schemas for Memory context, Nodes, Results and records.

CoRHub documentation and mobile release tooling are maintained in the
independent `corhub` repository. CoRAgent owns the small authenticated Host bridge
and optional browser gateway; it must not add a second Pi renderer, Phone
broker, or alternate session owner.

## Contract Change Matrix

| Change | Required updates |
| --- | --- |
| CoRAgent Host protocol or service | `apps/agent/`, launcher tests, CoRHub client, architecture docs |
| Workspace schema | Research Memory runtime contract, bootstrap, validation tests, workspace references |
| Scientific software | Skill scripts/parsers, environment configuration, focused Skill references, tests |
| Scientific analysis | script, validator/profile manifest when applicable, input and output validation, scientific counterexamples, execution and Skill resource digests |
| Job execution and recovery | dispatch and receipt transactions, native tools, restart and reconciliation tests |
| Package inventory | `package.json`, `scripts/package_inventory.py`, package layout tests |
| Installer/service path | `scripts/install_wizard.py`, uninstall logic, installation docs |

## Release Procedure

1. Run the fast and full Python suites plus the native Harness/Host lane.
2. Build and validate the Agent release with `npm run release:agent`.
3. Build the optional Web component when requested by the release plan.
4. Build the suite package with `npm run release:build` and inspect its manifest.
5. Test installation into a fresh private directory and start one installation Host.

The package manifest, archive digest, selected Agent component, and Pi source
commit must agree. Never publish a dirty source tree or modify a release after
it has been content-addressed.

## Rollback Discipline

Stop the Host service, select a prior validated release under
`releases`, and restart the single Host. Workspace JSONL and
scientific records are independent of the package release and must not be
deleted during rollback.
