# CoRAgent installation layout

[English](APP_LAYOUT.md) | [简体中文](APP_LAYOUT.zh-CN.md)

By default, an installation keeps configuration and mutable data beneath its software root. Research workspaces remain separate. `config.toml` selects the software,
local state and workspace roots; its own location selects the configuration directory.
The canonical implementation is `backend/src/research_agent/bootstrap/layout.py`.

| Root | Default | Configuration |
| --- | --- | --- |
| Software | `~/soft/coragent/` | `paths.software_root` |
| Configuration | `~/soft/coragent/config/` | Installer `--config`, runtime `CORAGENT_CONFIG` |
| Local state | `~/soft/coragent/state/` | `paths.state_root` |
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
  config/                   # configuration directory below
  state/                    # state root below
  generated/                # generated component configuration
  jobs/                     # local Qrun calculation files
  backups/                  # retained installation backups

<configuration_directory>/
  config.toml               # operator-owned settings
  credentials.json          # model credentials and named secrets

<state_root>/
  installation/             # installation identity and environment receipts
  host/                     # Host identity, Link token, leases and worker health
  pi/sessions/              # Pi durable SQLite sessions
  pi/agent/                 # Pi settings and generated model definitions
  qrun/                     # local queue database and service state
  logs/
  cache/

<workspace_root>/<name>/
  workspace_manifest.json
  research/
  runs/jobs/
  operations/
  artifacts/
```

The tree shows the default layout. If `paths.state_root` is outside the software
root, `generated/`, `jobs/` and `backups/` live under that state root instead.
Use the layout doctor below to obtain the resolved paths. A platform's configured
`storage.work_root` still determines its execution files; `jobs/` is not an
implicit replacement for that setting.

Edit `config.toml` and adjacent `credentials.json`. `generated/job.toml`,
`generated/email.toml`, `generated/name-resolver.toml` and `pi/agent/models.json`
are materialized component inputs (`pi/agent` remains under the state root). Editing them does not
update the operator configuration; the next materialization can replace them.
Runtime commands receive `CORAGENT_JOB_CONFIG` and the other resolved paths.
Explicit component imports first update the main configuration and credentials;
they do not establish another configuration source. Optional email and execution
errors are recorded in `generated/configuration-status.json` without secret values.
This status file is diagnostic output, not configuration. Missing optional settings
do not prevent research startup and do not create queue or resolver services.

Host Python bases and wheel overlays use
`<env_root>/<installation-id>/{base,kernels}/<hash>`.
`runtime.env_root` selects a dedicated store; the installer also accepts
`CORAGENT_HOST_ENV_ROOT`. Scientific interpreters and programs are configured
separately under `execution.platforms.<platform>.schedulers.<entry>.bindings` in `config.toml`.

Sockets and process locks use the installation-scoped system runtime directory.
Pi session history lives at
`<state_root>/pi/sessions/<workspace-id>/<session-id>/session.sqlite`, with adjacent
`meta.json`. Research files remain in the workspace across session changes.

Inspect resolved paths without changing the installation. Run from a source
checkout or the installed package root, `<software_root>/current/agent`:

```bash
python3 -B packaging/coragent_packaging/installer/app_layout_doctor.py --config /absolute/path/config.toml --json
```

The layout schema is `coragent-installation/3`. Old installation-root `etc/`,
`var/`, `.pi/` and `.agents/` layouts are not migrated. Keep their data when
redeploying into the current layout. Uninstall options and ownership rules are
documented in [Installation](INSTALLATION.md).

Existing installations with separate configuration and state roots retain those paths. Only the dedicated `config/` and `state/` children may overlap the software root; data must never live in `releases/` or `current`. Moving an existing installation requires stopping its services and updating ownership records, queue configuration and service paths together.
