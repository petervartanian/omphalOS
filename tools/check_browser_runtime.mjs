// Execute the published WebAssembly runtime, with all network access disabled.
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

async function main() {
  const base = path.resolve(process.argv[2] || 'dist/browser');
  const build = JSON.parse(fs.readFileSync(path.join(base, 'build-manifest.json'), 'utf8'));
  for (const file of build.files) {
    const bytes = fs.readFileSync(path.join(base, file.path));
    assert.equal(bytes.length, file.bytes, `${file.path}: length`);
    assert.equal(
      createHash('sha256').update(bytes).digest('hex'),
      file.sha256,
      `${file.path}: hash`,
    );
  }
  globalThis.fetch = async (url) => {
    throw new Error(`Runtime attempted a network request: ${url}`);
  };
  const sourceBytes = new TextEncoder().encode(
    JSON.stringify({
      total: 1,
      offset: 0,
      search_performed_at: '2026-10-16T12:00:00Z',
      sources_used: [],
      results: [
        {
          id: 'fictional-wasm-record',
          source: 'Entity List (EL)',
          name: 'Fictional WASM validation organization',
          start_date: '2020-01-01',
          addresses: [{ country: 'US' }],
        },
      ],
    }),
  );
  let sourceRequests = 0;
  globalThis.fixtureSha = createHash('sha256').update(sourceBytes).digest('hex');
  globalThis.fixtureTransport = (url, maximum, provider) => {
    assert.equal(provider, 'csl');
    assert.equal(
      url,
      'https://data.trade.gov/downloadable_consolidated_screening_list/v1/consolidated.json',
    );
    assert.ok(sourceBytes.length < maximum);
    sourceRequests += 1;
    return { status: 200, url, headers: { etag: 'fictional-wasm-fixture' }, body: sourceBytes };
  };
  const manifest = JSON.parse(fs.readFileSync(path.join(base, 'runtime/manifest.json'), 'utf8'));
  const runtime = path.join(base, manifest.pyodide.index_url);
  const { loadPyodide } = await import(pathToFileURL(path.join(runtime, 'pyodide.mjs')));
  const pyodide = await loadPyodide({ indexURL: runtime });
  await pyodide.loadPackage(
    manifest.wheels.map((wheel) => wheel.name),
    { checkIntegrity: true },
  );
  pyodide.unpackArchive(
    new Uint8Array(fs.readFileSync(path.join(base, manifest.engine.path))),
    'zip',
    { extractDir: '/app' },
  );
  const result = JSON.parse(
    pyodide.runPython(`
import sys, json, ssl, http.server, socket, importlib.metadata, hashlib, io, zipfile
sys.path.insert(0, '/app')
from pydantic import BaseModel, ValidationError
from omphalos.models import Case
from omphalos.browser import BrowserApp
from js import fixtureTransport, fixtureSha
class Probe(BaseModel):
    count: int
valid = Probe.model_validate({'count': '42'}).model_dump()
try:
    Probe.model_validate({'count': 'not-an-integer'})
    rejected = False
except ValidationError:
    rejected = True
app = BrowserApp('/workspace', transport=fixtureTransport)
def request(path, body=None):
    result = json.loads(app.dispatch_json(path, json.dumps(body) if body is not None else None))
    assert result['status'] == 200, (path, result)
    return result['body_json']
state = request('/api/state')
assert state['mode'] == 'browser_local'
assert state['capabilities']['package_signing'] is False
subject = request('/api/workflow/subject', {'name': 'Fictional WASM validation organization'})
source = request('/api/sources/fetch', {'source_id': 'csl'})
raw_source = (app.root / 'sources' / source['snapshot_id'] / 'raw.json').read_bytes()
assert hashlib.sha256(raw_source).hexdigest() == fixtureSha
inputs = {'dataset_id': subject['dataset_id'], 'goal_id': 'counterparty_screening', 'as_of': '2026-10-16', 'watchlist_snapshot_id': source['snapshot_id']}
plan = request('/api/workflow/plan', inputs)
assert plan['can_run'], plan
run_payload = {**inputs, 'plan_id': plan['plan_id'], 'case_id': plan['case']['case_id']}
run_id = request('/api/workflow/run', run_payload)['run_id']
run = request('/api/runs/' + run_id)
review = {
    'schema_version': '2.1', 'run_id': run_id, 'reviewer': 'Fictional WASM validation',
    'decision': 'keep_open', 'summary': 'Runtime test only.',
    'scope_finding_ids': [row['finding_id'] for row in run['analysis']['findings']],
    'acknowledge_limitations': True,
}
request('/api/runs/' + run_id + '/review', review)
package = request('/api/runs/' + run_id + '/export', {})
assert package['verification']['ok'], package
assert request('/api/runs/' + run_id + '/verify', {})['ok']
assert request('/api/runs/' + run_id + '/replay', {})['ok']
archive = app.export_bytes(package['download_url'])
assert hashlib.sha256(archive).hexdigest() == package['sha256']
with zipfile.ZipFile(io.BytesIO(archive)) as bundle:
    assert bundle.testzip() is None
    assert {'run/analysis.json', 'review.json', 'report.html'} <= set(bundle.namelist())
app = BrowserApp('/workspace')
assert request('/api/state')['token'] == state['token']
assert request('/api/workflow/run', run_payload)['run_id'] == run_id
assert request('/api/runs/' + run_id + '/replay', {})['ok']
backup = app.backup_bytes()
app = BrowserApp('/restored-workspace')
empty_token = request('/api/state')['token']
assert app.restore_bytes(b'not-a-workspace-zip')['status'] == 400
assert request('/api/state')['token'] == empty_token
restored = app.restore_bytes(memoryview(backup))
assert restored['status'] == 200, restored
assert request('/api/state')['token'] == state['token']
assert request('/api/workflow/run', run_payload)['run_id'] == run_id
assert request('/api/runs/' + run_id + '/replay', {})['ok']
assert app.export_bytes(package['download_url']) == archive
app = BrowserApp('/restored-workspace')
assert request('/api/state')['token'] == state['token']
assert request('/api/runs/' + run_id + '/verify', {})['ok']
json.dumps({
    'python': '.'.join(str(v) for v in sys.version_info[:3]),
    'pydantic': importlib.metadata.version('pydantic'),
    'pydantic_core': importlib.metadata.version('pydantic_core'),
    'valid': valid, 'invalid_rejected': rejected,
    'case_schema': bool(Case.model_json_schema()['properties']),
    'standard_imports': True,
    'workflow': 'subject-source-plan-run-review-export-verify-replay',
    'javascript_bytes_preserved': True,
    'workspace_reopened': True,
    'backup_restored_and_reopened': True,
    'export_bytes': len(archive),
})
`),
  );
  const app = pyodide.globals.get('app');
  const backupProxy = app.backup_bytes();
  const backupBytes = backupProxy.toJs();
  backupProxy.destroy();
  assert.ok(backupBytes instanceof Uint8Array);
  const restoredProxy = app.restore_bytes(backupBytes);
  const restored = restoredProxy.toJs({ dict_converter: Object.fromEntries });
  restoredProxy.destroy();
  app.destroy();
  assert.equal(restored.status, 200);
  assert.equal(result.python, manifest.pyodide.python_version);
  assert.equal(result.pydantic, manifest.wheels.find((wheel) => wheel.name === 'pydantic').version);
  assert.equal(
    result.pydantic_core,
    manifest.wheels.find((wheel) => wheel.name === 'pydantic-core').version,
  );
  assert.deepEqual(result.valid, { count: 42 });
  assert.equal(result.invalid_rejected, true);
  assert.equal(result.case_schema, true);
  assert.equal(result.workspace_reopened, true);
  assert.equal(result.backup_restored_and_reopened, true);
  assert.ok(result.export_bytes > 0);
  assert.equal(result.javascript_bytes_preserved, true);
  assert.equal(sourceRequests, 1);
  console.log(
    JSON.stringify(
      { ok: true, network_requests: 0, javascript_backup_roundtrip: true, ...result },
      null,
      2,
    ),
  );
}

main().catch((error) => {
  console.error(error.message);
  process.exitCode = 1;
});
