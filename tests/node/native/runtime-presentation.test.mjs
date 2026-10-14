import assert from "node:assert/strict";
import test from "node:test";
import { join } from "node:path";
import { pathToFileURL } from "node:url";
import { markInternalInput, RUNTIME_TASK_CONTINUATION_START, RUNTIME_TASK_CONTINUATION_END } from "../../../apps/agent/host/admission/input.mjs";
import { pinnedPiSource } from "./test-environment.mjs";

const source = pinnedPiSource();

test("task-controller input is marked for presentation without changing model role", () => {

  const prompt = "Continue the existing authorized user task using the runtime task snapshot.";
  const marked = markInternalInput(prompt, "task_controller");
  assert.equal(marked, `${RUNTIME_TASK_CONTINUATION_START}\n${prompt}\n${RUNTIME_TASK_CONTINUATION_END}`);
  assert.equal(markInternalInput(prompt, "monitor"), prompt);
  const richContent = [ { type: "text", text: prompt } ];
  assert.deepEqual(markInternalInput(richContent, "task_controller"), richContent);
});

test("runtime continuation renderer recognizes current and legacy messages", async () => {
  const { isRuntimeTaskContinuation, RuntimeTaskMessageComponent } = await import(pathToFileURL(join(
    source, "packages/coding-agent/src/modes/interactive/components/runtime-task-message.ts",
  )));
  const { initTheme } = await import(pathToFileURL(join(
    source, "packages/coding-agent/src/modes/interactive/theme/theme.ts",
  )));
  initTheme("dark");
  const prompt = "Continue the existing authorized user task using the runtime task snapshot.";
  assert.equal(isRuntimeTaskContinuation(`${RUNTIME_TASK_CONTINUATION_START}\n${prompt}\n${RUNTIME_TASK_CONTINUATION_END}`), true);
  assert.equal(isRuntimeTaskContinuation(prompt), true);
  assert.equal(isRuntimeTaskContinuation("Recover only the final response for the existing completion proposal."), true);
  assert.equal(isRuntimeTaskContinuation("Please inspect the candidate transition state."), false);
  const rendered = new RuntimeTaskMessageComponent().render(100).join("\n");
  assert.match(rendered, /Continuing authorized task/);
  assert.match(rendered, /internal runtime/);
});
