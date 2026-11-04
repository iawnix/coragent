import { createHash } from "node:crypto";

const MAX_BYTES = 24000;
const HISTORY = new Set(["audit", "progress_identities", "event_inputs", "completion_history"]);
const encode = value => JSON.stringify(value, null, 2);
const bytes = value => Buffer.byteLength(encode(value));
const digest = text => createHash("sha256").update(text).digest("hex");
const fail = (code, message) => { throw Object.assign(new Error(message), { code }); };

/** Model-facing view only. Durable records and runtime/Monitor readers stay intact. */
export function readTask(task, { field, offset = 0, limit = 8000, expected_digest } = {}) {
  if (!task) return null;
  if (field !== undefined) {
    if (!Object.hasOwn(task, field)) fail("task_field_unknown", "Select a current task field or a field listed in read_more.");
    if (!Number.isSafeInteger(offset) || offset < 0 || !Number.isSafeInteger(limit) || limit < 1 || limit > 12000)
      fail("task_page_invalid", "Use a nonnegative character offset and a limit between 1 and 12000.");
    if (offset > 0 && expected_digest === undefined)
      fail("task_digest_required", "Continue a field read with the digest returned by its first page.");
    const text = encode(task[field]), identity = digest(text);
    if (expected_digest !== undefined && identity !== expected_digest)
      fail("task_field_changed", "The selected field changed. Restart this field at offset 0 and reconsider dependent decisions.");
    const page = { user_task_id: task.user_task_id, revision: task.revision, field, digest: identity,
      format: "json", offset, total_chars: text.length, content: text.slice(offset, offset + limit), next_offset: null };
    // Escaping and multibyte text count against the same output budget.
    while (bytes(page) > MAX_BYTES - 64) page.content = page.content.slice(0, Math.floor(page.content.length / 2));
    page.next_offset = offset + page.content.length < text.length ? offset + page.content.length : null;
    return page;
  }
  if (offset !== 0 || expected_digest !== undefined) fail("task_field_required", "Specify field when continuing a task field read.");
  const view = { ...task, read_more: {} };
  const omit = key => {
    const text = encode(task[key]);
    view.read_more[key] = { field: key, total_chars: text.length, expected_digest: digest(text) };
    delete view[key];
  };
  for (const key of HISTORY) if (Object.hasOwn(task, key)) omit(key);
  // Current requirements normally fit in full. Oversized fields remain exactly
  // retrievable, with explicit omission instead of a silently truncated JSON tail.
  for (const key of Object.keys(task).filter(key => !HISTORY.has(key))
    .sort((a, b) => bytes(task[b]) - bytes(task[a]))) {
    if (bytes(view) <= MAX_BYTES - 1000) break;
    omit(key);
  }
  view.read_guidance = "read_more lists omitted fields, not missing requirements. Use task_read with field, offset and expected_digest to retrieve needed details. Read omitted requirements before changing scope or assessing completion; audit and progress identities do not need routine rereading. Reuse this revision within a stable analysis step; refresh on task changes or revision conflicts, not before each file page.";
  return view;
}
