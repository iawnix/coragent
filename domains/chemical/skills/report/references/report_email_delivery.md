# Chemical report email delivery

The report Skill is the policy layer above the generic SMTP email transport.
It decides whether a user request authorizes delivery and chooses one of these
report events: `progress`, `report_ready`, `calculation_failed`,
`calculation_ambiguous`, or `study_completed`. The event is stored in the
generic message's caller-owned `metadata`; the email transport never validates
or interprets it.

Prepare a report request with `notification_id`, `event`, `subject`, `summary`,
and `report_refs`. Each reference must be a regular file in a registered report
package and match that package's `ts-report-package/5` manifest. The adapter
converts it to `ts-email-message/1`, pins attachment digests, and preserves the
event and manifest digests in metadata. A scientific result, completion claim,
or limitation must be stated from the report evidence; sending acceptance does
not certify the science.

Use `scripts/email_delivery.py` for this orchestration. It calls the generic
email Skill for SMTP and receipt handling, then registers the delivery in the
research journal when that journal is present. A retry uses the same
`notification_id`; an uncertain transport result is reconciled before retrying.
