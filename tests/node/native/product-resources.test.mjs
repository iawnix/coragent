import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { cp, mkdir, mkdtemp, readFile, writeFile, symlink, rm } from "node:fs/promises";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";
import { TEST_ROOT } from "./test-environment.mjs";
import { loadProductSkills } from "../../../apps/agent/resources/skills.mjs";
import { createSystemPromptManifest } from "../../../apps/agent/pi/prompt.mjs";

test("installed core works alone and chemical uses the same discovery without duplicate Skills", async t => {
  const source = fileURLToPath(new URL("../../../", import.meta.url));
  for (const groups of [["core"], ["core", "chemical"]]) {
    const root = await mkdtemp(join(TEST_ROOT, "skill-groups-"));
    t.after(() => rm(root, { recursive: true, force: true }));
    await mkdir(join(root, "skills"));
    await mkdir(join(root, "config"));
    for (const group of groups) await cp(join(source, "skills", group), join(root, "skills", group), { recursive: true });
    await cp(join(source, "prompts"), join(root, "prompts"), { recursive: true });
    const manifest = JSON.parse(await readFile(join(source, "package.json"), "utf8"));
    manifest.pi.skills = groups.map(group => `./skills/${group}`);
    await writeFile(join(root, "package.json"), JSON.stringify(manifest));
    const inventory = JSON.parse(await readFile(join(source, "config/resources.json"), "utf8"));
    inventory.files = Object.fromEntries(Object.entries(inventory.files).filter(([path]) =>
      path.startsWith("prompts/") || groups.some(group => path.startsWith(`skills/${group}/`))));
    await writeFile(join(root, "config/resources.json"), JSON.stringify(inventory));
    const loaded = await loadProductSkills({ packageRoot: root });
    const names = loaded.skills.map(skill => skill.name);
    assert.equal(new Set(names).size, names.length);
    for (const name of ["research-workflow", "research-memory", "batch-schedulers", "tri-operations", "email"]) {
      assert.ok(names.includes(name));
    }
    assert.equal(names.includes("gaussian"), groups.includes("chemical"));
    assert.equal(names.includes("chemical-report"), groups.includes("chemical"));
    assert.equal(names.includes("report"), false);
    assert.equal(names.includes("_shared"), false);
    const prompt = createSystemPromptManifest({ native: { source: "product", text: await readFile(join(root, "prompts/coragent.md"), "utf8") },
      skills: { source: root, items: loaded.skills } });
    for (const skill of loaded.skills) assert.ok(prompt.effective.includes(skill.filePath));
    const workflowBody = await readFile(join(root, "skills/core/research-workflow/SKILL.md"), "utf8");
    assert.equal(prompt.effective.includes(workflowBody), false);
  }
});

async function fixture(t) {
  const root = await mkdtemp(join(TEST_ROOT, "r-"));
  t.after(() => rm(root, { recursive: true, force: true }));
  await mkdir(join(root, "skills", "demo"), { recursive: true });
  await mkdir(join(root, "prompts")); await mkdir(join(root, "config"));
  const files = {
    "skills/demo/SKILL.md": "---\nname: demo\ndescription: Test a managed resource.\n---\nRead references relative to this directory.\n",
    "skills/demo/example.txt": "resource\n",
    "prompts/coragent.md": "Product principles.\n",
  };
  for (const [name, content] of Object.entries(files)) await writeFile(join(root, name), content);
  await writeFile(join(root, "package.json"), JSON.stringify({ pi: { skills: ["./skills"] } }));
  const inventory = { schema_version: "coragent-resources/1", files: Object.fromEntries(Object.entries(files)
    .map(([name, content]) => [name, `sha256:${createHash("sha256").update(content).digest("hex")}`])) };
  await writeFile(join(root, "config/resources.json"), JSON.stringify(inventory));
  return root;
}

test("native Pi discovers managed Skills without mandatory product skill names", async t => {
  const root = await fixture(t);
  const loaded = await loadProductSkills({ packageRoot: root });
  assert.deepEqual(loaded.skills.map(skill => skill.name), ["demo"]);
  assert.equal(loaded.skills[0].filePath, join(root, "skills/demo/SKILL.md"));
  const prompt = createSystemPromptManifest({ native: { source: "product", text: "principles" },
    skills: { source: root, items: loaded.skills } });
  assert.match(prompt.effective, /<available_skills>/);
  assert.ok(prompt.effective.includes(join(root, "skills/demo/SKILL.md")));
  assert.doesNotMatch(prompt.effective, /skill:demo|orchestration/);
});

test("managed Skill modifications and unlisted resources fail integrity validation", async t => {
  const root = await fixture(t);
  await writeFile(join(root, "skills/demo/example.txt"), "changed");
  await assert.rejects(loadProductSkills({ packageRoot: root }), /digest mismatch/);
  await writeFile(join(root, "skills/demo/example.txt"), "resource\n");
  await writeFile(join(root, "skills/demo/unlisted.py"), "print('not allowed')");
  await assert.rejects(loadProductSkills({ packageRoot: root }), /digest mismatch/);
});

test("managed Skill roots cannot escape or redirect through symlinks", async t => {
  const root = await fixture(t);
  await symlink(join(root, "prompts/coragent.md"), join(root, "skills/demo/linked.md"));
  await assert.rejects(loadProductSkills({ packageRoot: root }), /symlink/);
  await rm(join(root, "skills/demo/linked.md"));
  await writeFile(join(root, "package.json"), JSON.stringify({ pi: { skills: ["../outside"] } }));
  await assert.rejects(loadProductSkills({ packageRoot: root }), /escapes package/);
});

test("Skills remain independent of scientific execution catalog discovery", async t => {
  const root = await fixture(t);
  const manifest = JSON.parse(await readFile(join(root, "package.json")));
  manifest.coragent = { execution: ["skills/missing/execution.json"] };
  await writeFile(join(root, "package.json"), JSON.stringify(manifest));
  assert.equal((await loadProductSkills({ packageRoot: root })).skills.length, 1);
});

test("the permanent system prompt is required even if omitted from the inventory", async t => {
  const root = await fixture(t);
  await rm(join(root, "prompts/coragent.md"));
  const path = join(root, "config/resources.json");
  const inventory = JSON.parse(await readFile(path));
  delete inventory.files["prompts/coragent.md"];
  await writeFile(path, JSON.stringify(inventory));
  await assert.rejects(loadProductSkills({ packageRoot: root }), /system prompt is missing/);
});
