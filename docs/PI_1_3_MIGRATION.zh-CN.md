# Pi 1.3.0 升级审查（待实施提案）

本文保留 2026-10-19 的上游审查基线，不是当前运行指南。文中的 Monitor 唤醒对应现在的 Job Manager 事件投递；当前命名和职责见[任务与作业架构](TASK_JOB_ARCHITECTURE.zh-CN.md)。

审查日期：2026-10-19。当前 CoRAgent 绑定 Pi **1.1.0**；本文是源码对照结果和迁移建议，**尚未完成 1.3.0 升级**。

| 对象 | 版本 / commit |
|---|---|
| 当前运行时 | `v1.1.0` / `abe508e1b89912adde45528136c3221eb69acdd7` |
| 目标运行时 | `v1.3.0` / `71023aec1546d6d677a65669c5665c0927ce0dd0` |
| 当前依赖 | `pi-agent-core`、`pi-ai`、`pi-coding-agent`、`pi-tui`、`pi-durable` 均为 `1.1.0` |

## 结论

14 份受管补丁中，未发现可以因 **1.2.0–1.3.0 已完整实现同等功能**而整份删除的补丁。上游的压缩失败处理与部分需求重叠；新应用消息类型可以简化 Monitor 和自动续跑的消息记录。安装脚本中另有一处类型强制转换，其对应的 provider 类型缺口已被上游补齐。

主要阻塞在集成接口：Pi 1.2.0 删除了我们依赖的 experimental server/client/plugin 栈，1.3.0 继续沿用这一变化。`apps/agent/runtime/source.mjs` 的 27 个源码入口中，12 个路径已经不存在。Chord 的旧 service/facet 接口也被替换。因此，仅更新版本、commit 和 lock 文件无法启动现有 Worker 与终端。

建议继续使用 Pi durable 的任务、会话、存储和模型执行能力，将被删除的 Worker 生命周期与客户端连接功能迁到 CoRAgent 适配层。领域知识和化学流程继续由 Skill 承担。

## 上游依据

以下链接均指向公开上游源码，便于复核：

- [删除 experimental 栈：7472cda0d](https://github.com/earendil-works/pi/commit/7472cda0d)：删除 server、session worker、client TUI、services 及 client/protocol/server 包。[1.2.0 changelog](https://github.com/earendil-works/pi/blob/v1.3.0/packages/coding-agent/CHANGELOG.md) 明确说明这些接口不属于已发布的 coding-agent 包。
- [Chord 替换：0104fef1e](https://github.com/earendil-works/pi/commit/0104fef1e)：旧 `defineService`、`createStaticFacetLoader` 等接口移除；同名 `defineFacet` 也需要按新契约迁移。
- [阻塞压缩失败处理：89e5c2c07](https://github.com/earendil-works/pi/commit/89e5c2c07)：阈值触发的阻塞压缩失败后终止 run，保留失败状态并暴露压缩错误。
- [应用消息：e6b9a6af5](https://github.com/earendil-works/pi/commit/e6b9a6af5)：输入支持 `entry: { kind, data }`；纯展示 write 可以立即记录。
- [压缩后系统提示顺序：5713c9507](https://github.com/earendil-works/pi/commit/5713c9507)：系统 baseline 在保留 assistant 消息时仍排在上下文前面。
- [OpenCode provider：195120a91](https://github.com/earendil-works/pi/commit/195120a91)：OpenCode Go 的 API 联合类型和实现增加 `google-generative-ai`。

## 逐项补丁处置

“可应用”仅指对干净的 1.3.0 源码执行补丁文本检查通过。它不证明类型、行为、补丁依赖或恢复兼容性；正式验证仍需完整补丁栈和运行测试。

| 补丁 | 1.3.0 对照结果 | 迁移处置 |
|---|---|---|
| 001 workspaces | session catalog、worker/服务等目标文件已删除 | 工作区目录、cwd、会话归属和同名会话消歧迁到 CoRAgent 会话管理层 |
| 002 worker-launch | worker manager 已删除 | Worker 启动入口和诊断日志由 CoRAgent 进程管理层配置 |
| 003 client-connection | client runtime 已删除 | 在客户端适配层实现连接、重连和 attach 状态订阅 |
| 004 client-lifecycle | client TUI 已删除 | 保留关闭界面时断开连接、选定会话不存在时报错的行为 |
| 005 client-history | client TUI 及其测试已删除 | 从当前会话中已接受的用户输入重建编辑器历史 |
| 006 tool-presentation | experimental chat/client TUI 已删除 | 紧凑工具卡、完整结果展开和渲染器注册迁到终端展示层 |
| 007 client-status | 7 个旧目标路径已删除；editor/select-list 部分仍可应用 | 页脚、活动区、命令反馈和文档面板迁到终端；编辑器扩展单独评估。上游压缩错误可作为反馈数据源 |
| 008 request-admission | durable 文件仍在，但 generation 补丁冲突；上游新增阻塞压缩失败分支 | 保留 model/output allowance、block/compact 返回值、异常处理、最多一次准入压缩和 `request_blocked`；重写时保留上游新分支 |
| 009 input-identity | controller 和客户端已删除 | 在新客户端/服务适配层传递稳定 requestId 和具体准入错误；durable 的 requestId 去重在 1.1.0 就已存在 |
| 010 context-lifecycle | 文本可应用；上游仍无 prepareContext/prepareSummary/maxInputTokens | 当前实现依赖 008 的 failRequest，不能独立使用；先评估 section、应用消息、文档和 beforeCompact 是否满足实际需求，再确定保留范围 |
| 011 markdown-presentation | experimental chat 已删除 | Markdown transformer 注册迁到终端展示层 |
| 012 skill-presentation | 文本可应用；上游仍把附加用户文本单独展示 | 保留合并折叠行为。若终端拥有 Skill 卡组件，在应用层实现后可删除源码补丁 |
| 013 monitor-presentation | experimental chat 已删除 | 用应用 entry 的 kind/data 记录事件，在终端渲染事件卡；保留历史会话显示兼容 |
| 014 runtime-presentation | experimental chat 已删除；普通 InteractiveMode 部分仍可应用 | 新续跑消息用应用 entry 标识，终端渲染简短状态；迁移旧消息的识别逻辑 |

完整补丁检查结果：11 份涉及已删除的目标；008 有上下文冲突；010、012 文本检查通过。007 的 editor/select-list 和 014 的普通 InteractiveMode 修改也单独检查通过。这些结果说明展示需求仍有实现工作，并不代表应继续修改普通 InteractiveMode：CoRAgent 当前实际使用的是被删除的 experimental TUI。

### 008：哪些部分能复用上游

1.3.0 的 `GenerationHooks.beforeRequest` 仍然只接收 `{ messages }`、返回替换后的 messages。它没有我们的 `{ block, compact }` 返回值，也没有提供本次请求的 model 和输出额度。

上游新增了阈值压缩失败后停止请求的处理，可直接保留；它与准入失败触发的单次压缩及 `request_blocked` 状态不是同一个分支。重写 008 时必须兼容两种触发原因，而不是用旧补丁覆盖新的 generation 状态机。

007 中等待压缩完成、将错误显示给用户的行为，可使用新版 `compaction_end.error` 和 `pi.live.compactionFailure`，但仍需由新的客户端接收和呈现。

### 010：系统提示修复没有替代上下文合同

上游修正了 compaction 后 system baseline 的顺序。我们的 010 还负责把外部准备的上下文与请求 cutoff 原子持久化，以及把摘要补充与选中的历史范围绑定。新版仍没有 `prepareContext`、`prepareSummary` 和 `maxInputTokens` 扩展，不能仅凭系统提示顺序修复就删除该补丁。

这些接口应保持通用：只处理上下文、预算、摘要和持久化。研究状态如何解释仍由应用和 Skill 提供。缺少同名 hook 只能证明没有直接替换，不能证明必须修改内核；公开扩展方案见下文。

### 013 / 014：新版可以减少消息文本识别

新输入可以携带应用定义的 `entry.kind` 和 `entry.data`，同时保留给模型的输入内容。Monitor 唤醒和任务续跑可通过结构化类型选择卡片，减少当前对文本首行或 XML 风格标记的识别。

这需要同步修改输入创建、队列、消费检查和 transcript 投影，并测试历史 `pi.user` 消息。消息类型用于展示分派，输入的来源和准入仍沿用现有持久化记录。纯展示 write 适合状态通知；需要唤醒模型的 Monitor 事件仍使用 input。

### 补丁目录以外：OpenCode Go 强制转换

`packaging/coragent_packaging/pi/prepare.py:hydrate_model_data()` 会修改 provider 源码，把 `Object.values(OPENCODE_GO_MODELS)` 转成 `any`。此改动不在 14 份补丁中。

1.3.0 的 OpenCode Go provider 已包含 `google-generative-ai` 类型和 API 实现。升级时应删除这处强制转换，再对实际生成的 catalog 执行构建。如果新 catalog 还有其他类型问题，按具体 API 修复。本次仅完成源码核对，尚未验证去掉转换后的完整构建。

## 需要迁移的调用点

| CoRAgent 文件 | 当前依赖 / 升级工作 |
|---|---|
| `apps/agent/runtime/source.mjs` | 27 个路径中 12 个消失：worker、process、setup、server、clientRuntime、clientCommand、client、clientTui、clientChat、slashCommands、presentationUI、transcript |
| `apps/agent/runtime/backend.mjs` | 启动被删除的 Pi server，通过旧 service 接口管理会话和订阅状态 |
| `apps/agent/runtime/worker.mjs` | 使用被删除的 session-worker/process 入口 |
| `apps/agent/runtime/setup.mjs` | 使用旧 Chord facet/service 和已删除的 harness-setup；需显式组装模型、settings、执行环境和服务适配 |
| `apps/agent/runtime/client.mjs`、`apps/agent/terminal/commands/facet.mjs` | 使用已删除的客户端、展示服务和命令扩展接口 |
| `apps/agent/runtime/tool-adapter.mjs` | 目前直接转交 coding tool 的 content 结果；新版 durable 的 ToolExecutionResult 使用 output，需在边界转换 |
| `packaging/coragent_packaging/pi/prepare.py` | 要求 experimental 文件与旧 protocol 8；准备、安装、验证和构建条件需随新集成更新 |
| `tools/test/environment.py`、native Pi 测试 | 依赖安装和原生集成验证需覆盖新启动路径与恢复行为 |

`experimental/source-resolver.ts` 仍然存在；不能把整个 experimental 目录一概视为消失。旧 Pi protocol 8 与新 Chord 协议属于不同协议，不能直接把 descriptor 的 8 改成新 Chord 的版本号。

durable 还改变了工具任务的 tagged union 和存储错误语义：`pi.tool` v2 提供 live v1 任务迁移；存储错误会关闭 Session。适配层需要处理会话失败和重连，旧 SQLite 会话恢复应作为迁移验证的一部分。上游提供单项迁移不等于 CoRAgent 全部自定义状态已经兼容。

## 建议采用的集成方式

| 方案 | 影响 | 判断 |
|---|---|---|
| Pi durable + CoRAgent Worker/客户端适配 | 延续持久化任务和 SQLite 会话；接管上游删除的通信与展示连接点，复用现有 Host transport 和 Pi TUI 组件 | 推荐。迁移范围明确，便于将大部分产品展示补丁转为应用代码 |
| 改用 coding-agent 的 createAgentSession / 普通 CLI RPC | 可复用普通交互模式与扩展 API；会话由另一套 SessionManager/JSONL 机制管理 | 需要重新设计 durable 任务、事务准入、恢复与历史会话转换，作为另一项架构选择评估 |
| 搬回旧 experimental 栈及旧 Chord | 短期保留原接口；同时维护已删除的 server/client/plugin 代码和旧运行时 | 维护成本高，且不能称为去除补丁或完成新版 API 迁移 |

推荐方案的职责分配：

- **Pi durable / ai**：模型调用、持久化任务、会话记录、工具调度和压缩。
- **CoRAgent Host / Worker**：工作区与会话路由、进程生命周期、输入准入、Monitor 和客户端连接。
- **CoRAgent terminal + Pi TUI 组件**：输入历史、命令、状态与消息卡片。
- **Skill**：领域方法、工具操作经验、科学验证和总结。

这样可以将 001–007、009、011、013、014 的产品能力迁出上游补丁；012 在终端拥有对应组件后也可迁出。008/010 应先评估公开扩展方案，确认存在具体缺口后再维护最小补丁并评估上游化。最终保留多少源码补丁，应以新适配的实现和测试结果为准。

## 进一步审查：能否只用公开 hook 和扩展

按主要职责划分，目前是 **5 份服务集成补丁、7 份展示补丁、2 份 durable 内核补丁**，另有安装脚本的类型强制转换。这个分类用于定位维护责任，不表示同一补丁只涉及一种行为。

- 服务集成：001、002、003、004、009。
- 展示：005、006、007、011、012、013、014。
- durable 内核：008、010。

“没有整份补丁被新版直接替代”和“必须保留这些补丁”是两种判断。前面的检查回答的是前者；后者必须从需求和公开接口重新评估。

### 普通 coding-agent 已有相当完整的扩展接口

1.3.0 的 `ExtensionAPI` 提供 `registerToolRenderer`、`registerMessageRenderer`、`registerEntryRenderer`、`registerMarkdownTransformer`，UI 提供 `setFooter`、`setWidget`、`setEditorComponent`。这覆盖了工具卡、应用消息、Markdown、页脚等大量需求。命令、输入、工具调用和结果也有扩展接口。

上下文可用 `before_agent_start`、`context`、`context_with_system`；压缩可用 `session_before_compact`；`turn_end` 和 `agent_before_settle` 可以追加结构化记录并请求继续执行。因此，普通 SDK 路线不应先复制现有 UI 补丁，也不应先自行重写这些机制。某些具体布局和内建 Skill 卡行为仍需验证。

这些 API 属于普通 coding-agent 的扩展运行时，不能直接注册到 durable Harness。保留 durable 时，需要使用其自己的扩展接口，并通过终端适配呈现状态；不能把两套 API 的能力相加后宣称当前架构已支持。

### durable 也有可能替代部分内核补丁的公开接口

| 需求 | 现有公开接口 | 需要验证的差异 |
|---|---|---|
| 动态运行说明进入历史并在恢复后重建 | `section()` / `wrapSection()`，变化自动持久化为 positional system entries | 不是当前 user-role 上下文记录；没有当前研究 anchor 元数据合同。外部证据优先通过工具结果或应用消息提供 |
| 给单次模型请求补充信息 | `beforeRequest` 替换 messages | 请求局部修改不自动成为历史记录 |
| 保存结构化状态、来源与事件 | 自定义 document、应用 entry、事务、带 requestId 的 submit | 需要设计事务边界；普通 submit 不能直接替代当前与业务文档同一事务执行的内部 admitSubmission |
| 控制工具、处理结果、要求继续 | `beforeTool`、`afterTool`、`afterTools`、`onYield` | 不能把 onYield 的一次继续等同于完整后台任务调度 |
| 自定义摘要 | `beforeCompact` 可接收选中的历史范围并返回 summary；hook 可用 memo | 可以接管摘要，但不是给内建摘要流程附加 instructions/metadata；要衡量新增应用代码是否比小补丁更复杂 |
| 控制上下文大小 | 原生 compaction 的 reserveTokens、keepRecentTokens、backgroundTokens | 独立输入预算、请求局部补充后的最终检查不是完全相同的语义；reserveTokens 还影响摘要输出额度 |

检查 `harness/prompt.ts` 和 `generation.ts` 可确认：section 的变化由 generation 准备阶段持久化并纳入请求 cutoff。因此，若需求只是“动态说明要进历史”，新增 prepareContext 并非唯一方案。

但检查 `harness/scheduler.ts` 也发现一个实际缺口：hook runner 对普通异常只报告错误并继续；`beforeRequest` 没有 block 返回类型。因此，**仅在 beforeRequest 中抛出异常，不能保证取消模型请求**。如果产品确实要求在最终请求边界拒绝调用，008 的这部分需求需要明确的替代实现或小范围上游扩展。不能用 hook 存在来推断它具备拦截语义。

### 开发方式的调整

继续基于 Pi 是合理的；以实验源码和持续扩大的补丁栈作为主要集成方式，维护成本已经过高。下一步应先做不修改 Pi 的最小适配验证，再决定缺口。验证以用户需要的结果为准：会话恢复、后台作业继续、输入不重复、上下文可追溯、压缩后仍能工作、终端能重连。旧的内部字段名称和记录布局属于迁移兼容问题，不应自动升级为新架构的必需条件。

同时避免为了“零补丁”在应用层复制整个 generation/compaction 状态机。对公开扩展无法合理实现的、经过行为验证的缺口，保留小而通用的补丁并推动上游支持，比另一套执行引擎更合适。当前只能确定两份内核补丁需要深入拆分，尚未证明必须保留两份，也未证明能做到零补丁。

机制推断、候选构建和科学验证的工作流优先由 Skill、工具结果和模型过程反馈形成闭环。Pi 内核应处理通用执行、持久化和生命周期问题。

## 实施与验证顺序

1. 在隔离测试环境中接入未打补丁的 1.3.0 durable，用公开扩展验证准入、压缩和持久化上下文，适配工具 output；记录确实无法满足的行为后，再确定 008/010 的最小保留范围。
2. 替换 Worker 启动和服务绑定，复用 CoRAgent Host 对外契约。验证工作区隔离、重复输入、并发准入、进程中断恢复和旧 SQLite 会话副本。
3. 迁移终端连接、命令和展示组件，使用应用 entry 记录新 Monitor/续跑消息；验证历史消息、展开、切换、重连及退出。
4. 同步更新源码 pin、npm 依赖和 lock、安装验证及测试入口，删除已迁移补丁与类型强制转换；验证离线构建、包内容及 Host/Phone/Monitor 集成。

本次完成了公开上游源码与提交记录对照、14 份补丁的独立文本检查、保留 TUI 片段检查及 27 个源码入口存在性检查。未执行新版构建和运行测试，未启动服务。活动 pin 与现有安装保持 1.1.0，升级需要先落实上述集成迁移。
