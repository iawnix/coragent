# Generic email delivery protocol

`message_id` identifies one authorized email message. It is stable across
retries and must not be changed to bypass an uncertain result. The request
uses `ts-email-message/1`; `attachments` contains at most eight regular files
under the workspace's `reports/` or `artifacts/` trees, each pinned by its
byte digest and size.

The transport locks the message identity, records a `sending` receipt before
opening SMTP, and then records `sent`, `failed`, or `unknown`. A failure proven
to precede SMTP transport can retry with the same identity. An uncertain result
must be reconciled first. Password rotation does not create a new delivery.

Receipts live under `artifacts/email/deliveries`. The transport does not write
research records, classify scientific status, validate a report manifest, or
choose a delivery event. A caller that needs those actions owns them and may
store the transport receipt as one of its own evidence references.

Chemical report delivery records its receipt through the application layer on the
controller. If updating the research journal fails after SMTP accepted the message,
the result remains `sent` and includes `journal_error`. Recover the research
projection from the existing receipt; do not send a second message to repair it.
