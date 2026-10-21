---
name: tri-operations
description: 安装和运维 TRI 任务队列，配置服务端与计算节点、管理资源，排查排队、失败、失联任务及 CoRAgent 接入问题。
---

# TRI 运维

## 脚本路由

调用仓库脚本前先看[脚本路由地图](../../docs/skill-script-routing.zh-CN.md#tri-operations)。地图列出支持的入口和接口；`scripts/` 下的 helper 不是独立命令。不要通过读取源码发现调用方式。

**入口：** `skills/tri-operations/scripts/queue.py`（stdin/子命令合同见脚本地图）。

[English version](SKILL.md)

在部署 TRI、配置节点与资源、维护服务、排查任务时使用。TRI 由持久队列服务端、计算节点客户端和命令行工具组成，适用于单机以及共享任务文件的多机环境。

## 选择操作

- 安装、服务配置、容量调整或升级，阅读[服务部署](references/service-setup.zh-CN.md)。
- 排队、失败、失联、取消、日志、重试身份和历史清理，阅读[任务诊断](references/task-diagnosis.zh-CN.md)。
- 在登录节点直接接入 TRI，或通过 SSH 接入，阅读 [CoRAgent Job 接入](references/coragent-jobs.zh-CN.md)。
- 排查 CoRAgent Job 时，从回执找到执行目标和 TRI `scheduler_id`。[research-workflow](../research-workflow/SKILL.zh-CN.md) 说明 Job 提交、状态核对和结果收集；下面的 TRI 工具用于检查底层调度器。

## 确认实际安装

用 `command -v tri_sub tri_stat tri_node tri-server tri-client` 定位程序。用 `tri_sub --help`、`tri_stat --help` 和 `tri-client --help` 核实当前版本参数，从安装元数据记录版本或构建身份。服务端入口会直接启动服务，应通过服务定义和发行元数据识别它。

确认服务所属用户、system/user 服务类型、socket/TCP 地址、数据库路径和计算节点。按需读取地址与路径配置，认证令牌保留在已有的受保护环境文件中。原生命令优先连接存在的 `TRI_SOCKET`，否则通过 `TRI_SERVER_ADDR` 连接 TCP。

## 检查队列

配置好目标连接地址后：

```bash
tri_node --json
tri_node --check
tri_stat --json
tri_ls --json
```

检查具体任务时，将 `TRI_TASK_ID` 设置为 TRI 返回的数字 ID：

```bash
tri_stat --json "$TRI_TASK_ID"
tri_log "$TRI_TASK_ID"
tri_log --stderr "$TRI_TASK_ID"
```

`tri_top` 提供交互式队列视图。交互维护直接使用原生命令。随附的 [queue.py](scripts/queue.py) 为后台 CoRAgent Job 提供稳定的提交、查询、取消和恢复操作。

## 完成操作

对已定位的服务或任务执行用户要求的维护，再复查对应状态。配置变更后检查节点能力；取消任务后检查任务状态、进程退出和资源释放。部署验收使用部署参考中的小型诊断任务。多节点 CoRAgent 后端覆盖使用 [Job 接入](references/coragent-jobs.zh-CN.md)中的逐节点验收，不能把登录主机探测当成集群验证。交付时说明受影响目标、观察到的原因、修改和验证结果。CoRAgent 任务通过原 Job 核对状态、收集结果，保留输出的生产者身份。
