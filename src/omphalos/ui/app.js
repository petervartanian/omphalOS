'use strict';

const main = document.querySelector('#main');
const notice = document.querySelector('#notice');
const model = { state: null, page: 'overview', selectedRun: null, run: null, runTab: 'findings', caseDraft: null, reviewDrafts: {}, findingPage: 0, reviewPage: 0, referenceLimits: {}, operation: false };
const PAGE_SIZE = 20;
const titles = { overview: 'Overview', data: 'Data & sources', cases: 'Cases', runs: 'Findings & review' };
const esc = (value) => String(value ?? '').replace(/[&<>"']/g, (char) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[char]));
const human = (value) => String(value ?? '').replaceAll('_', ' ');
const json = (value) => esc(JSON.stringify(value, null, 2));
const array = (value) => Array.isArray(value) ? value : [];
const lines = (value) => String(value || '').split(/\n/).map((item) => item.trim()).filter(Boolean);
const tokens = (value) => String(value || '').split(/[,\n]/).map((item) => item.trim()).filter(Boolean);
const dateToday = () => { const date = new Date(); return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`; };
const badge = (text, color = '') => `<span class="badge ${esc(color)}">${esc(text)}</span>`;
const empty = (title, description) => `<div class="empty"><h3>${esc(title)}</h3><p>${esc(description)}</p></div>`;
const list = (items) => `<ul class="compact-list">${array(items).map((item) => `<li>${esc(item)}</li>`).join('')}</ul>`;
const sourceLink = (url, title = 'Official guidance') => /^https:\/\//i.test(String(url)) ? `<a href="${esc(url)}" target="_blank" rel="noopener noreferrer">${esc(title)}</a>` : esc(url);
const countsText = (counts) => Object.entries(counts || {}).map(([key, value]) => `${value} ${human(key)}`).join(', ');

function announce(message, kind = 'success') {
  notice.textContent = message;
  notice.className = `notice ${kind}`;
  notice.hidden = false;
  notice.setAttribute('role', kind === 'error' ? 'alert' : 'status');
}

async function api(path, body) {
  const response = await fetch(`/api/${path}`, {
    method: body === undefined ? 'GET' : 'POST',
    headers: body === undefined ? {} : { 'Content-Type': 'application/json', 'X-Omphalos-Token': model.state?.token || '' },
    body: body === undefined ? undefined : JSON.stringify(body),
    credentials: 'same-origin',
    cache: 'no-store',
  });
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || `Request failed (${response.status}).`);
  return result;
}

async function task(message, fn) {
  if (model.operation) return;
  model.operation = true;
  document.body.setAttribute('aria-busy', 'true');
  announce(message, 'busy');
  try { await fn(); } catch (error) { announce(error.message, 'error'); }
  finally { model.operation = false; document.body.removeAttribute('aria-busy'); }
}

async function refresh(renderPage = true) {
  model.state = await api('state');
  if (renderPage) render();
}

function heading(eyebrow, title, description, actions = '') {
  return `<div class="page-heading"><div><div class="eyebrow">${esc(eyebrow)}</div><h1>${esc(title)}</h1><p>${esc(description)}</p></div>${actions ? `<div class="actions">${actions}</div>` : ''}</div>`;
}

function render() {
  if (!model.state) return;
  document.querySelectorAll('[data-nav]').forEach((link) => {
    const active = link.dataset.nav === model.page;
    link.classList.toggle('active', active);
    if (active) link.setAttribute('aria-current', 'page'); else link.removeAttribute('aria-current');
  });
  document.querySelector('#breadcrumb').textContent = `Workspace / ${titles[model.page]}`;
  ({ overview: renderOverview, data: renderData, cases: renderCases, runs: renderRuns })[model.page]();
}

function runTable(runs) {
  return array(runs).length ? `<div class="table-wrap"><table><thead><tr><th>Case / run</th><th>Observations</th><th>Record</th><th></th></tr></thead><tbody>${runs.map((run) => `<tr><td><strong>${esc(run.case_id || run.run_id)}</strong><small class="mono">${esc(run.run_id)}</small></td><td>${esc(run.findings_count ?? '—')}</td><td>${badge(human(run.status || 'run saved'), 'blue')}<small>${esc(run.created_at || '')}</small></td><td><button class="text-button" data-action="open-run" data-id="${esc(run.run_id)}">Inspect run →</button></td></tr>`).join('')}</tbody></table></div>` : empty('No runs yet', 'Import data, define a question, then run selected investigations.');
}

function renderOverview() {
  const s = model.state;
  main.innerHTML = `${heading('EVIDENCE BEFORE JUDGMENT', 'Your investigation workspace', 'Bring transaction records into a bounded case. Examine observations, check their supporting evidence, and record what you conclude.')}<div class="grid four metrics">${[['Datasets', s.datasets.length], ['Source snapshots', s.sources.length], ['Cases', s.cases.length], ['Analysis runs', s.runs.length]].map(([label, value]) => `<div class="metric"><div class="number">${value}</div><div class="label">${label}</div></div>`).join('')}</div><section class="panel"><div class="panel-heading"><h2>A reviewable chain of evidence</h2>${badge('Local and reproducible', 'green')}</div><div class="grid three"><div class="workflow-step"><div class="step-number">1</div><h3>Bring the records</h3><p>Import entities, shipments, and payments. Original files and record provenance are retained.</p><a href="#data">Add data & sources →</a></div><div class="workflow-step"><div class="step-number">2</div><h3>Ask a specific question</h3><p>Set the date, scope, and investigations. Each run freezes its inputs, parameters, and analysis.</p><a href="#cases">Define a case →</a></div><div class="workflow-step"><div class="step-number">3</div><h3>Investigate and assess</h3><p>Inspect the evidence, address uncertainty, and record a disposition for every observation.</p><a href="#runs">Review findings →</a></div></div><div class="callout">An observation is a reason to examine records. A name match is a candidate for identity review. Neither establishes a violation or determines a license requirement.</div></section><section class="panel"><div class="panel-heading"><h2>Recent analysis</h2><a class="small" href="#runs">All runs</a></div>${runTable(s.runs.slice(0, 6))}${s.runs.length > 6 ? `<p class="small muted">Showing 6 of ${s.runs.length} runs.</p>` : ''}</section>`;
}

function schemaHelp() {
  const schema = model.state.data_schema || {};
  return `<details><summary>File names, fields, and import rules</summary><p class="small muted">Upload named table files such as <code>entities.csv</code> and <code>payments.json</code>, or one <code>dataset.json</code> containing <code>{"tables": {"entities": […]}}</code>. JSON table files contain arrays of records. UTF-8 CSV files require a header.</p>${Object.entries(schema.tables || {}).map(([table, spec]) => `<details><summary>${esc(table)} <span class="muted small">Required: ${esc((spec.required || []).join(', '))}</span></summary><div class="schema-fields">${Object.entries(spec.properties || {}).map(([field, property]) => `<code title="${esc(property.description || JSON.stringify(property))}">${esc(field)}${(spec.required || []).includes(field) ? ' *' : ''}</code>`).join('')}</div><details><summary>Full field specification</summary><pre>${json(spec)}</pre></details></details>`).join('')}${list(schema.notes)}<p class="small muted">Duplicate IDs, broken references, unexpected fields, and invalid values reject the import. Nothing is silently discarded. The browser accepts at most 48 MiB of files per import.</p></details>`;
}

function renderData() {
  const s = model.state;
  const sourceOptions = s.source_catalog.map((item) => `<option value="${esc(item.id || item.source_id)}">${esc(item.title || item.name || item.id || item.source_id)}</option>`).join('');
  main.innerHTML = `${heading('INPUTS & PROVENANCE', 'Data & sources', 'Import records you are authorized to use. Source snapshots are dated evidence, and remain separate from your transaction data.')}<div class="grid two"><section class="panel"><h2>Import a dataset</h2><p class="section-subtitle">Original files are preserved alongside validated records.</p><form id="dataset-form"><div class="form-row"><div class="field"><label for="dataset-id">Dataset ID <span class="muted">(optional)</span></label><input id="dataset-id" name="dataset_id" pattern="[A-Za-z0-9][A-Za-z0-9_-]{0,79}" maxlength="80" placeholder="trade_review_2026"><small>Letters, numbers, underscores, and hyphens.</small></div><div class="field"><label for="dataset-label">Descriptive label</label><input id="dataset-label" name="label" maxlength="1000" placeholder="September transaction records"></div></div><div class="field"><label for="dataset-files">CSV or JSON files</label><input type="file" id="dataset-files" name="files" accept=".csv,.json" multiple required><small>Include entities. Add shipments, payments, ownership, or diligence as available.</small></div><button type="submit">Validate & import</button></form>${schemaHelp()}</section><div><section class="panel synthetic-box"><div class="eyebrow">EXPLICITLY SYNTHETIC</div><h2>Explore the workflow</h2><p class="small muted">Create a separate demonstration dataset with planted patterns, ambiguous records, and benign counterexamples. It contains no real counterparties.</p><button id="create-demo" class="secondary" type="button">Create synthetic dataset</button><p class="small muted stack-gap">Synthetic status follows the dataset into every run and evidence package.</p></section><section class="panel"><h3>What this workspace can establish</h3><p class="small muted">It can show what the imported records say, which comparisons ran, and how a reviewer assessed them. It cannot establish source completeness, verify a customer’s identity by name alone, or make a legal determination.</p><p class="small muted">HS codes and ECCNs remain distinct. Currencies are not converted. Missing fields remain visible.</p></section></div></div><section class="panel"><div class="panel-heading"><h2>Datasets</h2>${badge(`${s.datasets.length} imported`)}</div>${s.datasets.length ? `<div class="table-wrap"><table><thead><tr><th>Dataset</th><th>Records</th><th>Provenance</th></tr></thead><tbody>${s.datasets.map((data) => `<tr><td><strong>${esc(data.label || data.dataset_id)}</strong><small class="mono">${esc(data.dataset_id)}</small></td><td>${esc(countsText(data.counts))}${data.warnings?.length ? `<details><summary>Import notes (${data.warnings.length})</summary>${list(data.warnings)}</details>` : ''}</td><td>${badge(data.synthetic ? 'SYNTHETIC' : 'Analyst supplied', data.synthetic ? 'amber' : 'blue')}</td></tr>`).join('')}</tbody></table></div>` : empty('No datasets imported', 'Use the import form or create an explicitly synthetic dataset above.')}</section><section class="panel"><h2>Official screening snapshots</h2><p class="section-subtitle">Fetching downloads a public list from an allowlisted official source. No case or transaction data is sent. A snapshot records the retrieval date; it is not a historical list valid for every earlier date.</p><form id="source-form"><div class="form-row"><div class="field"><label for="source-id">Official source</label><select id="source-id" name="source_id">${sourceOptions}</select></div><div class="field"><label for="snapshot-id">Snapshot ID <span class="muted">(optional)</span></label><input id="snapshot-id" name="snapshot_id" pattern="[A-Za-z0-9][A-Za-z0-9_-]{0,79}" maxlength="80" placeholder="Generated when blank"></div></div><div id="source-description"></div><button type="submit" name="method" value="fetch">Fetch official snapshot</button><div class="source-option"><h3>Or import a downloaded official file</h3><div class="field"><label for="source-file">Snapshot file</label><input type="file" id="source-file" name="file" accept=".json,.xml,.csv"><small>Use the format supported by the selected source, shown in its details.</small></div><button class="secondary" type="submit" name="method" value="import">Validate & import snapshot</button></div></form><details><summary>Source formats and limitations</summary>${s.source_catalog.map((source) => `<h3>${esc(source.title || source.name || source.id)}</h3><pre>${json(source)}</pre>`).join('')}</details><hr><h3>Saved snapshots</h3>${s.sources.length ? `<div class="table-wrap"><table><thead><tr><th>Snapshot</th><th>Source / coverage</th><th>Timing</th></tr></thead><tbody>${s.sources.map((source) => `<tr><td class="mono">${esc(source.snapshot_id || source.source_snapshot_id || source.id)}</td><td>${esc(source.source_id || source.title || '')}<small>${esc(source.records_count ?? source.record_count ?? source.count ?? '')} records</small></td><td>${esc(source.fetched_at || source.imported_at || source.retrieved_at || '')}<small>${source.source_updated_at ? `Publisher update: ${esc(source.source_updated_at)}` : 'Publisher update: unknown unless recorded by source'}</small></td></tr>`).join('')}</tbody></table></div>` : empty('No screening snapshots', 'Transaction investigations work without a list. Screening requires a selected snapshot.')}</section>`;
  renderSourceDescription();
}

function renderSourceDescription() {
  const sourceId = document.querySelector('#source-id')?.value;
  const source = model.state.source_catalog.find((item) => (item.id || item.source_id) === sourceId);
  const container = document.querySelector('#source-description');
  if (container && source) container.innerHTML = `<p class="small muted">${esc(source.description || '')}</p>${source.url ? `<p class="small">${sourceLink(source.url, 'Official download endpoint')}</p>` : ''}`;
}

function investigationCard(item, draft) {
  const selected = draft.investigations.includes(item.id);
  const params = Object.entries(item.parameters || {});
  return `<div class="investigation-card"><label class="inline-check"><input type="checkbox" name="investigation" value="${esc(item.id)}" ${selected ? 'checked' : ''}><span><strong>${esc(item.title)}</strong><span class="description">${esc(item.description)}</span></span></label><div class="small muted">Requires ${esc(array(item.required_tables).join(', ') || 'record prerequisites declared by the investigation')}</div>${params.length ? `<div class="parameters" data-parameters="${esc(item.id)}" ${selected ? '' : 'hidden'}><div class="parameter-grid">${params.map(([name, spec]) => {
    const value = draft.parameters?.[item.id]?.[name] ?? spec.default ?? '';
    return `<div class="field"><label for="param-${esc(item.id)}-${esc(name)}">${esc(human(name))}${spec.required ? ' *' : ''}</label><input id="param-${esc(item.id)}-${esc(name)}" data-investigation="${esc(item.id)}" data-parameter="${esc(name)}" data-type="${esc(spec.type)}" data-required="${spec.required ? 'true' : 'false'}" type="${['integer', 'number'].includes(spec.type) ? 'number' : 'text'}" ${spec.minimum !== undefined ? `min="${esc(spec.minimum)}"` : ''} ${spec.maximum !== undefined ? `max="${esc(spec.maximum)}"` : ''} ${spec.type === 'integer' ? 'step="1"' : spec.type === 'number' ? 'step="any"' : ''} value="${esc(value)}" ${selected && spec.required ? 'required' : ''} ${selected ? '' : 'disabled'}><small>${esc(spec.description || '')}</small></div>`;
  }).join('')}</div></div>` : ''}<details><summary>Limitations & basis</summary>${list(item.limitations)}${array(item.source_urls).map((url) => `<p class="small">${sourceLink(url)}</p>`).join('')}<p class="small muted">Investigation ID: <code>${esc(item.id)}</code></p></details></div>`;
}

function renderCases() {
  const s = model.state;
  const draft = model.caseDraft || { case_id: '', question: '', dataset_id: s.datasets[0]?.dataset_id || '', as_of: dateToday(), investigations: ['data_quality', 'payment_fragmentation', 'shared_address'].filter((id) => s.catalog.some((item) => item.id === id)), parameters: {}, scope: { domains: [], entity_ids: [] }, watchlist_snapshot_id: null };
  main.innerHTML = `${heading('DEFINE THE QUESTION', 'Cases', 'Choose the dataset, time boundary, and analyses that can answer a specific investigative question. Every run preserves its own case snapshot.')}<section class="panel"><div class="panel-heading"><h2>${model.caseDraft ? 'Case definition' : 'Create a case'}</h2>${badge('Versioned by run', 'blue')}</div>${!s.datasets.length ? '<div class="callout warning">Import a dataset before running a case. <a href="#data">Go to data & sources</a>.</div>' : ''}<form id="case-form"><div class="form-row three"><div class="field"><label for="case-id">Case ID</label><input id="case-id" name="case_id" value="${esc(draft.case_id)}" pattern="[A-Za-z0-9][A-Za-z0-9_-]{0,79}" maxlength="80" placeholder="september_counterparty_review" required></div><div class="field"><label for="case-dataset">Dataset</label><select id="case-dataset" name="dataset_id" required><option value="">Choose a dataset</option>${s.datasets.map((data) => `<option value="${esc(data.dataset_id)}" ${data.dataset_id === draft.dataset_id ? 'selected' : ''}>${esc(data.label || data.dataset_id)}${data.synthetic ? ' [SYNTHETIC]' : ''}</option>`).join('')}</select></div><div class="field"><label for="case-asof">Analysis as of</label><input type="date" id="case-asof" name="as_of" value="${esc(draft.as_of)}" required><small>Records after this date are excluded. Source historical validity is assessed separately.</small></div></div><div class="field"><label for="case-question">Investigative question</label><textarea id="case-question" name="question" required minlength="12" maxlength="5000" placeholder="Which counterparties or transactions need follow-up, and what records would resolve the observed patterns?">${esc(draft.question)}</textarea></div><div class="field"><label for="case-snapshot">Screening snapshot <span class="muted">(optional)</span></label><select id="case-snapshot" name="watchlist_snapshot_id"><option value="">No snapshot selected</option>${s.sources.map((source) => { const id = source.snapshot_id || source.source_snapshot_id || source.id; return `<option value="${esc(id)}" ${id === draft.watchlist_snapshot_id ? 'selected' : ''}>${esc(id)} — ${esc(source.source_id || '')}</option>`; }).join('')}</select><small>Screening is not evaluable without a snapshot. List categories and dates constrain what a candidate means.</small></div><details ${model.caseDraft ? 'open' : ''}><summary>Bound the record scope</summary><div class="form-row"><div class="field"><label for="scope-from">From date <span class="muted">(optional)</span></label><input type="date" id="scope-from" name="date_from" value="${esc(draft.scope?.date_from || '')}"></div><div class="field"><label for="scope-to">Through date <span class="muted">(optional)</span></label><input type="date" id="scope-to" name="date_to" value="${esc(draft.scope?.date_to || '')}"></div></div><div class="form-row"><div class="field"><label for="scope-domains">Domains <span class="muted">(optional)</span></label><input id="scope-domains" name="domains" value="${esc(array(draft.scope?.domains).join(', '))}" placeholder="machine_tools, laboratory_equipment"><small>Exact dataset values, separated by commas.</small></div><div class="field"><label for="scope-entities">Entity IDs <span class="muted">(optional)</span></label><input id="scope-entities" name="entity_ids" value="${esc(array(draft.scope?.entity_ids).join(', '))}" placeholder="E1, E3"><small>Explicit IDs, never an automatic fuzzy merge.</small></div></div></details><hr><h3>Selected investigations</h3><p class="section-subtitle">Each investigation reports whether its required evidence was available. Thresholds are review parameters, not legal limits.</p><div class="catalog-grid">${s.catalog.map((item) => investigationCard(item, draft)).join('')}</div><div class="form-actions"><button type="submit" name="action" value="run" ${!s.datasets.length ? 'disabled' : ''}>Save & run investigation</button><button class="secondary" type="submit" name="action" value="save" ${!s.datasets.length ? 'disabled' : ''}>Save case</button><button class="text-button" id="new-case" type="button">Start a new case</button></div></form></section><section class="panel"><h2>Saved cases</h2>${s.cases.length ? `<div class="table-wrap"><table><thead><tr><th>Case</th><th>Question</th><th>As of</th><th></th></tr></thead><tbody>${s.cases.map((item) => `<tr><td><strong>${esc(item.case_id)}</strong><small>${esc(item.dataset_id)}</small></td><td>${esc(item.question || '')}</td><td class="nowrap">${esc(item.as_of || '')}</td><td><button class="text-button" data-action="load-case" data-id="${esc(item.case_id)}">Open definition</button></td></tr>`).join('')}</tbody></table></div>` : empty('No saved cases', 'Your investigative question and selections will appear here.')}</section>`;
}

function readCase(form) {
  const values = new FormData(form);
  const investigations = values.getAll('investigation');
  if (!investigations.length) throw new Error('Select at least one investigation.');
  const parameters = {};
  form.querySelectorAll('[data-parameter]:not(:disabled)').forEach((input) => {
    if (input.value === '') return;
    parameters[input.dataset.investigation] ||= {};
    parameters[input.dataset.investigation][input.dataset.parameter] = input.dataset.type === 'integer' ? Number.parseInt(input.value, 10) : input.dataset.type === 'number' ? input.value : input.value.trim();
  });
  return { schema_version: '2.0', case_id: values.get('case_id').trim(), question: values.get('question').trim(), dataset_id: values.get('dataset_id'), as_of: values.get('as_of'), investigations, scope: { date_from: values.get('date_from') || null, date_to: values.get('date_to') || null, domains: tokens(values.get('domains')), entity_ids: tokens(values.get('entity_ids')) }, parameters, watchlist_snapshot_id: values.get('watchlist_snapshot_id') || null };
}

function renderRuns() {
  const runs = model.state.runs;
  main.innerHTML = `${heading('OBSERVATIONS & ASSESSMENT', 'Findings & review', 'Inspect the archived evidence. Record what remains unresolved, what else could explain it, and what would change your assessment.')}<div class="run-layout"><aside class="panel run-list" aria-label="Saved runs">${runs.length ? runs.map((run) => `<button class="run-item ${run.run_id === model.selectedRun ? 'selected' : ''}" data-action="open-run" data-id="${esc(run.run_id)}"><strong>${esc(run.case_id || run.run_id)}</strong><small>${esc(run.run_id)}</small><small>${esc(run.findings_count ?? '—')} observations</small></button>`).join('') : '<p class="small muted">No runs yet.</p>'}</aside><div id="run-detail">${model.run ? renderRunDetail() : empty('Select an analysis run', 'A run contains the exact case, evidence, algorithms, coverage, and findings used for review.')}</div></div>`;
}

function renderRunDetail() {
  const run = model.run;
  const findings = array(run.analysis?.findings);
  const caseData = run.case || {};
  const verified = run.verification?.ok === true;
  const synthetic = run.dataset_metadata?.synthetic === true;
  const latest = run.latest_review;
  const blocked = !verified || !latest || run.review_validation?.ok === false;
  return `<section class="panel run-header"><div class="eyebrow">${esc(caseData.case_id)}</div><div class="question">${esc(caseData.question)}</div><div class="run-meta">${badge(verified ? 'Integrity verified' : 'Integrity failed', verified ? 'green' : 'red')}${synthetic ? badge('SYNTHETIC DATA', 'amber') : badge('Analyst-supplied records', 'blue')}<span>As of ${esc(caseData.as_of)}</span><span>${findings.length} observations</span><span>${latest ? 'Review recorded' : 'Review required'}</span></div><div class="small muted mono word-break">${esc(model.selectedRun)}</div><div class="run-actions actions"><button class="secondary" data-action="verify">Verify files</button><button class="secondary" data-action="replay">Replay analysis</button><button data-action="export" ${blocked ? 'disabled' : ''}>Create evidence package</button></div><p class="small muted stack-gap">${!verified ? 'Integrity verification must pass before export.' : !latest ? 'Export is locked until a named reviewer completes an assessment of every finding and acknowledges coverage limitations.' : 'Export includes the reviewed findings, original evidence, source snapshot, and verification records. Recorded reviewer identity is self-asserted.'}</p><div id="run-result" class="result-box"></div></section>${run.review_validation?.issues?.length ? `<div class="callout error"><strong>Stored review validation issues</strong>${list(run.review_validation.issues)}</div>` : ''}${!verified ? `<div class="callout error"><strong>Verification failed.</strong>${list(run.verification?.issues)}Treat displayed findings as unverified until this is resolved.</div>` : ''}<div class="tabs" role="tablist" aria-label="Run detail">${[['findings', `Observations (${findings.length})`], ['coverage', 'Coverage & limits'], ['review', 'Analyst review'], ['context', 'Run context']].map(([id, title]) => `<button role="tab" id="tab-${id}" aria-controls="run-tab-content" aria-selected="${model.runTab === id}" tabindex="${model.runTab === id ? '0' : '-1'}" class="${model.runTab === id ? 'active' : ''}" data-action="run-tab" data-tab="${id}">${title}</button>`).join('')}</div><section id="run-tab-content" role="tabpanel" aria-labelledby="tab-${esc(model.runTab)}">${({ findings: renderFindings, coverage: renderCoverage, review: renderReview, context: renderContext })[model.runTab]()}</section>`;
}

function pageControls(kind, page, total) {
  if (total <= PAGE_SIZE) return '';
  const last = Math.ceil(total / PAGE_SIZE) - 1;
  return `<nav class="pagination" aria-label="${kind === 'review' ? 'Review' : 'Observation'} pages"><span class="small muted">Showing ${page * PAGE_SIZE + 1}–${Math.min((page + 1) * PAGE_SIZE, total)} of ${total} observations</span><div class="actions"><button type="button" class="secondary" data-action="change-page" data-kind="${kind}" data-page="${page - 1}" ${page === 0 ? 'disabled' : ''}>Previous</button><span class="small">Page ${page + 1} of ${last + 1}</span><button type="button" class="secondary" data-action="change-page" data-kind="${kind}" data-page="${page + 1}" ${page === last ? 'disabled' : ''}>Next</button></div></nav>`;
}

function recordButtons(finding) {
  const refs = array(finding.record_refs);
  const limit = model.referenceLimits[finding.finding_id] || 40;
  return `<div class="record-chips">${refs.slice(0, limit).map((ref) => `<button class="record-chip" data-action="evidence" data-table="${esc(ref.table)}" data-id="${esc(ref.record_id)}" aria-label="Inspect ${esc(ref.table)} record ${esc(ref.record_id)}">${esc(ref.table)} / ${esc(ref.record_id)} ↗</button>`).join('')}</div>${refs.length > limit ? `<p class="small muted">Showing ${limit} of ${refs.length} cited records. <button type="button" class="text-button" data-action="more-records" data-id="${esc(finding.finding_id)}">Show next ${Math.min(40, refs.length - limit)} records</button></p>` : ''}`;
}

function reviewRowComplete(row) {
  return ['follow_up', 'explained', 'escalate'].includes(row?.disposition) && String(row.rationale || '').trim().length >= 12 && ['unknowns', 'alternatives', 'falsifiers'].every((key) => array(row[key]).length && row[key].every((value) => String(value).trim().length >= 12));
}

function renderFindings() {
  const findings = array(model.run.analysis?.findings);
  const reviewed = model.run.latest_review?.review?.findings || [];
  if (!findings.length) return `<section class="panel">${empty('No observations generated', 'This is not a clearance. Check coverage to see which investigations ran and what evidence was unavailable.')}<div class="actions stack-gap"><button class="secondary" data-action="run-tab" data-tab="coverage">Examine coverage</button><button data-action="run-tab" data-tab="review">Record assessment</button></div></section>`;
  model.findingPage = Math.min(model.findingPage, Math.ceil(findings.length / PAGE_SIZE) - 1);
  const start = model.findingPage * PAGE_SIZE;
  return pageControls('findings', model.findingPage, findings.length) + findings.slice(start, start + PAGE_SIZE).map((finding, localIndex) => {
    const index = start + localIndex;
    const assessment = reviewed.find((row) => row.finding_id === finding.finding_id);
    const refs = array(finding.record_refs);
    return `<article class="panel finding"><div class="finding-top"><div><div class="small muted">OBSERVATION ${String(index + 1).padStart(2, '0')} / ${esc(human(finding.investigation_id))}</div><h3>${esc(finding.title)}</h3></div>${assessment ? badge(human(assessment.disposition), 'blue') : badge('Unreviewed', 'amber')}</div><p class="observation">${esc(finding.observation)}</p><div class="evidence-label">SUPPORTING RECORDS (${refs.length})</div>${recordButtons(finding)}${Object.keys(finding.metrics || {}).length ? `<details><summary>Computed metrics</summary><dl class="kv">${Object.entries(finding.metrics).map(([key, value]) => `<dt>${esc(human(key))}</dt><dd>${esc(typeof value === 'object' ? JSON.stringify(value) : value)}</dd>`).join('')}</dl></details>` : ''}${finding.source_refs?.length ? `<div class="evidence-label">OFFICIAL SOURCE RECORDS</div><div class="record-chips">${finding.source_refs.map((ref) => `<button class="record-chip" data-action="source-evidence" data-id="${esc(ref.record_id)}">${esc(ref.source_id)} / ${esc(ref.record_id)} ↗</button>`).join('')}</div>` : ''}<div class="uncertainty-grid"><div><h4>WHAT IS UNKNOWN</h4>${list(finding.unknowns)}</div><div><h4>OTHER EXPLANATIONS</h4>${list(finding.alternatives)}</div><div><h4>WHAT WOULD CHANGE THIS</h4>${list(finding.falsifiers)}</div></div><div class="finding-meta"><span>Entities: ${esc(array(finding.entity_ids).join(', ') || 'See cited records')}</span><span class="mono">${esc(finding.finding_id)}</span></div></article>`;
  }).join('') + pageControls('findings', model.findingPage, findings.length);
}

function renderCoverage() {
  const analysis = model.run.analysis || {};
  return `<section class="panel"><h2>Investigation coverage</h2><p class="section-subtitle">Executed with zero observations is different from not evaluable. Inspect the specific limits before drawing any conclusion.</p><div class="table-wrap"><table><thead><tr><th>Investigation</th><th>Coverage</th><th>Records evaluated</th><th>Observations</th></tr></thead><tbody>${array(analysis.coverage).map((item) => `<tr><td>${esc(human(item.investigation_id))}<div class="small muted coverage-reason">${esc(item.reason || '')}${item.limitations?.length ? list(item.limitations) : ''}</div></td><td>${badge(human(item.status), item.status === 'executed' ? 'green' : 'amber')}</td><td>${esc(item.records_evaluated)}</td><td>${esc(item.findings_count)}</td></tr>`).join('')}</tbody></table></div>${analysis.warnings?.length ? `<div class="callout warning"><strong>Run warnings</strong>${list(analysis.warnings)}</div>` : ''}<details open><summary>Scope and record counts</summary><pre>${json(analysis.scope_counts || {})}</pre></details></section>`;
}

function renderReview() {
  const run = model.run;
  const findings = array(run.analysis?.findings);
  const draft = model.reviewDrafts[model.selectedRun] || run.latest_review?.review || {};
  model.reviewPage = Math.min(model.reviewPage, Math.max(0, Math.ceil(findings.length / PAGE_SIZE) - 1));
  const start = model.reviewPage * PAGE_SIZE;
  const completed = findings.filter((finding) => reviewRowComplete(array(draft.findings).find((item) => item.finding_id === finding.finding_id))).length;
  return `<section class="panel"><div class="panel-heading"><h2>Analyst assessment</h2>${badge(run.latest_review ? 'New revision on save' : 'Review required', 'blue')}</div><p class="section-subtitle">Address every observation. Review revisions are saved separately from the immutable run. An escalation or open follow-up can be documented; it does not need to be falsely resolved to export.</p>${run.latest_review ? `<div class="callout">Saved review: <code>${esc(run.latest_review.review_id)}</code>. Saving creates a new revision; the prior review remains retained.</div>` : ''}<form id="review-form" data-dirty="${model.reviewDrafts[model.selectedRun] ? 'true' : 'false'}"><div class="field"><label for="reviewer">Reviewer name</label><input id="reviewer" name="reviewer" value="${esc(draft.reviewer || '')}" required minlength="2" maxlength="200" placeholder="Name of the analyst making this assessment"><small>Self-asserted identity. A name here is not external identity authentication.</small></div><div class="field"><label for="review-summary">Overall assessment and next steps</label><textarea id="review-summary" name="summary" required minlength="20" placeholder="Summarize what the evidence supports, the important gaps, and the next steps.">${esc(draft.summary || '')}</textarea></div>${pageControls('review', model.reviewPage, findings.length)}${findings.slice(start, start + PAGE_SIZE).map((finding, localIndex) => {
    const index = start + localIndex;
    const row = array(draft.findings).find((item) => item.finding_id === finding.finding_id) || {};
    return `<fieldset class="review-finding" data-finding="${esc(finding.finding_id)}"><legend>Observation ${index + 1}</legend><h3>${esc(finding.title)}</h3><p class="small">${esc(finding.observation)}</p><div class="reference mono">${esc(finding.finding_id)}</div><details><summary>Review the analytical caveats</summary><strong class="small">Unknowns</strong>${list(finding.unknowns)}<strong class="small">Alternatives</strong>${list(finding.alternatives)}<strong class="small">Potential falsifiers</strong>${list(finding.falsifiers)}</details><div class="field"><label for="disposition-${index}">Disposition</label><select id="disposition-${index}" name="disposition" required><option value="">Choose an assessment</option>${[['follow_up', 'Follow up — more evidence needed'], ['explained', 'Explained — supported by the rationale below'], ['escalate', 'Escalate — specialist or legal review needed']].map(([value, title]) => `<option value="${value}" ${row.disposition === value ? 'selected' : ''}>${title}</option>`).join('')}</select></div><div class="field"><label for="rationale-${index}">Evidence-based rationale</label><textarea id="rationale-${index}" name="rationale" required minlength="20" placeholder="Cite the records that support your assessment and explain the reasoning.">${esc(row.rationale || '')}</textarea></div><div class="review-columns">${[['unknowns', 'Unresolved questions', 'What is still unknown, and how will it be resolved?'], ['alternatives', 'Alternative explanations', 'What other explanation did you consider?'], ['falsifiers', 'Evidence that would change the assessment', 'What specific record or result would change your conclusion?']].map(([key, title, placeholder]) => `<div class="field"><label for="${key}-${index}">${title}</label><textarea id="${key}-${index}" name="${key}" required minlength="12" placeholder="${placeholder}">${esc(array(row[key]).join('\n'))}</textarea><small>One specific item per line, at least 12 characters each.</small></div>`).join('')}</div></fieldset>`;
  }).join('')}${pageControls('review', model.reviewPage, findings.length)}${!findings.length ? '<div class="callout warning">This run has no observations. A named assessment of the question, executed coverage, and unavailable evidence is still required.</div>' : ''}<label class="inline-check"><input type="checkbox" name="acknowledge_limitations" required ${draft.acknowledge_limitations ? 'checked' : ''}><span>I reviewed the run’s coverage and limitations, including missing evidence. These observations and list candidates do not establish a legal violation or clearance.</span></label><div class="form-actions"><button type="submit" ${run.verification?.ok ? '' : 'disabled'}>Save complete review</button><span id="review-count" class="review-count" aria-live="polite">${completed} of ${findings.length} observations have all assessment fields filled.</span></div></form></section>`;
}

function readReview(form) {
  const values = new FormData(form);
  const prior = model.reviewDrafts[model.selectedRun] || model.run.latest_review?.review || {};
  const rows = new Map(array(prior.findings).map((row) => [row.finding_id, row]));
  form.querySelectorAll('[data-finding]').forEach((group) => {
    rows.set(group.dataset.finding, { finding_id: group.dataset.finding, disposition: group.querySelector('[name="disposition"]').value, rationale: group.querySelector('[name="rationale"]').value.trim(), unknowns: lines(group.querySelector('[name="unknowns"]').value), alternatives: lines(group.querySelector('[name="alternatives"]').value), falsifiers: lines(group.querySelector('[name="falsifiers"]').value) });
  });
  return { schema_version: '2.0', run_id: model.selectedRun, reviewer: values.get('reviewer').trim(), summary: values.get('summary').trim(), findings: array(model.run.analysis.findings).map((finding) => rows.get(finding.finding_id) || { finding_id: finding.finding_id, disposition: '', rationale: '', unknowns: [], alternatives: [], falsifiers: [] }), acknowledge_limitations: values.has('acknowledge_limitations') };
}

function renderContext() {
  const run = model.run;
  return `<section class="panel"><h2>Frozen case definition</h2><pre>${json(run.case)}</pre><h3>Analysis digest</h3><p class="mono small word-break">${esc(run.manifest?.analysis_digest || run.verification?.analysis_digest || 'See manifest')}</p><p class="small muted">A digest can demonstrate unchanged bytes or results. It does not establish truth, authorship, or legal admissibility.</p><details><summary>Run manifest</summary><pre>${json(run.manifest)}</pre></details><details><summary>Latest verification</summary><pre>${json(run.verification)}</pre></details>${run.latest_review ? `<details><summary>Saved review record</summary><pre>${json(run.latest_review)}</pre></details>` : ''}</section>`;
}

async function openRun(id) {
  const run = await api(`runs/${encodeURIComponent(id)}`);
  if (model.selectedRun !== id) { model.findingPage = 0; model.reviewPage = 0; }
  model.selectedRun = id;
  model.run = run;
  model.page = 'runs';
  if (location.hash !== '#runs') location.hash = 'runs';
  render();
}

function saveReviewDraft() {
  const form = document.querySelector('#review-form');
  if (form && model.selectedRun && (form.dataset.dirty === 'true' || model.reviewDrafts[model.selectedRun])) {
    const draft = readReview(form);
    model.reviewDrafts[model.selectedRun] = draft;
    const counter = document.querySelector('#review-count');
    const message = `${draft.findings.filter(reviewRowComplete).length} of ${draft.findings.length} observations have all assessment fields filled.`;
    if (counter && counter.textContent !== message) counter.textContent = message;
  }
}

async function filesPayload(files) {
  const entries = [...files];
  if (entries.reduce((total, file) => total + file.size, 0) > model.state.limits.upload_bytes) throw new Error('Combined files exceed the 48 MiB browser upload limit.');
  return Promise.all(entries.map(async (file) => {
    const bytes = new Uint8Array(await file.arrayBuffer());
    const chunks = [];
    for (let offset = 0; offset < bytes.length; offset += 32768) chunks.push(String.fromCharCode(...bytes.subarray(offset, offset + 32768)));
    return { name: file.name, content_base64: btoa(chunks.join('')) };
  }));
}

main.addEventListener('submit', (event) => {
  event.preventDefault();
  const form = event.target;
  const submitValue = event.submitter?.value;
  if (form.id === 'dataset-form') task('Validating the uploaded records…', async () => {
    const result = await api('datasets/import', { dataset_id: form.elements.dataset_id.value.trim(), label: form.elements.label.value.trim(), files: await filesPayload(form.elements.files.files) });
    await refresh();
    announce(`Imported ${result.dataset_id}. ${countsText(result.counts)}.${result.warnings?.length ? ` ${result.warnings.join(' ')}` : ''}`);
  });
  if (form.id === 'source-form') task(submitValue === 'import' ? 'Validating the source snapshot…' : 'Downloading the public official source. No case data is being sent…', async () => {
    const body = { source_id: form.elements.source_id.value, snapshot_id: form.elements.snapshot_id.value.trim() };
    if (submitValue === 'import') {
      if (!form.elements.file.files.length) throw new Error('Choose a downloaded snapshot file before importing.');
      body.files = await filesPayload(form.elements.file.files);
    }
    const result = await api(`sources/${submitValue === 'import' ? 'import' : 'fetch'}`, body);
    await refresh();
    announce(`Source snapshot saved: ${result.snapshot_id || result.source_snapshot_id || result.id || body.snapshot_id || body.source_id}.`);
  });
  if (form.id === 'case-form') task(submitValue === 'run' ? 'Saving the case and running the selected investigations…' : 'Saving the case definition…', async () => {
    const caseData = readCase(form);
    await api('cases', caseData);
    model.caseDraft = caseData;
    if (submitValue === 'run') {
      const run = await api(`cases/${encodeURIComponent(caseData.case_id)}/run`, {});
      await refresh(false);
      model.runTab = 'findings';
      await openRun(run.run_id);
      announce(`Run saved with ${run.findings_count} observations. Review coverage before assessing the findings.`);
    } else { await refresh(); announce(`Case ${caseData.case_id} saved.`); }
  });
  if (form.id === 'review-form') task('Validating and saving the complete review…', async () => {
    const review = readReview(form);
    model.reviewDrafts[model.selectedRun] = review;
    const incomplete = review.findings.findIndex((row) => !reviewRowComplete(row));
    if (incomplete !== -1) {
      model.reviewPage = Math.floor(incomplete / PAGE_SIZE);
      renderRuns();
      document.querySelector('#review-form [data-finding] select')?.focus();
      throw new Error(`Observation ${incomplete + 1} needs a disposition and specific rationale, unknowns, alternatives, and falsifiers. Complete every observation before saving.`);
    }
    const result = await api(`runs/${encodeURIComponent(model.selectedRun)}/review`, review);
    delete model.reviewDrafts[model.selectedRun];
    await refresh(false);
    await openRun(model.selectedRun);
    announce(`Review ${result.review_id} saved. The verified run is now eligible for evidence-package export.`);
  });
});

main.addEventListener('change', (event) => {
  const review = event.target.closest('#review-form');
  if (review) { review.dataset.dirty = 'true'; saveReviewDraft(); }
  if (event.target.id === 'source-id') renderSourceDescription();
  if (event.target.name === 'investigation') {
    const panel = [...document.querySelectorAll('[data-parameters]')].find((item) => item.dataset.parameters === event.target.value);
    if (panel) {
      panel.hidden = !event.target.checked;
      panel.querySelectorAll('input').forEach((input) => { input.disabled = !event.target.checked; input.required = event.target.checked && input.dataset.required === 'true'; });
    }
  }
});

main.addEventListener('input', (event) => {
  const form = event.target.closest('#review-form');
  if (form) { form.dataset.dirty = 'true'; saveReviewDraft(); }
});

main.addEventListener('click', (event) => {
  const button = event.target.closest('button');
  if (!button) return;
  const { action, id } = button.dataset;
  if (button.id === 'create-demo') task('Creating an explicitly synthetic dataset…', async () => {
    const result = await api('datasets/demo', {});
    await refresh();
    announce(`Synthetic dataset ${result.dataset_id} created. Choose it in a case to explore the workflow.`);
  });
  if (button.id === 'new-case') { model.caseDraft = null; renderCases(); }
  if (action === 'load-case') task('Loading the saved case definition…', async () => {
    model.caseDraft = await api(`cases/${encodeURIComponent(id)}`);
    renderCases(); window.scrollTo({ top: 0 }); announce('Case loaded. Existing runs retain their original definition.');
  });
  if (action === 'open-run') { saveReviewDraft(); task('Loading the run and verifying its archived files…', async () => { await openRun(id); announce('Run loaded. Integrity and coverage are shown separately from analyst assessment.'); }); }
  if (action === 'run-tab') { saveReviewDraft(); model.runTab = button.dataset.tab; renderRuns(); document.querySelector(`#tab-${model.runTab}`)?.focus(); }
  if (action === 'change-page') {
    saveReviewDraft();
    model[button.dataset.kind === 'review' ? 'reviewPage' : 'findingPage'] = Number(button.dataset.page);
    renderRuns();
    document.querySelector('#run-tab-content').scrollIntoView({ block: 'start' });
    document.querySelector('#run-tab-content button:not(:disabled), #run-tab-content input')?.focus({ preventScroll: true });
  }
  if (action === 'more-records') { model.referenceLimits[id] = (model.referenceLimits[id] || 40) + 40; renderRuns(); }
  if (action === 'verify' || action === 'replay') task(action === 'verify' ? 'Checking the complete archived file inventory…' : 'Recomputing the archived case and comparing the analysis…', async () => {
    const result = await api(`runs/${encodeURIComponent(model.selectedRun)}/${action}`, {});
    model.run = await api(`runs/${encodeURIComponent(model.selectedRun)}`);
    renderRuns();
    document.querySelector('#run-result').innerHTML = `<details open><summary>${action === 'verify' ? 'Verification result' : 'Replay result'}</summary><pre>${json(result)}</pre></details>`;
    announce(`${action === 'verify' ? 'Verification' : 'Replay'} ${result.ok === true ? 'passed' : 'did not pass'}. Inspect the result details.`, result.ok === true ? 'success' : 'error');
  });
  if (action === 'export') task('Verifying the run and review, then creating the evidence package…', async () => {
    const result = await api(`runs/${encodeURIComponent(model.selectedRun)}/export`, {});
    document.querySelector('#run-result').innerHTML = `<a class="download-link" href="${esc(result.download_url)}" download>Download ${esc(result.name || 'evidence package')} ↓</a><p class="small muted word-break stack-gap">SHA-256: <span class="mono">${esc(result.sha256 || '')}</span></p>`;
    announce('Evidence package created. Download it and use the included independent verification instructions.');
  });
  if (action === 'source-evidence') task('Loading the official source record from the verified run snapshot…', async () => {
    const source = await api(`runs/${encodeURIComponent(model.selectedRun)}/source-evidence?id=${encodeURIComponent(id)}`);
    document.querySelector('#dialog-title').textContent = `Official source / ${id}`;
    document.querySelector('#dialog-content').innerHTML = `<div class="callout warning">A source-list row supports identity and restriction review. It is not an automatic determination about the imported entity.</div><h3>Normalized official record</h3><pre>${json(source.record)}</pre><h3>Snapshot provenance</h3><pre>${json(source.metadata)}</pre><p class="small muted">Snapshot: <code>${esc(source.snapshot_id)}</code>. The original source row or XML is retained in this record and the exact raw download is retained in the run.</p>`;
    document.querySelector('#evidence-dialog').showModal(); notice.hidden = true;
  });
  if (action === 'evidence') task('Loading the cited record from the verified run snapshot…', async () => {
    const record = await api(`runs/${encodeURIComponent(model.selectedRun)}/evidence?table=${encodeURIComponent(button.dataset.table)}&id=${encodeURIComponent(id)}`);
    document.querySelector('#dialog-title').textContent = `${human(record.table)} / ${id}`;
    document.querySelector('#dialog-content').innerHTML = `${record.synthetic ? '<div class="callout warning">This record is explicitly synthetic.</div>' : ''}<h3>Archived record</h3><dl class="kv">${Object.entries(record.record).map(([key, value]) => `<dt>${esc(human(key))}</dt><dd>${value === null || value === '' ? '<span class="muted">Not supplied</span>' : esc(typeof value === 'object' ? JSON.stringify(value) : value)}</dd>`).join('')}</dl><h3 class="stack-gap">Original provenance</h3>${record.origin ? `<p class="small">File: <code>${esc(record.origin.source_file)}</code>, source row ${esc(record.origin.source_row)}.</p>` : '<p class="small muted">No per-row provenance was recorded.</p>'}<pre>${json(record.source_files)}</pre><p class="small muted">This is the record frozen in the run, not a new lookup in a changing dataset.</p>`;
    document.querySelector('#evidence-dialog').showModal(); notice.hidden = true;
  });
});

main.addEventListener('keydown', (event) => {
  if (event.target.getAttribute('role') !== 'tab' || !['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
  const tabs = ['findings', 'coverage', 'review', 'context'];
  const index = tabs.indexOf(model.runTab);
  const next = event.key === 'Home' ? 0 : event.key === 'End' ? tabs.length - 1 : (index + (event.key === 'ArrowRight' ? 1 : -1) + tabs.length) % tabs.length;
  event.preventDefault();
  saveReviewDraft();
  model.runTab = tabs[next];
  renderRuns();
  document.querySelector(`#tab-${model.runTab}`)?.focus();
});

document.querySelector('#close-dialog').addEventListener('click', () => document.querySelector('#evidence-dialog').close());
document.querySelector('#refresh').addEventListener('click', () => { saveReviewDraft(); task('Refreshing the local workspace…', async () => { await refresh(false); if (model.selectedRun) model.run = await api(`runs/${encodeURIComponent(model.selectedRun)}`); render(); announce('Workspace refreshed.'); }); });
window.addEventListener('hashchange', () => { saveReviewDraft(); model.page = Object.hasOwn(titles, location.hash.slice(1)) ? location.hash.slice(1) : 'overview'; render(); });
window.addEventListener('beforeunload', (event) => { if (Object.keys(model.reviewDrafts).length) { event.preventDefault(); event.returnValue = ''; } });
model.page = Object.hasOwn(titles, location.hash.slice(1)) ? location.hash.slice(1) : 'overview';
refresh().catch((error) => { main.innerHTML = empty('Unable to load the workspace', error.message); announce(error.message, 'error'); });
