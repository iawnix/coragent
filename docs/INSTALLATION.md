# Installation and configuration

CoRAgent uses one operator-owned `config.toml` and an adjacent private
`credentials.json`. The new layout does not read the retired installation-root
`etc/` or `var/` directories and does not migrate or remove existing deployments.

## Layout

| Content | Default location |
| --- | --- |
| Releases, Pi and Host environments | `~/soft/coragent/` |
| Configuration and credentials | `~/soft/coragent/config/` |
| Installation receipts, Host state, sessions, logs and caches | `~/soft/coragent/state/` |
| Research workspaces and Job files | `~/DATA/coragent/workspaces/` |

Configure `paths.software_root`, `paths.state_root` and `paths.workspace_root`.
The selected configuration file determines its configuration directory. These roots
must be dedicated directories; configuration and state may use the software root’s `config/` and `state/` children. Research workspaces remain separate. Configured data aliases are normalized;
workspace-internal path validation remains enforced. Installation ownership binds
the software root, configuration file and local state root. Relocation requires
explicit redeployment.

The software root contains an `installation.json` locator without credentials.
By default it also contains `config/`, `state/`, `generated/`, `jobs/` and `backups/`.
With an external `paths.state_root`, `generated/`, `jobs/` and `backups/` live
under that state root. Configuration follows the selected `--config` path.
Local state contains `installation/`, `host/`, `pi/sessions/`, `logs/` and `cache/`.
`generated/` and `pi/agent/models.json` are generated component inputs, never a
second operator-owned configuration source.
The flow is one way: validate the installation candidate, save `config.toml` and
`credentials.json`, then derive component inputs. Generated files are never read
back to infer user settings.

## Configuration

Use [config.example.toml](../config/config.example.toml) and
[credentials.example.json](../config/credentials.example.json), adjusting absolute
paths to the service account. Keep configuration directories private (0700) and
credentials at 0600.

Sections cover paths, service and Web settings, models, execution targets,
notifications, optional name resolution and remote terminal profiles. Merge the
`[execution]` table from `config/job.execution.example.toml` directly; do not nest
an additional `execution` table. `models.providers` uses native Pi provider definitions.

Execution, email and online name lookup are optional. An installation without
those settings can create workspaces, maintain research records and run research
tasks. It does not create a Qrun pool or enable PubChem/OPSIN. Bind a platform and
scheduler entry when a task first needs calculation; ordinary shell commands stay
local. Structure input and local graph checks do not require an online resolver.

Startup checks the core configuration and records optional component errors in
`generated/configuration-status.json`. A malformed optional configuration is
reported as unavailable for that operation; it is not silently replaced by a
different service. Ordinary startup does not probe SMTP, SSH or HTTP services.
Installation validates configured components before activation, while each
operation checks the external resources it needs.

Credentials have `models` and `secrets` objects. `models` contains native Pi
provider credentials, including refreshed OAuth credentials. `secrets` contains
named strings; reference them as `credential:NAME` in configuration fields.
For SMTP, set `notifications.email.password = "credential:smtp_password"`, or use
an explicit external `password_file`/`password_env`. External credential files are
not removed during uninstall. Pi updates its credential section under the canonical
file lock while preserving other sections; startup never copies stale auth back.
In a model's `thinkingLevelMap`, use `false` for an unsupported thinking level;
generated Pi configuration restores its native `null` value.

`password_env` names an external variable in the running Host's environment;
installation never captures its value into generated files or credentials.
Generated systemd units use `PassEnvironment=NAME`. For a user service, supply
the value to the user manager, for example with `systemctl --user set-environment
NAME=VALUE`, then restart `coragent.service`. Choose an injection method that
keeps the secret out of shell history. A shell export alone does not update an
already running systemd manager or Host. To keep an installation-owned password,
import a private password file or enter it interactively; these use credentials.json.

## Install and update

```sh
./install.sh --config /absolute/path/config.toml --dry-run
./install.sh --source local --config /absolute/path/config.toml
```

The default source is GitHub. `--source local` uses a local checkout;
`--source package` consumes a complete release package. Add
`--non-interactive --yes` for unattended installation. Preview neither installs
nor starts services and does not print credentials.

The installer prepares CoRAgent's own Python/Pi runtime and generated services,
and checks configured execution bindings. Prepare scientific environments
separately and bind their paths in `execution.platforms.<platform>.bindings`
(or an entry override). The core installer does not provision scientific environments.
Platform selection and Qrun options use `PLATFORM/ENTRY`; see [execution platforms](EXECUTION_PLATFORMS.md). See
[Scientific operations](SCIENTIFIC_CAPABILITIES_OPERATIONS.md) for environment preparation.

There is no implicit import from `~/.pi/agent`. Explicit one-time component
imports use `--import-config DIRECTORY`, `--agent-config-dir`, `--job-config` or
`--name-resolver-config`. Imported inputs are consolidated into the main
configuration; their original files are not runtime configuration sources.
An explicitly imported SMTP password file is copied into the private credentials
store as a named secret, and the main configuration retains its reference.
Imported model definitions are stored in `config.toml`; provider authentication
is stored in `credentials.json`. Editing a generated file cannot override them.

To use online chemical name lookup, import the desired resolver configuration
with `--name-resolver-config` or configure `[name_resolver]` directly. Bind
`CORAGENT_NAME_RESOLVER_CONFIG` explicitly in the structure backend's environment.
Its path must be readable on the selected platform; local settings do not imply
a remote path or enable an external service automatically.

Restart the Host after changing model or notification configuration. Rerun the
installer to apply service settings such as service scope or Web listen addresses.
Updates use the same configuration and a local maintenance record. Failures before
activation restore the prior release and configuration; failures after activation
retain the new state and require rerunning the installer for forward repair.

```sh
python3 /absolute/coragent/current/agent/packaging/coragent_packaging/installer/app_layout_doctor.py \
  --config /absolute/path/config.toml --json
```

Replace `/absolute/coragent` with the software root. From a source checkout,
use `packaging/coragent_packaging/installer/app_layout_doctor.py` relative to that checkout.

## Cluster boundary

TRI is independently deployed cluster infrastructure. CoRAgent submits, queries
and cancels Jobs through its external handler; it does not manage TRI servers,
clients, node registration, cluster authentication or queue databases.

Install shared software once on its writable host and validate it separately on
each compute node. Keep caches and scratch node-local. An online TRI node does
not imply that every scientific backend is available. See
[EXTERNAL_JOBS.md](EXTERNAL_JOBS.md) for the current submission interface.

Job records remain under each workspace's `runs/jobs/<job-id>/`. External targets
can use `file_mode="shared"` to execute there directly; staging remains the default.
See [external Jobs](EXTERNAL_JOBS.md) for storage checks and configuration.

After an execution entry explicitly selects local Qrun with its default handler,
the main installer can provision that pool. An installation without execution
configuration creates no queue. Enroll SSH queues explicitly with
`--manage-qrun PLATFORM/ENTRY` and state-directory/CPU/memory options. Local targets
share a pool; code upgrades require drained queues.
Use `qrun config` for online CPU/memory budget changes without draining jobs;
upgrades preserve this budget unless capacity flags are explicitly supplied. See
[Qrun installation and operations](QRUN.md) for examples and prerequisites.

## Uninstall

```sh
./uninstall.sh --config /absolute/path/config.toml
```

Default uninstall removes application releases and matching services while
preserving configuration, sessions and research workspaces. `--purge-config`
removes the selected configuration, credentials and generated inputs;
`--purge-workspaces` explicitly removes workspaces, sessions and local managed Job files;
`--purge-runtime` only removes CoRAgent-owned runtime environments with matching
ownership records. Scientific environments and TRI remain independently managed.
Owned local and SSH Qrun services are removed, retaining queue history and
calculation directories by default. Unfinished Jobs block removal unless
`--cancel-qrun-jobs` is supplied. `--purge-qrun-state` deletes queue history;
`--purge-all` includes history cleanup but does not imply Job cancellation.
Configuration cleanup does not recursively delete unrelated files in its parent.
The necessary parser modules are installed with the uninstaller, so removing the
source checkout does not prevent uninstall.

## Local verification

Keep every test installation, dependency environment, cache, temporary file and
artifact under repository `local_debug/`. Use deterministic local models and fake
credentials, stop and remove test services, and never publish the private test root
in Git, packages, external caches or attachments.

Backups are retained unless `--purge-backups` or `--purge-all` is selected. `--remove-root` also requires backup and Qrun state purge flags when those retained data exist inside the root. Ordinary uninstall preserves nested configuration, Job data and queue history.
