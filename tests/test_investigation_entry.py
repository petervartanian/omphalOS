"""Exercise the subject-first workflow through the shipped event handlers."""

from __future__ import annotations

import pytest
from test_frontend_guards import run_scenario
from test_guided_frontend import GUIDED_SETUP

ENTRY_SETUP = GUIDED_SETUP + r"""
  state.datasets = [];
  state.sources = [];
  state.runs = [];
  run(`model.state = ${JSON.stringify(state)}; model.flow = newFlow(); model.run = null; model.selectedRun = ''; model.reviewDrafts = {}; renderGuided();`);
  const subject = 'Example Components LLC';
  const subjectDataset = {dataset_id: 'subject-example', label: subject, counts: {entities: 1}, synthetic: false};
  const nameOnlyDataset = {...subjectDataset, dataset_id: 'subject-name-only'};
  const freshSource = {snapshot_id: 'fresh-csl', source_id: 'csl', ingestion_method: 'official_https', fetched_at: new Date().toISOString(), record_count: 2};
  const entryRequests = [];
  let entryIntercept = async () => {};
  let failSource = false;
  let identityReport = {research_id: 'research-subject', dataset_id: subjectDataset.dataset_id, entity_id: 'entity-subject', query: subject, status: 'no_match', providers: [{id: 'gleif', label: 'GLEIF', status: 'no_match'}, {id: 'wikidata', label: 'Wikidata', status: 'no_match'}], candidates: []};
  fetchImplementation = async (url, options) => {
    const body = options?.body ? JSON.parse(options.body) : null;
    entryRequests.push({url, body});
    await entryIntercept(url, body);
    if (url === '/api/workflow/subject') {
      state.datasets.push(subjectDataset);
      return jsonResponse(subjectDataset);
    }
    if (url === '/api/state') return jsonResponse(state);
    if (url === '/api/workflow/identity-research') return jsonResponse(identityReport);
    if (url === '/api/workflow/identity-select') {
      assert.equal(body.candidate_id, null, 'This fixture continues with an unresolved name.');
      state.datasets.push(nameOnlyDataset);
      return jsonResponse(nameOnlyDataset);
    }
    if (url === '/api/sources/fetch') {
      if (failSource) return {...jsonResponse({error: 'The official source could not be downloaded.'}), ok: false, status: 502};
      state.sources.push(freshSource);
      return jsonResponse(freshSource);
    }
    if (url === '/api/workflow/plan') {
      const snapshot = state.sources.find(item => item.snapshot_id === body.watchlist_snapshot_id);
      return jsonResponse({...planned(), can_run: body.goal_id !== 'counterparty_screening' || Boolean(snapshot), source_status: snapshot ? {...snapshot, selected: true} : {selected: false}});
    }
    if (url === '/api/workflow/approve') return jsonResponse({approval: approvedSources});
    if (url === '/api/workflow/run') return jsonResponse({run_id: 'subject-run'});
    if (url === '/api/runs/subject-run') {
      const execution = entryRequests.find(item => item.url === '/api/workflow/run').body;
      return jsonResponse({...runA, latest_review: null, manifest: {...runA.manifest, run_id: 'subject-run'}, case: {...runA.case, ...execution}, dataset_metadata: state.datasets.find(item => item.dataset_id === execution.dataset_id), analysis: {...runA.analysis, findings: [finding()]}});
    }
    throw new Error('Unexpected request: ' + url);
  };
  async function approveAndRun() {
    const previousRuns = entryRequests.filter(item => item.url === '/api/workflow/run').length;
    assert.equal(run('model.flow.cubeFace'), 1);
    click(flowButton('approve-sources'));
    await settle();
    assert.equal(run('model.flow.cubeFace'), 2);
    assert.equal(entryRequests.filter(item => item.url === '/api/workflow/run').length, previousRuns);
    click(flowButton('run'));
    await settle();
  }
  function subjectForm(name) {
    const form = new Element('#flow-subject-form');
    form.id = 'flow-subject-form';
    form.fields = {name};
    form.elements = {name: {value: name}};
    return form;
  }
  function submitSubject(name = subject) {
    const event = {target: subjectForm(name), defaultPrevented: false, preventDefault() {this.defaultPrevented = true;}};
    main.emit('submit', event);
    return event;
  }
"""


def run_entry(scenario: str) -> None:
    run_scenario(ENTRY_SETUP + scenario)


def test_screening_brief_distinguishes_no_candidates_from_unexecuted_check() -> None:
    run_entry(r"""
  state.sources.push(freshSource);
  run(`model.state = ${JSON.stringify(state)};`);
  const retained = {case: {watchlist_snapshot_id: freshSource.snapshot_id}, analysis: {findings: [finding()], coverage: [{investigation_id: 'screening_candidates', status: 'executed', records_evaluated: 1, findings_count: 0}]}};
  run(`model.run = ${JSON.stringify(retained)};`);
  const completed = run('flowScreeningBrief(model.run)');
  assert.match(completed, /No name or identifier candidates returned/);
  assert.match(completed, /Checked 1 record against 2 entries/);
  assert.match(completed, /does not confirm identity or establish clearance/);
  retained.analysis.coverage[0] = {...retained.analysis.coverage[0], status: 'not_evaluable', reason: '<source unavailable>'};
  run(`model.run = ${JSON.stringify(retained)};`);
  const unavailable = run('flowScreeningBrief(model.run)');
  assert.match(unavailable, /could not be completed/);
  assert.match(unavailable, /&lt;source unavailable&gt;/);
  assert.ok(!unavailable.includes('No name or identifier candidates'));
""")


def test_findings_present_screening_before_gaps_and_keep_original_evidence_indices() -> (
    None
):
    run_entry(r"""
  state.sources.push(freshSource);
  const retained = {dataset_metadata: {label: '<Submitted subject>'}, case: {watchlist_snapshot_id: freshSource.snapshot_id}, analysis: {findings: [finding('missingA'), {...finding('candidateB'), investigation_id: 'screening_candidates', title: 'Candidate to examine'}], coverage: [{investigation_id: 'screening_candidates', status: 'executed', records_evaluated: 1, findings_count: 1}]}};
  run(`model.state = ${JSON.stringify(state)}; model.flow.stage = 'review'; model.run = ${JSON.stringify(retained)};`);
  const markup = run('flowFindingsView()');
  assert.match(markup, /&lt;Submitted subject&gt;/);
  assert.match(markup, /1 candidate for identity review/);
  assert.ok(markup.indexOf('Candidate to examine') < markup.indexOf('Missing context'));
  assert.match(markup, /data-index="1"[^>]*>[\s\S]*?Candidate to examine/);
  assert.match(markup, /data-flow="findings-reviewed">Mark results reviewed/);
""")


def test_name_only_continuation_requires_approval_before_screening_and_review() -> None:
    run_entry(r"""
  assert.ok(main.innerHTML.includes('id="flow-subject-form"'));
  const event = submitSubject();
  assert.equal(event.defaultPrevented, true);
  await settle();
  assert.equal(run('model.flow.stage'), 'identity');
  assert.ok(!entryRequests.some(item => item.url === '/api/workflow/run'));
  click(flowButton('identity-skip'));
  await settle();
  const intake = entryRequests.filter(item => item.url === '/api/workflow/subject');
  assert.equal(intake.length, 1);
  assert.deepEqual(intake[0].body, {name: subject});
  const acquisition = entryRequests.filter(item => item.url === '/api/sources/fetch');
  assert.equal(acquisition.length, 1);
  assert.deepEqual(acquisition[0].body, {source_id: 'csl'}, 'Public-list acquisition must not transmit the subject name.');
  assert.equal(entryRequests.filter(item => item.url === '/api/workflow/run').length, 0);
  await approveAndRun();
  const executions = entryRequests.filter(item => item.url === '/api/workflow/run');
  assert.equal(executions.length, 1);
  assert.equal(executions[0].body.dataset_id, nameOnlyDataset.dataset_id);
  assert.equal(executions[0].body.goal_id, 'counterparty_screening');
  assert.equal(executions[0].body.watchlist_snapshot_id, freshSource.snapshot_id);
  assert.equal(executions[0].body.plan_id, 'planA');
  assert.equal(run('model.flow.stage'), 'review');
  assert.equal(run('model.selectedRun'), 'subject-run');
  assert.equal(run('Object.keys(model.reviewDrafts).length'), 0);
  assert.equal(run('model.run.latest_review'), null);
  assert.ok(!entryRequests.some(item => item.url.endsWith('/review')));
  assert.equal(run('model.flow.cubeFace'), 3);
  click(flowButton('review-step', {index: '0'}));
  assert.ok(main.innerHTML.includes('class="finding-detail"'));
  assert.ok(!main.innerHTML.includes('name="disposition"'));
  assert.equal(run('Object.keys(model.reviewDrafts).length'), 0);
  assert.equal(run('flowResultsReviewed(model.run)'), false);
  click(flowButton('findings-reviewed'));
  assert.equal(run('flowResultsReviewed(model.run)'), true);
  assert.ok(main.innerHTML.includes('data-review-scope="case"'));
  assert.ok(!/name="decision"[^>]*checked/.test(main.innerHTML));
  assert.ok(!/name="acknowledge_limitations"[^>]*checked/.test(main.innerHTML));
  assert.notEqual(notice.className, 'notice error');
""")


@pytest.mark.parametrize("phase", ["subject", "source", "plan"])
def test_navigation_during_subject_workflow_prevents_later_execution(
    phase: str,
) -> None:
    run_entry(r"""
  const stoppedUrl = {subject: '/api/workflow/subject', source: '/api/sources/fetch', plan: '/api/workflow/plan'}[PHASE];
  let release;
  let waiting = false;
  entryIntercept = async (url) => {
    if (url !== stoppedUrl || waiting) return;
    waiting = true;
    await new Promise(resolve => {release = resolve;});
  };
  submitSubject();
  if (PHASE !== 'subject') {
    await settle();
    assert.equal(run('model.flow.stage'), 'identity');
    click(flowButton('identity-skip'));
  }
  await until(() => waiting);
  const requestCount = entryRequests.length;
  navigate('data');
  release();
  await settle();
  assert.equal(run('model.page'), 'data');
  assert.ok(!entryRequests.some(item => item.url === '/api/workflow/run'));
  assert.ok(!entryRequests.slice(requestCount).some(item => item.url === '/api/sources/fetch'), 'Leaving the workflow must prevent a later source download.');
  assert.equal(run('Object.keys(model.reviewDrafts).length'), 0);
  assert.notEqual(notice.className, 'notice error');
""".replace("PHASE", repr(phase)))


def test_source_failure_preserves_subject_records_for_retry() -> None:
    run_entry(r"""
  failSource = true;
  submitSubject();
  await settle();
  click(flowButton('identity-skip'));
  await settle();
  assert.equal(run('model.flow.datasetId'), nameOnlyDataset.dataset_id);
  assert.equal(run('flowDataset().label'), subject);
  assert.equal(run('model.flow.goalId'), 'counterparty_screening');
  assert.equal(run('model.flow.busyStep'), '');
  assert.equal(run('model.operation'), false);
  assert.equal(notice.className, 'notice error');
  assert.ok(!entryRequests.some(item => item.url === '/api/workflow/run'));
  failSource = false;
  click(flowButton('investigate-dataset', {id: nameOnlyDataset.dataset_id}));
  await settle();
  assert.equal(entryRequests.filter(item => item.url === '/api/workflow/subject').length, 1, 'Retry should reuse the retained subject, not create it again.');
  assert.equal(entryRequests.filter(item => item.url === '/api/workflow/run').length, 0);
  assert.equal(run('model.flow.stage'), 'plan');
  assert.equal(run('model.flow.cubeFace'), 1);
""")


@pytest.mark.parametrize("kind", ["fresh_official", "stale_official", "fresh_manual"])
def test_saved_records_reuse_only_a_fresh_official_source_by_default(kind: str) -> None:
    run_entry(r"""
  const retained = {...freshSource, snapshot_id: 'retained-csl', ingestion_method: KIND === 'fresh_manual' ? 'manual_import' : 'official_https', fetched_at: KIND === 'stale_official' ? '2001-01-01T00:00:00Z' : new Date().toISOString()};
  state.datasets.push(subjectDataset);
  state.sources.push(retained);
  run(`model.state = ${JSON.stringify(state)}; renderGuided();`);
  click(flowButton('investigate-dataset', {id: subjectDataset.dataset_id}));
  await settle();
  const downloads = entryRequests.filter(item => item.url === '/api/sources/fetch');
  assert.equal(downloads.length, KIND === 'fresh_official' ? 0 : 1);
  const executions = entryRequests.filter(item => item.url === '/api/workflow/run');
  assert.equal(executions.length, 0);
  assert.equal(run('model.flow.planInputs.watchlist_snapshot_id'), KIND === 'fresh_official' ? retained.snapshot_id : freshSource.snapshot_id);
  assert.equal(run('model.flow.stage'), 'plan');
  assert.equal(run('model.flow.cubeFace'), 1);
""".replace("KIND", repr(kind)))


@pytest.mark.parametrize("preserve", ["explicit_source", "historical_date"])
def test_preparation_preserves_deliberate_source_or_date(preserve: str) -> None:
    run_entry(r"""
  const retained = {...freshSource, snapshot_id: 'historical-csl', fetched_at: '2020-01-01T00:00:00Z'};
  state.datasets.push(subjectDataset);
  state.sources.push(retained);
  const assessmentDate = PRESERVE === 'historical_date' ? '2020-01-02' : run('dateToday()');
  run(`model.state = ${JSON.stringify(state)}; Object.assign(model.flow, {goalId: 'counterparty_screening', goalInferred: false, snapshotId: 'historical-csl', sourcePolicy: ${JSON.stringify(PRESERVE === 'explicit_source' ? 'explicit' : 'automatic')}, asOf: ${JSON.stringify(assessmentDate)}}); renderGuided();`);
  click(flowButton('investigate-dataset', {id: subjectDataset.dataset_id}));
  await settle();
  assert.ok(!entryRequests.some(item => item.url === '/api/sources/fetch'));
  assert.equal(entryRequests.filter(item => item.url === '/api/workflow/run').length, 0);
  const preparation = entryRequests.filter(item => item.url === '/api/workflow/plan').at(-1);
  assert.equal(preparation.body.watchlist_snapshot_id, retained.snapshot_id);
  assert.equal(preparation.body.as_of, assessmentDate);
  assert.equal(preparation.body.goal_id, 'counterparty_screening');
""".replace("PRESERVE", repr(preserve)))


def test_saved_work_picker_offers_valid_investigations_and_skips_invalid_records() -> (
    None
):
    run_entry(r"""
  state.runs = [
    {run_id: 'invalid-newest', case_id: 'Broken case', status: 'invalid', created_at: '2026-10-15T12:00:00Z', verification_status: 'failed'},
    {run_id: 'ready-review', case_id: 'Retained inquiry', status: 'awaiting_review', created_at: '2026-10-14T12:00:00Z', findings_count: 2},
    {run_id: 'already-reviewed', case_id: 'Closed inquiry', status: 'review_recorded', created_at: '2026-10-13T12:00:00Z', findings_count: 0},
  ];
  state.datasets = [{dataset_id: 'broken-records', status: 'invalid'}, subjectDataset];
  run(`model.state = ${JSON.stringify(state)}; renderGuided();`);
  assert.ok(!main.innerHTML.includes('data-flow="resume"'), 'Individual retained cases belong in the picker, not the default entry.');
  click(flowButton('open-work'));
  assert.equal(node('#evidence-dialog').showModalCount, 1);
  const buttons = [...node('#dialog-content').innerHTML.matchAll(/<button\b[^>]*>/g)].map(item => item[0]);
  assert.ok(buttons.some(item => item.includes('data-flow="resume"') && item.includes('data-id="ready-review"')));
  assert.ok(buttons.some(item => item.includes('data-flow="resume"') && item.includes('data-id="already-reviewed"')));
  assert.ok(!buttons.some(item => item.includes('data-flow="resume"') && item.includes('data-id="invalid-newest"')));
  assert.ok(!buttons.some(item => item.includes('data-flow="investigate-dataset"') && item.includes('data-id="broken-records"')));
  assert.ok(buttons.some(item => item.includes('data-flow="investigate-dataset"') && item.includes('data-id="subject-example"')));
  assert.deepEqual(entryRequests, []);
""")


@pytest.mark.parametrize("completed", [1, 2])
def test_resuming_returns_to_the_first_incomplete_assessment(completed: int) -> None:
    run_entry(r"""
  const findings = [finding('first'), finding('second')];
  const retained = {...runA, latest_review: null, analysis: {...runA.analysis, findings}, case: {...runA.case, dataset_id: subjectDataset.dataset_id}};
  const row = id => ({finding_id: id, disposition: 'follow_up', rationale: 'The retained evidence requires further verification.', unknowns: ['The missing source documentation is not yet available.'], alternatives: ['The source export may omit an otherwise available record.'], falsifiers: ['A verified record establishing the missing context.']});
  const draft = {reviewer: 'Retained Reviewer', summary: '', acknowledge_limitations: false, findings: findings.slice(0, COMPLETED).map(item => row(item.finding_id))};
  run(`model.reviewDrafts.runA = ${JSON.stringify(draft)};`);
  fetchImplementation = async (url) => {
    assert.equal(url, '/api/runs/runA');
    return jsonResponse(retained);
  };
  click(flowButton('resume', {id: 'runA'}));
  await settle();
  assert.equal(run('model.flow.reviewIndex'), COMPLETED);
  assert.equal(run('model.flow.stage'), 'review');
  assert.equal(run('model.reviewDrafts.runA.reviewer'), draft.reviewer);
  assert.equal(run('model.reviewDrafts.runA.findings[0].rationale'), draft.findings[0].rationale);
""".replace("COMPLETED", str(completed)))


def test_duplicate_subject_submission_cannot_start_a_second_intake() -> None:
    run_entry(r"""
  let release;
  let waiting = false;
  entryIntercept = async url => {
    if (url !== '/api/workflow/subject') return;
    waiting = true;
    await new Promise(resolve => {release = resolve;});
  };
  submitSubject();
  await until(() => waiting);
  submitSubject('A different subject');
  assert.equal(entryRequests.filter(item => item.url === '/api/workflow/subject').length, 1);
  release();
  await settle();
  assert.equal(run('model.flow.stage'), 'identity');
  click(flowButton('identity-skip'));
  await settle();
  assert.equal(entryRequests.filter(item => item.url === '/api/workflow/run').length, 0);
  assert.equal(run('model.flow.cubeFace'), 1);
  assert.equal(run('flowDataset().label'), subject);
""")


def test_subject_draft_survives_cube_navigation_and_is_escaped() -> None:
    run_entry(r"""
  const typed = 'Example <script>named()</script> & "Partners"';
  const form = subjectForm(typed);
  const control = new Element('#flow-subject-name');
  control.id = 'flow-subject-name';
  control.name = 'name';
  control.value = typed;
  control.closest = selector => selector === '#flow-subject-form' || selector === 'form' ? form : null;
  main.emit('input', {target: control});
  assert.equal(run('model.flow.subjectName'), typed);
  click(flowButton('cube', {face: '3'}));
  click(flowButton('overview'));
  run('renderGuided();');
  assert.equal(run('model.flow.subjectName'), typed);
  assert.ok(main.innerHTML.includes('value="Example &lt;script&gt;named()&lt;/script&gt; &amp; &quot;Partners&quot;"'));
  assert.ok(!main.innerHTML.includes('<script>named()</script>'));
  assert.equal(entryRequests.length, 0);
""")


@pytest.mark.parametrize("phase", ["source", "plan"])
def test_available_stage_inspection_does_not_cancel_preparation_or_steal_the_view(
    phase: str,
) -> None:
    run_entry(r"""
  const stoppedUrl = {source: '/api/sources/fetch', plan: '/api/workflow/plan', run: '/api/workflow/run'}[PHASE];
  let release;
  let waiting = false;
  let scrollCount = 0;
  node('.object-surface').scrollIntoView = () => {scrollCount += 1;};
  entryIntercept = async url => {
    if (url !== stoppedUrl || waiting) return;
    waiting = true;
    await new Promise(resolve => {release = resolve;});
  };
  submitSubject();
  await settle();
  assert.equal(run('model.flow.stage'), 'identity');
  scrollCount = 0;
  click(flowButton('identity-skip'));
  await until(() => waiting);
  click(flowButton('cube', {face: '1'}));
  assert.equal(run('model.flow.inspectionFace'), 1);
  assert.equal(scrollCount, 1, 'The selected working surface is brought into view.');
  release();
  await settle();
  assert.equal(entryRequests.filter(item => item.url === '/api/workflow/run').length, 0);
  assert.equal(run('model.selectedRun'), '');
  assert.equal(run('model.flow.stage'), 'plan');
  assert.equal(run('model.flow.cubeFace'), 1);
  assert.equal(run('model.flow.inspectionFace'), 1);
  assert.equal(run('model.flow.sourceRetry'), false);
  assert.equal(run('model.flow.autoRunning'), false);
  assert.equal(scrollCount, 1, 'Completion must not scroll over an explicitly inspected face.');
  assert.notEqual(notice.className, 'notice error');
""".replace("PHASE", repr(phase)))


@pytest.mark.parametrize("phase", ["subject", "source", "plan"])
def test_leaving_and_returning_to_route_cancels_later_automatic_stages(
    phase: str,
) -> None:
    run_entry(r"""
  const stoppedUrl = {subject: '/api/workflow/subject', source: '/api/sources/fetch', plan: '/api/workflow/plan'}[PHASE];
  let release;
  let waiting = false;
  entryIntercept = async url => {
    if (url !== stoppedUrl || waiting) return;
    waiting = true;
    await new Promise(resolve => {release = resolve;});
  };
  submitSubject();
  if (PHASE !== 'subject') {
    await settle();
    assert.equal(run('model.flow.stage'), 'identity');
    click(flowButton('identity-skip'));
  }
  await until(() => waiting);
  const requestCount = entryRequests.length;
  navigate('data');
  navigate('investigate');
  const priorStage = run('model.flow.cubeFace');
  click(flowButton('cube', {face: '5'}));
  assert.equal(run('model.flow.cubeFace'), priorStage, 'Unavailable Package stays blocked after route navigation.');
  click(flowButton('cube', {face: '0'}));
  release();
  await settle();
  assert.ok(!entryRequests.some(item => item.url === '/api/workflow/run'));
  assert.ok(!entryRequests.slice(requestCount).some(item => item.url === '/api/sources/fetch'));
  assert.equal(run('model.flow.cubeFace'), 0);
  assert.equal(run('model.flow.autoRunning'), false);
  assert.equal(run('model.selectedRun'), '');
  assert.notEqual(notice.className, 'notice error');
""".replace("PHASE", repr(phase)))


@pytest.mark.parametrize("change", ["inputs", "flow", "run"])
def test_changed_investigation_ownership_cancels_automatic_stages(change: str) -> None:
    run_entry(r"""
  let release;
  let waiting = false;
  entryIntercept = async url => {
    if (url !== '/api/sources/fetch') return;
    waiting = true;
    await new Promise(resolve => {release = resolve;});
  };
  submitSubject();
  await settle();
  click(flowButton('identity-skip'));
  await until(() => waiting);
  if (CHANGE === 'inputs') changeControl('flow-as-of', '2020-01-01');
  if (CHANGE === 'flow') run('model.flow = newFlow(); renderGuided();');
  if (CHANGE === 'run') run('model.selectedRun = "different-run";');
  release();
  await settle();
  assert.ok(!entryRequests.some(item => item.url === '/api/workflow/run'));
  assert.notEqual(run('model.selectedRun'), 'subject-run');
  assert.notEqual(notice.className, 'notice error');
""".replace("CHANGE", repr(change)))


def test_automatic_progress_announces_the_current_stage_without_manual_run_prompt() -> (
    None
):
    run_entry(r"""
  let release;
  let waiting = false;
  entryIntercept = async url => {
    if (url !== '/api/sources/fetch') return;
    waiting = true;
    await new Promise(resolve => {release = resolve;});
  };
  submitSubject();
  await settle();
  click(flowButton('identity-skip'));
  await until(() => waiting);
  assert.equal(notice.className, 'notice busy');
  assert.match(notice.textContent, /Downloading the official screening list/);
  assert.ok(!notice.textContent.includes('run when ready'));
  release();
  await settle();
""")
