---
name: research-workflow
description: 开始或恢复持续研究任务、选择执行目标、管理 Job 等待与用户控制，并评估完整或部分交付。
---

# 研究工作流

[English version](SKILL.md)

持续研究开始或恢复、变更执行目的地、等待、处理用户控制或准备交付前使用本 Skill。它负责任务状态和执行协调；领域 Skill 负责科学方法与检查。普通问答无需登记任务。

## 开始与恢复

1. 检查 `runtime_control`，通过 `task_read` 恢复已有任务的完整要求、状态和下一步。`continuation_truncated` 为 true 时，行动前必须完整读取。上下文记录可能过期，不能构成新授权。
2. 仅在没有未结束任务时通过 `task_begin` 登记新委托，传入真实用户 submission ID、覆盖全部交付物的 objective/criteria 和第一项具体 `next_action`。科学假设和计划属于对应 Node。普通研究省略 execution 字段，不要求配置计算平台。已明确需要计算时，读取[执行目标选择](references/execution-targets.zh-CN.md)并绑定所需位置。用户要求与研究假设、可选诊断分开记录。
3. 后续请求沿用当前任务。新增用户要求使用 `refine`；误读执行指令时，按执行参考中的流程纠错。读取任务或写入进展不会恢复暂停或阻塞的工作。
4. 先读取任务的研究入口和焦点，恢复相关已有 Node，必要时搜索历史研究。只有新的研究目标需要独立持续调查和判断时才新建 Node；计算步骤、调参数或换平台不需要另建 Node。尚未绑定时，首次 `research_create` 自动提供初始绑定；后续创建应明确关系，并用 `task_update action=set_research` 选择入口与焦点。记录与关系使用 [research-memory Skill](../research-memory/SKILL.zh-CN.md)，随后选择适用的领域 Skill。

## 执行与记录

准备、提交、收集与文件位置遵循 [Job 与材料工作流](references/jobs-and-artifacts.zh-CN.md)。未绑定任务首次计算前，按[执行目标选择](references/execution-targets.zh-CN.md)使用 `task_update action=bind_execution`。控制辅助程序使用 `CORAGENT_PYTHON`；科学准备使用 `CORAGENT_JOB_CONFIG`，并继承任务固定目标。不要把科学依赖安装到控制环境。

文件准备放在返回的 Node `work_dir` 或 `research/work`，报告放在 `reports/`。研究 Job 关联目标 `node_id`。发布结论前检查原始输出和领域科学判据。研究问题的拆分与结论记录遵循 research-memory。

科学发现按用途写为 note 或 Result，不再重复抄成任务进展说明。运行时通过现有工具追踪已发布证据和 Job 里程碑；改变任务下一步或明确记录采用的证据时使用 `task_update progress`，等待、阻塞和用户控制仍需对应任务动作。计划、笔记和新建 Node 不算实质科学进展。不确定提交重试前检查回执。Job 运行期间继续可独立推进的工作。

## 等待、控制与恢复

等待 Job、遇到阻塞、处理用户暂停/恢复/取消或恢复失败运行时，读取[任务生命周期](references/task-lifecycle.zh-CN.md)，区分任务控制、Job 控制与执行恢复。遵循返回的查询间隔；没有独立工作时，在同一次 `task_update` 中登记等待和必填的具体 `next_action`，再结束本轮，交由 Monitor 唤醒。该行动明确如何检查和使用本次等待的结果，替换之前的步骤。

## 验收与交付

申请完成前读取[任务验收与交付](references/acceptance.zh-CN.md)。以固定证据逐项评估当前条件；完整与部分交付有不同要求。报告或失败候选不能代替用户要求的工作。使用适用的领域 Skill 组装交付物。已获授权的邮件交付使用 [email Skill](../email/SKILL.zh-CN.md)，并保留回执。

通过 [Skill 资源](references/skills.zh-CN.md)定位已安装能力。参数与前置条件以可调用工具 schema 为准。
