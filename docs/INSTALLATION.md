# Installation and configuration

CoRAgent uses one operator-owned `config.toml` and an adjacent private
`credentials.json`. The new layout does not read the retired installation-root
`etc/` or `var/` directories and does not migrate or remove existing deployments.

## Layout

| Content | Default location |
| --- | --- |
| Releases, Pi and Host environments | `~/soft/coragent/` |
| Configuration and credentials | `~/.config/coragent/` |
| Installation receipts, Host state, sessions, logs and caches | `~/.local/state/coragent/` |
| Research workspaces and Job files | `~/DATA/coragent/workspaces/` |

Configure `paths.software_root`, `paths.state_root` and `paths.workspace_root`.
The selected configuration file determines its configuration directory. These roots
must be separate dedicated directories. Configured data aliases are normalized;
workspace-internal path validation remains enforced. Installation ownership binds
the software root, configuration file and local state root. Relocation requires
explicit redeployment.

The software root contains an `installation.json` locator without credentials.
Local state contains `installation/`, `host/`, `pi/sessions/`, `logs/` and `cache/`.
`generated/` and `pi/agent/models.json` are generated component inputs, never a
second operator-owned configuration source.

## Configuration

Use [config.example.toml](../config/config.example.toml) and
[credentials.example.json](../config/credentials.example.json), adjusting absolute
paths to the service account. Keep configuration directories private (0700) and
credentials at 0600.

Sections cover paths, service and Web settings, models, execution targets,
notifications, optional name resolution and remote terminal profiles. Merge the
`[execution]` table from `config/job.execution.example.toml` directly; do not nest
an additional `execution` table. `models.providers` uses native Pi provider definitions.

Credentials have `models` and `secrets` objects. `models` contains native Pi
provider credentials, including refreshed OAuth credentials. `secrets` contains
named strings; reference them as `credential:NAME` in configuration fields.
For SMTP, set `notifications.email.password = "credential:smtp_password"`, or use
an explicit external `password_file`/`password_env`. External credential files are
not removed during uninstall. Pi updates its credential section under the canonical
file lock while preserving other sections; startup never copies stale auth back.
In a model's `thinkingLevelMap`, use `false` for an unsupported thinking level;
generated Pi configuration restores its native `null` value.

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
separately and bind their paths in `execution.targets.*.bindings`, or explicitly
select installer profiles with `--job-profile TARGET:PROFILE`. Core installation
does not provision scientific environments by default. See
[Scientific operations](SCIENTIFIC_CAPABILITIES_OPERATIONS.md) for environment preparation.

There is no implicit import from `~/.pi/agent`. Explicit one-time component
imports use `--import-config DIRECTORY`, `--agent-config-dir`, `--job-config` or
`--name-resolver-config`. Imported inputs are consolidated into the main
configuration; their original files are not runtime configuration sources.

Restart the Host after changing model or notification configuration. Rerun the
installer to apply service settings such as service scope or Web listen addresses.
Updates use the same configuration and a local maintenance record. Failures before
activation restore the prior release and configuration; failures after activation
retain the new state and require rerunning the installer for forward repair.

```sh
python3 scripts/app_layout_doctor.py --config /absolute/path/config.toml --json
```

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

## Uninstall

```sh
./uninstall.sh --config /absolute/path/config.toml
```

Default uninstall removes application releases and matching services while
preserving configuration, sessions and research workspaces. `--purge-config`
removes the selected configuration, credentials and generated inputs;
`--purge-workspaces` explicitly removes workspaces and sessions;
`--purge-runtime` only removes CoRAgent-owned runtime environments with matching
ownership records. Scientific environments and TRI remain independently managed.
Configuration cleanup does not recursively delete unrelated files in its parent.
The necessary parser modules are installed with the uninstaller, so removing the
source checkout does not prevent uninstall.

## Local verification

Keep every test installation, dependency environment, cache, temporary file and
artifact under repository `local_debug/`. Use deterministic local models and fake
credentials, stop and remove test services, and never publish the private test root
in Git, packages, external caches or attachments.
