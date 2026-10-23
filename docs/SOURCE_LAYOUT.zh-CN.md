# 源码目录与职责

CoRAgent 使用唯一的 Pi Harness。目录按运行职责与发行阶段划分；目录迁移不改变工作区格式、命令身份或事务语义。

| 目录 | 所有权 |
| --- | --- |
| `apps/agent/` | Pi Agent、Host、终端、任务控制、研究上下文和业务工具适配 |
| `apps/cli/` | Python 命令行入口及选择托管解释器的最小启动代码 |
| `apps/web/` | 可选、独立发行的只读研究浏览器 |
| `apps/relay/` | 独立运行的 Link 中继服务 |
| `backend/src/research_agent/` | 单一 Python 业务包 |
| `packages/link/` | Host 与 Relay 共用的通信库 |
| `skills/core/`、`skills/chemical/` | 通用研究流程与化学方法、执行脚本及参考资料 |
| `contracts/` | 跨模块接口源定义 |
| `config/` | 操作者配置示例、配置 schema 和使用说明 |
| `packaging/coragent_packaging/installer/` | 安装、升级、环境准备和卸载 |
| `packaging/coragent_packaging/build/` | 源码捕获、wheel 和发行包构建、发行包检查；不随产品发行 |
| `packaging/coragent_packaging/manifests/` | 发行布局、产品身份、资源摘要与归档验证合同 |
| `packaging/coragent_packaging/pi/` | 唯一 Pi 源码版本、补丁及安装准备 |
| `tools/` | 代码生成、静态检查、版本维护和测试运行器 |
| `tests/` | 全项目测试；分类由 `tools/test/manifest.toml` 定义 |
| `assets/`、`docs/` | 产品资源与文档 |
| `local_debug/` | 本机私有环境、缓存、测试安装和证据；禁止提交、打包和外传 |
| `dist/` | 生成的发行产物 |

应用的源码位置不决定是否可选安装。Web 的独立发行和 Relay 的独立部署由各自的发行与安装流程决定。

## Agent 内部

`runtime/` 装配 Pi Harness、SessionWorker、输入接纳和服务。`runtime/source.mjs` 是唯一 Pi 内部源码路径入口；其他模块通过此入口加载内部能力，或直接使用公开 Pi API。

`host/` 拥有认证、工作区路由、连接与进程监督。Host 不写 Pi durable 文档，不保存另一份研究任务状态。输入接纳在 `runtime/admission/` 中，通过原有 Pi 事务同时接纳输入与记录来源。

`tasks/` 拥有研究任务的生命周期策略。Controller 直接使用 Pi durable 文档；assessment、recovery、execution-plan、execution-selection 和 projection 保持为不依赖会话基础设施的规则模块。模型与工具循环、提交状态和会话恢复仍由 Pi 拥有。

`context/` 组织研究背景和压缩材料；`tools/` 适配模型工具；`bridge/` 传输 Python 命令；`terminal/` 提供 Pi 客户端接入及科研展示；`transport/` 提供连接方式；`prompts/` 保存 Agent 提示词。

## Python 内部

`application/` 分派命令并协调研究记录、作业和文件证据。`research/` 保存研究对象和查询视图，不能依赖执行或应用协调层。`jobs/` 管理通用计算执行，科学方法与解析器归各自 Skill。`artifacts/` 保存固定文件及来源。

`configuration/` 解析和校验配置、解析凭据引用。`bootstrap/` 处理安装布局、运行环境与启动。`foundation/` 只保存文件 IO、事务、协议标识及路径安全。基础模块不依赖上层业务；后端不导入应用入口、安装器、构建器或开发工具。

## 启动与发行

CLI 的解释器选择代码位于 `apps/cli/_bootstrap.py`；选定托管解释器后，业务命令从已安装 wheel 导入。源码安装与尚未安装环境时的引导逻辑归 `packaging/coragent_packaging/installer/`，不要求先运行业务应用。

`packaging/` 本身不是 Python 包，避免覆盖第三方 `packaging` 库。打包工具统一使用 `coragent_packaging` 命名空间，其下按 `installer`、`build`、`manifests` 和 `pi` 分组，避免与科学脚本中的同名模块冲突；直接执行的入口显式设置工具导入路径。产品应用不导入这些工具模块。

`packaging/coragent_packaging/manifests/source-layout.json` 是发行文件归属的单一源；`tools/layout.py` 生成 npm 文件清单。构建工具和测试不进入发行包。源码安装需要构建时，使用源码树中的构建器；发行包安装使用其附带的已验证 wheel。

## 接口与生成文件

`contracts/commands/` 定义 Python 分派与模型工具共同使用的命令身份、参数和返回值。`tools/generate_contracts.py` 生成后端目录、Node 类型、schema 和测试样例。消费者旁的副本是生成产物，不能独立修改。

`tools/layout.py` 维护产品和协议身份副本；`tools/update_resources.py` 维护 Skill 和提示词摘要。生成器的 `--check` 是静态验收的一部分。局部实现类型留在所属模块，不提升为跨模块契约。

## 验证

使用 `python3 tools/test/runner.py verify` 检查静态规则、Python、原生 Pi、发行文件和安装 wheel。完整发行包还必须通过 `release --artifact ...`：从源码目录之外安装、启动、恢复并卸载。

静态架构检查禁止旧目录中的实现、后端对交付工具的反向依赖、Host 对 Pi durable 状态的直接所有权，以及分散的 Pi 私有源码导入。重构不提供旧路径转发模块、双协议入口或第二套事务接口。
