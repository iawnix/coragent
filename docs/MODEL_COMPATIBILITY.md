# Model configuration and compatibility

[English](MODEL_COMPATIBILITY.md) | [简体中文](MODEL_COMPATIBILITY.zh-CN.md)

The pinned Pi runtime implements provider access and model calls. CoRAgent Host
exposes the same session model selection to the terminal, CoRHub and browser.
`packaging/coragent_packaging/pi/source.json` and `package.json` identify the current Pi version.

## Configuration

Define custom providers and models in `[models.providers]` in `config.toml`,
using Pi model fields such as `api`, `baseUrl`, model ID, `contextWindow`,
`maxTokens` and applicable `compat` options. See
[config.example.toml](../config/config.example.toml).

Adjacent `credentials.json` stores Pi provider credentials in `models` and named
secrets in `secrets`. Secret fields can reference `credential:NAME`. Refreshed
OAuth credentials are written back to this canonical file. Configuration produces
`<state_root>/pi/agent/models.json`; do not edit that generated file or use the
retired `<install>/etc/pi/` or personal `~/.pi/agent` as installation configuration.

Restart the owning Host after changing provider configuration. For the default
user service:

```bash
systemctl --user restart coragent.service
```

Omit `--user` for a system service. Within a session, `/model` selects an available
model and `/thinking` selects a supported reasoning level. Use `false` for an
unsupported level in `thinkingLevelMap`; materialization restores Pi's `null`.

## Compatibility

Available built-in providers and models come from the pinned Pi catalog and the
installation's custom definitions. A provider brand alone does not establish
endpoint, authentication, tool-call or reasoning compatibility. An OpenAI-compatible
endpoint needs matching API and compatibility fields. Media-generation APIs are
not interchangeable with the conversational model used by the research Agent.

Repository model tests use local deterministic providers to verify invocation and
error contracts. Actual credentials, quota and endpoint behavior need separate
validation. Repository tests must not send private `local_debug/` materials to real models.

## Prompt cache keys for Chat Completions proxies

For an `openai-completions` proxy that accepts `prompt_cache_key`, set
`compat.promptCacheKeyMode` on its provider or model. The managed Pi runtime
supports these values:

| Value | Generated `prompt_cache_key` |
| --- | --- |
| `auto` or omitted | Uses Pi's existing URL/retention detection: direct OpenAI requests, or long retention when supported |
| `enabled` | Uses the existing provider session ID, including for proxies with short retention |
| `disabled` | Omits the generated key |

`cacheRetention: "none"` omits the generated key in every mode. A request without
a session ID does not get a generated key. CoRAgent's durable conversation keeps
its provider session ID across compaction; Pi limits the key to 64 characters.
The key is a routing hint, and the upstream service determines actual cache hits.

For example, merge these settings into an existing proxy's `compat` table in
`config.toml` if it accepts cache keys and OpenAI affinity headers but does not
support long retention (replace `my_proxy` with the provider's configured name):

```toml
[models.providers.my_proxy.compat]
promptCacheKeyMode = "enabled"
supportsLongCacheRetention = false
sendSessionAffinityHeaders = true
sessionAffinityFormat = "openai"
```

`supportsLongCacheRetention` governs retention fields separately from key
generation; `false` does not disable prompt caching. Affinity headers are also
independent and remain available to compaction summaries that use retention
`none`. This policy applies to `openai-completions`. The configuration field is
`promptCacheKeyMode`, not the older proposal's `supportsPromptCacheKey` name.
Restart the owning Host after changing the canonical configuration as described
above.

## Context capacity and input budget

The runtime uses the selected model's `contextWindow` metadata. Custom endpoint
definitions must match the actual service; marketing specifications are not read
at runtime. The operating input budget is:

```text
max(0, min(contextWindow - max(reserveTokens, maxTokens + 4096), maxInputTokens))
```

Without `maxInputTokens`, no additional input cap applies. The reserve covers at
least the requested output plus 4,096 safety tokens, so compaction starts before
the SDK shrinks the output allowance. `CORAGENT_CONTEXT_INPUT_TOKENS` provides
an optional lower input cap and is unset by default. `maxTokens` is the current
output allowance (stream override or model maximum), separate from the context
window. For a 1,050,000 window and 128,000 output, the input budget is 917,904;
default background compaction starts another 32,768 tokens earlier. The terminal displays input
budget and model window; `/usage` provides usage details. Estimates are not billing
measurements. See [Architecture](ARCHITECTURE.md#context-and-next_run) for compaction
and research context preparation.
