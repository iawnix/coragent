# 模型配置与兼容性

[English](MODEL_COMPATIBILITY.md) | 简体中文

模型调用和 provider 实现由固定版本的 Pi 提供。CoRAgent Host 为终端、CoRHub 和浏览器
提供同一套会话模型选择；当前 Pi 版本以 `packaging/coragent_packaging/pi/source.json` 和 `package.json` 为准。

## 配置入口

在 `config.toml` 的 `[models.providers]` 中配置自定义 provider 和模型，字段遵循 Pi
模型格式，包括 `api`、`baseUrl`、模型 ID、`contextWindow`、`maxTokens` 和适用的 `compat`。
安装示例见 [config.example.toml](../config/config.example.toml)。

相邻 `credentials.json` 中，`models` 保存 Pi provider 凭据，`secrets` 保存具名密钥。
配置中的密钥字段可以使用 `credential:NAME` 引用。OAuth 刷新的凭据也写回这个规范文件。
主配置会生成 `<state_root>/pi/agent/models.json`；不直接编辑生成文件，也不使用旧
`<install>/etc/pi/` 或个人 `~/.pi/agent` 作为安装配置源。

修改 provider 配置后重启所属 Host 服务。默认用户服务使用：

```bash
systemctl --user restart coragent.service
```

系统服务使用不带 `--user` 的命令。会话内用 `/model` 选择可用模型，`/thinking` 选择
支持的思考等级。`thinkingLevelMap` 中可用 `false` 表示不支持的等级，生成时转为 Pi 的 `null`。

## 能力判断

内置 provider 和具体模型以当前 Pi 目录及安装的自定义配置为准。相同的品牌名称不代表
endpoint、认证、工具调用和思考模式都相同。OpenAI-compatible endpoint 需要匹配其实际
API 和兼容字段；媒体生成 API 不能直接充当研究 Agent 的对话模型。

CoRAgent 的模型测试使用本地确定性 provider，验证调用和错误处理合同。
实际 endpoint 的凭据、配额和工具调用需要另行验证；项目测试不得把 `local_debug/`
中的材料发送给真实模型。

## Chat Completions 代理的缓存 key

对于支持 `prompt_cache_key` 的 `openai-completions` 代理，可在 provider 或模型的
`compat` 中配置 `promptCacheKeyMode`。当前受管理的 Pi 运行时支持：

| 配置值 | 自动生成的 `prompt_cache_key` |
| --- | --- |
| `auto` 或未配置 | 沿用 Pi 的 URL/保留策略判断：直连 OpenAI，或请求长缓存且 endpoint 支持 |
| `enabled` | 使用已有的 provider 会话 ID，代理的短缓存请求也会携带 |
| `disabled` | 省略自动生成的 key |

所有模式都尊重 `cacheRetention: "none"`，此时省略自动生成的 key；请求没有会话 ID 时
也不会生成 key。CoRAgent 的持久会话在 compact 前后沿用同一 provider 会话 ID，Pi 将
key 限制为 64 个字符。key 是路由提示，实际缓存命中仍由上游决定。

例如，代理接受缓存 key 和 OpenAI 会话亲和头，但不支持长缓存时，把以下设置合并到
`config.toml` 中已有的 `compat` 表；将 `my_proxy` 换成实际 provider 名称：

```toml
[models.providers.my_proxy.compat]
promptCacheKeyMode = "enabled"
supportsLongCacheRetention = false
sendSessionAffinityHeaders = true
sessionAffinityFormat = "openai"
```

`supportsLongCacheRetention` 单独控制保留时长字段，设为 `false` 不代表关闭缓存。
会话亲和头也独立控制，compact 摘要使用 `none` 时仍可携带。这项策略适用于
`openai-completions`；配置字段为 `promptCacheKeyMode`，旧提案中的
`supportsPromptCacheKey` 不是本次支持的配置名。修改规范配置后，按上文重启所属 Host。

## 上下文窗口与预算

模型元数据的 `contextWindow` 是运行时认定的容量，不是读取宣传页得到的数字。
自定义 endpoint 的模型定义需要与实际服务相符。输入预算为：

```text
max(0, min(contextWindow - max(reserveTokens, maxTokens + 4096), maxInputTokens))
```

没有配置 `maxInputTokens` 时，不施加额外输入上限。预留空间取 Pi 的 `reserveTokens` 与本次最大输出加 4,096 token 安全余量中的较大值，压缩会在 SDK 缩减输出额度之前触发；
`CORAGENT_CONTEXT_INPUT_TOKENS` 可设置额外的输入上限，默认不设置。
`maxTokens` 优先使用本次 stream 配置，否则使用模型的最大输出额度，和整个上下文窗口不同。例如窗口 1,050,000、输出 128,000 时，输入预算为 917,904；默认后台压缩再提前 32,768 tokens。终端显示输入预算及模型窗口，
`/usage` 提供用量详情；估算 token 不等于账单用量。压缩及研究概览见[研究上下文](RESEARCH_CONTEXT.zh-CN.md)。
