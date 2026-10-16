"""Identity research requires a choice before it can change screening inputs."""

from __future__ import annotations

import pytest
from test_frontend_guards import run_scenario
from test_investigation_entry import ENTRY_SETUP

IDENTITY_SETUP = ENTRY_SETUP + r"""
  const candidate = {
    candidate_id: 'directory-candidate', name: 'Example <Research> Institute',
    description: 'Directory description <script>notExecutable()</script>',
    aliases: ['Example Research Institute'], entity_type: 'organization',
    fields: {country: 'RU', address: '12 <Research> Road', city: 'Example City'},
    claims: [{field: 'country', value: 'RU', source_label: 'Wikidata', kind: 'directory_claim', source_url: 'https://www.wikidata.org/wiki/Q123', record_id: 'Q123', pointer: '/entities/Q123/claims/P17'}],
    source_urls: ['https://www.wikidata.org/wiki/Q123'],
  };
  const selectedDataset = {...subjectDataset, dataset_id: 'identity-selected'};
  identityReport = {...identityReport, status: 'candidates', providers: [{id: 'wikidata', label: 'Wikidata', status: 'available'}], candidates: [candidate]};
  const entryFetch = fetchImplementation;
  let failSelection = false;
  fetchImplementation = async (url, options) => {
    if (url === '/api/workflow/identity-select') {
      const body = JSON.parse(options.body);
      if (body.candidate_id === null) return entryFetch(url, options);
      entryRequests.push({url, body});
      await entryIntercept(url, body);
      if (failSelection) return {...jsonResponse({error: 'The retained research no longer matches these records.'}), ok: false, status: 409};
      state.datasets.push(selectedDataset);
      return jsonResponse(selectedDataset);
    }
    return entryFetch(url, options);
  };
  function screeningRequests() {
    return entryRequests.filter(item => ['/api/workflow/plan', '/api/sources/fetch', '/api/workflow/run'].includes(item.url));
  }
"""


def run_identity(scenario: str) -> None:
    run_scenario(IDENTITY_SETUP + scenario)


def test_name_research_pauses_for_selection_and_uses_only_the_selected_derivation() -> (
    None
):
    run_identity(r"""
  submitSubject();
  await settle();
  assert.equal(run('model.flow.stage'), 'identity');
  assert.equal(run('model.flow.datasetId'), subjectDataset.dataset_id);
  assert.equal(run('model.flow.surfaceOpen'), true);
  assert.equal(run('flowCubeFaces()[0].complete'), false);
  assert.deepEqual(entryRequests.find(item => item.url === '/api/workflow/subject').body, {name: subject});
  assert.deepEqual(entryRequests.find(item => item.url === '/api/workflow/identity-research').body, {dataset_id: subjectDataset.dataset_id});
  assert.deepEqual(screeningRequests(), [], 'Research must not silently select a same-name entity or start screening.');
  assert.ok(main.innerHTML.includes('Example &lt;Research&gt; Institute'));
  assert.ok(main.innerHTML.includes('12 &lt;Research&gt; Road'));
  assert.ok(!main.innerHTML.includes('<script>notExecutable()</script>'));
  assert.ok(main.innerHTML.includes('Wikidata directory record'));
  assert.ok(main.innerHTML.includes('https://www.wikidata.org/wiki/Q123'));
  click(flowButton('identity-select', {id: candidate.candidate_id}));
  await settle();
  const selections = entryRequests.filter(item => item.url === '/api/workflow/identity-select');
  assert.equal(selections.length, 1);
  assert.deepEqual(selections[0].body, {dataset_id: subjectDataset.dataset_id, research_id: identityReport.research_id, candidate_id: candidate.candidate_id});
  const plans = entryRequests.filter(item => item.url === '/api/workflow/plan');
  assert.ok(plans.length > 0);
  assert.ok(plans.every(item => item.body.dataset_id === selectedDataset.dataset_id));
  const execution = entryRequests.find(item => item.url === '/api/workflow/run');
  assert.equal(execution.body.dataset_id, selectedDataset.dataset_id);
  assert.equal(execution.body.watchlist_snapshot_id, freshSource.snapshot_id);
  assert.equal(run('model.flow.stage'), 'review');
  assert.equal(run('model.flow.surfaceOpen'), false);
  assert.equal(run('Object.keys(model.reviewDrafts).length'), 0);
  assert.notEqual(notice.className, 'notice error');
""")


@pytest.mark.parametrize("status", ["no_match", "unavailable"])
def test_empty_or_unavailable_lookup_requires_explicit_name_only_continuation(
    status: str,
) -> None:
    run_identity(r"""
  identityReport = {...identityReport, status: STATUS, candidates: [], providers: [{id: 'wikidata', label: 'Wikidata', status: STATUS}]};
  submitSubject();
  await settle();
  assert.equal(run('model.flow.stage'), 'identity');
  assert.equal(run('flowCubeFaces()[0].complete'), false);
  assert.deepEqual(screeningRequests(), []);
  assert.ok(main.innerHTML.includes('data-flow="identity-skip"'));
  assert.ok(main.innerHTML.includes('data-flow="research-identity"'));
  assert.ok(!main.innerHTML.includes('data-flow="identity-select"'));
  assert.ok(main.innerHTML.includes(STATUS === 'unavailable' ? 'could not be reached' : 'no usable profile'));
  click(flowButton('identity-skip'));
  await settle();
  const execution = entryRequests.find(item => item.url === '/api/workflow/run');
  assert.ok(execution, 'Explicit continuation must remain available without a directory match.');
  assert.equal(execution.body.dataset_id, nameOnlyDataset.dataset_id);
  const continuation = entryRequests.find(item => item.url === '/api/workflow/identity-select');
  assert.deepEqual(continuation.body, {dataset_id: subjectDataset.dataset_id, research_id: identityReport.research_id, candidate_id: null});
  assert.equal(run('model.flow.stage'), 'review');
  assert.equal(entryRequests.filter(item => item.url === '/api/workflow/subject').length, 1);
  assert.equal(run('Object.keys(model.reviewDrafts).length'), 0);
""".replace("STATUS", repr(status)))


def test_lookup_retry_reuses_the_subject_and_does_not_start_screening() -> None:
    run_identity(r"""
  identityReport = {...identityReport, status: 'unavailable', candidates: []};
  submitSubject();
  await settle();
  identityReport = {...identityReport, research_id: 'second-research', status: 'candidates', candidates: [candidate]};
  click(flowButton('research-identity'));
  await settle();
  assert.equal(entryRequests.filter(item => item.url === '/api/workflow/subject').length, 1);
  assert.equal(entryRequests.filter(item => item.url === '/api/workflow/identity-research').length, 2);
  assert.equal(run('model.flow.identityResearch.research_id'), 'second-research');
  assert.equal(run('model.flow.datasetId'), subjectDataset.dataset_id);
  assert.equal(run('model.flow.stage'), 'identity');
  assert.deepEqual(screeningRequests(), []);
""")


@pytest.mark.parametrize("phase", ["research", "selection"])
@pytest.mark.parametrize("change", ["leave", "leave_and_return", "inputs"])
def test_stale_identity_response_cannot_change_the_chosen_view_or_start_checks(
    phase: str, change: str
) -> None:
    run_identity(r"""
  let release;
  let waiting = false;
  const stoppedUrl = PHASE === 'research' ? '/api/workflow/identity-research' : '/api/workflow/identity-select';
  entryIntercept = async url => {
    if (url !== stoppedUrl) return;
    waiting = true;
    await new Promise(resolve => {release = resolve;});
  };
  submitSubject();
  if (PHASE === 'selection') {
    await settle();
    click(flowButton('identity-select', {id: candidate.candidate_id}));
  }
  await until(() => waiting);
  const requestCount = entryRequests.length;
  if (CHANGE === 'inputs') run('invalidateFlow({datasetId: "different-records"});');
  else {
    navigate('data');
    if (CHANGE === 'leave_and_return') {
      navigate('investigate');
      click(flowButton('cube', {face: '5'}));
      assert.equal(run('model.flow.cubeFace'), 0, 'Package is unavailable before accepted intake and a recorded decision.');
    }
  }
  release();
  await settle();
  assert.deepEqual(screeningRequests(), []);
  assert.equal(run('model.selectedRun'), '');
  if (CHANGE === 'leave') assert.equal(run('model.page'), 'data');
  if (CHANGE === 'leave_and_return') assert.equal(run('model.flow.cubeFace'), 0);
  if (CHANGE === 'inputs') assert.equal(run('model.flow.datasetId'), 'different-records');
  assert.ok(!entryRequests.slice(requestCount).some(item => item.url === '/api/workflow/run'));
  assert.notEqual(notice.className, 'notice error');
""".replace("PHASE", repr(phase)).replace("CHANGE", repr(change)))


@pytest.mark.parametrize("phase", ["subject", "research"])
def test_stage_inspection_during_lookup_preserves_the_view_and_identity_choice(
    phase: str,
) -> None:
    run_identity(r"""
  let release;
  let waiting = false;
  let scrolls = 0;
  node('.object-surface').scrollIntoView = () => {scrolls += 1;};
  const stoppedUrl = PHASE === 'subject' ? '/api/workflow/subject' : '/api/workflow/identity-research';
  entryIntercept = async url => {
    if (url !== stoppedUrl) return;
    waiting = true;
    await new Promise(resolve => {release = resolve;});
  };
  submitSubject();
  await until(() => waiting);
  const navigation = run('model.navigationVersion');
  click(flowButton('cube', {face: '3'}));
  assert.equal(run('model.navigationVersion'), navigation, 'Unavailable Findings cannot interrupt identity lookup.');
  assert.equal(run('model.flow.autoViewChanged'), false);
  click(flowButton('cube', {face: '0'}));
  assert.equal(scrolls, 1, 'Choosing an available panel brings its working surface into view.');
  release();
  await settle();
  assert.equal(run('model.flow.stage'), 'identity');
  assert.equal(run('model.flow.identityResearch.research_id'), identityReport.research_id);
  assert.equal(run('model.flow.cubeFace'), 0);
  assert.equal(run('model.flow.inspectionFace'), 0);
  assert.equal(run('model.flow.surfaceOpen'), true);
  assert.equal(scrolls, 1, 'The lookup response must not move the view again.');
  assert.deepEqual(screeningRequests(), []);
""".replace("PHASE", repr(phase)))


def test_invalid_or_failed_selection_keeps_research_available_without_running_checks() -> (
    None
):
    run_identity(r"""
  submitSubject();
  await settle();
  click(flowButton('identity-select', {id: 'unreturned-candidate'}));
  await settle();
  assert.ok(!entryRequests.some(item => item.url === '/api/workflow/identity-select'));
  failSelection = true;
  click(flowButton('identity-select', {id: candidate.candidate_id}));
  await settle();
  assert.equal(notice.className, 'notice error');
  assert.equal(run('model.flow.stage'), 'identity');
  assert.equal(run('model.flow.datasetId'), subjectDataset.dataset_id);
  assert.equal(run('model.flow.identityResearch.research_id'), identityReport.research_id);
  assert.deepEqual(screeningRequests(), []);
  failSelection = false;
  click(flowButton('identity-select', {id: candidate.candidate_id}));
  await settle();
  assert.equal(run('model.flow.stage'), 'review');
  assert.equal(entryRequests.filter(item => item.url === '/api/workflow/run').length, 1);
""")


def test_duplicate_identity_selection_creates_one_derivation_and_one_run() -> None:
    run_identity(r"""
  submitSubject();
  await settle();
  let release;
  let waiting = false;
  entryIntercept = async url => {
    if (url !== '/api/workflow/identity-select') return;
    waiting = true;
    await new Promise(resolve => {release = resolve;});
  };
  click(flowButton('identity-select', {id: candidate.candidate_id}));
  await until(() => waiting);
  click(flowButton('identity-select', {id: candidate.candidate_id}));
  assert.equal(entryRequests.filter(item => item.url === '/api/workflow/identity-select').length, 1);
  release();
  await settle();
  assert.equal(entryRequests.filter(item => item.url === '/api/workflow/run').length, 1);
  assert.equal(run('model.flow.stage'), 'review');
""")
