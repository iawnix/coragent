import { loadPi } from "../../runtime/source.mjs";
import { parseSlashCommand, slashCompletions, SLASH_COMMAND_DEFINITIONS } from "../../tools/commands.mjs";
import { CLIENT_QUERIES_SERVICE_ID } from "../../runtime/services/queries.mjs";
import { createStatusPresentation } from "../status/presentation.mjs";
import { createDocumentView } from "../renderers/document.mjs";
import { createCommandPresentation } from "./panel.mjs";
import { formatMonitor } from "./monitor.mjs";
import { formatFields } from '../renderers/fields.mjs';

/** Presentation-only commands; all scientific reads execute in the worker. */
export async function createCoRAgentNativeClientFacet({ sourceRoot, session } = {}) {
  if (typeof sourceRoot !== "string" || !sourceRoot) throw new TypeError("sourceRoot is required");

  const [{ defineFacet, defineService }, { SlashCommands }, { PresentationUI }, components, { Transcript }, themeModule, { BACKGROUND_CONTEXT, withAbortSignal }] = await Promise.all([
    loadPi("chord", sourceRoot),
    loadPi("slashCommands", sourceRoot),
    loadPi("presentationUI", sourceRoot),
    loadPi("tui", sourceRoot),
    loadPi("transcript", sourceRoot),
    loadPi("theme", sourceRoot),
    loadPi("context", sourceRoot),
  ]);
  const queriesService = defineService(CLIENT_QUERIES_SERVICE_ID);
  return defineFacet({
    id: "@coragent/native-client-commands",
    setup(env) {
      const commands = env.use(SlashCommands);
      const ui = env.use(PresentationUI);
      const queries = env.use(queriesService);
      const transcript = env.use(Transcript);
      env.onActivate(() => {
        const theme = new Proxy({}, { get: (_, key) => {
          const value = themeModule.theme[key];
          return typeof value === 'function' ? value.bind(themeModule.theme) : value;
        } });
        const document = options => createDocumentView({ ...components, wrapText: components.wrapTextWithAnsi, theme, ...options });
        ui.setCommandPresentation(createCommandPresentation({ ...components, theme, scope: 'Session', createDocument: document }));
        const status = createStatusPresentation({ session, theme, ...components, ring: process.env.TERM !== "dumb" && process.env.CORAGENT_TUI_RING !== "0" });
        const lifetime = new AbortController();
        const queryContext = withAbortSignal(lifetime.signal, BACKGROUND_CONTEXT);
        let stopped = false;
        const redraw = () => { if (!stopped) { ui.setFooter(status.footer); ui.setActivity(status.activity); } };
        const telemetryRefresh = createRefreshLoop({ signal: session.signal,
          read: () => queries.telemetry(queryContext),
          apply(value) {
            if (value.session_id !== session.sessionId || value.workspace_id !== session.workspaceId) throw new Error('Context query returned a different session or workspace');
            status.update({telemetry:value.result, telemetryError:null}); redraw();
          },
          onError(error) { status.update({telemetryError:error.message || String(error)}); redraw(); },
        });
        const monitorRefresh = createRefreshLoop({ signal: session.signal,
          read: () => session.monitor(),
          apply(value) {
            if (value.session_id !== session.sessionId || value.workspace_id !== session.workspaceId) throw new Error('Monitor query returned a different session or workspace');
            status.update({monitor:value, monitorError:null}); redraw();
          },
          onError(error) { status.update({monitorError:error.message || String(error)}); redraw(); },
        });
        let signature;
        env.own(transcript.state.subscribe(view => {
          status.update({view});
          const next = JSON.stringify([view.entries.at(-1)?.id, view.docs["pi.agent"], view.entries[0]?.id]);
          if (next !== signature) { signature = next; telemetryRefresh.schedule(); monitorRefresh.schedule(); }
          // Pi already repaints transcript changes; the components read current state at render time.
        }));
        redraw(); void telemetryRefresh.refresh(); void monitorRefresh.refresh();
        if (session.subscribeMonitor) env.own(session.subscribeMonitor(() => { monitorRefresh.schedule(); }, () => {
          // A notification connection can drop while the request connection is
          // still healthy. Re-read the authoritative snapshot before showing an
          // unavailable state; a transport blip must not overwrite a fresh view.
          monitorRefresh.schedule();
        }));
        env.own(() => { stopped = true; lifetime.abort(); telemetryRefresh.stop(); monitorRefresh.stop(); ui.setFooter(undefined); ui.setActivity(undefined); ui.setCommandPresentation(undefined); });
        const show = (title, body, context, command, scope, mode) => ui.showDocument(document({ title, body, command, scope, mode }), context);
        for (const command of createTerminalCommands({ ui, queries, session, show, usage: () => status.usageDetails(), monitor: (value) => {
          if (value) status.update({monitor:value, monitorError:null});
          return status.monitorDetails();
        } })) {
          env.own(commands.replace(command));
        }
      });
    },
  });
}

/** One in-flight read per source; bursts request only one follow-up refresh. */
export function createRefreshLoop({ read, apply, onError, signal, intervalMs = 5000, coalesceMs = 250 }) {
  let stopped = false, running = false, dirty = false, timer, scheduledUpdate = false;
  const active = () => !stopped && !signal?.aborted;
  const scheduleAfter = (delay, update) => {
    clearTimeout(timer);
    scheduledUpdate = update;
    timer = setTimeout(() => { timer = undefined; scheduledUpdate = false; void refresh(); }, delay);
    timer.unref?.();
  };
  async function refresh() {
    if (!active()) return;
    if (running) { dirty = true; return; }
    clearTimeout(timer); timer = undefined; scheduledUpdate = false;
    running = true; dirty = false;
    try {
      const value = await read();
      if (active()) apply(value);
    } catch (error) {
      if (active()) onError(error);
    } finally {
      running = false;
      if (active()) scheduleAfter(dirty ? coalesceMs : intervalMs, dirty);
    }
  }
  return {
    refresh,
    schedule() {
      if (!active()) return;
      if (running) { dirty = true; return; }
      if (!scheduledUpdate) scheduleAfter(coalesceMs, true);
    },
    stop() { stopped = true; clearTimeout(timer); },
  };
}

export function createTerminalCommands({ ui, queries, session, show, usage, monitor }) {
  return Object.values(SLASH_COMMAND_DEFINITIONS).map((definition) => ({
    name: definition.name,
    description: definition.description,
    argumentHint: definition.name === "monitor" ? "[command]" : definition.usage.replace(`/${definition.name}`, "").trim(),
    getArgumentCompletions(prefix) { return slashCompletions(definition.name, prefix) || []; },
    validate(args) {
      try { parseSlashCommand(definition.name, args); }
      catch (error) { return error.message; }
    },
    async run(args, context) {
      try {
        const invocation = parseSlashCommand(definition.name, args);
        if (definition.name === "quit") { session.quit(); return; }
        if (definition.name === "usage") {
          await show("Session usage", usage, context, 'usage', 'Session', 'panel');
          return;
        }
        if (definition.name === "monitor") {
          const { method, ...params } = invocation.params;
          const response = await session.monitor(method, params);
          if (session.signal?.aborted) return;
          if (method === "monitor/overview" && monitor) monitor(response);
          const body = method === "monitor/overview" && monitor ? monitor : formatMonitor(method, response, params);
          await show("Monitor", body, context, `monitor${args ? ` ${args}` : ''}`, 'Session', 'panel');
          return;
        }
        if (definition.name === "resume") {
          let id = invocation.params.sessionId;
          if (!id) {
            const sessions = await session.list();
            if (!sessions.length) { ui.showStatus("No writable sessions in this workspace.", context); return; }
            id = await ui.select("Resume session", sessions.map((item) => ({
              value: item.session_id,
              label: item.session_id,
              description: `${item.updated_at || item.created_at || ""}${item.is_streaming ? " · running" : ""}`,
            })), session.sessionId, context);
          }
          if (id === session.sessionId) ui.showStatus("Already in this session. Research State is shared by sessions in this workspace.", context);
          else if (id) await session.resume(id);
          return;
        }
        const response = definition.name === "research"
          ? await queries.research(args, context)
          : await queries.systemPrompt(context);
        if (session.signal?.aborted) return;
        if (response.session_id !== session.sessionId) throw new Error("Query returned a different session");
        if (session.workspaceId && response.workspace_id !== session.workspaceId) throw new Error("Query returned a different workspace");
        if (response.error) {
          const { message, code, details = {} } = response.error;
          const fields = [
            ['Code', code], ['Command', details.command], ['Request', details.request_id],
            ['Elapsed', Number.isFinite(details.elapsed_ms) ? `${details.elapsed_ms} ms` : undefined],
          ].filter(([, value]) => value !== undefined);
          throw new Error([message, ...fields.map(([label, value]) => `${label}: ${value}`)].join('\n'));
        }
        const title = definition.name === "sys-prompt" ? "System prompt" : "Research state";
        const body = definition.name === "sys-prompt" ? formatPrompt(response.result) : formatResearch(response.result);
        await show(title, body, context, `${definition.name}${args ? ` ${args}` : ''}`, definition.name === 'research' ? 'Workspace' : 'Session', definition.name === 'sys-prompt' ? 'page' : 'auto');
      } catch (error) {
        if (!session.signal?.aborted) ui.showStatus(error instanceof Error ? error.message : String(error), context, 'error');
      }
    },
  }));
}

function formatPrompt(manifest) {
  const sources = (manifest.contributors || []).map((item) => `${item.origin}: ${item.source}`).join("\n");
  return `${manifest.effective}\n\nSources\n${sources}\n\nSHA256: ${manifest.sha256}${manifest.limitations?.length ? `\n\nLimitations\n${manifest.limitations.join("\n")}` : ""}`;
}

function formatResearch(value) {
  if (value?.schema_version !== 'research-summary/1') return formatFields(value);
  const sections = [
    ['Research overview', { workspace: value.workspace_id, revision: value.revision, state: value.lifecycle_state, progress: value.progress }],
    ['Current focus', value.focus], ['Phases and goals', value.phases], ['Claims', value.claims],
    ['Research nodes', value.nodes], ['Findings', value.findings], ['Gates', value.gates],
  ];
  return sections.map(([title, content]) => `${title}\n${'─'.repeat(title.length)}\n${formatFields(content)}`).join('\n\n')
    + '\n\nFull item: /research detail <kind> <id>';
}
