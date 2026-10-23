# TRI infrastructure operations

## Scope

This deployment guide uses installed TRI and system service commands. Job submission, resource translation, cancellation and recovery use [batch schedulers](../skills/core/batch-schedulers/SKILL.md).

[简体中文](TRI_OPERATIONS.zh-CN.md)

## Identify the installation

Locate `tri-server`, `tri-client` and `tri_node`, and record their build identity from installation metadata. Read `tri-client --help` and `tri_node --help` for installed options. The server entrypoint starts the service; inspect its service definition to identify it.

Identify the service owner and system/user service scope, socket/TCP endpoint, database path and registered nodes. Keep authentication tokens in their protected environment files. The CLI prefers an existing `TRI_SOCKET`, otherwise TCP through `TRI_SERVER_ADDR`.

## Deploy and maintain

[Service setup](#service-setup-and-maintenance) covers server/client installation, service units, shared paths, resource advertisement, acceptance, backups, upgrades and history retention. A single-host installation runs both server and client; multiple compute hosts register unique node names with the same queue server.

Use `tri_node --json` and `tri_node --check` to inspect registration, capacity, cgroups and the user manager. Inspect the identified server/client units and their journals. For connection failures, verify endpoint, ownership, service health and network connectivity. For protocol mismatch, compare server/CLI/client build identities. For an offline node, inspect its client service and heartbeat connection before changing advertised capacity.

## Verify maintenance

After a service or capacity change, check node registration, existing attempts and the bounded diagnostic Job in the setup reference. A login-host check does not establish compute-node software readiness; use the [per-node acceptance procedure](../skills/core/batch-schedulers/references/tri.md#verify-each-compute-node-and-backend) for that purpose.

Report affected services/nodes and verification results. Diagnose individual queued, failed, lost or cancelled Jobs through [TRI task diagnosis](../skills/core/batch-schedulers/references/tri-diagnosis.md), preserving their execution identities during maintenance.

## Service setup and maintenance

### Installation and topology

Use the selected TRI release or build its source with `cargo build --locked --release --bins`. Set `CARGO_HOME` and `CARGO_TARGET_DIR` to the installation/build area; use the repository's private test area for test builds. Install `tri-server`, `tri-client` and the `tri_*` tools from the same build. Keep the old binaries and service configuration for rollback.

One server owns the queue database. Each participating compute host runs a client with a unique node name; a single-host installation runs both. Run CLI diagnostics on the server host or configure its TCP address. Multi-host jobs need matching input, output and executable paths, usually through a shared filesystem. Keep the SQLite database on the server's local disk.

### Explicit environment configuration

Set absolute paths before starting the server. `TRI_DATA_DIR` defaults to `./data`, and `TRI_DB` defaults to `TRI_DATA_DIR/tri.db`; explicit settings make service restarts independent of the launch directory.

| Process | Settings |
| --- | --- |
| Server | `TRI_SOCKET`, `TRI_SERVER_ADDR`, `TRI_DATA_DIR`, `TRI_DB`, `TRI_AUTH_TOKEN` |
| Compute client | `TRI_SERVER_ADDR`, `TRI_AUTH_TOKEN`, `TRI_NODE`, `TRI_NODE_ADDRESS`, `TRI_NODE_CPUS`, `TRI_NODE_MEMORY`, `TRI_NODE_GPUS`, `TRI_NODE_SCRATCH` |
| CLI | `TRI_SOCKET` for a local server; `TRI_SERVER_ADDR` and `TRI_AUTH_TOKEN` for TCP |

Store server/client settings in separate environment files readable by the service owner (mode `0600`). Systemd `EnvironmentFile` values use literal absolute paths, not shell expansions. Set the same random token for the server and TCP clients. Bind a single-host deployment to loopback; use a private address and restrict TCP access to participating hosts for a cluster.

Advertise CPUs, memory and GPUs actually available to the queue, reserving resources for other applications. Set a writable node-local `TRI_NODE_SCRATCH`. GPU clients discover device paths; use `TRI_NODE_GPU_DEVICES` for nonstandard devices. Allocated tasks receive CPU sets, GPU visibility/device rules and, when requested, a cgroup memory limit.

### Service definitions

First identify existing units with `systemctl --user list-unit-files 'tri*'` and `systemctl list-unit-files 'tri*'`. Match the deployed service scope when inspecting or changing units. Task execution may use a system-managed execution account or a delegated user manager. Follow the installed TRI version and service configuration; the client service scope alone does not establish the task scope.

For a new user-service installation, this server template goes in the selected user's systemd unit directory. Replace `/ABS/TRI_BIN` with the installed binary directory and create the referenced environment file first:

```ini
[Unit]
Description=TRI queue server
[Service]
Type=simple
EnvironmentFile=%h/.config/tri/server.env
ExecStart=/ABS/TRI_BIN/tri-server
Restart=on-failure
RestartSec=2
UMask=0077
[Install]
WantedBy=default.target
```

Create a corresponding `tri-client.service` using `client.env` and `tri-client` in the two relevant lines. Each host gets its own client configuration. Start the server, then clients, after `systemctl --user daemon-reload`. For persistent user services, configure login linger for the service account as part of host provisioning. On compute hosts verify cgroup v2, the user manager and cpuset/CPU/memory controllers with `tri_node --check`.

Read service logs using `journalctl --user -u "$TRI_UNIT" -n 100 --no-pager` for user units, or the corresponding system journal for system units. Use actual discovered unit names.

### Acceptance and resource changes

After `tri_node --check` succeeds, choose an absolute shared diagnostic directory `TRI_CHECK_DIR` and a fresh, installation-scoped `TRI_CHECK_ID`. Create the directory, then submit:

```bash
tri_sub --json --name ops-check --request-id "$TRI_CHECK_ID" \
  --chdir "$TRI_CHECK_DIR" --cpu 1 --mem 64M --timeout 30 \
  --output 'tri-%j.out' --error 'tri-%j.err' -- /bin/echo tri-ready
```

Use the returned task ID to inspect status and logs. Completion is `done`, exit code zero and `tri-ready` in the output. This exercises node dispatch and output visibility. To change advertised capacity, update the relevant client environment and restart that client during the chosen maintenance window; verify the reported totals and existing task attempts afterward. Requests larger than any node's available capacity remain waiting.

For development tests, set socket, server address, database, data, scratch, build/cache and evidence paths to an isolated test setup. In this repository all test files belong under `local_debug/`. Use a distinct endpoint and node identity, and stop/remove the test services after checking task units have exited.

### Upgrade, backup and CoRAgent integration

Record active tasks and attempts before an upgrade. Take a consistent SQLite backup using the SQLite backup API, or stop the server for an offline backup that preserves its SQLite sidecar state. Preserve configuration and binary versions. Coordinate server/client upgrades because every request checks protocol compatibility. After restart, check node registration, existing attempts and the diagnostic job. For rollback, check database compatibility with the previous binary; restoring a historical database requires reconciling tasks launched since that snapshot.

CoRAgent Job integration and per-node software acceptance are documented in [batch schedulers](../skills/core/batch-schedulers/references/tri.md).

### History retention

For requested history maintenance, select a retention window and collect the needed Job outputs/receipts first. `tri_clean --json --older-than SECONDS` removes old terminal records; the default window is 30 days. Cleanup also removes idempotency receipts, so retrying a cleaned request can create a new task. Choose the retention window to cover outstanding workflow recovery and retry needs; use `--all` only for an explicitly selected complete terminal-history removal.
