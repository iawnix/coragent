# CoRAgent configuration

Maintain one `config.toml` and an adjacent private `credentials.json`. Start from
[config.example.toml](config.example.toml) and [credentials.example.json](credentials.example.json).
Do not commit the actual files; package builds exclude both names under this directory.

`config.toml` contains `paths`, `service`, `web`, `models`, optional `execution`,
`notifications`, `name_resolver`, `remote_host`, `phone`, and `runtime`
sections. Paths are absolute; the configuration directory is the parent of the
selected file. `execution` uses the target schema from
[job.execution.example.toml](job.execution.example.toml), without another nested
`execution` table. `models.providers` uses Pi provider definitions.

Research tasks, workspaces and records do not require execution, email or online
name resolution. No Qrun pool or PubChem/OPSIN configuration is added when those
sections are absent. Bind a platform and scheduler entry when a task first needs
calculation; ordinary shell commands remain local.

For local or SSH Qrun queues, see
[job.qrun.example.toml](job.qrun.example.toml) and the [Qrun guide](../docs/QRUN.md).
Platforms select `transport`; their scheduler entries select `executor`. Bare-host Jobs use
Qrun; the old driver/supervisor configuration and direct executors have been removed.

`credentials.json` has two objects: `models` holds native Pi provider credentials
(including refreshed OAuth credentials), and `secrets` holds named strings.
Use `credential:NAME` in a secret-valued configuration field to reference a named
string. For SMTP, use `password = "credential:smtp_password"`, or an explicit
external `password_file`/`password_env`. Files must be private (0600); directories
should be 0700. Pi updates only the `models` object under its credential lock,
preserving notification and execution credentials.

OpenAI-compatible gateways that route requests across an account pool should set
session affinity on every model in that provider:

```json
{
  "compat": {
    "sendSessionAffinityHeaders": true,
    "sessionAffinityFormat": "openai"
  }
}
```

Pi then sends the CoRAgent session ID as `session_id`, `x-client-request-id`, and
`x-session-affinity`. This keeps a multi-turn session on one gateway account when
the gateway supports those headers. It does not guarantee a KV-cache hit at the
final upstream model.

### Local request capture for debugging

Set `CORAGENT_REQUEST_CAPTURE=1` in the host service environment and restart the
service to capture subsequent OpenAI Chat Completions and Responses requests.
The default is off. It also enables the lightweight `request-cache.jsonl` diagnostics.
Each session stores one gzip-compressed JSON file per HTTP attempt under
`state/pi/sessions/<workspace>/<session>/request-bodies/`. The archive contains
the exact outgoing body string in `body`, model and request metadata, and an
allowlist of content-type and session-affinity headers. Authentication headers,
cookies, URL credentials and query strings are omitted. The body itself is **not
redacted**: prompts, skills, tool definitions, conversation history and any secrets
already present in that content remain in the private archive.

Files use mode 0600 and the capture directory uses 0700. Nothing is uploaded.
Archives are written before sending the request; capture failures are recorded as
`request_capture.status=error` without preventing model requests. The lightweight
log links attempts and response usage through `request_id`, `attempt` and
`request_capture.file`. Main generations and auxiliary requests are distinguished
by `purpose`. These are client-side requests, not a gateway's converted payloads.

Capture adds local compression and disk I/O to each request. Full archives are
not automatically rotated or deleted; watch disk usage and disable capture after
debugging by removing the environment variable and restarting the service.
Previously sent requests cannot be recovered. To inspect an archive locally:

```sh
gzip -dc /absolute/path/to/attempt.request.json.gz | jq '.body | fromjson'
```

```sh
./install.sh --config /absolute/path/config.toml --dry-run
./install.sh --config /absolute/path/config.toml
./uninstall.sh --config /absolute/path/config.toml
```

The installer never implicitly imports `~/.pi/agent`. The optional
`--import-config DIRECTORY` is an explicit one-time import of component files;
`--agent-config-dir`, `--job-config`, and `--name-resolver-config` also explicitly
import inputs. They are consolidated into the main configuration during install.
Explicit SMTP password-file imports store the secret in `credentials.json` and
write a credential reference into `config.toml`. Imported files remain owned by their original owner. Normal operation reads only
the main configuration and credentials, not the import directory.

Configuration flows in one direction: `config.toml` and `credentials.json` produce
`generated/` component files and Pi model definitions. Installation never imports
these generated files implicitly. Startup regenerates them; edit the primary files.
Optional configuration errors are recorded in `generated/configuration-status.json`
and reported for the affected operation. Startup does not probe SMTP, SSH or resolver
HTTP services; installation validates explicitly configured components before activation.
Installation receipts,
service identity, sessions, logs and caches are machine-managed state, not extra
operator configuration. See [installation](../docs/INSTALLATION.md).
