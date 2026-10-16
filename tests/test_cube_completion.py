"""Cube completion reflects retained work, not merely visiting a face."""

from __future__ import annotations

import pytest
from test_frontend_guards import run_scenario
from test_guided_frontend import GUIDED_SETUP

COMPLETION_SETUP = GUIDED_SETUP + r"""
  const recordedDecision = {schema_version: '2.1', run_id: 'runA', reviewer: 'Analyst Example', decision: 'keep_open', summary: 'Awaiting the signed invoice.', scope_finding_ids: ['findingA'], acknowledge_limitations: true};
  const completionRun = {...runA, latest_review: null, latest_export: null,
    case: {...runA.case, dataset_id: 'datasetA', investigations: ['data_quality'], watchlist_snapshot_id: null},
    dataset_metadata: {dataset_id: 'datasetA', label: 'Retained fixture', counts: {entities: 1}, synthetic: true},
    analysis: {...runA.analysis, findings: [finding()], coverage: [{investigation_id: 'data_quality', status: 'executed', findings_count: 1, records_evaluated: 1}]},
  };
  function completions() {return JSON.parse(run('JSON.stringify(flowCubeFaces().map(face => face.complete))'));}
  function openCompletionRun() {
    run(`model.run = ${JSON.stringify(completionRun)}; model.selectedRun = 'runA'; Object.assign(model.flow, {stage: 'review', datasetId: 'datasetA', goalId: 'transaction_review', preview: null}); model.reviewDrafts = {}; renderGuided();`);
  }
"""


def run_completion(scenario: str) -> None:
    run_scenario(COMPLETION_SETUP + scenario)


def test_visiting_faces_does_not_complete_a_new_investigation() -> None:
    run_completion(r"""
  run('model.flow = newFlow(); model.run = null; model.selectedRun = ""; renderGuided();');
  assert.deepEqual(completions(), [false, false, false, false, false, false]);
  for (let face = 0; face < 6; face += 1) click(flowButton('cube', {face: String(face)}));
  assert.deepEqual(completions(), [false, false, false, false, false, false]);
""")


@pytest.mark.parametrize("pending", ["preview", "identity", "invalid", "unconfirmed"])
def test_records_do_not_complete_while_confirmation_or_validity_is_missing(
    pending: str,
) -> None:
    run_completion(r"""
  run(`model.flow.stage = 'plan'; model.flow.plan = ${JSON.stringify(planned())}; model.flow.planInputs = flowInput();`);
  assert.equal(completions()[0], true);
  if (PENDING === 'preview') run(`model.flow.stage = 'data'; model.flow.preview = ${JSON.stringify(previewed())};`);
  if (PENDING === 'identity') run(`model.flow.stage = 'identity'; model.flow.identityResearch = {status: 'candidates', candidates: [{candidate_id: 'not-selected'}]};`);
  if (PENDING === 'invalid') run('model.state.datasets[0].status = "invalid";');
  if (PENDING === 'unconfirmed') run('model.flow.recordsConfirmed = false;');
  assert.equal(completions()[0], false);
""".replace("PENDING", repr(pending)))


def test_source_acceptance_and_plan_execution_are_separate_milestones() -> None:
    run_completion(r"""
  run(`model.flow.plan = ${JSON.stringify(planned())}; model.flow.planInputs = flowInput();`);
  assert.deepEqual(completions().slice(0, 4), [true, false, false, false], 'Preparing records does not accept sources or approve execution.');
  fetchImplementation = async url => {assert.equal(url, '/api/workflow/approve'); return jsonResponse({approval: approvedSources});};
  click(flowButton('approve-sources'));
  await settle();
  assert.deepEqual(completions().slice(0, 4), [true, true, false, false], 'An accepted source unlocks Plan but does not complete it.');
  changeControl('flow-source', 'changed-source');
  assert.deepEqual(completions().slice(0, 4), [true, false, false, false], 'Changing sources reopens acceptance and plan approval.');
""")


def test_a_verified_run_with_an_unevaluated_screening_check_has_no_completed_source() -> (
    None
):
    run_completion(r"""
  delete completionRun.workflow;
  completionRun.case.investigations = ['screening_candidates', 'data_quality'];
  completionRun.analysis.coverage.push({investigation_id: 'screening_candidates', status: 'not_evaluable', reason: 'No screening snapshot was retained.'});
  openCompletionRun();
  assert.equal(completions()[1], false, 'File verification alone cannot claim that a required screening source exists.');
  assert.equal(completions()[3], false, 'Verification is not a review of the results.');
  assert.equal(run('flowStageAccess(3)'), true, 'The retained findings and coverage remain available to inspect.');
  click(flowButton('findings-reviewed'));
  assert.equal(completions()[3], true);
""")


def test_recorded_assessment_and_persisted_package_are_separate_milestones() -> None:
    run_completion(r"""
  openCompletionRun();
  assert.deepEqual(completions(), [true, true, true, false, false, false]);
  click(flowButton('findings-reviewed'));
  assert.deepEqual(completions(), [true, true, true, true, false, false]);
  click(flowButton('review-summary'));
  assert.equal(completions()[4], false, 'Opening assessment cannot mark it recorded.');
  run(`model.reviewDrafts.runA = ${JSON.stringify(recordedDecision)};`);
  assert.equal(completions()[4], false, 'Even a filled draft is not a saved assessment.');
  run(`model.run.latest_review = {review_id: 'reviewA', review: ${JSON.stringify(recordedDecision)}}; model.reviewDrafts = {};`);
  assert.deepEqual(completions(), [true, true, true, true, true, false]);
  click(flowButton('cube', {face: '5'}));
  assert.equal(completions()[5], false, 'Opening the package face does not create an archive.');
  run('model.run.latest_export = {name: "runA-package.zip", download_url: "/api/exports/runA-package.zip"};');
  assert.deepEqual(completions(), [true, true, true, true, true, true]);
""")


@pytest.mark.parametrize("invalid", ["review", "files"])
def test_invalid_saved_work_cannot_claim_assessment_or_package_completion(
    invalid: str,
) -> None:
    run_completion(r"""
  completionRun.latest_review = {review_id: 'reviewA', review: recordedDecision};
  completionRun.latest_export = {name: 'runA-package.zip', download_url: '/api/exports/runA-package.zip'};
  openCompletionRun();
  assert.equal(completions()[4], true);
  if (INVALID === 'review') run('model.run.review_validation = {ok: false, issues: ["Invalid recorded scope"]};');
  else run('model.run.verification = {ok: false, issues: ["Retained bytes changed"]};');
  assert.equal(completions()[4], false);
  assert.equal(completions()[5], false);
  if (INVALID === 'files') {
    assert.equal(completions()[3], false);
    assert.deepEqual(JSON.parse(run('JSON.stringify(flowCubeFaces().slice(0, 3).map(face => face.status))')), ['Cannot verify', 'Cannot verify', 'Cannot verify']);
    const explanation = run('flowLegacyNote(model.run)');
    assert.match(explanation, /retained files could not be verified/);
    assert.ok(!explanation.includes('no recorded source acceptance'), 'Invalid bytes are not evidence that approval history is absent.');
  }
""".replace("INVALID", repr(invalid)))


def test_only_meaningful_draft_changes_reopen_assessment_and_package() -> None:
    run_completion(r"""
  completionRun.latest_review = {review_id: 'reviewA', review: recordedDecision};
  completionRun.latest_export = {name: 'runA-package.zip', download_url: '/api/exports/runA-package.zip'};
  openCompletionRun();
  const reordered = Object.fromEntries(Object.entries(recordedDecision).reverse());
  run(`model.reviewDrafts.runA = ${JSON.stringify(reordered)};`);
  assert.equal(completions()[4], true, 'Object property order is not an assessment edit.');
  assert.equal(completions()[5], true);
  run('model.reviewDrafts.runA.summary = "The newly supplied invoice changes the assessment.";');
  assert.equal(completions()[4], false);
  assert.equal(completions()[5], false);
  assert.equal(run('model.run.latest_review.review.summary'), recordedDecision.summary);
""")


def test_cube_controls_expose_the_same_completion_to_assistive_technology() -> None:
    run_completion(r"""
  openCompletionRun();
  const markup = run('flowCube()');
  const controls = [...markup.matchAll(/<button\b[^>]*aria-label="Open [^"]+"[^>]*>/g)].map(match => match[0]);
  assert.equal(controls.length, 6);
  const expected = completions();
  const statuses = JSON.parse(run('JSON.stringify(flowCubeFaces().map(face => face.status || (face.complete ? "Completed" : "Not started")))'));
  for (let index = 0; index < controls.length; index += 1) {
    assert.ok(controls[index].includes('data-complete="' + expected[index] + '"'));
    assert.ok(controls[index].includes(`aria-description="Step ${index + 1} of 6. ${statuses[index]}"`));
  }
  const numerals = [...markup.matchAll(/class="stage-number" aria-hidden="true">([^<]+)/g)].map(match => match[1]);
  assert.deepEqual(numerals, ['I', 'II', 'III', 'IV', 'V', 'VI'], 'Completed stages keep their sequence number.');
""")


@pytest.mark.parametrize(
    "workflow",
    [
        None,
        {"status": "unrecorded"},
        {
            "status": "recorded",
            "records_selected": True,
            "source_accepted": False,
            "plan_approved": True,
        },
    ],
)
def test_legacy_or_incomplete_workflow_history_never_claims_approval(
    workflow: dict | None,
) -> None:
    import json

    run_completion(r"""
  completionRun.workflow = WORKFLOW;
  completionRun.latest_review = {review_id: 'reviewA', review: recordedDecision};
  completionRun.latest_export = {name: 'runA-package.zip', download_url: '/api/exports/runA-package.zip'};
  openCompletionRun();
  assert.deepEqual(completions(), [false, false, false, true, true, false]);
  assert.deepEqual(JSON.parse(run('JSON.stringify([0,1,2,3,4,5].map(flowStageAccess))')), [true, true, true, true, true, true], 'A valid saved legacy decision and package remain usable without inventing past approvals.');
  assert.match(run('flowLegacyNote(model.run)'), /no recorded source acceptance or plan approval/);
  assert.match(run('flowPackageView()'), /runA-package.zip/);
""".replace("WORKFLOW", json.dumps(workflow)))
