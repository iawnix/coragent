# Source ownership

[简体中文](SOURCE_LAYOUT.zh-CN.md)

CoRAgent uses one Pi Harness. This layout separates runtime ownership from installation and development tooling without changing workspace formats, public command identities or transaction semantics.

| Directory | Responsibility |
| --- | --- |
| `apps/agent/` | Pi Agent, Host, terminal, task policy, research context and model tools |
| `apps/cli/` | Thin Python entrypoints and managed-interpreter selection |
| `libexec/` | The `coragent-host` service launcher |
| `apps/web/` | Optional, independently released research browser |
| `apps/relay/` | Independently deployed Link relay |
| `backend/src/research_agent/` | One Python business package |
| `packages/link/` | Shared transport library |
| `skills/core/`, `skills/chemical/` | Workflow and scientific knowledge, scripts and references |
| `contracts/` | Shared interface source definitions |
| `config/` | Operator configuration examples, schemas and documentation |
| `packaging/coragent_packaging/installer/` | Install, upgrade, environment preparation and uninstall |
| `packaging/coragent_packaging/build/` | Source capture, wheel/release builds and package checks; excluded from product releases |
| `packaging/coragent_packaging/manifests/` | Release layout, identity, resource inventory and archive contracts |
| `packaging/coragent_packaging/pi/` | Pinned Pi source, patches and preparation |
| `tools/` | Generators, static gates, version maintenance and test runner |
| `tests/` | All tests, owned by `tools/test/manifest.toml` |
| `docs/`, `assets/` | Documentation and product assets |
| `local_debug/` | Private test environments, caches, installations and evidence; never commit, package or upload |
| `dist/` | Generated release artifacts |

## Runtime boundaries

`apps/agent/runtime/` assembles Pi and owns Worker integration and input admission. `runtime/source.mjs` is the only importer of Pi internal source paths. Public Pi APIs can be used directly by their owning modules.

`host/` handles authentication, routing, connections and process supervision. It does not own Pi durable documents or a second task state machine. `runtime/admission/` uses the existing Pi transaction to record provenance and accept input together.

`tasks/` owns research-task policy. Its controller uses Pi durable documents directly; assessment, recovery, execution selection/planning and projection remain independent of session infrastructure. Pi owns the model/tool loop, submissions and session recovery. `context/`, `tools/`, `bridge/`, `terminal/`, `transport/` and `prompts/` own their respective integration surfaces.

The Python `application/` layer dispatches commands and coordinates `research/`, `jobs/` and `artifacts/`. Research records do not depend on execution or application policy. Configuration parsing belongs to `configuration/`; installation layout and runtime startup belong to `bootstrap/`. `foundation/` contains file IO, transactions, protocol identity and path safety. The backend never imports CLI, installation, build or development tools.

## Delivery and generated files

CLI interpreter selection lives in `apps/cli/_bootstrap.py`. Installed business commands import their verified wheel after interpreter selection. Pre-install bootstrap belongs to the installer and uses standard-library modules.

Source `libexec/coragent-host` ships inside the Agent release at
`current/agent/libexec/`. The installer generates a separate installation-root
`libexec/maintenance/` bundle for independent uninstall and its required modules.
Maintain its source in `packaging/coragent_packaging/installer/` and the other owning
directories. See [installation layout](APP_LAYOUT.md) for the installed paths.

`packaging/` is deliberately not a Python package, so it does not shadow the third-party `packaging` library. Tools use the unique `coragent_packaging` namespace, grouped into `installer`, `build`, `manifests` and `pi`, so scientific scripts with names such as `build` cannot shadow packaging modules. Direct tooling entrypoints establish their source import paths; product applications do not import these tools.

`packaging/coragent_packaging/manifests/source-layout.json` is the single source of release membership; `tools/layout.py` generates npm's file list. Source installations can invoke the source build tools. Release installations consume the bundled verified wheel. Web optionality and Relay deployment are release choices, independent of their source location.

`tools/generate_contracts.py` produces command catalogs, Node types, schemas and test examples from `contracts/`. Runtime copies remain beside their consumers and must not be edited independently. `tools/layout.py` generates identity copies and `tools/update_resources.py` generates resource digests. All generators have checked outputs in the static suite.

Run `python3 tools/test/runner.py verify`, then accept a complete package with `release --artifact ...` outside the source directory. Architecture checks reject retired implementations, reverse dependencies on delivery tools, Host-owned durable state and scattered Pi source imports. No old-path shims, alternate protocols or duplicate transaction APIs are provided.
