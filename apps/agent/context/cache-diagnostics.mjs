import { createHmac, randomBytes, randomUUID } from "node:crypto";
import { appendFile, rename, stat } from "node:fs/promises";

const BLOCK_BYTES = 1024;
const MAX_LINE = 1024 * 1024;
const number = value => Number.isSafeInteger(value) && value >= 0 ? value : null;
const RESPONSE_HEADERS = ["x-request-id", "request-id", "x-correlation-id", "cf-ray",
  "x-cache", "x-cache-status", "openai-processing-ms", "openai-version"];
const diagnosticToken = value => typeof value === "string" && value.length <= 256
  && /^[A-Za-z0-9][A-Za-z0-9_.:/= -]*$/u.test(value) ? value : null;

// Keep provider-specific numeric usage fields without accepting arbitrary text
// embedded by a proxy. Bounds and filtering are explicit in the diagnostic.
function usageSnapshot(value) {
  let remaining = 256, filtered = false, truncated = false;
  function copy(item, depth) {
    if (--remaining < 0 || depth > 6) { truncated = true; return undefined; }
    if (item === null || typeof item === "boolean" || (typeof item === "number" && Number.isFinite(item))) return item;
    if (!item || typeof item !== "object") { filtered = true; return undefined; }
    if (Array.isArray(item)) {
      if (item.length > 32) truncated = true;
      return item.slice(0, 32).map(child => copy(child, depth + 1) ?? null);
    }
    const result = Object.create(null), entries = Object.entries(item);
    if (entries.length > 64) truncated = true;
    for (const [key, child] of entries.slice(0, 64)) {
      if (!/^[A-Za-z][A-Za-z0-9_]{0,63}$/u.test(key) || ["constructor", "prototype"].includes(key)) { filtered = true; continue; }
      const copied = copy(child, depth + 1);
      if (copied !== undefined) result[key] = copied;
    }
    return result;
  }
  const snapshot = copy(value, 0);
  return { usage_raw: snapshot ?? null, usage_raw_filtered: filtered, usage_raw_truncated: truncated };
}

function responseDiagnostics() {
  return { headers: {}, time_to_headers_ms: null, time_to_first_body_byte_ms: null,
    response_ids: [], models: [], system_fingerprints: [], finish_reasons: [], statuses: [], incomplete_reasons: [],
    terminal_event: false, done_marker: false, error_event: false, oversized_sse_lines: 0,
    metadata_filtered: false, metadata_truncated: false,
    usage_raw: null, usage_raw_filtered: false, usage_raw_truncated: false };
}

function addResponseValue(diagnostic, key, value) {
  if (value === undefined || value === null) return;
  const token = diagnosticToken(value);
  if (token === null) { diagnostic.metadata_filtered = true; return; }
  const values = diagnostic[key];
  if (values.includes(token)) return;
  if (values.length >= 16) { diagnostic.metadata_truncated = true; return; }
  values.push(token);
}

// Missing usage fields are unknown, not a cache miss. Persist only numeric fields.
export function cacheUsage(value, api) {
  if (!value || typeof value !== "object") return null;
  const responses = api === "openai-responses";
  const details = responses ? value.input_tokens_details : value.prompt_tokens_details;
  const input = number(responses ? value.input_tokens : value.prompt_tokens);
  const cached = number(details?.cached_tokens ?? value.prompt_cache_hit_tokens ?? value.cached_tokens);
  const written = number(details?.cache_write_tokens);
  return { input_tokens: input, cache_read_tokens: cached, cache_write_tokens: written,
    output_tokens: number(responses ? value.output_tokens : value.completion_tokens),
    cache_read_status: cached === null ? "not_reported" : "reported",
    cache_hit_fraction: input > 0 && cached !== null && cached <= input ? cached / input : null };
}

/** Bounded local diagnostics, including allowlisted response headers, never model text or credentials. */
export function cacheDiagnosticWriter(file) {
  let tail = Promise.resolve(), pending = 0;
  return {
    write(record) {
      if (pending >= 128) return;
      pending++;
      tail = tail.then(async () => {
        if ((await stat(file).catch(() => null))?.size >= 8 * 1024 * 1024) {
          await rename(file, `${file}.1`);
        }
        await appendFile(file, `${JSON.stringify(record)}\n`, { mode: 0o600 });
      }).catch(() => {}).finally(() => { pending--; });
    },
    async flush() { await tail; },
  };
}

/** Observe the actual HTTP body and SSE usage without changing request contents.
 * Fingerprints use a fresh process-local HMAC key; only comparisons are logged.
 * After restart the first comparison is unknown. Byte prefixes are not tokens.
 */
export function createCacheDiagnostics({ write, captureRequest, now = Date.now }) {
  const secret = randomBytes(32), previous = new Map(), metadata = new WeakMap(), heads = new Map();
  const mac = value => createHmac("sha256", secret).update(value).digest("hex");
  const emit = record => { try { Promise.resolve(write(record)).catch(() => {}); } catch {} };
  function fingerprint(payload, model, purpose, started) {
    const input = payload.messages ?? payload.input;
    if (!Array.isArray(input)) return { available: false };
    const bytes = Buffer.from(JSON.stringify(input));
    const blocks = [];
    for (let offset = 0; offset + BLOCK_BYTES <= bytes.length; offset += BLOCK_BYTES) {
      blocks.push(mac(bytes.subarray(offset, offset + BLOCK_BYTES)));
    }
    const messages = input.map(item => mac(JSON.stringify(item)));
    const tools = mac(JSON.stringify(payload.tools ?? null));
    const instructions = mac(JSON.stringify(payload.instructions ?? null));
    const key = JSON.stringify([model.provider, model.id, model.api, purpose]);
    const prior = previous.get(key);
    let matched = 0, matchedMessages = 0;
    if (prior) {
      while (matched < blocks.length && blocks[matched] === prior.blocks[matched]) matched++;
      while (matchedMessages < messages.length && messages[matchedMessages] === prior.messages[matchedMessages]) matchedMessages++;
    }
    const full = mac(bytes);
    previous.delete(key);
    previous.set(key, { blocks, messages, tools, instructions, full, bytes: bytes.length, started });
    if (previous.size > 8) previous.delete(previous.keys().next().value);
    return { available: true, input_json_bytes: bytes.length, message_count: input.length,
      previous_input_json_bytes: prior?.bytes ?? null,
      previous_request_gap_ms: prior ? started - prior.started : null,
      common_prefix_bytes_lower_bound: prior ? (full === prior.full ? bytes.length : matched * BLOCK_BYTES) : null,
      unchanged_leading_messages: prior ? matchedMessages : null,
      input_identical: prior ? full === prior.full : null,
      tools_unchanged: prior ? tools === prior.tools : null,
      instructions_unchanged: prior ? instructions === prior.instructions : null,
      cache_key_present: typeof payload.prompt_cache_key === "string" };
  }
  function observeBody(response, model, finish, diagnostic, started) {
    if (!response.body || !response.headers.get("content-type")?.includes("text/event-stream")) {
      finish(null, "unobserved_response");
      return response;
    }
    let buffer = "", oversized = false, usage = null;
    const decoder = new TextDecoder();
    function line(text) {
      if (!text.startsWith("data:")) return;
      if (text.slice(5).trim() === "[DONE]") { diagnostic.done_marker = true; return; }
      try {
        const value = JSON.parse(text.slice(5));
        const responseValue = model.api === "openai-responses" ? value.response : value;
        addResponseValue(diagnostic, "response_ids", responseValue?.id);
        addResponseValue(diagnostic, "models", responseValue?.model);
        addResponseValue(diagnostic, "system_fingerprints", responseValue?.system_fingerprint);
        if (model.api === "openai-responses") {
          addResponseValue(diagnostic, "statuses", responseValue?.status);
          addResponseValue(diagnostic, "incomplete_reasons", responseValue?.incomplete_details?.reason);
          if (["response.completed", "response.done", "response.incomplete", "response.failed"].includes(value.type)) diagnostic.terminal_event = true;
          if (value.type === "response.failed" || responseValue?.error) diagnostic.error_event = true;
        }
        for (const choice of Array.isArray(value.choices) ? value.choices : []) {
          if (choice?.finish_reason !== null && choice?.finish_reason !== undefined) {
            diagnostic.terminal_event = true;
            addResponseValue(diagnostic, "finish_reasons", choice.finish_reason);
          }
        }
        if (value.type === "error" || value.error) diagnostic.error_event = true;
        const candidate = value.usage ?? value.response?.usage;
        if (candidate && typeof candidate === "object" && !Array.isArray(candidate)) {
          usage = cacheUsage(candidate, model.api);
          Object.assign(diagnostic, usageSnapshot(candidate));
        }
      } catch { /* Non-JSON SSE records and model content are not diagnostics. */ }
    }
    // Pass through original bytes. Bound buffering even for huge text/image events.
    function inspect(chunk) {
      for (const part of decoder.decode(chunk, { stream: true }).split(/(\n)/u)) {
        if (part === "\n") {
          if (!oversized) line(buffer);
          buffer = ""; oversized = false;
        } else if (!oversized) {
          if (buffer.length + part.length > MAX_LINE) { buffer = ""; oversized = true; diagnostic.oversized_sse_lines++; }
          else buffer += part;
        }
      }
    }
    const reader = response.body.getReader();
    const body = new ReadableStream({
      async pull(controller) {
        try {
          const { done, value } = await reader.read();
          if (done) {
            if (!oversized) line(buffer + decoder.decode());
            finish(usage, "stream_complete"); controller.close(); reader.releaseLock();
          } else {
            if (value.byteLength > 0 && diagnostic.time_to_first_body_byte_ms === null) diagnostic.time_to_first_body_byte_ms = Math.max(0, now() - started);
            try { inspect(value); } catch { /* Observation must not interrupt inference. */ }
            controller.enqueue(value);
          }
        } catch (error) { finish(usage, "stream_error"); controller.error(error); }
      },
      async cancel(reason) { finish(usage, "stream_cancelled"); await reader.cancel(reason); },
    });
    return new Response(body, { status: response.status, statusText: response.statusText, headers: response.headers });
  }
  return {
    context(generationId, headId) {
      heads.set(String(generationId), headId ?? null);
      if (heads.size > 128) heads.delete(heads.keys().next().value);
    },
    tag(messages, value) {
      if (messages?.length) metadata.set(messages.at(-1), { ...value, context_head_id: heads.get(value.generation_id) ?? null });
      heads.delete(value.generation_id);
    },
    wrap(models) {
      function stream(model, context, options = {}, purpose = "generation") {
        if (!["openai-completions", "openai-responses"].includes(model.api)) return models.streamSimple(model, context, options);
        const info = metadata.get(context.messages?.at(-1));
        const base = { schema_version: "coragent-cache-diagnostic/2", request_id: randomUUID(), purpose,
          generation_id: info?.generation_id ?? null, sources: info?.sources ?? [],
          context_head_id: info?.context_head_id ?? null,
          provider: model.provider, model: model.id, api: model.api };
        let attempt = 0;
        const fetch = options.fetch ?? globalThis.fetch;
        return models.streamSimple(model, context, { ...options, async fetch(url, init) {
          const started = now(), attemptId = ++attempt;
          const diagnostic = responseDiagnostics();
          let snapshot = { available: false }, finished = false, status = null, capture;
          try {
            if (typeof init?.body === "string") snapshot = fingerprint(JSON.parse(init.body), model, purpose, started);
          } catch { /* Unsupported payloads still execute normally. */ }
          const finish = (usage, outcome) => {
            if (finished) return;
            finished = true;
            emit({ ...base, attempt: attemptId, phase: "response", started_at_ms: started,
              elapsed_ms: now() - started, http_status: status, outcome, prefix: snapshot,
              usage, cache_read_status: usage?.cache_read_status ?? "not_reported",
              response_diagnostics: diagnostic,
              ...(capture ? { request_capture: capture } : {}) });
          };
          const requestRecord = { ...base, attempt: attemptId, phase: "request", started_at_ms: started, prefix: snapshot };
          if (captureRequest) {
            try { capture = await captureRequest({ url, init, record: requestRecord }); }
            catch { capture = { status: "error", code: "CAPTURE_FAILED" }; }
          }
          emit({ ...requestRecord, ...(capture ? { request_capture: capture } : {}) });
          let response;
          try { response = await fetch(url, init); }
          catch (error) { finish(null, "transport_error"); throw error; }
          status = response.status;
          try {
            diagnostic.time_to_headers_ms = Math.max(0, now() - started);
            for (const name of RESPONSE_HEADERS) {
              const value = response.headers.get(name);
              if (value === null) continue;
              const token = diagnosticToken(value);
              if (token !== null) diagnostic.headers[name] = token;
              else diagnostic.metadata_filtered = true;
            }
            return observeBody(response, model, finish, diagnostic, started);
          }
          catch { finish(null, "observation_unavailable"); return response; }
        } });
      }
      return new Proxy(models, { get(target, key) {
        if (key === "streamSimple") return (model, context, options) => stream(model, context, options);
        if (key === "completeSimple") return (model, context, options) => stream(model, context, options, "auxiliary").result();
        const value = Reflect.get(target, key, target);
        return typeof value === "function" ? value.bind(target) : value;
      } });
    },
  };
}
