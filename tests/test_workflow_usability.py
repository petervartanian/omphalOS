"""Exercise transitions between real intake, evidence, decision, and export paths."""

from __future__ import annotations

import pytest
from test_case_review_frontend import run_case_review
from test_guided_frontend import run_guided
from test_identity_frontend import run_identity


@pytest.mark.parametrize("saved_count", [0, 3])
def test_import_view_keeps_saved_records_in_open_without_changing_the_inventory(
    saved_count: int,
) -> None:
    run_guided(r"""
  const datasets = Array.from({length: SAVED_COUNT}, (_, index) => ({dataset_id: 'retained-version-' + index, label: 'Repeated subject', counts: {entities: 1}, intake_method: index ? 'subject_name' : 'vendor_csv'}));
  run(`model.state.datasets = ${JSON.stringify(datasets)}; model.state.runs = []; model.state.cases = []; model.flow = newFlow(); renderGuided();`);
  const inventory = run('JSON.stringify(model.state.datasets)');
  const requests = [];
  fetchImplementation = async url => {requests.push(url); throw new Error('Opening entry screens must not create, merge, or remove saved data.');};
  assert.ok(main.innerHTML.includes('id="flow-subject-form"'), 'Every fresh page starts with name entry and its Import/Open controls.');
  assert.ok(!main.innerHTML.includes('id="flow-vendor-file"'));
  assert.ok(!main.innerHTML.includes('Repeated subject'));
  click(flowButton('add-records'));
  assert.ok(main.innerHTML.includes('<h1>Import records</h1>'));
  assert.ok(main.innerHTML.includes('id="flow-vendor-file"'));
  assert.ok(main.innerHTML.includes('data-flow="open-work"'));
  assert.ok(!main.innerHTML.includes('Records already here'));
  assert.ok(!main.innerHTML.includes('data-flow="investigate-dataset"'));
  assert.ok(!main.innerHTML.includes('Repeated subject'));
  assert.ok(!main.innerHTML.includes('Saved records ↓'));
  click(flowButton('open-work'));
  const saved = node('#dialog-content').innerHTML;
  assert.equal(node('#evidence-dialog').showModalCount, 1);
  assert.equal((saved.match(/data-flow="investigate-dataset"/g) || []).length, SAVED_COUNT);
  datasets.forEach(dataset => assert.ok(saved.includes('data-id="' + dataset.dataset_id + '"')));
  if (!SAVED_COUNT) assert.ok(saved.includes('No saved work yet.'));
  assert.equal(run('JSON.stringify(model.state.datasets)'), inventory);
  assert.deepEqual(requests, []);
""".replace("SAVED_COUNT", str(saved_count)))


def test_saved_records_distinguish_original_selected_and_name_only_without_mutation() -> (
    None
):
    run_guided(r"""
  const datasets = [
    {dataset_id: 'entered-name', label: 'Example Company', counts: {entities: 1}, intake_method: 'subject_name', identity_research_retained: false},
    {dataset_id: 'selected-profile', label: 'Example Company', counts: {entities: 1}, intake_method: 'subject_name', identity_research_retained: true, parent_dataset_id: 'entered-name', identity_association: 'user_selected_public_record', identity_profile: {name: 'Example <Holding> N.V.', sources: ['GLEIF legal entity records']}},
    {dataset_id: 'name-only', label: 'Example Company', counts: {entities: 1}, intake_method: 'subject_name', identity_research_retained: true, parent_dataset_id: 'entered-name', identity_association: 'no_profile_selected'},
    {dataset_id: 'selected-directory', label: 'Example Company', counts: {entities: 1}, identity_association: 'user_selected_public_record', identity_profile: {name: 'Example Company directory entry', sources: ['Wikidata public directory']}},
    {dataset_id: 'imported-file', label: 'Quarterly records', counts: {entities: 4, payments: 12}, intake_method: 'linked_records'},
  ];
  run(`model.state.datasets=${JSON.stringify(datasets)}; model.state.runs=[];`);
  const before=run('JSON.stringify(model.state.datasets)');
  const requests=[];
  fetchImplementation=async(url)=>{requests.push(url);throw new Error('Opening records cannot alter them.');};
  click(flowButton('open-work'));
  const html=node('#dialog-content').innerHTML;
  const entries=html.match(/<li>.*?<\/li>/g);
  assert.equal(entries.length,5);
  assert.match(entries[0],/Example Company/);assert.match(entries[0],/Original name \/ 1 entity/);
  assert.match(entries[1],/Example &lt;Holding&gt; N.V./);assert.match(entries[1],/Selected GLEIF details \/ 1 entity/);
  assert.doesNotMatch(html,/<Holding>/);
  assert.match(entries[2],/Name only \/ 1 entity/);
  assert.match(entries[3],/Selected Wikidata details/);assert.doesNotMatch(entries[3],/verified|registry/i);
  assert.match(entries[4],/Quarterly records/);assert.doesNotMatch(entries[4],/Selected|Original name|Name only/);
  for (const dataset of datasets) assert.ok(html.includes('data-id="'+dataset.dataset_id+'"'));
  assert.equal(run('JSON.stringify(model.state.datasets)'),before);
  assert.deepEqual(requests,[]);
""")


@pytest.mark.parametrize("goal_inferred", [False, True])
def test_change_files_recovers_invalid_preview_and_preserves_intake_context(
    goal_inferred: bool,
) -> None:
    run_guided(r"""
  const invalid = {...previewed(), can_import: false, errors: ['Country <invalid> must be a recognized country name or code.']};
  run(`Object.assign(model.flow, {stage: 'data', surfaceOpen: true, goalId: 'transaction_review', goalInferred: INFERRED, asOf: '2021-07-05', snapshotId: 'historical-source', sourcePolicy: 'selected', files: [{name: 'invalid.csv', content_base64: 'bad'}], preview: ${JSON.stringify(invalid)}, mapping: ${JSON.stringify(invalid.mapping)}, plan: {can_run: true}}); renderGuided();`);
  assert.match(main.innerHTML, /data-flow="change-files">Change files/);
  assert.match(main.innerHTML, /data-flow="import" disabled/);
  assert.ok(main.innerHTML.includes('Country &lt;invalid&gt;'));
  const requests = [];
  fetchImplementation = async (url, options) => {
    requests.push({url, body: JSON.parse(options.body)});
    assert.equal(url, '/api/workflow/preview', 'Changing files and previewing a replacement must not import either file.');
    return jsonResponse({...previewed(), file_name: 'replacement.csv', preview_id: 'replacement-preview'});
  };
  click(flowButton('change-files'));
  assert.equal(run('model.flow.stage'), 'data');
  assert.equal(run('model.flow.cubeFace'), 0);
  assert.equal(run('model.flow.surfaceOpen'), true);
  assert.equal(run('model.flow.datasetId'), '');
  assert.equal(run('model.flow.preview'), null);
  assert.equal(run('model.flow.previewStale'), false);
  assert.equal(run('model.flow.files.length'), 0);
  assert.equal(run('Object.keys(model.flow.mapping).length'), 0);
  assert.equal(run('model.flow.plan'), null);
  assert.equal(run('model.flow.goalId'), 'transaction_review');
  assert.equal(run('model.flow.goalInferred'), INFERRED);
  assert.equal(run('model.flow.asOf'), '2021-07-05');
  assert.equal(run('model.flow.snapshotId'), 'historical-source');
  assert.equal(run('model.flow.sourcePolicy'), 'selected');
  assert.ok(main.innerHTML.includes('id="flow-vendor-file"'));
  assert.ok(!main.innerHTML.includes('Import preview'));
  assert.ok(node('#flow-vendor-file').focusCount > 0);
  assert.deepEqual(requests, []);
  main.emit('change', {target: fileControl('replacement.csv', 'Supplier,Country\nSynthetic Replacement,US\n')});
  await settle();
  assert.equal(requests.length, 1);
  assert.equal(requests[0].body.files[0].name, 'replacement.csv');
  assert.ok(!Object.hasOwn(requests[0].body, 'mapping'), 'The discarded file mapping cannot leak into the replacement preview.');
  assert.equal(run('model.flow.preview.preview_id'), 'replacement-preview');
  assert.equal(run('model.flow.datasetId'), '');
""".replace("INFERRED", str(goal_inferred).lower()))


def test_change_files_cancels_a_pending_mapping_preview_without_importing() -> None:
    run_guided(r"""
  const initial = previewed();
  run(`Object.assign(model.flow, {stage: 'data', surfaceOpen: true, files: [{name: 'previous.csv'}], preview: ${JSON.stringify(initial)}, mapping: ${JSON.stringify(initial.mapping)}}); renderGuided();`);
  let release;
  fetchImplementation = async (url) => {
    assert.equal(url, '/api/workflow/preview');
    return new Promise(resolve => {release = resolve;});
  };
  click(flowButton('repreview'));
  await until(() => Boolean(release));
  click(flowButton('change-files'));
  release(jsonResponse({...previewed(), preview_id: 'discarded-preview'}));
  await settle();
  assert.equal(run('model.flow.preview'), null);
  assert.equal(run('model.flow.files.length'), 0);
  assert.equal(run('model.flow.datasetId'), '');
  assert.ok(main.innerHTML.includes('id="flow-vendor-file"'));
  assert.ok(!main.innerHTML.includes('Import preview'));
  assert.notEqual(notice.className, 'notice error');
""")


def test_transaction_records_after_a_named_subject_infer_transaction_checks() -> None:
    run_identity(r"""
  submitSubject();
  await settle();
  click(flowButton('identity-select', {id: candidate.candidate_id}));
  await settle();
  const transactions = {dataset_id: 'transactions-after-subject', label: 'Quarterly transactions', counts: {entities: 2, shipments: 16, payments: 7}};
  state.datasets.push(transactions);
  run(`model.state = ${JSON.stringify(state)};`);
  const priorExecutions = entryRequests.filter(item => item.url === '/api/workflow/run').length;
  click(flowButton('investigate-dataset', {id: transactions.dataset_id}));
  await settle();
  const plan = entryRequests.filter(item => item.url === '/api/workflow/plan').at(-1).body;
  const execution = entryRequests.filter(item => item.url === '/api/workflow/run').at(-1).body;
  assert.equal(plan.goal_id, 'transaction_review');
  assert.equal(execution.goal_id, 'transaction_review');
  assert.equal(execution.dataset_id, transactions.dataset_id);
  assert.ok(!Object.hasOwn(execution, 'watchlist_snapshot_id'), 'An earlier name search cannot pin new transaction records to screening.');
  assert.equal(entryRequests.filter(item => item.url === '/api/workflow/run').length, priorExecutions + 1);
""")


def test_reopening_an_unfinished_direct_subject_resumes_public_identity_choice() -> (
    None
):
    run_identity(r"""
  state.datasets.push({...subjectDataset, intake_method: 'subject_name', identity_research_retained: false});
  run(`model.state = ${JSON.stringify(state)};`);
  click(flowButton('investigate-dataset', {id: subjectDataset.dataset_id}));
  await settle();
  assert.equal(run('model.flow.stage'), 'identity');
  assert.equal(entryRequests.filter(item => item.url === '/api/workflow/subject').length, 0);
  assert.equal(entryRequests.filter(item => item.url === '/api/workflow/identity-research').length, 1);
  assert.deepEqual(screeningRequests(), []);
  assert.ok(main.innerHTML.includes('Use this identity'));
""")


def test_reopening_an_explicit_name_only_choice_does_not_repeat_identity_setup() -> (
    None
):
    run_identity(r"""
  state.datasets.push({...nameOnlyDataset, intake_method: 'subject_name', identity_research_retained: true});
  run(`model.state = ${JSON.stringify(state)};`);
  click(flowButton('investigate-dataset', {id: nameOnlyDataset.dataset_id}));
  await settle();
  assert.equal(run('model.flow.stage'), 'review');
  assert.ok(!entryRequests.some(item => item.url === '/api/workflow/identity-research'));
  assert.equal(entryRequests.filter(item => item.url === '/api/workflow/run').length, 1);
  assert.equal(entryRequests.find(item => item.url === '/api/workflow/run').body.dataset_id, nameOnlyDataset.dataset_id);
""")


def test_hard_identity_failure_offers_retry_and_reuses_the_entered_subject() -> None:
    run_identity(r"""
  const normalFetch = fetchImplementation;
  let failed = false;
  fetchImplementation = async (url, options) => {
    if (url === '/api/workflow/identity-research' && !failed) {
      failed = true;
      entryRequests.push({url, body: JSON.parse(options.body)});
      return {...jsonResponse({error: 'Lookup <temporarily unavailable>.'}), ok: false, status: 503};
    }
    return normalFetch(url, options);
  };
  submitSubject();
  await settle();
  assert.equal(run('model.flow.stage'), 'identity');
  assert.equal(run('model.flow.datasetId'), subjectDataset.dataset_id);
  assert.ok(main.innerHTML.includes('Identity lookup paused'));
  assert.ok(main.innerHTML.includes('Lookup &lt;temporarily unavailable&gt;.'));
  assert.ok(!main.innerHTML.includes('Looking up the identity…'));
  assert.ok(main.innerHTML.includes('data-flow="research-identity"'));
  assert.deepEqual(screeningRequests(), []);
  click(flowButton('research-identity'));
  await settle();
  assert.equal(entryRequests.filter(item => item.url === '/api/workflow/subject').length, 1);
  assert.equal(entryRequests.filter(item => item.url === '/api/workflow/identity-research').length, 2);
  assert.equal(run('model.flow.identityError'), '');
  assert.equal(run('model.flow.identityResearch.research_id'), identityReport.research_id);
  assert.ok(main.innerHTML.includes('Use this identity'));
""")


def test_failed_lookup_for_an_abandoned_subject_does_not_replace_new_work() -> None:
    run_identity(r"""
  let release;
  const normalFetch = fetchImplementation;
  fetchImplementation = async (url, options) => {
    if (url === '/api/workflow/identity-research')
      return new Promise(resolve => {release = resolve;});
    return normalFetch(url, options);
  };
  submitSubject();
  await until(() => Boolean(release));
  navigate('data');
  release({...jsonResponse({error: 'The earlier lookup failed.'}), ok: false, status: 503});
  await settle();
  assert.equal(run('model.page'), 'data');
  assert.equal(run('model.flow.identityError'), '');
  assert.notEqual(notice.className, 'notice error');
  assert.deepEqual(screeningRequests(), []);
""")


def test_retained_names_replace_exact_ids_without_changing_evidence_or_inventing_names() -> (
    None
):
    run_case_review(r"""
  const observation = 'Exporter E1 and E10 share E1-reference; unrelated E100 is unchanged.';
  const names = {E1: 'Orion & Co.', E10: '<Orion Archive>', E100: 'Must not appear'};
  run(`model.run.entity_names = ${JSON.stringify(names)}; model.run.analysis.findings[1].observation = ${JSON.stringify(observation)}; model.run.analysis.findings[1].entity_ids = ['E1', 'E10'];`);
  const display = run('findingObservation(model.run.analysis.findings[1])');
  assert.equal(display, 'Exporter Orion & Co. and <Orion Archive> share E1-reference; unrelated E100 is unchanged.');
  assert.equal(run('model.run.analysis.findings[1].observation'), observation);
  const markup = run('flowFindingsView()');
  assert.ok(markup.includes('Orion &amp; Co.'));
  assert.ok(markup.includes('&lt;Orion Archive&gt;'));
  assert.ok(!markup.includes('<Orion Archive>'));
  assert.ok(!markup.includes('Must not appear'));
  run('model.run.verification.ok = false;');
  assert.equal(run('findingObservation(model.run.analysis.findings[1])'), observation);
""")


def test_evidence_tables_show_retained_names_and_preserve_original_ids() -> None:
    run_case_review(r"""
  run('model.run.entity_names = {E1: "Orion & Co."};');
  const cell = run('evidenceTableCell("exporter_id", "E1")');
  assert.ok(cell.includes('Orion &amp; Co.'));
  assert.ok(cell.includes('>E1</small>'));
  assert.equal(run('evidenceTableCell("shipment_id", "E1")'), 'E1', 'An equal-looking shipment ID cannot be treated as an entity.');
  assert.equal(run('evidenceTableCell("exporter_id", "unknown-entity")'), 'unknown-entity');
""")


def test_archived_source_attribution_does_not_depend_on_live_source_inventory() -> None:
    run_case_review(r"""
  run(`model.state.sources = []; model.run.case.watchlist_snapshot_id = 'retained-reference'; model.run.screening_source = {snapshot_id: 'retained-reference', source_id: 'csl', record_count: 26127, fetched_at: '2026-09-01T12:00:00Z', source_updated_at: '2026-09-01', ingestion_method: 'official_https'}; model.run.analysis.coverage.push({investigation_id: 'screening_candidates', status: 'executed', records_evaluated: 1, findings_count: 0});`);
  const brief = run('flowScreeningBrief(model.run)');
  assert.ok(brief.includes('26,127 entries'));
  assert.ok(brief.includes('Sep 1, 2026'));
  const sources = run('flowFaceView(1)');
  assert.ok(sources.includes('26,127') || sources.includes('26127'));
  assert.ok(sources.includes('Sep 1, 2026'));
  assert.ok(!sources.includes('No screening list was required'));
  assert.equal(run('flowCubeFaces()[1].value'), '26,127');
""")


def test_a_changed_decision_cannot_export_or_download_the_older_saved_assessment() -> (
    None
):
    run_case_review(r"""
  const saved = {schema_version: '2.1', run_id: 'runA', reviewer: 'Analyst Example', decision: 'keep_open', summary: 'Awaiting the complete shipment ledger.', scope_finding_ids: ['context-A', 'volume-B'], acknowledge_limitations: true};
  run(`model.run.latest_review = {review_id: 'earlier-review', review: ${JSON.stringify(saved)}}; model.run.latest_export = {name: 'earlier.zip', download_url: '/api/exports/earlier.zip'}; model.reviewDrafts.runA = {...model.run.latest_review.review, summary: 'The new ledger changes the proposed next step.'};`);
  const packageMarkup = run('flowPackageView()');
  assert.ok(packageMarkup.includes('unsaved edits'));
  assert.match(packageMarkup, /data-action="export" disabled/);
  assert.ok(!packageMarkup.includes('/api/exports/earlier.zip'));
  const requests = [];
  fetchImplementation = async url => {requests.push(url); throw new Error('A changed unsaved decision must not export an old assessment.');};
  await assert.rejects(run('exportRun()'), /Save the edited case decision/);
  assert.deepEqual(requests, []);
  assert.equal(run('model.run.latest_review.review.summary'), saved.summary);
""")


def test_completed_package_keeps_its_download_link_after_reopening() -> None:
    run_case_review(r"""
  const saved = {schema_version: '2.1', run_id: 'runA', reviewer: 'Analyst Example', decision: 'keep_open', summary: '', scope_finding_ids: ['context-A', 'volume-B'], acknowledge_limitations: true};
  run(`model.run.latest_review = {review_id: 'saved-review', review: ${JSON.stringify(saved)}}; model.run.latest_export = {name: 'retained-package.zip', download_url: '/api/exports/retained-package.zip'};`);
  const markup = run('flowPackageView()');
  assert.ok(markup.includes('href="/api/exports/retained-package.zip" download'));
  assert.ok(!markup.includes('data-action="export"'), 'Opening a completed artifact must not require creating it again.');
  const legacyPage = run('renderRunDetail()');
  assert.ok(legacyPage.includes('href="/api/exports/retained-package.zip" download'));
""")


@pytest.mark.parametrize("action", ["verify", "replay"])
@pytest.mark.parametrize("page", ["investigate", "runs"])
def test_run_checks_preserve_the_current_package_download(
    action: str, page: str
) -> None:
    run_case_review(r"""
  const saved = {schema_version: '2.1', run_id: 'runA', reviewer: 'Analyst Example', decision: 'keep_open', summary: '', scope_finding_ids: ['context-A', 'volume-B'], acknowledge_limitations: true};
  const retained = {...retainedCase, latest_review: {review_id: 'saved-review', review: saved}, latest_export: {name: 'retained-package.zip', download_url: '/api/exports/retained-package.zip'}};
  run(`model.run = ${JSON.stringify(retained)}; Object.assign(model.flow, {stage: 'package', cubeFace: 5, inspectionFace: 5, surfaceOpen: true});`);
  navigate(PAGE);
  const requests = [];
  fetchImplementation = async (url) => {
    requests.push(url);
    if (url === '/api/runs/runA/' + ACTION) return jsonResponse(ACTION === 'verify' ? {ok: true, files_checked: 8, issues: []} : {ok: true, code_match: true, issues: [], expected_digest: 'retained-digest', actual_digest: 'retained-digest'});
    assert.equal(url, '/api/runs/runA');
    return jsonResponse(retained);
  };
  click(button(ACTION));
  await settle();
  assert.deepEqual(requests, ['/api/runs/runA/' + ACTION, '/api/runs/runA']);
  const markup = node('#run-result').innerHTML;
  assert.ok(markup.includes('href="/api/exports/retained-package.zip" download'));
  assert.ok(markup.includes(ACTION === 'verify' ? 'Verification result' : 'Replay result'));
  if (PAGE === 'investigate') assert.ok(markup.includes(ACTION === 'verify' ? '8 files checked.' : 'Findings and coverage reproduced'));
  else assert.ok(markup.includes(ACTION === 'verify' ? 'files_checked' : 'actual_digest'));
""".replace("ACTION", repr(action)).replace("PAGE", repr(page)))


@pytest.mark.parametrize("blocker", ["unsaved", "unverified"])
def test_run_checks_do_not_restore_a_package_download_for_an_unready_case(
    blocker: str,
) -> None:
    run_case_review(r"""
  const saved = {schema_version: '2.1', run_id: 'runA', reviewer: 'Analyst Example', decision: 'keep_open', summary: '', scope_finding_ids: ['context-A', 'volume-B'], acknowledge_limitations: true};
  const retained = {...retainedCase, latest_review: {review_id: 'saved-review', review: saved}, latest_export: {name: 'old-package.zip', download_url: '/api/exports/old-package.zip'}, verification: {ok: BLOCKER !== 'unverified', issues: []}};
  run(`model.run = ${JSON.stringify(retained)}; Object.assign(model.flow, {stage: 'package', cubeFace: 5, inspectionFace: 5, surfaceOpen: true});`);
  if (BLOCKER === 'unsaved') run(`model.reviewDrafts.runA = {...${JSON.stringify(saved)}, summary: 'New evidence needs a revised decision.'};`);
  run('renderGuided();');
  fetchImplementation = async (url) => {
    if (url === '/api/runs/runA/replay') return jsonResponse({ok: BLOCKER !== 'unverified'});
    assert.equal(url, '/api/runs/runA');
    return jsonResponse(retained);
  };
  click(button('replay'));
  await settle();
  assert.ok(node('#run-result').innerHTML.includes('Replay result'));
  assert.ok(!node('#run-result').innerHTML.includes('/api/exports/old-package.zip'));
""".replace("BLOCKER", repr(blocker)))


def test_resume_restores_case_context_and_reopens_an_unsaved_decision() -> None:
    run_case_review(r"""
  const saved = {schema_version: '2.1', run_id: 'runA', reviewer: 'Analyst Example', decision: 'keep_open', summary: 'Awaiting original records from the supplier.', scope_finding_ids: ['context-A', 'volume-B'], acknowledge_limitations: true};
  const retained = {...retainedCase, case: {...retainedCase.case, as_of: '2021-07-05', investigations: ['screening_candidates', 'data_quality'], watchlist_snapshot_id: 'historical-snapshot'}, latest_review: {review_id: 'saved-review', review: saved}};
  run(`model.reviewDrafts.runA = {...${JSON.stringify(saved)}, summary: 'New supporting records require a revised decision.'}; Object.assign(model.flow, {settingsOpen: true, sourceRetry: true, asOf: '2026-10-15', goalId: 'transaction_review', files: [{name: 'obsolete.csv'}], mapping: {Obsolete: 'name'}, preview: {can_import: true}});`);
  fetchImplementation = async url => {assert.equal(url, '/api/runs/runA'); return jsonResponse(retained);};
  click(flowButton('resume', {id: 'runA'}));
  await settle();
  assert.equal(run('model.flow.stage'), 'review');
  assert.equal(run('model.flow.cubeFace'), 4);
  assert.equal(run('model.flow.asOf'), '2021-07-05');
  assert.equal(run('model.flow.snapshotId'), 'historical-snapshot');
  assert.equal(run('model.flow.sourcePolicy'), 'selected');
  assert.equal(run('model.flow.goalId'), 'counterparty_screening');
  assert.equal(run('model.flow.sourceRetry'), false);
  assert.equal(run('model.flow.preview'), null);
  assert.equal(run('model.flow.files.length'), 0);
  assert.equal(run('model.flow.settingsOpen'), false);
  assert.equal(run('model.reviewDrafts.runA.summary'), 'New supporting records require a revised decision.');
""")


def test_new_investigation_keeps_old_drafts_without_showing_them_on_its_cube() -> None:
    run_case_review(r"""
  const draft = {schema_version: '2.1', run_id: 'runA', reviewer: 'Analyst Example', decision: 'keep_open', summary: 'An earlier case still needs its shipment ledger.', scope_finding_ids: ['context-A', 'volume-B'], acknowledge_limitations: true};
  run(`model.reviewDrafts.runA = ${JSON.stringify(draft)};`);
  click(flowButton('restart'));
  assert.equal(run('model.flow.stage'), 'goal');
  const faces = JSON.parse(run('JSON.stringify(flowCubeFaces())'));
  assert.ok(faces.every(face => !face.complete));
  assert.equal(faces[4].value, '—');
  assert.equal(faces[3].value, '—');
  assert.equal(run('model.reviewDrafts.runA.summary'), draft.summary);
""")


@pytest.mark.parametrize("face", [0, 1, 2, 3, 5])
def test_continue_moves_through_retained_stages_in_sequence(
    face: int,
) -> None:
    run_case_review(r"""
  run(`Object.assign(model.flow, {stage: 'review', cubeFace: FACE, inspectionFace: FACE, surfaceOpen: true}); renderGuided();`);
  click(flowButton('continue'));
  assert.equal(run('model.flow.cubeFace'), FACE < 4 ? FACE + 1 : 4);
  assert.equal(run('model.flow.inspectionFace'), FACE < 4 ? FACE + 1 : 4);
  assert.equal(run('model.flow.surfaceOpen'), true);
  assert.equal(run('Object.keys(model.reviewDrafts).length'), 0);
  assert.ok(node('.object-surface').focusCount > 0);
""".replace("FACE", str(face)))


def test_editing_a_decision_during_export_does_not_expose_the_old_package_as_current() -> (
    None
):
    run_case_review(r"""
  const saved = {schema_version: '2.1', run_id: 'runA', reviewer: 'Analyst Example', decision: 'keep_open', summary: '', scope_finding_ids: ['context-A', 'volume-B'], acknowledge_limitations: true};
  const artifact = {name: 'earlier-decision.zip', download_url: '/api/exports/earlier-decision.zip'};
  run(`model.run.latest_review = {review_id: 'saved-review', review: ${JSON.stringify(saved)}}; Object.assign(model.flow, {stage: 'package', cubeFace: 5, inspectionFace: 5, surfaceOpen: true}); renderGuided();`);
  const retained = JSON.parse(run('JSON.stringify(model.run)'));
  let release;
  fetchImplementation = async url => {
    if (url === '/api/runs/runA/export') return new Promise(resolve => {release = resolve;});
    assert.equal(url, '/api/runs/runA');
    return jsonResponse({...retained, latest_export: artifact});
  };
  const pending = run('exportRun()');
  run(`model.reviewDrafts.runA = {...model.run.latest_review.review, summary: 'The new invoice changes the proposed next step.'};`);
  release(jsonResponse(artifact));
  await pending;
  assert.ok(!node('#run-result').innerHTML.includes(artifact.download_url));
  assert.ok(node('#run-result').innerHTML.includes('previously recorded decision'));
  assert.equal(run('flowCubeFaces()[5].complete'), false);
  assert.equal(run('model.reviewDrafts.runA.summary'), 'The new invoice changes the proposed next step.');
""")


def test_package_completion_requires_the_export_verified_for_the_latest_decision() -> (
    None
):
    run_case_review(r"""
  const saved = {schema_version: '2.1', run_id: 'runA', reviewer: 'Analyst Example', decision: 'keep_open', summary: '', scope_finding_ids: ['context-A', 'volume-B'], acknowledge_limitations: true};
  const artifact = {name: 'previous-review.zip', download_url: '/api/exports/previous-review.zip'};
  run(`model.run.latest_review = {review_id: 'saved-review', review: ${JSON.stringify(saved)}}; Object.assign(model.flow, {stage: 'package', cubeFace: 5, inspectionFace: 5, surfaceOpen: true}); renderGuided();`);
  const retained = JSON.parse(run('JSON.stringify(model.run)'));
  fetchImplementation = async url => {
    if (url === '/api/runs/runA/export') return jsonResponse(artifact);
    assert.equal(url, '/api/runs/runA');
    return jsonResponse({...retained, latest_review: {review_id: 'new-review', review: {...saved, decision: 'escalate'}}, latest_export: null});
  };
  await run('exportRun()');
  assert.ok(!node('#run-result').innerHTML.includes(artifact.download_url));
  assert.ok(node('#run-result').innerHTML.includes('changed while'));
  assert.equal(run('flowCubeFaces()[5].complete'), false);
""")
