// The legacy side uses its real product Harness; the candidate uses its actual supervised Worker.
import { join } from 'node:path';
import { pathToFileURL } from 'node:url';
const product = process.env.CORAGENT_PACKAGE_ROOT;
const candidate = process.env.CORAGENT_UPGRADE_SIDE === 'candidate';
let runtime, worker, context, metadata;
const submitted = new Map();
async function handle(method, params) {
  if (method === 'open') {
    metadata = params.metadata;
    if (candidate) {
      const { startSessionWorker } = await import(pathToFileURL(join(product, 'apps/agent/runtime/worker-process.mjs')));
      worker = startSessionWorker({ sourceRoot: process.env.CORAGENT_PI_RUNTIME_ROOT, packageRoot: product,
        metadata, producerToken: 'fixture-only', model: { provider: 'fixture', id: 'fixture' }, onView() {} });
      await worker.startup;
    } else {
      const { BACKGROUND_CONTEXT } = await import('@earendil-works/chord/context');
      context = BACKGROUND_CONTEXT;
      const { createCoRAgentHarness } = await import(pathToFileURL(join(product, 'apps/agent/runtime/setup.mjs')));
      runtime = await createCoRAgentHarness(join(metadata.path, 'session.sqlite'), { metadata, provider: 'fixture', model: 'fixture' });
      runtime.harness.resume();
    }
    return true;
  }
  if (method === 'submit') {
    if (candidate) {
      const result = await worker.request('service', { service: 'coragent.input-admission', method: 'submit', args: params });
      if (result.error) throw Object.assign(new Error(result.error.message), result.error);
      return result.result;
    }
    const submission = await runtime.conversation.submit({ type: 'input', ...params }, context);
    submitted.set(params.requestId, submission);
    return submission.status(context);
  }
  if (method === 'status') {
    if (candidate) return (await worker.request('service', { service: 'coragent.input-admission', method: 'status', args: params })).result;
    return submitted.get(params.requestId)?.status(context);
  }
  if (method === 'view') {
    if (candidate) return worker.request('snapshot');
    const view = await runtime.conversation.viewState(context);
    try { return view.value; } finally { await view.dispose(context); }
  }
  if (method === 'task') {
    if (candidate) {
      const call = async (method, params = {}) => {
        const reply = await worker.request('service', { service: 'coragent.monitor', method: 'handle', args: {
          method, params: { workspace_id: metadata.workspaceId, session_id: metadata.id, ...params } } });
        if (reply.error) throw new Error(reply.error.message);
        return reply.result;
      };
      const overview = await call('monitor/overview');
      return overview.task ? (await call('monitor/task/read', { user_task_id: overview.task.user_task_id })).task : null;
    }
    const { UserTasks, UserTask } = await import(pathToFileURL(join(product, 'apps/agent/tasks/controller.mjs')));
    const index = await runtime.harness.snapshot(UserTasks, runtime.conversation.id, context);
    return index?.current ? runtime.harness.snapshot(UserTask, runtime.conversation.id, index.current, context) : null;
  }
  if (method === 'compact') {
    if (candidate) return worker.request('compact', params);
    return { task_id: String(await runtime.conversation.compact(params.instructions, context)) };
  }
  if (method === 'close') {
    if (candidate) await worker?.close();
    else { try { await runtime?.cleanup(context); } finally { await runtime?.harness.close(context); } }
    return true;
  }
  throw new Error('Unknown rehearsal operation');
}
process.on('message', message => {
  void handle(message.method, message.params ?? {}).then(result => {
    process.send({ id: message.id, result }, () => { if (message.method === 'close') process.disconnect(); });
  }, error => process.send({ id: message.id, error: { code: error.code, message: error.message, stack: error.stack } }));
});
