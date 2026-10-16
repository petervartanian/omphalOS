"""Each completed stage follows an explicit, current workflow decision."""

from __future__ import annotations

import pytest
from test_case_review_frontend import run_case_review
from test_guided_frontend import run_guided
from test_identity_frontend import run_identity


def test_stage_access_requires_accepted_records_sources_and_reviewed_results() -> None:
    run_case_review(r"""
  const access = () => JSON.parse(run('JSON.stringify([0,1,2,3,4,5].map(flowStageAccess))'));
  run('model.flow = newFlow();');
  assert.deepEqual(access(), [true, false, false, false, false, false]);
  for (const index of [-1, 6, 1.5]) assert.equal(run(`flowStageAccess(${index})`), false);
  run('Object.assign(model.flow, {stage: "identity", datasetId: "datasetA"});');
  assert.deepEqual(access(), [true, false, false, false, false, false]);
  run(`Object.assign(model.flow, {stage: 'plan', recordsConfirmed: true, goalId: 'transaction_review', plan: ${JSON.stringify(planned())}}); model.flow.planInputs = flowInput();`);
  assert.deepEqual(access(), [true, true, false, false, false, false], 'A prepared plan cannot approve Sources.');
  run(`Object.assign(model.flow, {approval: ${JSON.stringify(approvedSources)}, approvalPlanId: 'planA'});`);
  assert.deepEqual(access(), [true, true, true, false, false, false]);
  run('model.flow.stage = "review";');
  assert.deepEqual(access(), [true, true, true, true, false, false], 'A finished check has results to inspect, not an automatically completed review.');
  click(flowButton('findings-reviewed'));
  assert.deepEqual(access(), [true, true, true, true, true, false]);
  const saved = {schema_version: '2.1', run_id: 'runA', reviewer: 'Analyst Example', decision: 'keep_open', summary: '', scope_finding_ids: ['context-A', 'volume-B'], acknowledge_limitations: true};
  run(`model.run.latest_review = {review_id: 'saved-review', review: ${JSON.stringify(saved)}};`);
  assert.equal(run('flowStageAccess(5)'), true);
  run(`model.reviewDrafts.runA = {...${JSON.stringify(saved)}, summary: 'The new records need a revised decision.'};`);
  assert.equal(run('flowStageAccess(5)'), false, 'Unsaved case changes cannot unlock an obsolete package.');
  run('model.run.verification.ok = false;');
  assert.deepEqual(access(), [true, true, true, true, false, false], 'Findings keeps its integrity error available; assessment and export remain blocked.');
""")


def test_blocked_stages_cannot_silently_mark_findings_reviewed_or_record_a_decision() -> (
    None
):
    run_case_review(r"""
  run('Object.assign(model.flow, {cubeFace: 3, inspectionFace: 3, surfaceOpen: true, resultsReview: null}); renderGuided();');
  for (const face of [4, 5]) click(flowButton('cube', {face: String(face)}));
  click(flowButton('continue'));
  click(flowButton('review-summary'));
  assert.equal(run('model.flow.cubeFace'), 3);
  assert.equal(run('model.flow.inspectionFace'), 3);
  assert.equal(run('flowResultsReviewed(model.run)'), false);
  assert.equal(run('Object.keys(model.reviewDrafts).length'), 0);
  assert.equal(run('model.run.latest_review'), null);
  click(flowButton('findings-reviewed'));
  assert.equal(run('model.flow.cubeFace'), 4);
  assert.equal(run('flowNextStage()'), 4, 'Marking results reviewed does not record an assessment.');
  click(flowButton('continue'));
  assert.equal(run('model.flow.cubeFace'), 4);
  assert.equal(run('Object.keys(model.reviewDrafts).length'), 0);
""")


def test_guide_names_available_stages_without_bypassing_review_actions() -> None:
    run_case_review(r"""
  run('Object.assign(model.flow, {cubeFace: 0, inspectionFace: 0, surfaceOpen: true, resultsReview: null});');
  assert.ok(!run('flowGuide()').includes('object-label'));
  assert.match(run('flowGuide()'), /data-flow="continue">Sources →/);
  click(flowButton('continue'));
  assert.match(run('flowGuide()'), /data-flow="continue">Plan →/);
  click(flowButton('continue'));
  assert.match(run('flowGuide()'), /data-flow="continue">Findings →/);
  click(flowButton('continue'));
  assert.ok(!run('flowGuide()').includes('data-flow="continue"'), 'The generic next action cannot mark results reviewed.');
  assert.match(run('flowFindingsView()'), /data-flow="findings-reviewed">Mark results reviewed/);
  click(flowButton('findings-reviewed'));
  assert.ok(!run('flowGuide()').includes('data-flow="continue"'));
  assert.equal(run('Object.keys(model.reviewDrafts).length'), 0);
""")


def test_sources_without_a_required_list_still_need_explicit_acceptance() -> None:
    run_guided(r"""
  run(`Object.assign(model.flow, {stage: 'plan', goalId: 'transaction_review', plan: ${JSON.stringify(planned())}, cubeFace: 1, inspectionFace: 1, surfaceOpen: true}); model.flow.planInputs = flowInput(); renderGuided();`);
  const contents = run('flowFaceView(1)');
  assert.ok(contents.includes('no external screening list is included'));
  assert.match(contents, /data-flow="approve-sources"/);
  assert.ok(!contents.includes('data-flow="goal"'));
  click(flowButton('continue'));
  assert.equal(run('model.flow.inspectionFace'), 1);
  const requests = [];
  fetchImplementation = async (url, options) => {
    requests.push({url, body: JSON.parse(options.body)});
    assert.equal(url, '/api/workflow/approve');
    return jsonResponse({approval: approvedSources});
  };
  click(flowButton('approve-sources'));
  await settle();
  assert.equal(run('model.flow.inspectionFace'), 2);
  assert.equal(run('model.flow.goalId'), 'transaction_review');
  assert.equal(requests[0].body.acknowledge_source, true);
  click(flowButton('cube', {face: '1'}));
  click(flowButton('approve-sources'));
  await settle();
  assert.equal(requests.length, 1, 'Reopening an unchanged accepted source reuses its approval.');
""")


def test_manual_execution_lands_on_unreviewed_findings_without_an_assessment() -> None:
    run_guided(r"""
  run(`Object.assign(model.flow, {stage: 'plan', plan: ${JSON.stringify(planned())}, planInputs: flowInput(), approval: ${JSON.stringify(approvedSources)}, approvalPlanId: 'planA', cubeFace: 2, inspectionFace: 2});`);
  const requests = [];
  fetchImplementation = async (url, options) => {
    requests.push(url);
    if (url === '/api/workflow/run') {
      const payload = JSON.parse(options.body);
      assert.deepEqual(payload.approval, approvedSources);
      assert.equal(payload.acknowledge_plan, true);
      return jsonResponse({run_id: 'runA'});
    }
    if (url === '/api/runs/runA') return jsonResponse({...runA, latest_review: null});
    if (url === '/api/state') return jsonResponse(state);
    throw new Error('Unexpected execution request: ' + url);
  };
  click(flowButton('run'));
  await settle();
  assert.equal(run('model.flow.stage'), 'review');
  assert.equal(run('model.flow.cubeFace'), 3);
  assert.equal(run('model.flow.inspectionFace'), 3);
  assert.equal(run('flowResultsReviewed(model.run)'), false);
  assert.equal(run('Object.keys(model.reviewDrafts).length'), 0);
  assert.ok(!requests.some(url => url.endsWith('/review')));
""")


def test_identity_preparation_stops_at_sources_until_each_explicit_action() -> None:
    run_identity(r"""
  submitSubject();
  await settle();
  run(`globalThis.renderedStages = []; const originalRender = renderGuided; renderGuided = () => { renderedStages.push(flowState().cubeFace); return originalRender(); };`);
  click(flowButton('identity-select', {id: candidate.candidate_id}));
  await settle();
  const stages = JSON.parse(run('JSON.stringify(renderedStages)')).filter((stage, index, all) => index === 0 || stage !== all[index - 1]);
  assert.deepEqual(stages, [0, 1]);
  assert.equal(entryRequests.filter(item => item.url === '/api/workflow/run').length, 0);
  assert.equal(entryRequests.filter(item => item.url === '/api/workflow/approve').length, 0);
  await approveAndRun();
  assert.equal(entryRequests.filter(item => item.url === '/api/workflow/run').length, 1);
  assert.equal(run('model.flow.cubeFace'), 3);
  assert.equal(run('Object.keys(model.reviewDrafts).length'), 0);
""")


def test_required_source_must_be_retained_and_accepted_before_plan_access() -> None:
    run_guided(r"""
  run(`Object.assign(model.flow, {stage: 'plan', goalId: 'counterparty_screening', plan: ${JSON.stringify(planned())}, cubeFace: 1}); model.flow.planInputs = flowInput(); model.run = null;`);
  let requests = 0;
  fetchImplementation = async url => {requests += 1; assert.equal(url, '/api/workflow/approve'); return jsonResponse({approval: approvedSources});};
  assert.equal(run('flowStageAccess(1)'), true);
  assert.equal(run('flowStageAccess(2)'), false);
  click(flowButton('approve-sources'));
  await settle();
  assert.equal(requests, 0, 'A stale approval control cannot accept a missing reference list.');
  run('model.flow.plan.source_status.selected = true;');
  assert.equal(run('flowStageAccess(2)'), false, 'Downloading a list is not accepting it.');
  click(flowButton('approve-sources'));
  await settle();
  assert.equal(run('flowStageAccess(2)'), true);
""")


@pytest.mark.parametrize(
    "change", ["goal", "date", "source", "records", "leave", "leave_return"]
)
def test_late_source_approval_cannot_authorize_changed_or_abandoned_work(
    change: str,
) -> None:
    run_guided(r"""
  run(`Object.assign(model.flow, {plan: ${JSON.stringify(planned())}, planInputs: flowInput(), cubeFace: 1, inspectionFace: 1});`);
  let release;
  const requests = [];
  fetchImplementation = async url => {requests.push(url); assert.equal(url, '/api/workflow/approve'); return new Promise(resolve => {release = resolve;});};
  click(flowButton('approve-sources'));
  assert.equal(requests.length, 1);
  if (CHANGE === 'goal') click(flowButton('goal', {goal: 'data_readiness'}));
  if (CHANGE === 'date') changeControl('flow-as-of', '2026-10-14');
  if (CHANGE === 'source') changeControl('flow-source', 'other-source');
  if (CHANGE === 'records') click(flowButton('back-data'));
  if (CHANGE.startsWith('leave')) {
    navigate('data');
    if (CHANGE === 'leave_return') navigate('investigate');
  }
  release(jsonResponse({approval: approvedSources}));
  await settle();
  assert.equal(run('model.flow.approval'), null);
  assert.equal(run('model.flow.approvalPlanId'), null);
  assert.equal(run('flowSourcesAccepted()'), false);
  click(flowButton('run'));
  await settle();
  assert.deepEqual(requests, ['/api/workflow/approve']);
""".replace("CHANGE", repr(change)))


@pytest.mark.parametrize("change", ["goal", "date", "source", "records", "plan_id"])
def test_changed_inputs_or_plan_cannot_reuse_a_previous_source_approval(
    change: str,
) -> None:
    run_guided(r"""
  run(`Object.assign(model.flow, {plan: ${JSON.stringify(planned())}, planInputs: flowInput(), approval: ${JSON.stringify(approvedSources)}, approvalPlanId: 'planA'});`);
  assert.equal(run('flowSourcesAccepted()'), true);
  if (CHANGE === 'goal') click(flowButton('goal', {goal: 'data_readiness'}));
  if (CHANGE === 'date') changeControl('flow-as-of', '2026-10-14');
  if (CHANGE === 'source') changeControl('flow-source', 'other-source');
  if (CHANGE === 'records') click(flowButton('back-data'));
  if (CHANGE === 'plan_id') run('model.flow.plan.plan_id = "replacement-plan";');
  assert.equal(run('flowSourcesAccepted()'), false);
  if (CHANGE !== 'plan_id') assert.equal(run('model.flow.approval'), null);
  let requests = 0;
  fetchImplementation = async () => {requests += 1; throw new Error('Changed work must not execute with stale approval.');};
  click(flowButton('run'));
  await settle();
  assert.equal(requests, 0);
""".replace("CHANGE", repr(change)))


def test_findings_review_is_bound_to_the_verified_run_not_its_display_name() -> None:
    run_case_review(r"""
  run('model.flow.resultsReview = null;');
  assert.equal(run('flowResultsReviewed(model.run)'), false);
  click(flowButton('findings-reviewed'));
  assert.equal(run('flowResultsReviewed(model.run)'), true);
  run('model.selectedRun = "different-run";');
  assert.equal(run('flowResultsReviewed(model.run)'), false);
  run('model.selectedRun = "runA"; model.run = {...model.run};');
  assert.equal(run('flowResultsReviewed(model.run)'), false, 'A newly loaded result must be reviewed unless it has a valid saved assessment.');
  run('model.run.verification.ok = false;');
  click(flowButton('findings-reviewed'));
  assert.equal(run('flowResultsReviewed(model.run)'), false);
  assert.equal(run('Object.keys(model.reviewDrafts).length'), 0);
""")


@pytest.mark.parametrize("change", ["inspect", "leave", "inputs"])
def test_late_explicit_execution_does_not_replace_the_chosen_view(change: str) -> None:
    run_identity(r"""
  submitSubject();
  await settle();
  click(flowButton('identity-select', {id: candidate.candidate_id}));
  await settle();
  click(flowButton('approve-sources'));
  await settle();
  let release;
  let waiting = false;
  entryIntercept = async url => {
    if (url !== '/api/workflow/run') return;
    waiting = true;
    await new Promise(resolve => {release = resolve;});
  };
  click(flowButton('run'));
  await until(() => waiting);
  assert.equal(entryRequests.filter(item => item.url === '/api/workflow/run').length, 1);
  if (CHANGE === 'inspect') click(flowButton('cube', {face: '1'}));
  if (CHANGE === 'leave') navigate('data');
  if (CHANGE === 'inputs') changeControl('flow-as-of', '2026-10-14');
  const face = run('model.flow.cubeFace');
  release();
  await settle();
  assert.equal(run('model.selectedRun'), '', 'A late response cannot select a result after ownership changed.');
  assert.equal(run('model.flow.cubeFace'), face);
  assert.ok(!entryRequests.some(item => item.url === '/api/runs/subject-run'));
  assert.equal(run('Object.keys(model.reviewDrafts).length'), 0);
  if (CHANGE === 'leave') assert.equal(run('model.page'), 'data');
  if (CHANGE === 'inputs') assert.equal(run('model.flow.approval'), null);
""".replace("CHANGE", repr(change)))
