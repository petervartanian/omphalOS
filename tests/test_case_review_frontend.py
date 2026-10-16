"""Protect case-level decisions from invented per-observation assessments.

These use the shipped handlers and the shared DOM adapter. Visual layout and
real-browser interaction remain separate checks.
"""

from __future__ import annotations

import pytest
from test_frontend_guards import run_scenario
from test_guided_frontend import GUIDED_SETUP

CASE_REVIEW_SETUP = GUIDED_SETUP + r"""
  const caseFindings = [finding('context-A'), {
    ...finding('volume-B'), investigation_id: 'volume_spike',
    title: 'Monthly shipment count increase',
    observation: 'Exporter E1 has 10 records in 2026-09, compared with a mean of 1 over the prior 6 months.',
    entity_ids: ['E1'], record_refs: [{table: 'shipments', record_id: 'S01'}],
    metrics: {month: '2026-09', current_count: 10, prior_month_counts: {'2026-03': 1, '2026-04': 1, '2026-05': 1, '2026-06': 1, '2026-07': 1, '2026-08': 1}, prior_mean: '1', ratio: '10'},
  }];
  const retainedCase = {
    ...runA, latest_review: null,
    case: {...runA.case, dataset_id: 'datasetA'},
    dataset_metadata: {label: 'Synthetic retained case', synthetic: true, counts: {entities: 1, shipments: 16}},
    analysis: {...runA.analysis, findings: caseFindings, coverage: [
      {investigation_id: 'data_quality', status: 'executed', records_evaluated: 1, findings_count: 1},
      {investigation_id: 'volume_spike', status: 'executed', records_evaluated: 16, findings_count: 1},
    ]},
  };
  run(`model.run = ${JSON.stringify(retainedCase)}; model.selectedRun = 'runA'; model.flow.stage = 'review'; model.flow.reviewIndex = 0; model.flow.inspectionFace = 4; model.reviewDrafts = {};`);
  navigate('investigate');
  click(flowButton('findings-reviewed'));
  function caseReviewForm(overrides = {}, dirty = false) {
    const fields = {reviewer: '', decision: '', summary: '', ...overrides};
    const controls = Object.fromEntries(Object.keys(fields).map((name) => {
      const control = new Element('[name="' + name + '"]');
      control.name = name;
      Object.defineProperty(control, 'value', {get: () => fields[name], set: (value) => {fields[name] = value;}});
      return [name, control];
    }));
    const form = {
      id: 'review-form', dataset: {reviewScope: 'case', ...(dirty ? {dirty: 'true'} : {})}, fields, elements: controls,
      querySelector(selector) {
        const name = selector.match(/name="([^"]+)"/)?.[1];
        return name ? controls[name] || null : null;
      },
      querySelectorAll(selector) {return selector === 'input, select, textarea' ? Object.values(controls) : [];},
    };
    Object.values(controls).forEach((control) => {
      control.closest = (selector) => selector === '#review-form' || selector === 'form' ? form : null;
    });
    currentReviewForm = form;
    return {form, fields, controls};
  }
  function readCaseReview() {
    return JSON.parse(run('JSON.stringify(readReview(document.querySelector("#review-form")))'));
  }
  function readCaseDraft() {
    return JSON.parse(run('JSON.stringify(model.reviewDrafts.runA)'));
  }
  function editCaseReview(overrides) {
    const form = caseReviewForm(overrides);
    main.emit('input', {target: form.controls.summary});
    return form;
  }
  function submitCaseReview(form) {
    main.emit('submit', {target: form, preventDefault() {}});
  }
  function assertCasePayload(review) {
    assert.deepEqual(Object.keys(review).sort(), ['schema_version', 'run_id', 'reviewer', 'decision', 'summary', 'scope_finding_ids', 'acknowledge_limitations'].sort());
    assert.equal(review.schema_version, '2.1');
    assert.equal(review.run_id, 'runA');
    assert.deepEqual(review.scope_finding_ids, ['context-A', 'volume-B']);
    assert.ok(!Object.hasOwn(review, 'findings'), 'A case decision must not manufacture individual finding reviews.');
  }
"""


def run_case_review(scenario: str) -> None:
    run_scenario(CASE_REVIEW_SETUP + scenario)


@pytest.mark.parametrize("view", ["flowReviewView", "renderReview"])
def test_new_reviews_show_one_case_decision_without_the_questionnaire(
    view: str,
) -> None:
    run_case_review(r"""
  const markup = run('VIEW()');
  assert.match(markup, /data-review-scope="case"/);
  assert.match(markup, /name="decision"/);
  for (const retired of ['Proposed follow-up', 'Edit this proposal', 'Use these review prompts', 'Questions to carry into the assessment', 'Write my own', 'Use this summary', 'all assessment fields filled']) {
    assert.ok(!markup.includes(retired), 'New case reviews must not expose the old questionnaire: ' + retired);
  }
  assert.ok(!/name="(?:disposition|rationale|unknowns|alternatives|falsifiers)"/.test(markup));
  assert.ok(!/name="decision"[^>]*checked|checked[^>]*name="decision"/.test(markup), 'Opening the screen must not choose a decision.');
  assert.equal(run('Object.keys(model.reviewDrafts).length'), 0);
""".replace("VIEW", view))


def test_viewing_case_and_findings_creates_no_draft_or_review_request() -> None:
    run_case_review(r"""
  const requests = [];
  fetchImplementation = async (url) => {requests.push(url); throw new Error('Viewing local retained results should not create a review request.');};
  run('flowReviewView(); flowFindingsView(); renderReview();');
  click(flowButton('cube', {face: '3'}));
  click(flowButton('cube', {face: '4'}));
  assert.equal(run('Object.keys(model.reviewDrafts).length'), 0);
  assert.equal(run('model.run.latest_review'), null);
  assert.deepEqual(requests, []);
""")


def test_empty_case_form_does_not_invent_decision_note_or_acknowledgment() -> None:
    run_case_review(r"""
  caseReviewForm();
  const review = readCaseReview();
  assertCasePayload(review);
  assert.equal(review.decision, '');
  assert.equal(review.summary, '');
  assert.equal(review.reviewer, '');
  assert.equal(review.acknowledge_limitations, false);
  assert.equal(run('Object.keys(model.reviewDrafts).length'), 0);
""")


@pytest.mark.parametrize("decision", ["keep_open", "escalate", "conclude"])
def test_case_form_keeps_the_explicit_case_decision_and_only_authored_note(
    decision: str,
) -> None:
    run_case_review(r"""
  const note = 'The supporting invoices have been reconciled against the retained transactions.';
  caseReviewForm({reviewer: '  Analyst Example  ', decision: DECISION, summary: '  ' + note + '  ', acknowledge_limitations: 'on'});
  const review = readCaseReview();
  assertCasePayload(review);
  assert.equal(review.decision, DECISION);
  assert.equal(review.reviewer, 'Analyst Example');
  assert.equal(review.summary, note);
  assert.equal(review.acknowledge_limitations, true);
""".replace("DECISION", repr(decision)))


def test_scope_comes_from_the_current_analysis_not_hidden_form_values() -> None:
    run_case_review(r"""
  caseReviewForm({reviewer: 'Analyst Example', decision: 'keep_open', scope_finding_ids: ['injected'], findings: [{finding_id: 'invented', disposition: 'explained'}]});
  const review = readCaseReview();
  assertCasePayload(review);
  assert.equal(review.summary, '');
""")


def test_pristine_case_form_does_not_become_a_draft_on_navigation() -> None:
    run_case_review(r"""
  caseReviewForm();
  navigate('data');
  navigate('investigate');
  assert.equal(run('Object.keys(model.reviewDrafts).length'), 0);
  const unload = {prevented: false, preventDefault() {this.prevented = true;}};
  window.emit('beforeunload', unload);
  assert.equal(unload.prevented, false);
""")


def test_edited_case_decision_survives_navigation_and_escapes_authored_text() -> None:
    run_case_review(r"""
  const note = '<Unverified supplier> needs a complete September shipment ledger.';
  editCaseReview({reviewer: 'Analyst Example', decision: 'keep_open', summary: note, acknowledge_limitations: 'on'});
  const before = readCaseDraft();
  assertCasePayload(before);
  navigate('data');
  navigate('investigate');
  assert.deepEqual(readCaseDraft(), before);
  const markup = run('flowReviewView()');
  assert.ok(markup.includes('&lt;Unverified supplier&gt;'));
  assert.ok(!markup.includes('<Unverified supplier>'));
  assert.equal(readCaseDraft().summary, note);
  const unload = {prevented: false, preventDefault() {this.prevented = true;}};
  window.emit('beforeunload', unload);
  assert.equal(unload.prevented, true);
""")


def test_editing_a_retained_case_review_keeps_its_schema_and_explicit_fields() -> None:
    run_case_review(r"""
  const retained = {schema_version: '2.1', run_id: 'runA', reviewer: 'Earlier Analyst', decision: 'keep_open', summary: 'Awaiting the complete ledger from the supplier.', scope_finding_ids: ['context-A', 'volume-B'], acknowledge_limitations: true};
  run(`model.run.latest_review = {review_id: 'case-reviewA', review: ${JSON.stringify(retained)}};`);
  assert.equal(run('Object.keys(model.reviewDrafts).length'), 0);
  editCaseReview({...retained, decision: 'escalate', summary: 'Specialist reconciliation is needed for the retained invoice records.', acknowledge_limitations: 'on'});
  const draft = readCaseDraft();
  assertCasePayload(draft);
  assert.equal(draft.decision, 'escalate');
  assert.equal(draft.reviewer, retained.reviewer);
  assert.equal(run('model.run.latest_review.review.decision'), 'keep_open', 'Editing must not mutate the saved review.');
""")


@pytest.mark.parametrize("decision", ["keep_open", "escalate"])
def test_open_case_decision_can_save_without_an_invented_note(decision: str) -> None:
    run_case_review(r"""
  const {form} = caseReviewForm({reviewer: 'Analyst Example', decision: DECISION, acknowledge_limitations: 'on'});
  const posted = [];
  fetchImplementation = async (url, options) => {
    if (url === '/api/runs/runA/review') {
      const review = JSON.parse(options.body);
      posted.push(review);
      return jsonResponse({review_id: 'case-reviewA'});
    }
    if (url === '/api/state') return jsonResponse(state);
    if (url === '/api/runs/runA') return jsonResponse({...retainedCase, latest_review: {review_id: 'case-reviewA', review: posted[0]}});
    throw new Error('Unexpected request: ' + url);
  };
  submitCaseReview(form);
  await settle();
  assert.equal(posted.length, 1);
  assertCasePayload(posted[0]);
  assert.equal(posted[0].decision, DECISION);
  assert.equal(posted[0].summary, '');
  assert.equal(posted[0].acknowledge_limitations, true);
  assert.equal(run('Object.keys(model.reviewDrafts).length'), 0);
  assert.equal(run('model.run.latest_review.review.schema_version'), '2.1');
  assert.notEqual(notice.className, 'notice error');
""".replace("DECISION", repr(decision)))


@pytest.mark.parametrize("decision", ["", "conclude"])
def test_save_requires_a_decision_and_conclusion_requires_an_authored_note(
    decision: str,
) -> None:
    run_case_review(r"""
  const {form} = caseReviewForm({reviewer: 'Analyst Example', decision: DECISION, acknowledge_limitations: 'on'});
  const requests = [];
  fetchImplementation = async (url) => {requests.push(url); throw new Error('An incomplete case decision must not be posted.');};
  submitCaseReview(form);
  await settle();
  assert.deepEqual(requests, []);
  assert.equal(notice.className, 'notice error');
  assert.equal(readCaseDraft().summary, '');
  assert.equal(readCaseDraft().decision, DECISION);
  assert.equal(run('model.run.latest_review'), null);
""".replace("DECISION", repr(decision)))


def test_delayed_case_save_cannot_discard_a_newer_authored_note() -> None:
    run_case_review(r"""
  const earlier = 'The original invoice has been requested from the supplier.';
  const later = 'The supplier replied; its full shipment ledger is still outstanding.';
  const {form} = editCaseReview({reviewer: 'Analyst Example', decision: 'keep_open', summary: earlier, acknowledge_limitations: 'on'});
  let release;
  let posted;
  const pending = new Promise(resolve => {release = resolve;});
  fetchImplementation = async (url, options) => {
    if (url === '/api/runs/runA/review') {posted = JSON.parse(options.body); return pending;}
    if (url === '/api/state') return jsonResponse(state);
    throw new Error('Unexpected request: ' + url);
  };
  submitCaseReview(form);
  assertCasePayload(posted);
  assert.equal(posted.summary, earlier);
  navigate('data');
  navigate('investigate');
  editCaseReview({reviewer: 'Analyst Example', decision: 'keep_open', summary: later, acknowledge_limitations: 'on'});
  release(jsonResponse({review_id: 'case-reviewA'}));
  await settle();
  assert.equal(readCaseDraft().summary, later);
  assert.equal(readCaseDraft().schema_version, '2.1');
  assert.notEqual(notice.className, 'notice error');
""")


def test_shipment_chart_uses_the_retained_months_and_actual_counts() -> None:
    run_case_review(r"""
  const chart = run('findingChart(model.run.analysis.findings[1])');
  assert.equal((chart.match(/class="shipment-bar /g) || []).length, 7);
  assert.equal((chart.match(/<strong>1<\/strong>/g) || []).length, 6);
  assert.equal((chart.match(/<strong>10<\/strong>/g) || []).length, 1);
  assert.match(chart, /aria-label="2026-03: 1; 2026-04: 1; 2026-05: 1; 2026-06: 1; 2026-07: 1; 2026-08: 1; 2026-09: 10"/);
  assert.ok(chart.includes('Prior monthly mean: 1. Current count: 10.'));
  assert.ok(!chart.includes('style='), 'The chart must render under the existing CSP without inline styles.');
  assert.equal((chart.match(/<rect /g) || []).length, 7);
  assert.equal(run('findingChart(model.run.analysis.findings[0])'), '', 'Other checks must not receive an invented shipment series.');
""")


def test_shipment_chart_escapes_retained_labels_and_rejects_invalid_counts() -> None:
    run_case_review(r"""
  const hostile = {...caseFindings[1], metrics: {...caseFindings[1].metrics, month: '<img src=x>', prior_mean: '<unverified>'}};
  run(`model.run.analysis.findings[1] = ${JSON.stringify(hostile)};`);
  const chart = run('findingChart(model.run.analysis.findings[1])');
  assert.ok(chart.includes('&lt;img src=x&gt;'));
  assert.ok(chart.includes('&lt;unverified&gt;'));
  assert.ok(!chart.includes('<img src=x>'));
  run('model.run.analysis.findings[1].metrics.current_count = "not a number";');
  assert.equal(run('findingChart(model.run.analysis.findings[1])'), '');
  run('model.run.analysis.findings[1].metrics.current_count = -1;');
  assert.equal(run('findingChart(model.run.analysis.findings[1])'), '');
""")


def test_evidence_tables_show_real_schema_units_links_and_escaped_values() -> None:
    run_case_review(r"""
  const evidence = {offset: 0, total: 5, rows: [
    {kind: 'record', table: 'shipments', id: 'S01', record: {shipment_id: 'S01', date: '2026-09-03', exporter_id: 'E1', qty: '375', unit: 'kg'}},
    {kind: 'record', table: 'payments', id: 'P01', record: {payment_id: 'P01', shipment_id: 'S01', amount: '23000', ccy: 'USD'}},
    {kind: 'record', table: 'ownership', id: 'R01', record: {relationship_id: 'R01', parent_id: 'Parent-Entity', child_id: 'Child-Entity', ownership_percent: '51.5'}},
    {kind: 'record', table: 'diligence', id: 'D01', record: {evidence_id: 'D01', entity_id: 'E1', title: 'Registry <img src=x>', text: 'Supplied registry text.'}},
    {kind: 'source', table: 'source', id: 'List-01', record: {name: 'Listing <script>bad()</script>', list_name: 'Synthetic list', countries: ['US']}},
  ]};
  run(`guidedReviewUi('volume-B').evidence = ${JSON.stringify(evidence)};`);
  const markup = run('findingEvidenceRows(model.run.analysis.findings[1])');
  for (const value of ['375', 'kg', '23000', 'USD', 'S01', 'Parent-Entity', 'Child-Entity', '51.5']) {
    assert.ok(markup.includes('>' + value + '<'), 'Evidence must retain material schema context: ' + value);
  }
  assert.ok(markup.includes('Registry &lt;img src=x&gt;'));
  assert.ok(markup.includes('Listing &lt;script&gt;bad()&lt;/script&gt;'));
  assert.ok(!markup.includes('<img src=x>'));
  assert.ok(!markup.includes('<script>bad()</script>'));
  assert.match(markup, /data-action="source-evidence" data-id="List-01"/);
  assert.match(markup, /data-action="evidence" data-id="P01" data-table="payments"/);
""")


def test_evidence_load_coalesces_pending_requests_and_reuses_the_loaded_page() -> None:
    run_case_review(r"""
  run('Object.assign(model.flow, {findingIndex: 1, inspectionFace: 3, cubeFace: 3, surfaceOpen: true});');
  let release;
  const requested = [];
  fetchImplementation = async url => {
    requested.push(url);
    return new Promise(resolve => {release = resolve;});
  };
  const first = run('loadFindingEvidence(model.run.analysis.findings[1])');
  await run('loadFindingEvidence(model.run.analysis.findings[1])');
  assert.equal(requested.length, 1);
  assert.match(requested[0], /finding-evidence\?finding_id=volume-B&offset=0$/);
  release(jsonResponse({offset: 0, total: 1, rows: [{kind: 'record', table: 'shipments', id: 'S01', record: {shipment_id: 'S01', qty: '375', unit: 'kg'}}]}));
  await first;
  assert.ok(node('#finding-evidence-records').innerHTML.includes('S01'));
  await run('loadFindingEvidence(model.run.analysis.findings[1])');
  assert.equal(requested.length, 1, 'An unchanged retained page should not be fetched repeatedly.');
  assert.equal(run('Object.keys(model.reviewDrafts).length'), 0);
""")


def test_late_evidence_response_cannot_replace_a_different_view() -> None:
    run_case_review(r"""
  let release;
  fetchImplementation = async () => new Promise(resolve => {release = resolve;});
  const pending = run('loadFindingEvidence(model.run.analysis.findings[1])');
  navigate('data');
  const view = main.innerHTML;
  const evidenceRegion = node('#finding-evidence-records').innerHTML;
  release(jsonResponse({offset: 0, total: 1, rows: [{kind: 'record', table: 'shipments', id: 'STALE-S01', record: {shipment_id: 'STALE-S01'}}]}));
  await pending;
  assert.equal(main.innerHTML, view);
  assert.equal(node('#finding-evidence-records').innerHTML, evidenceRegion);
  assert.equal(run('model.page'), 'data');
  assert.equal(run('Object.keys(model.reviewDrafts).length'), 0);
""")


def test_returning_to_a_finding_during_its_request_eventually_shows_its_records() -> (
    None
):
    run_case_review(r"""
  const releases = [];
  fetchImplementation = async url => {
    assert.match(url, /finding-evidence\?finding_id=volume-B&offset=0$/);
    return new Promise(resolve => {releases.push(resolve);});
  };
  click(flowButton('review-step', {index: '1'}));
  assert.equal(releases.length, 1);
  click(flowButton('review-summary'));
  click(flowButton('review-step', {index: '1'}));
  const evidence = {offset: 0, total: 1, rows: [{kind: 'record', table: 'shipments', id: 'RETURNED-S01', record: {shipment_id: 'RETURNED-S01', qty: '375', unit: 'kg'}}]};
  for (const release of releases) release(jsonResponse(evidence));
  await until(() => node('#finding-evidence-records').innerHTML.includes('RETURNED-S01'));
  assert.equal(run('model.flow.findingIndex'), 1);
  assert.equal(run('guidedReviewUi("volume-B").evidenceLoading'), false);
  assert.equal(run('Object.keys(model.reviewDrafts).length'), 0);
""")


def test_evidence_failure_keeps_retry_available_without_recording_a_review() -> None:
    run_case_review(r"""
  run('Object.assign(model.flow, {findingIndex: 1, inspectionFace: 3, cubeFace: 3, surfaceOpen: true});');
  let requests = 0;
  fetchImplementation = async () => {
    requests += 1;
    if (requests === 1) return {...jsonResponse({error: 'Retained file is unavailable.'}), ok: false, status: 404};
    return jsonResponse({offset: 0, total: 1, rows: [{kind: 'record', table: 'shipments', id: 'S01', record: {shipment_id: 'S01'}}]});
  };
  await run('loadFindingEvidence(model.run.analysis.findings[1])');
  assert.ok(node('#finding-evidence-records').innerHTML.includes('Retained file is unavailable.'));
  assert.ok(node('#finding-evidence-records').innerHTML.includes('data-flow="finding-records"'));
  click(flowButton('finding-records', {id: 'volume-B'}));
  await until(() => !run('guidedReviewUi("volume-B").evidenceLoading'));
  assert.equal(requests, 2);
  assert.ok(node('#finding-evidence-records').innerHTML.includes('S01'));
  assert.equal(run('guidedReviewUi("volume-B").evidenceError'), '');
  assert.equal(run('Object.keys(model.reviewDrafts).length'), 0);
""")


@pytest.mark.parametrize("view", ["flowReviewView", "flowFindingsView", "renderReview"])
def test_failed_integrity_suppresses_observation_outcomes_and_evidence_fetch(
    view: str,
) -> None:
    run_case_review(r"""
  run('model.run.verification = {ok: false, issues: ["The retained analysis changed."]};');
  const markup = run('VIEW()');
  assert.ok(/verification|verified|integrity/.test(markup));
  assert.ok(!markup.includes(caseFindings[1].observation));
  assert.ok(!markup.includes(caseFindings[0].observation));
  const requests = [];
  fetchImplementation = async url => {requests.push(url); throw new Error('Unverified evidence must not be fetched.');};
  await run('loadFindingEvidence(model.run.analysis.findings[1])');
  assert.deepEqual(requests, []);
""".replace("VIEW", view))


def test_failed_integrity_never_claims_zero_screening_candidates() -> None:
    run_case_review(r"""
  run(`model.run.verification = {ok: false}; model.run.analysis.findings = []; model.run.analysis.coverage = [{investigation_id: 'screening_candidates', status: 'executed', records_evaluated: 1, findings_count: 0}];`);
  const brief = run('flowScreeningBrief(model.run)');
  assert.ok(!brief.includes('No name or identifier candidates returned'));
  assert.ok(brief.includes('unavailable'));
""")
