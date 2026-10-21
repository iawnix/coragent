# 化学报告邮件交付

报告 Skill 是通用 SMTP 邮件运输层之上的策略层。它判断用户请求是否授权发送，并选择报告事件：
`progress`、`report_ready`、`calculation_failed`、`calculation_ambiguous` 或 `study_completed`。
事件放在通用消息由调用方负责的 `metadata` 中；邮件运输层不校验也不解释这些事件。

报告请求包含 `notification_id`、`event`、`subject`、`summary` 和 `report_refs`。每个引用必须是已登记
报告包中的普通文件，并与 `ts-report-package/5` 清单匹配。适配器将其转换为 `ts-email-message/1`，
固定附件摘要，并在 metadata 中保留事件与清单摘要。科学结果、完成声明和局限必须依据报告证据表述；
运输层接受邮件不代表科学结论已认证。

使用 `scripts/email_delivery.py` 执行这层编排。它调用通用 email Skill 负责 SMTP 和回执，并在存在研究日志时
登记交付。重试使用同一个 `notification_id`；运输结果不确定时先核查再重试。
