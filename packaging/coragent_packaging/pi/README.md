# Pinned Pi integration

`source.json` pins the only supported Pi runtime. `prepare.py` applies the ordered patch stack, verifies the resulting source and builds the runtime. Runtime-only source imports are centralized in `apps/agent/runtime/source.mjs`.

All patches target the commit in `source.json`. For an upgrade, evaluate every row below against the new upstream behavior, remove a patch only when its behavior is supplied upstream, and run the listed coverage plus the complete native and installed-release suites. Do not keep alternate protocol versions or fallback implementations.

| Patch | Required behavior | Regression coverage | Removal condition |
| --- | --- | --- | --- |
| 001-workspaces | Workspace-scoped sessions and catalog ownership | `coragent-host`, `pi-app-server`, `session-admission` | Upstream supports the same workspace isolation and discovery |
| 002-worker-launch | Launch the configured SessionWorker entry | `pi-session-worker-startup`, `pi-server-lifecycle` | Upstream exposes the required supervised worker entry |
| 003-client-connection | Native client connection lifecycle | `pi-session-worker-startup`, `coragent-native-commands` | Native remote client provides equivalent connection behavior |
| 004-client-lifecycle | Attach/detach and client shutdown | `pi-session-worker-startup`, `pi-server-lifecycle` | Upstream preserves Worker execution across client detach |
| 005-client-history | Restore session-specific input history | `pi-session-worker-startup` | Upstream restores and isolates native client history |
| 006-tool-presentation | Product tool rendering hooks | `tool-presentation`, `runtime-presentation` | Upstream exposes equivalent renderer registration |
| 007-client-status | Client status, commands and panels; Esc sends session pause even without an active model run; incomplete SSH key sequences retain the configured Escape window | `status-presentation`, `terminal-completion`, `coragent-native-commands`, `pi-session-worker-startup`, `session-admission` | Public UI APIs cover panels, status lifecycle, idle session interruption and SSH key reassembly |
| 008-request-admission | Validate the full model request before dispatch | `context-manager`, `tool-execution-boundary` | Upstream exposes equivalent request admission and failure semantics |
| 009-input-identity | Preserve submission identity through client and server | `input-admission`, `user-sources` | Public APIs preserve the same input identity end to end |
| 010-context-lifecycle | Context preparation and fixed-history compaction supplements | `context-manager`, `compaction-outcome` | Public hooks provide the same persistence and compaction boundaries |
| 011-markdown-presentation | Product Markdown presentation hooks | `tool-presentation`, `runtime-presentation` | Public renderers support the required transformations |
| 012-skill-presentation | Skill invocation presentation | `product-resources`, `runtime-presentation` | Upstream exposes equivalent Skill presentation |
| 013-monitor-presentation | Render authenticated runtime status | `monitor-records`, `monitor-research`, `runtime-presentation` | Public UI hooks cover Monitor messages without treating them as user authorization |
| 014-runtime-presentation | Runtime continuation presentation | `runtime-presentation`, `worker-task-continuation` | Upstream distinguishes internal continuations in its clients |
| 015-configuration-credentials | Shared credentials without overwriting non-model secrets | `test_install_credentials`, `product-resources` | Upstream credentials support the product's single configuration ownership |

Node coverage names refer to `tests/node/native/*.test.mjs`; installation credential tests are in `tests/integration/`. Patch contents are source integration only, never a second Agent loop or task store.
