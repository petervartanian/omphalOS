"""Recovery and navigation through the real guided frontend handlers."""

from __future__ import annotations

import pytest
from test_case_review_frontend import run_case_review
from test_guided_frontend import run_guided
from test_identity_frontend import run_identity


@pytest.mark.parametrize("change", ["goal", "date", "source", "route", "restart"])
def test_abandoned_plan_failure_cannot_replace_the_current_notice(change: str) -> None:
    run_guided(r"""
  let release;
  fetchImplementation = async url => {
    assert.equal(url, '/api/workflow/plan');
    return new Promise(resolve => {release = resolve;});
  };
  click(flowButton('plan'));
  if (CHANGE === 'goal') click(flowButton('goal', {goal: 'data_readiness'}));
  if (CHANGE === 'date') changeControl('flow-as-of', '2025-01-03');
  if (CHANGE === 'source') changeControl('flow-source', 'other-source');
  if (CHANGE === 'route') navigate('data');
  if (CHANGE === 'restart') click(flowButton('restart'));
  run("announce('Current investigation notice.');");
  release({...jsonResponse({error: 'An obsolete request failed.'}), ok: false, status: 503});
  await settle();
  assert.equal(notice.textContent, 'Current investigation notice.');
  assert.notEqual(notice.className, 'notice error');
  assert.equal(run('model.flow.plan'), null);
  assert.equal(run('model.operation'), false);
""".replace("CHANGE", repr(change)))


def test_a_current_plan_failure_is_reported_and_can_be_retried() -> None:
    run_guided(r"""
  let attempts = 0;
  fetchImplementation = async url => {
    assert.equal(url, '/api/workflow/plan');
    attempts += 1;
    return attempts === 1
      ? {...jsonResponse({error: 'Records are temporarily unavailable.'}), ok: false, status: 503}
      : jsonResponse(planned());
  };
  click(flowButton('plan'));
  await settle();
  assert.equal(notice.className, 'notice error');
  assert.equal(notice.textContent, 'Records are temporarily unavailable.');
  assert.ok(main.innerHTML.includes('data-flow="plan"'));
  click(flowButton('plan'));
  await settle();
  assert.equal(run('model.flow.plan.can_run'), true);
  assert.equal(attempts, 2);
""")


@pytest.mark.parametrize("failed", [False, True])
def test_old_source_response_cannot_change_a_new_investigation(failed: bool) -> None:
    run_guided(r"""
  run("Object.assign(model.flow, {goalId: 'counterparty_screening', snapshotId: 'original-source'});");
  let release;
  const requests = [];
  fetchImplementation = async url => {
    requests.push(url);
    assert.equal(url, '/api/sources/fetch');
    return new Promise(resolve => {release = resolve;});
  };
  click(flowButton('fetch-run'));
  click(flowButton('restart'));
  run("model.flow.subjectName = 'New subject'; announce('Ready for the new subject.');");
  release(FAILED ? {...jsonResponse({error: 'Old list request failed.'}), ok: false, status: 503} : jsonResponse({snapshot_id: 'obsolete-source'}));
  await settle();
  assert.deepEqual(requests, ['/api/sources/fetch']);
  assert.equal(run('model.flow.subjectName'), 'New subject');
  assert.equal(run('model.flow.snapshotId'), '');
  assert.equal(run('model.flow.stage'), 'goal');
  assert.equal(notice.textContent, 'Ready for the new subject.');
""".replace("FAILED", str(failed).lower()))


def test_a_late_inventory_failure_does_not_disrupt_the_new_case() -> None:
    run_guided(r"""
  let release;
  fetchImplementation = async url => {
    if (url === '/api/sources/fetch') return jsonResponse({snapshot_id: 'downloaded-source'});
    assert.equal(url, '/api/state');
    return new Promise(resolve => {release = resolve;});
  };
  click(flowButton('fetch'));
  await until(() => Boolean(release));
  click(flowButton('restart'));
  run("announce('Ready for another case.');");
  release({...jsonResponse({error: 'Old inventory refresh failed.'}), ok: false, status: 503});
  await settle();
  assert.equal(run('model.flow.stage'), 'goal');
  assert.equal(run('model.flow.snapshotId'), '');
  assert.equal(notice.textContent, 'Ready for another case.');
""")


@pytest.mark.parametrize("failure", ["network", "server"])
def test_temporary_evidence_failure_preserves_the_page_and_retries_the_requested_offset(
    failure: str,
) -> None:
    run_case_review(r"""
  const rows = Array.from({length: 40}, (_, index) => ({kind: 'record', table: 'shipments', id: 'S' + index, record: {shipment_id: 'S' + index}}));
  run(`Object.assign(model.flow, {findingIndex: 1, inspectionFace: 3, cubeFace: 3, surfaceOpen: true}); guidedReviewUi('volume-B').evidence = ${JSON.stringify({offset: 0, total: 41, rows})};`);
  let release;
  const requests = [];
  fetchImplementation = async url => {
    requests.push(url);
    assert.match(url, /offset=40$/);
    if (requests.length === 1) {
      await new Promise(resolve => {release = resolve;});
      if (FAILURE === 'network') throw new Error('Offline.');
      return {...jsonResponse({error: 'The server is temporarily unavailable.'}), ok: false, status: 503};
    }
    return jsonResponse({offset: 40, total: 41, rows: [{kind: 'record', table: 'shipments', id: 'LAST', record: {shipment_id: 'LAST'}}]});
  };
  const pending = run('loadFindingEvidence(model.run.analysis.findings[1], 40)');
  assert.match(node('#finding-evidence-records').innerHTML, /data-offset="40" disabled>Next/);
  assert.equal(node('#finding-evidence-records').getAttribute('aria-busy'), 'true');
  release();
  await pending;
  const markup = node('#finding-evidence-records').innerHTML;
  assert.ok(markup.includes('>S0<'), 'A connection failure must not erase the last verified page.');
  assert.match(markup, /data-offset="40">Retry records/);
  assert.equal(node('#finding-evidence-records').getAttribute('aria-busy'), 'false');
  click(flowButton('finding-records', {id: 'volume-B', offset: '40'}));
  await until(() => !run('guidedReviewUi("volume-B").evidenceLoading'));
  assert.equal(requests.length, 2);
  assert.equal(run('guidedReviewUi("volume-B").evidence.offset'), 40);
  assert.ok(node('#finding-evidence-records').innerHTML.includes('>LAST<'));
  assert.equal(run('Object.keys(model.reviewDrafts).length'), 0);
""".replace("FAILURE", repr(failure)))


def test_evidence_integrity_failure_removes_outcomes_and_blocks_a_decision() -> None:
    run_case_review(r"""
  const draft = {schema_version: '2.1', run_id: 'runA', reviewer: 'Analyst Example', decision: 'keep_open', summary: 'Waiting for the underlying shipment record.', scope_finding_ids: ['context-A', 'volume-B'], acknowledge_limitations: true};
  run(`Object.assign(model.flow, {findingIndex: 1, inspectionFace: 3, cubeFace: 3, surfaceOpen: true}); model.reviewDrafts.runA = ${JSON.stringify(draft)}; guidedReviewUi('volume-B').evidence = {offset: 0, total: 41, rows: [{kind: 'record', table: 'shipments', id: 'S0', record: {shipment_id: 'S0'}}]};`);
  let requests = 0;
  fetchImplementation = async () => {
    requests += 1;
    return {...jsonResponse({error: 'Run integrity failed. Evidence cannot be presented as verified.'}), ok: false, status: 409};
  };
  await run('loadFindingEvidence(model.run.analysis.findings[1], 40)');
  assert.equal(run('model.run.verification.ok'), false);
  assert.equal(run('guidedReviewUi("volume-B").evidence'), null);
  assert.ok(!main.innerHTML.includes(caseFindings[1].observation));
  assert.ok(!run('flowReviewView()').includes('name="decision"'));
  assert.equal(run('flowStageAccess(4)'), false);
  assert.equal(run('flowStageAccess(5)'), false);
  assert.equal(run('model.reviewDrafts.runA.summary'), draft.summary);
  await run('loadFindingEvidence(model.run.analysis.findings[1], 40)');
  assert.equal(requests, 1);
""")


def test_saved_runs_use_the_retained_dataset_even_after_a_case_changes() -> None:
    run_guided(r"""
  run(`model.state.datasets = [{dataset_id: 'original-records', label: 'Original <subject>'}, {dataset_id: 'replacement-records', label: 'Unrelated replacement'}]; model.state.cases = [{case_id: 'revised-case', dataset_id: 'replacement-records'}]; model.state.runs = [{run_id: 'retained-run', case_id: 'revised-case', dataset_id: 'original-records', findings_count: 2}];`);
  assert.equal(run('savedRunTitle(model.state.runs[0])'), 'Original <subject>');
  assert.match(run('savedWorkView()'), /data-id="retained-run"><span class="saved-work-name">Original &lt;subject&gt;/);
  run("model.state.datasets = model.state.datasets.filter(item => item.dataset_id !== 'original-records');");
  assert.equal(run('savedRunTitle(model.state.runs[0])'), 'original-records');
""")


def test_reopening_an_unassessed_case_starts_with_its_findings() -> None:
    run_case_review(r"""
  fetchImplementation = async url => {assert.equal(url, '/api/runs/runA'); return jsonResponse(retainedCase);};
  click(flowButton('resume', {id: 'runA'}));
  await settle();
  assert.equal(run('model.flow.cubeFace'), 3);
  assert.equal(run('model.flow.stage'), 'review');
  assert.ok(main.innerHTML.includes('Open findings'));
  assert.equal(run('Object.keys(model.reviewDrafts).length'), 0);
""")


def test_new_and_open_are_available_without_losing_an_unrecorded_decision() -> None:
    run_case_review(r"""
  editCaseReview({reviewer: 'Analyst Example', decision: 'keep_open', summary: 'Waiting for the source invoice.'});
  assert.equal((run('flowGuide()').match(/data-flow="restart"/g) || []).length, 1);
  assert.equal((run('flowGuide()').match(/data-flow="open-work"/g) || []).length, 1);
  click(flowButton('open-work'));
  assert.equal(readCaseDraft().summary, 'Waiting for the source invoice.');
  click(flowButton('restart'));
  assert.equal(readCaseDraft().summary, 'Waiting for the source invoice.');
  assert.equal(run('model.flow.stage'), 'goal');
  assert.ok(node('#flow-subject-name').focusCount > 0);
""")


def test_import_has_one_file_control_and_keeps_format_help_in_the_information_dialog() -> (
    None
):
    run_guided(r"""
  click(flowButton('add-records'));
  assert.ok(main.innerHTML.includes('Choose records <span>CSV or JSON</span>'));
  assert.equal((main.innerHTML.match(/id="flow-vendor-file"/g) || []).length, 1);
  assert.equal((main.innerHTML.match(/data-flow="open-work"/g) || []).length, 1);
  assert.ok(!main.innerHTML.includes('data-flow="choose-file"'));
  assert.ok(!main.innerHTML.includes('Table JSON files contain arrays'));
  click(flowButton('import-info'));
  const help = node('#dialog-content').innerHTML;
  assert.ok(help.includes('Counterparty CSV.'));
  assert.ok(help.includes('20 MiB'));
  assert.ok(help.includes('dataset.json'));
  assert.ok(help.includes('48 MiB'));
  assert.ok(help.includes('local workspace'));
  assert.ok(!help.includes('<form'));
""")


@pytest.mark.parametrize(
    "state", ["import", "source_retry", "busy", "missing_controls"]
)
def test_back_to_overview_falls_back_to_a_visible_action_or_stage(state: str) -> None:
    run_guided(r"""
  run("Object.assign(model.flow, {stage: 'data', cubeFace: 0, surfaceOpen: true, preview: null});");
  if (STATE === 'source_retry') run("Object.assign(model.flow, {stage: 'plan', sourceRetry: true});");
  if (STATE === 'busy') run("model.flow.busyStep = 'Preparing the checks…';");
  const action = flowButton(STATE === 'source_retry' ? 'investigate-dataset' : 'choose-file');
  const stage = flowButton('cube', {face: '0'});
  const querySelector = document.querySelector;
  document.querySelector = selector => {
    // Model absence in the rendered overview; the shared adapter otherwise
    // invents nodes for every selector, concealing this focus regression.
    if (selector.includes('[data-flow="focus-step"]') || selector.includes('#flow-subject-name')) return null;
    if (selector.includes('.object-heading')) return ['import', 'source_retry'].includes(STATE) ? action : null;
    if (selector.includes('.cube-controls')) return STATE === 'missing_controls' ? null : stage;
    return querySelector(selector);
  };
  click(flowButton('overview'));
  assert.equal(run('model.flow.surfaceOpen'), false);
  if (STATE === 'import') assert.ok(main.innerHTML.includes('data-flow="choose-file">Choose files'));
  if (STATE === 'source_retry') assert.ok(main.innerHTML.includes('Retry screening'));
  const target = ['import', 'source_retry'].includes(STATE) ? action : STATE === 'busy' ? stage : main;
  assert.equal(target.focusCount, 1, 'Back must focus an existing visible control, or the main region.');
  assert.equal(node('.object-surface').focusCount, 0, 'The now-hidden form must not receive focus.');
""".replace("STATE", repr(state)))


def test_file_picker_is_focused_before_opening_so_cancel_keeps_a_stable_target() -> (
    None
):
    run_guided(r"""
  run('model.flow = newFlow();');
  const input = node('#flow-vendor-file');
  const events = [];
  input.focus = () => {events.push('focus');};
  input.click = () => {events.push('picker');};
  const requests = [];
  fetchImplementation = async url => {requests.push(url); throw new Error('Canceling a picker must not start an import.');};
  click(flowButton('choose-file'));
  assert.deepEqual(events, ['focus', 'picker']);
  assert.equal(run('model.flow.surfaceOpen'), true);
  assert.equal(run('model.flow.stage'), 'data');
  assert.ok(main.innerHTML.includes('id="flow-vendor-file"'));
  assert.deepEqual(requests, []);
""")


@pytest.mark.parametrize("multiple", [False, True])
def test_linked_import_uses_a_readable_title_without_changing_files_or_identifiers(
    multiple: bool,
) -> None:
    run_guided(r"""
  run('model.flow = newFlow();');
  const original = '{"tables":{"entities":[{"entity_id":"E1","name":"Named in the records"}],"payments":[]}}';
  const control = fileControl(MULTIPLE ? 'entities.csv' : 'Quarterly_<ledger>-2026.JSON', original);
  if (MULTIPLE) control.files.push(fileControl('payments.csv', 'payment_id,shipment_id,date,amount,ccy\n').files[0]);
  const originalNames = control.files.map(file => file.name);
  const expectedLabel = MULTIPLE ? 'Linked records' : 'Quarterly <ledger> 2026';
  const dataset = {dataset_id: 'server-generated-record-id', label: expectedLabel, counts: {entities: 1, payments: 2}};
  let imported;
  fetchImplementation = async (url, options) => {
    const body = options?.body ? JSON.parse(options.body) : null;
    if (url === '/api/datasets/import') {
      imported = body;
      state.datasets.push(dataset);
      return jsonResponse(dataset);
    }
    if (url === '/api/state') return jsonResponse(state);
    if (url === '/api/workflow/plan') {
      assert.equal(body.dataset_id, dataset.dataset_id);
      return jsonResponse(planned());
    }
    if (url === '/api/workflow/run') {
      assert.equal(body.dataset_id, dataset.dataset_id);
      return jsonResponse({run_id: 'imported-run'});
    }
    if (url === '/api/runs/imported-run') return jsonResponse({...runA, latest_review: null, manifest: {...runA.manifest, run_id: 'imported-run'}, case: {...runA.case, dataset_id: dataset.dataset_id}, dataset_metadata: dataset});
    throw new Error('Unexpected request: ' + url);
  };
  main.emit('change', {target: control});
  await settle();
  assert.deepEqual(Object.keys(imported).sort(), ['files', 'label']);
  assert.equal(imported.label, expectedLabel);
  assert.deepEqual(imported.files.map(file => file.name), originalNames);
  assert.equal(Buffer.from(imported.files[0].content_base64, 'base64').toString(), original);
  assert.equal(run('model.flow.datasetId'), dataset.dataset_id);
  assert.equal(run('model.run.dataset_metadata.label'), expectedLabel);
  const escapedLabel = MULTIPLE ? expectedLabel : 'Quarterly &lt;ledger&gt; 2026';
  assert.ok(main.innerHTML.includes(escapedLabel));
  assert.ok(run('savedWorkView()').includes(escapedLabel));
  assert.ok(!main.innerHTML.includes('<ledger>'));
  assert.ok(!run('savedWorkView()').includes('<ledger>'));
  assert.notEqual(imported.label, 'Named in the records', 'A filename title does not infer the identity or scope of its contents.');
""".replace("MULTIPLE", str(multiple).lower()))


@pytest.mark.parametrize("page", ["investigate", "runs"])
def test_assessment_leads_with_the_decision_and_preserves_edits_while_reviewing_findings(
    page: str,
) -> None:
    run_case_review(r"""
  const findings = Array.from({length: 11}, (_, index) => ({...finding('observation-' + index), observation: 'Specific retained evidence ' + index}));
  run(`model.run.analysis.findings = ${JSON.stringify(findings)}; model.flow.surfaceOpen = true;`);
  navigate(PAGE);
  const markup = run('caseReviewView()');
  assert.ok(markup.includes('11 observations'));
  assert.ok(markup.includes('name="decision"'));
  assert.ok(markup.includes('name="acknowledge_limitations" required'));
  assert.ok(markup.includes('I reviewed the findings and coverage, including missing evidence.'));
  assert.ok(markup.includes('data-flow="finding-list">Review findings'));
  assert.ok(markup.includes('data-flow="coverage">Checks and sources'));
  assert.ok(!markup.includes('Specific retained evidence'));
  assert.ok(!markup.includes('case-brief'));
  assert.ok(!markup.includes('This records one decision for the case'));
  editCaseReview({reviewer: 'Analyst Example', decision: 'keep_open', summary: 'Awaiting the retained invoice reconciliation.'});
  click(flowButton('finding-list'));
  assert.equal(run('model.flow.findingIndex'), null);
  assert.equal(run('model.flow.cubeFace'), 3);
  assert.equal(run('model.reviewDrafts.runA.summary'), 'Awaiting the retained invoice reconciliation.');
  if (PAGE === 'runs') assert.equal(run('model.runTab'), 'findings');
  else assert.equal(run('model.flow.surfaceOpen'), true);
  findings.forEach(item => assert.ok(main.innerHTML.includes(item.observation), 'The complete findings remain accessible.'));
  click(flowButton('review-summary'));
  assert.ok(main.innerHTML.includes('Awaiting the retained invoice reconciliation.'));
  assert.ok(!main.innerHTML.includes('Specific retained evidence'));
  assert.equal(run('model.reviewDrafts.runA.acknowledge_limitations'), false, 'Navigation cannot acknowledge coverage on the user’s behalf.');
""".replace("PAGE", repr(page)))


@pytest.mark.parametrize("missing", [0, 1])
def test_findings_header_only_calls_out_checks_that_could_not_run(missing: int) -> None:
    run_case_review(r"""
  if (MISSING) run("model.run.analysis.coverage.push({investigation_id: 'invoice_overlap', status: 'not_evaluable', reason: 'Invoice records were not supplied.'});");
  const markup = run('flowFindingsView()');
  assert.ok(markup.includes('2 checks completed.'));
  assert.equal(markup.includes('1 check could not run.'), Boolean(MISSING));
  assert.ok(!markup.includes('0 checks could not run.'));
""".replace("MISSING", str(missing)))


def test_preview_exposes_actionable_issues_and_keeps_technical_details_available() -> (
    None
):
    run_guided(r"""
  const preview = {...previewed(), file_name: 'invalid.csv', can_import: false, generated_id_count: 1, warnings: [
    'Same-name records remain separate entities. No identity merge or transaction linking occurs.',
    'Original CSV bytes and unmapped columns will be retained. Only mapped fields participate in analysis.',
    'Text fields are trimmed; entity type defaults to organization when absent. Country conversions are explicitly listed below.',
    'Generated 1 deterministic record IDs from the complete file hash and source row; they are not verified business identifiers.',
    'Columns retained only in the original file: Internal comment',
    '1 repeated-name records are retained separately.',
  ], errors: ["invalid.csv:2: country: String should match pattern '^[A-Z]{2}$'", 'Several columns could supply name: Supplier, Name. Choose one.']};
  run(`Object.assign(model.flow, {stage: 'data', cubeFace: 0, surfaceOpen: true, preview: ${JSON.stringify(preview)}, mapping: ${JSON.stringify(preview.mapping)}}); renderGuided();`);
  assert.ok(main.innerHTML.includes('Row 2: Country must be a recognized country name or two-letter country code.'));
  assert.ok(main.innerHTML.includes('Several columns could supply name: Supplier, Name. Choose one.'));
  assert.ok(main.innerHTML.includes('Columns retained only in the original file: Internal comment'));
  assert.ok(main.innerHTML.includes('repeated-name records are retained separately.'));
  assert.ok(!main.innerHTML.includes('String should match pattern'));
  assert.ok(!main.innerHTML.includes('deterministic record IDs'));
  assert.ok(!main.innerHTML.includes('Text fields are trimmed'));
  assert.ok(!main.innerHTML.includes('data-flow="repreview"'));
  assert.match(main.innerHTML, /data-flow="import" disabled/);
  click(flowButton('preview-info'));
  const details = node('#dialog-content').innerHTML;
  assert.ok(details.includes('No company identities are merged.'));
  assert.ok(details.includes('deterministic record IDs'));
  assert.ok(details.includes('String should match pattern'));
  assert.ok(details.includes('1 record will receive a local ID'));
  assert.equal(run('model.flow.datasetId'), 'datasetA', 'Displaying a preview cannot create or replace a saved dataset.');
  changeControl('mapping-1', '', {mapping: 'Country'});
  assert.equal(run('model.flow.previewStale'), true);
  assert.ok(main.innerHTML.includes('data-flow="repreview"'));
  assert.match(main.innerHTML, /data-flow="import" disabled/);
""")


def test_identity_options_keep_name_correction_available_without_accepting_a_profile() -> (
    None
):
    run_identity(r"""
  submitSubject();
  await settle();
  assert.ok(main.innerHTML.includes('data-flow="back-goal">Use another name'));
  const original = run('model.flow.subjectName');
  click(flowButton('back-goal'));
  assert.equal(run('model.flow.stage'), 'goal');
  assert.equal(run('model.flow.subjectName'), original);
  assert.ok(main.innerHTML.includes('id="flow-subject-name"'));
  assert.ok(node('#flow-subject-name').focusCount > 0);
  assert.deepEqual(screeningRequests(), []);
  assert.ok(!entryRequests.some(item => item.url === '/api/workflow/identity-select'));
""")


@pytest.mark.parametrize("running", [False, True])
def test_switching_from_file_intake_to_a_name_clears_only_the_obsolete_notice(
    running: bool,
) -> None:
    run_guided(r"""
  run("Object.assign(model.flow, {stage: 'data', cubeFace: 0, surfaceOpen: true}); announce('Dataset rejected: invalid file.', 'error');");
  run('model.operation = RUNNING;');
  click(flowButton('back-goal'));
  assert.equal(run('model.flow.stage'), 'goal');
  assert.equal(notice.hidden, !RUNNING);
  assert.equal(notice.textContent, 'Dataset rejected: invalid file.');
  assert.ok(node('#flow-subject-name').focusCount > 0);
""".replace("RUNNING", str(running).lower()))


@pytest.mark.parametrize("action", ["verify", "replay"])
def test_guided_integrity_results_show_readable_outcomes_and_exact_escaped_issues(
    action: str,
) -> None:
    run_case_review(r"""
  const success = run(`integrityResultView(${JSON.stringify(ACTION)}, {ok: true, files_checked: 9, actual_digest: 'technical-digest'})`);
  assert.ok(success.includes(ACTION === 'verify' ? 'recorded checksums' : 'Findings and coverage reproduced'));
  assert.ok(success.includes('9 files checked.'));
  assert.ok(!success.includes('<pre>'));
  assert.ok(!success.includes('technical-digest'));
  const failure = run(`integrityResultView(${JSON.stringify(ACTION)}, {ok: false, issues: ['A retained record <changed>.'], verification: {files_checked: 3, issues: ['A retained record <changed>.', 'missing artifact: data/dataset.json']}})`);
  assert.equal((failure.match(/A retained record &lt;changed&gt;\./g) || []).length, 1);
  assert.ok(failure.includes('missing artifact: data/dataset.json'));
  assert.ok(failure.includes('3 files checked.'));
  assert.ok(!failure.includes('<changed>'));
""".replace("ACTION", repr(action)))
