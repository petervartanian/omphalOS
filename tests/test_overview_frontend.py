"""Keep the viewport overview separate from intentionally opened case details.

The shared adapter checks navigation, retained work, and request ownership. Actual
viewport fit is checked in the browser rather than inferred from CSS strings.
"""

from __future__ import annotations

import pytest
from test_frontend_guards import run_scenario
from test_guided_frontend import GUIDED_SETUP

OVERVIEW_SETUP = GUIDED_SETUP + r"""
  const retainedOverview = {
    ...runA, latest_review: null,
    case: {...runA.case, dataset_id: 'datasetA'},
    dataset_metadata: {label: 'Retained overview case', synthetic: true, counts: {entities: 1}},
    analysis: {...runA.analysis, findings: [finding()], coverage: [
      {investigation_id: 'data_quality', status: 'executed', records_evaluated: 1, findings_count: 1},
    ]},
  };
  const overviewRequests = [];
  let overviewIntercept = async () => {};
  fetchImplementation = async (url, options) => {
    const body = options?.body ? JSON.parse(options.body) : null;
    overviewRequests.push({url, body});
    await overviewIntercept(url, body);
    if (url === '/api/state') return jsonResponse(state);
    if (url === '/api/workflow/plan') return jsonResponse(planned());
    if (url === '/api/workflow/run') return jsonResponse({run_id: 'runA'});
    if (url === '/api/runs/runA') return jsonResponse(retainedOverview);
    if (url.startsWith('/api/runs/runA/finding-evidence?'))
      return jsonResponse({rows: [], offset: 0, total: 0});
    throw new Error('Unexpected overview request: ' + url);
  };
  function showRetainedOverview() {
    run(`model.run = ${JSON.stringify(retainedOverview)}; model.selectedRun = 'runA'; Object.assign(model.flow, {stage: 'review', datasetId: 'datasetA', cubeFace: 3, inspectionFace: 3, surfaceOpen: false, findingIndex: null}); renderGuided();`);
  }
  function pendingCaseForm(fields) {
    const controls = Object.fromEntries(Object.keys(fields).map(name => [name, {name, value: fields[name]}]));
    currentReviewForm = {
      id: 'review-form', dataset: {reviewScope: 'case', dirty: 'true'}, fields, elements: controls,
      querySelectorAll(selector) {return selector === 'input, select, textarea' ? Object.values(controls) : [];},
      querySelector(selector) {return controls[selector.match(/name="([^"]+)"/)?.[1]] || null;},
    };
  }
"""


def run_overview(scenario: str) -> None:
    run_scenario(OVERVIEW_SETUP + scenario)


def test_landing_starts_in_overview_without_opening_records_or_creating_work() -> None:
    run_overview(r"""
  run('model.flow = newFlow(); model.run = null; model.selectedRun = ""; renderGuided();');
  assert.equal(run('model.flow.surfaceOpen'), false);
  assert.equal(run('model.flow.stage'), 'goal');
  assert.ok(main.innerHTML.includes('id="flow-subject-form"'));
  assert.equal(run('Object.keys(model.reviewDrafts).length'), 0);
  assert.deepEqual(overviewRequests, []);
""")


def test_screening_explanation_opens_from_a_labeled_information_control() -> None:
    run_overview(r"""
  run('model.flow = newFlow(); renderGuided();');
  const markup = run('flowStartView()');
  const info = markup.match(/<button\b[^>]*data-flow="screening-info"[^>]*>/)?.[0];
  assert.ok(info, 'The entry must provide a screening information control.');
  assert.match(info, /aria-label="[^"]+"/, 'An icon-only control needs an accessible name.');
  assert.ok(!markup.includes('omphalOS downloads the official U.S. screening list and checks the name locally.'), 'The explanation belongs in the information dialog, not the default entry.');
  click(flowButton('screening-info'));
  assert.equal(node('#evidence-dialog').showModalCount, 1);
  assert.match(node('#dialog-title').textContent, /screening|name|search/i);
  assert.match(node('#dialog-content').innerHTML, /official/i);
  assert.match(node('#dialog-content').innerHTML, /local/i);
  assert.equal(run('model.flow.surfaceOpen'), false);
  assert.equal(run('model.flow.stage'), 'goal');
  assert.deepEqual(overviewRequests, [], 'Opening an explanation must not start screening.');
""")


def test_automatic_completion_returns_to_overview_without_focusing_hidden_details() -> (
    None
):
    run_overview(r"""
  let scrolls = 0;
  node('.object-surface').scrollIntoView = () => {scrolls += 1;};
  click(flowButton('investigate-dataset', {id: 'datasetA'}));
  await settle();
  assert.equal(overviewRequests.filter(item => item.url === '/api/workflow/run').length, 1);
  assert.equal(run('model.flow.stage'), 'review');
  assert.equal(run('model.selectedRun'), 'runA');
  assert.equal(run('model.flow.datasetId'), 'datasetA');
  assert.equal(run('model.flow.surfaceOpen'), false);
  assert.equal(node('.object-surface').focusCount, 0);
  assert.equal(scrolls, 0);
  assert.equal(run('Object.keys(model.reviewDrafts).length'), 0);
  assert.ok(!overviewRequests.some(item => item.url.endsWith('/review')));
  assert.notEqual(notice.className, 'notice error');
""")


@pytest.mark.parametrize("reviewed", [False, True])
def test_resuming_a_case_opens_overview_and_preserves_recorded_review(
    reviewed: bool,
) -> None:
    run_overview(r"""
  if (REVIEWED) retainedOverview.latest_review = {
    review_id: 'recorded-case-review',
    review: {schema_version: '2.1', run_id: 'runA', reviewer: 'Analyst Example', decision: 'keep_open', summary: 'Awaiting the retained invoice.', scope_finding_ids: ['findingA'], acknowledge_limitations: true},
  };
  let scrolls = 0;
  node('.object-surface').scrollIntoView = () => {scrolls += 1;};
  click(flowButton('resume', {id: 'runA'}));
  await settle();
  assert.equal(run('model.flow.surfaceOpen'), false);
  assert.equal(run('model.flow.stage'), REVIEWED ? 'package' : 'review');
  assert.equal(run('model.selectedRun'), 'runA');
  assert.equal(run('model.flow.datasetId'), 'datasetA');
  assert.equal(run('model.run.latest_review?.review_id || null'), REVIEWED ? 'recorded-case-review' : null);
  assert.equal(node('.object-surface').focusCount, 0);
  assert.equal(scrolls, 0);
  assert.equal(run('Object.keys(model.reviewDrafts).length'), 0);
  assert.deepEqual(overviewRequests.map(item => item.url), ['/api/runs/runA']);
""".replace("REVIEWED", str(reviewed).lower()))


@pytest.mark.parametrize("face", range(5))
def test_selecting_a_face_opens_details_and_return_keeps_the_case(face: int) -> None:
    run_overview(r"""
  showRetainedOverview();
  click(flowButton('cube', {face: String(FACE)}));
  assert.equal(run('model.flow.surfaceOpen'), true);
  assert.equal(run('model.flow.inspectionFace'), FACE);
  const before = run('JSON.stringify(model.run)');
  click(flowButton('overview'));
  assert.equal(run('model.flow.surfaceOpen'), false);
  assert.equal(run('model.selectedRun'), 'runA');
  assert.equal(run('model.flow.datasetId'), 'datasetA');
  assert.equal(run('JSON.stringify(model.run)'), before);
  assert.equal(run('Object.keys(model.reviewDrafts).length'), 0);
  assert.deepEqual(overviewRequests, []);
  click(flowButton('focus-step'));
  assert.equal(run('model.flow.surfaceOpen'), true);
  assert.equal(run('model.flow.inspectionFace'), FACE);
""".replace("FACE", str(face)))


def test_return_to_overview_captures_unsaved_case_decision_and_reopens_it() -> None:
    run_overview(r"""
  showRetainedOverview();
  click(flowButton('review-summary'));
  assert.equal(run('model.flow.surfaceOpen'), true);
  const note = '<Supplier ledger> still needs reconciliation.';
  pendingCaseForm({reviewer: 'Analyst Example', decision: 'keep_open', summary: note, acknowledge_limitations: 'on'});
  assert.equal(run('Object.keys(model.reviewDrafts).length'), 0, 'The pending DOM edits must be captured by the return action.');
  click(flowButton('overview'));
  assert.equal(run('model.flow.surfaceOpen'), false);
  const draft = JSON.parse(run('JSON.stringify(model.reviewDrafts.runA)'));
  assert.equal(draft.schema_version, '2.1');
  assert.equal(draft.reviewer, 'Analyst Example');
  assert.equal(draft.decision, 'keep_open');
  assert.equal(draft.summary, note);
  assert.equal(draft.acknowledge_limitations, true);
  assert.deepEqual(draft.scope_finding_ids, ['findingA']);
  assert.equal(run('model.run.latest_review'), null);
  click(flowButton('review-summary'));
  assert.equal(run('model.flow.surfaceOpen'), true);
  assert.ok(main.innerHTML.includes('&lt;Supplier ledger&gt; still needs reconciliation.'));
  assert.deepEqual(JSON.parse(run('JSON.stringify(model.reviewDrafts.runA)')), draft);
  assert.deepEqual(overviewRequests, [], 'Returning to the overview must not save or execute the case.');
""")


@pytest.mark.parametrize("action", ["add-records", "choose-file"])
def test_record_entry_opens_the_surface_and_file_picker_remains_available(
    action: str,
) -> None:
    run_overview(r"""
  run('model.flow = newFlow(); renderGuided();');
  let pickerOpens = 0;
  node('#flow-vendor-file').click = () => {pickerOpens += 1;};
  click(flowButton(ACTION));
  assert.equal(run('model.flow.surfaceOpen'), true);
  assert.equal(run('model.flow.stage'), 'data');
  assert.ok(main.innerHTML.includes('id="flow-vendor-file"'));
  assert.equal(pickerOpens, ACTION === 'choose-file' ? 1 : 0);
  assert.deepEqual(overviewRequests, []);
""".replace("ACTION", repr(action)))


@pytest.mark.parametrize("selection", ["resume", "investigate-dataset"])
def test_saved_work_selection_dispatches_once_from_its_dialog(selection: str) -> None:
    run_overview(r"""
  state.runs = [{run_id: 'runA', case_id: 'caseA', dataset_id: 'datasetA', status: 'awaiting_review', findings_count: 1}];
  state.datasets[0].counts.shipments = 2;
  run(`model.state = ${JSON.stringify(state)}; model.flow = newFlow(); renderGuided();`);
  let closes = 0;
  node('#evidence-dialog').close = () => {closes += 1;};
  click(flowButton('open-work'));
  assert.equal(node('#evidence-dialog').showModalCount, 1);
  assert.deepEqual(overviewRequests, [], 'Opening saved work must not start an investigation.');
  const selected = flowButton(SELECTION, {id: SELECTION === 'resume' ? 'runA' : 'datasetA'});
  selected.closest = selector => selector === '.saved-work button[data-flow]' || selector === 'button' ? selected : null;
  // The dialog is outside #main. Dispatch on the dialog itself so an accidental
  // dependency on the main page click handler cannot make this test pass.
  node('#evidence-dialog').emit('click', {target: selected, preventDefault() {}});
  node('#evidence-dialog').emit('click', {target: selected, preventDefault() {}});
  await settle();
  assert.equal(closes, 1);
  assert.equal(run('model.selectedRun'), 'runA');
  assert.equal(run('model.flow.datasetId'), 'datasetA');
  assert.equal(run('model.flow.surfaceOpen'), false);
  assert.equal(overviewRequests.filter(item => item.url === '/api/runs/runA').length, 1);
  assert.equal(overviewRequests.filter(item => item.url === '/api/workflow/run').length, SELECTION === 'resume' ? 0 : 1);
  assert.equal(run('Object.keys(model.reviewDrafts).length'), 0);
  assert.notEqual(notice.className, 'notice error');
""".replace("SELECTION", repr(selection)))


@pytest.mark.parametrize("return_to_overview", [False, True])
def test_automatic_completion_respects_the_view_chosen_while_running(
    return_to_overview: bool,
) -> None:
    run_overview(r"""
  let release;
  let waiting = false;
  overviewIntercept = async url => {
    if (url !== '/api/workflow/run') return;
    waiting = true;
    await new Promise(resolve => {release = resolve;});
  };
  click(flowButton('investigate-dataset', {id: 'datasetA'}));
  await until(() => waiting);
  click(flowButton('cube', {face: '1'}));
  assert.equal(run('model.flow.surfaceOpen'), true);
  if (RETURN) click(flowButton('overview'));
  release();
  await settle();
  assert.equal(run('model.selectedRun'), 'runA');
  assert.equal(run('model.flow.stage'), 'review');
  assert.equal(run('model.flow.surfaceOpen'), !RETURN);
  assert.equal(run('model.flow.inspectionFace'), 1);
  assert.equal(overviewRequests.filter(item => item.url === '/api/workflow/run').length, 1);
  assert.notEqual(notice.className, 'notice error');
""".replace("RETURN", str(return_to_overview).lower()))


def test_hidden_finding_does_not_fetch_until_opened_and_late_evidence_stays_hidden() -> (
    None
):
    run_overview(r"""
  showRetainedOverview();
  run('model.flow.findingIndex = 0; renderGuided(); loadVisibleFindingEvidence();');
  assert.deepEqual(overviewRequests, [], 'A retained selection must not eagerly fetch hidden evidence.');
  let release;
  let waiting = false;
  overviewIntercept = async url => {
    if (!url.includes('/finding-evidence?')) return;
    waiting = true;
    await new Promise(resolve => {release = resolve;});
  };
  click(flowButton('focus-step'));
  await until(() => waiting);
  assert.equal(run('model.flow.surfaceOpen'), true);
  click(flowButton('overview'));
  node('#finding-evidence-records').innerHTML = 'No visible detail region';
  release();
  for (let index = 0; index < 10; index += 1) await new Promise(resolve => setImmediate(resolve));
  assert.equal(run('model.flow.surfaceOpen'), false);
  assert.equal(node('#finding-evidence-records').innerHTML, 'No visible detail region', 'A late evidence response must not render into the hidden surface.');
  assert.equal(overviewRequests.filter(item => item.url.includes('/finding-evidence?')).length, 1);
  click(flowButton('focus-step'));
  assert.equal(run('model.flow.surfaceOpen'), true);
  assert.equal(overviewRequests.filter(item => item.url.includes('/finding-evidence?')).length, 1, 'Reopening may use the retained evidence cache.');
""")
