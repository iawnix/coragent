# Pinned Pi integration

`source.json` pins Pi 1.4.0 at `4a080252f06caf63a525d7873c5d94d3c23887e0`.
`prepare.py` applies and reverses the ordered patch stack to verify it, validates
package versions and builds the source. Source-only imports are confined to
`apps/agent/runtime/source.mjs`. The published Durable and TUI APIs provide the
execution and presentation primitives; CoRAgent owns the Host, Worker supervisor,
session catalog and terminal client.

| Patch | Required behavior | Regression coverage | Removal condition |
| --- | --- | --- | --- |
| 001-durable-policy | Fail-closed request admission, persistent context preparation, admission refresh with durable backoff, summary supplements, output reservation, shared compaction coordination | `context-manager`, `tool-execution-boundary`, `compact-coordination`, `compaction-outcome` | Public Durable hooks and compaction policy provide all these boundaries |
| 003-proxy-cache-affinity | Keep routing identity during compaction; support explicit proxy prompt-cache keys independently of long retention | `compact-session-affinity`, `test_pi_source_pin` | Upstream provides equivalent affinity and `promptCacheKeyMode` behavior |
| 004-terminal-input | Preserve the SSH Escape timeout across incomplete CSI/SS3 function keys | `pi-session-worker-startup` | Upstream applies the configured timeout to incomplete key prefixes |

Node names refer to `tests/node/native/*.test.mjs`; Python names are in
`tests/integration/`. The former twenty patches have been consolidated: the
experimental server/client/plugin patches are replaced by application code, the
shared credentials adapter is owned by CoRAgent, and the system-baseline fix is
already present upstream. The remaining Chord context
and storage utilities are dependencies of Pi Durable; CoRAgent no longer uses
Chord service discovery, RPC or facets.

`001` is kept together because generation checkpoints, context preparation,
admission and shared compaction depend on the same execution boundary and Hook
types. CoRAgent implements research policy through these hooks. The removed
`002` is implemented in `apps/agent/runtime/credentials.mjs` using the public
`CredentialStore` contract. Installation verifies the current patch stack against
the pinned source and restores managed checkouts that retain retired patches.

For each upgrade, review every patch and source-only import against the new pin,
then run native, source and installed-release tests. Use a new managed runtime
directory. Never open a schema-v2 session with Pi 1.1; see the
[migration and rollback notes](../../../docs/PI_1_4_MIGRATION.zh-CN.md).
