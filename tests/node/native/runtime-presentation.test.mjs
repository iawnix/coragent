import assert from "node:assert/strict";
import test from "node:test";
import { join } from "node:path";
import { pathToFileURL } from "node:url";
import { markInternalInput, RUNTIME_TASK_CONTINUATION_START, RUNTIME_TASK_CONTINUATION_END } from "../../../apps/agent/runtime/admission/input.mjs";
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
  const { isRuntimeTaskContinuation, createChatView } = await import("../../../apps/agent/terminal/chat.mjs");
  const [components,themes] = await Promise.all([
    import(pathToFileURL(join(source,"packages/tui/src/index.ts"))),
    import(pathToFileURL(join(source,"packages/coding-agent/src/modes/interactive/theme/theme.ts"))),
  ]);
  themes.initTheme("dark");
  const prompt = "Continue the existing authorized user task using the runtime task snapshot.";
  assert.equal(isRuntimeTaskContinuation(`${RUNTIME_TASK_CONTINUATION_START}\n${prompt}\n${RUNTIME_TASK_CONTINUATION_END}`), true);
  assert.equal(isRuntimeTaskContinuation(prompt), true);
  assert.equal(isRuntimeTaskContinuation("Recover only the final response for the existing completion proposal."), true);
  assert.equal(isRuntimeTaskContinuation("Please inspect the candidate transition state."), false);
  const chat = createChatView({components,theme:themes.theme,markdownTheme:themes.getMarkdownTheme(),requestRender(){}});
  chat.update({docs:{},entries:[{id:1,kind:"pi.user",model:[{role:"user",content:markInternalInput(prompt,"task_controller")}]}]});
  const rendered = chat.render(100).join("\n");
  assert.match(rendered, /Continuing authorized task/);
  assert.match(rendered, /internal runtime/);
});

test("unified credentials preserve other secrets through native Pi refresh and deletion", async () => {
  const { mkdtemp, readFile, writeFile, rm } = await import("node:fs/promises");
  const { TEST_ROOT } = await import("./test-environment.mjs");
  const root = await mkdtemp(join(TEST_ROOT, "credentials-"));
  const credentialPath = join(root, "credentials.json");
  const previous = process.env.CORAGENT_CREDENTIALS_FILE;
  try {
    await writeFile(credentialPath, JSON.stringify({
      models: { fixture: { type: "oauth", access: "fake-old", refresh: "fake-refresh", expires: 0 } },
      secrets: { smtp_password: "fake-smtp", tri_token: "fake-tri" },
    }), { mode: 0o600 });
    process.env.CORAGENT_CREDENTIALS_FILE = credentialPath;
    const { AuthStorage } = await import(pathToFileURL(join(source, "packages/coding-agent/src/core/auth-storage.ts")));
    const first = AuthStorage.create();
    const second = AuthStorage.create();
    await first.modify("fixture", async credential => ({ ...credential, access: "fake-refreshed" }));
    assert.equal((await second.read("fixture")).access, "fake-refreshed");
    await Promise.all([
      first.modify("other", async () => ({ type: "api_key", key: "fake-other" })),
      second.modify("third", async () => ({ type: "api_key", key: "fake-third" })),
    ]);
    const updated = JSON.parse(await readFile(credentialPath, "utf8"));
    assert.deepEqual(updated.secrets, { smtp_password: "fake-smtp", tri_token: "fake-tri" });
    assert.deepEqual(Object.keys(updated.models).sort(), ["fixture", "other", "third"]);
    await first.delete("fixture");
    const deleted = JSON.parse(await readFile(credentialPath, "utf8"));
    assert.equal(deleted.models.fixture, undefined);
    assert.deepEqual(deleted.secrets, updated.secrets);
  } finally {
    if (previous === undefined) delete process.env.CORAGENT_CREDENTIALS_FILE;
    else process.env.CORAGENT_CREDENTIALS_FILE = previous;
    await rm(root, { recursive: true, force: true });
  }
});

test('request admission failures remain visible without an assistant message',async()=>{
  const {createChatView}=await import('../../../apps/agent/terminal/chat.mjs');
  const [components,themes]=await Promise.all([
    import(pathToFileURL(join(source,'packages/tui/src/index.ts'))),
    import(pathToFileURL(join(source,'packages/coding-agent/src/modes/interactive/theme/theme.ts'))),
  ]);
  themes.initTheme('dark');
  const chat=createChatView({components,theme:themes.theme,markdownTheme:themes.getMarkdownTheme(),requestRender(){}});
  chat.update({entries:[],docs:{},failure:{summary:'Request blocked',detail:'Input budget exceeded'}});
  assert.match(chat.render(100).join('\n'),/Input budget exceeded/);
  chat.update({entries:[],docs:{'pi.live':{run:{}}},failure:null});
  assert.doesNotMatch(chat.render(100).join('\n'),/Input budget exceeded/);
});
