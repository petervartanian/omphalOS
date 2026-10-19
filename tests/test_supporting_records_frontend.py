"""Retained diligence stays inspectable independently of generated findings."""

from __future__ import annotations

import pytest
from test_case_review_frontend import run_case_review

SUPPORTING_SETUP = r"""
  const supportingRows = Array.from({length: 41}, (_, index) => ({
    kind: 'record', table: 'diligence', id: 'D' + index,
    record: {evidence_id: 'D' + index, entity_id: 'E1', date: '2026-09-18',
      title: index === 0 ? '<Supplier explanation>' : 'Inspection note ' + index,
      text: index === 0 ? 'The invoice covers a replacement shipment. <script>unsafe()</script>' : 'The retained site visit did not resolve the missing delivery ledger.',
      source_url: index === 0 ? 'javascript:unsafe()' : 'https://example.test/inspection/' + index},
    origin: {source_file: 'diligence.csv', source_row: index + 2},
    source_files: [{name: 'diligence.csv', sha256: 'retained-file-hash'}], synthetic: true,
  }));
  run('model.run.dataset_metadata.counts.diligence = 41;');
  const supportingRequests = [];
  let supportingIntercept = async () => {};
  let supportingFailure = null;
  function supportingPage(offset) {
    return {run_id: 'runA', table: 'diligence', scope: 'all_retained_diligence', offset, limit: 40, total: supportingRows.length, rows: supportingRows.slice(offset, offset + 40)};
  }
  fetchImplementation = async (url) => {
    supportingRequests.push(url);
    await supportingIntercept(url);
    if (supportingFailure) return {...jsonResponse({error: supportingFailure.message}), ok: false, status: supportingFailure.status};
    if (url.startsWith('/api/runs/runA/supporting-records?')) {
      const query = new URL('https://local.test' + url).searchParams;
      assert.equal(query.get('limit'), '40');
      return jsonResponse(supportingPage(Number(query.get('offset'))));
    }
    if (url.startsWith('/api/runs/runA/evidence?')) {
      const query = new URL('https://local.test' + url).searchParams;
      assert.equal(query.get('table'), 'diligence');
      return jsonResponse(supportingRows.find(row => row.id === query.get('id')));
    }
    throw new Error('Unexpected supporting-record request: ' + url);
  };
  function dialogClick(target) {
    node('#evidence-dialog').emit('click', {target, preventDefault() {}});
  }
"""


def run_supporting(scenario: str) -> None:
    run_case_review(SUPPORTING_SETUP + scenario)


@pytest.mark.parametrize("findings", [0, 2])
def test_supporting_records_are_available_without_a_corresponding_finding(
    findings: int,
) -> None:
    run_supporting(r"""
  run('model.run.analysis.findings = model.run.analysis.findings.slice(0, FINDINGS);');
  for (const view of ['flowFindingsView()', 'caseReviewView()', 'flowFaceView(0)']) {
    assert.match(run(view), /data-flow="supporting-records"/);
  }
  if (FINDINGS) assert.match(run('findingEvidenceView(model.run, 0)'), /data-flow="supporting-records"/);
  click(flowButton('supporting-records'));
  await settle();
  const markup = node('#dialog-content').innerHTML;
  assert.match(markup, /All retained diligence records, including records that produced no finding/);
  assert.match(markup, /&lt;Supplier explanation&gt;/);
  assert.match(markup, /replacement shipment/);
  assert.ok(!markup.includes('<script>'));
  assert.ok(!markup.includes('href="javascript:'));
  assert.match(markup, /1–40 of 41 records/);
  assert.match(markup, /data-supporting-offset="0"/);
  assert.equal(run('Object.keys(model.reviewDrafts).length'), 0);
  assert.equal(run('model.run.latest_review'), null);
  assert.equal(supportingRequests.length, 1);
  run('model.run.dataset_metadata.counts.diligence = 0;');
  assert.ok(!run('flowFindingsView()').includes('data-flow="supporting-records"'));
""".replace("FINDINGS", str(findings)))


def test_pagination_and_provenance_preserve_the_authored_case_draft() -> None:
    run_supporting(r"""
  editCaseReview({reviewer: 'Analyst Example', decision: 'keep_open', summary: 'Compare the supplier explanation with the retained inspection note.', acknowledge_limitations: 'on'});
  const draft = readCaseDraft();
  const stage = run('model.flow.cubeFace');
  click(flowButton('supporting-records'));
  await settle();
  dialogClick(flowButton('supporting-records', {offset: '40'}));
  await settle();
  assert.match(node('#dialog-content').innerHTML, /41–41 of 41 records/);
  assert.match(node('#dialog-content').innerHTML, /Inspection note 40/);
  assert.match(node('#dialog-content').innerHTML, /data-offset="41" disabled/);
  const provenance = button('evidence', 'D40');
  provenance.dataset.table = 'diligence';
  provenance.dataset.supportingOffset = '40';
  dialogClick(provenance);
  await settle();
  const markup = node('#dialog-content').innerHTML;
  assert.match(markup, /Original provenance/);
  assert.match(markup, /diligence.csv/);
  assert.match(markup, /source row 42/);
  assert.match(markup, /retained-file-hash/);
  assert.match(markup, /data-flow="supporting-records" data-offset="40"/);
  dialogClick(flowButton('supporting-records', {offset: '40'}));
  await settle();
  assert.match(node('#dialog-content').innerHTML, /Inspection note 40/);
  node('#close-dialog').emit('click');
  assert.deepEqual(readCaseDraft(), draft);
  assert.equal(run('model.flow.cubeFace'), stage);
  assert.equal(run('model.run.latest_review'), null);
  assert.equal(supportingRequests.filter(url => url.includes('/supporting-records?')).length, 3);
  assert.equal(supportingRequests.filter(url => url.includes('/evidence?')).length, 1);
""")


@pytest.mark.parametrize("change", ["close", "navigation", "other_dialog"])
def test_late_supporting_page_cannot_replace_a_newer_view(change: str) -> None:
    run_supporting(r"""
  let release;
  supportingIntercept = () => new Promise(resolve => {release = resolve;});
  click(flowButton('supporting-records'));
  assert.match(node('#dialog-content').innerHTML, /Loading supporting records/);
  if (CHANGE === 'close') node('#close-dialog').emit('click');
  if (CHANGE === 'navigation') navigate('data');
  if (CHANGE === 'other_dialog') click(flowButton('coverage'));
  const markup = node('#dialog-content').innerHTML;
  const opens = node('#evidence-dialog').showModalCount;
  release();
  await settle();
  assert.equal(node('#dialog-content').innerHTML, markup);
  assert.equal(node('#evidence-dialog').showModalCount, opens);
  assert.equal(notice.hidden, true);
  assert.equal(run('Object.keys(model.reviewDrafts).length'), 0);
""".replace("CHANGE", repr(change)))


def test_supporting_provenance_cannot_reopen_a_closed_dialog() -> None:
    run_supporting(r"""
  click(flowButton('supporting-records'));
  await settle();
  let release;
  supportingIntercept = () => new Promise(resolve => {release = resolve;});
  const provenance = button('evidence', 'D0');
  provenance.dataset.table = 'diligence';
  provenance.dataset.supportingOffset = '0';
  dialogClick(provenance);
  node('#close-dialog').emit('click');
  const opens = node('#evidence-dialog').showModalCount;
  release();
  await settle();
  assert.equal(node('#evidence-dialog').showModalCount, opens);
  assert.ok(!node('#dialog-content').innerHTML.includes('Original provenance'));
  assert.equal(notice.hidden, true);
""")


def test_supporting_record_retry_keeps_the_requested_page() -> None:
    run_supporting(r"""
  supportingFailure = {status: 503, message: 'Records are temporarily unavailable.'};
  click(flowButton('supporting-records', {offset: '40'}));
  await settle();
  assert.match(node('#dialog-content').innerHTML, /Retry records/);
  assert.match(node('#dialog-content').innerHTML, /data-offset="40"/);
  assert.ok(!node('#dialog-content').innerHTML.includes('<table>'));
  supportingFailure = null;
  dialogClick(flowButton('supporting-records', {offset: '40'}));
  await settle();
  assert.match(node('#dialog-content').innerHTML, /Inspection note 40/);
  assert.equal(run('Object.keys(model.reviewDrafts).length'), 0);
""")


def test_failed_supporting_integrity_blocks_records_without_losing_the_draft() -> None:
    run_supporting(r"""
  editCaseReview({reviewer: 'Analyst Example', decision: 'keep_open', summary: 'Compare the supplier explanation with the retained inspection note.', acknowledge_limitations: 'on'});
  const draft = readCaseDraft();
  supportingFailure = {status: 409, message: 'The retained files did not pass verification.'};
  click(flowButton('supporting-records'));
  await settle();
  assert.equal(run('model.run.verification.ok'), false);
  assert.deepEqual(readCaseDraft(), draft);
  assert.match(node('#dialog-content').innerHTML, /did not pass verification/);
  assert.ok(!node('#dialog-content').innerHTML.includes('<table>'));
  assert.ok(!node('#dialog-content').innerHTML.includes('Retry records'));
  assert.ok(!run('caseReviewView()').includes('data-flow="supporting-records"'));
  click(flowButton('supporting-records'));
  await settle();
  assert.equal(supportingRequests.length, 1, 'An unverified run cannot retry the data endpoint.');
""")


@pytest.mark.parametrize("close_dialog", [False, True])
def test_provenance_integrity_failure_invalidates_the_run_and_preserves_the_draft(
    close_dialog: bool,
) -> None:
    run_supporting(r"""
  editCaseReview({reviewer: 'Analyst Example', decision: 'keep_open', summary: 'Compare the supplier explanation with the retained inspection note.', acknowledge_limitations: 'on'});
  const draft = readCaseDraft();
  click(flowButton('supporting-records'));
  await settle();
  assert.match(node('#dialog-content').innerHTML, /replacement shipment/);
  supportingFailure = {status: 409, message: 'The retained files did not pass verification.'};
  let release;
  supportingIntercept = () => new Promise(resolve => {release = resolve;});
  const provenance = button('evidence', 'D0');
  provenance.dataset.table = 'diligence';
  provenance.dataset.supportingOffset = '0';
  dialogClick(provenance);
  if (CLOSE) node('#close-dialog').emit('click');
  const opens = node('#evidence-dialog').showModalCount;
  release();
  await settle();
  assert.equal(run('model.run.verification.ok'), false);
  assert.deepEqual(readCaseDraft(), draft);
  assert.equal(run('flowStageAccess(4)'), false);
  assert.equal(run('flowStageAccess(5)'), false);
  assert.ok(!run('caseReviewView()').includes('data-flow="supporting-records"'));
  if (CLOSE) assert.equal(node('#evidence-dialog').showModalCount, opens, 'An integrity error cannot reopen a dismissed dialog.');
  else {
    assert.match(node('#dialog-content').innerHTML, /did not pass verification/);
    assert.ok(!node('#dialog-content').innerHTML.includes('<table>'));
  }
""".replace("CLOSE", str(close_dialog).lower()))
