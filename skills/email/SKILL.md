---
name: email
description: Deliver an explicitly authorized email through the installation's SMTP transport, with durable idempotent receipts.
---

# Email transport

This Skill is a transport interface. It does not decide when a message should
be sent, what a message means, which domain event it represents, or which files
belong in an attachment. A caller prepares a generic email message and invokes
this Skill only after the user has authorized the delivery.

The configured recipient owns addressing. The SMTP configuration is inspected
through `CORAGENT_NOTIFICATION_CONFIG`; credentials are never copied into a
message request or a receipt.

The generic message contract is `ts-email-message/1`:

```json
{
  "schema_version": "ts-email-message/1",
  "message_id": "stable-authorized-delivery-id",
  "subject": "Message subject",
  "body": "Message body",
  "attachments": [
    {"ref": "artifacts/example.txt", "sha256": "sha256:...", "size_bytes": 123}
  ],
  "metadata": {"optional": "caller-owned context"}
}
```

`prepare` pins the configured recipient and attachment digests without sending.
`send` accepts the prepared message, revalidates the SMTP configuration and
attachments, and returns a receipt. `sent` means the SMTP server accepted the
message; `already_sent` is the idempotent result for the same message. An
`unknown` result must be reconciled before another attempt.

```text
"$CORAGENT_PYTHON" <this Skill directory>/scripts/email_cli.py check --root <workspace> --output <workspace>/email-check.json
"$CORAGENT_PYTHON" <this Skill directory>/scripts/email_cli.py prepare --root <workspace> --request-file <workspace>/email-message.json --output <workspace>/email-prepared.json
"$CORAGENT_PYTHON" <this Skill directory>/scripts/email_cli.py send --root <workspace> --request-file <workspace>/email-prepared.json --output <workspace>/email-result.json
```

Domain Skills own message composition and domain-specific authorization before
calling this transport.

Read [delivery protocol](references/email_delivery.md) for the generic
message, receipt, and retry contract.
