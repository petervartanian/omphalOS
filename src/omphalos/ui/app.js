'use strict';

const main = document.querySelector('#main');
const notice = document.querySelector('#notice');
let cubeMaterial = null;
let dialogRevision = 0;
const model = {
  state: null,
  page: 'investigate',
  flow: null,
  selectedRun: null,
  run: null,
  runTab: 'findings',
  caseDraft: null,
  caseDirty: false,
  navigationVersion: 0,
  routeVersion: 0,
  reviewDrafts: {},
  findingPage: 0,
  reviewPage: 0,
  referenceLimits: {},
  operation: false,
  handoff: null,
  independentReview: null,
  receiptCache: {},
};
const PAGE_SIZE = 20;
const BOX_STEPS = ['I', 'II', 'III', 'IV', 'V', 'VI'];
const titles = {
  investigate: 'Investigate',
  overview: 'Overview',
  data: 'Data & sources',
  cases: 'Cases',
  runs: 'Findings & review',
};
const esc = (value) =>
  String(value ?? '').replace(
    /[&<>"']/g,
    (char) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[char],
  );
const human = (value) => String(value ?? '').replaceAll('_', ' ');
const json = (value) => esc(JSON.stringify(value, null, 2));
const array = (value) => (Array.isArray(value) ? value : []);
const lines = (value) =>
  String(value || '')
    .split(/\n/)
    .map((item) => item.trim())
    .filter(Boolean);
const tokens = (value) =>
  String(value || '')
    .split(/[,\n]/)
    .map((item) => item.trim())
    .filter(Boolean);
const dateToday = () => {
  const date = new Date();
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
};
const badge = (text, color = '') => `<span class="badge ${esc(color)}">${esc(text)}</span>`;
const empty = (title, description, actions = '') =>
  `<div class="empty"><h3>${esc(title)}</h3><p>${esc(description)}</p>${actions ? `<div class="actions">${actions}</div>` : ''}</div>`;
const list = (items) =>
  `<ul class="compact-list">${array(items)
    .map((item) => `<li>${esc(item)}</li>`)
    .join('')}</ul>`;
const sourceLink = (url, title = 'Official guidance') =>
  /^https:\/\//i.test(String(url))
    ? `<a href="${esc(url)}" target="_blank" rel="noopener noreferrer">${esc(title)}</a>`
    : esc(url);
const formatNumber = (value) =>
  typeof value === 'number' ? value.toLocaleString('en-US') : String(value ?? '—');
const countLabel = (count, singular, plural = `${singular}s`) =>
  `${formatNumber(count)} ${count === 1 ? singular : plural}`;
const countsText = (counts) =>
  Object.entries(counts || {})
    .map(([key, value]) => {
      const singular =
        {
          entities: 'entity',
          shipments: 'shipment',
          payments: 'payment',
          ownership: 'ownership relationship',
          diligence: 'diligence record',
        }[key] || human(key);
      return countLabel(
        value,
        singular,
        key === 'entities'
          ? 'entities'
          : key === 'ownership'
            ? 'ownership relationships'
            : key === 'diligence'
              ? 'diligence records'
              : human(key),
      );
    })
    .join(', ');

function displayDate(value) {
  if (!value) return '';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  const dateOnly = /^\d{4}-\d{2}-\d{2}$/.test(String(value));
  const options = { timeZone: 'UTC', year: 'numeric', month: 'short', day: 'numeric' };
  if (!dateOnly) Object.assign(options, { hour: '2-digit', minute: '2-digit', hourCycle: 'h23' });
  return `${new Intl.DateTimeFormat('en-US', options).format(date)}${dateOnly ? '' : ' UTC'}`;
}

function acquisitionNote(metadata) {
  if (metadata.ingestion_method === 'manual_import')
    return 'Manual import. The origin of this file was not independently authenticated.';
  if (metadata.ingestion_method === 'official_https')
    return 'Downloaded from the official source over HTTPS.';
  return 'Acquisition method was not recorded.';
}

function sourceTitle(id) {
  return (
    model.state?.source_catalog?.find((source) => (source.id || source.source_id) === id)?.title ||
    human(id)
  );
}

function investigationTitle(id) {
  return model.state?.catalog?.find((item) => item.id === id)?.title || human(id);
}

function retainedEntityName(id, run = model.run) {
  const name = run?.verification?.ok === true ? run.entity_names?.[id] : null;
  return typeof name === 'string' && name.trim() ? name : String(id || '');
}

function findingObservation(finding, run = model.run) {
  const observation = String(finding.observation || '');
  const ids = array(finding.entity_ids)
    .filter((id) => retainedEntityName(id, run) !== id && observation.includes(id))
    .sort((left, right) => right.length - left.length);
  if (!ids.length) return observation;
  const pattern = ids.map((id) => id.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|');
  return observation.replace(
    new RegExp(`(^|[^\\p{L}\\p{N}_-])(${pattern})(?=$|[^\\p{L}\\p{N}_-])`, 'gu'),
    (_match, prefix, id) => prefix + retainedEntityName(id, run),
  );
}

function screeningSource(run) {
  const snapshotId = run?.case?.watchlist_snapshot_id;
  if (!snapshotId) return null;
  if (run.verification?.ok === true && run.screening_source?.snapshot_id === snapshotId)
    return run.screening_source;
  return (
    array(model.state?.sources).find((item) => item.snapshot_id === snapshotId) || {
      snapshot_id: snapshotId,
    }
  );
}

function reviewRecorded(status) {
  return status === 'reviewed' || status === 'review_recorded';
}

function reviewStatus(status, decision) {
  if (status === 'invalid') return badge('Invalid run', 'red');
  const disposition = caseDecisionStatus(decision);
  return badge(
    reviewRecorded(status)
      ? disposition
        ? `Recorded: ${disposition}`
        : 'Review recorded'
      : 'Needs review',
    reviewRecorded(status) ? '' : 'amber',
  );
}

function announce(message, kind = 'success') {
  notice.textContent = message;
  notice.className = `notice ${kind}`;
  notice.hidden = false;
  notice.setAttribute('role', kind === 'error' ? 'alert' : 'status');
}

function storageExplanation() {
  if (model.state?.storage?.mode === 'browser')
    return 'Files and results stay in this browser. Clearing website data or browser storage eviction can remove them. Download an evidence package to keep a permanent copy.';
  return 'Original files and results stay in this local workspace.';
}

function uploadLimitLabel() {
  return `${Math.floor((model.state?.limits?.upload_bytes || 48 * 1024 * 1024) / (1024 * 1024))} MiB`;
}

function updateStorageLabels() {
  const browser = model.state?.storage?.mode === 'browser';
  const label = document.querySelector('.session-label');
  const note = document.querySelector('#storage-note');
  if (label) label.textContent = browser ? 'Browser workspace' : 'Local session';
  if (note) note.textContent = browser ? 'Browser storage' : 'Stored on this device';
}

async function api(path, body) {
  if (window.omphalosBrowser) return window.omphalosBrowser.request(path, body);
  let response;
  try {
    response = await fetch(`/api/${path}`, {
      method: body === undefined ? 'GET' : 'POST',
      headers:
        body === undefined
          ? {}
          : { 'Content-Type': 'application/json', 'X-Omphalos-Token': model.state?.token || '' },
      body: body === undefined ? undefined : JSON.stringify(body),
      credentials: 'same-origin',
      cache: 'no-store',
    });
  } catch {
    throw new Error('Unable to reach omphalOS. Check your connection and try again.');
  }
  let result;
  try {
    result = await response.json();
  } catch {
    throw new Error(
      `omphalOS returned an unreadable response${response.status ? ` (${response.status})` : ''}. Reload the workspace and try again.`,
    );
  }
  if (!response.ok) {
    const error = new Error(
      result.error || `The operation failed (${response.status}). Try again in a moment.`,
    );
    error.status = response.status;
    throw error;
  }
  return result;
}

async function task(message, fn) {
  if (model.operation) return;
  model.operation = true;
  main.setAttribute('aria-busy', 'true');
  const trigger = document.activeElement;
  if (trigger?.tagName === 'BUTTON') trigger.setAttribute('aria-busy', 'true');
  const controls = [
    ...document.querySelectorAll(
      '[data-flow="approve-sources"], [data-flow="findings-reviewed"], [data-flow="run"], [data-flow="fetch-run"], [data-flow="import"], [data-flow="plan"], [data-flow="fetch"], [data-flow="repreview"], button[type="submit"], button[data-action="verify"], button[data-action="replay"], button[data-action="export"], button[data-action="open-run"], button[data-action="load-case"], [data-flow="handoff-import"], [data-handoff-file], [data-reviewer-file], [data-reviewer-action], #refresh',
    ),
  ];
  const disabled = controls.map((control) => control.disabled);
  controls.forEach((control) => {
    control.disabled = true;
  });
  announce(message, 'busy');
  try {
    await fn();
  } catch (error) {
    announce(error.message, 'error');
  } finally {
    model.operation = false;
    main.removeAttribute('aria-busy');
    if (trigger?.tagName === 'BUTTON') trigger.removeAttribute('aria-busy');
    controls.forEach((control, index) => {
      control.disabled = disabled[index];
    });
  }
}

async function refresh(renderPage = true) {
  model.state = await api('state');
  updateStorageLabels();
  if (renderPage) render();
}

function heading(_context, title, description, actions = '') {
  return `<div class="page-heading"><div><h1>${esc(title)}</h1><p>${esc(description)}</p></div>${actions ? `<div class="actions">${actions}</div>` : ''}</div>`;
}

function render() {
  if (!model.state) return;
  if (model.page !== 'investigate') {
    cubeMaterial?.destroy();
    cubeMaterial = null;
  }
  document.querySelector('body')?.classList.toggle('object-mode', model.page === 'investigate');
  document.querySelectorAll('[data-nav]').forEach((link) => {
    const active = link.dataset.nav === model.page;
    link.classList.toggle('active', active);
    if (active) link.setAttribute('aria-current', 'page');
    else link.removeAttribute('aria-current');
  });
  document.querySelector('#breadcrumb').textContent = `Workspace / ${titles[model.page]}`;
  ({
    investigate: renderGuided,
    overview: renderOverview,
    data: renderData,
    cases: renderCases,
    runs: renderRuns,
  })[model.page]();
}

function runTable(runs) {
  if (!runs.length) {
    return empty(
      'No analysis runs',
      'Create a case to examine imported records.',
      '<a class="button-link secondary" href="#cases">Create case</a>',
    );
  }
  return `
    <div class="table-wrap">
      <table>
        <thead><tr><th>Case</th><th>Observations</th><th>Review status</th><th></th></tr></thead>
        <tbody>
          ${runs
            .map(
              (run) => `
            <tr>
              <td><strong>${esc(run.case_id || run.run_id)}</strong>
                <small>${esc(displayDate(run.created_at))}</small></td>
              <td class="numeric">${esc(formatNumber(run.findings_count))}
                ${run.not_evaluable_count ? `<small>${run.not_evaluable_count} checks need attention</small>` : ''}</td>
              <td>${reviewStatus(run.status, run.case_decision)}</td>
              <td><button class="text-button" data-action="open-run" data-id="${esc(run.run_id)}">
                ${reviewRecorded(run.status) ? 'View run' : 'Review observations'} →
              </button></td>
            </tr>
          `,
            )
            .join('')}
        </tbody>
      </table>
    </div>`;
}

function renderOverview() {
  const state = model.state;
  const metrics = [
    ['Datasets', state.datasets.length],
    ['Source snapshots', state.sources.length],
    ['Cases', state.cases.length],
    ['Runs awaiting review', state.runs.filter((run) => run.status === 'awaiting_review').length],
  ];
  const firstUse = !state.runs.length;
  main.innerHTML = `
    ${heading(
      '',
      'Overview',
      'Cases, evidence, and analyst review in one workspace.',
      `<a class="button-link" href="${state.datasets.length ? '#cases' : '#data'}">${state.datasets.length ? 'Create case' : 'Import records'}</a>`,
    )}
    ${
      state.runs.length
        ? `
      <section class="panel panel-flush">
        <div class="panel-heading"><h2>Recent analysis</h2><a class="small" href="#runs">View all runs</a></div>
        ${runTable(state.runs.slice(0, 6))}
        ${state.runs.length > 6 ? `<div class="panel-body small muted">Showing 6 of ${state.runs.length} runs.</div>` : ''}
      </section>`
        : ''
    }
    <div class="metrics">
      ${metrics.map(([label, value]) => `<div class="metric"><div class="label">${label}</div><div class="number">${formatNumber(value)}</div></div>`).join('')}
    </div>
    ${
      firstUse
        ? `
      <section class="panel">
        <h2>Start an investigation</h2>
        <ol class="workflow-list">
          <li><span class="step-number">01</span><div><h3>Import the evidence</h3><p>Add entity and transaction records.</p></div><a class="button-link secondary" href="#data">Add data</a></li>
          <li><span class="step-number">02</span><div><h3>Define the question</h3><p>Choose the scope, date, and checks relevant to the case.</p></div><a class="button-link secondary" href="#cases">Create case</a></li>
          <li><span class="step-number">03</span><div><h3>Review the observations</h3><p>Examine supporting records and document your assessment.</p></div><a class="button-link secondary" href="#runs">View runs</a></li>
        </ol>
      </section>`
        : `
      <section class="panel panel-flush">
        <div class="panel-heading"><h2>Cases</h2><a class="small" href="#cases">Manage cases</a></div>
        ${caseTable(state.cases.slice(0, 5))}
      </section>`
    }
  `;
}

function schemaHelp() {
  const schema = model.state.data_schema || {};
  return `
    <details>
      <summary>Import format and field reference</summary>
      <p class="small muted">Upload named files such as <code>entities.csv</code> and <code>payments.json</code>,
        or one <code>dataset.json</code> containing <code>{"tables": {"entities": […]}}</code>.
        Table JSON files contain arrays; UTF-8 CSV files require a header.</p>
      ${Object.entries(schema.tables || {})
        .map(
          ([table, spec]) => `
        <details><summary>${esc(table)} <span class="summary-hint">Required: ${esc((spec.required || []).join(', '))}</span></summary>
          <div class="schema-fields">
            ${Object.entries(spec.properties || {})
              .map(
                ([field, property]) => `
              <code title="${esc(property.description || JSON.stringify(property))}">${esc(field)}${(spec.required || []).includes(field) ? ' *' : ''}</code>
            `,
              )
              .join('')}
          </div>
          <details><summary>Full field specification</summary><pre>${json(spec)}</pre></details>
        </details>`,
        )
        .join('')}
      ${list(schema.notes)}
      <p class="small muted">Invalid rows reject the import; none are silently discarded. Upload limit: six files, ${uploadLimitLabel()} combined.</p>
    </details>`;
}

function datasetTable(datasets) {
  if (!datasets.length)
    return empty('No datasets', 'Import entity or transaction records to begin.');
  return `
    <div class="table-wrap"><table>
      <thead><tr><th>Dataset</th><th>Records</th><th>Type</th></tr></thead>
      <tbody>${datasets
        .map(
          (dataset) => `
        <tr>
          <td><strong>${esc(dataset.label || dataset.dataset_id)}</strong><small class="mono">${esc(dataset.dataset_id)}</small></td>
          <td>${esc(countsText(dataset.counts))}
            ${dataset.warnings?.length ? `<details><summary>${dataset.warnings.length} import notes</summary>${list(dataset.warnings)}</details>` : ''}</td>
          <td>${dataset.status === 'invalid' ? badge('Invalid', 'red') : badge(dataset.synthetic ? 'Synthetic' : 'Analyst supplied', dataset.synthetic ? 'amber' : '')}</td>
        </tr>`,
        )
        .join('')}
      </tbody>
    </table></div>`;
}

function datasetImport() {
  return `
    <details id="dataset-import" class="panel" ${model.state.datasets.length ? '' : 'open'}>
      <summary>Import a dataset <span class="summary-hint">CSV or JSON</span></summary>
      <form id="dataset-form">
        <div class="form-row">
          <div class="field"><label for="dataset-label">Dataset label</label><input id="dataset-label" name="label" maxlength="1000" placeholder="September transaction records"></div>
          <div class="field"><label for="dataset-id">Dataset ID <span class="muted">(optional)</span></label><input id="dataset-id" name="dataset_id" pattern="[A-Za-z0-9][A-Za-z0-9_-]{0,79}" maxlength="80" placeholder="Generated if blank"><small>Letters, numbers, underscores, and hyphens.</small></div>
        </div>
        <div class="field"><label for="dataset-files">Files</label><input id="dataset-files" type="file" name="files" accept=".csv,.json" multiple required><small>Include entities. Add shipments, payments, ownership, or diligence as available. Original files are retained.</small></div>
        <button type="submit">Validate & import</button>
      </form>
      ${schemaHelp()}
    </details>`;
}

function sourceTable(sources) {
  if (!sources.length)
    return empty(
      'No source snapshots',
      'Transaction checks work without a list. Identity screening requires a selected official snapshot.',
    );
  return `
    <div class="table-wrap"><table>
      <thead><tr><th>Official source</th><th>Source timestamp</th><th>Saved snapshot</th></tr></thead>
      <tbody>${sources
        .map(
          (source) => `
        <tr>
          <td><strong>${esc(source.title || sourceTitle(source.source_id))}</strong><small>${esc(countLabel(source.record_count, 'record'))}</small><small>${esc(acquisitionNote(source))}</small></td>
          <td>${esc(displayDate(source.source_updated_at) || 'Not supplied')}<small>Saved ${esc(displayDate(source.fetched_at || source.imported_at) || 'date not supplied')}</small></td>
          <td><span class="mono">${esc(source.snapshot_id)}</span>${source.status === 'invalid' ? `<small>${badge('Invalid snapshot', 'red')}</small>` : ''}</td>
        </tr>`,
        )
        .join('')}
      </tbody>
    </table></div>`;
}

function sourceImport() {
  const options = model.state.source_catalog
    .map(
      (source) =>
        `<option value="${esc(source.id || source.source_id)}">${esc(source.title)}</option>`,
    )
    .join('');
  return `
    <details id="source-import" class="panel" ${model.state.sources.length ? '' : 'open'}>
      <summary>Add a source snapshot</summary>
      <div class="source-layout">
        <form id="source-form">
          <div class="field"><label for="source-id">Official source</label><select id="source-id" name="source_id">${options}</select></div>
          <div class="field"><label for="snapshot-id">Snapshot ID <span class="muted">(optional)</span></label><input id="snapshot-id" name="snapshot_id" pattern="[A-Za-z0-9][A-Za-z0-9_-]{0,79}" maxlength="80" placeholder="Generated if blank"></div>
          <div id="source-description"></div>
          <button type="submit" name="method" value="fetch">Fetch official snapshot</button>
          <div class="source-option">
            <h3>Import a downloaded file</h3>
            <div class="field"><label for="source-file">Official snapshot file</label><input type="file" id="source-file" name="file" accept=".json,.xml"><small id="source-file-hint">Use the format required by the selected source.</small></div>
            <button class="secondary" type="submit" name="method" value="import">Import snapshot</button>
          </div>
        </form>
        <div class="source-guidance">
          <h3>Fixed evidence for a case</h3>
          <p>Fetching downloads a public official list. No case or transaction data is sent.</p>
          <p>Each snapshot stays fixed. Source timestamps may describe publication or aggregation, rather than the update of every underlying list. A current snapshot may not establish historical membership.</p>
          <p>A list candidate requires identity and restriction review. It does not determine that a transaction is prohibited.</p>
          <details><summary>Source formats and limitations</summary>
            ${model.state.source_catalog.map((source) => `<h3>${esc(source.title)}</h3><p>${esc(source.description)}</p>${list(source.limitations)}<p>${sourceLink(source.documentation_url || source.url, 'Official documentation')}</p>`).join('')}
          </details>
        </div>
      </div>
    </details>`;
}

function renderData() {
  const state = model.state;
  main.innerHTML = `
    ${heading(
      '',
      'Data & sources',
      'Import transaction records and retain dated screening snapshots.',
      `
      <button data-action="open-disclosure" data-target="dataset-import" type="button">Import records</button>`,
    )}
    <section class="panel panel-flush">
      <div class="panel-heading"><div><h2>Datasets</h2><p>Original files and record provenance are retained.</p></div>${badge(countLabel(state.datasets.length, 'dataset'))}</div>
      ${datasetTable(state.datasets)}
    </section>
    ${datasetImport()}
    <section class="panel panel-flush">
      <div class="panel-heading"><div><h2>Screening snapshots</h2><p>Public lists retained as evidence for a specific case.</p></div><button class="secondary" data-action="open-disclosure" data-target="source-import" type="button">Add snapshot</button></div>
      ${sourceTable(state.sources)}
    </section>
    ${sourceImport()}
  `;
  renderSourceDescription();
}

function renderSourceDescription() {
  const source = model.state.source_catalog.find(
    (item) => (item.id || item.source_id) === document.querySelector('#source-id')?.value,
  );
  if (!source) return;
  document.querySelector('#source-description').innerHTML =
    `<p class="small muted">${esc(source.description)}</p><p class="small">${sourceLink(source.url, 'Official download endpoint')}</p>`;
  const input = document.querySelector('#source-file');
  if (input) input.accept = `.${source.format}`;
  const hint = document.querySelector('#source-file-hint');
  if (hint)
    hint.textContent = `Upload the official ${String(source.format).toUpperCase()} download for this source.`;
}

function parameterInput(investigation, name, spec, value, selected) {
  const number = ['integer', 'number'].includes(spec.type);
  return `
    <div class="field">
      <label for="param-${esc(investigation)}-${esc(name)}">${esc(human(name))}${spec.required ? ' *' : ''}</label>
      <input id="param-${esc(investigation)}-${esc(name)}" data-investigation="${esc(investigation)}"
        data-parameter="${esc(name)}" data-type="${esc(spec.type)}" data-required="${Boolean(spec.required)}"
        type="${number ? 'number' : 'text'}" value="${esc(value)}"
        ${spec.minimum !== undefined ? `min="${esc(spec.minimum)}"` : ''}
        ${spec.maximum !== undefined ? `max="${esc(spec.maximum)}"` : ''}
        ${number ? `step="${spec.type === 'integer' ? '1' : 'any'}"` : ''}
        ${selected && spec.required ? 'required' : ''} ${selected ? '' : 'disabled'}>
      <small>${esc(spec.description || '')}</small>
    </div>`;
}

function investigationCard(item, draft) {
  const selected = draft.investigations.includes(item.id);
  const parameters = Object.entries(item.parameters || {});
  const missingRequired = parameters.some(
    ([name, spec]) => spec.required && !draft.parameters?.[item.id]?.[name],
  );
  return `
    <div class="investigation-card">
      <label class="inline-check"><input type="checkbox" name="investigation" value="${esc(item.id)}" ${selected ? 'checked' : ''}>
        <span><strong>${esc(item.title)}</strong><span class="description">${esc(item.description)}</span></span>
      </label>
      <div class="prerequisites">Requires ${esc(array(item.required_tables).join(', '))}</div>
      <details class="settings" ${selected && missingRequired ? 'open' : ''}>
        <summary>${parameters.length ? 'Settings and limitations' : 'Limitations'}</summary>
        ${
          parameters.length
            ? `
          <div class="parameters" data-parameters="${esc(item.id)}" ${selected ? '' : 'hidden'}>
            <div class="parameter-grid">${parameters.map(([name, spec]) => parameterInput(item.id, name, spec, draft.parameters?.[item.id]?.[name] ?? spec.default ?? '', selected)).join('')}</div>
          </div>`
            : ''
        }
        ${list(item.limitations)}
        ${array(item.source_urls)
          .map((url) => `<p class="small">${sourceLink(url)}</p>`)
          .join('')}
      </details>
    </div>`;
}

function caseTable(cases) {
  if (!cases.length)
    return empty(
      'No saved cases',
      'A case records the question, scope, and selected investigations.',
    );
  return `
    <div class="table-wrap"><table>
      <thead><tr><th>Case</th><th>Question</th><th>As of</th><th></th></tr></thead>
      <tbody>${cases
        .map(
          (item) => `
        <tr><td><strong>${esc(item.case_id)}</strong><small>${esc(item.dataset_id)}</small></td>
          <td>${esc(item.question || '')}</td><td class="nowrap">${esc(item.as_of || '')}</td>
          <td><button class="text-button" data-action="load-case" data-id="${esc(item.case_id)}">Open case →</button></td></tr>`,
        )
        .join('')}
      </tbody>
    </table></div>`;
}

function caseScope(draft) {
  return `
    <details ${draft.scope?.date_from || draft.scope?.date_to || draft.scope?.domains?.length || draft.scope?.entity_ids?.length ? 'open' : ''}>
      <summary>Limit the record scope</summary>
      <div class="form-row">
        <div class="field"><label for="scope-from">From date <span class="muted">(optional)</span></label><input type="date" id="scope-from" name="date_from" value="${esc(draft.scope?.date_from || '')}"></div>
        <div class="field"><label for="scope-to">Through date <span class="muted">(optional)</span></label><input type="date" id="scope-to" name="date_to" value="${esc(draft.scope?.date_to || '')}"></div>
      </div>
      <div class="form-row">
        <div class="field"><label for="scope-domains">Domains <span class="muted">(optional)</span></label><input id="scope-domains" name="domains" value="${esc(array(draft.scope?.domains).join(', '))}" placeholder="machine_tools, laboratory_equipment"><small>Exact dataset values, separated by commas.</small></div>
        <div class="field"><label for="scope-entities">Entity IDs <span class="muted">(optional)</span></label><input id="scope-entities" name="entity_ids" value="${esc(array(draft.scope?.entity_ids).join(', '))}" placeholder="E1, E3"><small>Exact IDs, separated by commas.</small></div>
      </div>
    </details>`;
}

function screeningSnapshotField(draft) {
  return `
    <div class="field" id="screening-snapshot-field" ${draft.investigations.includes('screening_candidates') ? '' : 'hidden'}>
      <label for="case-snapshot">Official screening snapshot</label>
      <select id="case-snapshot" name="watchlist_snapshot_id">
        <option value="">No snapshot selected</option>
        ${model.state.sources.map((source) => `<option value="${esc(source.snapshot_id)}" ${source.snapshot_id === draft.watchlist_snapshot_id ? 'selected' : ''} ${source.status === 'invalid' ? 'disabled' : ''}>${esc(source.title || sourceTitle(source.source_id))} — ${esc(source.snapshot_id)}</option>`).join('')}
      </select>
      <small>Screening needs a selected snapshot. Current lists may not establish historical membership. <a href="#data">Manage snapshots</a>.</small>
    </div>`;
}

function renderCases() {
  const state = model.state;
  const draft = model.caseDraft || {
    case_id: '',
    question: '',
    dataset_id: state.datasets[0]?.dataset_id || '',
    as_of: dateToday(),
    investigations: ['data_quality', 'payment_fragmentation', 'shared_address'].filter((id) =>
      state.catalog.some((item) => item.id === id),
    ),
    parameters: {},
    scope: { domains: [], entity_ids: [] },
    watchlist_snapshot_id: null,
  };
  if (!state.datasets.length) {
    main.innerHTML = `${heading('', 'Cases', 'Define a question and choose the records and checks that can address it.')}
      <section class="panel">${empty('Import records to create a case', 'A case needs entity or transaction records.', '<a class="button-link" href="#data">Add data</a>')}</section>`;
    return;
  }
  main.innerHTML = `
    ${heading('', 'Cases', 'Define the question, time boundary, and investigations. Each run retains its own case definition.', '<button class="secondary" id="new-case" type="button">New case</button>')}
    ${state.cases.length ? `<section class="panel panel-flush"><div class="panel-heading"><h2>Saved cases</h2>${badge(countLabel(state.cases.length, 'case'))}</div>${caseTable(state.cases)}</section>` : ''}
    <details id="case-editor" class="panel" ${model.caseEditorOpen || model.caseDraft || model.caseDirty || !state.cases.length ? 'open' : ''}>
      <summary>${draft.case_id ? `Case: ${esc(draft.case_id)}` : 'New case definition'} ${model.caseDirty ? badge('Unsaved draft', 'amber') : ''}</summary>
      <form id="case-form">
        <div class="form-row three">
          <div class="field"><label for="case-id">Case ID</label><input id="case-id" name="case_id" value="${esc(draft.case_id)}" pattern="[A-Za-z0-9][A-Za-z0-9_-]{0,79}" maxlength="80" placeholder="counterparty_review" required></div>
          <div class="field"><label for="case-dataset">Dataset</label><select id="case-dataset" name="dataset_id" required><option value="">Choose a dataset</option>${state.datasets.map((data) => `<option value="${esc(data.dataset_id)}" ${data.dataset_id === draft.dataset_id ? 'selected' : ''} ${data.status === 'invalid' ? 'disabled' : ''}>${esc(data.label || data.dataset_id)}${data.synthetic ? ' [Synthetic]' : ''}</option>`).join('')}</select></div>
          <div class="field"><label for="case-asof">Analysis as of</label><input type="date" id="case-asof" name="as_of" value="${esc(draft.as_of)}" required><small>Excludes records after this date.</small></div>
        </div>
        <div class="field"><label for="case-question">Investigative question</label><textarea id="case-question" name="question" required minlength="12" maxlength="5000" placeholder="Which transactions need follow-up, and what evidence would resolve the observed patterns?">${esc(draft.question)}</textarea></div>
        ${caseScope(draft)}
        <hr>
        <h3>Investigations</h3>
        <p class="section-subtitle">Select checks relevant to your question. Checks with missing prerequisites or settings are reported as not evaluated. Thresholds are analyst choices, not legal limits.</p>
        <div class="catalog-grid">${state.catalog.map((item) => investigationCard(item, draft)).join('')}</div>
        <div class="stack-gap">${screeningSnapshotField(draft)}</div>
        <div class="form-actions"><button type="submit" name="action" value="run">Save & run investigation</button><button class="secondary" type="submit" name="action" value="save">Save case</button></div>
      </form>
    </details>
`;
}

function readCase(form, validate = true) {
  const values = new FormData(form);
  const investigations = values.getAll('investigation');
  if (validate && !investigations.length) throw new Error('Select at least one investigation.');
  const parameters = {};
  form.querySelectorAll('[data-parameter]:not(:disabled)').forEach((input) => {
    if (input.value === '') return;
    const value = input.dataset.type === 'integer' ? Number(input.value) : input.value.trim();
    if (validate && input.dataset.type === 'integer' && !Number.isSafeInteger(value)) {
      throw new Error(
        `${human(input.dataset.parameter)} must be a whole number within the supported range.`,
      );
    }
    parameters[input.dataset.investigation] ||= {};
    parameters[input.dataset.investigation][input.dataset.parameter] = value;
  });
  return {
    schema_version: '2.0',
    case_id: values.get('case_id').trim(),
    question: values.get('question').trim(),
    dataset_id: values.get('dataset_id'),
    as_of: values.get('as_of'),
    investigations,
    scope: {
      date_from: values.get('date_from') || null,
      date_to: values.get('date_to') || null,
      domains: tokens(values.get('domains')),
      entity_ids: tokens(values.get('entity_ids')),
    },
    parameters,
    watchlist_snapshot_id: values.get('watchlist_snapshot_id') || null,
  };
}

function renderRuns() {
  const runs = model.state.runs;
  const headingHtml = heading(
    '',
    'Findings & review',
    'Inspect the evidence and document what the observations support, what remains unknown, and what comes next.',
  );
  if (!runs.length) {
    main.innerHTML = `${headingHtml}<section class="panel">${empty('No analysis runs', 'Save and run a case to generate observations from your imported records.', '<a class="button-link" href="#cases">Create case</a>')}</section>`;
    return;
  }
  main.innerHTML = `
    ${headingHtml}
    <div class="run-layout">
      <aside class="panel run-list" aria-label="Saved runs">
        <div class="run-list-heading">Analysis runs</div>
        ${runs
          .map(
            (run) => `
          <button type="button" class="run-item ${run.run_id === model.selectedRun ? 'selected' : ''}" data-action="open-run" data-id="${esc(run.run_id)}" ${run.run_id === model.selectedRun ? 'aria-current="true"' : ''}>
            <strong>${esc(savedRunTitle(run))}</strong><small>${esc(displayDate(run.created_at))}</small>
            <small>${esc(formatNumber(run.findings_count))} observations / ${reviewRecorded(run.status) ? 'Review recorded' : 'Needs review'}</small>
          </button>`,
          )
          .join('')}
      </aside>
      <div id="run-detail">${model.run ? renderRunDetail() : `<section class="panel">${empty('Select a run', 'Each run retains its case, evidence, coverage, observations, and review.')}</section>`}</div>
    </div>`;
}

function renderRunDetail() {
  const run = model.run;
  const findings = array(run.analysis?.findings);
  const coverage = array(run.analysis?.coverage);
  const completed = coverage.filter((item) => item.status === 'executed').length;
  const needsData = coverage.filter((item) => item.status === 'not_evaluable').length;
  const verified = run.verification?.ok === true;
  const reviewed = Boolean(run.latest_review) && run.review_validation?.ok !== false;
  const canExport = flowReviewRecorded(run);
  const pendingDecision = reviewed && Boolean(model.reviewDrafts[model.selectedRun]) && !canExport;
  const tabs = [
    ['findings', `Observations (${findings.length})`],
    ['coverage', 'Coverage'],
    ['review', 'Analyst review'],
    ['context', 'Details'],
  ];
  return `
    <section class="panel run-header">
      <div class="run-case-id">${esc(run.case.case_id)}</div>
      <h2 class="question">${esc(run.case.question)}</h2>
      <div class="run-meta">
        ${reviewStatus(reviewed ? 'reviewed' : 'awaiting_review', run.latest_review?.review?.decision)}
        ${run.dataset_metadata?.synthetic ? badge('Synthetic data', 'amber') : ''}
        <span>As of ${esc(run.case.as_of)}</span>
        <span>${verified ? 'Files verified' : badge('File verification failed', 'red')}</span>
      </div>
      <div class="run-summary">
        <span><strong>${findings.length}</strong> observations</span>
        <span><strong>${completed}</strong> checks completed</span>
        <span class="${needsData ? 'attention' : ''}"><strong>${needsData}</strong> checks need attention</span>
      </div>
      <div class="run-actions">
        <div class="actions">
          ${!reviewed ? '<button type="button" data-action="run-tab" data-tab="review">Review observations</button>' : ''}
          <button type="button" class="${reviewed ? '' : 'secondary'}" data-action="export" ${canExport ? '' : 'disabled'}>Create evidence package</button>
        </div>
        <details class="integrity-controls"><summary>Evidence integrity</summary>
          <div class="actions"><button class="secondary" type="button" data-action="verify">Verify files</button><button class="secondary" type="button" data-action="replay">Replay analysis</button></div>
          <p class="small muted">File verification checks retained evidence. Replay checks whether the analysis reproduces. Neither establishes the truth of a conclusion.</p>
        </details>
      </div>
      <p class="export-note">${!verified ? 'Resolve the file verification issues before exporting.' : pendingDecision ? 'Save the edited case decision before creating its package.' : !reviewed ? 'Record a case decision and acknowledge its coverage before exporting.' : 'The package includes the recorded review and retained evidence. Reviewer identity is self-asserted.'}</p>
      <div id="run-result" class="result-box">${canExport && run.latest_export ? packageDownload(run.latest_export) : ''}</div>
    </section>
    ${run.review_validation?.issues?.length ? `<div class="callout error"><strong>Stored review could not be validated</strong>${list(run.review_validation.issues)}</div>` : ''}
    ${!verified ? `<div class="callout error"><strong>File verification failed</strong>${list(run.verification?.issues)}Displayed observations are unverified until this is resolved.</div>` : ''}
    <div class="tabs" role="tablist" aria-label="Run detail">
      ${tabs.map(([id, title]) => `<button type="button" role="tab" id="tab-${id}" aria-controls="run-tab-content" aria-selected="${model.runTab === id}" tabindex="${model.runTab === id ? '0' : '-1'}" class="${model.runTab === id ? 'active' : ''}" data-action="run-tab" data-tab="${id}">${title}</button>`).join('')}
    </div>
    <section id="run-tab-content" role="tabpanel" aria-labelledby="tab-${esc(model.runTab)}">
      ${{ findings: renderFindings, coverage: renderCoverage, review: renderReview, context: renderContext }[model.runTab]()}
    </section>`;
}

function pageControls(kind, page, total) {
  if (total <= PAGE_SIZE) return '';
  const last = Math.ceil(total / PAGE_SIZE) - 1;
  return `
    <nav class="pagination" aria-label="${kind === 'review' ? 'Review' : 'Observation'} pages">
      <span class="small muted">Showing ${page * PAGE_SIZE + 1}–${Math.min((page + 1) * PAGE_SIZE, total)} of ${total} observations</span>
      <div class="actions">
        <button type="button" class="secondary" data-action="change-page" data-kind="${kind}" data-page="${page - 1}" ${page === 0 ? 'disabled' : ''}>Previous</button>
        <span class="small">Page ${page + 1} of ${last + 1}</span>
        <button type="button" class="secondary" data-action="change-page" data-kind="${kind}" data-page="${page + 1}" ${page === last ? 'disabled' : ''}>Next</button>
      </div>
    </nav>`;
}

function recordButtons(finding) {
  const refs = array(finding.record_refs);
  const limit = model.referenceLimits[finding.finding_id] || 40;
  return `
    <div class="record-chips">
      ${refs
        .slice(0, limit)
        .map(
          (ref) =>
            `<button type="button" class="record-chip" data-action="evidence" data-table="${esc(ref.table)}" data-id="${esc(ref.record_id)}" aria-label="Inspect ${esc(ref.table)} record ${esc(ref.record_id)}">${esc(ref.table)} / ${esc(ref.record_id)} ↗</button>`,
        )
        .join('')}
    </div>
    ${refs.length > limit ? `<p class="small muted">Showing ${limit} of ${refs.length} cited records. <button type="button" class="text-button" data-action="more-records" data-id="${esc(finding.finding_id)}">Show next ${Math.min(40, refs.length - limit)} records</button></p>` : ''}`;
}

function sourceButtons(finding) {
  if (!finding.source_refs?.length) return '';
  return `
    <div class="evidence-label">Official source records</div>
    <div class="record-chips">
      ${finding.source_refs.map((ref) => `<button type="button" class="record-chip" data-action="source-evidence" data-id="${esc(ref.record_id)}">${esc(sourceTitle(ref.source_id))} ↗</button>`).join('')}
    </div>`;
}

function keyValues(values) {
  return `<dl class="kv">${Object.entries(values)
    .map(
      ([key, value]) => `
    <dt>${esc(key)}</dt><dd>${value === null || value === undefined || value === '' ? '<span class="muted">Not supplied</span>' : esc(typeof value === 'object' ? JSON.stringify(value) : value)}</dd>`,
    )
    .join('')}</dl>`;
}

function candidateFacts(finding) {
  if (finding.investigation_id !== 'screening_candidates') return '';
  const metrics = finding.metrics || {};
  return `
    <div class="candidate-facts">
      ${keyValues({
        'Entity name compared': metrics.entity_name_compared,
        'Source name compared': metrics.source_name_compared,
        'Underlying list': metrics.list_name,
        'Name similarity': metrics.name_similarity,
        'Country comparison': metrics.country_context,
        'Entity type comparison': metrics.entity_type_context,
        'Identifier comparisons': metrics.identifier_comparisons?.length
          ? metrics.identifier_comparisons
          : 'No comparable identifiers supplied',
        'Source timestamp': displayDate(metrics.source_updated_at),
      })}
      <p class="small muted">Name similarity is omphalOS’s string comparison, not an identity probability or an official OFAC search score. Differences and missing details require follow-up.</p>
    </div>`;
}

function analyticalCaveats(finding) {
  return `
    <div class="uncertainty-grid">
      <div><h4>Unresolved questions</h4>${list(finding.unknowns)}</div>
      <div><h4>Alternative explanations</h4>${list(finding.alternatives)}</div>
      <div><h4>What would change this</h4>${list(finding.falsifiers)}</div>
    </div>`;
}

function findingCard(finding, index) {
  const assessment = model.run.latest_review?.review?.findings?.find(
    (row) => row.finding_id === finding.finding_id,
  );
  return `
    <article class="panel finding">
      <div class="finding-top">
        <div><div class="finding-kicker">Observation ${index + 1} / ${esc(investigationTitle(finding.investigation_id))}</div><h3>${esc(finding.title)}</h3></div>
        ${assessment ? badge(human(assessment.disposition)) : ''}
      </div>
      <p class="observation">${esc(findingObservation(finding))}</p>
      ${candidateFacts(finding)}
      <div class="evidence-label">Supporting records (${array(finding.record_refs).length})</div>
      ${recordButtons(finding)}
      ${sourceButtons(finding)}
      ${Object.keys(finding.metrics || {}).length ? `<details><summary>Computed values</summary>${keyValues(Object.fromEntries(Object.entries(finding.metrics).map(([key, value]) => [human(key), value])))}</details>` : ''}
      ${analyticalCaveats(finding)}
      <div class="finding-meta"><span>Entities: ${esc(
        array(finding.entity_ids)
          .map((id) => retainedEntityName(id))
          .join(', ') || 'See cited records',
      )}</span><span class="mono">${esc(finding.finding_id)}</span></div>
    </article>`;
}

function renderFindings() {
  if (Number.isSafeInteger(flowState().findingIndex))
    return findingEvidenceView(model.run, flowState().findingIndex);
  const findings = array(model.run.analysis?.findings);
  if (!findings.length) {
    return `<section class="panel">${empty('No observations generated', 'This is not a clearance. Examine coverage to see which checks ran and what evidence was unavailable.')}
      <div class="actions"><button class="secondary" type="button" data-action="run-tab" data-tab="coverage">Examine coverage</button><button type="button" data-action="run-tab" data-tab="review">Record assessment</button></div></section>`;
  }
  model.findingPage = Math.min(model.findingPage, Math.ceil(findings.length / PAGE_SIZE) - 1);
  const start = model.findingPage * PAGE_SIZE;
  return (
    pageControls('findings', model.findingPage, findings.length) +
    findings
      .slice(start, start + PAGE_SIZE)
      .map((finding, index) => findingCard(finding, start + index))
      .join('') +
    pageControls('findings', model.findingPage, findings.length)
  );
}

function renderCoverage() {
  const analysis = model.run.analysis || {};
  return `
    <section class="panel panel-flush">
      <div class="panel-heading"><div><h2>Investigation coverage</h2><p>A completed check with no observations differs from a check that could not be evaluated.</p></div></div>
      <div class="table-wrap"><table>
        <thead><tr><th>Investigation and limitations</th><th>Status</th><th>Records</th><th>Observations</th></tr></thead>
        <tbody>${array(analysis.coverage)
          .map(
            (item) => `
          <tr><td>${esc(investigationTitle(item.investigation_id))}<div class="coverage-reason">${esc(item.reason || '')}${item.limitations?.length ? list(item.limitations) : ''}</div></td>
            <td>${badge(item.status === 'executed' ? 'Completed' : 'Not evaluated', item.status === 'executed' ? '' : 'amber')}</td>
            <td class="numeric">${esc(item.records_evaluated)}</td><td class="numeric">${esc(item.findings_count)}</td></tr>`,
          )
          .join('')}
        </tbody>
      </table></div>
      <div class="panel-body">
        ${analysis.warnings?.length ? `<div class="callout warning"><strong>Coverage notes</strong>${list(analysis.warnings)}</div>` : ''}
        <details><summary>Scope and record counts</summary>${keyValues(Object.fromEntries(Object.entries(analysis.scope_counts || {}).map(([key, value]) => [human(key), value])))}</details>
      </div>
    </section>`;
}

function reviewRowComplete(row) {
  return (
    ['follow_up', 'explained', 'escalate'].includes(row?.disposition) &&
    String(row.rationale || '').trim().length >= 12 &&
    ['unknowns', 'alternatives', 'falsifiers'].every(
      (key) =>
        array(row[key]).length && row[key].every((value) => String(value).trim().length >= 12),
    )
  );
}

function reviewFinding(finding, index, row) {
  const uncertaintyFields = [
    ['unknowns', 'Unresolved questions', 'What is still unknown, and how will it be resolved?'],
    ['alternatives', 'Alternative explanations', 'What other explanation did you consider?'],
    [
      'falsifiers',
      'What would change your assessment',
      'What specific evidence would change your conclusion?',
    ],
  ];
  return `
    <fieldset class="review-finding" data-finding="${esc(finding.finding_id)}">
      <legend>Observation ${index + 1}</legend>
      <h3>${esc(finding.title)}</h3>
      <div class="review-evidence">
        <p class="small">${esc(findingObservation(finding))}</p>
        ${recordButtons(finding)}${sourceButtons(finding)}
        <details><summary>Analytical context and caveats</summary>${candidateFacts(finding)}${analyticalCaveats(finding)}</details>
      </div>
      <div class="suggestion-action"><button type="button" class="text-button" data-action="suggest-questions" data-id="${esc(finding.finding_id)}">Use suggested questions</button><p class="small muted">Fills empty uncertainty fields from the check’s suggestions. Edit them for this case; your disposition and rationale stay yours.</p></div>
      <div class="field"><label for="disposition-${index}">Disposition</label>
        <select id="disposition-${index}" name="disposition" required>
          <option value="">Choose an assessment</option>
          ${[
            ['follow_up', 'Follow up — additional evidence needed'],
            ['explained', 'Explained — supported by the rationale'],
            ['escalate', 'Escalate — specialist review needed'],
          ]
            .map(
              ([value, title]) =>
                `<option value="${value}" ${row.disposition === value ? 'selected' : ''}>${title}</option>`,
            )
            .join('')}
        </select>
      </div>
      <div class="field"><label for="rationale-${index}">Evidence-based rationale</label><textarea id="rationale-${index}" name="rationale" required minlength="12" placeholder="Cite the records and explain the reasoning behind your assessment.">${esc(row.rationale || '')}</textarea></div>
      <div class="review-columns">
        ${uncertaintyFields
          .map(
            ([key, label, placeholder]) => `
          <div class="field"><label for="${key}-${index}">${label}</label><textarea id="${key}-${index}" name="${key}" required minlength="12" placeholder="${placeholder}">${esc(array(row[key]).join('\n'))}</textarea><small>One specific item per line, at least 12 characters.</small></div>`,
          )
          .join('')}
      </div>
    </fieldset>`;
}

function guidedReviewUi(findingId) {
  const flow = flowState();
  if (!flow.reviewUi) flow.reviewUi = Object.create(null);
  const key = `${model.selectedRun}:${findingId}`;
  if (!flow.reviewUi[key]) flow.reviewUi[key] = { editing: {}, evidenceIndex: 0 };
  return flow.reviewUi[key];
}

function guidedReviewEvidence(finding) {
  const refs = [
    ...array(finding.record_refs).map((ref) => ({ ...ref, official: false })),
    ...array(finding.source_refs).map((ref) => ({ ...ref, official: true })),
  ];
  if (!refs.length) return '<p class="small muted">No individual records were cited.</p>';
  const ui = guidedReviewUi(finding.finding_id);
  const index = Math.min(Math.max(ui.evidenceIndex, 0), refs.length - 1);
  const ref = refs[index];
  const title = ref.official
    ? `${sourceTitle(ref.source_id)} / ${ref.record_id}`
    : `${human(ref.table)} / ${ref.record_id}`;
  return `<div class="guided-evidence-browser">
    <p class="small muted">${countLabel(array(finding.record_refs).length, 'cited record')} / ${countLabel(array(finding.source_refs).length, 'source listing')}</p>
    <div class="actions">
      <button type="button" class="secondary" data-guided-review="evidence-step" data-id="${esc(finding.finding_id)}" data-index="${index - 1}" aria-label="Previous cited record" ${index === 0 ? 'disabled' : ''}>←</button>
      <button type="button" class="text-button" data-action="${ref.official ? 'source-evidence' : 'evidence'}" data-id="${esc(ref.record_id)}" ${ref.official ? '' : `data-table="${esc(ref.table)}"`}>Open ${esc(title)} ↗</button>
      <button type="button" class="secondary" data-guided-review="evidence-step" data-id="${esc(finding.finding_id)}" data-index="${index + 1}" aria-label="Next cited record" ${index === refs.length - 1 ? 'disabled' : ''}>→</button>
    </div>
    <p class="small muted" aria-live="polite">Cited record ${index + 1} of ${refs.length}. Records open from this run's retained evidence.</p>
  </div>`;
}

function guidedReviewPrompt(finding, index, row, key, title, question) {
  const values = array(row[key]);
  const suggestions = array(finding[key]);
  const editing = Boolean(guidedReviewUi(finding.finding_id).editing[key]);
  const displayed = values.length
    ? `<div class="adopted-review-prompts">${list(values)}</div>`
    : `<p class="small muted">Suggested for consideration. Not yet part of your assessment.</p>${suggestions.length ? list(suggestions) : `<p class="small">${esc(question)}</p>`}`;
  const content = editing
    ? `<div class="field"><label for="guided-${key}-${index}">${esc(question)}</label><textarea id="guided-${key}-${index}" name="${key}" rows="3" minlength="12">${esc(values.join('\n'))}</textarea><small>One specific item per line. These words become part of your assessment.</small></div>`
    : `<textarea name="${key}" hidden aria-hidden="true" tabindex="-1">${esc(values.join('\n'))}</textarea>${displayed}`;
  return `<section class="guided-review-prompt">
    <div class="panel-heading"><h4>${esc(title)}</h4><button type="button" class="text-button" data-guided-review="${editing ? 'finish-edit' : 'edit-prompt'}" data-id="${esc(finding.finding_id)}" data-field="${key}" data-index="${index}">${editing ? 'Keep these words' : values.length ? 'Edit' : 'Write my own'}</button></div>
    ${content}
  </section>`;
}

function guidedReviewProposal(finding, disposition = 'follow_up') {
  const excerpt = (value, limit) => {
    const text = String(value || '').trim();
    return text.length > limit ? `${text.slice(0, limit)}…` : text;
  };
  const observation = excerpt(finding.observation, 6000);
  const question = excerpt(array(finding.unknowns)[0], 1000);
  const falsifier = excerpt(array(finding.falsifiers)[0], 1000);
  return [
    disposition === 'escalate'
      ? 'Request specialist review before resolving this observation.'
      : 'Keep this observation open while the supporting evidence is obtained.',
    `The retained analysis reports: ${observation}`,
    question ? `Question to resolve: ${question}` : '',
    falsifier ? `Evidence that could change the assessment: ${falsifier}` : '',
  ]
    .filter(Boolean)
    .join('\n\n');
}

function guidedReviewRationale(finding, index, row) {
  const ui = guidedReviewUi(finding.finding_id);
  const rationale = String(row.rationale || '');
  const proposed = guidedReviewProposal(finding);
  if (ui.editing.rationale) {
    return `<section class="guided-review-rationale"><div class="field"><label for="guided-rationale-${index}">${row.disposition === 'explained' ? 'What evidence explains this observation?' : 'Your reasoning and proposed next step'}</label><textarea id="guided-rationale-${index}" name="rationale" rows="4" required minlength="12" placeholder="Describe the case-specific evidence and the reasoning behind your assessment.">${esc(rationale)}</textarea><small>${row.disposition === 'explained' ? 'An explanation needs your case-specific reasoning. No explanation is generated for you.' : 'Edit the prepared words to reflect your assessment.'}</small></div><button type="button" class="text-button" data-guided-review="finish-rationale" data-id="${esc(finding.finding_id)}">Keep this reasoning</button></section>`;
  }
  return `<section class="guided-review-rationale ${rationale ? 'recorded-rationale' : 'proposed-rationale'}"><div class="panel-heading"><h4>${rationale ? 'Reasoning in this draft' : 'Proposed follow-up'}</h4><button type="button" class="text-button" data-guided-review="edit-rationale" data-id="${esc(finding.finding_id)}" data-index="${index}">${rationale ? 'Edit reasoning' : 'Edit this proposal'}</button></div><textarea name="rationale" hidden aria-hidden="true" tabindex="-1">${esc(rationale)}</textarea><div class="prepared-review-copy">${(
    rationale || proposed
  )
    .split('\n\n')
    .map((paragraph) => `<p>${esc(paragraph)}</p>`)
    .join(
      '',
    )}</div><p class="small muted">${rationale ? 'Your existing reasoning and review questions will be kept when you choose an action.' : 'Prepared from this observation and its review prompts. It becomes part of your draft only when you choose an action or edit it.'}</p></section>`;
}

function guidedReviewFinding(finding, index, row = {}) {
  const prompts = [
    ['unknowns', 'What remains unresolved', 'What is unknown, and how will you resolve it?'],
    ['alternatives', 'Other explanations', 'What other explanation have you considered?'],
    ['falsifiers', 'What would change your view', 'What evidence would change your assessment?'],
  ];
  const missingPrompts = prompts.some(
    ([key]) => !array(row[key]).length && array(finding[key]).length,
  );
  const recordedPrompts = prompts.every(([key]) => array(row[key]).length);
  return `<fieldset class="review-finding guided-review-finding" data-finding="${esc(finding.finding_id)}">
    <legend>Observation ${index + 1}</legend>
    <h3>${esc(finding.title)}</h3>
    <div class="review-evidence"><p>${esc(findingObservation(finding))}</p>${candidateFacts(finding)}${guidedReviewEvidence(finding)}</div>
    <section class="guided-assessment-action">
      <input type="hidden" name="disposition" value="${esc(row.disposition || '')}">
      ${guidedReviewRationale(finding, index, row)}
      <div class="actions" role="group" aria-label="Assessment action">
        ${[
          ['follow_up', 'adopt-follow-up', 'Keep open with this follow-up'],
          ['escalate', 'adopt-escalation', 'Escalate with this context'],
          ['explained', 'explain', 'Add an explanation'],
        ]
          .map(
            ([value, action, title]) =>
              `<button type="button" class="${row.disposition === value || (!row.disposition && value === 'follow_up') ? '' : 'secondary'}" data-guided-review="${action}" data-id="${esc(finding.finding_id)}" data-disposition="${value}" aria-pressed="${row.disposition === value}">${title}</button>`,
          )
          .join('')}
      </div>
    </section>
    <section class="guided-review-prompts"><div class="panel-heading"><div><h4>Questions to carry into the assessment</h4><p>Consider the check's prompts, then adopt or revise the ones that fit this observation.</p></div>${missingPrompts ? `<button type="button" class="secondary" data-action="suggest-questions" data-id="${esc(finding.finding_id)}">Use these review prompts</button>` : recordedPrompts ? badge('Prompts recorded in this draft') : badge('Your assessment needs context', 'amber')}</div>
      ${prompts.map(([key, title, question]) => guidedReviewPrompt(finding, index, row, key, title, question)).join('')}
    </section>
  </fieldset>`;
}

function handleGuidedReviewClick(button) {
  const action = button.dataset.guidedReview;
  if (!action) return false;
  const finding = array(model.run?.analysis?.findings).find(
    (item) => item.finding_id === button.dataset.id,
  );
  const form = document.querySelector('#review-form');
  if (!finding || !form || form.dataset.saving === 'true') return true;
  const group = [...form.querySelectorAll('[data-finding]')].find(
    (item) => item.dataset.finding === finding.finding_id,
  );
  if (!group) return true;
  const ui = guidedReviewUi(finding.finding_id);
  if (action === 'adopt-follow-up' || action === 'adopt-escalation') {
    const disposition = action === 'adopt-escalation' ? 'escalate' : 'follow_up';
    group.querySelector('[name="disposition"]').value = disposition;
    const rationale = group.querySelector('[name="rationale"]');
    if (!rationale.value.trim()) {
      rationale.value = guidedReviewProposal(finding, disposition);
      ui.preparedRationale = rationale.value;
    }
    ['unknowns', 'alternatives', 'falsifiers'].forEach((key) => {
      const control = group.querySelector(`[name="${key}"]`);
      if (!lines(control.value).length) control.value = array(finding[key]).join('\n');
    });
    ui.editing.rationale = false;
    form.dataset.dirty = 'true';
    saveReviewDraft();
  } else if (action === 'explain') {
    group.querySelector('[name="disposition"]').value = 'explained';
    const rationale = group.querySelector('[name="rationale"]');
    // A prepared open-follow-up statement cannot stand in for a new explanation.
    // Preserve every rationale the analyst has changed or supplied independently.
    if (ui.preparedRationale && rationale.value === ui.preparedRationale) {
      ui.previousPreparedRationale = rationale.value;
      rationale.value = '';
    }
    ui.editing.rationale = true;
    form.dataset.dirty = 'true';
    saveReviewDraft();
  } else if (action === 'edit-rationale' || action === 'finish-rationale') {
    const rationale = group.querySelector('[name="rationale"]');
    if (
      action === 'edit-rationale' &&
      !rationale.value.trim() &&
      group.querySelector('[name="disposition"]').value !== 'explained'
    ) {
      rationale.value = guidedReviewProposal(finding);
      ui.preparedRationale = rationale.value;
      form.dataset.dirty = 'true';
      saveReviewDraft();
    } else preserveDrafts();
    ui.editing.rationale = action === 'edit-rationale';
  } else if (action === 'edit-prompt' || action === 'finish-edit') {
    const field = button.dataset.field;
    if (!['unknowns', 'alternatives', 'falsifiers'].includes(field)) return true;
    preserveDrafts();
    ui.editing[field] = action === 'edit-prompt';
  } else if (action === 'evidence-step') {
    const index = Number(button.dataset.index);
    const total = array(finding.record_refs).length + array(finding.source_refs).length;
    if (!Number.isSafeInteger(index) || index < 0 || index >= total) return true;
    preserveDrafts();
    ui.evidenceIndex = index;
  } else return false;
  model.navigationVersion += 1;
  renderGuided();
  if (action === 'edit-prompt')
    document
      .querySelector(`#guided-${button.dataset.field}-${button.dataset.index}`)
      ?.focus({ preventScroll: true });
  if (action === 'explain' || action === 'edit-rationale')
    document
      .querySelector('.guided-review-finding [name="rationale"]')
      ?.focus({ preventScroll: true });
  if (action === 'evidence-step')
    document
      .querySelector('.guided-evidence-browser [data-action]')
      ?.focus({ preventScroll: true });
  return true;
}

function renderLegacyReview() {
  const run = model.run;
  const findings = array(run.analysis?.findings);
  const draft = model.reviewDrafts[model.selectedRun] || run.latest_review?.review || {};
  model.reviewPage = Math.min(
    model.reviewPage,
    Math.max(0, Math.ceil(findings.length / PAGE_SIZE) - 1),
  );
  const start = model.reviewPage * PAGE_SIZE;
  const completed = findings.filter((finding) =>
    reviewRowComplete(array(draft.findings).find((item) => item.finding_id === finding.finding_id)),
  ).length;
  return `
    <section class="panel">
      <div class="panel-heading"><h2>Analyst assessment</h2>${run.latest_review ? badge('New revision on save') : ''}</div>
      <p class="section-subtitle">Address every observation. Follow-up and escalation can remain open; document the evidence and next steps without implying resolution.</p>
      ${run.latest_review ? '<p class="small muted">A recorded review is loaded below. Saving creates a new revision and retains the earlier assessment.</p>' : ''}
      <form id="review-form" data-dirty="${model.reviewDrafts[model.selectedRun] ? 'true' : 'false'}">
        <div class="field"><label for="reviewer">Reviewer name</label><input id="reviewer" name="reviewer" value="${esc(draft.reviewer || '')}" required minlength="2" maxlength="200" placeholder="Name of the analyst making this assessment"><small>Self-asserted identity, not external authentication.</small></div>
        <div class="field"><label for="review-summary">Overall assessment and next steps</label><textarea id="review-summary" name="summary" required minlength="12" placeholder="What does the evidence support? What remains unresolved, and what happens next?">${esc(draft.summary || '')}</textarea></div>
        <div class="review-toolbar"><span id="review-count" class="review-count" aria-live="polite">${completed} of ${findings.length} observations have all assessment fields filled.</span>${completed < findings.length ? '<button type="button" class="text-button" data-action="next-unreviewed">Go to next incomplete assessment →</button>' : ''}</div>
        ${pageControls('review', model.reviewPage, findings.length)}
        ${findings
          .slice(start, start + PAGE_SIZE)
          .map((finding, index) =>
            reviewFinding(
              finding,
              start + index,
              array(draft.findings).find((item) => item.finding_id === finding.finding_id) || {},
            ),
          )
          .join('')}
        ${pageControls('review', model.reviewPage, findings.length)}
        ${!findings.length ? '<div class="callout">No observations were generated. Record a named assessment of the question, coverage, and unavailable evidence.</div>' : ''}
        <label class="inline-check"><input type="checkbox" name="acknowledge_limitations" required ${draft.acknowledge_limitations ? 'checked' : ''}><span>I reviewed the coverage and limitations, including missing evidence. These observations and identity candidates do not establish a legal violation or clearance.</span></label>
        <div class="form-actions"><button type="submit" ${run.verification?.ok ? '' : 'disabled'}>Save complete review</button><span class="small muted">Required fields are checked. Judgment quality remains the reviewer’s responsibility.</span></div>
      </form>
    </section>`;
}

function readReview(form) {
  const values = new FormData(form);
  if (form.dataset.reviewScope === 'case') {
    return {
      schema_version: '2.2',
      run_id: model.selectedRun,
      reviewer: String(values.get('reviewer') || '').trim(),
      decision: String(values.get('decision') || ''),
      summary: String(values.get('summary') || '').trim(),
      scope_finding_ids: array(model.run.analysis?.findings).map((finding) => finding.finding_id),
      acknowledge_limitations: values.has('acknowledge_limitations'),
    };
  }
  const prior = model.reviewDrafts[model.selectedRun] || model.run.latest_review?.review || {};
  const rows = new Map(array(prior.findings).map((row) => [row.finding_id, row]));
  form.querySelectorAll('[data-finding]').forEach((group) => {
    rows.set(group.dataset.finding, {
      finding_id: group.dataset.finding,
      disposition: group.querySelector('[name="disposition"]').value,
      rationale: group.querySelector('[name="rationale"]').value.trim(),
      unknowns: lines(group.querySelector('[name="unknowns"]').value),
      alternatives: lines(group.querySelector('[name="alternatives"]').value),
      falsifiers: lines(group.querySelector('[name="falsifiers"]').value),
    });
  });
  return {
    schema_version: '2.0',
    run_id: model.selectedRun,
    reviewer: values.get('reviewer').trim(),
    summary: values.get('summary').trim(),
    findings: array(model.run.analysis.findings).map(
      (finding) =>
        rows.get(finding.finding_id) || {
          finding_id: finding.finding_id,
          disposition: '',
          rationale: '',
          unknowns: [],
          alternatives: [],
          falsifiers: [],
        },
    ),
    acknowledge_limitations: values.has('acknowledge_limitations'),
  };
}

function renderContext() {
  const run = model.run;
  return `<section class="panel"><h2>Frozen case definition</h2><pre>${json(run.case)}</pre><h3>Analysis digest</h3><p class="mono small word-break">${esc(run.manifest?.analysis_digest || run.verification?.analysis_digest || 'See manifest')}</p><p class="small muted">A digest can demonstrate unchanged bytes or results. It does not establish truth, authorship, or legal admissibility.</p><details><summary>Run manifest</summary><pre>${json(run.manifest)}</pre></details><details><summary>Latest verification</summary><pre>${json(run.verification)}</pre></details>${run.latest_review ? `<details><summary>Saved review record</summary><pre>${json(run.latest_review)}</pre></details>` : ''}</section>`;
}

function currentView() {
  return { navigation: model.navigationVersion, page: model.page, runId: model.selectedRun };
}

function viewIsCurrent(view) {
  return (
    view.navigation === model.navigationVersion &&
    view.page === model.page &&
    view.runId === model.selectedRun
  );
}

async function openRun(id, expectedNavigation = model.navigationVersion) {
  const run = await api(`runs/${encodeURIComponent(id)}`);
  if (expectedNavigation !== model.navigationVersion) return false;
  if (model.selectedRun !== id) {
    flowState().findingIndex = null;
    model.findingPage = 0;
    model.reviewPage = 0;
  }
  model.selectedRun = id;
  model.run = run;
  model.page = 'runs';
  if (location.hash !== '#runs') location.hash = 'runs';
  render();
  return true;
}

function updateDraftIndicator() {
  const indicator = document.querySelector('#draft-status');
  if (indicator) indicator.hidden = !model.caseDirty && !Object.keys(model.reviewDrafts).length;
}

function saveCaseDraft() {
  const form = document.querySelector('#case-form');
  if (
    !form ||
    form.dataset.saving === 'true' ||
    (form.dataset.dirty !== 'true' && !model.caseDirty)
  )
    return;
  model.caseDraft = readCase(form, false);
  model.caseDirty = true;
  updateDraftIndicator();
}

function saveReviewDraft() {
  const form = document.querySelector('#review-form');
  if (
    form &&
    form.dataset.saving !== 'true' &&
    model.selectedRun &&
    (form.dataset.dirty === 'true' || model.reviewDrafts[model.selectedRun])
  ) {
    const draft = readReview(form);
    model.reviewDrafts[model.selectedRun] = draft;
    const counter = document.querySelector('#review-count');
    const message = isCaseReview(draft)
      ? 'Case decision saved in this draft.'
      : `${draft.findings.filter(reviewRowComplete).length} of ${draft.findings.length} observations have all assessment fields filled.`;
    if (counter && counter.textContent !== message) counter.textContent = message;
    updateDraftIndicator();
    if (model.page === 'investigate') updateFlowCube();
  }
}

function preserveDrafts() {
  saveCaseDraft();
  saveReviewDraft();
}

async function filesPayload(files) {
  const entries = [...files];
  if (entries.reduce((total, file) => total + file.size, 0) > model.state.limits.upload_bytes) {
    throw new Error(`Combined files exceed the ${uploadLimitLabel()} upload limit.`);
  }
  return Promise.all(
    entries.map(async (file) => {
      const bytes = new Uint8Array(await file.arrayBuffer());
      const chunks = [];
      for (let offset = 0; offset < bytes.length; offset += 32768) {
        chunks.push(String.fromCharCode(...bytes.subarray(offset, offset + 32768)));
      }
      return { name: file.name, content_base64: btoa(chunks.join('')) };
    }),
  );
}

function lockForm(form) {
  form.dataset.saving = 'true';
  const controls = [...form.querySelectorAll('input, select, textarea')];
  const original = controls.map((control) => control.disabled);
  controls.forEach((control) => {
    control.disabled = true;
  });
  return () => {
    form.dataset.saving = 'false';
    controls.forEach((control, index) => {
      control.disabled = original[index];
    });
  };
}

async function submitDataset(form) {
  const view = currentView();
  const body = {
    dataset_id: form.elements.dataset_id.value.trim(),
    label: form.elements.label.value.trim(),
    files: await filesPayload(form.elements.files.files),
  };
  const unlock = lockForm(form);
  try {
    const result = await api('datasets/import', body);
    await refresh(false);
    if (viewIsCurrent(view)) render();
    announce(
      `Imported ${result.dataset_id}. ${countsText(result.counts)}.${result.warnings?.length ? `\n${result.warnings.join('\n')}` : ''}`,
    );
  } finally {
    unlock();
  }
}

async function submitSource(form, method) {
  const view = currentView();
  const body = {
    source_id: form.elements.source_id.value,
    snapshot_id: form.elements.snapshot_id.value.trim(),
  };
  if (method === 'import') {
    if (!form.elements.file.files.length)
      throw new Error('Choose a downloaded snapshot file before importing.');
    body.files = await filesPayload(form.elements.file.files);
  }
  const unlock = lockForm(form);
  try {
    const result = await api(`sources/${method === 'import' ? 'import' : 'fetch'}`, body);
    await refresh(false);
    if (viewIsCurrent(view)) render();
    announce(`Source snapshot saved: ${result.snapshot_id || body.snapshot_id || body.source_id}.`);
  } finally {
    unlock();
  }
}

async function submitCase(form, action) {
  const view = currentView();
  const definition = readCase(form);
  model.caseDraft = definition;
  model.caseDirty = true;
  const submittedDraft = JSON.stringify(definition);
  const unlock = lockForm(form);
  try {
    await api('cases', definition);
    if (JSON.stringify(model.caseDraft) === submittedDraft) model.caseDirty = false;
    if (action === 'run') {
      const run = await api(`cases/${encodeURIComponent(definition.case_id)}/run`, {});
      await refresh(false);
      if (viewIsCurrent(view)) {
        model.runTab = 'findings';
        await openRun(run.run_id, view.navigation);
      }
      announce(
        `Run saved with ${run.findings_count} observations. Find it in Findings & review and inspect coverage before assessing it.`,
      );
    } else {
      await refresh(false);
      if (viewIsCurrent(view)) render();
      announce(`Case ${definition.case_id} saved.`);
    }
    updateDraftIndicator();
  } finally {
    unlock();
  }
}

async function submitReview(form) {
  const view = currentView();
  const review = readReview(form);
  const runId = model.selectedRun;
  model.reviewDrafts[runId] = review;
  const submittedDraft = JSON.stringify(review);
  if (!model.run?.verification?.ok)
    throw new Error('The retained files must pass verification before a decision can be recorded.');
  if (!isCaseReview(review) && model.page === 'investigate' && flowSummaryNeedsUpdate(review))
    throw new Error(
      'The individual assessments changed. Update the prepared summary or edit it before saving.',
    );
  if (isCaseReview(review)) {
    if (!['keep_open', 'escalate', 'conclude'].includes(review.decision))
      throw new Error('Choose whether to keep the case open, escalate it, or conclude it.');
    if (review.reviewer.length < 2) throw new Error('Enter the name attached to this decision.');
    if (!review.acknowledge_limitations)
      throw new Error('Confirm that you reviewed the findings and coverage.');
    if (review.summary.length < 12)
      throw new Error('Add a specific reason and next step (at least 12 characters).');
  }
  const incomplete = isCaseReview(review)
    ? -1
    : review.findings.findIndex((row) => !reviewRowComplete(row));
  if (incomplete !== -1) {
    model.reviewPage = Math.floor(incomplete / PAGE_SIZE);
    if (model.page === 'investigate') {
      model.flow.reviewIndex = incomplete;
      renderGuided();
    } else renderRuns();
    document.querySelector('#review-form [data-finding] select')?.focus();
    throw new Error(
      `Observation ${incomplete + 1} needs a disposition and specific rationale, unknowns, alternatives, and evidence that would change the assessment.`,
    );
  }
  const unlock = lockForm(form);
  try {
    await api(`runs/${encodeURIComponent(runId)}/review`, review);
    if (JSON.stringify(model.reviewDrafts[runId]) === submittedDraft)
      delete model.reviewDrafts[runId];
    await refresh(false);
    if (viewIsCurrent(view)) {
      if (model.page === 'investigate') {
        const run = await api(`runs/${encodeURIComponent(runId)}`);
        if (viewIsCurrent(view)) {
          model.run = run;
          model.flow.stage = 'package';
          model.flow.cubeFace = 5;
          model.flow.inspectionFace = null;
          renderGuided();
        }
      } else await openRun(runId, view.navigation);
    }
    announce('Case decision recorded.');
    updateDraftIndicator();
  } finally {
    unlock();
  }
}

// Guided investigation: a revision owns every preview, plan, and result.
function newFlow() {
  return {
    stage: 'goal',
    goalId: '',
    goalInferred: false,
    datasetId: '',
    asOf: dateToday(),
    snapshotId: '',
    sourcePolicy: 'automatic',
    sourceRetry: false,
    subjectName: '',
    identityResearch: null,
    identityError: '',
    files: [],
    preview: null,
    mapping: {},
    previewStale: false,
    plan: null,
    planInputs: null,
    recordsConfirmed: false,
    approval: null,
    approvalPlanId: null,
    resultsReview: null,
    revision: 0,
    reviewIndex: 0,
    cubeFace: 0,
    motionPaused: false,
    inspectionFace: null,
    surfaceOpen: false,
    settingsOpen: false,
    busyStep: '',
    revealResults: false,
    autoRunning: false,
    autoViewChanged: false,
  };
}

function flowState() {
  if (!model.flow) model.flow = newFlow();
  return model.flow;
}

function flowContext() {
  const flow = flowState();
  return {
    view: currentView(),
    flow,
    revision: flow.revision,
    route: model.routeVersion,
    automatic: flow.autoRunning,
  };
}

function flowIsCurrent(context) {
  const sameInput = context.flow === flowState() && context.revision === flowState().revision;
  if (!sameInput) return false;
  // Turning the object changes its visible face, not the work in progress.
  // Leaving the route (even briefly), changing inputs, or opening another run
  // still cancels later stages of an automatic investigation.
  return context.automatic
    ? context.route === model.routeVersion &&
        context.view.page === model.page &&
        context.view.runId === model.selectedRun
    : viewIsCurrent(context.view);
}

async function flowRequest(context, path, body) {
  try {
    return await api(path, body);
  } catch (error) {
    // An abandoned request must not report its error in another investigation.
    if (!flowIsCurrent(context)) return null;
    throw error;
  }
}

async function refreshFlow(context) {
  const state = await flowRequest(context, 'state');
  if (!flowIsCurrent(context)) return false;
  model.state = state;
  updateStorageLabels();
  return true;
}

function invalidateFlow(changes = {}, keepInspection = false) {
  preserveDrafts();
  const flow = flowState();
  const inspectionFace =
    keepInspection && flow.autoRunning && flow.autoViewChanged ? flow.inspectionFace : null;
  Object.assign(flow, { settingsOpen: false }, changes, {
    plan: null,
    planInputs: null,
    approval: null,
    approvalPlanId: null,
    resultsReview: null,
    ...('datasetId' in changes && !changes.recordsConfirmed ? { recordsConfirmed: false } : {}),
    inspectionFace,
  });
  if ('datasetId' in changes && changes.datasetId !== flow.identityResearch?.dataset_id)
    flow.identityResearch = null;
  model.flow.revision += 1;
}

function flowDataset() {
  return array(model.state.datasets).find((item) => item.dataset_id === flowState().datasetId);
}

function flowGoal() {
  return array(model.state.workflow_goals).find((item) => item.id === flowState().goalId);
}

function flowInput() {
  const flow = flowState();
  return {
    dataset_id: flow.datasetId,
    goal_id: flow.goalId,
    as_of: flow.asOf,
    ...(flow.snapshotId && flowGoal()?.requires_source
      ? { watchlist_snapshot_id: flow.snapshotId }
      : {}),
  };
}

function flowReviewRecorded(run) {
  const draft = model.reviewDrafts[model.selectedRun];
  const canonical = (value) =>
    Array.isArray(value)
      ? value.map(canonical)
      : value && typeof value === 'object'
        ? Object.fromEntries(
            Object.keys(value)
              .sort()
              .map((key) => [key, canonical(value[key])]),
          )
        : value;
  return Boolean(
    run?.verification?.ok &&
    run.latest_review &&
    run.review_validation?.ok === true &&
    (!draft ||
      JSON.stringify(canonical(draft)) === JSON.stringify(canonical(run.latest_review.review))),
  );
}

function flowSourcesAccepted() {
  const flow = flowState();
  return Boolean(
    flow.approval &&
    flow.plan &&
    flow.approvalPlanId === flow.plan.plan_id &&
    flow.planInputs &&
    JSON.stringify(flow.planInputs) === JSON.stringify(flowInput()),
  );
}

function flowWorkflowRecorded(run) {
  return Boolean(
    run?.verification?.ok &&
    run.workflow?.status === 'recorded' &&
    run.workflow.records_selected &&
    run.workflow.source_accepted &&
    run.workflow.plan_approved,
  );
}

function flowResultsReviewed(run) {
  if (!run?.verification?.ok) return false;
  return Boolean(
    (run.latest_review?.review?.acknowledge_limitations && run.review_validation?.ok === true) ||
    (flowState().resultsReview?.runId === model.selectedRun &&
      flowState().resultsReview?.run === run),
  );
}

function flowLegacyNote(run) {
  if (flowWorkflowRecorded(run)) return '';
  if (!run?.verification?.ok)
    return '<p class="callout error">The retained files could not be verified. Stage approvals cannot be verified.</p>';
  return `<div class="callout workflow-history"><p>This run has no recorded source acceptance or plan approval. Its saved results and assessment remain available.</p><button type="button" class="text-button" data-flow="investigate-dataset" data-id="${esc(run?.handoff?.continuation_dataset_id || run?.case?.dataset_id || '')}">Review these records anew →</button></div>`;
}

function flowStageAccess(index) {
  if (!Number.isInteger(index) || index < 0 || index > 5) return false;
  if (index === 0) return true;
  const flow = flowState();
  const run = ['review', 'package'].includes(flow.stage) ? model.run : null;
  if (run) {
    if (index < 4) return true;
    if (index === 4) return flowResultsReviewed(run);
    return flowReviewRecorded(run);
  }
  const accepted =
    Boolean(flow.datasetId && flow.recordsConfirmed) &&
    !['goal', 'data', 'identity'].includes(flow.stage);
  if (index === 1) return accepted;
  if (index === 2) return accepted && Boolean(flow.plan) && flowCubeFaces()[1].complete;
  return false;
}

function flowNextStage() {
  const flow = flowState();
  const current = flow.inspectionFace ?? flow.cubeFace;
  return flowStageAccess(current + 1) ? current + 1 : current;
}

function flowCubeFaces() {
  const flow = flowState();
  const run = ['review', 'package'].includes(flow.stage) ? model.run : null;
  const preview = flow.stage === 'data' ? flow.preview : null;
  const counts =
    run?.dataset_metadata?.counts || flowDataset()?.counts || flow.plan?.dataset_summary?.counts;
  const review = run ? model.reviewDrafts[model.selectedRun] || run.latest_review?.review : null;
  const findings = array(run?.analysis?.findings);
  const source = run
    ? screeningSource(run)
    : flow.plan?.source_status?.selected
      ? flow.plan.source_status
      : null;
  const checked = run
    ? array(run.analysis?.coverage).filter((row) => row.status === 'executed').length
    : array(flow.plan?.selected_checks).length;
  const verified = run?.verification?.ok === true;
  const workflowRecorded = flowWorkflowRecorded(run);
  const datasetReady = Boolean(
    !preview &&
    !['identity', 'goal', 'data'].includes(flow.stage) &&
    (run
      ? workflowRecorded
      : flow.recordsConfirmed && flowDataset() && flowDataset().status !== 'invalid'),
  );
  const planReady = run ? workflowRecorded : false;
  const sourcesReady = run ? workflowRecorded : flowSourcesAccepted();
  const findingsReady = flowResultsReviewed(run);
  const legacy = Boolean(run && !workflowRecorded);
  const reviewReady = flowReviewRecorded(run);
  return [
    {
      title: 'Records',
      complete: datasetReady,
      status:
        run && !verified
          ? 'Cannot verify'
          : legacy
            ? 'Not recorded'
            : datasetReady
              ? 'Selected'
              : '',
      value: preview
        ? formatNumber(preview.row_count)
        : counts
          ? formatNumber(Object.values(counts).reduce((sum, n) => sum + Number(n || 0), 0))
          : '—',
      detail: preview ? 'Rows ready for your confirmation' : counts ? countsText(counts) : '',
    },
    {
      title: 'Sources',
      complete: sourcesReady,
      status:
        run && !verified
          ? 'Cannot verify'
          : legacy
            ? 'Not recorded'
            : sourcesReady
              ? 'Accepted'
              : flow.plan
                ? 'Review needed'
                : '',
      value: source ? formatNumber(source.record_count) : '—',
      detail: source
        ? source.record_count === undefined
          ? 'Source retained in the saved investigation'
          : 'Entries in the selected reference snapshot'
        : sourcesReady
          ? 'No reference list required'
          : 'No reference list selected',
    },
    {
      title: 'Plan',
      complete: planReady,
      status:
        run && !verified
          ? 'Cannot verify'
          : legacy
            ? 'Not recorded'
            : planReady
              ? 'Approved'
              : flow.plan
                ? 'Draft'
                : '',
      value: checked ? formatNumber(checked) : '—',
      detail: run
        ? 'Checks executed on the retained records'
        : flow.plan
          ? 'Checks prepared from your records'
          : 'A plan takes shape from your records',
    },
    {
      title: 'Findings',
      complete: findingsReady,
      status: findingsReady ? 'Reviewed' : verified ? 'Review needed' : '',
      value: run ? formatNumber(findings.length) : '—',
      detail: run
        ? 'Observations linked to their evidence'
        : 'Run the plan to see what needs attention',
    },
    {
      title: 'Assessment',
      complete: reviewReady,
      status: reviewReady
        ? caseDecisionStatus(run.latest_review.review.decision) || 'Recorded'
        : review
          ? 'Draft'
          : '',
      value: reviewReady ? 'Recorded' : review ? 'Draft' : '—',
      detail: 'Case decision and notes',
    },
    {
      title: 'Package',
      complete: Boolean(workflowRecorded && reviewReady && run?.latest_export),
      status:
        reviewReady && run?.latest_export
          ? legacy
            ? 'Earlier package'
            : 'Created'
          : reviewReady
            ? 'Ready'
            : '',
      value: reviewReady && run?.latest_export ? 'Created' : reviewReady ? 'Ready' : '—',
      detail: run?.latest_review
        ? 'Recorded review and retained evidence'
        : 'A complete review enables the evidence package',
    },
  ];
}

// The stored stage index is retained across saved workflows. The object itself
// is a folding document box; it has no free rotation or drag navigation.
function boxPanelState() {
  return flowCubeFaces().map((face, index) => ({
    ...face,
    step: BOX_STEPS[index],
    available: flowStageAccess(index),
  }));
}

function flowCube() {
  const flow = flowState();
  const faces = boxPanelState();
  return `<section class="flow-instrument" aria-label="Investigation box">
    <div class="box-scene" aria-label="The investigation folds into an evidence box"></div>
    <nav class="cube-controls box-stages" aria-label="Investigation stages">
      ${faces.map((item, index) => `<button type="button" data-flow="cube" data-face="${index}" data-complete="${item.complete}" aria-label="Open ${esc(item.title)}" aria-description="Step ${index + 1} of 6. ${item.status || 'Not started'}" aria-pressed="${flow.cubeFace === index}" ${item.available ? '' : 'disabled'}><span class="stage-number" aria-hidden="true">${item.step}<span class="stage-check">✓</span></span><span class="stage-copy">${esc(item.title)}<small class="stage-status">${esc(item.status)}</small></span></button>`).join('')}
    </nav>
  </section>`;
}

function flowGuide() {
  const flow = flowState();
  const run = ['review', 'package'].includes(flow.stage) ? model.run : null;
  const disposition = caseDecisionStatus(run?.latest_review?.review?.decision);
  const findings = array(run?.analysis?.findings);
  const face = flow.inspectionFace ?? flow.cubeFace;
  const stages = flowCubeFaces();
  const next = flowNextStage();
  if (flow.stage === 'goal' && !flow.busyStep) return flowStartView();
  let status = '';
  let title = '';
  let action = '<button type="button" data-flow="choose-file">Add records</button>';
  if (flow.busyStep) {
    status = flow.busyStep;
    action = '';
  } else if (flow.stage === 'identity') {
    title = flow.identityResearch?.query || flow.subjectName;
    status = flow.identityError
      ? 'Identity lookup paused'
      : array(flow.identityResearch?.candidates).length
        ? 'Choose the public record that fits'
        : 'No identity selected';
    action = `<button type="button" data-flow="focus-step">${flow.identityError ? 'Resume identity lookup' : 'Review identity'} →</button>`;
  } else if (flow.stage === 'data') {
    status = flow.preview
      ? `${countLabel(flow.preview.row_count, 'record')} / ${!flow.preview.can_import ? 'corrections needed' : flow.previewStale ? 'mapping changed' : 'ready to import'}`
      : '';
    action = flow.preview
      ? '<button type="button" data-flow="focus-step">Review import ↓</button>'
      : flow.surfaceOpen
        ? ''
        : '<button type="button" data-flow="choose-file">Choose files</button>';
  } else if (flow.stage === 'plan' || flow.stage === 'running') {
    if (flow.sourceRetry)
      return `<div class="flow-guide"><p class="guide-status" role="status">Records saved. The screening list is unavailable.</p><button type="button" data-flow="investigate-dataset" data-id="${esc(flow.datasetId)}">Retry source download →</button>${flowWorkActions()}</div>`;
    status = !flow.plan
      ? 'Preparing sources and checks'
      : flowSourcesAccepted()
        ? 'Plan ready for your review'
        : 'Sources ready for your review';
    action = '<button type="button" data-flow="focus-step">Continue review →</button>';
  } else if (flow.stage === 'review' || flow.stage === 'package') {
    title = run?.dataset_metadata?.label || run?.case?.question || '';
    status =
      run?.verification?.ok !== true
        ? 'Retained files could not be verified'
        : face >= 4
          ? flowReviewRecorded(run)
            ? `${disposition ? `Recorded: ${disposition}` : 'Case decision recorded'}${run.latest_export ? ' / Evidence package created' : ''}`
            : model.reviewDrafts[model.selectedRun]
              ? 'Case decision has unsaved changes'
              : run?.latest_review
                ? 'Recorded decision needs verification'
                : 'Case decision not yet recorded'
          : face === 3
            ? `${countLabel(findings.length, 'observation')} / ${countLabel(array(run?.analysis?.coverage).filter((row) => row.status === 'executed').length, 'completed check')}`
            : stages[face]?.detail || '';
    action = `<button type="button" data-flow="focus-step">Open ${face === 5 ? 'evidence package' : (stages[face]?.title || 'investigation').toLowerCase()} →</button>`;
  }
  if (!flow.busyStep && flow.surfaceOpen && next !== face)
    action = `<button type="button" data-flow="continue">${esc(stages[next].title)} →</button>`;
  return `<div class="flow-guide">${title ? `<p class="overview-case-title">${esc(title)}</p>` : ''}${status ? `<p class="guide-status" role="status">${esc(status)}</p>` : ''}<div class="actions">${action}</div>${flow.busyStep ? '' : flowWorkActions()}</div>`;
}

function flowWorkActions() {
  return '<div class="entry-tools" role="group" aria-label="Other investigations"><button type="button" class="text-button" data-flow="restart" aria-label="Start a new investigation">New</button><button type="button" class="text-button" data-flow="open-work" aria-label="Open saved work" aria-haspopup="dialog">Open</button></div>';
}

function flowStartView() {
  const flow = flowState();
  return `<div class="flow-guide flow-start">
    <form id="flow-subject-form" class="subject-start">
      <div class="subject-label"><label for="flow-subject-name">Who are you looking into?</label><button type="button" class="information-button" data-flow="screening-info" aria-label="About name screening" aria-haspopup="dialog"><svg viewBox="0 0 20 20" aria-hidden="true"><circle cx="10" cy="10" r="7.5"/><path d="M10 9v5M10 6v.5"/></svg></button></div>
      <div class="subject-entry"><input id="flow-subject-name" name="name" type="text" required maxlength="200" autocomplete="off" placeholder="Company or person" value="${esc(flow.subjectName)}"><button type="submit">Find records →</button></div>
    </form>
    <div class="entry-tools" role="group" aria-label="Other ways to begin">
      <button type="button" class="text-button" data-flow="choose-file" aria-label="Import records"><svg viewBox="0 0 20 20" aria-hidden="true"><path d="M10 3v9m-3-3 3 3 3-3M4 12v4a1 1 0 0 0 1 1h10a1 1 0 0 0 1-1v-4"/></svg><span>Import</span></button>
      <button type="button" class="text-button" data-flow="open-work" aria-label="Open saved work" aria-haspopup="dialog"><svg viewBox="0 0 20 20" aria-hidden="true"><path d="M3 6V5a1 1 0 0 1 1-1h4l2 2h6a1 1 0 0 1 1 1v1M3 8h14l-2 8H3z"/></svg><span>Open</span></button>
    </div>
  </div>`;
}

function savedRunTitle(run) {
  const dataset = array(model.state.datasets).find((item) => item.dataset_id === run.dataset_id);
  return (
    run.dataset_label || dataset?.label || run.dataset_id || run.case_id || 'Untitled investigation'
  );
}

function savedWorkView() {
  const datasets = array(model.state.datasets).filter((item) => item.status !== 'invalid');
  const runs = array(model.state.runs)
    .filter((item) => item.status !== 'invalid' && item.verification_status !== 'failed')
    .toSorted((a, b) => String(b.created_at || '').localeCompare(String(a.created_at || '')));
  const investigations = runs.map((run) => {
    const title = savedRunTitle(run);
    const disposition = reviewRecorded(run.status) && caseDecisionStatus(run.case_decision);
    const assessment = disposition
      ? ` / Recorded: ${disposition}`
      : reviewRecorded(run.status)
        ? ' / Assessed'
        : '';
    return `<li><button type="button" class="saved-work-item" data-flow="resume" data-id="${esc(run.run_id)}"><span class="saved-work-name">${esc(title)}</span><span class="saved-work-meta"><span>${esc(displayDate(run.created_at))}</span><span>${countLabel(run.findings_count, 'observation')}${esc(assessment)}</span></span></button></li>`;
  });
  const records = datasets.map((dataset) => {
    const selected = dataset.identity_association === 'user_selected_public_record';
    const sources = array(dataset.identity_profile?.sources).map(
      (source) =>
        ({ 'GLEIF legal entity records': 'GLEIF', 'Wikidata public directory': 'Wikidata' })[
          source
        ] || source,
    );
    const kind = selected
      ? sources.length
        ? `Selected ${sources.join(' + ')} details`
        : 'Selected public identity'
      : dataset.identity_association === 'no_profile_selected'
        ? 'Name only'
        : dataset.intake_method === 'subject_name' && !dataset.identity_research_retained
          ? 'Original name'
          : '';
    const title =
      (selected && dataset.identity_profile?.name) || dataset.label || 'Untitled records';
    const detail = [kind, countsText(dataset.counts)].filter(Boolean).join(' / ');
    return `<li><button type="button" class="saved-work-item" data-flow="investigate-dataset" data-id="${esc(dataset.dataset_id)}"><span class="saved-work-name">${esc(title)}</span><span class="saved-work-meta"><span>${esc(detail)}</span><span>Investigate →</span></span></button></li>`;
  });
  return `<div class="saved-work"><div class="actions"><label class="text-button browser-restore-label">Open a case package<input type="file" accept=".zip,application/zip" data-handoff-file aria-label="Choose an evidence package to open"></label></div>${model.state?.storage?.mode === 'browser' ? '<div class="actions browser-workspace-tools"><button type="button" class="text-button" data-browser-backup>Download workspace backup</button><label class="text-button browser-restore-label">Restore a backup<input type="file" accept=".zip,application/zip" data-browser-restore aria-label="Choose a workspace backup to restore"></label></div>' : ''}${investigations.length ? `<section aria-label="Investigations"><h3>Investigations</h3><ul>${investigations.join('')}</ul></section>` : ''}${records.length ? `<section aria-label="Records"><h3>Records</h3><ul>${records.join('')}</ul></section>` : ''}${!investigations.length && !records.length ? '<p class="small muted">No saved work yet.</p>' : ''}</div>`;
}

function handoffPreviewView(preview) {
  return `<section class="flow-section"><h3>${esc(preview.case_title || 'Received investigation')}</h3><p>${esc(caseDecisionStatus(preview.decision) || 'Recorded assessment')} · ${esc(preview.analyst || 'Analyst not recorded')}</p><p class="small muted">${esc(countsText(preview.counts))}</p><p>The retained files passed verification. Adding this case keeps your existing work.</p><div class="actions"><button type="button" data-flow="handoff-import">Add to my workspace →</button><button type="button" class="information-button" data-flow="handoff-info" aria-label="About received case packages" aria-haspopup="dialog">i</button></div></section>`;
}

async function inspectHandoff(file) {
  preserveDrafts();
  model.handoff = null;
  const view = currentView();
  showFlowDocument(
    'Open case package',
    '<p role="status">Checking the package and retained records…</p>',
  );
  const revision = dialogRevision;
  try {
    const [payload] = await filesPayload([file]);
    const preview = await api('handoffs/inspect', { file: payload });
    if (!viewIsCurrent(view) || revision !== dialogRevision) return;
    if (preview.verification?.ok !== true || !/^[a-f0-9]{64}$/.test(preview.package_sha256 || ''))
      throw new Error('This package did not pass verification. No records were added.');
    model.handoff = { file: payload, preview };
    document.querySelector('#dialog-content').innerHTML = handoffPreviewView(preview);
    announce('Package checked. Review it before adding it to your workspace.');
  } catch (error) {
    if (viewIsCurrent(view) && revision === dialogRevision) {
      document.querySelector('#dialog-content').innerHTML =
        `<p class="callout error">${esc(error.message)}</p><label class="text-button browser-restore-label">Choose another package<input type="file" accept=".zip,application/zip" data-handoff-file aria-label="Choose another evidence package"></label>`;
      throw error;
    }
  } finally {
    if ((!viewIsCurrent(view) || revision !== dialogRevision) && notice.className === 'notice busy')
      notice.hidden = true;
  }
}

async function importHandoff() {
  const handoff = model.handoff;
  if (!handoff?.preview || handoff.preview.verification?.ok !== true)
    throw new Error('Choose and check a case package first.');
  preserveDrafts();
  const view = currentView();
  const revision = dialogRevision;
  let result;
  try {
    result = await api('handoffs/import', {
      file: handoff.file,
      expected_sha256: handoff.preview.package_sha256,
    });
  } catch (error) {
    if (viewIsCurrent(view) && revision === dialogRevision)
      document.querySelector('#dialog-content').innerHTML =
        `${handoffPreviewView(handoff.preview)}<p class="callout error">${esc(error.message)}</p>`;
    throw error;
  }
  await refresh(false);
  if (viewIsCurrent(view) && revision === dialogRevision) {
    model.handoff = null;
    document.querySelector('#evidence-dialog').close();
    if (model.page !== 'investigate') {
      model.page = 'investigate';
      location.hash = 'investigate';
    }
    await resumeFlowRun(result.run_id);
  }
  announce(
    result.imported
      ? 'Case added. The original records and assessment are retained.'
      : 'This package is already in your workspace.',
  );
}

function flowGoalsView() {
  return '';
}

function previewIssue(issue, preview) {
  const text = String(issue);
  const prefix = `${preview.file_name}:`;
  const row = text.startsWith(prefix)
    ? text.slice(prefix.length).match(/^(\d+): ([^:]+): (.+)$/)
    : null;
  if (!row) return text;
  const [, number, field, detail] = row;
  if (field === 'country' && detail.includes("'^[A-Z]{2}$'"))
    return `Row ${number}: Country must be a recognized country name or two-letter country code.`;
  if (field === 'lei' && detail.includes("'^[A-Z0-9]{20}$'"))
    return `Row ${number}: LEI must contain 20 letters or digits.`;
  if (field === 'name' && detail.includes('at least 1 character'))
    return `Row ${number}: Counterparty name is required.`;
  const title =
    array(preview.target_fields).find((item) => item.id === field)?.title || human(field);
  return `Row ${number}: ${title}: ${detail}`;
}

function previewActionWarnings(preview) {
  return array(preview.warnings).filter(
    (warning) =>
      !/^(?:Same-name records remain separate|Original CSV bytes and unmapped columns|Text fields are trimmed|Aliases accept a JSON array|Generated \d+ deterministic record IDs)/.test(
        warning,
      ),
  );
}

function flowPreviewView() {
  const flow = flowState();
  const preview = flow.preview;
  if (!preview) return '';
  return `<section class="flow-preview">
    <div class="panel-heading"><div><h3>Import preview</h3><p>${esc(preview.file_name)} / ${countLabel(preview.row_count, 'row')}</p></div><div class="actions">${badge(flow.previewStale ? 'Mapping changed' : 'Preview only')}<button type="button" class="information-button" data-flow="preview-info" aria-label="About this import preview" aria-haspopup="dialog">ⓘ</button></div></div>
    <div class="table-wrap"><table><thead><tr><th>File column</th><th>Use as</th><th>Values from file</th></tr></thead><tbody>
      ${array(preview.columns)
        .map(
          (column, index) =>
            `<tr><td><label for="mapping-${index}">${esc(column.name)}</label></td><td><select id="mapping-${index}" data-mapping="${esc(column.name)}"><option value="">Retain in original file only</option>${array(
              preview.target_fields,
            )
              .map(
                (field) =>
                  `<option value="${esc(field.id)}" ${flow.mapping[column.name] === field.id ? 'selected' : ''}>${esc(field.title)}${field.required ? ' (required)' : ''}</option>`,
              )
              .join(
                '',
              )}</select></td><td class="small">${esc(array(column.samples).join(' / '))}</td></tr>`,
        )
        .join('')}
    </tbody></table></div>
    ${array(preview.transformations).length ? `<section class="conversion-summary"><h3>Values recognized</h3>${list(preview.transformations.map((item) => `${item.source_value} → ${item.normalized_value} (${countLabel(item.record_count, 'record')})`))}</section>` : ''}
    ${previewActionWarnings(preview).length ? `<div class="callout warning">${list(previewActionWarnings(preview))}</div>` : ''}
    ${array(preview.errors).length ? `<div class="callout error"><strong>Fix before importing</strong>${list(preview.errors.map((issue) => previewIssue(issue, preview)))}</div>` : ''}
    <div class="preview-records">${array(preview.preview_rows)
      .slice(0, 3)
      .map(
        (row) =>
          `<div><strong>${esc(row.name || row.entity_id)}</strong><span>${esc([row.country, row.address].filter(Boolean).join(' / '))}</span></div>`,
      )
      .join('')}</div>
    <div class="actions"><button type="button" class="text-button" data-flow="change-files">Change files</button>${flow.previewStale ? '<button type="button" class="secondary" data-flow="repreview">Update preview</button>' : ''}<button type="button" data-flow="import" ${!preview.can_import || flow.previewStale ? 'disabled' : ''}>Investigate these records →</button></div>
  </section>`;
}

function flowDataView() {
  if (flowState().preview) return flowPreviewView();
  return `<div class="flow-intro identity-heading"><h1>Import records</h1><button type="button" class="information-button" data-flow="import-info" aria-label="About record formats and privacy" aria-haspopup="dialog">ⓘ</button></div>
    <form id="flow-upload-form" class="object-upload"><label for="flow-vendor-file">Choose records <span>CSV or JSON</span></label><input id="flow-vendor-file" name="files" type="file" accept=".csv,.json" multiple required></form>
    <div class="actions"><button class="text-button" type="button" data-flow="back-goal">Start with a name</button></div>`;
}

function identityProfile(candidate) {
  const labels = {
    country: 'Country',
    address: 'Address',
    city: 'City',
    postal_code: 'Postal code',
    registration_id: 'Registration',
    lei: 'LEI',
  };
  const fields = Object.fromEntries(
    Object.entries(candidate.fields || {})
      .filter(([, value]) => value !== null && value !== '')
      .map(([field, value]) => [labels[field] || human(field), value]),
  );
  const directory = array(candidate.claims).some((claim) => claim.kind === 'directory_claim');
  const recordUrl =
    array(candidate.claims).find((claim) => claim.field === 'name')?.source_url ||
    array(candidate.source_urls)[0];
  return `<div class="identity-profile"><h2>${esc(candidate.name)}</h2>${candidate.description ? `<p class="small muted">${esc(candidate.description)}</p>` : ''}${keyValues(fields)}<p class="identity-attribution small">${directory ? 'Wikidata directory record' : 'GLEIF reference record'}${recordUrl ? ` ${sourceLink(recordUrl, 'Source ↗')}` : ''}</p></div>`;
}

function flowIdentityView() {
  const flow = flowState();
  const report = flow.identityResearch;
  if (!report)
    return flow.identityError
      ? `<div class="flow-intro"><h1>Identity lookup paused</h1><p>${esc(flow.subjectName || flowDataset()?.label || '')}</p></div><p class="callout error">${esc(flow.identityError)}</p><div class="actions"><button type="button" data-flow="research-identity">Retry lookup →</button><button type="button" class="text-button" data-flow="back-goal">Use another name</button></div>`
      : '<div class="flow-intro"><h1>Looking up the identity…</h1></div>';
  const candidates = array(report.candidates);
  return `<div class="flow-intro identity-heading"><div><h1>${candidates.length ? 'Which identity fits?' : report.status === 'unavailable' ? 'Identity lookup unavailable' : 'No identity found'}</h1><p>${esc(report.query)}</p></div><button type="button" class="information-button" data-flow="identity-info" aria-label="About these identity sources" aria-haspopup="dialog">ⓘ</button></div>
    ${candidates.length ? `<div class="identity-options">${candidates.map((candidate) => `<article>${identityProfile(candidate)}<button type="button" data-flow="identity-select" data-id="${esc(candidate.candidate_id)}">Use this identity →</button></article>`).join('')}</div>` : `<p>${report.status === 'unavailable' ? 'The public directories could not be reached. You can retry or screen the entered name.' : 'The public directories returned no usable profile. You can still screen the entered name.'}</p>`}
    <div class="actions"><button type="button" class="text-button" data-flow="identity-skip">Continue with name only →</button><button type="button" class="text-button" data-flow="back-goal">Use another name</button>${!candidates.length ? '<button type="button" class="text-button" data-flow="research-identity">Retry lookup</button>' : ''}</div>`;
}

function identityResearchDetails(research) {
  const candidate = research?.selected_candidate;
  const claims = array(research?.claims || candidate?.claims);
  return `${candidate ? identityProfile(candidate) : ''}${research?.notice ? `<p class="small muted">${esc(research.notice)}</p>` : ''}${array(research?.conflicts).length ? `<h3>Different values retained</h3>${list(research.conflicts.map((item) => `${human(item.field)}: supplied record ${item.retained_value}; public source ${item.source_value}`))}` : ''}${
    claims.length
      ? `<div class="table-wrap"><table><thead><tr><th>Field</th><th>Source value</th><th>Attribution</th></tr></thead><tbody>${claims
          .map(
            (claim) =>
              `<tr><td>${esc(human(claim.field))}</td><td>${esc(claim.value)}</td><td>${sourceLink(claim.source_url, claim.source_label || claim.kind)}${array(
                claim.reference_urls,
              )
                .map((url) => `<br>${sourceLink(url, 'Cited reference ↗')}`)
                .join('')}</td></tr>`,
          )
          .join('')}</tbody></table></div>`
      : ''
  }<p class="small muted">${array(research?.providers)
    .map((provider) => `${esc(provider.label || provider.id)}: ${esc(human(provider.status))}`)
    .join('; ')}</p>`;
}

function flowCheckRows(checks, proposed) {
  return array(checks)
    .map(
      (check) =>
        `<div class="proposed-check"><div><h3>${esc(check.title || investigationTitle(check.investigation_id))}</h3><p>${esc(check.reason || check.description || '')}</p></div><button type="button" class="text-button" data-flow="check-info" data-check="${esc(check.investigation_id)}">${proposed ? 'Method ↗' : 'Needs data ↗'}</button></div>`,
    )
    .join('');
}

function flowSourceView(plan) {
  const flow = flowState();
  const status = plan?.source_status || {};
  const requiresSource = flowGoal()?.requires_source;
  const ready = Boolean(plan && (!requiresSource || status.selected));
  const warnings = array(status.warnings).filter(
    (warning) =>
      warning !== 'List membership is source-specific evidence, not a legal determination.',
  );
  const settings = flow.settingsOpen;
  const selector =
    requiresSource && (settings || !status.selected)
      ? `<div class="field"><label for="flow-source">Reference snapshot</label><select id="flow-source"><option value="">Choose a snapshot or download the official list</option>${array(
          model.state.sources,
        )
          .map(
            (source) =>
              `<option value="${esc(source.snapshot_id)}" ${source.snapshot_id === flow.snapshotId ? 'selected' : ''}>${esc(sourceTitle(source.source_id))} / ${esc(displayDate(source.source_updated_at || source.fetched_at))}</option>`,
          )
          .join('')}</select></div>`
      : '';
  return `<section class="flow-section source-review">
    ${requiresSource ? `<h2>${esc(status.title || 'Consolidated Screening List')}</h2>${status.selected ? `<div class="source-summary">${keyValues({ Entries: formatNumber(status.record_count), Acquired: displayDate(status.fetched_at) || 'Unknown', 'Source updated': displayDate(status.source_updated_at) || 'Unknown' })}</div>` : '<p>The official list must be retained before name screening can run.</p>'}` : `<h2>Supplied records</h2><p>${esc(countsText(plan?.dataset_summary?.counts || flowDataset()?.counts))}. These checks use the selected dataset; no external screening list is included.</p>`}
    ${warnings.length ? `<div class="callout warning">${list(warnings)}</div>` : ''}
    ${selector}
    ${settings || !ready ? (requiresSource ? '<button type="button" class="secondary" data-flow="fetch">Download official CSL →</button>' : '') : ''}
    ${!settings ? `<div class="object-next"><button type="button" data-flow="approve-sources" ${ready ? '' : 'disabled'}>${flowSourcesAccepted() ? 'Continue to plan' : 'Use these sources'} →</button><button class="information-button" type="button" data-flow="source-info" aria-label="Source provenance and limitations" aria-haspopup="dialog">i</button><button class="text-button" type="button" data-flow="plan-settings">Change sources</button></div>` : ''}
    ${!settings && !plan ? '<button class="text-button" type="button" data-flow="plan">Prepare sources and checks →</button>' : ''}
  </section>`;
}

function flowPlanView() {
  const flow = flowState();
  const plan = flow.plan;
  const dataset = flowDataset();
  if (!flowSourcesAccepted())
    return `<div class="flow-intro"><h1>Review sources</h1></div>${flowSourceView(plan)}`;
  return `<div class="flow-intro"><h1>Review plan</h1><p>${esc(plan?.case?.question || 'Select the records to prepare a plan.')}</p></div>
    <div class="plan-overview"><div><strong>${esc(countsText(plan?.dataset_summary?.counts || dataset?.counts))}</strong><span class="small muted">${esc(dataset?.label || flow.datasetId)}</span></div><div><span class="small muted">As of ${esc(displayDate(flow.asOf))}</span><button class="text-button" type="button" data-flow="plan-settings">Change scope or date</button></div></div>
    <section class="flow-section"><h2>${countLabel(array(plan.selected_checks).length, 'available check')}</h2>${flowCheckRows(plan.selected_checks, true)}${!plan.selected_checks.length ? '<p>No checks have enough evidence yet.</p>' : ''}</section>
    ${array(plan.unavailable_checks).length ? `<section class="flow-section"><h2>Cannot evaluate</h2>${flowCheckRows(plan.unavailable_checks, false)}</section>` : ''}
    ${flowGoal()?.requires_source ? '<p class="plan-scope">Scope: name and identifier screening. Item classification, destination, end use, ownership restrictions, and export authorization are outside this plan.</p>' : ''}
    <div class="object-next"><button type="button" data-flow="run" ${plan.can_run ? '' : 'disabled'}>Run reviewed plan →</button><button class="information-button" type="button" data-flow="plan-info" aria-label="Plan methods and limitations" aria-haspopup="dialog">i</button></div>`;
}

function flowReviewNavigation(index, total) {
  return `<div class="flow-review-nav"><button class="secondary" type="button" data-flow="review-step" data-index="${index - 1}" ${index === 0 ? 'disabled' : ''}>← Previous</button><span>${index < total ? `Observation ${index + 1} of ${total}` : 'Overall assessment'}</span><button type="button" data-flow="review-step" data-index="${index + 1}" ${index >= total ? 'disabled' : ''}>${index + 1 < total ? 'Next observation' : 'Overall assessment'} →</button></div>`;
}

function preparedReviewSummary(run, draft) {
  const coverage = array(run.analysis?.coverage);
  const findings = array(run.analysis?.findings);
  const rows = array(draft.findings);
  const executed = coverage.filter((row) => row.status === 'executed').length;
  const missing = coverage.length - executed;
  const open = rows.filter((row) => row.disposition === 'follow_up').length;
  const escalated = rows.filter((row) => row.disposition === 'escalate').length;
  const explained = rows.filter((row) => row.disposition === 'explained').length;
  return [
    `Assessment of: ${run.case?.question || 'the retained investigation'}`,
    `${run.dataset_metadata?.synthetic ? 'This run uses fictional example records. ' : ''}The retained analysis completed ${countLabel(executed, 'check')} and generated ${countLabel(findings.length, 'observation')}. ${countLabel(missing, 'check')} could not be evaluated.`,
    findings.length
      ? `The individual assessments record ${open} for follow-up, ${escalated} for escalation, and ${explained} as explained. Follow the evidence requests and next steps recorded for each observation; an open item remains unresolved.`
      : 'No observations were generated by the checks that ran. This does not establish that the underlying records are accurate, complete, or clear of restrictions.',
    `${missing ? 'Obtain the missing evidence identified in the coverage before drawing conclusions about checks that could not run. ' : ''}The result is limited to the retained inputs and executed checks. It does not establish identity, a legal violation, or clearance.`,
  ].join('\n\n');
}

function flowSummaryNeedsUpdate(draft) {
  const ui = guidedReviewUi('__summary');
  const saved = model.run.latest_review?.review;
  if (
    !ui.preparedSummary &&
    saved?.summary &&
    saved.summary === preparedReviewSummary(model.run, saved)
  )
    ui.preparedSummary = saved.summary;
  return Boolean(
    ui.preparedSummary &&
    draft.summary === ui.preparedSummary &&
    draft.summary !== preparedReviewSummary(model.run, draft),
  );
}

function flowSummaryView(draft, completed, total) {
  const ui = guidedReviewUi('__summary');
  const proposed = preparedReviewSummary(model.run, draft);
  const stale = flowSummaryNeedsUpdate(draft);
  const complete = completed === total;
  return `<section class="guided-review-rationale"><div class="panel-heading"><h2>${draft.summary ? 'Your overall assessment' : 'Prepared overall assessment'}</h2><button type="button" class="text-button" data-flow="summary-edit">${ui.editing.summary ? 'Keep these words' : 'Edit the summary'}</button></div>
    ${
      ui.editing.summary
        ? `<div class="field"><label for="review-summary">Overall assessment and next steps</label><textarea id="review-summary" name="summary" required minlength="12">${esc(draft.summary || '')}</textarea></div>`
        : `<textarea name="summary" hidden aria-hidden="true" tabindex="-1">${esc(draft.summary || '')}</textarea><div class="prepared-review-copy">${(
            draft.summary || proposed
          )
            .split('\n\n')
            .map((paragraph) => `<p>${esc(paragraph)}</p>`)
            .join('')}</div>`
    }
    ${stale ? '<p class="callout warning">The individual assessments changed after this summary was prepared. Update it or edit it before saving.</p>' : ''}
    ${!draft.summary || stale ? `<button type="button" data-flow="summary-adopt" ${complete ? '' : 'disabled'}>${stale ? 'Update the summary from these assessments' : 'Use this summary'}</button>` : ''}
    <p class="small muted">${complete ? 'Prepared from the retained results and the actions you selected. Adopt or edit it before recording the review.' : 'Assess each observation first. The summary will reflect your selected actions.'}</p>
  </section>`;
}

function legacyFlowReviewView() {
  const flow = flowState();
  const run = model.run;
  if (!run) return empty('Run unavailable', 'Open a retained run from Findings & review.');
  const findings = array(run.analysis?.findings);
  const draft = model.reviewDrafts[model.selectedRun] || run.latest_review?.review || {};
  const index = Math.min(flow.reviewIndex, findings.length);
  const completed = array(draft.findings).filter(reviewRowComplete).length;
  const coverage = array(run.analysis?.coverage);
  const summary = index === findings.length;
  return `<div class="flow-intro"><h1>${summary ? 'Overall assessment' : 'Assessment'}</h1><p>${esc(run.case?.question)}</p></div>
    ${run.dataset_metadata?.synthetic ? `<p>${badge('Synthetic example', 'amber')}</p>` : ''}
    <div class="review-progress"><strong>${countLabel(findings.length, 'observation')}</strong><span>${countLabel(coverage.filter((row) => row.status === 'executed').length, 'check')} completed</span><span>${countLabel(coverage.filter((row) => row.status !== 'executed').length, 'check')} not evaluated</span></div>
    ${run.verification?.ok ? '' : '<div class="callout error">Retained files did not pass verification. Review cannot be saved or exported.</div>'}
    ${array(run.review_validation?.issues).length ? `<div class="callout error">${list(run.review_validation.issues)}</div>` : ''}
    <button type="button" class="text-button" data-flow="coverage">View coverage and missing evidence ↗</button>
    <form id="review-form" data-dirty="${model.reviewDrafts[model.selectedRun] ? 'true' : 'false'}">
      <div class="review-toolbar"><span id="review-count" class="review-count" aria-live="polite">${completed} of ${findings.length} observations have all assessment fields filled.</span><button type="button" class="text-button" data-flow="review-summary">Go to overall assessment →</button></div>
      ${
        summary
          ? `${flowSummaryView(draft, completed, findings.length)}<div class="field"><label for="reviewer">Record the assessment under your name</label><input id="reviewer" name="reviewer" value="${esc(draft.reviewer || '')}" required minlength="2" maxlength="200" autocomplete="name"><small>This identifies the reviewer; it is not external authentication.</small></div>
      ${
        findings.length
          ? `<div class="assessment-index">${findings
              .map((finding, findingIndex) => {
                const row = array(draft.findings).find(
                  (item) => item.finding_id === finding.finding_id,
                );
                return `<button class="secondary" type="button" data-flow="review-step" data-index="${findingIndex}"><span>${findingIndex + 1}. ${esc(finding.title)}</span>${badge(reviewRowComplete(row) ? human(row.disposition) : 'Needs assessment', reviewRowComplete(row) ? '' : 'amber')}</button>`;
              })
              .join('')}</div>`
          : '<div class="callout">No observations were generated. Review the coverage and unavailable evidence before recording your overall assessment. This is not a clearance.</div>'
      }
      <label class="inline-check"><input name="acknowledge_limitations" type="checkbox" required ${draft.acknowledge_limitations ? 'checked' : ''}><span>I reviewed the coverage and limitations, including missing evidence. These observations and identity candidates do not establish a legal violation or clearance.</span></label>
      <div class="form-actions"><button type="submit" ${run.verification?.ok ? '' : 'disabled'}>Save complete review & continue →</button><span class="small muted">Required fields are checked. Judgment quality remains your responsibility.</span></div>`
          : `<input type="hidden" name="reviewer" value="${esc(draft.reviewer || '')}"><input type="hidden" name="summary" value="${esc(draft.summary || '')}">${draft.acknowledge_limitations ? '<input type="hidden" name="acknowledge_limitations" value="true">' : ''}${guidedReviewFinding(findings[index], index, array(draft.findings).find((row) => row.finding_id === findings[index].finding_id) || {})}`
      }
      ${flowReviewNavigation(index, findings.length)}
    </form>`;
}

function caseDecisionStatus(decision) {
  const labels = { keep_open: 'Keep open', escalate: 'Escalated', conclude: 'Concluded' };
  return Object.hasOwn(labels, decision) ? labels[decision] : '';
}

function isCaseReview(review) {
  return ['2.1', '2.2'].includes(review?.schema_version);
}

function caseReviewDraft() {
  const review = model.reviewDrafts[model.selectedRun] || model.run?.latest_review?.review;
  return isCaseReview(review) ? review : {};
}

function caseReviewView() {
  const run = model.run;
  if (!run) return empty('Run unavailable', 'Open a retained investigation.');
  if (!run.verification?.ok)
    return `<div class="flow-intro"><h1>Assessment unavailable</h1></div><div class="callout error"><p>The retained files did not pass verification. Existing decision drafts are kept.</p>${list(run.verification?.issues)}</div><button type="button" class="secondary" data-action="verify">Verify files again</button>`;
  const draft = caseReviewDraft();
  const saved = run.latest_review?.review;
  const coverage = array(run.analysis?.coverage);
  const complete = coverage.filter((row) => row.status === 'executed').length;
  const gaps = coverage.length - complete;
  return `<div class="flow-intro case-heading"><h1>Assessment</h1><p>${esc(run.dataset_metadata?.label || run.case?.question || 'Retained investigation')}</p>
    <p class="small muted">${countLabel(array(run.analysis?.findings).length, 'observation')} / ${countLabel(complete, 'completed check')}${gaps ? ` / ${countLabel(gaps, 'check')} not evaluated` : ''}${run.dataset_metadata?.synthetic ? ' / Fictional example' : ''}</p></div>
    ${array(run.review_validation?.issues).length ? `<div class="callout error">${list(run.review_validation.issues)}</div>` : ''}
    <div class="actions"><button type="button" class="text-button" data-flow="finding-list">Review findings ↗</button>${supportingRecordsAction(run)}<button type="button" class="text-button" data-flow="coverage">Checks and sources ↗</button></div>
    ${saved ? `<p class="small muted">Recorded by ${esc(saved.reviewer)}${isCaseReview(saved) ? `: ${esc(caseDecisionStatus(saved.decision))}` : ' in an earlier review'}. Saving keeps that record and adds a revision.</p>` : ''}
    <form id="review-form" data-review-scope="case" class="case-decision-form" data-dirty="${model.reviewDrafts[model.selectedRun] ? 'true' : 'false'}">
      <h2>Case decision</h2>
      <fieldset class="case-decisions"><legend class="sr-only">Decision for this investigation</legend>
        ${[
          ['keep_open', 'Keep open', 'Further evidence needed'],
          ['escalate', 'Escalate', 'Specialist review needed'],
          ['conclude', 'Conclude', 'Record your conclusion'],
        ]
          .map(
            ([value, title, detail]) =>
              `<label><input type="radio" name="decision" value="${value}" required ${draft.decision === value ? 'checked' : ''}><span><strong>${title}</strong><small>${detail}</small></span></label>`,
          )
          .join('')}
      </fieldset>
      <div class="field"><label for="review-summary">Reason and next step</label><textarea id="review-summary" name="summary" rows="3" required minlength="12" maxlength="10000" placeholder="Explain the evidence, remaining uncertainty, and what happens next.">${esc(draft.summary || '')}</textarea></div>
      <div class="field case-reviewer"><label for="reviewer">Your name</label><input id="reviewer" name="reviewer" value="${esc(draft.reviewer || '')}" required minlength="2" maxlength="200" autocomplete="name"></div>
      <label class="inline-check"><input type="checkbox" name="acknowledge_limitations" required ${draft.acknowledge_limitations ? 'checked' : ''}><span>I reviewed the findings and coverage, including missing evidence.</span></label>
      <div class="form-actions"><button type="submit" ${run.verification?.ok ? '' : 'disabled'}>Record case decision →</button></div>
    </form>`;
}

function flowReviewView() {
  // Preserve unfinished legacy drafts in their original contract, never silently convert them.
  if (model.reviewDrafts[model.selectedRun]?.schema_version === '2.0')
    return legacyFlowReviewView();
  return caseReviewView();
}

function renderReview() {
  if (model.reviewDrafts[model.selectedRun]?.schema_version === '2.0') return renderLegacyReview();
  return `<section class="panel case-review-panel">${caseReviewView()}</section>`;
}

function findingChart(finding) {
  if (finding.investigation_id !== 'volume_spike') return '';
  const metrics = finding.metrics || {};
  const counts = [
    ...Object.entries(metrics.prior_month_counts || {}).sort(([a], [b]) => a.localeCompare(b)),
    [metrics.month, metrics.current_count],
  ];
  if (
    !metrics.month ||
    !counts.length ||
    counts.some(([, value]) => !Number.isFinite(Number(value)) || Number(value) < 0)
  )
    return '';
  const maximum = Math.max(1, ...counts.map(([, value]) => Number(value)));
  return `<figure class="shipment-chart"><figcaption>Monthly shipments <span>Retained records</span></figcaption><div class="shipment-bars" role="img" aria-label="${esc(counts.map(([month, value]) => `${month}: ${value}`).join('; '))}">${counts.map(([month, value], index) => `<div class="shipment-bar ${index === counts.length - 1 ? 'current-month' : ''}"><strong>${esc(value)}</strong><div class="shipment-bar-track"><svg aria-hidden="true" viewBox="0 0 50 128" preserveAspectRatio="none"><rect x="0" y="${128 - (Number(value) / maximum) * 128}" width="50" height="${(Number(value) / maximum) * 128}" rx="2"/></svg></div><span>${esc(month)}</span></div>`).join('')}</div><p class="small muted">Prior monthly mean: ${esc(metrics.prior_mean)}. Current count: ${esc(metrics.current_count)}.</p></figure>`;
}

function evidenceCell(value) {
  if (value === null || value === undefined || value === '') return '—';
  if (Array.isArray(value))
    return value
      .map((item) => (typeof item === 'object' ? JSON.stringify(item) : String(item)))
      .join(', ');
  if (typeof value === 'object')
    return Object.entries(value)
      .map(([key, item]) => `${human(key)}: ${evidenceCell(item)}`)
      .join('; ');
  return String(value);
}

function evidenceTableCell(key, value) {
  if (['entity_id', 'exporter_id', 'importer_id', 'parent_id', 'child_id'].includes(key)) {
    const name = retainedEntityName(value);
    if (name && name !== String(value))
      return `<span class="evidence-name">${esc(name)}</span><small class="evidence-id muted">${esc(value)}</small>`;
  }
  return esc(evidenceCell(value));
}

function findingEvidenceRows(finding) {
  if (!model.run?.verification?.ok)
    return '<p class="callout error">The retained files could not be verified. Reopen the investigation after restoring them.</p>';
  const ui = guidedReviewUi(finding.finding_id);
  const evidence = ui.evidence;
  const count = array(finding.record_refs).length + array(finding.source_refs).length;
  if (!count) return '<p class="small muted">This result cites no individual records.</p>';
  const status = ui.evidenceError
    ? `<div class="callout error"><p>${esc(ui.evidenceError)}</p><button type="button" class="secondary" data-flow="finding-records" data-id="${esc(finding.finding_id)}" data-offset="${ui.evidenceRequestedOffset || 0}">Retry records</button></div>`
    : ui.evidenceLoading || !evidence
      ? '<p class="small muted" role="status">Loading the cited records…</p>'
      : '';
  if (!evidence) return status;
  const groups = new Map();
  array(evidence.rows).forEach((row) => {
    const table = row.table;
    if (!groups.has(table)) groups.set(table, []);
    groups.get(table).push(row);
  });
  const columns = {
    shipments: ['shipment_id', 'date', 'exporter_id', 'importer_id', 'qty', 'unit'],
    payments: ['payment_id', 'shipment_id', 'date', 'amount', 'ccy', 'bank', 'broker'],
    entities: ['entity_id', 'name', 'country', 'address'],
    ownership: ['parent_id', 'child_id', 'ownership_percent'],
    diligence: ['evidence_id', 'entity_id', 'date', 'title', 'text'],
    source: ['name', 'list_name', 'countries'],
  };
  return (
    status +
    [...groups.entries()]
      .map(([table, rows]) => {
        const keys = (columns[table] || Object.keys(rows[0]?.record || {}).slice(0, 5)).filter(
          (key) => rows.some((row) => row.record?.[key] !== undefined),
        );
        return `<div class="evidence-table"><h3>${esc(human(table === 'source' ? 'Official listings' : table))}</h3><div class="table-wrap"><table><thead><tr>${keys.map((key) => `<th scope="col">${esc(human(key))}</th>`).join('')}<th scope="col">Provenance</th></tr></thead><tbody>${rows.map((row) => `<tr>${keys.map((key) => `<td>${evidenceTableCell(key, row.record?.[key])}${row.identity_research?.applied_fields?.[key] ? '<small class="muted">Public-source claim</small>' : ''}</td>`).join('')}<td><button type="button" class="text-button" data-action="${row.kind === 'source' ? 'source-evidence' : 'evidence'}" data-id="${esc(row.id)}" ${row.kind === 'source' ? '' : `data-table="${esc(table)}"`} aria-label="Open ${esc(table)} ${esc(row.id)} with provenance">View ↗</button></td></tr>`).join('')}</tbody></table></div></div>`;
      })
      .join('') +
    (evidence.total > evidence.rows.length
      ? `<div class="actions evidence-pagination"><span class="small muted">${evidence.offset + 1}–${evidence.offset + evidence.rows.length} of ${evidence.total} records</span><button class="text-button" type="button" data-flow="finding-records" data-id="${esc(finding.finding_id)}" data-offset="${Math.max(0, evidence.offset - 40)}" ${ui.evidenceLoading || evidence.offset === 0 ? 'disabled' : ''}>Previous</button><button class="text-button" type="button" data-flow="finding-records" data-id="${esc(finding.finding_id)}" data-offset="${evidence.offset + evidence.rows.length}" ${ui.evidenceLoading || evidence.offset + evidence.rows.length >= evidence.total ? 'disabled' : ''}>Next</button></div>`
      : '')
  );
}

function findingEvidenceIsVisible(runId, findingId) {
  const flow = flowState();
  const finding = array(model.run?.analysis?.findings)[flow.findingIndex];
  return (
    model.selectedRun === runId &&
    finding?.finding_id === findingId &&
    ((model.page === 'investigate' &&
      flow.surfaceOpen &&
      (flow.inspectionFace ?? flow.cubeFace) === 3) ||
      (model.page === 'runs' && model.runTab === 'findings'))
  );
}

async function loadFindingEvidence(finding, offset = 0) {
  const runId = model.selectedRun;
  const retainedRun = model.run;
  if (!retainedRun?.verification?.ok) return;
  const ui = guidedReviewUi(finding.finding_id);
  if (ui.evidence?.offset === offset || ui.evidenceLoading) return;
  ui.evidenceLoading = true;
  ui.evidenceError = '';
  ui.evidenceRequestedOffset = offset;
  const updateRecords = () => {
    if (findingEvidenceIsVisible(runId, finding.finding_id)) {
      const region = document.querySelector('#finding-evidence-records');
      if (region) {
        region.setAttribute('aria-busy', String(ui.evidenceLoading));
        region.innerHTML = findingEvidenceRows(finding);
      }
    }
  };
  updateRecords();
  try {
    const evidence = await api(
      `runs/${encodeURIComponent(runId)}/finding-evidence?finding_id=${encodeURIComponent(finding.finding_id)}&offset=${offset}`,
    );
    // This cache belongs to this immutable run/finding, even if its view has changed.
    ui.evidence = evidence;
  } catch (error) {
    // Keep the last verified page during a temporary connection/server failure.
    // A rejected reference or failed integrity check invalidates that cache.
    if (error.status >= 400 && error.status < 500) ui.evidence = null;
    ui.evidenceError = error.message || 'The cited records could not be loaded.';
    if (error.status === 409) {
      retainedRun.verification = { ok: false, issues: [ui.evidenceError] };
      if (model.run === retainedRun && ['investigate', 'runs'].includes(model.page)) {
        preserveDrafts();
        if (model.page === 'investigate') renderGuided();
        else if (model.page === 'runs') renderRuns();
        announce(ui.evidenceError, 'error');
      }
    }
  } finally {
    ui.evidenceLoading = false;
    updateRecords();
  }
}

function loadVisibleFindingEvidence() {
  const flow = flowState();
  const finding = array(model.run?.analysis?.findings)[flow.findingIndex];
  if (finding && findingEvidenceIsVisible(model.selectedRun, finding.finding_id)) {
    const ui = guidedReviewUi(finding.finding_id);
    if (!ui.evidence && !ui.evidenceError) loadFindingEvidence(finding);
  }
}

function findingEvidenceView(run, index) {
  if (run.verification?.ok === false)
    return '<p class="callout error">The retained files failed verification. This finding and its evidence are unavailable.</p>';
  const findings = array(run.analysis?.findings);
  const finding = findings[index];
  if (!finding) return empty('Finding unavailable', 'Return to the retained findings.');
  const chart = findingChart(finding);
  const values =
    finding.investigation_id !== 'screening_candidates' && !chart
      ? Object.fromEntries(
          Object.entries(finding.metrics || {}).map(([key, value]) => [
            human(key),
            evidenceCell(value),
          ]),
        )
      : {};
  return `<article class="finding-detail"><nav class="finding-detail-nav" aria-label="Finding navigation"><button type="button" class="text-button" data-flow="finding-list">← All findings</button>${supportingRecordsAction(run)}<button type="button" class="text-button" data-flow="review-summary">Case assessment ↗</button></nav>
    <header class="flow-intro"><span class="object-label">${esc(
      array(finding.entity_ids)
        .map((id) => retainedEntityName(id, run))
        .join(', '),
    )}${run.dataset_metadata?.synthetic ? ' / Fictional example' : ''}</span><h1>${esc(finding.title)}</h1><p>${esc(findingObservation(finding))}</p></header>
    ${candidateFacts(finding)}${chart}${Object.keys(values).length ? `<section class="computed-evidence">${keyValues(values)}</section>` : ''}
    <section class="finding-records"><div class="panel-heading"><h2>Cited evidence</h2><span class="small muted">${countLabel(array(finding.record_refs).length + array(finding.source_refs).length, 'record')}</span></div><div id="finding-evidence-records" aria-live="polite">${run.verification?.ok ? findingEvidenceRows(finding) : '<p class="callout error">The retained files failed verification. These records cannot be opened.</p>'}</div></section>
    <section class="finding-limits"><h2>Limits of this result</h2>${list([...array(finding.unknowns), ...array(finding.alternatives)])}<h2>Evidence that could resolve it</h2>${list(finding.falsifiers)}</section>
    <nav class="finding-detail-nav" aria-label="Adjacent findings"><button type="button" class="text-button" data-flow="review-step" data-index="${index - 1}" ${index === 0 ? 'disabled' : ''}>← Previous finding</button><span class="small muted">${index + 1} / ${findings.length}</span><button type="button" class="text-button" data-flow="review-step" data-index="${index + 1}" ${index === findings.length - 1 ? 'disabled' : ''}>Next finding →</button></nav>
  </article>`;
}

function packageReviewContext(run = model.run) {
  if (!flowReviewRecorded(run) || !run?.latest_export?.sha256 || !run.latest_review?.review_id)
    return null;
  return {
    package_sha256: run.latest_export.sha256,
    run_id: run.manifest?.run_id || model.selectedRun,
    review_id: run.latest_review.review_id,
    analysis_digest: run.manifest?.analysis_digest || run.verification?.analysis_digest,
    analyst: run.latest_review.review.reviewer,
  };
}

function reviewerApi() {
  if (!window.OmphalosReviewer)
    throw new Error('Signed review is unavailable. Reload this page to load the review tools.');
  return window.OmphalosReviewer;
}

function independentReceiptSummary(context) {
  const receipts = context && model.receiptCache[context.package_sha256];
  if (!receipts) return '';
  const trusted = receipts.filter(
    (item) => item.trusted && !item.own_key && !item.same_analyst_name,
  );
  if (!trusted.length) return 'No review from a trusted reviewer key.';
  const decisions = new Set(trusted.map((item) => item.receipt.payload.decision));
  if (decisions.size > 1) return 'Conflicting signed reviews — resolve with the reviewers.';
  return decisions.has('request_changes')
    ? 'Reviewer requested changes.'
    : 'Approved by a trusted reviewer key.';
}

function independentReviewActions(run) {
  const context = packageReviewContext(run);
  if (!context) return '';
  return '<div class="actions"><button type="button" class="secondary" data-flow="independent-review" aria-haspopup="dialog">Independent review ↗</button></div>';
}

function signedReceiptView(item) {
  const payload = item.receipt.payload;
  const label = payload.decision === 'approve' ? 'Approved' : 'Changes requested';
  const trust = item.own_key
    ? 'Signed in this browser'
    : item.same_analyst_name
      ? 'Same name as the analyst'
      : item.trusted
        ? 'Trusted reviewer key'
        : 'Reviewer key not trusted';
  return `<section class="flow-section"><h3>${label} · ${esc(payload.reviewer_name)}</h3><p>${esc(payload.note)}</p><p class="small muted">${esc(displayDate(payload.created_at))} / ${trust}</p><button type="button" class="text-button" data-reviewer-action="download-receipt" data-id="${esc(item.id)}">Download signed receipt ↓</button></section>`;
}

function reviewerDialogView(session) {
  const pending = session.pending;
  if (pending) {
    const payload = pending.receipt.payload;
    return `<section class="flow-section"><h3>${payload.decision === 'approve' ? 'Approved' : 'Changes requested'} · ${esc(payload.reviewer_name)}</h3><p>${esc(payload.note)}</p><p>The signature matches this exact package.</p>${pending.own_key || pending.same_analyst_name ? '<p class="callout">This receipt cannot count as independent review: it uses this browser’s key or the analyst’s name.</p>' : pending.trusted ? '<button type="button" data-reviewer-action="accept-receipt">Retain signed review →</button>' : `<p class="small muted">Confirm the reviewer’s key through a separate trusted channel before accepting this receipt.</p><p class="mono small word-break">${esc(pending.reviewer.key_sha256)}</p><form id="reviewer-trust-form"><div class="field"><label for="reviewer-fingerprint">Fingerprint received directly from your reviewer</label><input id="reviewer-fingerprint" name="fingerprint" required pattern="[A-Fa-f0-9]{64}" minlength="64" maxlength="64" autocomplete="off" spellcheck="false"></div><button type="submit">Trust this key and retain review →</button></form>`}</section><button type="button" class="text-button" data-reviewer-action="back">← Review tools</button><p id="reviewer-status" role="status" hidden></p>`;
  }
  const caseLabel = `<p><strong>${esc(session.caseTitle || 'Evidence package')}</strong>${session.caseDecision ? ` / ${esc(session.caseDecision)}` : ''}</p>`;
  if (session.mode === 'sign') {
    const draft = session.signDraft || {};
    const form = session.profile
      ? `<form id="reviewer-sign-form"><h3>Review this package</h3><p class="small muted">Signing as ${esc(session.profile.name)}</p><input type="text" name="username" autocomplete="username" value="${esc(session.profile.name)}" hidden><div class="field"><label for="reviewer-decision">Decision</label><select id="reviewer-decision" name="decision" required><option value="">Choose a decision</option><option value="approve" ${draft.decision === 'approve' ? 'selected' : ''}>Approve this package</option><option value="request_changes" ${draft.decision === 'request_changes' ? 'selected' : ''}>Request changes</option></select></div><div class="field"><label for="reviewer-note">Reason and next step</label><textarea id="reviewer-note" name="note" rows="3" minlength="12" maxlength="10000" required>${esc(draft.note || '')}</textarea></div><div class="field"><label for="reviewer-unlock">Signing passphrase</label><input id="reviewer-unlock" name="passphrase" type="password" maxlength="1024" autocomplete="current-password" required></div><button type="submit">Sign review →</button></form>`
      : '<form id="reviewer-profile-form"><h3>Your signing key</h3><div class="field"><label for="reviewer-signing-name">Your name</label><input id="reviewer-signing-name" name="name" minlength="2" maxlength="120" autocomplete="name" required></div><div class="field"><label for="reviewer-passphrase">Signing passphrase</label><input id="reviewer-passphrase" name="passphrase" type="password" minlength="14" maxlength="1024" autocomplete="new-password" required><small>At least 14 characters. Store it in your password manager.</small></div><div class="field"><label for="reviewer-confirm">Confirm passphrase</label><input id="reviewer-confirm" name="confirmation" type="password" minlength="14" maxlength="1024" autocomplete="new-password" required></div><button type="submit">Create my signing key →</button></form>';
    return `<button type="button" class="text-button" data-reviewer-action="back">← Review tools</button>${caseLabel}${form}<p id="reviewer-status" role="status" hidden></p>`;
  }
  return `${caseLabel}<div class="actions"><button type="button" data-reviewer-action="start-review">Review this package</button><label class="text-button browser-restore-label">Open a signed review<input type="file" accept=".json,application/json" data-reviewer-file aria-label="Choose a signed review receipt"></label><button type="button" class="information-button" data-reviewer-action="info" aria-label="About signing and reviewer trust">i</button></div>${reviewerReceiptsView(session)}<div class="actions">${session.profile ? '<button type="button" class="text-button" data-reviewer-action="download-key">Download my public key card ↓</button>' : ''}<button type="button" class="text-button" data-reviewer-action="trust-settings">Trusted reviewer keys</button></div><p id="reviewer-status" role="status" hidden></p>`;
}

function reviewerReceiptsView(session) {
  const received = session.receipts.map(signedReceiptView).join('');
  return `<div id="reviewer-receipts">${session.receipts.length ? `<p class="small muted">${esc(independentReceiptSummary(session.context))}</p>` : ''}${received}${session.issued.map(signedReceiptView).join('')}${!session.receipts.length && !session.issued.length ? '<p class="small muted">No signed reviews for this package.</p>' : ''}</div>`;
}

async function refreshReviewerTrust() {
  const session = model.independentReview;
  if (!session || !reviewerSessionIsCurrent(session) || model.operation) return;
  try {
    const service = reviewerApi();
    const [receipts, issued] = await Promise.all([
      service.receipts(session.context),
      service.issued(session.context),
    ]);
    if (!reviewerSessionIsCurrent(session) || model.operation) return;
    Object.assign(session, { receipts, issued });
    model.receiptCache[session.context.package_sha256] = receipts;
    if (session.pending) {
      const pending = await service.inspect(session.pending.receipt, session.context);
      if (!reviewerSessionIsCurrent(session) || model.operation) return;
      if (pending.trusted !== session.pending.trusted) {
        session.pending = pending;
        document.querySelector('#dialog-content').innerHTML = reviewerDialogView(session);
      }
    } else {
      const region = document.querySelector('#reviewer-receipts');
      if (region)
        region.innerHTML = reviewerReceiptsView(session).replace(
          /^<div id="reviewer-receipts">|<\/div>$/g,
          '',
        );
    }
  } catch (error) {
    if (!reviewerSessionIsCurrent(session)) return;
    const region = document.querySelector('#reviewer-receipts');
    if (region)
      region.innerHTML = `<p class="callout error">Reviewer trust could not be checked: ${esc(error.message)}</p>`;
  }
}

function reviewerSessionIsCurrent(session) {
  return (
    model.independentReview === session &&
    viewIsCurrent(session.view) &&
    dialogRevision === session.revision
  );
}

async function updateReviewerDialog(session) {
  const service = reviewerApi();
  const [profile, receipts, issued] = await Promise.all([
    service.profile(),
    service.receipts(session.context),
    service.issued(session.context),
  ]);
  if (!reviewerSessionIsCurrent(session)) return;
  Object.assign(session, { profile, receipts, issued });
  model.receiptCache[session.context.package_sha256] = receipts;
  document.querySelector('#dialog-content').innerHTML = reviewerDialogView(session);
  document.querySelector('#evidence-dialog').scrollTop = 0;
}

async function openIndependentReview() {
  preserveDrafts();
  if (!packageReviewContext())
    throw new Error('Create a package for the recorded assessment first.');
  const view = currentView();
  showFlowDocument('Independent review', '<p role="status">Checking the current package…</p>');
  const revision = dialogRevision;
  try {
    const run = await api(`runs/${encodeURIComponent(view.runId)}`);
    if (!viewIsCurrent(view) || revision !== dialogRevision) return;
    model.run = run;
    const context = packageReviewContext(run);
    if (!context) {
      if (model.page === 'investigate') renderGuided();
      throw new Error(
        'This package is no longer current or its retained files failed verification. Return to the assessment before requesting review.',
      );
    }
    const session = {
      context,
      view,
      revision,
      profile: null,
      receipts: [],
      issued: [],
      pending: null,
      mode: 'list',
      signDraft: null,
    };
    session.caseTitle = run.dataset_metadata?.label || run.case?.question || run.manifest?.run_id;
    session.caseDecision = caseDecisionStatus(run.latest_review?.review?.decision);
    model.independentReview = session;
    await updateReviewerDialog(session);
  } catch (error) {
    if (error.status === 409 && viewIsCurrent(view)) {
      model.run.verification = { ok: false, issues: [error.message] };
      if (model.page === 'investigate') renderGuided();
      else if (model.page === 'runs') renderRuns();
    }
    if (viewIsCurrent(view) && revision === dialogRevision) {
      model.independentReview = null;
      document.querySelector('#dialog-content').innerHTML =
        `<p class="callout error">${esc(error.message)}</p>`;
      throw error;
    }
  } finally {
    if (notice.className === 'notice busy') notice.hidden = true;
  }
}

async function verifyReviewerContext(session) {
  let run;
  try {
    run = await api(`runs/${encodeURIComponent(session.context.run_id)}`);
  } catch (error) {
    if (error.status === 409 && viewIsCurrent(session.view)) {
      preserveDrafts();
      model.run.verification = { ok: false, issues: [error.message] };
      if (model.page === 'investigate') renderGuided();
      else if (model.page === 'runs') renderRuns();
      if (reviewerSessionIsCurrent(session))
        document.querySelector('#dialog-content').innerHTML =
          `<p class="callout error">${esc(error.message)}</p>`;
      model.independentReview = null;
    }
    throw error;
  }
  if (!reviewerSessionIsCurrent(session))
    throw new Error('Review closed. Open the package again before continuing.');
  const context = packageReviewContext(run);
  if (
    !context ||
    Object.keys(session.context).some((key) => context[key] !== session.context[key])
  ) {
    preserveDrafts();
    model.run = run;
    model.independentReview = null;
    document.querySelector('#dialog-content').innerHTML =
      '<p class="callout error">The case or package changed. Close this dialog and open the current package before reviewing it.</p>';
    if (model.page === 'investigate') renderGuided();
    else if (model.page === 'runs') renderRuns();
    throw new Error('The package changed. No review was signed or accepted.');
  }
  model.run = run;
}

function reviewerTask(message, fn) {
  const session = model.independentReview;
  if (!session || !reviewerSessionIsCurrent(session)) return;
  task(message, async () => {
    try {
      await fn(session);
    } catch (error) {
      if (reviewerSessionIsCurrent(session)) {
        const status = document.querySelector('#reviewer-status');
        if (status) {
          status.textContent = error.message;
          status.className = 'callout error';
          status.hidden = false;
          status.setAttribute('role', 'alert');
        }
      }
      throw error;
    }
  });
}

function downloadReviewJson(value, name) {
  const url = URL.createObjectURL(
    new Blob([`${JSON.stringify(value, null, 2)}\n`], { type: 'application/json' }),
  );
  const link = document.createElement('a');
  link.href = url;
  link.download = name;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

async function inspectSignedReview(file, session) {
  if (file.size > 128 * 1024)
    throw new Error('A signed review receipt must be smaller than 128 KiB.');
  let receipt;
  try {
    receipt = JSON.parse(await file.text());
  } catch {
    throw new Error('Choose a signed review JSON file.');
  }
  const inspected = await reviewerApi().inspect(receipt, session.context);
  if (!reviewerSessionIsCurrent(session)) return;
  session.pending = inspected;
  document.querySelector('#dialog-content').innerHTML = reviewerDialogView(session);
  announce('Signature checked against this package.');
}

async function acceptSignedReview(session, fingerprint) {
  const pending = session.pending;
  if (!pending) throw new Error('Open a signed review first.');
  await verifyReviewerContext(session);
  if (fingerprint) await reviewerApi().trustReviewer(pending.reviewer, fingerprint.trim());
  await reviewerApi().receive(pending.receipt, session.context);
  if (!reviewerSessionIsCurrent(session)) return;
  session.pending = null;
  session.mode = 'list';
  await updateReviewerDialog(session);
  announce('Signed review retained for this package.');
}

function handleReviewerClick(button) {
  const session = model.independentReview;
  if (!session || !reviewerSessionIsCurrent(session) || model.operation) return;
  const action = button.dataset.reviewerAction;
  if (action === 'start-review') {
    session.mode = 'sign';
    reviewerTask('Opening review signing…', async (current) => {
      await updateReviewerDialog(current);
      if (reviewerSessionIsCurrent(current)) notice.hidden = true;
    });
  }
  if (action === 'back') {
    session.pending = null;
    session.mode = 'list';
    reviewerTask('Checking review status…', async (current) => {
      await updateReviewerDialog(current);
      if (reviewerSessionIsCurrent(current)) notice.hidden = true;
    });
  }
  if (action === 'download-key' && session.profile)
    downloadReviewJson(
      session.profile,
      `omphalos-reviewer-${session.profile.key_sha256.slice(0, 12)}.json`,
    );
  if (action === 'download-receipt') {
    const item = [...session.receipts, ...session.issued].find(
      (receipt) => receipt.id === button.dataset.id,
    );
    if (item) downloadReviewJson(item.receipt, `omphalos-review-${item.id.slice(0, 12)}.json`);
  }
  if (action === 'accept-receipt')
    reviewerTask('Retaining the signed review…', (current) => acceptSignedReview(current));
  if (action === 'info')
    document.querySelector('#dialog-content').innerHTML =
      `<p class="mono small word-break">Package SHA-256: ${esc(session.context.package_sha256)}</p><p>Signatures bind the reviewer’s note to the exact package bytes. A trusted key means you confirmed its fingerprint with that person through a separate trusted channel. It does not certify their role, authority, or judgment.</p><p>Your encrypted signing key stays in this browser. Its passphrase is required for every signature and is never saved or sent. Losing the passphrase or clearing browser data requires a new key that reviewers must confirm again. Workspace backups exclude signing keys, trust settings, and receipts; download receipts separately. Download your public key card to share your fingerprint.</p><p>Send packages and signed receipts through your existing secure sharing channel. Copies do not synchronize. A changed package needs a new review. Conflicting reviews remain visible until you resolve them with the reviewers.</p><button type="button" class="text-button" data-reviewer-action="back">← Review tools</button>`;
  if (action === 'trust-settings')
    reviewerTask('Loading trusted reviewer keys…', async (current) => {
      const trusted = await reviewerApi().trustedReviewers();
      if (!reviewerSessionIsCurrent(current)) return;
      document.querySelector('#dialog-content').innerHTML =
        `<h3>Trusted reviewer keys</h3>${trusted.length ? trusted.map((card) => `<section class="flow-section"><strong>${esc(card.name)}</strong><p class="mono small word-break">${esc(card.key_sha256)}</p><button type="button" class="text-button" data-reviewer-action="forget-key" data-id="${esc(card.key_sha256)}">Stop trusting this key</button></section>`).join('') : '<p>No reviewer keys have been confirmed.</p>'}<button type="button" class="text-button" data-reviewer-action="back">← Review tools</button><p id="reviewer-status" role="status" hidden></p>`;
      notice.hidden = true;
    });
  if (action === 'forget-key')
    reviewerTask('Removing reviewer trust…', async (current) => {
      await reviewerApi().forgetReviewer(button.dataset.id);
      await updateReviewerDialog(current);
      announce('Key no longer trusted. Its signed receipts are retained.');
    });
}

function packageDownload(artifact) {
  return artifact?.download_url
    ? `<a class="download-link" href="${esc(artifact.download_url)}" download>Download evidence package ↓</a>`
    : '';
}

function flowPackageView() {
  const run = model.run;
  const review = run?.latest_review?.review;
  const rows = array(review?.findings);
  const ready = flowReviewRecorded(run);
  const pending = Boolean(review && model.reviewDrafts[model.selectedRun] && !ready);
  return `<div class="flow-intro"><h1>Evidence package</h1><p>Original records, results, and the recorded assessment.</p></div>${flowLegacyNote(run)}
    ${run?.dataset_metadata?.synthetic ? `<p>${badge('Synthetic example', 'amber')}</p>` : ''}
    <section class="flow-section"><h2>Recorded assessment</h2>${isCaseReview(review) ? `<h3>${esc(caseDecisionStatus(review.decision))}</h3>${review.summary ? `<p>${esc(review.summary)}</p>` : ''}` : `<p>${esc(review?.summary || 'Record a case decision before creating an evidence package.')}</p>`}<p class="small muted">Reviewer: ${esc(review?.reviewer || 'Not recorded')}</p>
      ${isCaseReview(review) ? `<p class="small muted">Assessment covers ${countLabel(array(review.scope_finding_ids).length, 'observation')}.</p>` : `<div class="review-progress"><span>${rows.filter((row) => row.disposition === 'follow_up').length} follow up</span><span>${rows.filter((row) => row.disposition === 'escalate').length} escalate</span><span>${rows.filter((row) => row.disposition === 'explained').length} explained</span></div>`}
      ${pending ? '<p class="callout">This saved decision has unsaved edits. Record those changes before creating a package.</p>' : ''}
      <div class="actions">${ready && run.latest_export ? '' : `<button type="button" data-action="export" ${ready ? '' : 'disabled'}>Create evidence package →</button>`}<button type="button" class="${pending ? '' : 'secondary'}" data-flow="review-summary">${pending ? 'Finish the case decision' : 'Revise assessment'}</button></div><div id="run-result" class="result-box">${ready && run.latest_export ? packageDownload(run.latest_export) : ''}</div>${independentReviewActions(run)}${run.verification?.ok && run.handoff?.continuation_dataset_id ? `<div class="actions"><button type="button" class="text-button" data-flow="continue-handoff">Continue with these records →</button></div>` : ''}
    </section><section class="flow-section"><h2>Evidence integrity</h2><p class="small muted">Verify the saved files or repeat the analysis against them.</p><div class="actions"><button type="button" class="secondary" data-action="verify">Verify files</button><button type="button" class="secondary" data-action="replay">Replay analysis</button></div></section>`;
}

function flatSections(html) {
  return html
    .replace(
      /<details[^>]*>\s*<summary>([\s\S]*?)<\/summary>/g,
      '<section class="flow-section"><h3>$1</h3>',
    )
    .replace(/<\/details>/g, '</section>');
}

function showFlowDocument(title, content) {
  dialogRevision += 1;
  document.querySelector('#dialog-title').textContent = title;
  document.querySelector('#dialog-content').innerHTML = flatSections(content);
  document.querySelector('#evidence-dialog').showModal();
}

function supportingRecordsAction(run) {
  return run?.verification?.ok && run.dataset_metadata?.counts?.diligence > 0
    ? '<button type="button" class="text-button" data-flow="supporting-records" aria-haspopup="dialog">Supporting records ↗</button>'
    : '';
}

function supportingRecordsView(evidence) {
  const rows = array(evidence.rows);
  if (!rows.length) return '<p class="small muted">No supporting records are retained.</p>';
  return `<section class="supporting-records"><p class="small muted">All retained diligence records, including records that produced no finding.</p>
    <div class="table-wrap"><table><thead><tr><th scope="col">Date</th><th scope="col">Entity</th><th scope="col">Record</th><th scope="col">Supporting context</th><th scope="col">Provenance</th></tr></thead><tbody>${rows
      .map(
        (row) =>
          `<tr><td>${esc(displayDate(row.record?.date) || 'Not supplied')}</td><td>${evidenceTableCell('entity_id', row.record?.entity_id)}</td><td><strong>${esc(row.record?.title)}</strong><small>${esc(row.id)}</small></td><td>${esc(row.record?.text).replaceAll('\n', '<br>')}${row.record?.source_url ? `<p>${sourceLink(row.record.source_url, 'Source link ↗')}</p>` : ''}</td><td><button type="button" class="text-button" data-action="evidence" data-table="diligence" data-id="${esc(row.id)}" data-supporting-offset="${evidence.offset}" aria-label="Open ${esc(row.record?.title || row.id)} with provenance">View ↗</button></td></tr>`,
      )
      .join('')}</tbody></table></div>
    <div class="actions evidence-pagination"><span class="small muted">${evidence.offset + 1}–${evidence.offset + rows.length} of ${evidence.total} records</span><button type="button" class="text-button" data-flow="supporting-records" data-offset="${Math.max(0, evidence.offset - evidence.limit)}" ${evidence.offset === 0 ? 'disabled' : ''}>Previous</button><button type="button" class="text-button" data-flow="supporting-records" data-offset="${evidence.offset + rows.length}" ${evidence.offset + rows.length >= evidence.total ? 'disabled' : ''}>Next</button></div></section>`;
}

async function openSupportingRecords(offset = 0) {
  preserveDrafts();
  if (!model.run?.verification?.ok)
    throw new Error(
      'The retained files must pass verification before supporting records can open.',
    );
  const view = currentView();
  const retainedRun = model.run;
  showFlowDocument(
    'Supporting records',
    '<p class="small muted" role="status">Loading supporting records…</p>',
  );
  const revision = dialogRevision;
  const current = () => viewIsCurrent(view) && revision === dialogRevision;
  try {
    const evidence = await api(
      `runs/${encodeURIComponent(view.runId)}/supporting-records?offset=${offset}&limit=40`,
    );
    if (current()) {
      document.querySelector('#dialog-content').innerHTML = supportingRecordsView(evidence);
      notice.hidden = true;
    }
  } catch (error) {
    if (error.status === 409) {
      retainedRun.verification = { ok: false, issues: [error.message] };
      if (model.run === retainedRun && ['investigate', 'runs'].includes(model.page)) {
        preserveDrafts();
        if (model.page === 'investigate') renderGuided();
        else renderRuns();
      }
    }
    if (current()) {
      document.querySelector('#dialog-content').innerHTML =
        `<div class="callout error"><p>${esc(error.message)}</p>${error.status === 409 ? '' : `<button type="button" class="secondary" data-flow="supporting-records" data-offset="${offset}">Retry records</button>`}</div>`;
      notice.hidden = true;
    }
  } finally {
    if (notice.className === 'notice busy') notice.hidden = true;
  }
}

function flowScreeningBrief(run) {
  if (run.verification?.ok === false)
    return '<p class="callout error">The retained files failed verification. Screening outcomes are unavailable.</p>';
  const coverage = array(run.analysis?.coverage).find(
    (row) => row.investigation_id === 'screening_candidates',
  );
  if (!coverage) return '';
  if (coverage.status !== 'executed')
    return `<section class="screening-brief"><h2>List screening could not be completed</h2><p>${esc(coverage.reason || 'The required reference source was unavailable.')}</p></section>`;
  const candidates = array(run.analysis?.findings).filter(
    (finding) => finding.investigation_id === 'screening_candidates',
  );
  const source = screeningSource(run);
  return `<section class="screening-brief"><span class="object-label">Official list screening</span><h2>${candidates.length ? `${countLabel(candidates.length, 'candidate')} for identity review` : 'No name or identifier candidates returned'}</h2>
    <p>Checked ${countLabel(coverage.records_evaluated, 'record')} against ${source?.record_count !== undefined ? `${countLabel(source.record_count, 'entry', 'entries')} in ` : ''}the retained ${esc(source?.source_id ? sourceTitle(source.source_id) : 'screening list')}.</p>
    ${source?.fetched_at ? `<p class="small muted">List acquired ${esc(displayDate(source.fetched_at))}.</p>` : ''}
    <p class="small muted">This comparison does not confirm identity or establish clearance.</p></section>`;
}

function flowFindingsView() {
  const run = ['review', 'package'].includes(flowState().stage) ? model.run : null;
  const findings = array(run?.analysis?.findings);
  if (!run) return flowNotReady('No results yet');
  if (run.verification?.ok === false)
    return '<div class="flow-intro"><h1>Findings unavailable</h1></div><p class="callout error">The retained files failed verification. These results cannot be relied on or exported.</p><button type="button" class="text-button" data-flow="coverage">Inspect coverage and diagnostics ↗</button>';
  if (Number.isSafeInteger(flowState().findingIndex))
    return findingEvidenceView(run, flowState().findingIndex);
  const rows = findings.map((finding, index) => ({ finding, index }));
  const coverage = array(run.analysis?.coverage);
  const completed = coverage.filter((row) => row.status === 'executed').length;
  const missingChecks = coverage.length - completed;
  const observations = rows.filter(({ finding }) => finding.investigation_id !== 'data_quality');
  const missing = rows.filter(({ finding }) => finding.investigation_id === 'data_quality');
  const indexView = (items) =>
    `<div class="finding-index">${items.map(({ finding, index }) => `<button class="secondary" type="button" data-flow="review-step" data-index="${index}"><span class="object-label">${String(index + 1).padStart(2, '0')}</span><span><strong>${esc(finding.title)}</strong><small>${esc(findingObservation(finding))}</small></span><span aria-hidden="true">↗</span></button>`).join('')}</div>`;
  return `<div class="flow-intro"><h1>${esc(run.dataset_metadata?.label || 'Findings')}</h1><p>${countLabel(completed, 'check')} completed.${missingChecks ? ` ${countLabel(missingChecks, 'check')} could not run.` : ''}</p></div>
    ${run.dataset_metadata?.synthetic ? `<p>${badge('Fictional example / real analysis', 'amber')}</p>` : ''}
    ${flowScreeningBrief(run)}
    ${observations.length ? `<section class="flow-section"><h2>${countLabel(observations.length, 'observation')}</h2>${indexView(observations)}</section>` : ''}
    ${missing.length ? `<section class="flow-section"><div class="panel-heading"><h2>Missing context</h2>${run.dataset_metadata?.counts?.entities === 1 ? '<button type="button" class="text-button" data-flow="research-identity">Research identity →</button>' : ''}</div>${indexView(missing)}</section>` : ''}
    <div class="object-next"><button type="button" data-flow="findings-reviewed">${flowResultsReviewed(run) ? 'Continue to assessment' : 'Mark results reviewed'} →</button>${supportingRecordsAction(run)}<button class="text-button" type="button" data-flow="coverage">Checks and sources ↗</button></div>`;
}

function flowNotReady(description) {
  const flow = flowState();
  const next =
    flow.stage === 'review'
      ? 'Open the case assessment'
      : flow.stage === 'package'
        ? 'Open the recorded assessment'
        : flow.plan
          ? 'Continue with the prepared plan'
          : flow.datasetId
            ? 'Prepare the next step'
            : 'Start with your records';
  const detail =
    flow.stage === 'review'
      ? 'The findings and their evidence are ready.'
      : flow.datasetId
        ? 'Continue with the plan prepared from your records.'
        : 'Add records to prepare the relevant checks.';
  return `<div class="flow-intro"><h1>${esc(description)}</h1><p>${esc(detail)}</p></div><div class="object-next"><button type="button" data-flow="continue">${next} →</button></div>`;
}

function flowFaceView(index) {
  const flow = flowState();
  const run = ['review', 'package'].includes(flow.stage) ? model.run : null;
  if (index === 0) {
    if (flow.stage === 'identity') return flowIdentityView();
    if (!flow.datasetId || flow.stage === 'data') return flowDataView();
    const counts = run?.dataset_metadata?.counts || flowDataset()?.counts;
    const research = run?.identity_research || flowDataset()?.identity_research;
    if (research?.selected_candidate)
      return `<div class="flow-intro"><h1>Records</h1></div>${identityProfile(research.selected_candidate)}<div class="object-next"><button type="button" data-flow="continue">Sources →</button>${supportingRecordsAction(run)}<button type="button" class="text-button" data-flow="identity-info">Source details ↗</button></div>`;
    return `<div class="flow-intro"><h1>Records</h1><p>${esc(countsText(counts))}</p></div><div class="records-inventory">${Object.entries(
      counts || {},
    )
      .map(
        ([key, value]) =>
          `<div><span>${esc(human(key))}</span><strong>${formatNumber(value)}</strong></div>`,
      )
      .join(
        '',
      )}</div><div class="object-next"><button type="button" data-flow="continue">Sources →</button>${supportingRecordsAction(run)}${counts?.entities === 1 ? '<button type="button" class="text-button" data-flow="research-identity">Research identity</button>' : ''}<button type="button" class="secondary" data-flow="back-data">Choose other records</button></div>`;
  }
  if (index === 1) {
    if (run) {
      const snapshotId = run.case?.watchlist_snapshot_id;
      const source = screeningSource(run);
      return `<div class="flow-intro"><h1>Sources</h1>${flowLegacyNote(run)}<p>${source?.source_id ? esc(sourceTitle(source.source_id)) : snapshotId ? `Snapshot ${esc(snapshotId)} is retained in this run.` : 'No screening list was required.'}</p></div>${source?.source_id ? keyValues({ Entries: source.record_count, 'Source timestamp': displayDate(source.source_updated_at), Acquired: displayDate(source.fetched_at) }) : ''}${run.identity_research ? `<section class="flow-section"><h2>Identity research</h2>${identityResearchDetails(run.identity_research)}</section>` : ''}<button type="button" data-flow="continue">Plan →</button>`;
    }
    return `<div class="flow-intro"><h1>Review sources</h1><p>${esc(flowDataset()?.label || flow.datasetId)}</p></div>${flowSourceView(flow.plan)}`;
  }
  if (index === 2) {
    if (run)
      return `<div class="flow-intro"><h1>Executed plan</h1>${flowLegacyNote(run)}<p>${esc(run.case?.question)}</p></div>${flatSections(renderCoverage())}<div class="object-next"><button type="button" data-flow="continue">Findings →</button></div>`;
    return flow.plan || flow.datasetId ? flowPlanView() : flowNotReady('Plan not prepared');
  }
  if (index === 3) return flowFindingsView();
  if (index === 4) return run && flowResultsReviewed(run) ? flowReviewView() : flowFindingsView();
  return run?.latest_review
    ? flowPackageView()
    : flowNotReady('Complete the assessment to create a package');
}

function flowSettingsView() {
  const flow = flowState();
  return `<div class="flow-intro"><h1>Investigation settings</h1><p>Adjust the purpose, assessment date, or reference source.</p></div><div class="field"><label for="flow-goal">Investigation purpose</label><select id="flow-goal">${array(
    model.state.workflow_goals,
  )
    .map(
      (goal) =>
        `<option value="${esc(goal.id)}" ${goal.id === flow.goalId ? 'selected' : ''}>${esc(goal.title)}</option>`,
    )
    .join(
      '',
    )}</select></div><div class="field"><label for="flow-as-of">Assessment date</label><input type="date" id="flow-as-of" value="${esc(flow.asOf)}"></div>${flowSourceView(flow.plan)}<button type="button" data-flow="plan">Prepare updated plan →</button>`;
}

function flowBody() {
  const flow = flowState();
  if (flow.settingsOpen) return flowSettingsView();
  if (flow.inspectionFace !== null && flow.inspectionFace !== undefined)
    return flowFaceView(flow.inspectionFace);
  return {
    goal: flowGoalsView,
    data: flowDataView,
    identity: flowIdentityView,
    plan: () => flowFaceView(flow.cubeFace === 2 ? 2 : 1),
    running: flowPlanView,
    review: () => flowFaceView(flow.cubeFace === 4 ? 4 : 3),
    package: flowPackageView,
  }[flow.stage]();
}

function selectFlowFace(index) {
  if (!flowStageAccess(index)) return;
  preserveDrafts();
  model.navigationVersion += 1;
  const flow = flowState();
  if (flow.autoRunning) flow.autoViewChanged = true;
  flow.cubeFace = index;
  flow.inspectionFace = index;
  flow.surfaceOpen = true;
  flow.settingsOpen = false;
  updateFlowCube();
  const surface = document.querySelector('.object-surface');
  if (surface) {
    surface.hidden = false;
    surface.innerHTML = flowSurfaceContent();
    surface.scrollIntoView({ block: 'nearest' });
    surface.focus({ preventScroll: true });
  }
  loadVisibleFindingEvidence();
  updateDraftIndicator();
}

function measureObjectHeader() {
  const workspace = document.querySelector('.object-workspace');
  const height = document.querySelector('.topbar')?.getBoundingClientRect?.().height;
  if (workspace && height) workspace.style.setProperty('--object-topbar-height', `${height}px`);
}

function flowSurfaceContent() {
  const content = flowBody();
  return content
    ? `<nav class="surface-navigation" aria-label="Investigation overview"><button type="button" class="text-button" data-flow="overview">← Back to the box</button></nav>${content}`
    : '';
}

function renderGuided() {
  const flow = flowState();
  const retainedScene = main.querySelector?.('.box-scene');
  main.innerHTML = `<div class="guided-workspace object-workspace" data-face="${flow.cubeFace}"><div class="object-core">${flowCube()}<header class="object-heading">${flowGuide()}</header></div><div class="object-surface" tabindex="-1" ${flow.surfaceOpen ? '' : 'hidden'}>${flowSurfaceContent()}</div></div>`;
  measureObjectHeader();
  loadVisibleFindingEvidence();
  const placeholder = main.querySelector?.('.box-scene');
  if (retainedScene && cubeMaterial && placeholder) {
    placeholder.replaceWith(retainedScene);
    cubeMaterial.update(boxPanelState(), flow.cubeFace);
  } else {
    cubeMaterial?.destroy();
    cubeMaterial = window.OmphalosBox?.mount(placeholder, {
      faces: boxPanelState(),
      selected: flow.cubeFace,
    });
  }
  if (flow.busyStep) {
    main
      .querySelectorAll(
        '[data-flow="run"], [data-flow="fetch-run"], [data-flow="import"], [data-flow="plan"], [data-flow="fetch"], [data-flow="dataset"], [data-flow="investigate-dataset"], [data-flow="resume"], [data-flow="repreview"], [data-flow="identity-select"], [data-flow="identity-skip"], [data-flow="research-identity"], button[type="submit"], input[type="file"]',
      )
      .forEach((button) => {
        button.disabled = true;
      });
  }
}

async function flowOperation(message, fn, automatic = false) {
  await task(message, async () => {
    const flow = flowState();
    flow.autoRunning = automatic;
    flow.autoViewChanged = false;
    flow.busyStep = message;
    renderGuided();
    try {
      await fn();
    } finally {
      flow.busyStep = '';
      flow.autoRunning = false;
      if (notice.className === 'notice busy') notice.hidden = true;
      if (model.page === 'investigate' && model.flow === flow) {
        preserveDrafts();
        renderGuided();
        if (flow.revealResults) {
          flow.revealResults = false;
          const destination = document.querySelector(
            flow.surfaceOpen ? '.object-surface' : '.object-workspace',
          );
          destination?.scrollIntoView({ block: 'start' });
          if (flow.surfaceOpen) destination?.focus({ preventScroll: true });
          else main.focus({ preventScroll: true });
        }
      }
    }
  });
}

async function prepareFlowPlan() {
  const context = flowContext();
  const input = flowInput();
  const plan = await flowRequest(context, 'workflow/plan', input);
  if (!flowIsCurrent(context)) return false;
  Object.assign(model.flow, {
    settingsOpen: false,
    plan,
    planInputs: input,
    approval: null,
    approvalPlanId: null,
    stage: 'plan',
  });
  if (!model.flow.autoRunning || !model.flow.autoViewChanged)
    Object.assign(model.flow, { cubeFace: 1, inspectionFace: 1, surfaceOpen: true });
  renderGuided();
  if (!model.flow.autoRunning)
    announce('Sources and draft plan prepared. Review the sources to continue.');
  return true;
}

async function chooseFlowDataset(id) {
  invalidateFlow(
    {
      datasetId: id,
      recordsConfirmed: true,
      stage: 'plan',
      preview: null,
      previewStale: false,
      sourceRetry: false,
      identityError: '',
    },
    true,
  );
  if (!model.flow.goalId || model.flow.goalInferred) {
    model.flow.goalInferred = true;
    const counts = flowDataset()?.counts || {};
    model.flow.goalId =
      counts.shipments || counts.payments ? 'transaction_review' : 'counterparty_screening';
  }
  if (flowGoal()?.requires_source && !model.flow.snapshotId) {
    model.flow.snapshotId = suggestedFlowSource()?.snapshot_id || '';
  }
  return prepareFlowPlan();
}

function flowProgress(message, face) {
  const flow = flowState();
  flow.busyStep = message;
  if (!flow.autoRunning || !flow.autoViewChanged) {
    flow.cubeFace = face;
    flow.inspectionFace = null;
  }
  announce(message, 'busy');
  if (model.page === 'investigate') renderGuided();
}

async function investigateFlowDataset(id) {
  const dataset = array(model.state.datasets).find((item) => item.dataset_id === id);
  if (dataset?.intake_method === 'subject_name' && !dataset.identity_research_retained) {
    Object.assign(flowState(), {
      subjectName: dataset.label || '',
      goalId: 'counterparty_screening',
      goalInferred: true,
    });
    await researchFlowIdentity(id);
    return;
  }
  flowProgress('Checking the sources required by these records…', 1);
  if (!(await chooseFlowDataset(id))) return;
  const flow = flowState();
  if (flowGoal()?.requires_source) {
    const source = array(model.state.sources).find((item) => item.snapshot_id === flow.snapshotId);
    const age = Date.now() - Date.parse(source?.fetched_at);
    const recentOfficial =
      source?.ingestion_method === 'official_https' && age >= 0 && age < 24 * 60 * 60 * 1000;
    if (
      !flow.plan?.source_status?.selected ||
      (flow.sourcePolicy === 'automatic' && flow.asOf === dateToday() && !recentOfficial)
    ) {
      flow.sourceRetry = true;
      flowProgress('Downloading the official screening list…', 1);
      await fetchFlowSource();
      return;
    }
  }
  // Preparation stops here. Sources and plan each require an explicit action.
}

async function startFlowSubject(name) {
  const subjectName = String(name || '').trim();
  if (!subjectName) throw new Error('Enter a company or person’s name.');
  invalidateFlow({
    subjectName,
    datasetId: '',
    goalId: 'counterparty_screening',
    goalInferred: true,
    sourcePolicy: 'automatic',
    sourceRetry: false,
    snapshotId: '',
    asOf: dateToday(),
    stage: 'goal',
    preview: null,
    cubeFace: 0,
  });
  const context = flowContext();
  const result = await flowRequest(context, 'workflow/subject', { name: subjectName });
  if (!flowIsCurrent(context) || !(await refreshFlow(context))) return;
  await researchFlowIdentity(result.dataset_id);
}

async function researchFlowIdentity(datasetId = flowState().datasetId) {
  if (!datasetId) throw new Error('Open a retained subject first.');
  invalidateFlow({ datasetId, identityResearch: null, identityError: '', stage: 'identity' }, true);
  flowProgress('Looking up public identity records…', 0);
  const context = flowContext();
  let report;
  try {
    report = await api('workflow/identity-research', { dataset_id: datasetId });
  } catch (error) {
    if (!flowIsCurrent(context)) return;
    const flow = flowState();
    flow.identityError = error.message;
    if (!flow.autoViewChanged) {
      flow.inspectionFace = 0;
      flow.surfaceOpen = true;
      flow.revealResults = true;
    }
    throw error;
  }
  if (!flowIsCurrent(context)) return;
  const flow = flowState();
  flow.identityResearch = report;
  flow.subjectName = report.query;
  if (!flow.autoViewChanged) {
    flow.inspectionFace = 0;
    flow.surfaceOpen = true;
    flow.revealResults = true;
  }
}

async function selectFlowIdentity(candidateId) {
  const flow = flowState();
  const report = flow.identityResearch;
  if (
    !report ||
    report.dataset_id !== flow.datasetId ||
    !array(report.candidates).some((candidate) => candidate.candidate_id === candidateId)
  )
    throw new Error('Choose an identity from the current research.');
  const context = flowContext();
  const result = await flowRequest(context, 'workflow/identity-select', {
    dataset_id: flow.datasetId,
    research_id: report.research_id,
    candidate_id: candidateId,
  });
  if (!flowIsCurrent(context) || !(await refreshFlow(context))) return;
  flow.surfaceOpen = false;
  await investigateFlowDataset(result.dataset_id);
}

async function skipFlowIdentity() {
  const flow = flowState();
  const report = flow.identityResearch;
  if (!flow.datasetId || flow.stage !== 'identity' || report?.dataset_id !== flow.datasetId) return;
  const context = flowContext();
  const result = await flowRequest(context, 'workflow/identity-select', {
    dataset_id: flow.datasetId,
    research_id: report.research_id,
    candidate_id: null,
  });
  if (!flowIsCurrent(context) || !(await refreshFlow(context))) return;
  flow.surfaceOpen = false;
  await investigateFlowDataset(result.dataset_id);
}

function suggestedFlowSource() {
  const timestamp = (value) => {
    const parsed = Date.parse(value);
    return Number.isFinite(parsed) ? parsed : 0;
  };
  return array(model.state.sources)
    .filter(
      (source) => source.source_id === 'csl' && source.snapshot_id && source.status !== 'invalid',
    )
    .sort(
      (left, right) =>
        Number(right.ingestion_method === 'official_https') -
          Number(left.ingestion_method === 'official_https') ||
        timestamp(right.fetched_at) - timestamp(left.fetched_at) ||
        timestamp(right.source_updated_at) - timestamp(left.source_updated_at) ||
        right.snapshot_id.localeCompare(left.snapshot_id),
    )[0];
}

async function previewFlowFiles(form) {
  const inputFiles = [...form.elements.files.files];
  if (inputFiles.length !== 1 || inputFiles[0].size > 20 * 1024 * 1024)
    throw new Error('Choose one counterparty CSV no larger than 20 MiB.');
  invalidateFlow({ preview: null, previewStale: true });
  const context = flowContext();
  const files = await filesPayload(inputFiles);
  if (!flowIsCurrent(context)) return;
  model.flow.files = files;
  const preview = await flowRequest(context, 'workflow/preview', { files });
  if (!flowIsCurrent(context)) return;
  Object.assign(model.flow, { preview, mapping: { ...preview.mapping }, previewStale: false });
  renderGuided();
  announce('Column preview prepared. Review every mapping before confirming the import.');
}

function flowFilesAreLinked(form) {
  const files = [...form.elements.files.files];
  return files.length !== 1 || files[0].name.toLowerCase().endsWith('.json');
}

async function intakeFlowFiles(form) {
  if (flowFilesAreLinked(form)) {
    await importFlowRecords(form);
  } else {
    await previewFlowFiles(form);
  }
}

async function updateFlowPreview() {
  const context = flowContext();
  const preview = await flowRequest(context, 'workflow/preview', {
    files: model.flow.files,
    mapping: model.flow.mapping,
  });
  if (!flowIsCurrent(context)) return;
  Object.assign(model.flow, { preview, mapping: { ...preview.mapping }, previewStale: false });
  renderGuided();
}

async function importFlowPreview() {
  const flow = flowState();
  if (!flow.preview?.can_import || flow.previewStale)
    throw new Error('Update and review the preview before importing.');
  const context = flowContext();
  const result = await flowRequest(context, 'workflow/import', {
    files: flow.files,
    mapping: flow.mapping,
    preview_id: flow.preview.preview_id,
  });
  if (!flowIsCurrent(context) || !(await refreshFlow(context))) return;
  await investigateFlowDataset(result.dataset_id);
}

async function importFlowRecords(form) {
  const context = flowContext();
  const files = await filesPayload(form.elements.files.files);
  if (!flowIsCurrent(context)) return;
  const label =
    files.length === 1
      ? files[0].name
          .replace(/\.(?:json|csv)$/i, '')
          .replace(/[-_]+/g, ' ')
          .trim()
          .slice(0, 200) || 'Imported records'
      : 'Linked records';
  const result = await flowRequest(context, 'datasets/import', { files, label });
  if (!flowIsCurrent(context) || !(await refreshFlow(context))) return;
  await investigateFlowDataset(result.dataset_id);
}

async function fetchFlowSource() {
  const context = flowContext();
  const source = await flowRequest(context, 'sources/fetch', { source_id: 'csl' });
  if (!flowIsCurrent(context) || !(await refreshFlow(context))) return;
  invalidateFlow({ snapshotId: source.snapshot_id, sourceRetry: false }, true);
  await prepareFlowPlan();
}

async function approveFlowSources() {
  const flow = flowState();
  if (
    !flow.recordsConfirmed ||
    !flow.plan ||
    !flow.planInputs ||
    (flowGoal()?.requires_source && !flow.plan.source_status?.selected)
  )
    throw new Error('Select records and prepare the sources before accepting them.');
  if (!flowSourcesAccepted()) {
    const context = flowContext();
    const result = await flowRequest(context, 'workflow/approve', {
      ...flow.planInputs,
      plan_id: flow.plan.plan_id,
      case_id: flow.plan.case.case_id,
      acknowledge_records: true,
      acknowledge_source: true,
    });
    if (!flowIsCurrent(context)) return;
    flow.approval = result.approval;
    flow.approvalPlanId = flow.plan.plan_id;
  }
  Object.assign(flow, { cubeFace: 2, inspectionFace: 2, surfaceOpen: true });
  renderGuided();
  announce('Sources accepted. Review the proposed checks before running.');
}

function reviewFlowFindings() {
  if (!model.run?.verification?.ok) return;
  flowState().resultsReview = { runId: model.selectedRun, run: model.run };
  selectFlowReview(array(model.run.analysis?.findings).length);
}

async function runFlowPlan() {
  const flow = flowState();
  if (!flow.plan?.can_run || !flow.planInputs || !flowSourcesAccepted())
    throw new Error('Accept the sources and review a runnable plan before starting.');
  const context = flowContext();
  const body = {
    ...flow.planInputs,
    plan_id: flow.plan.plan_id,
    case_id: flow.plan.case.case_id,
    approval: flow.approval,
    acknowledge_plan: true,
  };
  const result = await flowRequest(context, 'workflow/run', body);
  if (!flowIsCurrent(context)) return;
  const run = await flowRequest(context, `runs/${encodeURIComponent(result.run_id)}`);
  if (!flowIsCurrent(context) || !(await refreshFlow(context))) return;
  model.selectedRun = result.run_id;
  model.run = run;
  const preserveInspection = flow.autoRunning && flow.autoViewChanged;
  Object.assign(flow, {
    stage: 'review',
    resultsReview: null,
    reviewIndex: 0,
    findingIndex: null,
    ...(preserveInspection ? {} : { cubeFace: 3, inspectionFace: 3, surfaceOpen: true }),
    revealResults: !preserveInspection,
  });
  renderGuided();
  announce(
    `Analysis saved with ${countLabel(array(run.analysis?.findings).length, 'observation')}.`,
  );
}

async function resumeFlowRun(id) {
  const context = flowContext();
  const run = await flowRequest(context, `runs/${encodeURIComponent(id)}`);
  if (!flowIsCurrent(context)) return;
  preserveDrafts();
  model.selectedRun = id;
  model.run = run;
  const reviewed = model.reviewDrafts[id] || run.latest_review?.review || {};
  const recorded = flowReviewRecorded(run);
  const resumeFace =
    run.verification?.ok !== true
      ? 3
      : recorded
        ? 5
        : flowResultsReviewed(run) && reviewed.schema_version
          ? 4
          : 3;
  const findings = array(run.analysis?.findings);
  const checks = array(run.case?.investigations);
  const goalId = checks.some(
    (check) => !['data_quality', 'shared_address', 'screening_candidates'].includes(check),
  )
    ? 'transaction_review'
    : checks.includes('screening_candidates')
      ? 'counterparty_screening'
      : 'data_readiness';
  const firstIncomplete = findings.findIndex(
    (finding) =>
      !reviewRowComplete(
        array(reviewed.findings).find((row) => row.finding_id === finding.finding_id),
      ),
  );
  Object.assign(model.flow, {
    stage: recorded ? 'package' : 'review',
    recordsConfirmed: false,
    approval: null,
    approvalPlanId: null,
    resultsReview: null,
    reviewIndex: firstIncomplete < 0 ? findings.length : firstIncomplete,
    findingIndex: null,
    datasetId: run.handoff?.continuation_dataset_id || run.case?.dataset_id || '',
    subjectName: run.dataset_metadata?.label || '',
    asOf: run.case?.as_of || dateToday(),
    goalId,
    goalInferred: true,
    sourcePolicy: run.case?.watchlist_snapshot_id ? 'selected' : 'automatic',
    sourceRetry: false,
    identityResearch: null,
    identityError: '',
    preview: null,
    previewStale: false,
    files: [],
    mapping: {},
    plan: null,
    planInputs: null,
    settingsOpen: false,
    snapshotId: run.handoff?.continuation_source_id || run.case?.watchlist_snapshot_id || '',
    cubeFace: resumeFace,
    inspectionFace: null,
    surfaceOpen: false,
    revealResults: true,
  });
  renderGuided();
}

function selectFlowReview(index) {
  if (index >= array(model.run?.analysis?.findings).length && !flowResultsReviewed(model.run)) {
    Object.assign(flowState(), {
      cubeFace: 3,
      inspectionFace: 3,
      surfaceOpen: true,
      findingIndex: null,
    });
    renderGuided();
    announce('Review the results and coverage, then mark the results reviewed.');
    return;
  }
  preserveDrafts();
  model.navigationVersion += 1;
  const findings = array(model.run?.analysis?.findings);
  const detail = Number.isSafeInteger(index) && index >= 0 && index < findings.length;
  const legacy = model.reviewDrafts[model.selectedRun]?.schema_version === '2.0';
  Object.assign(model.flow, {
    stage: 'review',
    surfaceOpen: true,
    cubeFace: detail && !legacy ? 3 : 4,
    inspectionFace: detail && !legacy ? 3 : 4,
    findingIndex: detail ? index : null,
    reviewIndex: Math.max(0, Math.min(index, findings.length)),
  });
  if (model.page !== 'investigate') model.runTab = detail ? 'findings' : 'review';
  if (model.page === 'investigate') renderGuided();
  else renderRuns();
  const surface = document.querySelector('.object-surface');
  surface?.scrollIntoView({ block: 'start' });
  surface?.focus({ preventScroll: true });
  if (detail && !legacy) loadFindingEvidence(findings[index]);
}

function updateFlowCube() {
  const flow = flowState();
  const faces = boxPanelState();
  const face = faces[flow.cubeFace];
  const heading = document.querySelector('.object-heading');
  if (heading && flow.stage !== 'goal') heading.innerHTML = flowGuide();
  document.querySelector('.object-workspace')?.setAttribute('data-face', String(flow.cubeFace));
  const title = document.querySelector('.cube-caption strong');
  if (title) title.textContent = `${face.title} / ${face.value}`;
  const detail = document.querySelector('.cube-caption span');
  if (detail) detail.textContent = face.detail;
  document.querySelectorAll('.cube-controls [data-flow="cube"]').forEach((button) => {
    const index = Number(button.dataset.face);
    const item = faces[index];
    button.setAttribute('aria-pressed', String(index === flow.cubeFace));
    button.setAttribute('data-complete', String(item.complete));
    button.setAttribute(
      'aria-description',
      `Step ${index + 1} of 6. ${item.status || 'Not started'}`,
    );
    const status = button.querySelector?.('.stage-status');
    if (status) status.textContent = item.status || '';
    button.disabled = !item.available;
  });
  cubeMaterial?.update(faces, flow.cubeFace);
}

function handleFlowClick(button) {
  const action = button.dataset.flow;
  if (!action) return;
  const flow = flowState();
  if (action === 'cube') selectFlowFace(Number(button.dataset.face));
  if (action === 'open-work') {
    preserveDrafts();
    model.handoff = null;
    showFlowDocument('Open', savedWorkView());
  }
  if (action === 'continue-handoff' && model.run?.verification?.ok && model.run?.handoff) {
    const handoff = model.run.handoff;
    const asOf = model.run.case?.as_of || dateToday();
    preserveDrafts();
    invalidateFlow({
      stage: 'plan',
      datasetId: handoff.continuation_dataset_id,
      asOf,
      snapshotId: handoff.continuation_source_id || '',
      sourcePolicy: handoff.continuation_source_id ? 'selected' : 'automatic',
    });
    flowOperation(
      'Preparing a separate continuation…',
      () => investigateFlowDataset(handoff.continuation_dataset_id),
      true,
    );
  }
  if (action === 'independent-review') task('Opening signed review tools…', openIndependentReview);
  if (action === 'handoff-import') task('Adding the verified case package…', importHandoff);
  if (action === 'handoff-preview' && model.handoff)
    showFlowDocument('Open case package', handoffPreviewView(model.handoff.preview));
  if (action === 'handoff-info')
    showFlowDocument(
      'Received case packages',
      '<p>Verification checks the retained bytes against the package inventory. It does not establish who supplied the package or whether its claims are true.</p><p>The original analysis and recorded assessment are preserved. Further work uses a separate copy of the records and source snapshot. Packages do not synchronize between people or devices.</p><button type="button" class="text-button" data-flow="handoff-preview">← Package preview</button>',
    );
  if (action === 'import-info')
    showFlowDocument(
      'Record formats',
      `<p><strong>Counterparty CSV.</strong> Choose one file up to 20 MiB. omphalOS recognizes columns and values, then shows a preview before importing.</p><p><strong>Linked records.</strong> Choose entity records together with any shipments, payments, ownership, or diligence records. A dataset JSON can contain these tables in one file.</p><p>${esc(storageExplanation())} Invalid rows must be corrected before analysis.</p>${schemaHelp()}`,
    );
  if (action === 'preview-info' && flow.preview) {
    const preview = flow.preview;
    showFlowDocument(
      'About this import preview',
      `<p>Nothing is imported until you choose “Investigate these records.” Every original column is retained; only mapped fields are analyzed. No company identities are merged.</p><p>${countLabel(preview.generated_id_count || 0, 'record')} will receive a local ID tied to this file and its source row. These IDs are not verified business identifiers.</p>${list(preview.warnings)}${array(preview.errors).length ? `<h3>Validation details</h3>${list(preview.errors)}` : ''}`,
    );
  }
  if (action === 'change-files') {
    invalidateFlow({
      stage: 'data',
      surfaceOpen: true,
      cubeFace: 0,
      datasetId: '',
      files: [],
      mapping: {},
      preview: null,
      previewStale: false,
      sourceRetry: false,
      identityError: '',
    });
    renderGuided();
    document.querySelector('#flow-vendor-file')?.focus();
    announce('Choose replacement files. The previous preview was not imported.');
  }
  if (action === 'add-records' || action === 'choose-file') {
    invalidateFlow({
      stage: 'data',
      surfaceOpen: true,
      ...(flow.stage === 'goal' ? { goalId: '', goalInferred: false } : {}),
      cubeFace: 0,
    });
    renderGuided();
    if (action === 'choose-file') {
      const input = document.querySelector('#flow-vendor-file');
      input?.focus({ preventScroll: true });
      input?.click();
    } else {
      const surface = document.querySelector('.object-surface');
      surface?.scrollIntoView({ block: 'start' });
      surface?.focus({ preventScroll: true });
    }
  }
  if (action === 'continue' || action === 'focus-step') {
    preserveDrafts();
    flow.surfaceOpen = true;
    const current = flow.inspectionFace ?? flow.cubeFace;
    let next = action === 'continue' ? flowNextStage() : current;
    if (!flowStageAccess(next))
      next = flowStageAccess(4)
        ? 4
        : flowStageAccess(3)
          ? 3
          : flowStageAccess(2)
            ? 2
            : flowStageAccess(1)
              ? 1
              : 0;
    if (next !== current) {
      model.navigationVersion += 1;
      flow.findingIndex = null;
    }
    if (flow.autoRunning) flow.autoViewChanged = true;
    flow.cubeFace = next;
    flow.inspectionFace = next;
    if (['review', 'package'].includes(flow.stage)) flow.stage = next === 5 ? 'package' : 'review';
    flow.settingsOpen = false;
    if (flow.stage === 'goal') flow.stage = 'data';
    renderGuided();
    if (action === 'focus-step' || action === 'continue') {
      const surface = document.querySelector('.object-surface');
      surface?.scrollIntoView({ block: 'start' });
      surface?.focus({ preventScroll: true });
    }
  }
  if (action === 'screening-info')
    showFlowDocument(
      'Name screening',
      `<p>The entered name is sent to GLEIF and Wikidata to find public identity records. Choose a profile to use its sourced details, or continue with the name alone.</p><p>The official U.S. screening list is downloaded separately and compared locally. Your case records are not sent with that download.</p>${model.state?.storage ? `<p>${esc(storageExplanation())}</p>` : ''}`,
    );
  if (action === 'identity-info') {
    const research =
      flow.stage === 'identity'
        ? flow.identityResearch
        : ['review', 'package'].includes(flow.stage)
          ? model.run?.identity_research
          : flowDataset()?.identity_research;
    showFlowDocument(
      'Identity sources',
      `<p>GLEIF provides legal-entity reference records. Wikidata is a community-maintained directory; its claims and cited links are retained as attribution, not independently verified website content.</p><p>Choosing a profile associates it with this case. It does not resolve a screening candidate. Existing supplied values are preserved when a source disagrees.</p>${identityResearchDetails(research)}`,
    );
  }
  if (action === 'research-identity')
    flowOperation('Looking up public identity records…', () => researchFlowIdentity(), true);
  if (action === 'identity-select')
    flowOperation(
      'Retaining the selected identity and preparing checks…',
      () => selectFlowIdentity(button.dataset.id),
      true,
    );
  if (action === 'identity-skip')
    flowOperation('Preparing sources for the entered name…', skipFlowIdentity, true);
  if (action === 'source-info') {
    const source = flow.plan?.source_status || {};
    showFlowDocument(
      'Sources and scope',
      `<p>The selected records and this source snapshot will be retained together when you run the plan. Accepting sources records your choice; it does not verify identity or approve a transaction.</p><p>${esc(acquisitionNote(source))} ${esc(source.date_note || '')} ${esc(source.freshness_note || '')}</p>${list(source.warnings)}${flowGoal()?.requires_source ? '<p>The Consolidated Screening List is a screening aid. Apparent matches require identity checks and review of the underlying official list and restrictions.</p><p><a href="https://www.trade.gov/consolidated-screening-list" target="_blank" rel="noopener noreferrer">Official CSL guidance ↗</a></p>' : ''}${flowDataset()?.identity_research ? identityResearchDetails(flowDataset().identity_research) : ''}`,
    );
  }
  if (action === 'plan-info')
    showFlowDocument('Plan methods and limitations', list(flow.plan?.notes));
  if (action === 'approve-sources')
    flowOperation('Recording source acceptance…', approveFlowSources);
  if (action === 'findings-reviewed') reviewFlowFindings();
  if (action === 'coverage') showFlowDocument('Coverage and missing evidence', renderCoverage());
  if (action === 'supporting-records')
    task('Loading supporting records…', () =>
      openSupportingRecords(Number(button.dataset.offset || 0)),
    );
  if (action === 'check-info') {
    const check = [
      ...array(flow.plan?.selected_checks),
      ...array(flow.plan?.unavailable_checks),
    ].find((item) => item.investigation_id === button.dataset.check);
    if (check)
      showFlowDocument(
        check.title || investigationTitle(check.investigation_id),
        `<p>${esc(check.description || check.reason || '')}</p><h3>Parameters</h3>${Object.keys(check.parameters || {}).length ? keyValues(check.parameters) : '<p>No configurable parameters.</p>'}<h3>Limitations</h3>${list(check.limitations)}`,
      );
  }
  if (action === 'plan-settings') {
    preserveDrafts();
    model.navigationVersion += 1;
    flow.inspectionFace = null;
    flow.settingsOpen = true;
    flow.surfaceOpen = true;
    renderGuided();
  }
  if (action === 'goal') {
    invalidateFlow({
      goalId: button.dataset.goal,
      surfaceOpen: true,
      goalInferred: false,
      stage: 'data',
      cubeFace: 0,
    });
    renderGuided();
  }
  if (action === 'back-goal' || action === 'back-data') {
    invalidateFlow({
      stage: action === 'back-goal' ? 'goal' : 'data',
      surfaceOpen: action !== 'back-goal',
      cubeFace: 0,
      preview: null,
    });
    if (action === 'back-goal' && !model.operation) notice.hidden = true;
    renderGuided();
    if (action === 'back-goal') document.querySelector('#flow-subject-name')?.focus();
  }
  if (action === 'overview') {
    preserveDrafts();
    model.navigationVersion += 1;
    flow.surfaceOpen = false;
    renderGuided();
    document.querySelector('.topbar')?.scrollIntoView({ block: 'start' });
    const target =
      document.querySelector(
        '.object-heading [data-flow="focus-step"]:not(:disabled), .object-heading #flow-subject-name',
      ) ||
      document.querySelector(
        '.object-heading button[data-flow]:not(:disabled):not([aria-haspopup="dialog"]):not([data-flow="restart"])',
      ) ||
      document.querySelector('.cube-controls button[aria-pressed="true"]:not(:disabled)') ||
      main;
    target.focus({ preventScroll: true });
  }
  if (action === 'restart') {
    preserveDrafts();
    model.navigationVersion += 1;
    model.flow = newFlow();
    notice.hidden = true;
    renderGuided();
    document.querySelector('#flow-subject-name')?.focus();
  }
  if (action === 'dataset')
    flowOperation('Preparing checks…', () => chooseFlowDataset(button.dataset.id));
  if (action === 'investigate-dataset')
    flowOperation(
      'Preparing the retained records…',
      () => investigateFlowDataset(button.dataset.id),
      true,
    );
  if (action === 'plan') flowOperation('Preparing the plan…', prepareFlowPlan);
  if (action === 'repreview')
    flowOperation('Validating the revised column mapping…', updateFlowPreview);
  if (action === 'import')
    flowOperation('Importing records and preparing checks…', importFlowPreview, true);
  if (action === 'fetch-run') flowOperation('Downloading the official list…', fetchFlowSource);
  if (action === 'fetch')
    flowOperation('Downloading the official CSL. No case data is sent…', fetchFlowSource);
  if (action === 'run') flowOperation('Running checks…', runFlowPlan);
  if (action === 'resume')
    flowOperation('Verifying retained records…', () => resumeFlowRun(button.dataset.id));
  if (action === 'summary-adopt' || action === 'summary-edit') {
    const form = document.querySelector('#review-form');
    if (!form || form.dataset.saving === 'true') return;
    preserveDrafts();
    const draft = model.reviewDrafts[model.selectedRun] || model.run?.latest_review?.review || {};
    const ui = guidedReviewUi('__summary');
    const complete = array(model.run?.analysis?.findings).every((finding) =>
      reviewRowComplete(array(draft.findings).find((row) => row.finding_id === finding.finding_id)),
    );
    if (action === 'summary-adopt') {
      if (!complete || (draft.summary && !flowSummaryNeedsUpdate(draft))) return;
      draft.summary = preparedReviewSummary(model.run, draft);
      ui.preparedSummary = draft.summary;
      ui.editing.summary = false;
    } else {
      ui.editing.summary = !ui.editing.summary;
      if (ui.editing.summary && !draft.summary && complete) {
        draft.summary = preparedReviewSummary(model.run, draft);
        ui.preparedSummary = draft.summary;
      }
    }
    model.reviewDrafts[model.selectedRun] = draft;
    model.navigationVersion += 1;
    renderGuided();
    updateDraftIndicator();
    if (ui.editing.summary)
      document.querySelector('#review-summary')?.focus({ preventScroll: true });
  }
  if (action === 'review-step') selectFlowReview(Number(button.dataset.index));
  if (action === 'finding-list') {
    preserveDrafts();
    model.navigationVersion += 1;
    flow.findingIndex = null;
    flow.cubeFace = 3;
    flow.inspectionFace = 3;
    flow.surfaceOpen = true;
    if (model.page === 'investigate') {
      renderGuided();
      const surface = document.querySelector('.object-surface');
      surface?.scrollIntoView({ block: 'nearest' });
      surface?.focus({ preventScroll: true });
    } else {
      model.runTab = 'findings';
      renderRuns();
      main.focus({ preventScroll: true });
    }
  }
  if (action === 'finding-records') {
    const finding = array(model.run?.analysis?.findings).find(
      (item) => item.finding_id === button.dataset.id,
    );
    if (finding) loadFindingEvidence(finding, Number(button.dataset.offset || 0));
  }
  if (action === 'review-summary') selectFlowReview(array(model.run?.analysis?.findings).length);
}

main.addEventListener('submit', (event) => {
  event.preventDefault();
  const form = event.target;
  const action = event.submitter?.value;
  if (form.id === 'flow-subject-form') {
    if (model.operation) return;
    const name = String(new FormData(form).get('name') || '');
    flowOperation('Opening the investigation…', () => startFlowSubject(name), true);
  }
  if (form.id === 'flow-upload-form')
    flowOperation('Reading the records…', () => intakeFlowFiles(form), flowFilesAreLinked(form));
  if (form.id === 'flow-records-form')
    flowOperation(
      'Validating linked records and preparing the investigation…',
      () => importFlowRecords(form),
      true,
    );
  if (form.id === 'dataset-form') task('Validating uploaded records…', () => submitDataset(form));
  if (form.id === 'source-form')
    task(
      action === 'import'
        ? 'Validating the source snapshot…'
        : 'Downloading the official public list. No case data is being sent…',
      () => submitSource(form, action),
    );
  if (form.id === 'case-form')
    task(
      action === 'run'
        ? 'Saving the case and running selected investigations…'
        : 'Saving the case…',
      () => submitCase(form, action),
    );
  if (form.id === 'review-form')
    task('Checking and saving the complete review…', () => submitReview(form));
});

function captureEditedForm(event) {
  if (event.target.id === 'flow-subject-name') flowState().subjectName = event.target.value;
  const review = event.target.closest('#review-form');
  if (review) {
    review.dataset.dirty = 'true';
    saveReviewDraft();
  }
  const definition = event.target.closest('#case-form');
  if (definition) {
    definition.dataset.dirty = 'true';
    saveCaseDraft();
  }
}

main.addEventListener('input', captureEditedForm);
main.addEventListener('change', (event) => {
  if (model.operation && ['flow-vendor-file', 'flow-record-files'].includes(event.target.id)) {
    announce(
      'The current file is still being read. Choose another file after it finishes.',
      'busy',
    );
    return;
  }
  captureEditedForm(event);
  if (event.target.dataset.mapping !== undefined) {
    invalidateFlow({ previewStale: true });
    model.flow.mapping = Object.fromEntries([
      ...Object.entries(model.flow.mapping).filter(([key]) => key !== event.target.dataset.mapping),
      [event.target.dataset.mapping, event.target.value || null],
    ]);
    renderGuided();
    if (/^mapping-\d+$/.test(event.target.id))
      document.querySelector(`#${event.target.id}`)?.focus({ preventScroll: true });
  }
  if (event.target.id === 'flow-vendor-file') {
    invalidateFlow({ preview: null, previewStale: true, files: [], mapping: {} });
    const form = event.target.closest('form');
    if (event.target.files?.length)
      flowOperation('Reading the records…', () => intakeFlowFiles(form), flowFilesAreLinked(form));
  }
  if (event.target.id === 'flow-record-files' && event.target.files?.length) {
    const form = event.target.closest('form');
    flowOperation(
      'Validating linked records and preparing the investigation…',
      () => importFlowRecords(form),
      true,
    );
  }
  if (event.target.id === 'flow-goal') {
    invalidateFlow({ goalId: event.target.value, goalInferred: false, stage: 'plan' });
    if (flowGoal()?.requires_source && !flowState().snapshotId)
      flowState().snapshotId = suggestedFlowSource()?.snapshot_id || '';
    flowOperation('Preparing the checks for this purpose…', prepareFlowPlan);
  }
  if (event.target.id === 'flow-as-of' || event.target.id === 'flow-source') {
    invalidateFlow(
      event.target.id === 'flow-as-of'
        ? { asOf: event.target.value, settingsOpen: flowState().settingsOpen }
        : {
            snapshotId: event.target.value,
            sourcePolicy: 'selected',
            settingsOpen: flowState().settingsOpen,
          },
    );
    renderGuided();
  }
  if (event.target.id === 'source-id') renderSourceDescription();
  if (event.target.name === 'investigation') {
    const panel = [...document.querySelectorAll('[data-parameters]')].find(
      (item) => item.dataset.parameters === event.target.value,
    );
    if (panel) {
      panel.hidden = !event.target.checked;
      panel.querySelectorAll('input').forEach((input) => {
        input.disabled = !event.target.checked;
        input.required = event.target.checked && input.dataset.required === 'true';
      });
      const required = [...panel.querySelectorAll('input')].some(
        (input) => input.required && !input.value,
      );
      if (required) panel.closest('details').open = true;
    }
    if (event.target.value === 'screening_candidates') {
      document.querySelector('#screening-snapshot-field').hidden = !event.target.checked;
    }
    captureEditedForm(event);
  }
});

async function checkRun(action) {
  const view = currentView();
  const result = await api(`runs/${encodeURIComponent(view.runId)}/${action}`, {});
  const run = await api(`runs/${encodeURIComponent(view.runId)}`);
  if (viewIsCurrent(view)) {
    model.run = run;
    if (model.page === 'investigate') renderGuided();
    else renderRuns();
    const panel = document.querySelector('#run-result');
    const download =
      flowReviewRecorded(run) && run.latest_export ? packageDownload(run.latest_export) : '';
    if (panel)
      panel.innerHTML =
        download +
        (model.page === 'investigate'
          ? integrityResultView(action, result)
          : `<details open><summary>${action === 'verify' ? 'Verification result' : 'Replay result'}</summary><pre>${json(result)}</pre></details>`);
  }
  announce(
    `${action === 'verify' ? 'Verification' : 'Replay'} ${result.ok === true ? 'passed' : 'did not pass'}.${viewIsCurrent(view) ? '' : ' Reopen the investigation for details.'}`,
    result.ok === true ? 'success' : 'error',
  );
}

function integrityResultView(action, result) {
  const verify = action === 'verify';
  const issues = [...new Set([...array(result.issues), ...array(result.verification?.issues)])];
  const summary =
    result.ok === true
      ? verify
        ? 'The retained files match their recorded checksums.'
        : 'Findings and coverage reproduced from the retained records.'
      : verify
        ? 'The retained files did not pass verification.'
        : 'Replay did not pass.';
  const checked = result.files_checked ?? result.verification?.files_checked;
  return `<section class="flow-section"><h3>${verify ? 'Verification result' : 'Replay result'}</h3><p${result.ok === true ? '' : ' class="callout error"'}>${summary}</p>${Number.isInteger(checked) ? `<p class="small muted">${countLabel(checked, 'file')} checked.</p>` : ''}${list(issues)}</section>`;
}

async function exportRun() {
  preserveDrafts();
  if (!flowReviewRecorded(model.run))
    throw new Error(
      model.reviewDrafts[model.selectedRun]
        ? 'Save the edited case decision before creating its evidence package.'
        : 'A verified run and recorded case decision are required before creating a package.',
    );
  const view = currentView();
  const result = await api(`runs/${encodeURIComponent(view.runId)}/export`, {});
  const run = await api(`runs/${encodeURIComponent(view.runId)}`);
  if (viewIsCurrent(view)) {
    model.run = run;
    if (model.page === 'investigate') renderGuided();
    if (
      !flowReviewRecorded(run) ||
      run.latest_export?.name !== result.name ||
      run.latest_export?.download_url !== result.download_url
    ) {
      const message = model.reviewDrafts[view.runId]
        ? 'The package contains the previously recorded decision. Save the current edits before creating their package.'
        : 'The investigation changed while the package was being created. Check its current assessment and verification before exporting again.';
      const panel = document.querySelector('#run-result');
      if (panel) panel.innerHTML = `<p class="small muted">${esc(message)}</p>`;
      announce(message, 'warning');
      return;
    }
    document.querySelector('#run-result').innerHTML = `
      ${packageDownload(result)}
      <details><summary>Package details</summary><p class="small">${esc(result.name)}</p><p class="mono small word-break">SHA-256: ${esc(result.sha256 || '')}</p></details>`;
    if (model.page === 'investigate') {
      const panel = document.querySelector('#run-result');
      panel.innerHTML = flatSections(panel.innerHTML);
    }
  }
  announce(
    viewIsCurrent(view)
      ? 'Evidence package created.'
      : 'Evidence package created and retained with its investigation.',
  );
}

async function inspectEvidence(button, official = false) {
  preserveDrafts();
  const revision = ++dialogRevision;
  const view = currentView();
  const retainedRun = model.run;
  const id = button.dataset.id;
  const query = official
    ? `source-evidence?id=${encodeURIComponent(id)}`
    : `evidence?table=${encodeURIComponent(button.dataset.table)}&id=${encodeURIComponent(id)}`;
  let evidence;
  try {
    evidence = await api(`runs/${encodeURIComponent(view.runId)}/${query}`);
  } catch (error) {
    if (error.status === 409) {
      retainedRun.verification = { ok: false, issues: [error.message] };
      if (model.run === retainedRun && ['investigate', 'runs'].includes(model.page)) {
        preserveDrafts();
        if (model.page === 'investigate') renderGuided();
        else renderRuns();
      }
      if (viewIsCurrent(view) && revision === dialogRevision)
        showFlowDocument(
          'Evidence unavailable',
          `<p class="callout error">${esc(error.message)}</p>`,
        );
    }
    throw error;
  }
  if (!viewIsCurrent(view) || revision !== dialogRevision) {
    if (notice.className === 'notice busy') notice.hidden = true;
    return;
  }
  document.querySelector('#dialog-title').textContent = official
    ? evidence.record.name || `Official source / ${id}`
    : `${human(evidence.table)} / ${id}`;
  if (official) {
    document.querySelector('#dialog-content').innerHTML = `
      <p class="small">${badge(evidence.metadata.ingestion_method === 'manual_import' ? 'Manual import' : evidence.metadata.ingestion_method === 'official_https' ? 'Official HTTPS download' : 'Acquisition unknown')}</p><p class="small muted">${esc(acquisitionNote(evidence.metadata))}</p>
      <p class="section-subtitle">This retained listing supports identity and restriction review. It is not a determination about the imported entity.</p>
      ${keyValues({ 'Underlying list': evidence.record.list_name, 'Listed name': evidence.record.name, 'Entity type': evidence.record.entity_type, Countries: evidence.record.countries, Identifiers: evidence.record.identifiers, 'Listing start': evidence.record.start_date, 'Listing end': evidence.record.end_date, 'Source timestamp': displayDate(evidence.metadata.source_updated_at) })}
      <details><summary>Complete source record</summary><pre>${json(evidence.record)}</pre></details>
      <p class="small muted">${esc(evidence.metadata.date_note || 'Source timestamps may describe publication or aggregation.')}</p>
      <details><summary>Snapshot provenance</summary><pre>${json(evidence.metadata)}</pre></details>
      <p class="small muted">Snapshot: <code>${esc(evidence.snapshot_id)}</code>. The original source content is retained in the run.</p>`;
  } else {
    document.querySelector('#dialog-content').innerHTML = `
      ${evidence.synthetic ? `<p class="small">${badge('Synthetic record', 'amber')}</p>` : ''}
      ${keyValues(Object.fromEntries(Object.entries(evidence.record).map(([key, value]) => [human(key), value])))}
      ${evidence.identity_research ? `<h3>Public identity sources</h3>${identityResearchDetails(evidence.identity_research)}` : ''}
      <h3 class="stack-gap">Original provenance</h3>
      ${evidence.origin ? `<p class="small">File <code>${esc(evidence.origin.source_file)}</code>, source row ${esc(evidence.origin.source_row)}.</p>` : '<p class="small muted">Per-row provenance was not recorded.</p>'}
      <details><summary>Original file hashes</summary><pre>${json(evidence.source_files)}</pre></details>
      <p class="small muted">This record is frozen in the run, rather than read from a changing dataset.</p>`;
  }
  if (model.page === 'investigate') {
    const panel = document.querySelector('#dialog-content');
    panel.innerHTML = flatSections(panel.innerHTML);
  }
  if (button.dataset.supportingOffset !== undefined) {
    const panel = document.querySelector('#dialog-content');
    panel.innerHTML = `<button type="button" class="text-button" data-flow="supporting-records" data-offset="${esc(button.dataset.supportingOffset)}">← Supporting records</button>${panel.innerHTML}`;
  }
  document.querySelector('#evidence-dialog').showModal();
  notice.hidden = true;
}

function selectRunTab(tab) {
  preserveDrafts();
  model.navigationVersion += 1;
  model.runTab = tab;
  renderRuns();
  document.querySelector(`#tab-${tab}`)?.focus();
}

main.addEventListener('click', (event) => {
  const button = event.target.closest('button') || event.target.closest('[data-flow="cube"]');
  if (!button || button.disabled) return;
  handleFlowClick(button);
  handleGuidedReviewClick(button);
  const { action, id } = button.dataset;
  if (button.id === 'new-case') {
    if (model.caseDirty && !window.confirm('Discard unsaved case changes and start a new case?'))
      return;
    model.navigationVersion += 1;
    model.caseEditorOpen = true;
    model.caseDraft = null;
    model.caseDirty = false;
    updateDraftIndicator();
    renderCases();
    document.querySelector('#case-editor')?.scrollIntoView({ block: 'start' });
    document.querySelector('#case-id')?.focus();
  }
  if (action === 'suggest-questions') {
    const form = document.querySelector('#review-form');
    form.dataset.dirty = 'true';
    saveReviewDraft();
    const finding = array(model.run.analysis?.findings).find((item) => item.finding_id === id);
    const row = model.reviewDrafts[model.selectedRun]?.findings?.find(
      (item) => item.finding_id === id,
    );
    if (finding && row) {
      ['unknowns', 'alternatives', 'falsifiers'].forEach((key) => {
        if (!array(row[key]).length) row[key] = [...array(finding[key])];
      });
      if (model.page === 'investigate') renderGuided();
      else renderRuns();
      announce(
        'Suggested questions filled empty uncertainty fields. Edit them for this case before saving.',
      );
    }
  }
  if (action === 'open-disclosure') {
    const disclosure = document.getElementById(button.dataset.target);
    disclosure.open = true;
    disclosure.scrollIntoView({ block: 'start' });
    disclosure.querySelector('input,select')?.focus({ preventScroll: true });
  }
  if (
    action === 'load-case' &&
    (!model.caseDirty || window.confirm('Discard unsaved case changes and open another case?'))
  )
    task('Loading the case…', async () => {
      const view = currentView();
      const definition = await api(`cases/${encodeURIComponent(id)}`);
      if (!viewIsCurrent(view)) return;
      preserveDrafts();
      model.caseDraft = definition;
      model.caseDirty = false;
      model.page = 'cases';
      if (location.hash !== '#cases') location.hash = 'cases';
      render();
      updateDraftIndicator();
      document.querySelector('#case-editor')?.scrollIntoView({ block: 'start' });
      document.querySelector('#case-question')?.focus();
      announce('Case loaded. Existing runs retain their original definition.');
    });
  if (action === 'open-run') {
    preserveDrafts();
    task('Loading the run and checking retained files…', async () => {
      if (await openRun(id))
        announce('Run loaded. File integrity, coverage, and review status are shown separately.');
    });
  }
  if (action === 'run-tab') selectRunTab(button.dataset.tab);
  if (action === 'change-page') {
    preserveDrafts();
    model.navigationVersion += 1;
    model[button.dataset.kind === 'review' ? 'reviewPage' : 'findingPage'] = Number(
      button.dataset.page,
    );
    renderRuns();
    document.querySelector('#run-tab-content').scrollIntoView({ block: 'start' });
    document
      .querySelector('#run-tab-content button:not(:disabled), #run-tab-content input')
      ?.focus({ preventScroll: true });
  }
  if (action === 'more-records') {
    preserveDrafts();
    model.referenceLimits[id] = (model.referenceLimits[id] || 40) + 40;
    if (model.page === 'investigate') renderGuided();
    else renderRuns();
  }
  if (action === 'next-unreviewed') {
    saveReviewDraft();
    const rows =
      model.reviewDrafts[model.selectedRun]?.findings ||
      model.run.latest_review?.review?.findings ||
      [];
    const index = model.run.analysis.findings.findIndex(
      (finding) => !reviewRowComplete(rows.find((row) => row.finding_id === finding.finding_id)),
    );
    if (index !== -1) {
      model.reviewPage = Math.floor(index / PAGE_SIZE);
      renderRuns();
      document.querySelector(`#disposition-${index}`)?.focus();
    }
  }
  if (action === 'verify' || action === 'replay')
    task(
      action === 'verify'
        ? 'Checking the retained file inventory…'
        : 'Recomputing the retained case and comparing results…',
      () => checkRun(action),
    );
  if (action === 'export')
    task('Checking the run and review, then creating the package…', exportRun);
  if (action === 'evidence' || action === 'source-evidence')
    task('Loading the cited evidence from the verified run…', () =>
      inspectEvidence(button, action === 'source-evidence'),
    );
});

main.addEventListener('keydown', (event) => {
  if (
    event.target.dataset.flow === 'cube' &&
    ['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)
  ) {
    event.preventDefault();
    const available = [0, 1, 2, 3, 4, 5].filter(flowStageAccess);
    const current = available.indexOf(Number(event.target.dataset.face));
    const offset = event.key === 'ArrowRight' ? 1 : -1;
    const next =
      event.key === 'Home'
        ? available[0]
        : event.key === 'End'
          ? available.at(-1)
          : available[Math.max(0, Math.min(available.length - 1, current + offset))];
    selectFlowFace(next);
    document.querySelector(`.cube-controls [data-face="${next}"]`)?.focus();
    return;
  }
  if (
    event.target.getAttribute('role') !== 'tab' ||
    !['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)
  )
    return;
  const tabs = ['findings', 'coverage', 'review', 'context'];
  const index = tabs.indexOf(model.runTab);
  const next =
    event.key === 'Home'
      ? 0
      : event.key === 'End'
        ? tabs.length - 1
        : (index + (event.key === 'ArrowRight' ? 1 : -1) + tabs.length) % tabs.length;
  event.preventDefault();
  selectRunTab(tabs[next]);
});

// Skip navigation changes focus only. It never enters the hash router.
document.querySelector('.skip-link').addEventListener('click', (event) => {
  event.preventDefault();
  main.focus();
});
document.querySelector('#close-dialog').addEventListener('click', () => {
  dialogRevision += 1;
  document.querySelector('#evidence-dialog').close();
});
document.querySelector('#evidence-dialog').addEventListener('close', () => {
  dialogRevision += 1;
});
document.querySelector('#evidence-dialog').addEventListener('click', (event) => {
  const supporting = event.target.closest('button');
  if (supporting?.dataset.reviewerAction) {
    if (!supporting.disabled) handleReviewerClick(supporting);
    return;
  }
  if (['handoff-import', 'handoff-info', 'handoff-preview'].includes(supporting?.dataset.flow)) {
    if (!supporting.disabled && !model.operation) handleFlowClick(supporting);
    return;
  }
  if (supporting?.dataset.flow === 'supporting-records') {
    if (!supporting.disabled && !model.operation) handleFlowClick(supporting);
    return;
  }
  if (
    supporting?.dataset.action === 'evidence' &&
    supporting.dataset.supportingOffset !== undefined
  ) {
    if (!supporting.disabled)
      task('Loading the retained supporting record…', () => inspectEvidence(supporting));
    return;
  }
  const button = event.target.closest('.saved-work button[data-flow]');
  if (!button || model.operation) return;
  document.querySelector('#evidence-dialog').close();
  handleFlowClick(button);
});
document.querySelector('#evidence-dialog').addEventListener('change', (event) => {
  const input = event.target;
  if (input.dataset.reviewerFile !== undefined && input.files?.length) {
    const receipt = input.files[0];
    input.value = '';
    reviewerTask('Checking the signed review…', (session) => inspectSignedReview(receipt, session));
    return;
  }
  if (input.dataset.handoffFile === undefined || !input.files?.length) return;
  const file = input.files[0];
  input.value = '';
  if (!model.operation) task('Checking the received case package…', () => inspectHandoff(file));
});
document.querySelector('#evidence-dialog').addEventListener('input', (event) => {
  const session = model.independentReview;
  if (!session || !reviewerSessionIsCurrent(session) || session.mode !== 'sign') return;
  const field = { 'reviewer-decision': 'decision', 'reviewer-note': 'note' }[event.target.id];
  if (!field) return;
  session.signDraft ||= {};
  session.signDraft[field] = event.target.value;
});
document.querySelector('#evidence-dialog').addEventListener('submit', (event) => {
  const form = event.target;
  if (!['reviewer-profile-form', 'reviewer-sign-form', 'reviewer-trust-form'].includes(form.id))
    return;
  event.preventDefault();
  if (
    ['reviewer-profile-form', 'reviewer-sign-form'].includes(form.id) &&
    model.independentReview?.mode !== 'sign'
  )
    return;
  const values = new FormData(form);
  const passphrase = String(values.get('passphrase') || '');
  const confirmation = String(values.get('confirmation') || '');
  for (const input of form.querySelectorAll?.('input[type="password"]') || []) input.value = '';
  if (form.id === 'reviewer-profile-form')
    reviewerTask('Creating your signing key…', async (session) => {
      if (passphrase !== confirmation)
        throw new Error('The passphrases do not match. Enter them again.');
      await reviewerApi().createProfile(String(values.get('name') || '').trim(), passphrase);
      session.mode = 'sign';
      await updateReviewerDialog(session);
      announce('Signing key created in this browser.');
    });
  if (form.id === 'reviewer-sign-form')
    reviewerTask('Signing this package review…', async (session) => {
      await verifyReviewerContext(session);
      const receipt = await reviewerApi().sign(
        session.context,
        values.get('decision'),
        String(values.get('note') || '').trim(),
        passphrase,
      );
      session.mode = 'list';
      session.signDraft = null;
      await updateReviewerDialog(session);
      if (reviewerSessionIsCurrent(session)) {
        const issued = session.issued.find((item) => item.receipt.signature === receipt.signature);
        const status = document.querySelector('#reviewer-status');
        status.textContent =
          'Review signed. Download its receipt above and send it to the case owner.';
        status.hidden = false;
        if (issued) downloadReviewJson(receipt, `omphalos-review-${issued.id.slice(0, 12)}.json`);
      }
      announce('Review signed for this exact package.');
    });
  if (form.id === 'reviewer-trust-form')
    reviewerTask('Confirming the reviewer key…', (session) =>
      acceptSignedReview(session, String(values.get('fingerprint') || '')),
    );
});
document.querySelector('#refresh').addEventListener('click', () => {
  preserveDrafts();
  task('Refreshing workspace…', async () => {
    const view = currentView();
    await refresh(false);
    const run =
      ['runs', 'investigate'].includes(view.page) && view.runId
        ? await api(`runs/${encodeURIComponent(view.runId)}`)
        : null;
    if (viewIsCurrent(view)) {
      if (run) model.run = run;
      render();
    }
    announce(
      'Workspace refreshed. Unsaved case and review edits are retained in this page session.',
    );
  });
});
window.addEventListener('focus', refreshReviewerTrust);
window.addEventListener('omphalos-reviewer-trust-changed', refreshReviewerTrust);
document.addEventListener('visibilitychange', () => {
  if (document.visibilityState === 'visible') refreshReviewerTrust();
});
window.addEventListener('omphalos-browser-error', (event) => announce(event.detail, 'error'));
window.addEventListener('omphalos-browser-restored', () => {
  document.querySelector('#evidence-dialog').close();
  model.navigationVersion += 1;
  model.routeVersion += 1;
  Object.assign(model, {
    page: 'investigate',
    flow: newFlow(),
    selectedRun: null,
    run: null,
    caseDraft: null,
    caseDirty: false,
    reviewDrafts: {},
    referenceLimits: {},
  });
  task('Opening the restored workspace…', async () => {
    await refresh(false);
    const latest = array(model.state.runs).find((run) => run.status !== 'invalid');
    if (latest) await resumeFlowRun(latest.run_id);
    else render();
    announce('Workspace restored.');
  });
});
window.addEventListener('hashchange', () => {
  preserveDrafts();
  model.navigationVersion += 1;
  model.routeVersion += 1;
  model.page = Object.hasOwn(titles, location.hash.slice(1))
    ? location.hash.slice(1)
    : 'investigate';
  render();
});
window.addEventListener('beforeunload', (event) => {
  if (model.caseDirty || Object.keys(model.reviewDrafts).length) {
    event.preventDefault();
    event.returnValue = '';
  }
});
if (window.ResizeObserver) {
  const headerSize = new window.ResizeObserver(measureObjectHeader);
  headerSize.observe(document.querySelector('.topbar'));
}
model.page = Object.hasOwn(titles, location.hash.slice(1)) ? location.hash.slice(1) : 'investigate';
refresh().catch((error) => {
  main.innerHTML = empty('Unable to load workspace', error.message);
  announce(error.message, 'error');
});
