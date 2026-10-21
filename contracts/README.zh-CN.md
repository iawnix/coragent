# 框架契约

[English](README.md) | [简体中文](README.zh-CN.md)

本目录维护框架、执行运行时与客户端共享的机器接口。Skill 说明何时、如何使用这些接口，
不重复维护参数 schema，也不定义客户端传输协议。

| 归属 | 契约 | 使用方 |
| --- | --- | --- |
| 应用与工具 | [commands](commands/README.md) | Python 分派、Node 工具、生成类型与返回值检查 |
| 任务监控 | [Monitor API](monitor/README.md) | Host、终端和浏览器客户端 |
| 执行事件 | [Job Monitor 记录](monitor/jobs/README.md) | Python outbox 与 Host 事件通知 |
| 连接 | [Link](link/README.md) | Host、Relay 与设备客户端 |
| 工作区材料 | [Files](files/README.md) | Host 文件访问与手机预览 |
| 研究视图 | [Web](coragent-web/README.md) | 研究数据提供方与独立 Web 组件 |

目录按职责命名。`schema_version`、协议名称和 schema ID 标识当前传输或存储格式。

`tools/generate_contracts.py` 生成应用命令目录、Node 类型、随 Python 包分发的 Monitor schema，
以及命令测试样例。修改本目录源定义后重新生成，并运行 `--check`。
测试样例位于 `tests/fixtures/contracts/`，不进入产品包。运行时副本由生成器维护，不能独立修改。

领域输入输出格式归实际生产或消费它们的 Skill：用法说明放在 `references/`，脚本实际校验的
机器 schema 按需放在 `schemas/`。任务流程说明属于 `skills/core/research-workflow/`；
通用任务和 Job schema 属于框架。每项契约都应有明确的读写方，并用真实请求、记录或返回值验证。
