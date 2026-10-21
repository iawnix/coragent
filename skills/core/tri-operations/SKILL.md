---
name: tri-operations
description: Deploy and maintain TRI queue servers and compute-node clients, configure connectivity and node capacity, and manage service health, database retention, backups and upgrades.
---

# TRI infrastructure operations

## Script routing

This Skill uses installed TRI and system service commands. Job submission, resource translation, cancellation and recovery use [batch schedulers](../batch-schedulers/SKILL.md).

[简体中文](SKILL.zh-CN.md)

## Identify the installation

Locate `tri-server`, `tri-client` and `tri_node`, and record their build identity from installation metadata. Read `tri-client --help` and `tri_node --help` for installed options. The server entrypoint starts the service; inspect its service definition to identify it.

Identify the service owner and system/user service scope, socket/TCP endpoint, database path and registered nodes. Keep authentication tokens in their protected environment files. The CLI prefers an existing `TRI_SOCKET`, otherwise TCP through `TRI_SERVER_ADDR`.

## Deploy and maintain

[Service setup](references/service-setup.md) covers server/client installation, service units, shared paths, resource advertisement, acceptance, backups, upgrades and history retention. A single-host installation runs both server and client; multiple compute hosts register unique node names with the same queue server.

Use `tri_node --json` and `tri_node --check` to inspect registration, capacity, cgroups and the user manager. Inspect the identified server/client units and their journals. For connection failures, verify endpoint, ownership, service health and network connectivity. For protocol mismatch, compare server/CLI/client build identities. For an offline node, inspect its client service and heartbeat connection before changing advertised capacity.

## Verify maintenance

After a service or capacity change, check node registration, existing attempts and the bounded diagnostic Job in the setup reference. A login-host check does not establish compute-node software readiness; use the [per-node acceptance procedure](../batch-schedulers/references/tri.md#verify-each-compute-node-and-backend) for that purpose.

Report affected services/nodes and verification results. Diagnose individual queued, failed, lost or cancelled Jobs through [TRI task diagnosis](../batch-schedulers/references/tri-diagnosis.md), preserving their execution identities during maintenance.
