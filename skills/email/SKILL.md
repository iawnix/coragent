---
name: email
description: Deliver an authorized email through configured SMTP with prepared attachments and durable idempotent receipts.
---

# Email delivery

## Script routing

Use the [script routing map](../../docs/skill-script-routing.md#email) before invoking a bundled script. It identifies the supported entrypoint and interface; helper files under `scripts/` are not standalone commands. Do not inspect source code to discover invocation details.

**Entrypoint:** `skills/email/scripts/email_cli.py` (see the map for its stdin/subcommand contract).

[Chinese version](SKILL.zh-CN.md)

Use this Skill after a domain Skill has composed a message and the user has authorized sending. It checks the configured SMTP transport, pins attachment digests, sends once, and records a receipt that can be reconciled after an interrupted delivery.

## Message workflow

1. Write a `ts-email-message/1` request with a stable `message_id`, subject, body, attachment references/digests, and caller metadata.
2. Run `check` against `CORAGENT_NOTIFICATION_CONFIG` to confirm the configured recipient and transport.
3. Run `prepare` to pin the recipient and attachment files. Review the prepared message before delivery.
4. Run `send` with the prepared request. A successful SMTP acceptance returns `sent`; repeating the same message returns `already_sent`.
5. If the receipt is `unknown`, inspect the delivery record and SMTP state before another attempt. Keep the receipt with the research report.

```text
"$CORAGENT_PYTHON" <this Skill directory>/scripts/email_cli.py check --root <workspace> --output <workspace>/email-check.json
"$CORAGENT_PYTHON" <this Skill directory>/scripts/email_cli.py prepare --root <workspace> --request-file <workspace>/email-message.json --output <workspace>/email-prepared.json
"$CORAGENT_PYTHON" <this Skill directory>/scripts/email_cli.py send --root <workspace> --request-file <workspace>/email-prepared.json --output <workspace>/email-result.json
```

The caller owns message composition, recipient intent, and domain authorization. SMTP credentials stay in the configured environment and are absent from requests and receipts. Read [delivery protocol](references/email_delivery.md) for schema, receipt states, attachment pinning, and reconciliation.
