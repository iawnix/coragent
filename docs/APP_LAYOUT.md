# CoRAgent installation layout

[English](APP_LAYOUT.md) | [简体中文](APP_LAYOUT.zh-CN.md)

An installation has four separate roots. `config.toml` selects the software,
local state and workspace roots; its own location selects the configuration directory.
The canonical implementation is `backend/src/research_agent/foundation/layout.py`.

| Root | Default | Configuration |
| --- | --- | --- |
| Software | `~/soft/coragent/` | `paths.software_root` |
| Configuration | `~/.config/coragent/` | Installer `--config`, runtime `CORAGENT_CONFIG` |
| Local state | `~/.local/state/coragent/` | `paths.state_root` |
| Research workspaces | `~/DATA/coragent/workspaces/` | `paths.workspace_root` |

```text
<software_root>/
  coragent
  uninstall.sh
  installation.json          # locator: configuration and state roots
  current -> releases/<id>
  releases/<id>/             # application code and bundled Skills
  runtimes/pi/<commit>/      # pinned Pi runtime
  runtimes/maintenance/      # independent uninstall/recovery code
  host-envs/                 # default Host Python environment store

<configuration_directory>/
  config.toml               # operator-owned settings
  credentials.json          # model credentials and named secrets

<state_root>/
  installation/             # installation identity and environment receipts
  host/                     # Host identity, Link token, leases and worker health
  pi/sessions/              # Pi durable SQLite sessions
  pi/agent/                 # Pi settings and generated model definitions
  generated/                # generated component configuration
  logs/
  cache/

<workspace_root>/<name>/
  workspace_manifest.json
  research/
  runs/jobs/
  operations/
  artifacts/
```

Edit `config.toml` and adjacent `credentials.json`. `generated/job.toml`,
`generated/email.toml`, `generated/name-resolver.toml` and `pi/agent/models.json`
are materialized component inputs under the state root. Editing them does not
update the operator configuration; the next materialization can replace them.
Runtime commands receive `CORAGENT_JOB_CONFIG` and the other resolved paths.

Host Python bases and wheel overlays use
`<env_root>/<installation-id>/{base,kernels}/<hash>`.
`runtime.env_root` selects a dedicated store; the installer also accepts
`CORAGENT_HOST_ENV_ROOT`. Scientific interpreters and programs are configured
separately under `execution.targets.<target>.bindings` in `config.toml`.

Sockets and process locks use the installation-scoped system runtime directory.
Pi session history lives at
`<state_root>/pi/sessions/<workspace-id>/<session-id>/session.sqlite`, with adjacent
`meta.json`. Research files remain in the workspace across session changes.

Inspect resolved paths without changing the installation:

```bash
python3 -B scripts/app_layout_doctor.py --config /absolute/path/config.toml --json
```

The layout schema is `coragent-installation/3`. Old installation-root `etc/`,
`var/`, `.pi/` and `.agents/` layouts are not migrated. Keep their data when
redeploying into the current layout. Uninstall options and ownership rules are
documented in [Installation](INSTALLATION.md).
