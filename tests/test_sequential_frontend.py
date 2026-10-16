"""Stage availability follows retained work without adding preparation chores."""

from __future__ import annotations

from test_case_review_frontend import run_case_review
from test_guided_frontend import run_guided
from test_identity_frontend import run_identity


def test_stage_access_requires_accepted_records_results_and_a_recorded_decision() -> (
    None
):
    run_case_review(r"""
  const access = () => JSON.parse(run('JSON.stringify([0,1,2,3,4,5].map(flowStageAccess))'));
  run('model.flow = newFlow();');
  assert.deepEqual(access(), [true, false, false, false, false, false]);
  assert.equal(run('flowStageAccess(-1)'), false);
  assert.equal(run('flowStageAccess(6)'), false);
  assert.equal(run('flowStageAccess(1.5)'), false);
  run('Object.assign(model.flow, {stage: "identity", datasetId: "datasetA"});');
  assert.deepEqual(access(), [true, false, false, false, false, false], 'A subject still awaiting an identity decision is not accepted intake.');
  run(`Object.assign(model.flow, {stage: 'plan', plan: ${JSON.stringify(planned())}});`);
  assert.deepEqual(access(), [true, true, true, false, false, false]);
  run('model.flow.stage = "review";');
  assert.deepEqual(access(), [true, true, true, true, true, false]);
  const saved = {schema_version: '2.1', run_id: 'runA', reviewer: 'Analyst Example', decision: 'keep_open', summary: '', scope_finding_ids: ['context-A', 'volume-B'], acknowledge_limitations: true};
  run(`model.run.latest_review = {review_id: 'saved-review', review: ${JSON.stringify(saved)}};`);
  assert.equal(run('flowStageAccess(5)'), true);
  run(`model.reviewDrafts.runA = {...${JSON.stringify(saved)}, summary: 'The new records need a revised decision.'};`);
  assert.equal(run('flowStageAccess(5)'), false, 'Unsaved case changes cannot unlock an obsolete package.');
  run('model.run.verification.ok = false;');
  assert.deepEqual(access(), [true, true, true, true, false, false], 'Findings keeps its integrity error available; assessment and export remain blocked.');
""")


def test_blocked_package_selection_cannot_move_or_create_a_case_decision() -> None:
    run_case_review(r"""
  run('Object.assign(model.flow, {cubeFace: 3, inspectionFace: 3, surfaceOpen: true}); renderGuided();');
  click(flowButton('cube', {face: '5'}));
  assert.equal(run('model.flow.cubeFace'), 3);
  assert.equal(run('model.flow.inspectionFace'), 3);
  assert.equal(run('Object.keys(model.reviewDrafts).length'), 0);
  assert.equal(run('model.run.latest_review'), null);
  click(flowButton('continue'));
  assert.equal(run('model.flow.cubeFace'), 4);
  assert.equal(run('flowNextStage()'), 4, 'Viewing the assessment does not record a decision.');
  click(flowButton('continue'));
  assert.equal(run('model.flow.cubeFace'), 4);
  assert.equal(run('Object.keys(model.reviewDrafts).length'), 0);
""")


def test_guide_names_current_and_next_available_stage_without_generic_continue() -> (
    None
):
    run_case_review(r"""
  run('Object.assign(model.flow, {cubeFace: 0, inspectionFace: 0, surfaceOpen: true});');
  assert.ok(!run('flowGuide()').includes('object-label'), 'Stage navigation already names the current panel; do not add a duplicate eyebrow.');
  assert.match(run('flowGuide()'), /data-flow="continue">Sources →/);
  click(flowButton('continue'));

  assert.match(run('flowGuide()'), /data-flow="continue">Plan →/);
  click(flowButton('continue'));
  assert.match(run('flowGuide()'), /data-flow="continue">Findings →/);
  click(flowButton('continue'));
  assert.match(run('flowGuide()'), /data-flow="continue">Assessment →/);
  click(flowButton('continue'));
  assert.ok(!run('flowGuide()').includes('data-flow="continue"'), 'The next step is gated by the explicit case decision.');
  assert.equal(run('Object.keys(model.reviewDrafts).length'), 0);
""")


def test_sources_without_a_required_list_continue_to_plan_without_changing_purpose() -> (
    None
):
    run_guided(r"""
  run(`Object.assign(model.flow, {stage: 'plan', goalId: 'transaction_review', plan: ${JSON.stringify(planned())}, cubeFace: 1, inspectionFace: 1, surfaceOpen: true}); renderGuided();`);
  const contents = run('flowFaceView(1)');
  assert.ok(contents.includes('No reference list is required'));
  assert.match(contents, /data-flow="continue">Plan →/);
  assert.ok(!contents.includes('data-flow="goal"'));
  click(flowButton('focus-step'));
  assert.equal(run('model.flow.inspectionFace'), 1, 'Opening the selected Sources panel must not replace it with Plan.');
  click(flowButton('continue'));
  assert.equal(run('model.flow.inspectionFace'), 2);
  assert.equal(run('model.flow.goalId'), 'transaction_review');
""")


def test_manual_execution_lands_on_findings_without_creating_an_assessment() -> None:
    run_guided(r"""
  run(`Object.assign(model.flow, {stage: 'plan', plan: ${JSON.stringify(planned())}, planInputs: flowInput(), cubeFace: 2, inspectionFace: 2});`);
  const requests = [];
  fetchImplementation = async url => {
    requests.push(url);
    if (url === '/api/workflow/run') return jsonResponse({run_id: 'runA'});
    if (url === '/api/runs/runA') return jsonResponse({...runA, latest_review: null});
    if (url === '/api/state') return jsonResponse(state);
    throw new Error('Unexpected execution request: ' + url);
  };
  click(flowButton('run'));
  await settle();
  assert.equal(run('model.flow.stage'), 'review');
  assert.equal(run('model.flow.cubeFace'), 3);
  assert.equal(run('model.flow.inspectionFace'), 3);
  assert.equal(run('Object.keys(model.reviewDrafts).length'), 0);
  assert.ok(!requests.some(url => url.endsWith('/review')));
""")


def test_automatic_intake_progresses_from_sources_to_plan_to_findings_once() -> None:
    run_identity(r"""
  submitSubject();
  await settle();
  run(`globalThis.renderedStages = []; const originalRender = renderGuided; renderGuided = () => { renderedStages.push(flowState().cubeFace); return originalRender(); };`);
  click(flowButton('identity-select', {id: candidate.candidate_id}));
  await settle();
  const stages = JSON.parse(run('JSON.stringify(renderedStages)')).filter((stage, index, all) => index === 0 || stage !== all[index - 1]);
  assert.deepEqual(stages, [0, 1, 2, 3], 'Preparation is automatic and does not jump backward from Plan to Sources.');
  assert.equal(entryRequests.filter(item => item.url === '/api/workflow/run').length, 1);
  assert.equal(run('Object.keys(model.reviewDrafts).length'), 0);
""")


def test_required_source_must_be_retained_before_plan_becomes_available() -> None:
    run_guided(r"""
  run(`Object.assign(model.flow, {stage: 'plan', goalId: 'counterparty_screening', plan: ${JSON.stringify(planned())}, cubeFace: 1}); model.run = null;`);
  assert.equal(run('flowStageAccess(1)'), true);
  assert.equal(run('flowStageAccess(2)'), false, 'A plan awaiting required reference evidence must not skip Sources.');
  click(flowButton('cube', {face: '2'}));
  assert.equal(run('model.flow.cubeFace'), 1);
  run('model.flow.plan.source_status.selected = true;');
  assert.equal(run('flowStageAccess(2)'), true);
""")
