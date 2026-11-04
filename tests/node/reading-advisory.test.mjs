import assert from "node:assert/strict";
import test from "node:test";
import { readingAdvisory } from "../../apps/agent/context/reading.mjs";

const call = (name, args = {}) => ({ role: "assistant", content: [{ type: "toolCall", name, arguments: args }] });
const result = (revision, extra = {}) => ({ role: "toolResult", toolName: "task_read",
  content: [{ type: "text", text: JSON.stringify({ revision, ...extra }) }] });
const loop = (count = 8) => Array.from({ length: count }, (_, i) => [call("task_read"), result(7),
  call("read", { path: "/workspace/results.json", offset: 1 + i * 33, limit: 35 })]).flat();

test("unchanged task reads between small file windows produce a replanning advisory", () => {
  const messages = loop(), original = structuredClone(messages);
  assert.match(readingAdvisory(messages), /structured parsing/);
  assert.match(readingAdvisory(messages), /does not block tools/);
  assert.deepEqual(messages, original);
});

test("new input, task changes and productive tools bound the observation", () => {
  assert.equal(readingAdvisory(loop(3)), undefined);
  assert.equal(readingAdvisory([...loop(), { role: "user", content: "Inspect another endpoint." }]), undefined);
  assert.equal(readingAdvisory([...loop(), call("bash", { command: "python analyze.py" })]), undefined);
  assert.equal(readingAdvisory([...loop(), call("task_update"), ...loop(2)]), undefined);
  assert.equal(readingAdvisory([...loop(), result(8)]), undefined);
});

test("needed field pagination and ordinary file paging do not count as task rereads", () => {
  assert.equal(readingAdvisory(Array.from({ length: 12 }, () => result(7, { field: "sources" }))), undefined);
  assert.equal(readingAdvisory(loop().filter(message => message.role !== "toolResult")), undefined);
  const failed = Array.from({ length: 12 }, () => ({ ...result(7), isError: true }));
  assert.equal(readingAdvisory(failed), undefined);
});
