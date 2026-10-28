# Managed Pi runtime patches

CoRAgent pins Pi **1.4.0** at `4a080252f06caf63a525d7873c5d94d3c23887e0`.
The [integration registry](../packaging/coragent_packaging/pi/README.md) describes
each remaining patch, its regression tests and removal conditions.

Pi 1.2 removed the unpublished experimental server/client/plugin stack. CoRAgent
now owns session discovery, one supervised Worker per SQLite session, Host RPC,
reconnection and the terminal presentation. Pi Durable supplies the Harness,
transactions, execution and recovery. Public pi-tui components supply the editor,
layout, scrolling and rendering. The Host wire protocol remains `coragent-host/3`;
there is no separate Pi server protocol or second SSH socket.

`prepare.py` verifies the exact commit and package versions, applies patches in
order and checks their complete reverse application in an isolated directory.
The reversed files must match the pinned source, with no tracked changes outside
the current stack. Reinstallation restores an installer-owned checkout if it
contains retired or incompatible patches. Model catalog hydration is followed by
the upstream offline build; there is no untracked provider type cast.

The Durable policy patch preserves request admission before model dispatch,
request-bound research orientation, fixed-history summary supplements, and output
reservation. The reserved context is the greater of the configured reserve and
the effective requested output plus 4,096 tokens. Thresholds, admission and
terminal telemetry use the same policy. A generation waiting on a shared summary
places its queued write before rebuilding context. Conflicting compaction
instructions fail explicitly; failed, declined or stale blocking summaries stop
the generation. The system-baseline ordering fix is supplied by upstream 1.4.

`001-durable-policy` remains one patch because context preparation, request
admission, generation checkpoints and shared compaction change the same execution
boundary and Hook types. A stale control snapshot prepares a new committed
context within the same run; repeated refreshes yield with durable backoff.
Research policy and credentials belong to CoRAgent. The patch supplies the Durable
hooks and execution guarantees that those policies require.

CoRAgent's runtime credential adapter preserves non-model secrets while exposing
only the `models` object through Pi's public `CredentialStore`. It reuses Pi's
`AuthStorage` backend and locking; this no longer requires a Pi source patch.

The Chat Completions patch retains
opted-in session-affinity headers even when a summary disables prompt caching.
`compat.promptCacheKeyMode` supports `auto`, `enabled` and `disabled`; it uses the
existing provider session ID and 64-character clamp. Long retention remains a
separate option, and explicit `onPayload` overrides still apply. This controls
routing hints; it does not prove a proxy's cache hit rate improved. See the
[proxy configuration example](MODEL_COMPATIBILITY.md#prompt-cache-keys-for-chat-completions-proxies).

CoRAgent-owned terminal code handles input identities, tool cards, internal
continuation markers, Monitor status and command panels. `/compact` reports its
durable outcome, displaying a compacted-context marker without exposing the
internal summary as an ordinary reply. `/reload` refreshes model configuration
and credentials; the removed experimental plugin loader is not supported.
Closing or switching the terminal leaves the Worker running.

A source resolver retained by upstream under `src/experimental` loads pinned
workspace aliases. It is a build/bootstrap helper, not the removed server stack.
Other private model/settings/tool helpers remain isolated in `source.mjs` and
must be checked on future upgrades. SQLite schema migration and rollback are
covered in the [1.4 migration notes](PI_1_4_MIGRATION.zh-CN.md).
