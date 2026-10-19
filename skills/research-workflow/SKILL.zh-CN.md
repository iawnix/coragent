---
name: research-workflow
description: 通过原生研究闭环协调任务、研究 Node、科学 Job、材料、证据和交付。
---

# 研究工作流

[English version](SKILL.md)

执行持续研究任务时使用本 Skill。它连接用户需求、Research Memory、领域 Skill、托管 Job、证据检查和最终交付；领域 Skill 负责科学方法，本 Skill 负责任务状态、执行生命周期和持久进度。

## 启动与恢复

1. 检查 `runtime_control` 和 `research-review/1` 上下文；通过 `task_read` 恢复已有任务的要求和状态。
2. 仅在没有未结束任务且开始新委托时使用 `task_begin`，传入真实用户 submission ID、覆盖每项交付物的目标与标准、`initial_plan` 和 `next_action`。后续请求沿用当前任务，新增用户要求通过 `task_update action=refine` 更新。读取任务不会恢复暂停或阻塞的工作：暂停需要用户明确恢复，阻塞解除后需引用新用户指令执行 `refine`。
3. 用 `research_create` 创建或选择 Node，再用 `task_update action=set_research` 绑定 entry/focus Node。
4. 读取相关领域 Skill，选择下一项能区分假设的操作。

用 `task_update` 记录有意义进度、明确等待、具体阻塞、完成证据或用户暂停/恢复/取消。用户控制用 `action=apply_user_control`、当前 `expected_revision`、真实 `source_submission_ids` 和 `control` 持久化。取消时按用户意图设置 `jobs=cancel` 或 `jobs=keep`，并检查返回的取消回执。

## 执行与记录

文件放在返回的 research `work_dir` 或 `research/work`，报告放在 `reports/`。科学计算用 `job_start` 启动并传入目标 `node_id`，用 `job_collect` 收集输出。准备和诊断可以不关联 Node。检查收敛、几何、频率、连通性和方法元数据后，再写 `research_update` 或 `research_result`。

同一问题的重试和扫描点留在 Node。路线不再提供信息时，记录失败类型并改变方法、种子、端点或假设。重复提交前检查已有回执；不确定调度通过身份和回执核对。

## 交付闭环

把每项交付标准对应到不可变 Result 或 Material，确认剩余 Job，再由报告/领域 Skill 组装所需输出。部分和否定结果都是有用进度；是否完成取决于约定范围和证据。邮件交付使用[email Skill](../email/SKILL.zh-CN.md)，准备消息并保留发送回执。

Job 命令和文件约定见[工具与执行](references/tools.zh-CN.md)，领域路由见[Skill 资源路径](references/skills.zh-CN.md)，可调用接口见[公共合同](references/public_contract.zh-CN.md)。多步化学使用[路径证据合同](../../domains/chemical/skills/reaction-investigation/references/pathway_execution.zh-CN.md)。
