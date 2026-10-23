# Phone 客户端协议

本文描述当前 CoRAgent 服务端合同。CoRHub 在独立仓库维护；这里不指定其版本号、
内部文件位置或发布状态。连接与配对见[CoRAgent Link](CORAGENT_LINK.zh-CN.md)。

## 协议身份

规范值来自 `packaging/coragent_packaging/manifests/identity.json`，由 `tools/layout.py` 同步到运行时代码：

| 项目 | 当前值 |
| --- | --- |
| Host initialize 请求和响应 | `coragent-host/3` |
| Link WebSocket 子协议、配对响应 protocol | `coragent-link.v1` |
| Phone 设备 token 前缀 | `cad_` |
| Host token 前缀 | `cah_`，仅 Host 使用 |

Host 和 Link 是两个传输层，版本号独立。客户端应使用当前 Host 协议，不回退到旧版本。
设备 token 由服务端签发；修改旧 token 的前缀不能转换身份。

## 配对和连接

- 配对兑换：`POST /v1/pairings/redeem`，字段为 `code`、`deviceName`。
- 响应包含 `relayUrl`、`protocol`、`hostId`、`deviceId`、`deviceName`、`deviceToken`。
- Link 路径：`/v1/link`；认证头：`Authorization: Bearer <device-token>`。
- 配对码有效期五分钟、只能使用一次。`hostId` 和 `deviceId` 是 UUID，设备绑定指定 Host。
- Host 消息是 UTF-8 NDJSON，通过 WebSocket 二进制帧传输。

初始化示例（实际发送为单行 JSON 加换行）：

```json
{
  "id": "phone-1",
  "method": "initialize",
  "params": {
    "protocol": "coragent-host/3",
    "server_id": "00000000-0000-4000-8000-000000000001",
    "client": { "name": "corhub" }
  }
}
```

客户端根据 initialize 返回的 capabilities 展示功能。会话创建、恢复和 `model/select`
使用 `model: {provider, id}`。读取与附着的游标为 `after_cursor: {epoch, sequence}`；
epoch 改变时重新读取快照。输入使用稳定 `client_message_id`，响应丢失后查询 `input/status`。

## Monitor 和材料

Monitor 方法、请求字段、分页和 DTO 以[Monitor 合同](../contracts/monitor/README.md)为准。
任务控制需要稳定 `request_id` 和当前 `expected_revision`；取消任务明确选择
`jobs: "keep"` 或 `jobs: "cancel"`。控制状态保存在 SessionWorker 的 Pi durable 中。

执行记录区分 `producer` 和 `reason`：来源为 `user`、`job_manager`、`task_controller`，
原因为 `user_message`、`job_event`、`task_continue`、`execution_retry` 或
`final_response_retry`。Task DTO 使用 `research_context`，其可用性、投影完整性及摘要状态
含义见[研究上下文](RESEARCH_CONTEXT.zh-CN.md)。

`monitor/event` 和 `session/event` 是刷新提示；重连后重新取得快照。
`files/*` 提供目录、内容范围读取及材料固定能力，详见[文件合同](../contracts/files/README.md)。
这些查询不调用模型，也不会自动恢复用户暂停的任务。

## 客户端验收

握手、配对、撤销和消息合同可用本仓库的确定性 Host/Link 测试验证。
真实 Dart 客户端互操作使用 `tools/test/runner.py phone`，需要显式提供客户端源码、
本机私有测试目录下的 Flutter SDK 和缓存，参见[测试运行器](../tools/test/README.md)。
客户端联调和手机实机验收是不同范围，服务端测试通过不代表两者已经完成。
