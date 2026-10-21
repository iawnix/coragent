---
name: email
description: 通过配置的 SMTP 发送已授权邮件，固定附件并保存持久、幂等的发送回执。
---

# 邮件交付

## 脚本路由

使用下文链接的本 Skill 操作合同与命令说明。未列为入口的辅助文件不作为独立命令调用。

[English version](SKILL.md)

用户要求的邮件内容准备好并获得发送授权后，使用本 Skill。它检查 SMTP 配置、固定附件 digest、执行一次发送，并在中断后提供可核对的回执。

## 消息流程

1. 写入 `ts-email-message/1` 请求，包含稳定的 `message_id`、主题、正文、附件引用/digest 和调用方元数据。
2. 用 `check` 检查 `CORAGENT_NOTIFICATION_CONFIG` 中的收件人与传输配置。
3. 用 `prepare` 固定收件人和附件文件，发送前审阅准备好的消息。
4. 用准备好的请求运行 `send`。SMTP 接受返回 `sent`；相同消息再次发送返回 `already_sent`。
5. 若回执为 `unknown`，先检查交付记录和 SMTP 状态，再决定是否重试，并把回执保存在研究报告中。

```text
"$CORAGENT_PYTHON" <此 Skill 目录>/scripts/email_cli.py check --root <工作区> --output <工作区>/email-check.json
"$CORAGENT_PYTHON" <此 Skill 目录>/scripts/email_cli.py prepare --root <工作区> --request-file <工作区>/email-message.json --output <工作区>/email-prepared.json
"$CORAGENT_PYTHON" <此 Skill 目录>/scripts/email_cli.py send --root <工作区> --request-file <工作区>/email-prepared.json --output <工作区>/email-result.json
```

调用方负责邮件内容、收件人意图和领域授权。SMTP 凭据保存在配置环境中，不写入请求或回执。schema、回执状态、附件固定和核对流程见[交付协议](references/email_delivery.zh-CN.md)。
