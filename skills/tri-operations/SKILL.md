---
name: tri-operations
description: Install and operate TRI task queues, configure server and compute-node services, manage resources, and diagnose queued, failed or lost tasks and CoRAgent integration.
---

# TRI operations

[简体中文](SKILL.zh-CN.md)

Use this Skill for TRI deployment, node/resource configuration, service maintenance and task troubleshooting. TRI consists of a persistent queue server, compute-node clients and command-line tools. It can run on one host or across hosts with shared job files.

## Choose the operation

- For installation, service configuration, capacity changes or upgrades, read [Service setup](references/service-setup.md).
- For waiting, failed, lost or cancelled tasks, logs, retry identity and retention, read [Task diagnosis](references/task-diagnosis.md).
- To connect CoRAgent to TRI on a login host or through SSH, read [CoRAgent Jobs](references/coragent-jobs.md).
- For a CoRAgent Job, read its receipt to locate the execution target and TRI `scheduler_id`. Use [research-workflow](../research-workflow/SKILL.md) for Job submission, reconciliation and collection; use the TRI tools below to inspect the underlying scheduler.

## Establish the actual installation

Locate binaries with `command -v tri_sub tri_stat tri_node tri-server tri-client`. Read `tri_sub --help`, `tri_stat --help` and `tri-client --help` for the installed options. Record the release/build identity from installation metadata. The server entrypoint starts the service directly, so inspect its service definition and release metadata to identify it.

Identify the service owner, whether units are system or user services, the socket/TCP endpoint, database path and compute nodes. Read endpoint/path settings selectively; keep authentication tokens in their existing protected environment files. Native CLI calls use an existing `TRI_SOCKET` first, otherwise TCP through `TRI_SERVER_ADDR`.

## Inspect the queue

With the selected endpoint configured:

```bash
tri_node --json
tri_node --check
tri_stat --json
tri_ls --json
```

For a task, set `TRI_TASK_ID` to the numeric ID returned by TRI:

```bash
tri_stat --json "$TRI_TASK_ID"
tri_log "$TRI_TASK_ID"
tri_log --stderr "$TRI_TASK_ID"
```

`tri_top` gives an interactive queue view. Use native binaries for interactive maintenance. The bundled [queue.py](scripts/queue.py) supplies stable submission, observation, cancellation and recovery for background CoRAgent Jobs.

## Complete the operation

Apply the requested maintenance to the identified service or task, then repeat the relevant observation. Check node capabilities after configuration changes, and task state plus process/resource release after cancellation. For deployment acceptance, use the small diagnostic job in the setup reference. Report the affected target, observed cause, change and verification result. For CoRAgent work, reconcile and collect through the existing Job so its outputs retain their producer identity.
