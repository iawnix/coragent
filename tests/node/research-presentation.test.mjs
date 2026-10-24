import assert from 'node:assert/strict';
import test from 'node:test';
import { formatResearchOverview, formatResearchDetail, formatResearchSearch, researchChoices } from '../../apps/agent/terminal/commands/research.mjs';
import { parseSlashCommand } from '../../apps/agent/tools/commands.mjs';

const time = '2026-10-24T10:00:00+00:00';
function overview(overrides = {}) {
  return {
    schema_version: 'research-brief/1', scope: { entry_node_ids: ['node_1'], focus_node_ids: ['node_1'], selection: 'explicit_focus' },
    coverage: { omitted: { nodes: 0, results: 0, notes: 0, jobs: 0 } }, projection_status: 'complete',
    findings: [
      { kind: 'node', ref: 'node_1', title: 'Compare reaction pathways', summary: 'Find the preferred pathway.',
        updated_at: time, assessment_ref: 'note_2', status: 'open', omitted_fields: [] },
      { kind: 'note', ref: 'note_2', node_id: 'node_1', selected_assessment: true, summary: 'Only conformer screening is established.',
        limitations: 'No transition state has been verified.', references: ['result_1', 'art_5'], content_omitted: false, created_at: time },
      { kind: 'result', ref: 'result_1', node_id: 'node_1', summary: 'Nine conformers were retained.',
        limitations: 'Electronic-state validation is pending.', references: ['art_5'], content_omitted: false, created_at: time },
    ], contradictions: [], uncertainties: [], limitations: [], follow_up: [], ...overrides,
  };
}
function task(overrides = {}) {
  return { user_task_id: 'task_1', title: 'Identify the favored pathway', objective: 'Compare both pathways at the requested level.',
    state: 'active', updated_at: time, next_action: 'Validate the transition-state input.', reason: null,
    block_kind: null, resume_when: null, wait: null, truncated: false, ...overrides };
}
function result(overrides = {}) {
  return { schema_version: 'research-result/1', id: 'result_1', node_id: 'node_1', created_at: time,
    summary: 'Screening is complete.', observation: 'Nine candidate conformers were saved.', conclusion: 'Only screening is complete; no preferred pathway is established.',
    limitations: 'No transition state has been verified.', inputs: ['art_1'], evidence_refs: ['art_2'], check_refs: ['art_3'],
    subjects: { candidate: 'art_4' }, files: [{ name: 'Conformer ensemble', artifact_ref: 'art_5', purpose: 'Input for the next calculation.' }],
    supersedes: null, ...overrides };
}
function readResponse(value, overrides = {}) {
  const text = JSON.stringify(value);
  return { schema_version: 'research-read/2', ref: value.id || value.ref || value.node.id, text,
    offset: 0, next_offset: null, total_characters: text.length, offset_unit: 'unicode_characters', ...overrides };
}

test('cancelled execution preserves the scientific judgment, its caveats, citations and last planned action', () => {
  const brief = overview();
  brief.findings[0].status = 'closed';
  brief.findings.push({ kind: 'job', ref: 'job_8', node_id: 'node_1', summary: 'succeeded', state: 'succeeded', collection_state: 'complete' });
  const body = formatResearchOverview(brief, task({ state: 'cancelled', reason: 'The user stopped the task.' }));
  assert.match(body, /Task: Identify the favored pathway · Cancelled/);
  assert.match(body, /Only conformer screening is established\./);
  assert.match(body, /No transition state has been verified\./);
  assert.match(body, /References: result_1, art_5/);
  assert.match(body, /Recorded results[\s\S]*Nine conformers were retained\.[\s\S]*Electronic-state validation is pending\./);
  assert.match(body, /Last recorded next step[\s\S]*Validate the transition-state input\.[\s\S]*not continuing automatically/);
  assert.match(body, /Updated: 2026-10-24T10:00:00/);
  assert.doesNotMatch(body, /Research complete|Verified result|Your action needed|succeeded/);
});

test('a saved unrelated question is not presented as the current task research', () => {
  const brief = overview({ scope: { entry_node_ids: [], focus_node_ids: [], selection: 'session_recent_fallback' } });
  const body = formatResearchOverview(brief, task({ title: 'Write a shell helper', objective: 'List local files.',
    progress: { summary: 'The local directory listing is ready.', at: time } }));
  assert.match(body, /No research question is linked to the current task/);
  assert.match(body, /Task progress[\s\S]*The local directory listing is ready\.[\s\S]*Recorded: 2026-10-24T10:00:00/);
  assert.doesNotMatch(body, /conformer|transition state|Compare reaction pathways|Current judgment/);
});

test('the recorded question plan supplies next-step context only when no task action is saved', () => {
  const brief = overview();
  brief.findings[0].plan = 'Refine both candidate transition structures.';
  const plan = formatResearchOverview(brief, task({ next_action: null }));
  assert.match(plan, /Next step[\s\S]*Recorded research plan: Compare reaction pathways[\s\S]*Refine both candidate transition structures\.[\s\S]*Updated: 2026-10-24T10:00:00/);
  const action = formatResearchOverview(brief, task());
  assert.match(action, /Next step[\s\S]*Validate the transition-state input/);
  assert.doesNotMatch(action, /Refine both candidate transition structures/);
  delete brief.findings[0].plan;
  brief.findings[0].omitted_fields = ['plan'];
  const omitted = formatResearchOverview(brief, task({ next_action: null }));
  assert.match(omitted, /The plan is omitted from this overview\. Read \/research read node_1/);
});

test('related research remains navigation and does not mix a different judgment into this task', () => {
  const brief = overview();
  brief.findings.push(
    { kind: 'node', ref: 'node_9', title: 'Related spectroscopy', summary: 'Identify the spectrum.', omitted_fields: [] },
    { kind: 'result', ref: 'result_9', node_id: 'node_9', selected_assessment: true, summary: 'The molecule is definitely stable.', references: ['art_99'] },
    { kind: 'job', ref: 'job_99', node_id: 'node_9', state: 'failed', summary: 'failed' },
  );
  brief.contradictions.push({ ref: 'job_99', kind: 'job_failure', summary: 'Unrelated spectrum failed.' });
  const body = formatResearchOverview(brief, task());
  assert.match(body, /Related questions[\s\S]*Related spectroscopy · \/research read node_9/);
  assert.doesNotMatch(body, /definitely stable|art_99|Unrelated spectrum failed/);
});

test('omitted judgments never display an incomplete conclusion without its limitations', () => {
  const brief = overview();
  Object.assign(brief.findings[1], { summary: 'Incorrect partial claim', limitations: 'Partial caveat', content_omitted: true, references: [] });
  brief.coverage.omitted.results = 4;
  brief.findings[0].omitted_fields = ['goal', 'plan'];
  brief.projection_status = 'incomplete';
  const body = formatResearchOverview(brief, task({ truncated: true }));
  assert.match(body, /Full text and its caveats are omitted[\s\S]*\/research read note_2/);
  assert.match(body, /Full question omitted\. Read \/research read node_1/);
  assert.match(body, /omits 4 results/);
  assert.match(body, /execution updates are still being reconciled/);
  assert.match(body, /Task details are shortened/);
  assert.doesNotMatch(body, /Incorrect partial claim|Partial caveat/);
  const missing = formatResearchOverview(overview({ findings: [] }), task());
  assert.match(missing, /Question details are omitted\. Read \/research read node_1/);
  assert.doesNotMatch(missing, /No current judgment has been recorded/);
});

test('new evidence and superseded citations request review without erasing the current judgment', () => {
  const brief = overview();
  brief.findings[1].review_codes = ['new_evidence_after_assessment', 'cited_result_superseded'];
  brief.uncertainties.push({ ref: 'node_1', kind: 'assessment_review', code: 'new_evidence_after_assessment', references: ['result_3'] });
  const body = formatResearchOverview(brief, task());
  assert.match(body, /New evidence is available; the current judgment needs review/);
  assert.match(body, /References: result_3/);
  assert.match(body, /A cited result has been superseded/);
  assert.match(body, /Only conformer screening is established/);
  assert.doesNotMatch(body, /undefined|invalidated|Your action needed/);
});

test('only an actual user input blocker asks the user for missing information', () => {
  const base = { state: 'blocked', reason: 'The next step needs a prerequisite.',
    block_kind: 'execution_failure', resume_when: 'Correct the geometry.' };
  const execution = formatResearchOverview(overview(), task(base));
  assert.match(execution, /Current obstacles[\s\S]*Correct the geometry/);
  assert.doesNotMatch(execution, /Your action needed/);
  const input = formatResearchOverview(overview(), task({ ...base,
    block_kind: 'missing_user_input', resume_when: 'Provide the intended charge and spin.' }));
  assert.match(input, /Your action needed[\s\S]*Provide the intended charge and spin/);
  const waiting = formatResearchOverview(overview(), task({ state: 'waiting', wait: { mode: 'all', job_count: 1 } }));
  assert.match(waiting, /Waiting for 1 job \(all must finish\)/);
  assert.doesNotMatch(waiting, /Your action needed/);
});

test('full result reads present complete scientific content and explicit supersession without raw protocol data', () => {
  const body = formatResearchDetail(readResponse(result({ subjects: { target_structure: 'art_4', calculated_structure: 'art_6' } }), { review_notices: [
    { code: 'result_superseded', used: 'result_1', superseded_by: 'result_2' },
  ], review_notice_count: 1 }));
  assert.match(body, /This result has been superseded by result_2/);
  assert.match(body, /Only screening is complete; no preferred pathway is established/);
  assert.match(body, /No transition state has been verified/);
  assert.match(body, /Inputs: art_1/);
  assert.match(body, /Cited records: art_2/);
  assert.match(body, /Check records: art_3/);
  assert.match(body, /Subject — target structure: art_4/);
  assert.match(body, /Subject — calculated structure: art_6/);
  assert.match(body, /Conformer ensemble · art_5/);
  assert.doesNotMatch(body, /schema_version|content_digest|"conclusion"|\{\s*"/);
  assert.throws(() => formatResearchDetail(readResponse(result(), { next_offset: 200 })), /incomplete/);
});

test('question reads distinguish research plan, current judgment, result summaries, notes and related questions', () => {
  const note = { schema_version: 'research-record/2', ref: 'note_2', origin: 'agent', title: 'Compare reaction pathways',
    node_id: 'node_1', content: 'No favored route is established.', references: ['result_1'], created_at: time };
  const detail = { node: { id: 'node_1', title: 'Compare reaction pathways', status: 'closed', updated_at: time,
    goal: 'Determine the preferred pathway.', plan: 'Compare both transition structures.', assessment_ref: 'note_2' },
    assessment: note, review_notices: [{ code: 'new_evidence_after_assessment', references: ['result_3'] }],
    results: [{ id: 'result_1', summary: 'Initial screening.', created_at: time, supersedes: null }],
    recent_notes: { total: 0, records: [] }, related_nodes: [{ id: 'node_2', title: 'Competing route', status: 'open' }],
    diagnostics: [], jobs: [], relations: [] };
  const body = formatResearchDetail(readResponse(detail));
  assert.match(body, /Question status: Ended/);
  assert.match(body, /Current judgment[\s\S]*No favored route is established/);
  assert.match(body, /Research plan[\s\S]*Compare both transition structures/);
  assert.match(body, /Result summary: Initial screening\.[\s\S]*Full result and caveats: \/research read result_1/);
  assert.match(body, /New evidence is available/);
  assert.match(body, /Competing route · \/research read node_2/);
  assert.doesNotMatch(body, /schema_version|assessment_ref|Research completed/);
  const selectedResult = formatResearchDetail(readResponse({ ...detail,
    node: { ...detail.node, assessment_ref: 'result_1', subjects: { target_structure: 'art_7', calculated_structure: 'art_8' } },
    assessment: result({ subjects: { target_structure: 'art_4', calculated_structure: 'art_6' } }),
  }));
  assert.match(selectedResult, /Research materials[\s\S]*Subject — target structure: art_7\nSubject — calculated structure: art_8/);
  assert.match(selectedResult, /Current judgment[\s\S]*No transition state has been verified\.[\s\S]*Inputs: art_1\nCited records: art_2\nCheck records: art_3\nSubject — target structure: art_4\nSubject — calculated structure: art_6/);
});

test('search labels excerpts and offers exact reads while question selection uses titles', () => {
  const found = { schema_version: 'research-search/2', total: 2, next_offset: 1, records: [
    { ref: 'note_2', title: 'Compare reaction pathways', kind: 'note', excerpt: 'Only preliminary evidence.', created_at: time },
  ] };
  const body = formatResearchSearch(found, 'reaction pathways');
  assert.match(body, /Search: reaction pathways · 2 matches/);
  assert.match(body, /Excerpts may omit context and caveats/);
  assert.match(body, /Excerpt: Only preliminary evidence\./);
  assert.match(body, /Read: \/research read note_2/);
  assert.match(body, /\/research search --offset 1 -- reaction pathways/);
  const questions = { schema_version: 'research-search/2', total: 1, next_offset: null, records: [
    { ref: 'node_1', title: 'Compare reaction pathways', kind: 'node', excerpt: 'Find the preferred pathway.', created_at: time },
  ] };
  assert.deepEqual(researchChoices(questions), [{ value: 'node_1', label: 'Compare reaction pathways', description: 'Research question · node_1' }]);
  assert.doesNotMatch(body, /schema_version|next_offset|ranking_reason/);
  const literal = 'Gaussian --opt --offset 9';
  const paged = formatResearchSearch(found, literal);
  const hint = paged.split('More matches: /research ')[1];
  assert.deepEqual(parseSlashCommand('research', hint).params, { query: literal, offset: 1 });
});
