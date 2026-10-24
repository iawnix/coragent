import { taskStateLabel } from './monitor.mjs';

const section = (title, body) => `${title}\n${'─'.repeat(title.length)}\n${body}`;
const join = items => items.filter(Boolean).join('\n');
const unique = items => [...new Set(items)];
const questionState = state => ({ open: 'Open', paused: 'Paused', closed: 'Ended' })[state];
const read = ref => `/research read ${ref}`;
const refs = values => values?.length ? `References: ${unique(values).join(', ')}` : '';
const updated = value => value ? `Updated: ${value}` : '';
const recorded = value => value ? `Recorded: ${value}` : '';
const subjectLines = (subjects = {}) => Object.entries(subjects).map(([role, ref]) => `Subject — ${role.replaceAll('_', ' ')}: ${ref}`);
const researchKind = kind => ({ node: 'Research question', result: 'Result', note: 'Research note',
  node_created: 'Question created', node_updated: 'Research update', result_published: 'Result published',
  job: 'Execution record', user: 'User request' })[kind] || kind.replaceAll('_', ' ');

function reviewNotice(notice) {
  switch (notice.code) {
    case 'new_evidence_after_assessment':
      return join(['New evidence is available; the current judgment needs review.', refs(notice.references)]);
    case 'result_superseded':
      return notice.superseded_by ? `This result has been superseded by ${notice.superseded_by}. Read ${read(notice.superseded_by)}.`
        : 'The current judgment has been superseded; read the research question to review its replacement.';
    case 'cited_result_superseded':
      return notice.superseded_by ? `Cited result ${notice.used} has been superseded by ${notice.superseded_by}. Review ${read(notice.superseded_by)}.`
        : 'A cited result has been superseded; read the research question to review the changed evidence.';
    case 'node_context_changed':
      return 'The research question or plan changed after this result was recorded; review its relevance.';
    case 'cited_node_changed':
      return notice.node_id ? `Related research ${notice.node_id} changed; review ${read(notice.node_id)}.`
        : 'Related research changed; read the research question to review the changed evidence.';
    case 'review_notices_omitted':
      return 'Review details are omitted; read the research question before relying on this judgment.';
    default:
      return notice.superseded_by
        ? `Cited result ${notice.used} has been superseded by ${notice.superseded_by}. Review ${read(notice.superseded_by)}.`
        : `Review needed: ${notice.summary || notice.code.replaceAll('_', ' ')}.`;
  }
}

function reviewLines(notices = [], count = notices.length) {
  return join([
    ...unique(notices.map(reviewNotice)),
    count > notices.length ? `${count - notices.length} additional review notices omitted; read the research question.` : '',
  ]);
}

function findingText(item) {
  return join([
    item.content_omitted ? `Full text and its caveats are omitted from this overview. Read ${read(item.ref)}.` : item.summary,
    !item.content_omitted && item.limitations ? `Limitations: ${item.limitations}` : '',
    !item.content_omitted ? refs(item.references) : '',
    item.reference_count > (item.references?.length || 0) ? `Some references are omitted. Read ${read(item.ref)}.` : '',
    recorded(item.created_at),
    `Read: ${read(item.ref)}`,
  ]);
}

/** A view of persisted judgments. Task and Job states never establish a scientific conclusion. */
export function formatResearchOverview(brief, task) {
  if (brief.schema_version !== 'research-brief/1') throw new Error('Unsupported research overview');
  const bound = unique([...brief.scope.entry_node_ids, ...brief.scope.focus_node_ids]);
  // A recent question from this session is a navigation hint, not a new task's research.
  const scoped = bound.length > 0;
  const findings = scoped ? brief.findings : [];
  const primary = new Set(bound);
  const questions = findings.filter(item => item.kind === 'node' && primary.has(item.ref));
  const assessments = findings.filter(item => item.selected_assessment && primary.has(item.node_id));
  const primaryJobs = new Set(findings.filter(item => item.kind === 'job' && primary.has(item.node_id)).map(item => item.ref));
  const allQuestions = bound;
  const titles = new Map(findings.filter(item => item.kind === 'node').map(item => [item.ref, item.title || 'Research question']));
  const sections = [join([
    task ? `Task: ${task.title} · ${taskStateLabel(task.state)}` : 'No current task',
    task?.reason && ['paused', 'cancelled'].includes(task.state) ? `Reason: ${task.reason}` : '',
    updated(task?.updated_at),
  ])];
  if (task?.objective) sections.push(section('Research goal', task.objective));
  if (!scoped) {
    sections.push('No research question is linked to the current task. Browse saved questions with /research read.');
  } else {
    const judgments = allQuestions.map(nodeId => {
      const node = questions.find(item => item.ref === nodeId);
      const assessment = assessments.find(item => item.node_id === nodeId);
      const notices = unique([
        ...(assessment?.review_codes || []),
        ...brief.uncertainties.filter(item => item.ref === nodeId && item.kind === 'assessment_review').map(item => item.code),
        ...brief.contradictions.filter(item => item.ref === nodeId && item.kind === 'node_review').flatMap(item => item.codes || []),
      ]).map(code => reviewNotice(brief.uncertainties.find(item => item.ref === nodeId && item.code === code) || { code }));
      return join([
        `${titles.get(nodeId) || 'Research question'} · ${nodeId}`,
        node?.summary && node.summary !== task?.objective ? `Question: ${node.summary}` : '',
        node?.omitted_fields?.includes('goal') ? `Full question omitted. Read ${read(nodeId)}.` : '',
        ...notices,
        assessment ? findingText(assessment) : !node ? `Question details are omitted. Read ${read(nodeId)}.` : node.assessment_ref
          ? `The current judgment is omitted from this overview. Read ${read(node.assessment_ref)}.`
          : 'No current judgment has been recorded.',
        updated(node?.updated_at),
        `Question details: ${read(nodeId)}`,
      ]);
    });
    sections.push(section('Current judgment', judgments.join('\n\n') || 'Judgments omitted from this overview. Open /research read to choose the question.'));
    const results = findings.filter(item => item.kind === 'result' && !item.selected_assessment && primary.has(item.node_id));
    const replacements = new Map(findings.filter(item => item.supersedes).map(item => [item.supersedes, item.ref]));
    if (results.length) sections.push(section('Recorded results', results.map(item => join([
      `${titles.get(item.node_id) || 'Research question'} · ${item.ref}`,
      replacements.has(item.ref) ? `Superseded by ${replacements.get(item.ref)}.` : '',
      item.supersedes ? `Replaces ${item.supersedes}.` : '', findingText(item),
    ])).join('\n\n')));
    const notes = findings.filter(item => item.kind === 'note' && !item.selected_assessment && primary.has(item.node_id));
    if (notes.length) sections.push(section('Recent research notes', notes.map(item => join([
      `${titles.get(item.node_id) || 'Research question'} · ${item.ref}`, findingText(item),
    ])).join('\n\n')));
  }
  if (task?.progress?.summary) sections.push(section('Task progress', join([
    task.progress.summary, recorded(task.progress.at),
  ])));
  const nextStep = task?.next_action || questions.filter(node => node.plan || node.omitted_fields.includes('plan')).map(node => join([
    `Recorded research plan: ${node.title || 'Research question'}`,
    node.plan || `The plan is omitted from this overview. Read ${read(node.ref)}.`,
    updated(node.updated_at), `Question details: ${read(node.ref)}`,
  ])).join('\n\n');
  if (nextStep) sections.push(section(
    ['completed', 'partial', 'cancelled'].includes(task?.state) ? 'Last recorded next step' : 'Next step',
    join([nextStep, ['paused', 'cancelled', 'completed', 'partial'].includes(task?.state) ? 'This task is not continuing automatically.' : '']),
  ));
  const obstacles = join([
    task?.state === 'blocked' ? task.reason : '',
    task?.state === 'blocked' && task.resume_when ? `To continue: ${task.resume_when}` : '',
    task?.execution_recovery?.detail ? `Execution recovery: ${task.execution_recovery.detail}` : '',
    task?.execution_recovery?.next_retry_at ? `Automatic retry after: ${task.execution_recovery.next_retry_at}` : '',
    task?.wait && task.state === 'waiting' ? `Waiting for ${task.wait.job_count} job${task.wait.job_count === 1 ? '' : 's'} (${task.wait.mode === 'all' ? 'all must finish' : 'any may finish'}).` : '',
    ...brief.contradictions.filter(item => item.kind === 'job_failure' && primaryJobs.has(item.ref)).map(item => `${item.ref}: ${item.summary}`),
  ]);
  if (obstacles) sections.push(section('Current obstacles', obstacles));
  const actionRequired = task?.state === 'blocked' && task.block_kind === 'missing_user_input'
    ? task.resume_when
    : task?.state === 'paused' ? `Resume when ready: /monitor task resume ${task.user_task_id}`
    : task?.execution_recovery?.state === 'attention_required' ? `Inspect the execution failure: /monitor task ${task.user_task_id}` : '';
  if (actionRequired) sections.push(section('Your action needed', actionRequired));
  const related = findings.filter(item => item.kind === 'node' && !primary.has(item.ref));
  if (related.length) sections.push(section('Related questions', related.map(item => `${item.title || 'Research question'} · ${read(item.ref)}`).join('\n')));
  const omitted = Object.entries(brief.coverage.omitted).filter(([, count]) => count > 0);
  const limits = join([
    scoped && omitted.length ? `This overview omits ${omitted.map(([kind, count]) => `${count} ${kind.replaceAll('_', ' ')}`).join(', ')}. Read the question for its full records.` : '',
    brief.projection_status === 'incomplete' ? 'Some execution updates are still being reconciled; this overview may not include them yet.' : '',
    task?.truncated ? `Task details are shortened. Read /monitor task ${task.user_task_id}.` : '',
  ]);
  if (limits) sections.push(section('View limits', limits));
  sections.push(join([
    'Task and Job completion do not establish scientific validity; use the recorded judgments and evidence.',
    'Browse: /research read · Search: /research search <keywords>',
    task ? `Execution details: /monitor task ${task.user_task_id}` : '',
  ]));
  return sections.join('\n\n');
}

function resultText(result) {
  const references = join([
    result.inputs?.length ? `Inputs: ${result.inputs.join(', ')}` : '',
    result.evidence_refs?.length ? `Cited records: ${result.evidence_refs.join(', ')}` : '',
    result.check_refs?.length ? `Check records: ${result.check_refs.join(', ')}` : '',
    ...subjectLines(result.subjects),
  ]);
  return [
    join([`Result: ${result.id}`, recorded(result.created_at), result.supersedes ? `Replaces ${result.supersedes}.` : '']),
    ...(result.observation ? [section('Observations', result.observation)] : []),
    section('Conclusion', result.conclusion),
    ...(result.limitations ? [section('Limitations', result.limitations)] : []),
    ...(references ? [section('References', references)] : []),
    ...(result.files?.length ? [section('Saved materials', result.files.map(file => join([
      `${file.name} · ${file.artifact_ref}`, file.purpose,
    ])).join('\n\n'))] : []),
    result.node_id ? `Research question: ${read(result.node_id)}` : '',
  ].filter(Boolean).join('\n\n');
}

function recordText(record) {
  const kind = record.origin === 'user' ? 'Original request' : record.origin === 'runtime' ? 'Execution record' : 'Research note';
  return join([`${kind}: ${record.title} · ${record.ref}`, recorded(record.created_at), '', record.content,
    refs(record.references), record.node_id ? `Research question: ${read(record.node_id)}` : '']);
}

/** Full reads use the existing read protocol; callers assemble character pages before formatting. */
export function formatResearchDetail(value) {
  if (value.schema_version !== 'research-read/2') throw new Error('Unsupported research detail');
  if (value.offset !== 0 || value.next_offset !== null) throw new Error('Research detail is incomplete; load all read pages before displaying it.');
  const detail = JSON.parse(value.text);
  if (detail.node) {
    const { node, assessment } = detail;
    const subjects = subjectLines(node.subjects);
    return [
      join([`${node.title} · ${node.id}`, `Question status: ${questionState(node.status)}`, updated(node.updated_at)]),
      section('Research goal', node.goal),
      ...(subjects.length ? [section('Research materials', subjects.join('\n'))] : []),
      section('Current judgment', join([
        reviewLines(detail.review_notices),
        assessment ? assessment.schema_version === 'research-result/1' ? resultText(assessment) : recordText(assessment) : 'No current judgment has been recorded.',
      ])),
      ...(node.plan ? [section('Research plan', node.plan)] : []),
      ...(detail.results.length ? [section('Recorded results', detail.results.map(item => join([
        `Result summary: ${item.summary}`, recorded(item.created_at),
        detail.results.some(other => other.supersedes === item.id) ? `Superseded by ${detail.results.find(other => other.supersedes === item.id).id}.` : '',
        `Full result and caveats: ${read(item.id)}`,
      ])).join('\n\n'))] : []),
      ...(detail.recent_notes.records.length ? [section('Recent research notes', detail.recent_notes.records.map(recordText).join('\n\n'))] : []),
      ...(detail.recent_notes.total > detail.recent_notes.records.length
        ? [`${detail.recent_notes.total - detail.recent_notes.records.length} older notes are not shown. Search saved history with /research search <keywords>.`] : []),
      ...(detail.related_nodes.length ? [section('Related questions', detail.related_nodes.map(item => `${item.title} · ${read(item.id)}`).join('\n'))] : []),
      'Question status records whether the question is open or ended; the judgment and evidence state what is established.',
    ].join('\n\n');
  }
  if (detail.schema_version === 'research-result/1') return [reviewLines(value.review_notices, value.review_notice_count), resultText(detail)].filter(Boolean).join('\n\n');
  if (detail.schema_version === 'research-record/2') return recordText(detail);
  throw new Error('Unsupported research record');
}

export function formatResearchSearch(value, query) {
  if (value.schema_version !== 'research-search/2') throw new Error('Unsupported research search');
  return [
    `Search: ${query || 'All saved records'} · ${value.total} match${value.total === 1 ? '' : 'es'}`,
    'Matches saved text. Excerpts may omit context and caveats; open a record before relying on it.',
    ...value.records.map(item => join([
      `${item.title} · ${researchKind(item.kind)} · ${item.ref}`,
      recorded(item.created_at), `Excerpt: ${item.excerpt}`, `Read: ${read(item.ref)}`,
    ])),
    ...(!value.records.length ? ['No matching records.'] : []),
    ...(value.next_offset !== null ? [`More matches: /research search --offset ${value.next_offset} -- ${query}`] : []),
  ].join('\n\n');
}

/** Titles navigate; references identify the exact immutable or current record. */
export function researchChoices(value) {
  if (value.schema_version === 'research-search/2') return value.records.map(item => ({
    value: item.ref, label: item.title, description: `${researchKind(item.kind)} · ${item.ref}`,
  }));
  throw new Error('Unsupported research navigation');
}
