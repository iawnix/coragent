import { NodeExecutionEnv } from "@earendil-works/pi-durable/env/node";
import { loadPi } from "./source.mjs";

/** CoRAgent owns the host configuration of the public Durable Harness. */
export function createHarnessSettings(settings) {
  return {
    get stream() {
      const provider = settings.getProviderRetrySettings();
      const idle = settings.getHttpIdleTimeoutMs();
      return { timeoutMs: provider.timeoutMs ?? (idle === 0 ? 2147483647 : idle),
        maxRetryDelayMs: provider.maxRetryDelayMs,
        ...(provider.maxRetries === undefined ? {} : { maxRetries: provider.maxRetries }) };
    },
    get compaction() { return settings.getCompactionSettings(); },
    get retry() { return settings.getRetrySettings(); },
    get steeringMode() { return settings.getSteeringMode(); },
    get followUpMode() { return settings.getFollowUpMode(); },
  };
}

export async function configureHarnessHttp(settings) {
  const { applyHttpProxySettings, configureHttpDispatcher } = await loadPi("http");
  applyHttpProxySettings(settings.getGlobalSettings().httpProxy);
  configureHttpDispatcher(settings.getHttpIdleTimeoutMs());
}

export class ExecutionEnvs {
  #envs = new Map();
  constructor(defaultCwd) { this.defaultCwd = defaultCwd; }
  env = ({ cwd = this.defaultCwd }) => {
    if (!this.#envs.has(cwd)) this.#envs.set(cwd, new NodeExecutionEnv({ cwd }));
    return this.#envs.get(cwd);
  };
  async cleanup(context) {
    const envs = [...this.#envs.values()];
    this.#envs.clear();
    await Promise.all(envs.map(env => env.cleanup(context)));
  }
}

export async function findInitialAgentModel(settings, modelRuntime, cli) {
  const { resolveCliModel, findInitialModel } = await loadPi("modelResolver");
  const selected = cli
    ? resolveCliModel({ cliProvider: cli.provider, cliModel: cli.model, modelRuntime })
    : await findInitialModel({ scopedModels: [], isContinuing: false,
      defaultProvider: settings.getDefaultProvider(), defaultModelId: settings.getDefaultModel(),
      defaultThinkingLevel: settings.getDefaultThinkingLevel(), modelRuntime });
  if (cli && (selected.error || !selected.model)) throw new Error(`Could not resolve model: ${selected.error ?? cli.model}`);
  return { ...(selected.model ? { model: { provider: selected.model.provider, modelId: selected.model.id } } : {}),
    ...(selected.thinkingLevel === undefined ? {} : { thinkingLevel: selected.thinkingLevel }) };
}
