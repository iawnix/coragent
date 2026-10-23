import { formatFields } from '../renderers/fields.mjs';

const STATES = {
  active: 'Researching', waiting: 'Waiting for compute', paused: 'Paused', blocked: 'Needs attention',
  completing: 'Preparing delivery', completed: 'Completed', partial: 'Partially completed', cancelled: 'Cancelled', recovering: 'Checking recovery',
};

export const taskStateLabel = state => STATES[state] || 'Unknown';
const text = value => value === null || value === undefined || value === '' ? '—' : String(value);
const lines = value => value.length ? value.join('\n') : 'No entries';

export function formatTask(task) {
  if (!task) return 'No current task';
  return [
    `Task: ${task.title} · ${taskStateLabel(task.state)}`,
    `Goal: ${task.objective}`,
    `Progress: ${text(task.progress?.summary)}`,
    ...(task.next_action && !['completed', 'partial', 'cancelled'].includes(task.state) ? [`Next: ${task.next_action}`] : []),
    ...(task.block_details?.resume_when ? [`To resume: ${task.block_details.resume_when}`] : []),
    ...(task.execution_recovery ? [
      `Execution recovery: ${task.execution_recovery.state} · ${task.execution_recovery.phase}`,
      `Failure: ${task.execution_recovery.reason} · ${text(task.execution_recovery.detail)}`,
      ...(task.execution_recovery.next_retry_at ? [`Retry after: ${task.execution_recovery.next_retry_at}`] : []),
      'Research evidence is retained. Inspect execution records before resuming.',
    ] : []),
    ...(task.wait ? [`Waiting: ${task.wait.job_ids.join(', ')} (${task.wait.mode})`] : []),
    ...(task.reason ? [`Reason: ${task.reason}`] : []),
    `Delivery criteria:\n${lines(task.criteria.map(item => `• ${item.description}`))}`,
    `Updated: ${task.updated_at}`,
    '', `/monitor task ${task.user_task_id}`,
    `/monitor jobs --task ${task.user_task_id}`,
    `/monitor runs --task ${task.user_task_id}`,
    ...(['active', 'waiting', 'blocked'].includes(task.state) ? [`/monitor task pause ${task.user_task_id}`] : []),
    ...(['paused', 'blocked'].includes(task.state) || task.execution_recovery?.state === 'attention_required' ? [`/monitor task resume ${task.user_task_id}`] : []),
  ].join('\n');
}

function jobRow(job) {
  return `${job.job_id} · ${text(job.state)} · Collection: ${text(job.collection_state)}`;
}

// Five user-facing activity labels. A dash means the observation is not ready.
// Detailed lifecycle and controller facts remain in task details and health.
export function continuationLabel(response) {
  const task = response.task, running = response.execution?.state === 'running';
  switch (response.continuation?.state) {
    case 'idle': return task?.state === 'partial' ? 'Partially completed' : task?.state === 'completed' ? 'Completed'
      : task?.state === 'cancelled' ? 'Stopped' : running ? 'Working' : 'Idle';
    case 'paused':
    case 'blocked':
    case 'error':
    case 'attention_required': return 'Stopped';
    case 'disabled': return running ? 'Working' : 'Stopped';
    case 'checking': return running ? 'Working' : '—';
    case 'retrying': return running ? 'Working' : 'Waiting';
    case 'waiting': return 'Waiting';
    case 'pending':
    case 'ready': return 'Working';
    default: return '—';
  }
}

export function continuationDetail(response) {
  switch (response.continuation?.state) {
    case 'idle': return response.task?.state === 'cancelled' ? 'The task was cancelled.' : null;
    case 'paused': return 'The task is paused. Resume it when ready.';
    case 'blocked': return 'Research is blocked. Resolve the reason below before continuing.';
    case 'disabled': return 'Automatic continuation is off. Inspect /monitor health before resuming.';
    case 'checking': return 'Waiting for the first continuation check.';
    case 'overdue': return 'Continuation checks are overdue. Inspect /monitor health.';
    case 'error': return 'Automatic continuation failed. Inspect /monitor health and the task execution records.';
    case 'attention_required': return 'Execution recovery needs attention. Inspect the task execution records before resuming.';
    case 'retrying': return response.execution?.state === 'running'
      ? 'Execution recovery is running.' : 'Execution will retry automatically.';
    case 'waiting': return 'Waiting for compute. Continues when ready.';
    default: return null;
  }
}

function formatOverview(response) {
  const { task, jobs } = response;
  const counts = jobs?.counts || {};
  const jobSummary = `${counts.running ?? 0} running · ${counts.queued ?? 0} queued · ${counts.total ?? 0} total`;
  const scopeLabel = jobs?.scope === 'task' ? 'Task jobs' : 'Session jobs';
  const command = jobs?.scope === 'task' && task ? `/monitor jobs --task ${task.user_task_id}` : '/monitor jobs';
  const continuation = continuationLabel(response);
  const detail = continuationDetail(response);
  return [
    task ? `Task: ${task.title}` : 'No current task',
    `Status: ${continuation}`,
    ...(detail ? [`Details: ${detail}`] : []),
    ...(task ? [`Goal: ${task.objective}`] : []),
    ...(task?.progress?.summary ? [`Progress: ${task.progress.summary}`] : []),
    ...(task?.next_action && !['completed', 'partial', 'cancelled'].includes(task.state) ? [`Next: ${task.next_action}`] : []),
    ...(task?.wait ? [`Waiting for: ${task.wait.job_count} jobs (${task.wait.mode === 'all' ? 'all must finish' : 'any may finish'})`] : []),
    ...(task?.reason ? [`Reason: ${task.reason}`] : []),
    ...(task?.resume_when ? [`To resume: ${task.resume_when}`] : []),
    ...(task?.execution_recovery?.detail ? [`Execution: ${task.execution_recovery.detail}`] : []),
    ...(task?.execution_recovery?.next_retry_at ? [`Retry after: ${task.execution_recovery.next_retry_at}`] : []),
    `${scopeLabel}: ${jobSummary}`,
    ...(jobs?.active?.length ? ['Active jobs', ...jobs.active.map(job => `${job.job_id} · ${job.state}`)] : []),
    ...(jobs?.active_omitted ? [`${jobs.active_omitted} more active jobs: ${command}`] : []),
    ...(task?.truncated ? [`Task summary shortened. Read /monitor task ${task.user_task_id} for complete details.`] : []),
    `Updated: ${text(response.updated_at)}`,
    '', task ? `/monitor task ${task.user_task_id} · ${command}` : '/monitor tasks · /monitor jobs · /monitor health',
  ].join('\n');
}

function nextPage(response, command, params) {
  if (!response.next_cursor) return '';
  return `\n\nNext page: /monitor ${command}${params.user_task_id ? ` --task ${params.user_task_id}` : ''}${params.limit ? ` --limit ${params.limit}` : ''} --cursor ${response.next_cursor}`;
}

function formatResearch(snapshot, sessionJobIds) {
  const research = snapshot.research;
  const labels = { open: 'Open', paused: 'Paused', closed: 'Ended' };
  const nodes = research.nodes.map(node => {
    const detail = snapshot.nodes.find(item => item.id === node.id);
    return [
      `• ${node.id} · ${node.title}`,
      `  Status: ${node.status} · ${labels[node.status]} · Revision: ${node.revision}`,
      `  Plan: ${text(node.plan)}`,
      ...(node.content_omitted ? ['  Excerpt only; read the problem for its complete plan.'] : []),
      `  Assessment reference: ${text(node.assessment_ref)}`,
      ...(detail?.recent_results || []).map(result => `  Result: ${result.id} · ${result.summary}`),
      `  Read: /research read ${node.read.ref}`,
    ].join('\n');
  });
  const nodeIds = new Set(research.nodes.map(node => node.id));
  const jobs = [...snapshot.running_jobs, ...snapshot.uncollected_jobs].filter(job => nodeIds.has(job.node_id));
  const sessionJobs = new Set(sessionJobIds);
  const omitted = Object.entries(research.omitted).filter(([, count]) => count > 0);
  return [
    'Research problems',
    `Entry references: ${research.entry_node_ids.join(', ') || '—'}`,
    `Current focus: ${research.focus_node_ids.join(', ') || '—'}`,
    ...(nodes.length ? nodes : [omitted.length ? 'Research details omitted from this snapshot.' : 'No research problems linked.']),
    '', 'Relations (references to the same problems)',
    lines(research.relations.map(edge => `• ${edge.source} ${edge.kind} ${edge.target}`)),
    ...(jobs.length ? ['', 'Related compute jobs', ...jobs.map(job => sessionJobs.has(job.job_id)
      ? `${job.node_id}: /monitor job ${job.job_id}`
      : `${job.node_id}: ${job.job_id} · Outside this session`)] : []),
    ...(omitted.length ? ['', `Omitted: ${omitted.map(([key, count]) => `${key.replaceAll('_', ' ')} ${count}`).join(', ')}. Read the referenced problems for more detail.`] : []),
    '', `Research snapshot: ${snapshot.sequence}. Ended problems do not imply verified conclusions or task completion.`,
  ].join('\n');
}

/** Explicit fields keep execution internals and tool payloads out of the task overview. */
export function formatMonitor(method, response, params = {}) {
  switch (method) {
    case 'monitor/overview':
      return formatOverview(response);
    case 'monitor/tasks':
      return lines(response.items.map(task => `${task.user_task_id} · ${task.title}${task.truncated ? '…' : ''} · ${taskStateLabel(task.state)}`))
        + '\n\nDetails: /monitor task <task-id>' + nextPage(response, 'tasks', params);
    case 'monitor/task/read':
      return formatTask(response.task) + '\n\n' + formatResearch(response.research, response.session_job_ids);
    case 'monitor/task/pause':
    case 'monitor/task/resume':
      return formatTask(response.task);
    case 'monitor/task/cancel':
      return formatTask(response.task) + `\n\nCompute jobs: ${response.jobs_policy === 'keep' ? 'Kept running' : 'Cancellation requested'}`
        + (response.job_cancellations ? '\n' + formatFields(response.job_cancellations) : '');
    case 'monitor/jobs':
      return lines(response.items.map(jobRow)) + '\n\nDetails: /monitor job <job-id>' + nextPage(response, 'jobs', params);
    case 'monitor/job/read':
    case 'monitor/job/cancel':
      return [`Job: ${response.job.job_id}`, `Execution: ${text(response.job.state)}`,
        `Collection: ${text(response.job.collection_state)}`,
        `User task: ${text(response.job.user_task_id)}`, `Platform: ${text(response.job.platform)}`,
        ...(response.job.error ? [`Error: ${text(response.job.error)}`] : []),
        ...(response.job.result_receipt ? ['Receipt:\n' + formatFields(response.job.result_receipt)] : []),
        '', `/monitor job cancel ${response.job.job_id}`].join('\n');
    case 'monitor/runs':
      return lines(response.items.map(run => `${run.run_id} · ${text(({user_message: "User message", job_event: "Job event", task_continue: "Continue task", execution_retry: "Retry execution", final_response_retry: "Retry final response"})[run.reason])} · ${text(run.state)} · ${text(run.generation_count)} model calls`))
        + '\n\nExecution details: /monitor run <run-id>' + nextPage(response, 'runs', params);
    case 'monitor/run/read':
      return [`Execution: ${response.run.run_id}`, `User task: ${text(response.run.user_task_id)}`, '',
        lines(response.items.map(item => [
          `${item.kind === 'pi.generation' ? 'Model request' : item.kind === 'pi.tool' ? 'Tool call' : item.kind}${item.tool_name ? ': ' + item.tool_name : ''} · ${item.state}${item.outcome ? ' / ' + item.outcome : ''}`,
          `  Started: ${text(item.started_at)} · Ended: ${text(item.ended_at)}`,
          ...(item.error ? [`  Error: ${item.error.code}`,
            ...(item.error.failure_class ? [`  Class: ${item.error.failure_class}`] : []),
            ...(typeof item.error.retryable === 'boolean' ? [`  Retryable: ${item.error.retryable ? 'Yes' : 'No'}`] : []),
            ...(item.error.action_outcome ? [`  Action outcome: ${item.error.action_outcome}`] : [])] : []),
          `  Pi task: ${item.pi_task_id}${item.result_entry_id ? ' · Result entry: ' + item.result_entry_id : ''}`,
        ].join('\n'))),
      ].join('\n') + nextPage(response, `run ${params.run_id}`, params);
    case 'monitor/health':
      return formatFields(response);
    default: throw new Error(`Unsupported Monitor view: ${method}`);
  }
}
