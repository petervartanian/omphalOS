"""Exercise guided workflow state through the shipped browser event handlers.

The shared lightweight DOM adapter is intentionally limited to state and escaping
regressions. Browser interaction and layout checks remain separate validation.
"""

from __future__ import annotations

import pytest
from test_frontend_guards import run_scenario

GUIDED_SETUP = r"""
  let guidedSurfaceMarkup = '';
  const htmlDescriptor = Object.getOwnPropertyDescriptor(Element.prototype, 'innerHTML');
  Object.defineProperty(Element.prototype, 'innerHTML', {
    get: htmlDescriptor.get,
    set(value) {
      htmlDescriptor.set.call(this, value);
      if (this.selector === '.object-surface') currentReviewForm = null;
      if (this.selector === '.object-surface' || this.selector === '#main') guidedSurfaceMarkup = String(value);
    },
  });
  context.btoa = (value) => Buffer.from(value, 'binary').toString('base64');
  state.workflow_goals = [
    {id: 'transaction_review', title: 'Review transactions', description: 'Inspect retained transactions.', requires_source: false},
    {id: 'counterparty_screening', title: 'Screen counterparties', description: 'Compare names with a retained list.', requires_source: true},
    {id: 'data_readiness', title: 'Check data readiness', description: 'Inspect missing evidence.', requires_source: false},
  ];
  state.datasets.push({dataset_id: 'datasetB', label: 'Another retained dataset', counts: {entities: 2}, synthetic: false});
  run(`model.state = ${JSON.stringify(state)}; model.flow = newFlow(); Object.assign(model.flow, {stage: 'plan', recordsConfirmed: true, goalId: 'transaction_review', datasetId: 'datasetA', asOf: '2026-10-13'});`);
  function flowButton(action, attributes = {}) {
    const element = button('');
    element.dataset = {flow: action, ...attributes};
    return element;
  }
  function changeControl(id, value, dataset = {}) {
    const target = new Element(id);
    target.id = id;
    target.value = value;
    target.dataset = dataset;
    main.emit('change', {target});
    return target;
  }
  function planned(question = 'Inspect these synthetic records with the proposed checks.') {
    return {
      plan_id: 'planA', can_run: true,
      case: {case_id: 'prepared-case', question},
      selected_checks: [{investigation_id: 'data_quality', title: 'Data quality', parameters: {}, limitations: []}],
      unavailable_checks: [], notes: [], dataset_summary: {counts: {entities: 1}},
      source_status: {selected: false},
    };
  }
  const approvedSources = {signature: 'opaque-test-approval', plan_id: 'planA', records_selected: true, source_accepted: true};
  function previewed(mapping = {Supplier: 'name', Country: 'country'}) {
    return {
      preview_id: 'previewA', file_name: 'suppliers.csv', row_count: 1,
      can_import: true, generated_id_count: 1, mapping,
      columns: Object.entries(mapping).map(([name, target_field]) => ({name, target_field, samples: ['Synthetic value']})),
      target_fields: [{id: 'name', title: 'Company name', required: true}, {id: 'country', title: 'Country', required: false}],
      preview_rows: [{name: 'Synthetic Supplier', country: 'US'}], warnings: [], errors: [], transformations: [],
    };
  }
  function finding(id = 'findingA') {
    return {
      finding_id: id, investigation_id: 'data_quality', title: 'Missing contextual evidence',
      observation: 'The supplied synthetic record omits contextual evidence.',
      record_refs: [], source_refs: [], entity_ids: [], metrics: {},
      unknowns: ['Which retained record establishes the missing context?'],
      alternatives: ['The source export may have omitted an available field.'],
      falsifiers: ['A verified source record supplies the missing context.'],
    };
  }
  function enterReview() {
    const retained = {...runA, latest_review: null, case: {...runA.case, dataset_id: 'datasetA'}, analysis: {...runA.analysis, findings: [finding()]}};
    run(`model.run = ${JSON.stringify(retained)}; model.flow.stage = 'review'; model.flow.reviewIndex = 0; model.reviewDrafts = {};`);
    navigate('investigate');
    return retained;
  }
  function enterLegacyReview() {
    const retained = enterReview();
    click(flowButton('findings-reviewed'));
    run('model.flow.reviewIndex = 0;');
    // These compatibility cases exercise an unfinished 2.0 draft. New reviews
    // use the case-level form covered by test_case_review_frontend.py.
    run(`model.reviewDrafts.runA = {schema_version: '2.0', run_id: 'runA', reviewer: '', summary: '', findings: [], acknowledge_limitations: false}; renderGuided();`);
    return retained;
  }
  function reviewForm(values = {}, general = {}) {
    const fields = {disposition: '', rationale: '', unknowns: '', alternatives: '', falsifiers: '', ...values};
    const controls = Object.fromEntries(Object.keys(fields).map((name) => {
      const control = new Element('[name="' + name + '"]');
      control.name = name;
      Object.defineProperty(control, 'value', {get: () => fields[name], set: (value) => {fields[name] = value;}});
      return [name, control];
    }));
    const group = {
      dataset: {finding: 'findingA'},
      querySelector(selector) { return controls[selector.match(/name="([^"]+)"/)[1]]; },
    };
    currentReviewForm = {
      id: 'review-form', dataset: {}, fields: {reviewer: '', summary: '', ...general},
      querySelectorAll(selector) { return selector === '[data-finding]' ? [group] : []; },
    };
    const form = currentReviewForm;
    Object.values(controls).forEach((control) => {control.closest = (selector) => selector === '#review-form' || selector === 'form' ? form : null;});
    return {form, fields, controls};
  }
  function summaryForm(overrides = {}) {
    const draft = JSON.parse(run('JSON.stringify(model.reviewDrafts[model.selectedRun] || model.run?.latest_review?.review || {})'));
    const fields = {reviewer: draft.reviewer || '', summary: draft.summary || '', ...(draft.acknowledge_limitations ? {acknowledge_limitations: 'on'} : {}), ...overrides};
    const controls = Object.fromEntries(Object.keys(fields).map((name) => {
      const control = new Element('[name="' + name + '"]');
      control.name = name;
      Object.defineProperty(control, 'value', {get: () => fields[name], set: (value) => {fields[name] = value;}});
      return [name, control];
    }));
    const form = {id: 'review-form', dataset: {}, fields, querySelectorAll(selector) {return selector === 'input, select, textarea' ? Object.values(controls) : [];}};
    Object.values(controls).forEach((control) => {control.closest = (selector) => selector === '#review-form' || selector === 'form' ? form : null;});
    currentReviewForm = form;
    return {form, fields, controls};
  }
  function restoreFindingForm() {
    const draft = JSON.parse(run('JSON.stringify(model.reviewDrafts[model.selectedRun] || model.run?.latest_review?.review)'));
    const row = draft.findings[0];
    return reviewForm({...row, unknowns: row.unknowns.join('\n'), alternatives: row.alternatives.join('\n'), falsifiers: row.falsifiers.join('\n')}, {reviewer: draft.reviewer, summary: draft.summary, ...(draft.acknowledge_limitations ? {acknowledge_limitations: 'on'} : {})});
  }
  function guidedButton(action, attributes = {}) {
    const element = button('');
    element.dataset = {guidedReview: action, id: 'findingA', ...attributes};
    return element;
  }
  function fileControl(name, text) {
    const bytes = Buffer.from(text, 'utf8');
    const target = new Element('#flow-vendor-file');
    target.id = 'flow-vendor-file';
    target.files = [{name, size: bytes.length, arrayBuffer: async () => bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength)}];
    const form = {elements: {files: target}};
    target.closest = (selector) => selector === 'form' ? form : null;
    return target;
  }
  async function until(predicate) {
    for (let index = 0; index < 30; index += 1) {
      if (predicate()) return;
      await new Promise((resolve) => setImmediate(resolve));
    }
    throw new Error('Expected state transition did not occur.');
  }
  navigate('investigate');
"""


def run_guided(scenario: str) -> None:
    run_scenario(GUIDED_SETUP + scenario)


@pytest.mark.parametrize("change", ["goal", "date", "source", "navigation"])
def test_delayed_plan_cannot_replace_changed_investigation(change: str) -> None:
    run_guided(r"""
  let release;
  let requested;
  const pending = new Promise((resolve) => { release = resolve; });
  fetchImplementation = async (url, options) => {
    assert.equal(url, '/api/workflow/plan');
    requested = JSON.parse(options.body);
    return pending;
  };
  click(flowButton('plan'));
  assert.equal(requested.dataset_id, 'datasetA');
  if (CHANGE === 'goal') click(flowButton('goal', {goal: 'data_readiness'}));
  if (CHANGE === 'date') changeControl('flow-as-of', '2026-10-14');
  if (CHANGE === 'source') changeControl('flow-source', 'different-snapshot');
  if (CHANGE === 'navigation') navigate('data');
  release(jsonResponse(planned('Obsolete plan that must not be displayed.')));
  await settle();
  assert.equal(run('model.flow.plan'), null, 'An earlier response cannot approve changed inputs.');
  assert.equal(run('model.flow.planInputs'), null);
  assert.ok(!main.innerHTML.includes('Obsolete plan that must not be displayed.'));
  if (CHANGE === 'goal') assert.equal(run('model.flow.goalId'), 'data_readiness');
  if (CHANGE === 'date') assert.equal(run('model.flow.asOf'), '2026-10-14');
  if (CHANGE === 'source') assert.equal(run('model.flow.snapshotId'), 'different-snapshot');
  if (CHANGE === 'navigation') assert.equal(run('model.page'), 'data');
  assert.notEqual(notice.className, 'notice error');
""".replace("CHANGE", repr(change)))


def test_choosing_another_dataset_invalidates_the_previous_runnable_plan() -> None:
    run_guided(r"""
  run(`model.flow.plan = ${JSON.stringify(planned())}; model.flow.planInputs = flowInput();`);
  click(flowButton('back-data'));
  assert.equal(run('model.flow.plan'), null);
  let release;
  const pending = new Promise((resolve) => { release = resolve; });
  let submitted;
  fetchImplementation = async (url, options) => {
    assert.equal(url, '/api/workflow/plan');
    submitted = JSON.parse(options.body);
    return pending;
  };
  click(flowButton('dataset', {id: 'datasetB'}));
  assert.equal(run('model.flow.datasetId'), 'datasetB');
  assert.equal(run('model.flow.plan'), null, 'The old runnable plan must disappear before preparing new records.');
  assert.equal(submitted.dataset_id, 'datasetB');
  release(jsonResponse(planned('Review the second dataset after selecting it.')));
  await settle();
  assert.equal(run('model.flow.planInputs.dataset_id'), 'datasetB');
  assert.equal(run('model.flow.plan.case.question'), 'Review the second dataset after selecting it.');
  assert.equal(run('model.flow.recordsConfirmed'), true);
  assert.equal(run('model.flow.cubeFace'), 1);
  assert.equal(run('model.flow.approval'), null);
  assert.notEqual(notice.className, 'notice error');
""")


@pytest.mark.parametrize("explicit", [False, True])
def test_screening_uses_newest_official_snapshot_or_preserves_user_choice(
    explicit: bool,
) -> None:
    run_guided(r"""
  const sources = [
    {snapshot_id: 'csl-2026-10-12', source_id: 'csl', ingestion_method: 'official_https', fetched_at: '2026-10-12T10:00:00Z', source_updated_at: '2026-10-12T09:00:00Z'},
    {snapshot_id: 'csl-2026-10-13-a', source_id: 'csl', ingestion_method: 'official_https', fetched_at: '2026-10-13T10:00:00Z', source_updated_at: '2026-10-12T09:00:00Z'},
    {snapshot_id: 'csl-2026-10-13-b', source_id: 'csl', ingestion_method: 'official_https', fetched_at: '2026-10-13T10:00:00Z', source_updated_at: '2026-10-13T09:00:00Z'},
    {snapshot_id: 'csl-2026-10-14-manual', source_id: 'csl', ingestion_method: 'manual_import', fetched_at: '2026-10-14T10:00:00Z'},
    {snapshot_id: 'csl-2026-10-15-invalid', source_id: 'csl', ingestion_method: 'official_https', fetched_at: '2026-10-15T10:00:00Z', status: 'invalid'},
    {snapshot_id: 'other-2026-10-16', source_id: 'ofac_sdn', ingestion_method: 'official_https', fetched_at: '2026-10-16T10:00:00Z'},
  ];
  run(`model.state.sources = ${JSON.stringify(sources)};`);
  click(flowButton('goal', {goal: 'counterparty_screening'}));
  if (EXPLICIT) changeControl('flow-source', 'csl-2026-10-14-manual');
  let submitted;
  fetchImplementation = async (url, options) => {
    assert.equal(url, '/api/workflow/plan');
    submitted = JSON.parse(options.body);
    return jsonResponse(planned());
  };
  click(flowButton('dataset', {id: 'datasetA'}));
  await settle();
  assert.equal(submitted.watchlist_snapshot_id, EXPLICIT ? 'csl-2026-10-14-manual' : 'csl-2026-10-13-b');
  assert.equal(run('model.flow.snapshotId'), submitted.watchlist_snapshot_id);
  assert.notEqual(notice.className, 'notice error');
""".replace("EXPLICIT", "true" if explicit else "false"))


def test_mapping_edits_require_a_new_preview_before_import() -> None:
    run_guided(r"""
  const initial = previewed();
  run(`Object.assign(model.flow, {stage: 'data', files: [{name: 'suppliers.csv', content_base64: 'example'}], preview: ${JSON.stringify(initial)}, mapping: ${JSON.stringify(initial.mapping)}});`);
  navigate('investigate');
  changeControl('mapping-1', '', {mapping: 'Country'});
  assert.equal(run('model.flow.previewStale'), true);
  assert.match(main.innerHTML, /data-flow="import" disabled/);
  let requests = [];
  fetchImplementation = async (url, options) => {
    requests.push({url, body: options.body && JSON.parse(options.body)});
    if (url === '/api/workflow/preview') return jsonResponse({...previewed({Supplier: 'name', Country: null}), preview_id: 'previewB'});
    if (url === '/api/workflow/import') return jsonResponse(state.datasets[1]);
    if (url === '/api/state') return jsonResponse(state);
    if (url === '/api/workflow/plan') return jsonResponse(planned());
    if (url === '/api/workflow/run') return jsonResponse({run_id: 'runA'});
    if (url === '/api/runs/runA') return jsonResponse({...runA, latest_review: null});
    throw new Error('Unexpected request: ' + url);
  };
  // The event handler also protects a stale preview if a stale control is invoked.
  click(flowButton('import'));
  await settle();
  assert.equal(requests.length, 0, 'A changed mapping cannot reach the import endpoint.');
  assert.match(notice.textContent, /Update and review the preview/);
  click(flowButton('repreview'));
  await settle();
  assert.equal(requests[0].url, '/api/workflow/preview');
  assert.equal(requests[0].body.mapping.Country, null);
  assert.equal(run('model.flow.previewStale'), false);
  click(flowButton('import'));
  await settle();
  const imported = requests.find((request) => request.url === '/api/workflow/import');
  assert.equal(imported.body.preview_id, 'previewB');
  assert.deepEqual(imported.body.mapping, {Supplier: 'name', Country: null});
  assert.equal(run('model.flow.stage'), 'plan');
  assert.equal(run('model.flow.cubeFace'), 1);
  assert.equal(run('model.flow.recordsConfirmed'), true);
  assert.equal(run('model.flow.approval'), null);
  assert.equal(requests.filter(request => request.url === '/api/workflow/run').length, 0);
  assert.equal(run('Object.keys(model.reviewDrafts).length'), 0);
  assert.notEqual(notice.className, 'notice error');
""")


def test_preview_from_older_mapping_cannot_approve_newer_mapping() -> None:
    run_guided(r"""
  const initial = previewed();
  run(`Object.assign(model.flow, {stage: 'data', files: [], preview: ${JSON.stringify(initial)}, mapping: ${JSON.stringify(initial.mapping)}});`);
  navigate('investigate');
  changeControl('mapping-1', '', {mapping: 'Country'});
  let release;
  const pending = new Promise((resolve) => { release = resolve; });
  fetchImplementation = async (url) => {
    assert.equal(url, '/api/workflow/preview');
    return pending;
  };
  click(flowButton('repreview'));
  changeControl('mapping-1', 'country', {mapping: 'Country'});
  release(jsonResponse({...previewed({Supplier: 'name', Country: null}), preview_id: 'obsolete-preview'}));
  await settle();
  assert.equal(run('model.flow.mapping.Country'), 'country');
  assert.equal(run('model.flow.previewStale'), true);
  assert.notEqual(run('model.flow.preview.preview_id'), 'obsolete-preview');
  assert.match(main.innerHTML, /data-flow="import" disabled/);
""")


def test_uploaded_columns_values_and_prototype_named_headers_are_safe() -> None:
    run_guided(r"""
  const hostileHeader = '"><img src=x onerror="injected()">';
  const hostileValue = '</td><script>injected()</script><td>';
  const mapping = Object.fromEntries([['__proto__', null], [hostileHeader, 'name']]);
  const preview = previewed(mapping);
  preview.columns.forEach((column) => { column.samples = [hostileValue]; });
  preview.file_name = '<svg onload="injected()">.csv';
  preview.preview_rows = [{name: hostileValue}];
  preview.warnings = [hostileHeader];
  run(`Object.assign(model.flow, {stage: 'data', preview: JSON.parse(${JSON.stringify(JSON.stringify(preview))}), mapping: JSON.parse(${JSON.stringify(JSON.stringify(mapping))})});`);
  navigate('investigate');
  assert.ok(!main.innerHTML.includes('<script>injected()'));
  assert.ok(!main.innerHTML.includes('<img src=x'));
  assert.ok(!main.innerHTML.includes('<svg onload='));
  assert.ok(main.innerHTML.includes('&lt;script&gt;injected()&lt;/script&gt;'));
  assert.ok(main.innerHTML.includes('data-mapping="&quot;&gt;&lt;img src=x onerror=&quot;injected()&quot;&gt;"'));
  changeControl('mapping-0', 'country', {mapping: '__proto__'});
  assert.equal(run('Object.hasOwn(model.flow.mapping, "__proto__")'), true);
  assert.equal(run('model.flow.mapping["__proto__"]'), 'country');
  assert.equal(run('Object.getPrototypeOf(model.flow.mapping) === Object.prototype'), true);
  assert.equal(run('Object.prototype.country'), undefined);
  let submitted;
  fetchImplementation = async (url, options) => {
    assert.equal(url, '/api/workflow/preview');
    submitted = JSON.parse(options.body);
    return jsonResponse(previewed(submitted.mapping));
  };
  click(flowButton('repreview'));
  await settle();
  assert.equal(Object.hasOwn(submitted.mapping, '__proto__'), true);
  assert.equal(submitted.mapping.__proto__, 'country');
  assert.equal(submitted.mapping[hostileHeader], 'name');
  assert.equal(run('Object.hasOwn(model.flow.mapping, "__proto__")'), true);
  assert.notEqual(notice.className, 'notice error');
""")


def test_legacy_new_review_is_blank_until_explicit_suggestions_are_requested() -> None:
    run_guided(r"""
  const retained = enterLegacyReview();
  assert.equal(run('Object.keys(model.reviewDrafts).length'), 1);
  for (const field of ['rationale', 'unknowns', 'alternatives', 'falsifiers']) {
    assert.match(main.innerHTML, new RegExp('name="' + field + '"[^>]*></textarea>'), 'New assessment fields must be empty: ' + field);
  }
  assert.ok(!/data-disposition="(?:follow_up|explained|escalate)" aria-pressed="true"/.test(main.innerHTML));
  assert.match(main.innerHTML, /<textarea name="rationale" hidden/);
  assert.ok(main.innerHTML.includes('proposed-rationale'));
  assert.ok(main.innerHTML.includes(retained.analysis.findings[0].observation));
  reviewForm();
  let requests = 0;
  fetchImplementation = async () => { requests += 1; throw new Error('Suggestions must not save a review.'); };
  click(button('suggest-questions', 'findingA'));
  const draft = JSON.parse(run('JSON.stringify(model.reviewDrafts.runA)'));
  assert.equal(draft.reviewer, '');
  assert.equal(draft.summary, '');
  assert.equal(draft.acknowledge_limitations, false);
  assert.equal(draft.findings[0].disposition, '');
  assert.equal(draft.findings[0].rationale, '');
  for (const field of ['unknowns', 'alternatives', 'falsifiers']) {
    assert.deepEqual(draft.findings[0][field], retained.analysis.findings[0][field]);
  }
  assert.equal(requests, 0);
  assert.equal(run('reviewRowComplete(model.reviewDrafts.runA.findings[0])'), false);
""")


def test_legacy_suggested_questions_preserve_authored_assessment_and_nonempty_fields() -> (
    None
):
    run_guided(r"""
  const retained = enterLegacyReview();
  reviewForm({disposition: 'follow_up', rationale: 'The analyst requests the retained original records.', unknowns: 'Who supplied the verified export and when?', alternatives: '', falsifiers: 'A verified source record contradicts this observation.'}, {reviewer: 'Synthetic Reviewer', summary: 'An authored assessment remains subject to follow-up.', acknowledge_limitations: 'on'});
  click(button('suggest-questions', 'findingA'));
  const draft = JSON.parse(run('JSON.stringify(model.reviewDrafts.runA)'));
  assert.equal(draft.reviewer, 'Synthetic Reviewer');
  assert.equal(draft.summary, 'An authored assessment remains subject to follow-up.');
  assert.equal(draft.acknowledge_limitations, true);
  const row = draft.findings[0];
  assert.equal(row.disposition, 'follow_up');
  assert.equal(row.rationale, 'The analyst requests the retained original records.');
  assert.deepEqual(row.unknowns, ['Who supplied the verified export and when?']);
  assert.deepEqual(row.falsifiers, ['A verified source record contradicts this observation.']);
  assert.deepEqual(row.alternatives, retained.analysis.findings[0].alternatives);
  const unload = {prevented: false, preventDefault() {this.prevented = true;}};
  window.emit('beforeunload', unload);
  assert.ok(unload.prevented, 'Suggested questions create an unsaved draft, not a saved review.');
""")


@pytest.mark.parametrize("interaction", ["click", "keyboard"])
def test_legacy_stage_navigation_preserves_and_restores_the_review_draft(
    interaction: str,
) -> None:
    run_guided(r"""
  enterLegacyReview();
  const {form, fields} = reviewForm({rationale: 'An unfinished analyst rationale must stay in the form.'});
  main.emit('input', {target: {name: 'rationale', closest: (selector) => selector === '#review-form' ? form : null}});
  const draft = run('JSON.stringify(model.reviewDrafts.runA)');
  const markup = main.innerHTML;
  const revision = run('model.flow.revision');
  if (INTERACTION === 'click') click(flowButton('cube', {face: '3'}));
  if (INTERACTION === 'keyboard') {
    let prevented = false;
    main.emit('keydown', {target: flowButton('cube', {face: '0'}), key: 'End', preventDefault() {prevented = true;}});
    assert.ok(prevented);
    assert.equal(node('.cube-controls [data-face="4"]').focusCount, 1, 'End selects the last available stage; an unsaved assessment cannot open Package.');
  }
  assert.equal(main.innerHTML, markup, 'Face navigation updates the working surface without replacing the central object.');
  assert.equal(fields.rationale, 'An unfinished analyst rationale must stay in the form.');
  assert.equal(run('JSON.stringify(model.reviewDrafts.runA)'), draft);
  assert.equal(run('model.flow.revision'), revision);
  if (INTERACTION === 'click') assert.equal(run('model.flow.cubeFace'), 3);
  if (INTERACTION === 'keyboard') assert.equal(run('model.flow.cubeFace'), 4);
  assert.equal(currentReviewForm, null, 'Opening another face removes the live form after retaining its draft.');
  click(flowButton('cube', {face: '4'}));
  assert.ok(node('.object-surface').innerHTML.includes('An unfinished analyst rationale must stay in the form.'));
  assert.ok(node('.object-surface').innerHTML.includes('id="review-form"'));
  assert.equal(run('JSON.stringify(model.reviewDrafts.runA)'), draft);
""".replace("INTERACTION", repr(interaction)))


@pytest.mark.parametrize(
    ("action", "disposition"),
    [
        ("adopt-follow-up", "follow_up"),
        ("adopt-escalation", "escalate"),
        ("explain", "explained"),
    ],
)
def test_legacy_guided_action_preserves_authored_reasoning_and_context(
    action: str, disposition: str
) -> None:
    run_guided(r"""
  const retained = enterLegacyReview();
  const {fields} = reviewForm({rationale: 'Preserve the analyst reasoning already entered.', unknowns: 'Who supplied the verified original record?', falsifiers: 'An independently authenticated invoice would change this assessment.'});
  assert.equal(run('Object.keys(model.reviewDrafts).length'), 1);
  let requests = 0;
  fetchImplementation = async () => {requests += 1; throw new Error('A choice does not save a review.');};
  click(guidedButton(ACTION));
  assert.equal(fields.disposition, CHOICE, 'The actual hidden control must receive the explicit selection.');
  const row = JSON.parse(run('JSON.stringify(model.reviewDrafts.runA.findings[0])'));
  assert.equal(row.disposition, CHOICE);
  assert.equal(row.rationale, 'Preserve the analyst reasoning already entered.');
  assert.deepEqual(row.unknowns, ['Who supplied the verified original record?']);
  assert.deepEqual(row.alternatives, ACTION === 'explain' ? [] : retained.analysis.findings[0].alternatives);
  assert.deepEqual(row.falsifiers, ['An independently authenticated invoice would change this assessment.']);
  assert.equal(requests, 0);
  assert.equal(run('model.reviewDrafts.runA.acknowledge_limitations'), false);
  assert.match(main.innerHTML, new RegExp('data-disposition="' + CHOICE + '" aria-pressed="true"'));
""".replace("CHOICE", repr(disposition)).replace("ACTION", repr(action)))


@pytest.mark.parametrize(
    ("action", "disposition"),
    [("adopt-follow-up", "follow_up"), ("adopt-escalation", "escalate")],
)
def test_legacy_proposed_assessment_is_adopted_only_by_an_explicit_action(
    action: str, disposition: str
) -> None:
    run_guided(r"""
  const retained = enterLegacyReview();
  const {fields} = reviewForm();
  assert.equal(fields.disposition, '');
  assert.equal(fields.rationale, '');
  assert.equal(run('Object.keys(model.reviewDrafts).length'), 1);
  let requests = 0;
  fetchImplementation = async () => {requests += 1; throw new Error('Adopting a draft cannot save it.');};
  click(guidedButton(ACTION));
  const draft = JSON.parse(run('JSON.stringify(model.reviewDrafts.runA)'));
  const row = draft.findings[0];
  assert.equal(row.disposition, CHOICE);
  assert.ok(row.rationale.includes(retained.analysis.findings[0].observation));
  assert.ok(row.rationale.includes(retained.analysis.findings[0].unknowns[0]));
  assert.ok(row.rationale.includes(retained.analysis.findings[0].falsifiers[0]));
  assert.ok(row.rationale.startsWith(ACTION === 'adopt-escalation' ? 'Request specialist review' : 'Keep this observation open'));
  for (const key of ['unknowns', 'alternatives', 'falsifiers']) assert.deepEqual(row[key], retained.analysis.findings[0][key]);
  assert.equal(draft.reviewer, '');
  assert.equal(draft.summary, '');
  assert.equal(draft.acknowledge_limitations, false);
  assert.equal(requests, 0);
  assert.equal(run('reviewRowComplete(model.reviewDrafts.runA.findings[0])'), true);
  assert.match(main.innerHTML, /<textarea name="rationale" hidden/);
""".replace("CHOICE", repr(disposition)).replace("ACTION", repr(action)))


def test_legacy_explanation_needs_reasoning_beyond_the_prepared_open_followup() -> None:
    run_guided(r"""
  enterLegacyReview();
  reviewForm();
  click(guidedButton('adopt-follow-up'));
  const prepared = JSON.parse(run('JSON.stringify(model.reviewDrafts.runA.findings[0])'));
  reviewForm({...prepared, unknowns: prepared.unknowns.join('\n'), alternatives: prepared.alternatives.join('\n'), falsifiers: prepared.falsifiers.join('\n')});
  click(guidedButton('explain'));
  const explained = JSON.parse(run('JSON.stringify(model.reviewDrafts.runA.findings[0])'));
  assert.equal(explained.disposition, 'explained');
  assert.equal(explained.rationale, '', 'A prepared request for more evidence cannot stand in for an explanation.');
  assert.equal(run('guidedReviewUi("findingA").previousPreparedRationale'), prepared.rationale);
  assert.equal(run('guidedReviewUi("findingA").editing.rationale'), true);
  assert.equal(run('reviewRowComplete(model.reviewDrafts.runA.findings[0])'), false);
  assert.match(main.innerHTML, /id="guided-rationale-0" name="rationale" rows="4"/);
  assert.ok(main.innerHTML.includes('What evidence explains this observation?'));
""")


def test_legacy_editing_a_proposal_does_not_select_an_action_or_replace_user_edits() -> (
    None
):
    run_guided(r"""
  enterLegacyReview();
  reviewForm();
  click(guidedButton('edit-rationale', {index: '0'}));
  const draft = JSON.parse(run('JSON.stringify(model.reviewDrafts.runA.findings[0])'));
  assert.equal(draft.disposition, '');
  assert.ok(draft.rationale.includes('The retained analysis reports:'));
  assert.deepEqual(draft.unknowns, []);
  const edited = reviewForm({...draft, unknowns: '', alternatives: '', falsifiers: ''});
  edited.controls.rationale.value = 'Request the original signed invoice and compare its payment schedule.';
  main.emit('input', {target: edited.controls.rationale});
  click(guidedButton('adopt-escalation'));
  assert.equal(run('model.reviewDrafts.runA.findings[0].rationale'), 'Request the original signed invoice and compare its payment schedule.');
  assert.equal(run('model.reviewDrafts.runA.findings[0].disposition'), 'escalate');
""")


def test_legacy_prompt_editor_preserves_untouched_categories_and_explicit_adoption() -> (
    None
):
    run_guided(r"""
  const retained = enterLegacyReview();
  reviewForm();
  click(guidedButton('edit-prompt', {field: 'unknowns', index: '0'}));
  assert.equal(run('Object.keys(model.reviewDrafts).length'), 1, 'Opening an editor cannot adopt a suggested answer.');
  assert.match(main.innerHTML, /id="guided-unknowns-0" name="unknowns" rows="3"/);
  assert.match(main.innerHTML, /<textarea name="alternatives" hidden/);
  assert.ok(!main.innerHTML.includes('<details'));
  const edited = reviewForm();
  edited.controls.unknowns.value = 'Who can supply the original contract and delivery record?';
  main.emit('input', {target: edited.controls.unknowns});
  click(guidedButton('finish-edit', {field: 'unknowns', index: '0'}));
  assert.equal(run('guidedReviewUi("findingA").editing.unknowns'), false);
  assert.ok(main.innerHTML.includes('Who can supply the original contract and delivery record?'));
  assert.match(main.innerHTML, /<textarea name="unknowns" hidden/);
  const rowBefore = JSON.parse(run('JSON.stringify(model.reviewDrafts.runA.findings[0])'));
  assert.deepEqual(rowBefore.alternatives, []);
  assert.deepEqual(rowBefore.falsifiers, []);
  reviewForm({unknowns: rowBefore.unknowns.join('\n')});
  click(button('suggest-questions', 'findingA'));
  const rowAfter = JSON.parse(run('JSON.stringify(model.reviewDrafts.runA.findings[0])'));
  assert.deepEqual(rowAfter.unknowns, rowBefore.unknowns);
  assert.deepEqual(rowAfter.alternatives, retained.analysis.findings[0].alternatives);
  assert.deepEqual(rowAfter.falsifiers, retained.analysis.findings[0].falsifiers);
  assert.equal(rowAfter.disposition, '');
  assert.equal(rowAfter.rationale, '');
""")


@pytest.mark.parametrize("explicit", [False, True])
def test_purpose_tracks_records_unless_the_analyst_selected_it(explicit: bool) -> None:
    run_guided(r"""
  run("model.flow = newFlow(); model.flow.stage = 'data'; model.state.datasets[0].counts = {entities: 1, payments: 3, shipments: 2};");
  if (EXPLICIT) click(flowButton('goal', {goal: 'data_readiness'}));
  const payloads = [];
  fetchImplementation = async (url, options) => {
    assert.equal(url, '/api/workflow/plan');
    payloads.push(JSON.parse(options.body));
    return jsonResponse(planned());
  };
  click(flowButton('dataset', {id: 'datasetA'}));
  await settle();
  assert.equal(payloads[0].goal_id, EXPLICIT ? 'data_readiness' : 'transaction_review');
  click(flowButton('back-data'));
  click(flowButton('dataset', {id: 'datasetB'}));
  await settle();
  assert.equal(payloads[1].goal_id, EXPLICIT ? 'data_readiness' : 'counterparty_screening');
""".replace("EXPLICIT", "true" if explicit else "false"))


def test_file_selection_starts_preview_without_an_extra_submit() -> None:
    run_guided(r"""
  run("model.flow = newFlow(); model.flow.stage = 'data';");
  const requests = [];
  fetchImplementation = async (url, options) => {
    assert.equal(url, '/api/workflow/preview');
    requests.push(JSON.parse(options.body));
    return jsonResponse(previewed());
  };
  main.emit('change', {target: fileControl('suppliers.csv', 'Supplier,Country\nSynthetic Supplier,US\n')});
  await settle();
  assert.equal(requests.length, 1);
  assert.equal(requests[0].files[0].name, 'suppliers.csv');
  assert.equal(Buffer.from(requests[0].files[0].content_base64, 'base64').toString('utf8'), 'Supplier,Country\nSynthetic Supplier,US\n');
  assert.equal(run('model.flow.preview.preview_id'), 'previewA');
  assert.equal(run('model.flow.previewStale'), false);
  assert.equal(run('model.flow.datasetId'), '', 'A preview must not silently import the selected file.');
""")


def test_unavailable_stage_cannot_take_over_a_pending_import_preview() -> None:
    run_guided(r"""
  run("model.flow = newFlow(); model.flow.stage = 'data';");
  let release;
  let requested = false;
  fetchImplementation = async (url) => {
    assert.equal(url, '/api/workflow/preview');
    requested = true;
    return new Promise((resolve) => {release = resolve;});
  };
  main.emit('change', {target: fileControl('suppliers.csv', 'Supplier\nSynthetic Supplier\n')});
  await until(() => requested);
  const navigation = run('model.navigationVersion');
  click(flowButton('cube', {face: '4'}));
  assert.equal(run('model.flow.inspectionFace'), null);
  assert.equal(run('model.navigationVersion'), navigation, 'A blocked future stage cannot invalidate the active preview.');
  release(jsonResponse(previewed()));
  await settle();
  assert.equal(run('model.flow.inspectionFace'), null);
  assert.equal(run('model.flow.cubeFace'), 0);
  assert.ok(guidedSurfaceMarkup.includes('data-flow="import"'), 'The completed preview remains available in the Records stage.');
  assert.equal(run('Object.keys(model.reviewDrafts).length'), 0);
""")


def test_busy_file_selection_cannot_invalidate_the_active_preview() -> None:
    run_guided(r"""
  run("model.flow = newFlow(); model.flow.stage = 'data';");
  let release;
  const requested = [];
  fetchImplementation = async (url, options) => {
    assert.equal(url, '/api/workflow/preview');
    const payload = JSON.parse(options.body);
    requested.push(payload.files[0].name);
    if (requested.length === 1) return new Promise((resolve) => {release = resolve;});
    return jsonResponse({...previewed(), preview_id: 'second-preview', file_name: 'second.csv'});
  };
  main.emit('change', {target: fileControl('first.csv', 'Supplier\nFirst Synthetic Supplier\n')});
  await until(() => requested.length === 1);
  const revision = run('model.flow.revision');
  const ownedFiles = run('JSON.stringify(model.flow.files)');
  // File inputs are disabled while processing. A late change event must also be
  // rejected before it can invalidate the operation that owns the current file.
  main.emit('change', {target: fileControl('second.csv', 'Supplier\nSecond Synthetic Supplier\n')});
  assert.equal(run('model.flow.revision'), revision);
  assert.equal(run('JSON.stringify(model.flow.files)'), ownedFiles);
  release(jsonResponse({...previewed(), preview_id: 'first-preview', file_name: 'first.csv'}));
  await settle();
  assert.deepEqual(requested, ['first.csv']);
  assert.equal(run('model.flow.preview.preview_id'), 'first-preview');
  assert.equal(run('model.flow.files[0].name'), 'first.csv');
  assert.equal(run('model.flow.previewStale'), false);
""")


def test_legacy_evidence_paging_keeps_the_assessment_and_reaches_later_citations() -> (
    None
):
    run_guided(r"""
  const retained = enterLegacyReview();
  retained.analysis.findings[0].record_refs = Array.from({length: 45}, (_, index) => ({table: 'payments', record_id: 'payment-' + index}));
  run(`model.run = ${JSON.stringify(retained)};`);
  click(flowButton('findings-reviewed'));
  run('model.flow.reviewIndex = 0;');
  navigate('investigate');
  const {controls} = reviewForm({rationale: 'The analyst is checking the cited payment documents.'});
  main.emit('input', {target: controls.rationale});
  const saved = run('JSON.stringify(model.reviewDrafts.runA)');
  assert.equal((main.innerHTML.match(/data-action="evidence"/g) || []).length, 1);
  click(guidedButton('evidence-step', {index: '44'}));
  assert.equal(run('guidedReviewUi("findingA").evidenceIndex'), 44);
  assert.match(main.innerHTML, /data-action="evidence" data-id="payment-44" data-table="payments"/);
  assert.ok(main.innerHTML.includes('Cited record 45 of 45'));
  assert.equal((main.innerHTML.match(/data-action="evidence"/g) || []).length, 1);
  assert.equal(run('JSON.stringify(model.reviewDrafts.runA)'), saved);
""")


def test_new_investigation_faces_do_not_display_an_unrelated_retained_run() -> None:
    run_guided(r"""
  const retained = enterReview();
  const title = retained.analysis.findings[0].title;
  click(flowButton('restart'));
  click(flowButton('cube', {face: '3'}));
  assert.ok(!node('.object-surface').innerHTML.includes(title));
  assert.equal(run('flowCubeFaces()[3].value'), '—');
  assert.ok(!node('.object-surface').innerHTML.includes('data-flow="review-step"'));
""")


def test_archived_screening_is_not_erased_by_missing_live_source_metadata() -> None:
    run_guided(r"""
  const retained = enterReview();
  retained.case.watchlist_snapshot_id = 'archived-only-csl';
  run(`model.run = ${JSON.stringify(retained)}; model.state.sources = [];`);
  click(flowButton('cube', {face: '1'}));
  const contents = node('.object-surface').innerHTML;
  assert.ok(contents.includes('archived-only-csl'));
  assert.ok(contents.includes('retained in this run'));
  assert.ok(!contents.includes('No reference list was used'));
  assert.ok(!contents.includes('did not perform list screening'));
""")


def test_landing_action_opens_the_file_picker_after_rendering_the_intake() -> None:
    run_guided(r"""
  run('model.flow = newFlow(); renderGuided();');
  assert.ok(!main.innerHTML.includes('data-flow="goal"'), 'A new user should not have to classify the investigation before supplying records.');
  let opened = 0;
  node('#flow-vendor-file').click = () => {
    opened += 1;
    assert.equal(run('model.flow.stage'), 'data');
    assert.ok(main.innerHTML.includes('id="flow-vendor-file"'), 'The file control must exist before its native click.');
  };
  click(flowButton('choose-file'));
  assert.equal(opened, 1);
  assert.equal(run('model.flow.goalId'), '');
""")


def test_retained_records_require_source_and_plan_approval_then_findings_review() -> (
    None
):
    run_guided(r"""
  const records = {dataset_id: 'retained-fixture', label: 'Retained test records', counts: {entities: 2, shipments: 3, payments: 4}, synthetic: true};
  state.datasets.push(records);
  run(`model.state = ${JSON.stringify(state)}; model.flow = newFlow(); renderGuided();`);
  const retained = {...runA, latest_review: null, manifest: {...runA.manifest, run_id: 'retained-run'}, case: {...runA.case, dataset_id: records.dataset_id}, dataset_metadata: {...records}, analysis: {...runA.analysis, findings: [finding()]}};
  const requests = [];
  fetchImplementation = async (url, options) => {
    requests.push({url, payload: options?.body ? JSON.parse(options.body) : null});
    if (url === '/api/state') return jsonResponse(state);
    if (url === '/api/workflow/plan') return jsonResponse(planned());
    if (url === '/api/workflow/approve') return jsonResponse({approval: approvedSources});
    if (url === '/api/workflow/run') return jsonResponse({run_id: 'retained-run'});
    if (url === '/api/runs/retained-run') return jsonResponse(retained);
    throw new Error('Unexpected request: ' + url);
  };
  click(flowButton('investigate-dataset', {id: records.dataset_id}));
  await settle();
  assert.equal(run('model.flow.cubeFace'), 1);
  assert.equal(run('model.flow.recordsConfirmed'), true);
  assert.equal(run('flowStageAccess(2)'), false);
  assert.equal(requests.filter(item => item.url === '/api/workflow/run').length, 0);
  assert.equal(requests.filter(item => item.url === '/api/workflow/approve').length, 0);
  click(flowButton('approve-sources'));
  await settle();
  const acceptance = requests.find(item => item.url === '/api/workflow/approve').payload;
  assert.deepEqual(acceptance, {dataset_id: records.dataset_id, goal_id: 'transaction_review', as_of: run('model.flow.asOf'), plan_id: 'planA', case_id: 'prepared-case', acknowledge_records: true, acknowledge_source: true});
  assert.equal(run('model.flow.cubeFace'), 2);
  assert.equal(run('flowCubeFaces()[2].complete'), false, 'Preparing or opening Plan is not approval to execute.');
  assert.equal(requests.filter(item => item.url === '/api/workflow/run').length, 0);
  click(flowButton('run'));
  await settle();
  assert.equal(requests.filter(item => item.url === '/api/workflow/run').length, 1);
  const execution = requests.find(item => item.url === '/api/workflow/run').payload;
  assert.equal(execution.dataset_id, records.dataset_id);
  assert.equal(execution.goal_id, 'transaction_review');
  assert.equal(execution.plan_id, 'planA');
  assert.deepEqual(execution.approval, approvedSources);
  assert.equal(execution.acknowledge_plan, true);
  assert.equal(run('model.selectedRun'), 'retained-run');
  assert.equal(run('model.flow.stage'), 'review');
  assert.equal(run('model.flow.cubeFace'), 3);
  assert.equal(run('Object.keys(model.reviewDrafts).length'), 0);
  assert.equal(run('model.run.latest_review'), null);
  assert.ok(!requests.some(item => item.url.endsWith('/review')));
  click(flowButton('review-step', {index: '0'}));
  assert.ok(main.innerHTML.includes('class="finding-detail"'));
  assert.ok(!main.innerHTML.includes('name="disposition"'));
  assert.ok(!main.innerHTML.includes('proposed-rationale'));
  assert.equal(run('Object.keys(model.reviewDrafts).length'), 0);
  assert.equal(run('flowResultsReviewed(model.run)'), false);
  assert.equal(run('flowStageAccess(4)'), false);
  click(flowButton('findings-reviewed'));
  assert.equal(run('flowResultsReviewed(model.run)'), true);
  assert.equal(run('model.flow.cubeFace'), 4);
  assert.ok(main.innerHTML.includes('data-review-scope="case"'));
  assert.ok(!/name="decision"[^>]*checked/.test(main.innerHTML));
  assert.ok(!/name="acknowledge_limitations"[^>]*checked/.test(main.innerHTML));
""")


@pytest.mark.parametrize("interrupt_at", ["import", "plan"])
def test_navigation_during_linked_import_prevents_automatic_execution(
    interrupt_at: str,
) -> None:
    run_guided(r"""
  run('model.flow = newFlow(); renderGuided();');
  const records = {dataset_id: 'imported-fixture', counts: {entities: 1, payments: 2}, synthetic: true};
  state.datasets.push(records);
  let release;
  let waiting = false;
  const requests = [];
  fetchImplementation = async (url) => {
    requests.push(url);
    if (url === '/api/state') return jsonResponse(state);
    if (url === '/api/datasets/import') {
      if (PHASE !== 'import') return jsonResponse(records);
      waiting = true;
      return new Promise(resolve => {release = () => resolve(jsonResponse(records));});
    }
    if (url === '/api/workflow/plan') {
      waiting = true;
      return new Promise(resolve => {release = () => resolve(jsonResponse(planned()));});
    }
    throw new Error('Execution must not begin after navigation: ' + url);
  };
  main.emit('change', {target: fileControl('dataset.json', '{"tables":{"entities":[{"entity_id":"E1","name":"Synthetic fixture"}]}}')});
  await until(() => waiting);
  navigate('data');
  release();
  await settle();
  assert.equal(run('model.page'), 'data');
  assert.ok(!requests.includes('/api/workflow/run'));
  if (PHASE === 'import') assert.ok(!requests.includes('/api/workflow/plan'), 'Leaving during import must also stop automatic planning.');
  assert.equal(run('model.flow.plan'), null);
  assert.equal(run('Object.keys(model.reviewDrafts).length'), 0);
  assert.notEqual(notice.className, 'notice error');
""".replace("PHASE", repr(interrupt_at)))


@pytest.mark.parametrize("action", ["fetch", "fetch-run"])
def test_source_download_prepares_sources_without_accepting_or_running_them(
    action: str,
) -> None:
    run_guided(r"""
  run("model.flow.goalId = 'counterparty_screening'; model.flow.snapshotId = ''; model.flow.plan = null;");
  const snapshot = {snapshot_id: 'fresh-csl', source_id: 'csl', ingestion_method: 'official_https', fetched_at: '2026-10-14T12:00:00Z', record_count: 1};
  const retained = {...runA, latest_review: null, case: {...runA.case, dataset_id: 'datasetA', watchlist_snapshot_id: snapshot.snapshot_id}, analysis: {...runA.analysis, findings: []}};
  const requests = [];
  fetchImplementation = async (url, options) => {
    requests.push(url);
    if (url === '/api/sources/fetch') {state.sources.push(snapshot); return jsonResponse(snapshot);}
    if (url === '/api/state') return jsonResponse(state);
    if (url === '/api/workflow/plan') return jsonResponse({...planned(), source_status: {...snapshot, selected: true}});
    if (url === '/api/workflow/run') {assert.equal(JSON.parse(options.body).watchlist_snapshot_id, 'fresh-csl'); return jsonResponse({run_id: 'runA'});}
    if (url === '/api/runs/runA') return jsonResponse(retained);
    throw new Error('Unexpected request: ' + url);
  };
  click(flowButton(ACTION));
  await settle();
  assert.equal(requests.includes('/api/workflow/run'), false);
  assert.equal(run('model.flow.stage'), 'plan');
  assert.equal(run('model.flow.cubeFace'), 1);
  assert.equal(run('flowSourcesAccepted()'), false);
  assert.equal(run('flowStageAccess(2)'), false);
  assert.equal(run('Object.keys(model.reviewDrafts).length'), 0);
""".replace("ACTION", repr(action)))


def test_legacy_incomplete_observations_prevent_summary_adoption() -> None:
    run_guided(r"""
  enterLegacyReview();
  click(flowButton('review-summary'));
  summaryForm();
  assert.ok(main.innerHTML.includes('data-flow="summary-adopt"'));
  assert.match(main.innerHTML, /<textarea name="summary" hidden[^>]*><\/textarea>/);
  assert.match(main.innerHTML, /data-flow="summary-adopt" disabled/);
  assert.equal(run('Object.keys(model.reviewDrafts).length'), 1);
  click(flowButton('summary-adopt'));
  assert.equal(run('Object.keys(model.reviewDrafts).length'), 1, 'Even a stale adoption control cannot summarize incomplete assessments.');
""")


def test_legacy_summary_adoption_preserves_empty_reviewer_and_unchecked_acknowledgment() -> (
    None
):
    run_guided(r"""
  enterLegacyReview();
  reviewForm();
  click(guidedButton('adopt-follow-up'));
  click(flowButton('review-summary'));
  summaryForm();
  assert.equal(run('model.reviewDrafts.runA.summary'), '');
  let requests = 0;
  fetchImplementation = async () => {requests += 1; throw new Error('Adoption is not a save.');};
  click(flowButton('summary-adopt'));
  const draft = JSON.parse(run('JSON.stringify(model.reviewDrafts.runA)'));
  assert.ok(draft.summary.includes('1 for follow-up, 0 for escalation, and 0 as explained'));
  assert.equal(draft.reviewer, '');
  assert.equal(draft.acknowledge_limitations, false);
  assert.equal(requests, 0);
  assert.equal(run('flowSummaryNeedsUpdate(model.reviewDrafts.runA)'), false);
""")


def test_legacy_prepared_summary_never_replaces_authored_summary_text() -> None:
    run_guided(r"""
  enterLegacyReview();
  reviewForm();
  click(guidedButton('adopt-follow-up'));
  click(flowButton('review-summary'));
  const authored = summaryForm({reviewer: 'Synthetic Reviewer', summary: 'The analyst has specified an original sequence of evidence requests.', acknowledge_limitations: 'on'});
  main.emit('input', {target: authored.controls.summary});
  click(flowButton('summary-adopt'));
  assert.equal(run('model.reviewDrafts.runA.summary'), authored.fields.summary);
  assert.equal(run('model.reviewDrafts.runA.reviewer'), 'Synthetic Reviewer');
  assert.equal(run('model.reviewDrafts.runA.acknowledge_limitations'), true);
""")


def test_legacy_changed_assessments_block_stale_generated_summary_until_updated() -> (
    None
):
    run_guided(r"""
  enterLegacyReview();
  reviewForm();
  click(guidedButton('adopt-follow-up'));
  click(flowButton('review-summary'));
  summaryForm();
  click(flowButton('summary-adopt'));
  const originalSummary = run('model.reviewDrafts.runA.summary');
  click(flowButton('review-step', {index: '0'}));
  restoreFindingForm();
  click(guidedButton('adopt-escalation'));
  assert.equal(run('model.reviewDrafts.runA.summary'), originalSummary);
  assert.equal(run('flowSummaryNeedsUpdate(model.reviewDrafts.runA)'), true);
  click(flowButton('review-summary'));
  const {form} = summaryForm({reviewer: 'Synthetic Reviewer', acknowledge_limitations: 'on'});
  let requests = 0;
  fetchImplementation = async () => {requests += 1; throw new Error('A stale summary must not reach the server.');};
  main.emit('submit', {target: form, preventDefault() {}, submitter: {value: ''}});
  await settle();
  assert.equal(requests, 0);
  assert.match(notice.textContent, /individual assessments changed/i);
  click(flowButton('summary-adopt'));
  assert.equal(run('flowSummaryNeedsUpdate(model.reviewDrafts.runA)'), false);
  assert.ok(run('model.reviewDrafts.runA.summary').includes('0 for follow-up, 1 for escalation, and 0 as explained'));
  assert.equal(run('model.reviewDrafts.runA.reviewer'), 'Synthetic Reviewer');
  assert.equal(run('model.reviewDrafts.runA.acknowledge_limitations'), true);
""")


@pytest.mark.parametrize(
    "summary_style", ["generated", "saved_authored", "edited_after_reload"]
)
def test_legacy_reopened_review_recognizes_only_unchanged_generated_summaries(
    summary_style: str,
) -> None:
    run_guided(r"""
  enterLegacyReview();
  reviewForm();
  click(guidedButton('adopt-follow-up'));
  click(flowButton('review-summary'));
  summaryForm();
  click(flowButton('summary-adopt'));
  const saved = JSON.parse(run('JSON.stringify(model.reviewDrafts.runA)'));
  saved.reviewer = 'Synthetic Reviewer';
  saved.acknowledge_limitations = true;
  if (SUMMARY_STYLE === 'saved_authored') saved.summary += '\n\nThe analyst requested the original shipping records before any further action.';
  const retained = JSON.parse(run('JSON.stringify(model.run)'));
  retained.latest_review = {review_id: 'saved-review', review: saved};

  // A new browser session has retained records, but no drafts or per-view markers.
  currentReviewForm = null;
  run('model.flow = newFlow(); model.reviewDrafts = {}; model.run = null; model.selectedRun = "";');
  navigate('investigate');
  fetchImplementation = async (url) => {
    assert.equal(url, '/api/runs/runA');
    return jsonResponse(retained);
  };
  click(flowButton('resume', {id: 'runA'}));
  await settle();
  assert.equal(run('model.flow.stage'), 'package');
  assert.equal(run('Object.keys(model.reviewDrafts).length'), 0);
  if (SUMMARY_STYLE === 'edited_after_reload') {
    click(flowButton('review-summary'));
    summaryForm();
    click(flowButton('summary-edit'));
    const authored = summaryForm({summary: saved.summary + '\n\nThe analyst is retaining this wording while awaiting source records.'});
    main.emit('input', {target: authored.controls.summary});
  }

  click(flowButton('review-step', {index: '0'}));
  restoreFindingForm();
  click(guidedButton('adopt-escalation'));
  const expectedSummary = run('model.reviewDrafts.runA.summary');
  assert.equal(run('flowSummaryNeedsUpdate(model.reviewDrafts.runA)'), SUMMARY_STYLE === 'generated');
  assert.equal(run('model.run.latest_review.review.findings[0].disposition'), 'follow_up', 'Editing a draft must leave the retained review intact.');
  click(flowButton('review-summary'));
  const {form} = summaryForm();
  if (SUMMARY_STYLE === 'generated') {
    assert.ok(main.innerHTML.includes('The individual assessments changed after this summary was prepared.'));
    let requests = 0;
    fetchImplementation = async () => {requests += 1; throw new Error('A stale summary must not reach the server.');};
    main.emit('submit', {target: form, preventDefault() {}, submitter: {value: ''}});
    await settle();
    assert.equal(requests, 0);
    assert.match(notice.textContent, /individual assessments changed/i);
    click(flowButton('summary-adopt'));
    assert.equal(run('flowSummaryNeedsUpdate(model.reviewDrafts.runA)'), false);
    assert.ok(run('model.reviewDrafts.runA.summary').includes('0 for follow-up, 1 for escalation, and 0 as explained'));
  } else {
    assert.ok(!main.innerHTML.includes('data-flow="summary-adopt"'));
    click(flowButton('summary-adopt'));
    assert.equal(run('model.reviewDrafts.runA.summary'), expectedSummary, 'Prepared text must never overwrite edited analyst prose.');
  }
""".replace("SUMMARY_STYLE", repr(summary_style)))


def test_purpose_in_settings_is_an_explicit_override_that_replans() -> None:
    run_guided(r"""
  run("model.flow.goalInferred = true; model.flow.plan = {can_run:true}; model.flow.planInputs = flowInput();");
  click(flowButton('plan-settings'));
  assert.ok(guidedSurfaceMarkup.includes('id="flow-goal"'));
  assert.equal(run('model.flow.settingsOpen'), true);
  const payloads = [];
  fetchImplementation = async (url, options) => {
    assert.equal(url, '/api/workflow/plan');
    payloads.push(JSON.parse(options.body));
    return jsonResponse(planned());
  };
  changeControl('flow-goal', 'data_readiness');
  await settle();
  assert.equal(run('model.flow.goalInferred'), false);
  assert.equal(run('model.flow.settingsOpen'), false);
  assert.ok(!guidedSurfaceMarkup.includes('id="flow-goal"'));
  assert.equal(payloads[0].goal_id, 'data_readiness');
  click(flowButton('back-data'));
  click(flowButton('dataset', {id: 'datasetB'}));
  await settle();
  assert.equal(payloads[1].goal_id, 'data_readiness');
""")


def test_opening_settings_owns_the_view_against_a_pending_plan_response() -> None:
    run_guided(r"""
  let release;
  fetchImplementation = async (url) => {
    assert.equal(url, '/api/workflow/plan');
    return new Promise(resolve => {release = resolve;});
  };
  click(flowButton('plan'));
  click(flowButton('plan-settings'));
  assert.ok(guidedSurfaceMarkup.includes('id="flow-goal"'));
  release(jsonResponse(planned()));
  await settle();
  assert.equal(run('model.flow.plan'), null, 'A pending plan response no longer owns the settings view.');
  assert.ok(guidedSurfaceMarkup.includes('id="flow-goal"'), 'Operation cleanup must keep the settings surface open.');
""")
