"""Simulate complete analyst tasks through the shipped browser event handlers.

The fixtures are fictional and the DOM adapter is deliberately limited. These
checks establish workflow behavior, not human usability or detection accuracy.
"""

from __future__ import annotations

import pytest
from test_case_review_frontend import run_case_review
from test_investigation_entry import run_entry


@pytest.mark.parametrize("intake", ["name", "csv"])
@pytest.mark.parametrize(
    ("decision", "label"),
    [("keep_open", "Keep open"), ("escalate", "Escalated"), ("conclude", "Concluded")],
)
def test_intake_evidence_decision_export_and_reopen_keep_disposition_visible(
    intake: str, decision: str, label: str
) -> None:
    run_entry(
        r"""
  const intake = INTAKE, decision = DECISION, label = LABEL;
  const requests = [];
  const originalFetch = fetchImplementation;
  let retained = null;
  let revision = 0;
  const note = 'The supplied invoice was reconciled; the missing shipment ledger remains documented.';
  fetchImplementation = async (url, options) => {
    const body = options?.body ? JSON.parse(options.body) : null;
    requests.push({url, body});
    if (url === '/api/workflow/preview') return jsonResponse(previewed());
    if (url === '/api/workflow/import') {
      state.datasets.push(subjectDataset);
      return jsonResponse(subjectDataset);
    }
    if (url === '/api/runs/subject-run/review') {
      revision += 1;
      retained = {...retained, latest_review: {review_id: 'review-' + revision, review: body}, latest_export: null};
      state.runs = [{run_id: 'subject-run', dataset_id: retained.case.dataset_id, status: 'review_recorded', case_decision: body.decision, findings_count: 1, created_at: '2026-10-18T10:00:00Z', verification_status: 'not_checked'}];
      return jsonResponse({review_id: 'review-' + revision});
    }
    if (url === '/api/runs/subject-run/export') {
      retained.latest_export = {name: 'case-' + revision + '.zip', download_url: '/api/exports/case-' + revision + '.zip'};
      return jsonResponse(retained.latest_export);
    }
    if (url.startsWith('/api/runs/subject-run/finding-evidence?'))
      return jsonResponse({offset: 0, total: 1, rows: [{kind: 'record', table: 'entities', id: 'entity-subject', record: {entity_id: 'entity-subject', name: subject}}]});
    if (url === '/api/runs/subject-run') {
      if (!retained) {
        retained = await (await originalFetch(url, options)).json();
        retained.analysis.findings[0].record_refs = [{table: 'entities', record_id: 'entity-subject'}];
        retained.analysis.coverage = [{investigation_id: 'data_quality', status: 'executed', records_evaluated: 1, findings_count: 1}];
      }
      return jsonResponse(retained);
    }
    return originalFetch(url, options);
  };
  function authorDecision(selected, summary) {
    const fields = {reviewer: 'Analyst Example', decision: selected, summary, acknowledge_limitations: 'on'};
    const controls = Object.fromEntries(Object.keys(fields).map(name => [name, new Element(name)]));
    const form = {
      id: 'review-form', dataset: {reviewScope: 'case'}, fields, elements: controls,
      querySelectorAll(selector) {return selector === 'input, select, textarea' ? Object.values(controls) : [];},
    };
    Object.values(controls).forEach(control => {control.closest = selector => selector === '#review-form' ? form : null;});
    currentReviewForm = form;
    main.emit('input', {target: controls.summary});
    return form;
  }
  if (intake === 'name') {
    submitSubject();
    await settle();
    assert.equal(run('model.flow.stage'), 'identity');
    click(flowButton('identity-skip'));
  } else {
    node('#flow-vendor-file').click = () => {};
    click(flowButton('choose-file'));
    main.emit('change', {target: fileControl('suppliers.csv', 'Supplier,Country\nExample Components LLC,US\n')});
    await settle();
    assert.equal(run('model.flow.preview.can_import'), true);
    assert.ok(!requests.some(item => item.url === '/api/workflow/import'));
    click(flowButton('import'));
  }
  await settle();
  assert.equal(run('model.flow.cubeFace'), 1);
  assert.ok(!requests.some(item => item.url === '/api/workflow/run'));
  await approveAndRun();
  assert.equal(run('flowStageAccess(4)'), false);
  click(flowButton('review-step', {index: '0'}));
  await until(() => node('#finding-evidence-records').innerHTML.includes(subject));
  assert.equal(run('flowResultsReviewed(model.run)'), false);
  click(flowButton('finding-list'));
  click(flowButton('findings-reviewed'));
  assert.equal(run('flowStageAccess(4)'), true);
  assert.equal(run('flowStageAccess(5)'), false);
  const form = authorDecision(decision, note);
  main.emit('submit', {target: form, preventDefault() {}});
  await settle();
  assert.equal(retained.latest_review.review.decision, decision);
  assert.equal(retained.latest_review.review.schema_version, '2.2');
  assert.equal(run('model.flow.cubeFace'), 5);
  assert.equal(run('flowCubeFaces()[4].status'), label);
  assert.ok(run('flowGuide()').includes('Recorded: ' + label));
  assert.ok(run('savedWorkView()').includes('Recorded: ' + label));
  assert.ok(run('runTable(model.state.runs)').includes('Recorded: ' + label));
  assert.ok(!run('flowCubeFaces()[5].complete'));
  click(button('export'));
  await settle();
  assert.equal(run('flowCubeFaces()[5].complete'), true);
  assert.ok(run('flowGuide()').includes('Recorded: ' + label));
  assert.ok(run('flowGuide()').includes('Evidence package created'));
  click(flowButton('restart'));
  click(flowButton('resume', {id: 'subject-run'}));
  await settle();
  assert.equal(run('model.flow.surfaceOpen'), false);
  assert.equal(run('model.run.latest_review.review.decision'), decision);
  assert.ok(run('flowGuide()').includes('Recorded: ' + label));
  click(flowButton('focus-step'));
  assert.ok(run('flowPackageView()').includes('/api/exports/case-1.zip'));
  click(flowButton('review-summary'));
  const revised = authorDecision('keep_open', 'Additional shipping records are needed for a new assessment.');
  assert.equal(run('flowCubeFaces()[4].complete'), false);
  assert.equal(run('flowCubeFaces()[5].complete'), false);
  assert.ok(!run('flowPackageView()').includes('/api/exports/case-1.zip'));
  assert.ok(run('flowGuide()').includes('unsaved changes'));
  click(flowButton('overview'));
  click(flowButton('focus-step'));
  assert.equal(run('model.reviewDrafts[model.selectedRun].summary'), revised.fields.summary);
  assert.equal(run('model.run.latest_review.review.decision'), decision, 'Draft edits must preserve the retained decision.');
  assert.equal(requests.filter(item => item.url.endsWith('/review')).length, 1);
  assert.equal(requests.filter(item => item.url.endsWith('/export')).length, 1);
  assert.notEqual(notice.className, 'notice error');
""".replace("INTAKE", repr(intake))
        .replace("DECISION", repr(decision))
        .replace("LABEL", repr(label))
    )


def test_inventory_does_not_promote_unrecorded_or_unknown_dispositions() -> None:
    run_case_review(r"""
  run(`model.state.runs = [
    {run_id: 'pending', status: 'awaiting_review', case_decision: 'conclude'},
    {run_id: 'invalid', status: 'invalid', case_decision: 'conclude'},
    {run_id: 'legacy', status: 'review_recorded', case_decision: null},
    {run_id: 'unknown', status: 'reviewed', case_decision: '__proto__'},
  ];`);
  const saved = run('savedWorkView()');
  assert.ok(!saved.includes('Concluded'));
  assert.ok(!saved.includes('[object Object]'));
  assert.ok(saved.includes('Assessed'), 'Legacy inventory keeps its existing label.');
  const table = run('runTable(model.state.runs)');
  assert.ok(table.includes('Needs review'));
  assert.ok(table.includes('Invalid run'));
  assert.ok(table.includes('Review recorded'));
  assert.ok(!table.includes('Concluded'));
""")


def test_reopening_an_earlier_note_free_decision_preserves_its_export() -> None:
    run_case_review(r"""
  const saved = {schema_version: '2.1', run_id: 'runA', reviewer: 'Earlier Analyst', decision: 'keep_open', summary: '', scope_finding_ids: ['context-A', 'volume-B'], acknowledge_limitations: true};
  run(`model.run.latest_review = {review_id: 'earlier-review', review: ${JSON.stringify(saved)}}; model.run.latest_export = {name: 'earlier.zip', download_url: '/api/exports/earlier.zip'}; Object.assign(model.flow, {stage: 'package', cubeFace: 5, inspectionFace: null});`);
  assert.equal(run('flowReviewRecorded(model.run)'), true);
  assert.ok(run('flowPackageView()').includes('/api/exports/earlier.zip'));
  click(flowButton('review-summary'));
  caseReviewForm({...saved, acknowledge_limitations: 'on'});
  click(flowButton('overview'));
  assert.equal(run('Object.keys(model.reviewDrafts).length'), 0);
  assert.equal(run('model.run.latest_review.review.schema_version'), '2.1');
  assert.equal(run('flowReviewRecorded(model.run)'), true);
  assert.ok(run('flowPackageView()').includes('/api/exports/earlier.zip'));
  click(flowButton('review-summary'));
  const {form} = editCaseReview({...saved, decision: 'escalate', acknowledge_limitations: 'on'});
  const requests = [];
  fetchImplementation = async url => {requests.push(url); throw new Error('A new revision requires authored context.');};
  submitCaseReview(form);
  await settle();
  assert.deepEqual(requests, []);
  assert.equal(readCaseDraft().schema_version, '2.2');
  assert.equal(run('model.run.latest_review.review.schema_version'), '2.1');
  assert.equal(run('model.run.latest_review.review.decision'), 'keep_open');
  assert.match(notice.textContent, /specific reason and next step/);
""")


@pytest.mark.parametrize("failure", ["verification", "review_validation"])
def test_invalid_retained_state_never_displays_a_completed_case_disposition(
    failure: str,
) -> None:
    run_case_review(r"""
  const saved = {schema_version: '2.1', run_id: 'runA', reviewer: 'Analyst Example', decision: 'conclude', summary: 'The retained shipment records support the stated conclusion.', scope_finding_ids: ['context-A', 'volume-B'], acknowledge_limitations: true};
  run(`model.run.latest_review = {review_id: 'saved-review', review: ${JSON.stringify(saved)}}; model.run.latest_export = {name: 'case.zip', download_url: '/api/exports/case.zip'}; model.run[FAILURE] = {ok: false, issues: ['Retained content needs verification.']}; Object.assign(model.flow, {stage: 'package', cubeFace: 5, inspectionFace: null});`);
  assert.equal(run('flowCubeFaces()[4].complete'), false);
  assert.equal(run('flowCubeFaces()[5].complete'), false);
  assert.ok(!run('flowGuide()').includes('Recorded: Concluded'));
  assert.ok(!run('flowGuide()').includes('Evidence package created'));
  assert.ok(!run('flowPackageView()').includes('/api/exports/case.zip'));
""".replace("FAILURE", repr(failure)))
