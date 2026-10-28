# CoRAgent 文档

[English](README.md) | 简体中文

从安装与终端使用开始。以下指南描述当前源码和版本化合同；已完成的实施计划和一次性
验收记录保留在 Git 历史中，不再作为当前操作说明。

## 使用与运维

| 需求 | 文档 |
| --- | --- |
| 安装、配置、升级和卸载 | [安装与运维](INSTALLATION.zh-CN.md)、[目录布局](APP_LAYOUT.zh-CN.md) |
| 终端、会话和 Monitor | [终端](TERMINAL.zh-CN.md) |
| 手机连接及客户端协议 | [CoRAgent Link](CORAGENT_LINK.zh-CN.md)、[Phone 协议](PHONE_PROTOCOL.zh-CN.md) |
| 模型、凭据和上下文容量 | [模型配置](MODEL_COMPATIBILITY.zh-CN.md) |
| 科学计算方法和支持范围 | [科学执行与运维](SCIENTIFIC_CAPABILITIES_OPERATIONS.zh-CN.md)、[能力清单](../skills/chemical/method-selection/references/capabilities.zh-CN.md) |
| 调度器接入和 Job 资源 | [外部 Job](EXTERNAL_JOBS.zh-CN.md)、[Qrun 本机／SSH 队列](QRUN.zh-CN.md) |
| Skill 和操作入口 | [Skill 目录](../skills/README.zh-CN.md)、[脚本索引](skill-script-routing.zh-CN.md) |

## 理解与维护

| 需求 | 文档 |
| --- | --- |
| 运行时和存储职责 | [架构](ARCHITECTURE.zh-CN.md)、[执行边界（英文）](ARCHITECTURE_BOUNDARIES.md) |
| 源码目录、依赖与发行归属 | [目录与职责](SOURCE_LAYOUT.zh-CN.md) |
| Task Controller、Job Manager 和输入接纳 | [任务与作业架构](TASK_JOB_ARCHITECTURE.zh-CN.md) |
| Research Memory 的选择、注入和模型摘要 | [研究上下文](RESEARCH_CONTEXT.zh-CN.md) |
| Node 划分、规划和修正 | [研究规划](RESEARCH_PLANNING.zh-CN.md) |
| 证据、材料和来源 | [Research Memory Skill](../skills/core/research-memory/SKILL.zh-CN.md)、[证据架构](RESEARCH_EVIDENCE_ARCHITECTURE.zh-CN.md)、[Artifact Store（英文）](ARTIFACT_PROVIDERS.md) |
| Skill 加载、提示词组装和执行声明 | [Skill 与执行目录](EXTENSIONS.zh-CN.md) |
| 维护、测试和打包 | [维护指南](MAINTAINER_GUIDE.zh-CN.md)、[贡献指南](../CONTRIBUTING.zh-CN.md)、[测试运行器（英文）](../tools/test/README.md) |
| 科学回归的覆盖范围 | [领域科学回归](SCIENTIFIC_REGRESSIONS.zh-CN.md) |
| 固定 Pi 运行时集成 | [Pi 补丁（英文）](PI_RUNTIME_PATCHES.md) |

[命名计算平台与多集群执行](EXECUTION_PLATFORMS.zh-CN.md)说明平台／入口配置、共享环境、
存储、任务计划与安装入口选择。

## 待实施提案

[Pi 1.3.0 升级审查](PI_1_3_MIGRATION.zh-CN.md)是注明日期的上游对照和未实施建议。
当前固定 Pi 1.4.0；参见[迁移与回滚说明](PI_1_4_MIGRATION.zh-CN.md)。

## 文档维护

按源码、配置示例和 schema 核对命令与路径，中英文成对更新。每项合同保留一份当前说明，
其他位置通过链接引用；已完成方案中的有效指导合入指南后，删除旧计划。尚未实施的提案
明确标注。测试结果只适用于对应源码或发行产物，历史通过记录不能证明后续版本已经验收。

项目源码采用 [Apache License 2.0](../LICENSE)；第三方依赖、固定 Pi 源码和素材保留各自许可证。

- [TRI 部署与维护](TRI_OPERATIONS.zh-CN.md)
