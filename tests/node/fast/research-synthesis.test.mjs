import assert from "node:assert/strict";
import test from "node:test";
import { createResearchSynthesis } from "../../../apps/agent/context/synthesis.mjs";

const review = {
  schema_version: "research-brief/1", projection_status: "complete", state_digest: "sha256:state",
  brief_digest: "sha256:review", status: "attention", source_refs: ["node_1", "job_1"],
  coverage: {}, findings: [], contradictions: [{ ref: "job_1", summary: "failed" }],
  uncertainties: [], limitations: [], follow_up: [],
};

test("research reviewer binds model synthesis to the deterministic brief", async () => {
  let calls = 0;
  const reviewer = createResearchSynthesis({ getModel: () => ({ provider: "fixture", id: "reviewer" }), modelRuntime: {
    completeSimple: async (_model, request) => {
      calls += 1;
      assert.match(request.systemPrompt, /Do not invent facts/);
      return { content: [{ type: "text", text: JSON.stringify({
        status: "attention", summary: "Inspect the failed Job before interpretation.",
        key_findings: [{ ref: "job_1", statement: "The Job is recorded as failed." }],
        contradictions: [], uncertainties: [], next_actions: [{ action: "inspect", ref: "job_1" }],
        source_refs: ["job_1"],
      }) }] };
    },
  }});
  const first = await reviewer(review);
  const second = await reviewer(review);
  assert.deepEqual(first, second);
  assert.equal(calls, 1);
  assert.equal(first.source_state_digest, review.state_digest);
  assert.deepEqual(first.source_refs, ["job_1"]);
});

test("research reviewer drops hallucinated references and malformed actions", async () => {
  const reviewer = createResearchSynthesis({ getModel: () => ({ provider: "fixture", id: "reviewer" }), modelRuntime: {
    completeSimple: async () => ({ content: [{ type: "text", text: JSON.stringify({
      status: "uncertain", summary: "Needs inspection", key_findings: [{ ref: "made_up", statement: "No" }],
      contradictions: [], uncertainties: [], next_actions: [{ action: "write", ref: "made_up" }], source_refs: ["made_up"],
    }) }] }),
  }});
  const result = await reviewer({ ...review, brief_digest: "sha256:other" });
  assert.deepEqual(result.key_findings, []);
  assert.deepEqual(result.next_actions, []);
  assert.deepEqual(result.source_refs, []);
});

test("synthesis resolves the current model and keeps different scoped briefs separate", async () => {
  let model = {provider:"fixture",id:"first"};
  const calls = [];
  const summarize = createResearchSynthesis({getModel:()=>model, modelRuntime:{
    async completeSimple(selected) {
      calls.push(selected.id);
      return {content:[{type:"text",text:JSON.stringify({status:"oriented",summary:"Recorded facts",source_refs:[]})}]};
    },
  }});
  await summarize(review);
  await summarize(review);
  model = {provider:"fixture",id:"second"};
  await summarize(review);
  await summarize({...review,brief_digest:"sha256:other-scope"});
  await summarize({...review,projection_status:"incomplete"});
  assert.deepEqual(calls,["first","second","second"]);
});
