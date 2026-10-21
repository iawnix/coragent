---
name: tri-operations
description: 部署和维护 TRI 队列服务端与计算节点客户端，配置连接和节点容量，管理服务健康、数据库历史、备份及升级。
---

# TRI 基础设施运维

## 脚本路由

本 Skill 使用已安装的 TRI 和系统服务命令，见[脚本路由地图](../../docs/skill-script-routing.zh-CN.md#tri-operations)。作业提交、资源转换、取消和恢复使用[批处理调度器](../batch-schedulers/SKILL.zh-CN.md)。

[English version](SKILL.md)

## 确认安装

定位 `tri-server`、`tri-client` 和 `tri_node`，通过安装元数据记录构建身份。用 `tri-client --help` 和 `tri_node --help` 核实当前参数。服务端入口会启动服务，应通过服务定义识别它。

确认服务所属用户、system/user 服务类型、socket/TCP 地址、数据库路径和已注册节点。认证令牌保留在受保护环境文件中。CLI 优先连接存在的 `TRI_SOCKET`，否则使用 `TRI_SERVER_ADDR` 的 TCP 地址。

## 部署与维护

[服务部署](references/service-setup.zh-CN.md)说明服务端/客户端安装、服务单元、共享路径、资源声明、验收、备份、升级和历史保留。单机同时运行服务端与客户端；多计算节点以不同节点名注册到同一队列服务端。

用 `tri_node --json`、`tri_node --check` 检查注册、容量、cgroup 和用户服务管理器，并检查实际服务端/客户端单元及日志。连接失败时检查地址、权限、服务健康和网络；协议不匹配时核对服务端、CLI、客户端构建身份；节点离线时先检查客户端服务与心跳连接，再调整声明容量。

## 验证维护结果

修改服务或容量后，核对节点注册、已有 attempt，并执行部署说明中的有限诊断任务。登录主机检查不能证明计算节点软件就绪，逐节点检查使用[软件验收流程](../batch-schedulers/references/tri.zh-CN.md)。

交付时说明受影响服务/节点和验证结果。单个排队、失败、失联或取消 Job 的分析见[TRI 任务诊断](../batch-schedulers/references/tri-diagnosis.zh-CN.md)，维护时保留已有执行身份。
