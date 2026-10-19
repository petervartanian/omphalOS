"""Portable cases and signing controls preserve explicit choices and exact scope."""

from __future__ import annotations

import pytest
from test_case_review_frontend import run_case_review

HANDOFF_SETUP = r"""
  const packageHash = 'a'.repeat(64);
  const preview = {package_sha256: packageHash, run_id: 'receivedRun', review_id: 'receivedReview',
    case_title: 'Received <case>', analyst: 'Received Analyst', decision: 'keep_open',
    counts: {entities: 2, diligence: 1}, findings_count: 2, verification: {ok: true}};
  const handoffRequests = [];
  const receivedRun = {...retainedCase, manifest: {...retainedCase.manifest, run_id: 'receivedRun'}, latest_review: {
    review_id: 'receivedReview', review: {schema_version: '2.2', run_id: 'receivedRun', reviewer: 'Received Analyst', decision: 'keep_open', summary: 'Obtain complete delivery evidence before resolving this case.', scope_finding_ids: ['context-A', 'volume-B'], acknowledge_limitations: true}}, review_validation: {ok: true}};
  let handoffResponse = preview;
  let handoffDelay = async () => {};
  fetchImplementation = async (url, options) => {
    const body = options?.body ? JSON.parse(options.body) : undefined;
    handoffRequests.push({url, body});
    if (url === '/api/handoffs/inspect') {await handoffDelay(); return jsonResponse(handoffResponse);}
    if (url === '/api/handoffs/import') return jsonResponse({run_id: 'receivedRun', imported: true, package_sha256: packageHash});
    if (url === '/api/state') return jsonResponse(state);
    if (url === '/api/runs/receivedRun') return jsonResponse(receivedRun);
    throw new Error('Unexpected handoff URL: ' + url);
  };
  function packageFile() {
    return {name: 'case.zip', size: 4, arrayBuffer: async () => Uint8Array.from([1, 2, 3, 4]).buffer};
  }
  function choosePackage() {
    node('#evidence-dialog').emit('change', {target: {dataset: {handoffFile: ''}, files: [packageFile()], value: 'file'}});
  }
  function dialogFlow(action) {node('#evidence-dialog').emit('click', {target: flowButton(action)});}
"""


def run_handoff(scenario: str) -> None:
    run_case_review(HANDOFF_SETUP + scenario)


def test_receiving_case_checks_bytes_before_explicit_add() -> None:
    run_handoff(r"""
  assert.match(run('savedWorkView()'), /Open a case package/);
  choosePackage();
  await settle();
  assert.equal(handoffRequests.length, 1);
  assert.equal(handoffRequests[0].url, '/api/handoffs/inspect');
  assert.equal(handoffRequests[0].body.file.content_base64, 'AQIDBA==');
  assert.match(node('#dialog-content').innerHTML, /Received &lt;case&gt;/);
  assert.match(node('#dialog-content').innerHTML, /2 entities, 1 diligence record/);
  assert.equal(run('model.selectedRun'), 'runA');
  dialogFlow('handoff-import');
  await settle();
  assert.equal(handoffRequests[1].body.expected_sha256, packageHash);
  assert.equal(handoffRequests[1].body.file.content_base64, 'AQIDBA==');
  assert.equal(run('model.selectedRun'), 'receivedRun');
  assert.equal(run('model.flow.approval'), null);
  assert.equal(run('model.flow.recordsConfirmed'), false);
""")


@pytest.mark.parametrize("failure", ["integrity", "missing_hash"])
def test_unverified_preview_has_no_add_action(failure: str) -> None:
    run_handoff(r"""
  handoffResponse = {...preview, ...(FAILURE === 'integrity' ? {verification: {ok: false}} : {package_sha256: ''})};
  choosePackage();
  await settle();
  assert.match(node('#dialog-content').innerHTML, /did not pass verification/);
  assert.ok(!node('#dialog-content').innerHTML.includes('data-flow="handoff-import"'));
  assert.equal(run('model.handoff'), null);
  assert.equal(handoffRequests.length, 1);
""".replace("FAILURE", repr(failure)))


@pytest.mark.parametrize("change", ["close", "navigate", "other_dialog"])
def test_late_inspection_does_not_open_over_changed_view(change: str) -> None:
    run_handoff(r"""
  let release;
  handoffDelay = () => new Promise(resolve => {release = resolve;});
  choosePackage();
  await new Promise(resolve => setImmediate(resolve));
  if (CHANGE === 'close') node('#close-dialog').emit('click');
  if (CHANGE === 'navigate') navigate('data');
  if (CHANGE === 'other_dialog') click(flowButton('coverage'));
  const markup = node('#dialog-content').innerHTML;
  const opens = node('#evidence-dialog').showModalCount;
  release();
  await settle();
  assert.equal(node('#dialog-content').innerHTML, markup);
  assert.equal(node('#evidence-dialog').showModalCount, opens);
  assert.equal(run('model.handoff'), null);
""".replace("CHANGE", repr(change)))


def test_case_import_retains_an_unfinished_assessment_draft() -> None:
    run_handoff(r"""
  editCaseReview({reviewer: 'Working Analyst', decision: 'keep_open', summary: 'Retain this unfinished note while receiving the other case.'});
  const before = readCaseDraft();
  choosePackage();
  await settle();
  dialogFlow('handoff-info');
  assert.match(node('#dialog-content').innerHTML, /does not establish who supplied/);
  dialogFlow('handoff-preview');
  assert.match(node('#dialog-content').innerHTML, /data-flow="handoff-import"/);
  dialogFlow('handoff-import');
  await settle();
  assert.deepEqual(readCaseDraft(), before);
  assert.equal(run('model.selectedRun'), 'receivedRun');
""")


def test_continuation_uses_copied_records_and_requires_new_approvals() -> None:
    run_handoff(r"""
  receivedRun.handoff = {continuation_dataset_id: 'copiedDataset', continuation_source_id: 'copiedSource'};
  state.datasets.push({dataset_id: 'copiedDataset', label: 'Received records', counts: {entities: 2, shipments: 1}});
  state.sources.push({snapshot_id: 'copiedSource', source_id: 'csl', ingestion_method: 'manual_import'});
  choosePackage();
  await settle();
  dialogFlow('handoff-import');
  await settle();
  assert.equal(run('model.flow.datasetId'), 'copiedDataset');
  assert.equal(run('model.flow.snapshotId'), 'copiedSource');
  assert.match(run('flowPackageView()'), /Continue with these records/);
  let planRequest;
  fetchImplementation = async (url, options) => {
    assert.equal(url, '/api/workflow/plan');
    planRequest = JSON.parse(options.body);
    return jsonResponse(planned());
  };
  click(flowButton('continue-handoff'));
  await settle();
  assert.equal(planRequest.dataset_id, 'copiedDataset');
  assert.equal(run('model.flow.stage'), 'plan');
  assert.equal(run('model.flow.approval'), null);
  assert.equal(run('flowCubeFaces()[1].complete'), false);
  assert.equal(run('flowCubeFaces()[2].complete'), false);
  assert.equal(run('model.run.latest_review.review_id'), 'receivedReview');
""")
