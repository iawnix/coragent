import { loadPi } from "./source.mjs";
import { createContextManager, contextPolicy, contextInputBudget } from "../context/manager.mjs";
import { createResearchReviewer } from "../context/reviewer.mjs";
import { recordUserSources } from "../tools/user-sources.mjs";
import { createInputAdmission, createInputService, bindUserInputConversation, INPUT_ADMISSION_SERVICE_ID } from "../host/admission/input.mjs";
import { createMonitorAdmission, MONITOR_ADMISSION_SERVICE_ID } from "../host/admission/monitor.mjs";
import { createSessionAdmission, SESSION_ADMISSION_SERVICE_ID } from "../host/admission/session.mjs";
import { createTaskController } from "../tasks/controller.mjs";
import { createTaskTools } from "../tasks/tools.mjs";
import { createMonitorService, recordRun, MONITOR_SERVICE_ID } from "../tasks/service.mjs";
import { wakeMessage } from "../host/monitor/worker.mjs";
import { CLIENT_QUERIES_SERVICE_ID, createClientQueries } from "./services/queries.mjs";
import { dirname, join } from "node:path";
import { readFile } from "node:fs/promises";
import { createStaticFacetLoader, defineFacet, defineService } from "@earendil-works/chord";
import {
  Harness, createRegistry, defineExtension, hook, section,
  GenerationTask, CompactionTask, ToolTask, LiveDoc, InboxDoc,
} from "@earendil-works/pi-durable";
import { createCodingTools } from "./coding-tools.mjs";
import { loadProductSkills } from "../resources/skills.mjs";
import { createCoreTools } from "../tools/registry.mjs";
import { openNodeSqliteStorage } from "@earendil-works/pi-durable/storage/sqlite/node";
import { TODO_CONTEXT as PI_TODO_CONTEXT } from "@earendil-works/chord/context";
import { createSystemPromptManifest } from "./prompt.mjs";
import { createPackageSourceReadGuard } from "./policy.mjs";
import { wrapToolForHarness } from "../tools/envelope.mjs";
import { createToolExecutionContext } from "../tools/context.mjs";
import { create_python_runtime_bridge } from "../bridge/client.mjs";
import { RESEARCH_MEMORY_WRITE_PRINCIPAL } from "../bridge/ports.mjs";
import { createTransactionCoordinator } from "../bridge/transactions.mjs";


const sourceRoot = process.env.CORAGENT_PI_RUNTIME_ROOT;
if (!sourceRoot) throw new Error("CoRAgent worker requires CORAGENT_PI_RUNTIME_ROOT");
const { estimateContextTokens } = await loadPi("estimate", sourceRoot);
const setupModule = await loadPi("setup", sourceRoot);
const { createHarnessSettings, configureHarnessHttp, ExecutionEnvs, findInitialAgentModel } = setupModule;
// Pinned Pi transaction primitive keeps Monitor admission atomic with native input.
const { admitSubmission } = await loadPi("submissions", sourceRoot);
const CoRAgentMonitorAdmission = defineService(MONITOR_ADMISSION_SERVICE_ID);
const CoRAgentInputAdmission = defineService(INPUT_ADMISSION_SERVICE_ID);
const CoRAgentSessionAdmission = defineService(SESSION_ADMISSION_SERVICE_ID);
const CoRAgentClientQueries = defineService(CLIENT_QUERIES_SERVICE_ID);
const CoRAgentMonitor = defineService(MONITOR_SERVICE_ID);

export async function createCoRAgentHarness(databasePath, options) {
  const producerToken = process.env.CORAGENT_INPUT_PRODUCER_TOKEN;
  delete process.env.CORAGENT_INPUT_PRODUCER_TOKEN;
  if (!producerToken) throw new Error("Worker requires supervised input producer identity");
  const { cwd, workspaceId, id: sessionId } = options.metadata;
  const modelRuntime = await (await loadPi("modelRuntime", sourceRoot)).ModelRuntime.create();
  const { SettingsManager } = await loadPi("settings", sourceRoot);
  const settingsManager = SettingsManager.create(cwd);
  configureHarnessHttp(settingsManager);
  const executionEnvs = new ExecutionEnvs(cwd);
  let commandBridge, harness, taskController;
  try {
    const resolved = await findInitialAgentModel(
      settingsManager,
      modelRuntime,
      options.model === undefined ? undefined : { provider: options.provider, model: options.model },
    );
    const loadedSkills = await loadProductSkills();
    commandBridge = create_python_runtime_bridge({ workspace_root: cwd, workspace_id: workspaceId });
    const transactionCoordinator = createTransactionCoordinator({ bridge: commandBridge, workspaceRoot: cwd });
    const businessTools = createCoreTools({ commandBridge, getTaskBinding: context => taskController.binding(context) });
    const promptManifest = createSystemPromptManifest({
      native: { source: join(loadedSkills.packageRoot, "prompts/coragent.md"), text: `Working directory: ${cwd}\n\n${await readFile(join(loadedSkills.packageRoot, "prompts/coragent.md"), "utf8")}` },
      skills: { source: loadedSkills.skillsRoot, items: loadedSkills.skills },

    });
    const harnessSettings = contextPolicy(createHarnessSettings(settingsManager));
    const reviewerModel = resolved.model ? modelRuntime.getModel(resolved.model.provider, resolved.model.modelId) : null;
    const synthesizeReview = createResearchReviewer({ modelRuntime, model: reviewerModel });
    const contextManager = createContextManager({ bridge: commandBridge, coordinator: transactionCoordinator,
      synthesizeReview,
      sessionId, estimateContextTokens, getCompactionPolicy: () => harnessSettings.compaction,
    });
    const packageReadGuard = createPackageSourceReadGuard({ packageRoot: loadedSkills.packageRoot, cwd,
      publicKnowledgeRoots: loadedSkills.skills.map(skill => dirname(skill.filePath)),
      publicResourceFiles: loadedSkills.resourceFiles,
    });
    const toolContext = createToolExecutionContext({
      workspace_root: cwd, workspace_id: workspaceId, session_id: sessionId, operation_id: null,
      replay_mode: "normal", principal: RESEARCH_MEMORY_WRITE_PRINCIPAL,
      allowed_authorities: ["host_read", "kernel_read", "kernel_write", "runtime_read", "execution_runtime", "research_write", "artifact_runtime", "external_side_effect", "task_control"],
      allowed_effects: ["read", "research_write", "result_collection", "artifact_write", "execution_control", "external_write", "task_write"],
    });
    const durableTools = [
      ...businessTools,
      ...createTaskTools(() => taskController),
    ].map((tool) => wrapToolForHarness(tool, {
      toolContext,
      invocation: api => ({ workspaceRoot: cwd, sessionId,
        operationId: String(api.taskId) }),
    }));
    let monitorAdmission, inputAdmission;
    const recordedUserSources = new Set();
    const registry = createRegistry();
    registry.install(defineExtension({ name: "coding-tools", tools:
      await createCodingTools(cwd),
    }));
    registry.install(defineExtension({ name: "coragent-tools", tools: durableTools }));
    registry.install(defineExtension({
      name: "coragent-prompt",
      sections: [section("research_agent_system_prompt", () => promptManifest.effective, { tag: false })],
      hooks: [
        hook(GenerationTask, {
          prepareContext: async (view, api, context) => {
            const live = await api.snapshot(LiveDoc, api.conversationId, context);
            const task = await taskController.current(context);
            await recordUserSources({ harness, admission: inputAdmission, monitorAdmission, taskController, api, context,
              inputIds: live?.run?.inputs, bridge: commandBridge, sessionId, recordedIds: recordedUserSources });
            const inputIds = live?.run?.inputs || [];
            const origins = await Promise.all(inputIds.map(async id => {
              const record = await (await harness.submission(id, context)).status(context);
              return inputAdmission.origin(record, context);
            }));
            const monitorEvidence = origins.some(origin => origin?.producer === "monitor");
            const taskEvidence = origins.some(origin => origin?.producer === "task_controller")
              && task?.progress?.review_pending === true;
            // Internal monitor/task continuations are the coalescing boundary for
            // a new Review. Ordinary tool turns reuse the durable context anchor.
            const refresh = (monitorEvidence || taskEvidence) && (!task || task.state === "active");
            const prepared = await contextManager.prepare(view, api, context, { task,
              input_ids: inputIds, refresh_research: refresh,
              review_trigger: refresh ? "new_evidence" : "context_refresh" });
            // Review persistence is a Monitor pointer. A durable pointer write
            // must never turn an otherwise usable model context into a failed
            // generation; the canonical Review remains readable from research.
            if (prepared?.data) {
              try { await taskController.recordResearchReview(prepared.data, context, task?.user_task_id ?? null); }
              catch { /* Monitor can report the last durable pointer; context stays usable. */ }
            }
            return prepared;
          },
          afterTools: async (_assistant, results, api, context) => {
            await taskController.observeToolResults(await Promise.all(results.map(id => api.entry(id, context))), context);
          },
          beforeRequest: (request, api, context) => {
            return (async () => {
              const live = await api.snapshot(LiveDoc, api.conversationId, context);
              await recordUserSources({ harness, admission: inputAdmission, monitorAdmission, taskController, api, context, inputIds: live?.run?.inputs,
                bridge: commandBridge, sessionId, recordedIds: recordedUserSources });
              const task = await taskController.current(context);
              await recordRun({ conversation, api, inputIds: live?.run?.inputs || [], userTaskId: task?.user_task_id ?? null, context });
              const actualUserIds = [];
              for (const id of live?.run?.inputs || []) {
                const record = await (await harness.submission(id, context)).status(context);
                if ((await inputAdmission.origin(record, context))?.producer === "user") actualUserIds.push(String(id));
              }
              const admitted = await contextManager.admit(request, String(api.taskId), {
                task, actual_user_submission_ids: actualUserIds,
                automatic_continuation_enabled: taskController.health().automatic_continuation_enabled,
              });
              // Recheck after external projection IO, immediately before Pi sends the request.
              for (const id of live?.run?.inputs || []) {
                const record = await (await harness.submission(id, context)).status(context);
                const origin = await inputAdmission.origin(record, context);
                if (origin.producer !== "user") await taskController.assertExecutionAllowed(record, origin, context);
              }
              return admitted;
            })();
          },
        }),
        hook(CompactionTask, { prepareSummary: input => contextManager.prepareSummary(input) }),
        hook(ToolTask, {
          beforeTool: async (call, api, context) => {
            const restriction = await taskController.toolRestriction(context, call.name);
            const tool = durableTools.find(tool => tool.name === call.name);
            if (restriction && !["read", "grep", "find", "ls"].includes(call.name) && tool?.metadata?.effect !== "read") return { block: restriction };
            const packagePolicy = packageReadGuard({ toolName: call.name, args: call.arguments });
            if (packagePolicy?.arguments) return { arguments: packagePolicy.arguments };
            if (packagePolicy?.block) return { block: packagePolicy.block.reason || String(packagePolicy.block) };
            return undefined;
          },
        }),
      ],
    }));
    harness = await Harness.open(await openNodeSqliteStorage(databasePath), {
      models: modelRuntime,
      registry,
      settings: harnessSettings,
      env: executionEnvs.env,
      onReport: (error) => { if (process.env.CORAGENT_DEBUG === "1") console.error(error); },
    }, PI_TODO_CONTEXT);
    const created = (await harness.conversation("root", PI_TODO_CONTEXT)) === undefined;
    const conversation = await harness.root(PI_TODO_CONTEXT, { agent: { cwd, ...(created && resolved.model ? { model: resolved.model } : {}), ...(created && resolved.thinkingLevel ? { thinkingLevel: resolved.thinkingLevel } : {}) } });
    inputAdmission = createInputAdmission({ harness, conversation, LiveDoc, InboxDoc, admitSubmission });
    taskController = createTaskController({ harness, conversation, admission: inputAdmission, LiveDoc, InboxDoc,
      kernel: commandBridge, workspaceId, sessionId, context: PI_TODO_CONTEXT,
      enabled: process.env.CORAGENT_AUTOMATIC_CONTINUATION !== "0" });
    await inputAdmission.checkRecovery(PI_TODO_CONTEXT);
  monitorAdmission = createMonitorAdmission({ admission: inputAdmission, kernel: commandBridge, sessionId,
      wakeMessage, producerToken, taskController });
    const sessionAdmission = createSessionAdmission({ harness, conversation, LiveDoc, taskController });
    taskController.start();
    return {
      harness, conversation: bindUserInputConversation(conversation, inputAdmission, harness, sessionAdmission), modelRuntime, settingsManager,
      facetLoader: createStaticFacetLoader([defineFacet({ id: "@coragent/client-queries", setup(env) {
        const { validateConsumption: _validate, ...monitorService } = monitorAdmission;
        env.provide(CoRAgentMonitorAdmission, monitorService);
        env.provide(CoRAgentInputAdmission, createInputService(inputAdmission));
        env.provide(CoRAgentSessionAdmission, sessionAdmission);
        env.provide(CoRAgentMonitor, createMonitorService({ controller: taskController, harness, conversation, kernel: commandBridge, workspaceId, sessionId, LiveDoc }));
        env.provide(CoRAgentClientQueries, createClientQueries({ workspaceId, sessionId, commandBridge, promptManifest,
          readTelemetry: async (context) => {
            const { estimateContext } = await loadPi("compaction", sourceRoot);
            const [view, agent, research] = await Promise.all([conversation.context(context), conversation.agent(context), commandBridge.execute_command("research.read", {})]);
            const model = agent.model && modelRuntime.getModel(agent.model.provider, agent.model.modelId);
            // Reuse Pi's compaction-aware request estimate. It is not an exact tokenizer count.
            const contextWindow = model?.contextWindow || null;
            const inputBudgetTokens = contextWindow === null ? null : contextInputBudget(contextWindow, harnessSettings.compaction);
            return { model: agent.model || null, contextWindow,
              contextTokens: estimateContext(view, []), inputBudgetTokens,
              reserveTokens: harnessSettings.compaction.reserveTokens ?? null,
              estimated: true,
              entryId: view.entries.at(-1)?.id ?? null, firstEntryId: view.entries[0]?.id ?? null, headId: view.head?.id ?? null, research };
          },
        }));
      } })]),
      cleanup: async (context) => { await taskController.close(); try { await executionEnvs.cleanup(context); } finally { await commandBridge.close(); } },
    };
  } catch (error) {
    await taskController?.close();
    await commandBridge?.close().catch(() => {});
    await harness?.close(PI_TODO_CONTEXT).catch(() => {});
    await executionEnvs.cleanup(PI_TODO_CONTEXT).catch(() => {});
    throw error;
  }
}
