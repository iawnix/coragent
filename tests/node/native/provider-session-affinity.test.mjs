import assert from 'node:assert/strict';
import test from 'node:test';
import { join } from 'node:path';
import { pathToFileURL } from 'node:url';
import { pinnedPiSource } from './test-environment.mjs';

const { stream } = await import(pathToFileURL(join(pinnedPiSource(), 'packages/ai/src/api/openai-completions.ts')));

const baseModel = {
  id: 'fixture', provider: 'fixture', api: 'openai-completions',
  baseUrl: 'https://api.ecnu.space/v1', reasoning: false, input: ['text'],
  contextWindow: 1_000_000, maxTokens: 512,
  cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
};

function response() {
  const body = [
    `data: ${JSON.stringify({ choices: [{ index: 0, delta: { role: 'assistant', content: 'ok' }, finish_reason: null }] })}\n\n`,
    `data: ${JSON.stringify({ choices: [{ index: 0, delta: {}, finish_reason: 'stop' }], usage: { prompt_tokens: 1, completion_tokens: 1 } })}\n\n`,
    'data: [DONE]\n\n',
  ].join('');
  return new Response(body, { headers: { 'content-type': 'text/event-stream' } });
}

async function capture(model) {
  let request;
  const result = await stream(model, { messages: [{ role: 'user', content: 'hello', timestamp: 0 }] }, {
    apiKey: 'fixture-only', sessionId: 'coragent-session', maxTokens: 32, maxRetries: 0,
    fetch: async (_url, init) => { request = init; return response(); },
  }).result();
  assert.equal(result.stopReason, 'stop');
  return request;
}

test('custom OpenAI gateways receive stable CoRAgent session affinity headers when enabled', async () => {
  const request = await capture({ ...baseModel, compat: { sendSessionAffinityHeaders: true, sessionAffinityFormat: 'openai' } });
  const headers = Object.fromEntries(new Headers(request.headers));
  assert.equal(headers.session_id, 'coragent-session');
  assert.equal(headers['x-client-request-id'], 'coragent-session');
  assert.equal(headers['x-session-affinity'], 'coragent-session');
});

test('custom OpenAI gateways keep affinity opt-in', async () => {
  const request = await capture(baseModel);
  const headers = Object.fromEntries(new Headers(request.headers));
  assert.equal(headers.session_id, undefined);
  assert.equal(headers['x-client-request-id'], undefined);
  assert.equal(headers['x-session-affinity'], undefined);
});
