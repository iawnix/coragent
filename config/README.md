# CoRAgent configuration

Maintain one `config.toml` and an adjacent private `credentials.json`. Start from
[config.example.toml](config.example.toml) and [credentials.example.json](credentials.example.json).
Do not commit the actual files; package builds exclude both names under this directory.

`config.toml` contains `paths`, `service`, `web`, `models`, `execution`,
`notifications`, optional `name_resolver`, `remote_host`, `phone`, and `runtime`
sections. Paths are absolute; the configuration directory is the parent of the
selected file. `execution` uses the target schema from
[job.execution.example.toml](job.execution.example.toml), without another nested
`execution` table. `models.providers` uses Pi provider definitions.

For local or SSH queues backed by systemd, see
[job.qrun.example.toml](job.qrun.example.toml) and the [Qrun guide](../docs/QRUN.md).
Every target selects `transport` and `executor` independently. Bare-host Jobs use
Qrun; the old driver/supervisor configuration and direct executors have been removed.

`credentials.json` has two objects: `models` holds native Pi provider credentials
(including refreshed OAuth credentials), and `secrets` holds named strings.
Use `credential:NAME` in a secret-valued configuration field to reference a named
string. For SMTP, use `password = "credential:smtp_password"`, or an explicit
external `password_file`/`password_env`. Files must be private (0600); directories
should be 0700. Pi updates only the `models` object under its credential lock,
preserving notification and execution credentials.

```sh
./install.sh --config /absolute/path/config.toml --dry-run
./install.sh --config /absolute/path/config.toml
./uninstall.sh --config /absolute/path/config.toml
```

The installer never implicitly imports `~/.pi/agent`. The optional
`--import-config DIRECTORY` is an explicit one-time import of component files;
`--agent-config-dir`, `--job-config`, and `--name-resolver-config` also explicitly
import inputs. They are consolidated into the main configuration during install.
Imported files remain owned by their original owner. Normal operation reads only
the main configuration and credentials, not the import directory.

Component files under the configured local state directory are generated inputs.
Do not edit them: startup regenerates them from `config.toml`. Installation receipts,
service identity, sessions, logs and caches are machine-managed state, not extra
operator configuration. See [installation](../docs/INSTALLATION.md).
