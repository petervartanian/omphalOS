"""Drive navigation and delayed responses through the actual browser event handlers.

The small DOM adapter supports the controls involved in these state regressions;
it is not a substitute for browser layout, keyboard, or accessibility inspection.
No package downloads or network access are needed.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

APP_SCRIPT = Path(__file__).parents[1] / "src/omphalos/ui/app.js"

HARNESS = r"""
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const nodes = new Map();
let currentCaseForm = null;
let currentReviewForm = null;
class Element {
  constructor(selector) {
    this.selector = selector;
    this.listeners = new Map();
    this.dataset = {};
    this.attributes = {};
    this.style = {};
    this.className = '';
    this.textContent = '';
    this.hidden = false;
    this.disabled = false;
    this.focusCount = 0;
    this.showModalCount = 0;
    this.html = '';
    this.classList = { toggle() {}, add() {}, remove() {} };
  }
  addEventListener(type, listener) {
    const listeners = this.listeners.get(type) || [];
    listeners.push(listener);
    this.listeners.set(type, listeners);
  }
  emit(type, event = {}) {
    event.target ||= this;
    for (const listener of this.listeners.get(type) || []) listener(event);
  }
  setAttribute(name, value) { this.attributes[name] = String(value); }
  getAttribute(name) { return this.attributes[name] ?? null; }
  removeAttribute(name) { delete this.attributes[name]; }
  querySelectorAll() { return []; }
  closest(selector) { return selector === 'button' && this.tagName === 'BUTTON' ? this : null; }
  focus() { this.focusCount += 1; }
  showModal() { this.showModalCount += 1; }
  close() {}
  scrollIntoView() {}
  set innerHTML(value) {
    this.html = String(value);
    if (this.selector === '#main') { currentCaseForm = null; currentReviewForm = null; }
  }
  get innerHTML() { return this.html; }
}
function node(selector) {
  if (!nodes.has(selector)) nodes.set(selector, new Element(selector));
  return nodes.get(selector);
}
const main = node('#main');
const notice = node('#notice');
const skipLink = node('.skip-link');
nodes.set('#skip-navigation', skipLink);
skipLink.tagName = 'A';
skipLink.href = '#main';
skipLink.closest = (selector) => selector.includes('skip') || selector === 'a' ? skipLink : null;
const document = new Element('document');
document.body = node('body');
document.querySelector = (selector) => {
  if (selector === '#case-form') return currentCaseForm;
  if (selector === '#review-form') return currentReviewForm;
  if (selector === '#run-result' && !main.innerHTML.includes('id="run-result"')) return null;
  if (selector.includes('skip-link')) return skipLink;
  return node(selector);
};
document.querySelectorAll = () => [];
const window = new Element('window');
window.scrollTo = () => {};
window.confirm = () => true;
const location = {hash: '#overview'};
class FormData {
  constructor(form) { this.fields = form.fields; }
  get(name) { const value = this.fields[name] ?? ''; return Array.isArray(value) ? value[0] : value; }
  getAll(name) { const value = this.fields[name]; return Array.isArray(value) ? value : value === undefined ? [] : [value]; }
  has(name) { return Object.hasOwn(this.fields, name); }
}
const state = {
  token: 'synthetic-session-token', datasets: [{dataset_id: 'datasetA', label: 'Fixture data', counts: {entities: 1}, synthetic: true}],
  sources: [], cases: [], runs: [{run_id: 'runA', case_id: 'caseA', findings_count: 0}],
  catalog: [{id: 'data_quality', title: 'Data quality', description: 'Inspect supplied records.', parameters: {}, required_tables: [], limitations: []}],
  source_catalog: [], data_schema: {tables: {}}, limits: {upload_bytes: 50331648},
};
const runA = {
  workflow: {status: 'recorded', records_selected: true, source_accepted: true, plan_approved: true},
  manifest: {run_id: 'runA', case_id: 'caseA'}, case: {case_id: 'caseA', question: 'Inspect the synthetic supplied records.', as_of: '2026-10-13'},
  analysis: {findings: [], coverage: [], scope_counts: {}, warnings: []},
  latest_review: {review_id: 'reviewA', review: {findings: []}}, review_validation: {ok: true, issues: []}, verification: {ok: true, issues: []},
};
let fetchImplementation = () => new Promise(() => {});
const context = vm.createContext({document, window, location, FormData, console, setTimeout, clearTimeout, URL, URLSearchParams, AbortController,
  fetch: (...args) => fetchImplementation(...args)});
vm.runInContext(fs.readFileSync(process.argv[1], 'utf8'), context);
const run = (code) => vm.runInContext(code, context);
run(`model.state = ${JSON.stringify(state)}; model.run = ${JSON.stringify(runA)}; model.selectedRun = 'runA';`);
function jsonResponse(value) { return {ok: true, status: 200, headers: {get: () => 'application/json'}, json: async () => value, text: async () => JSON.stringify(value)}; }
function navigate(page) {
  location.hash = '#' + page;
  window.emit('hashchange', {oldURL: '', newURL: location.hash});
}
function click(target) {
  const event = {target, defaultPrevented: false, preventDefault() {this.defaultPrevented = true;}};
  target.emit('click', event);
  main.emit('click', event);
  document.emit('click', event);
  return event;
}
function button(action, id = '') {
  const element = new Element('button');
  element.tagName = 'BUTTON';
  element.dataset = {action, id, table: 'entities'};
  return element;
}
function editingCase(question) {
  currentCaseForm = {
    id: 'case-form', dataset: {},
    fields: {case_id: 'unfinished-case', question, dataset_id: 'datasetA', as_of: '2026-10-13', investigation: [], date_from: '', date_to: '', domains: 'testing', entity_ids: '', watchlist_snapshot_id: ''},
    querySelectorAll(selector) { return selector === 'input, select, textarea' ? Object.values(this.elements) : []; },
  };
  currentCaseForm.elements = Object.fromEntries(Object.entries(currentCaseForm.fields).map(([key, value]) => [key, {value}]));
  const form = currentCaseForm;
  main.emit('input', {target: {id: 'case-question', name: 'question', value: question, closest: (selector) => selector.includes('case-form') ? form : null}});
}
function editingReview(summary) {
  currentReviewForm = {
    id: 'review-form', dataset: {dirty: 'true'},
    fields: {reviewer: 'Synthetic Reviewer', summary, acknowledge_limitations: 'on'},
    querySelectorAll(selector) { return selector === 'input, select, textarea' ? Object.values(this.elements) : []; },
  };
  currentReviewForm.elements = Object.fromEntries(Object.entries(currentReviewForm.fields).map(([key, value]) => [key, {value}]));
  const form = currentReviewForm;
  main.emit('input', {target: {name: 'summary', value: summary, closest: (selector) => selector.includes('review-form') ? form : null}});
}
async function settle() {
  for (let i = 0; i < 20; i += 1) {
    await new Promise((resolve) => setImmediate(resolve));
    if (!run('model.operation')) return;
  }
  throw new Error('The frontend operation did not settle.');
}
async function scenario() {
__SCENARIO__
}
scenario().catch((error) => { console.error(error); process.exitCode = 1; });
"""


def run_scenario(scenario: str) -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is required for offline frontend state regression tests")
    result = subprocess.run(
        [node, "-e", HARNESS.replace("__SCENARIO__", scenario), str(APP_SCRIPT)],
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_skip_link_preserves_current_route_and_focuses_content() -> None:
    run_scenario(r"""
  navigate('cases');
  const contents = main.innerHTML;
  const event = click(skipLink);
  if (!event.defaultPrevented) navigate('main');
  assert.equal(run('model.page'), 'cases', 'Skip navigation must not change the application route.');
  assert.equal(location.hash, '#cases');
  assert.ok(main.innerHTML === contents, 'Skip navigation must retain the current content.');
  assert.ok(main.focusCount > 0, 'Skip navigation must move keyboard focus to main content.');
""")


def test_incomplete_case_edits_survive_navigation_and_workspace_refresh() -> None:
    run_scenario(r"""
  navigate('cases');
  editingCase('Unfinished question preserved while choosing investigations.');
  navigate('data');
  navigate('cases');
  assert.ok(main.innerHTML.includes('Unfinished question preserved while choosing investigations.'), 'Leaving and returning must retain the case draft.');
  assert.equal(run('model.caseDraft.investigations.length'), 0, 'A partially edited case is a valid draft, even before any investigation is selected.');
  editingCase('Second revision retained through a workspace refresh.');
  fetchImplementation = async (url) => {
    assert.equal(url, '/api/state', 'Refreshing a draft must not save it to the server.');
    return jsonResponse(state);
  };
  click(node('#refresh'));
  await settle();
  assert.equal(run('model.page'), 'cases');
  assert.ok(main.innerHTML.includes('Second revision retained through a workspace refresh.'));
  assert.notEqual(notice.className, 'notice error');
""")


@pytest.mark.parametrize(
    "action", ["verify", "export", "open-run", "evidence", "source-evidence"]
)
def test_delayed_run_response_does_not_overwrite_another_view(action: str) -> None:
    run_scenario(r"""
  navigate('runs');
  let release;
  let requested;
  const pending = new Promise((resolve) => { release = resolve; });
  fetchImplementation = async (url) => {
    if (!requested) { requested = url; return pending; }
    assert.equal(url, '/api/runs/runA');
    return jsonResponse(runA);
  };
  click(button(ACTION, ACTION === 'open-run' ? 'runA' : 'E1'));
  assert.ok(requested, 'The selected action must start a real request.');
  navigate('data');
  const chosenView = main.innerHTML;
  const result = ACTION === 'open-run' ? runA : ACTION === 'export' ? {download_url: '/api/exports/runA-package.zip', name: 'runA-package.zip', sha256: '0'.repeat(64)} : ACTION.includes('evidence') ? {record: {}, metadata: {}, snapshot_id: 'sourceA', table: 'entities', origin: null, source_files: [], synthetic: true} : {ok: true, issues: []};
  release(jsonResponse(result));
  await settle();
  assert.equal(run('model.page'), 'data', 'A completed background response must not take navigation away from the user.');
  assert.ok(main.innerHTML === chosenView, 'An earlier run action must not render into a different current page.');
  assert.equal(node('#evidence-dialog').showModalCount, 0, 'A stale record response must not open a modal over the new page.');
  assert.notEqual(notice.className, 'notice error', 'Navigating during work must not cause a missing-element error.');
""".replace("ACTION", repr(action)))


@pytest.mark.parametrize("kind", ["case", "review"])
def test_completed_save_cannot_discard_a_newer_draft(kind: str) -> None:
    run_scenario(r"""
  run("model.runTab = 'review'");
  navigate(KIND === 'case' ? 'cases' : 'runs');
  const earlier = 'Earlier assessment sent to the local workspace for saving.';
  const later = 'Newer assessment typed after returning while the save is pending.';
  if (KIND === 'case') {
    editingCase(earlier);
    currentCaseForm.fields.investigation = ['data_quality'];
  } else editingReview(earlier);
  const submittedForm = KIND === 'case' ? currentCaseForm : currentReviewForm;
  let release;
  let sent;
  const pending = new Promise((resolve) => { release = resolve; });
  fetchImplementation = async (url, options) => {
    if (options.method === 'POST') {
      assert.equal(url, KIND === 'case' ? '/api/cases' : '/api/runs/runA/review');
      sent = JSON.parse(options.body);
      return pending;
    }
    assert.equal(url, '/api/state');
    return jsonResponse(state);
  };
  main.emit('submit', {target: submittedForm, submitter: {value: 'save'}, preventDefault() {}});
  assert.equal(sent[KIND === 'case' ? 'question' : 'summary'], earlier, 'Capture the payload before disabling submitted controls.');
  assert.ok(Object.values(submittedForm.elements).every((control) => control.disabled), 'The submitting form must be protected while its save is pending.');
  navigate('data');
  navigate(KIND === 'case' ? 'cases' : 'runs');
  if (KIND === 'case') editingCase(later); else editingReview(later);
  release(jsonResponse(KIND === 'case' ? sent : {review_id: 'saved-review'}));
  await settle();
  assert.equal(run(KIND === 'case' ? 'model.caseDraft.question' : 'model.reviewDrafts.runA.summary'), later, 'An earlier save completion must retain edits made to the reopened draft.');
  if (KIND === 'case') assert.equal(run('model.caseDirty'), true);
  const unload = {prevented: false, preventDefault() {this.prevented = true;}};
  window.emit('beforeunload', unload);
  assert.ok(unload.prevented, 'The remaining unsaved draft must retain its close-page warning.');
  assert.notEqual(notice.className, 'notice error');
""".replace("KIND", repr(kind)))


def test_starting_new_case_invalidates_pending_case_load() -> None:
    run_scenario(r"""
  navigate('cases');
  let release;
  const pending = new Promise((resolve) => { release = resolve; });
  fetchImplementation = async (url) => {
    assert.equal(url, '/api/cases/saved-case');
    return pending;
  };
  click(button('load-case', 'saved-case'));
  const newCase = button('');
  newCase.id = 'new-case';
  click(newCase);
  editingCase('A new question authored after abandoning the pending case load.');
  release(jsonResponse({case_id: 'saved-case', question: 'An earlier saved definition.', dataset_id: 'datasetA', as_of: '2026-10-13', investigations: ['data_quality'], scope: {}, parameters: {}}));
  await settle();
  assert.equal(run('model.caseDraft.question'), 'A new question authored after abandoning the pending case load.', 'Starting a new case must invalidate a pending response for an older case.');
  assert.equal(run('model.caseDirty'), true);
  assert.notEqual(notice.className, 'notice error');
""")


@pytest.mark.parametrize("replacement", ["new-case", "load-case"])
def test_canceling_case_replacement_retains_the_unsaved_draft(replacement: str) -> None:
    run_scenario(r"""
  navigate('cases');
  editingCase('Retain this unfinished question when replacement is canceled.');
  let confirmations = 0;
  window.confirm = () => { confirmations += 1; return false; };
  let requests = 0;
  fetchImplementation = async () => { requests += 1; throw new Error('A canceled replacement must not load another case.'); };
  const replacement = button(REPLACEMENT, 'another-case');
  if (REPLACEMENT === 'new-case') replacement.id = 'new-case';
  click(replacement);
  await settle();
  assert.equal(confirmations, 1, 'Replacing an unsaved case must let the analyst retain it.');
  assert.equal(requests, 0);
  assert.equal(run('model.caseDraft.question'), 'Retain this unfinished question when replacement is canceled.');
  assert.equal(run('model.caseDirty'), true);
  assert.notEqual(notice.className, 'notice error');
""".replace("REPLACEMENT", repr(replacement)))


def test_integer_parameter_preserves_valid_number_input_exponents() -> None:
    run_scenario(r"""
  navigate('cases');
  editingCase('Evaluate payment counts with the precise chosen threshold.');
  const form = currentCaseForm;
  form.fields.investigation = ['payment_fragmentation'];
  const threshold = {value: '2e2', dataset: {type: 'integer', investigation: 'payment_fragmentation', parameter: 'minimum_payments'}, disabled: false};
  form.querySelectorAll = (selector) => selector.includes('[data-parameter]') ? [threshold] : Object.values(form.elements);
  let sent;
  fetchImplementation = async (url, options) => {
    if (url === '/api/cases') { sent = JSON.parse(options.body); return jsonResponse(sent); }
    assert.equal(url, '/api/state');
    return jsonResponse(state);
  };
  main.emit('submit', {target: form, submitter: {value: 'save'}, preventDefault() {}});
  await settle();
  assert.equal(sent.parameters.payment_fragmentation.minimum_payments, 200, 'HTML number inputs accept scientific notation; the chosen200 must not become2.');
  assert.notEqual(notice.className, 'notice error');
""")
