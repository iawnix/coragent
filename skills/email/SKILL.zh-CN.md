---
name: email
description: 通过安装配置的 SMTP 运输层发送已明确授权的邮件，并保存持久、幂等的发送回执。
---

# 邮件运输层

这个 Skill 只提供运输接口。它不决定何时发送、邮件代表什么、对应哪个领域事件，
也不决定哪些文件应作为附件。调用方先准备通用邮件消息，并在用户明确授权后调用本 Skill。

收件人来自安装配置。通过 `CORAGENT_NOTIFICATION_CONFIG` 检查 SMTP 配置；凭据不能复制到
邮件请求或发送回执中。

通用消息合同为 `ts-email-message/1`：

```json
{
  "schema_version": "ts-email-message/1",
  "message_id": "stable-authorized-delivery-id",
  "subject": "邮件主题",
  "body": "邮件正文",
  "attachments": [
    {"ref": "artifacts/example.txt", "sha256": "sha256:...", "size_bytes": 123}
  ],
  "metadata": {"optional": "由调用方定义的上下文"}
}
```

`prepare` 固定配置收件人与附件摘要，但不发送；`send` 接收已准备好的消息，重新核对 SMTP
配置和附件并返回回执。`sent` 表示 SMTP 服务器已接受消息；同一消息再次发送返回
`already_sent`。结果为 `unknown` 时必须先核查，不能直接重试。

```text
"$CORAGENT_PYTHON" <此 Skill 目录>/scripts/email_cli.py check --root <工作区> --output <工作区>/email-check.json
"$CORAGENT_PYTHON" <此 Skill 目录>/scripts/email_cli.py prepare --root <工作区> --request-file <工作区>/email-message.json --output <工作区>/email-prepared.json
"$CORAGENT_PYTHON" <此 Skill 目录>/scripts/email_cli.py send --root <工作区> --request-file <工作区>/email-prepared.json --output <工作区>/email-result.json
```

领域 Skill 负责组织邮件内容和领域授权，然后调用这个运输接口。

通用消息、回执和重试合同见[交付协议](references/email_delivery.zh-CN.md)。
