"""Signed review UI never mistakes a checked signature for a trusted person."""

from __future__ import annotations

import pytest
from test_case_review_frontend import run_case_review

REVIEWER_SETUP = r"""
  const reviewContext = {package_sha256: 'a'.repeat(64), analysis_digest: 'b'.repeat(64), run_id: 'runA', review_id: 'reviewA', analyst: 'Case Analyst'};
  const reviewed = {...retainedCase, manifest: {...retainedCase.manifest, ...reviewContext}, latest_export: {sha256: reviewContext.package_sha256, name: 'runA.zip', download_url: '/api/exports/runA.zip'},
    latest_review: {review_id: 'reviewA', review: {schema_version: '2.2', run_id: 'runA', reviewer: 'Case Analyst', decision: 'keep_open', summary: 'Request the complete delivery record before resolving the case.', scope_finding_ids: ['context-A', 'volume-B'], acknowledge_limitations: true}}, review_validation: {ok: true}};
  run(`model.run = ${JSON.stringify(reviewed)}; model.flow.stage = 'package'; model.flow.cubeFace = 5; model.flow.inspectionFace = 5; model.flow.surfaceOpen = true; model.reviewDrafts = {}; renderGuided();`);
  let reviewerProfile = null;
  let accepted = [];
  let issued = [];
  let trusted = false;
  let inspectFailure = '';
  let profileDelay = async () => {};
  const reviewerCalls = [];
  const card = {schema_version: 'omphalos-reviewer-key/1', name: '<Independent Reviewer>', key_sha256: 'c'.repeat(64), public_key: {}};
  const receipt = {payload: {...reviewContext, reviewer_name: card.name, decision: 'approve', note: 'Compared the retained evidence against the analyst assessment.', created_at: '2026-10-18T18:00:00.000Z'}, signature: 'signature'};
  let inspection = {receipt, id: 'd'.repeat(64), signature_valid: true, trusted: false, own_key: false, same_analyst_name: false, reviewer: card};
  window.OmphalosReviewer = {
    async profile() {await profileDelay(); return reviewerProfile;},
    async createProfile(name, passphrase) {reviewerCalls.push({action: 'profile', name, passphrase}); reviewerProfile = {...card, name}; return reviewerProfile;},
    async receipts(ctx) {assert.deepEqual(JSON.parse(JSON.stringify(ctx)), reviewContext); return accepted.map(item => ({...item, trusted}));},
    async issued(ctx) {assert.deepEqual(JSON.parse(JSON.stringify(ctx)), reviewContext); return issued;},
    async sign(ctx, decision, note, passphrase) {reviewerCalls.push({action: 'sign', context: ctx, decision, note, passphrase}); const signed = {...receipt, payload: {...receipt.payload, decision, note}}; issued.push({...inspection, own_key: true, receipt: signed}); return signed;},
    async inspect(value, ctx) {reviewerCalls.push({action: 'inspect', context: ctx}); if (inspectFailure) throw new Error(inspectFailure); assert.deepEqual(JSON.parse(JSON.stringify(value)), receipt); return {...inspection, trusted};},
    async trustReviewer(value, fingerprint) {reviewerCalls.push({action: 'trust', fingerprint}); assert.deepEqual(value, card); if (fingerprint !== card.key_sha256) throw new Error('The fingerprint does not match.'); trusted = true;},
    async receive(value, ctx) {reviewerCalls.push({action: 'receive', context: ctx}); if (!trusted) throw new Error('Reviewer key is not trusted.'); accepted.push({...inspection, trusted});},
    async trustedReviewers() {return trusted ? [card] : [];},
    async forgetReviewer(fingerprint) {assert.equal(fingerprint, card.key_sha256); trusted = false;},
  };
  fetchImplementation = async (url) => {assert.equal(url, '/api/runs/runA'); return jsonResponse(reviewed);};
  context.downloadedReviews = [];
  run('downloadReviewJson = (value, name) => downloadedReviews.push({value, name});');
  function reviewerButton(action, id) {
    const result = button('');
    result.dataset = {reviewerAction: action, id};
    return result;
  }
  function reviewerClick(action, id) {node('#evidence-dialog').emit('click', {target: reviewerButton(action, id)});}
  function reviewerSubmit(id, fields) {node('#evidence-dialog').emit('submit', {target: {id, fields}, preventDefault() {}});}
  function chooseReceipt() {node('#evidence-dialog').emit('change', {target: {dataset: {reviewerFile: ''}, files: [{size: 100, text: async () => JSON.stringify(receipt)}], value: 'receipt'}});}
  async function openReview() {click(flowButton('independent-review')); await settle();}
  async function startReview() {reviewerClick('start-review'); await settle();}
"""


def run_reviewer(scenario: str) -> None:
    run_case_review(REVIEWER_SETUP + scenario)


def test_signing_requires_explicit_profile_decision_and_note() -> None:
    run_reviewer(r"""
  assert.match(run('flowPackageView()'), /Independent review/);
  await openReview();
  assert.ok(!node('#dialog-content').innerHTML.includes('<form'));
  assert.match(node('#dialog-content').innerHTML, /data-reviewer-action="start-review"/);
  await startReview();
  assert.match(node('#dialog-content').innerHTML, /reviewer-profile-form/);
  assert.equal(reviewerCalls.length, 0);
  reviewerSubmit('reviewer-profile-form', {name: 'Independent Reviewer', passphrase: 'long example passphrase', confirmation: 'long example passphrase'});
  await settle();
  assert.match(node('#dialog-content').innerHTML, /reviewer-sign-form/);
  assert.match(node('#dialog-content').innerHTML, /<option value="">Choose a decision/);
  assert.ok(!/selected/.test(node('#dialog-content').innerHTML));
  reviewerSubmit('reviewer-sign-form', {decision: 'request_changes', note: 'Obtain the delivery ledger before resolving the disagreement.', passphrase: 'long example passphrase'});
  await settle();
  const call = reviewerCalls.find(item => item.action === 'sign');
  assert.deepEqual(JSON.parse(JSON.stringify(call.context)), reviewContext);
  assert.equal(call.decision, 'request_changes');
  assert.equal(call.passphrase, 'long example passphrase');
  assert.ok(!run('JSON.stringify(model)').includes('long example passphrase'));
  assert.match(node('#dialog-content').innerHTML, /Signed in this browser/);
  assert.ok(!node('#dialog-content').innerHTML.includes('reviewer-sign-form'));
  assert.ok(!node('#dialog-content').innerHTML.includes('reviewer-profile-form'));
  assert.equal(accepted.length, 0);
  assert.equal(context.downloadedReviews.length, 1);
""")


def test_unknown_key_needs_external_fingerprint_before_retention() -> None:
    run_reviewer(r"""
  await openReview();
  chooseReceipt();
  await settle();
  const previewMarkup = node('#dialog-content').innerHTML;
  assert.match(previewMarkup, /&lt;Independent Reviewer&gt;/);
  assert.match(previewMarkup, /separate trusted channel/);
  assert.match(previewMarkup, /reviewer-trust-form/);
  assert.ok(!previewMarkup.includes('data-reviewer-action="accept-receipt"'));
  assert.equal(accepted.length, 0);
  assert.equal(trusted, false);
  reviewerSubmit('reviewer-trust-form', {fingerprint: 'f'.repeat(64)});
  await settle();
  assert.match(node('#reviewer-status').textContent, /does not match/);
  assert.equal(accepted.length, 0);
  reviewerSubmit('reviewer-trust-form', {fingerprint: card.key_sha256});
  await settle();
  assert.equal(accepted.length, 1);
  assert.match(node('#dialog-content').innerHTML, /Trusted reviewer key/);
  assert.ok(!node('#dialog-content').innerHTML.includes('reviewer-trust-form'));
  assert.ok(!node('#dialog-content').innerHTML.includes('reviewer-profile-form'));
""")


@pytest.mark.parametrize("self_kind", ["own_key", "same_analyst_name"])
def test_self_review_is_not_offered_as_independent_acceptance(self_kind: str) -> None:
    run_reviewer(r"""
  inspection[SELF_KIND] = true;
  await openReview();
  chooseReceipt();
  await settle();
  assert.match(node('#dialog-content').innerHTML, /cannot count as independent review/);
  assert.ok(!node('#dialog-content').innerHTML.includes('reviewer-trust-form'));
  assert.ok(!node('#dialog-content').innerHTML.includes('data-reviewer-action="accept-receipt"'));
  assert.equal(accepted.length, 0);
""".replace("SELF_KIND", repr(self_kind)))


def test_receipt_from_another_package_cannot_reach_trust_or_retention() -> None:
    run_reviewer(r"""
  inspectFailure = 'This receipt covers a different evidence package.';
  await openReview();
  chooseReceipt();
  await settle();
  assert.match(node('#reviewer-status').textContent, /different evidence package/);
  assert.equal(run('model.independentReview.pending'), null);
  assert.ok(!node('#dialog-content').innerHTML.includes('reviewer-trust-form'));
  assert.equal(accepted.length, 0);
  assert.equal(trusted, false);
""")


def test_revocation_retains_receipts_without_claiming_trust() -> None:
    run_reviewer(r"""
  trusted = true;
  accepted = [inspection];
  await openReview();
  assert.match(node('#dialog-content').innerHTML, /Trusted reviewer key/);
  reviewerClick('trust-settings');
  await settle();
  assert.match(node('#dialog-content').innerHTML, /Stop trusting this key/);
  reviewerClick('forget-key', card.key_sha256);
  await settle();
  assert.equal(accepted.length, 1);
  assert.match(node('#dialog-content').innerHTML, /Reviewer key not trusted/);
  assert.ok(!run('independentReceiptSummary(packageReviewContext())').includes('Approved'));
""")


def test_conflicting_reviews_are_all_shown_without_a_latest_winner() -> None:
    run_reviewer(r"""
  trusted = true;
  accepted = [inspection, {...inspection, id: 'e'.repeat(64), receipt: {...receipt, payload: {...receipt.payload, decision: 'request_changes', note: 'Delivery evidence remains incomplete; obtain the missing ledger.'}}}];
  await openReview();
  assert.match(node('#dialog-content').innerHTML, /Approved/);
  assert.match(node('#dialog-content').innerHTML, /Changes requested/);
  assert.match(node('#dialog-content').innerHTML, /Delivery evidence remains incomplete/);
  assert.match(run('independentReceiptSummary(packageReviewContext())'), /Conflicting signed reviews/);
""")


@pytest.mark.parametrize("change", ["close", "navigate", "other_dialog"])
def test_late_reviewer_load_cannot_reopen_or_replace_current_dialog(
    change: str,
) -> None:
    run_reviewer(r"""
  let release;
  profileDelay = () => new Promise(resolve => {release = resolve;});
  click(flowButton('independent-review'));
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
""".replace("CHANGE", repr(change)))


def test_changed_decision_or_failed_integrity_blocks_independent_review() -> None:
    run_reviewer(r"""
  run('model.reviewDrafts.runA = {...model.run.latest_review.review, decision: "escalate"};');
  assert.equal(run('packageReviewContext()'), null);
  assert.ok(!run('flowPackageView()').includes('data-flow="independent-review"'));
  run('model.reviewDrafts = {}; model.run.verification.ok = false;');
  assert.equal(run('packageReviewContext()'), null);
  assert.ok(!run('flowPackageView()').includes('data-flow="independent-review"'));
""")


@pytest.mark.parametrize("operation", ["sign", "receive"])
def test_revised_package_is_rechecked_before_signing_or_accepting(
    operation: str,
) -> None:
    run_reviewer(r"""
  reviewerProfile = card;
  trusted = true;
  await openReview();
  if (OPERATION === 'receive') {chooseReceipt(); await settle();}
  else await startReview();
  reviewed.latest_export = {...reviewed.latest_export, sha256: 'f'.repeat(64)};
  if (OPERATION === 'sign') reviewerSubmit('reviewer-sign-form', {decision: 'approve', note: 'The retained evidence supports the recorded decision.', passphrase: 'example passphrase'});
  else reviewerClick('accept-receipt');
  await settle();
  assert.match(node('#dialog-content').innerHTML, /case or package changed/);
  assert.equal(run('model.independentReview'), null);
  assert.equal(reviewerCalls.filter(call => ['sign', 'receive'].includes(call.action)).length, 0);
  assert.equal(accepted.length, 0);
""".replace("OPERATION", repr(operation)))


def test_integrity_failure_before_signing_invalidates_run() -> None:
    run_reviewer(r"""
  reviewerProfile = card;
  await openReview();
  await startReview();
  fetchImplementation = async () => ({...jsonResponse({error: 'Retained files failed verification.'}), ok: false, status: 409});
  reviewerSubmit('reviewer-sign-form', {decision: 'approve', note: 'The retained evidence supports the recorded decision.', passphrase: 'example passphrase'});
  await settle();
  assert.match(node('#dialog-content').innerHTML, /failed verification/);
  assert.equal(run('model.run.verification.ok'), false);
  assert.equal(run('model.independentReview'), null);
  assert.equal(reviewerCalls.filter(call => call.action === 'sign').length, 0);
""")


def test_passphrase_controls_are_cleared_and_mismatch_cannot_create_key() -> None:
    run_reviewer(r"""
  await openReview();
  await startReview();
  const controls = [{value: 'passphrase entered once'}, {value: 'different confirmation'}];
  node('#evidence-dialog').emit('submit', {target: {id: 'reviewer-profile-form', fields: {name: 'Reviewer', passphrase: controls[0].value, confirmation: controls[1].value}, querySelectorAll: () => controls}, preventDefault() {}});
  assert.deepEqual(controls.map(control => control.value), ['', '']);
  await settle();
  assert.match(node('#reviewer-status').textContent, /do not match/);
  assert.equal(reviewerCalls.filter(call => call.action === 'profile').length, 0);
  assert.ok(!run('JSON.stringify(model)').includes('passphrase entered once'));
""")


def test_external_trust_revocation_refreshes_only_receipt_status() -> None:
    run_reviewer(r"""
  trusted = true;
  accepted = [inspection];
  reviewerProfile = card;
  await openReview();
  const markup = node('#dialog-content').innerHTML;
  node('#reviewer-note').value = 'Do not erase this unsaved review note.';
  trusted = false;
  window.emit('omphalos-reviewer-trust-changed');
  await new Promise(resolve => setImmediate(resolve));
  await new Promise(resolve => setImmediate(resolve));
  assert.match(node('#reviewer-receipts').innerHTML, /Reviewer key not trusted/);
  assert.ok(!node('#reviewer-receipts').innerHTML.includes('Trusted reviewer key'));
  assert.equal(node('#dialog-content').innerHTML, markup);
  assert.equal(node('#reviewer-note').value, 'Do not erase this unsaved review note.');
""")


def test_back_from_signing_preserves_only_note_and_decision() -> None:
    run_reviewer(r"""
  reviewerProfile = card;
  await openReview();
  await startReview();
  assert.match(node('#dialog-content').innerHTML, /name="username" autocomplete="username"[^>]*hidden/);
  for (const [id, value] of [['reviewer-note', 'Retain this unresolved delivery question until more records arrive.'], ['reviewer-decision', 'request_changes'], ['reviewer-unlock', 'never persist this secret']]) {
    node('#evidence-dialog').emit('input', {target: {id, value}});
  }
  reviewerClick('back');
  await settle();
  assert.ok(!node('#dialog-content').innerHTML.includes('<form'));
  assert.ok(!run('JSON.stringify(model)').includes('never persist this secret'));
  await startReview();
  assert.match(node('#dialog-content').innerHTML, /Retain this unresolved delivery question/);
  assert.match(node('#dialog-content').innerHTML, /value="request_changes" selected/);
  assert.ok(!node('#dialog-content').innerHTML.includes('never persist this secret'));
""")


def test_default_received_and_issued_review_views_have_no_key_or_signing_form() -> None:
    run_reviewer(r"""
  trusted = true;
  accepted = [inspection];
  issued = [{...inspection, own_key: true}];
  reviewerProfile = card;
  await openReview();
  assert.match(node('#dialog-content').innerHTML, /Trusted reviewer key/);
  assert.match(node('#dialog-content').innerHTML, /Signed in this browser/);
  assert.ok(!node('#dialog-content').innerHTML.includes('<form'));
  assert.ok(!node('#dialog-content').innerHTML.includes('No signed reviews'));
""")
