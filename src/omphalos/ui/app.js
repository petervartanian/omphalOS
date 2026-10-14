'use strict';

const main = document.querySelector('#main');
const notice = document.querySelector('#notice');
const model = {
  state: null,
  page: 'overview',
  selectedRun: null,
  run: null,
  runTab: 'findings',
  caseDraft: null,
  caseDirty: false,
  navigationVersion: 0,
  reviewDrafts: {},
  findingPage: 0,
  reviewPage: 0,
  referenceLimits: {},
  operation: false,
};
const PAGE_SIZE = 20;
const titles = {
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

function reviewStatus(status) {
  if (status === 'invalid') return badge('Invalid run', 'red');
  return badge(
    status === 'reviewed' ? 'Review recorded' : 'Needs review',
    status === 'reviewed' ? '' : 'amber',
  );
}

function announce(message, kind = 'success') {
  notice.textContent = message;
  notice.className = `notice ${kind}`;
  notice.hidden = false;
  notice.setAttribute('role', kind === 'error' ? 'alert' : 'status');
}

async function api(path, body) {
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
    throw new Error(
      'Unable to reach the local workbench. Check that its server is running, then try again.',
    );
  }
  let result;
  try {
    result = await response.json();
  } catch {
    throw new Error(
      `The local server returned an unreadable response${response.status ? ` (${response.status})` : ''}. Reload the workspace and try again.`,
    );
  }
  if (!response.ok)
    throw new Error(
      result.error ||
        `The operation failed (${response.status}). Try again or inspect the local server log.`,
    );
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
      'button[type="submit"], button[data-action="verify"], button[data-action="replay"], button[data-action="export"], button[data-action="open-run"], button[data-action="load-case"], #create-demo, #refresh',
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
  if (renderPage) render();
}

function heading(_context, title, description, actions = '') {
  return `<div class="page-heading"><div><h1>${esc(title)}</h1><p>${esc(description)}</p></div>${actions ? `<div class="actions">${actions}</div>` : ''}</div>`;
}

function render() {
  if (!model.state) return;
  document.querySelectorAll('[data-nav]').forEach((link) => {
    const active = link.dataset.nav === model.page;
    link.classList.toggle('active', active);
    if (active) link.setAttribute('aria-current', 'page');
    else link.removeAttribute('aria-current');
  });
  document.querySelector('#breadcrumb').textContent = `Workspace / ${titles[model.page]}`;
  ({ overview: renderOverview, data: renderData, cases: renderCases, runs: renderRuns })[
    model.page
  ]();
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
              <td>${reviewStatus(run.status)}</td>
              <td><button class="text-button" data-action="open-run" data-id="${esc(run.run_id)}">
                ${run.status === 'reviewed' ? 'View run' : 'Review observations'} →
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
      'Cases, evidence, and analyst review in one local workspace.',
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
          <li><span class="step-number">01</span><div><h3>Import the evidence</h3><p>Add entity and transaction records, or explore a clearly labeled synthetic dataset.</p></div><a class="button-link secondary" href="#data">Add data</a></li>
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
      <p class="small muted">Invalid rows reject the import; none are silently discarded. Browser limit: six files, 48 MiB combined.</p>
    </details>`;
}

function datasetTable(datasets) {
  if (!datasets.length)
    return empty(
      'No datasets',
      'Import your records or create a separate synthetic dataset to explore the workflow.',
    );
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
      <button class="secondary" id="create-demo" type="button">Create synthetic dataset</button>
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
    <p class="small muted">Synthetic datasets contain planted signals and benign counterexamples, not real counterparties. Their synthetic label stays with every run and exported report.</p>
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
      <section class="panel">${empty('Import records to create a case', 'A case needs a dataset. You can use your own records or explore an explicitly synthetic dataset.', '<a class="button-link" href="#data">Add data</a>')}</section>`;
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
            <strong>${esc(run.case_id || run.run_id)}</strong><small>${esc(displayDate(run.created_at))}</small>
            <small>${esc(formatNumber(run.findings_count))} observations / ${run.status === 'reviewed' ? 'Review recorded' : 'Needs review'}</small>
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
  const canExport = verified && reviewed;
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
        ${badge(reviewed ? 'Review recorded' : 'Needs review', reviewed ? '' : 'amber')}
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
      <p class="export-note">${!verified ? 'Resolve the file verification issues before exporting.' : !reviewed ? 'Export requires a named assessment of every observation and an acknowledgment of coverage limits.' : 'The package includes the recorded review and retained evidence. Reviewer identity is self-asserted.'}</p>
      <div id="run-result" class="result-box"></div>
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
        ${assessment ? badge(human(assessment.disposition)) : badge('Unreviewed', 'amber')}
      </div>
      <p class="observation">${esc(finding.observation)}</p>
      ${candidateFacts(finding)}
      <div class="evidence-label">Supporting records (${array(finding.record_refs).length})</div>
      ${recordButtons(finding)}
      ${sourceButtons(finding)}
      ${Object.keys(finding.metrics || {}).length ? `<details><summary>Computed values</summary>${keyValues(Object.fromEntries(Object.entries(finding.metrics).map(([key, value]) => [human(key), value])))}</details>` : ''}
      ${analyticalCaveats(finding)}
      <div class="finding-meta"><span>Entities: ${esc(array(finding.entity_ids).join(', ') || 'See cited records')}</span><span class="mono">${esc(finding.finding_id)}</span></div>
    </article>`;
}

function renderFindings() {
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
        <p class="small">${esc(finding.observation)}</p>
        ${recordButtons(finding)}${sourceButtons(finding)}
        <details><summary>Analytical context and caveats</summary>${candidateFacts(finding)}${analyticalCaveats(finding)}</details>
      </div>
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

function renderReview() {
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
    const message = `${draft.findings.filter(reviewRowComplete).length} of ${draft.findings.length} observations have all assessment fields filled.`;
    if (counter && counter.textContent !== message) counter.textContent = message;
    updateDraftIndicator();
  }
}

function preserveDrafts() {
  saveCaseDraft();
  saveReviewDraft();
}

async function filesPayload(files) {
  const entries = [...files];
  if (entries.reduce((total, file) => total + file.size, 0) > model.state.limits.upload_bytes) {
    throw new Error('Combined files exceed the 48 MiB browser upload limit.');
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
  const incomplete = review.findings.findIndex((row) => !reviewRowComplete(row));
  if (incomplete !== -1) {
    model.reviewPage = Math.floor(incomplete / PAGE_SIZE);
    renderRuns();
    document.querySelector('#review-form [data-finding] select')?.focus();
    throw new Error(
      `Observation ${incomplete + 1} needs a disposition and specific rationale, unknowns, alternatives, and evidence that would change the assessment.`,
    );
  }
  const unlock = lockForm(form);
  try {
    const result = await api(`runs/${encodeURIComponent(runId)}/review`, review);
    if (JSON.stringify(model.reviewDrafts[runId]) === submittedDraft)
      delete model.reviewDrafts[runId];
    await refresh(false);
    if (viewIsCurrent(view)) await openRun(runId, view.navigation);
    announce(`Review ${result.review_id} saved. The verified run can now be exported.`);
    updateDraftIndicator();
  } finally {
    unlock();
  }
}

main.addEventListener('submit', (event) => {
  event.preventDefault();
  const form = event.target;
  const action = event.submitter?.value;
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
  captureEditedForm(event);
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
    renderRuns();
    document.querySelector('#run-result').innerHTML =
      `<details open><summary>${action === 'verify' ? 'Verification result' : 'Replay result'}</summary><pre>${json(result)}</pre></details>`;
  }
  announce(
    `${action === 'verify' ? 'Verification' : 'Replay'} ${result.ok === true ? 'passed' : 'did not pass'} for ${view.runId}.${viewIsCurrent(view) ? ' Inspect the result details.' : ' Reopen the run for details.'}`,
    result.ok === true ? 'success' : 'error',
  );
}

async function exportRun() {
  const view = currentView();
  const result = await api(`runs/${encodeURIComponent(view.runId)}/export`, {});
  if (viewIsCurrent(view)) {
    document.querySelector('#run-result').innerHTML = `
      <a class="download-link" href="${esc(result.download_url)}" download>Download evidence package ↓</a>
      <details><summary>Package details</summary><p class="small">${esc(result.name)}</p><p class="mono small word-break">SHA-256: ${esc(result.sha256 || '')}</p></details>`;
  }
  announce(
    `Evidence package created for ${view.runId}.${viewIsCurrent(view) ? ' Use the download link and included verification instructions.' : ' Reopen the run to create another download link. The package is retained in the workspace exports folder.'}`,
  );
}

async function inspectEvidence(button, official = false) {
  const view = currentView();
  const id = button.dataset.id;
  const query = official
    ? `source-evidence?id=${encodeURIComponent(id)}`
    : `evidence?table=${encodeURIComponent(button.dataset.table)}&id=${encodeURIComponent(id)}`;
  const evidence = await api(`runs/${encodeURIComponent(view.runId)}/${query}`);
  if (!viewIsCurrent(view)) return;
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
      <h3 class="stack-gap">Original provenance</h3>
      ${evidence.origin ? `<p class="small">File <code>${esc(evidence.origin.source_file)}</code>, source row ${esc(evidence.origin.source_row)}.</p>` : '<p class="small muted">Per-row provenance was not recorded.</p>'}
      <details><summary>Original file hashes</summary><pre>${json(evidence.source_files)}</pre></details>
      <p class="small muted">This record is frozen in the run, rather than read from a changing dataset.</p>`;
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
  const button = event.target.closest('button');
  if (!button) return;
  const { action, id } = button.dataset;
  if (button.id === 'create-demo')
    task('Creating a separate synthetic dataset…', async () => {
      const view = currentView();
      const result = await api('datasets/demo', {});
      await refresh(false);
      if (viewIsCurrent(view)) render();
      announce(
        `Synthetic dataset ${result.dataset_id} created. Select it in a case to explore the workflow.`,
      );
    });
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
    renderRuns();
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
document
  .querySelector('#close-dialog')
  .addEventListener('click', () => document.querySelector('#evidence-dialog').close());
document.querySelector('#refresh').addEventListener('click', () => {
  preserveDrafts();
  task('Refreshing workspace…', async () => {
    const view = currentView();
    await refresh(false);
    const run =
      view.page === 'runs' && view.runId
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
window.addEventListener('hashchange', () => {
  preserveDrafts();
  model.navigationVersion += 1;
  model.page = Object.hasOwn(titles, location.hash.slice(1)) ? location.hash.slice(1) : 'overview';
  render();
});
window.addEventListener('beforeunload', (event) => {
  if (model.caseDirty || Object.keys(model.reviewDrafts).length) {
    event.preventDefault();
    event.returnValue = '';
  }
});
model.page = Object.hasOwn(titles, location.hash.slice(1)) ? location.hash.slice(1) : 'overview';
refresh().catch((error) => {
  main.innerHTML = empty('Unable to load workspace', error.message);
  announce(error.message, 'error');
});
