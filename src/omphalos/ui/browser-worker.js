'use strict';

let engine;
let bridge;
let dispatch;
let exportBytes;
let queue = Promise.resolve();
let unsavedChanges = false;
const WORKSPACE = '/omphalos-workspace';

function progress(message) {
  self.postMessage({ type: 'progress', message });
}

function syncWorkspace(populate) {
  return new Promise((resolve, reject) => {
    engine.FS.syncfs(populate, (error) => (error ? reject(error) : resolve()));
  });
}

async function saveWorkspace() {
  try {
    await syncWorkspace(false);
    unsavedChanges = false;
  } catch {
    unsavedChanges = true;
  }
  self.postMessage({ type: 'storage', saved: !unsavedChanges });
}

function binaryResult(proxy) {
  try {
    // Own the copied bytes after releasing the Python proxy. Never transfer a
    // view of the WebAssembly heap to the main thread.
    return Uint8Array.from(proxy.toJs());
  } finally {
    proxy.destroy();
  }
}

async function checkedBytes(base, asset) {
  const response = await fetch(new URL(asset.path, base), { credentials: 'same-origin' });
  if (!response.ok) throw new Error('The website engine could not be downloaded. Reload to retry.');
  const bytes = await response.arrayBuffer();
  const digest = new Uint8Array(await crypto.subtle.digest('SHA-256', bytes));
  const hex = [...digest].map((byte) => byte.toString(16).padStart(2, '0')).join('');
  if (hex !== asset.sha256 || bytes.byteLength !== asset.bytes)
    throw new Error('The engine download did not pass its integrity check. Reload to retry.');
  return bytes;
}

// Synchronous requests are confined to this dedicated worker. The interface
// remains responsive, and the original Python parsers receive original bytes.
self.omphalosFetch = (canonicalUrl, maxBytes, provider) => {
  const allowed = new Set(['data.trade.gov', 'api.gleif.org', 'www.wikidata.org']);
  const canonical = new URL(canonicalUrl);
  if (canonical.protocol !== 'https:' || !allowed.has(canonical.hostname))
    throw new Error(
      'This source is unavailable for direct browser download. Import its file instead.',
    );
  const transportUrl =
    provider === 'wikidata' || canonical.hostname === 'www.wikidata.org'
      ? `${canonicalUrl}${canonical.search ? '&' : '?'}origin=*`
      : canonicalUrl;
  const request = new XMLHttpRequest();
  request.open('GET', transportUrl, false);
  request.responseType = 'arraybuffer';
  request.timeout = 90000;
  request.setRequestHeader('Accept', 'application/json');
  request.send();
  const actual = new URL(request.responseURL);
  const expected = new URL(transportUrl);
  actual.searchParams.sort();
  expected.searchParams.sort();
  if (actual.href !== expected.href)
    throw new Error('The source redirected to an unexpected address.');
  const body = new Uint8Array(request.response || new ArrayBuffer(0));
  if (body.byteLength > maxBytes) throw new Error('The source exceeds its download limit.');
  const headers = {};
  for (const line of request
    .getAllResponseHeaders()
    .trim()
    .split(/[\r\n]+/)) {
    const separator = line.indexOf(':');
    if (separator > 0)
      headers[line.slice(0, separator).toLowerCase()] = line.slice(separator + 1).trim();
  }
  return { status: request.status, url: canonicalUrl, headers, body };
};

async function initialize(appBase) {
  progress('Preparing omphalOS…');
  const base = new URL(appBase);
  if (base.origin !== self.location.origin)
    throw new Error('The engine must load from this website.');
  const response = await fetch(new URL('runtime/manifest.json', base));
  if (!response.ok) throw new Error('The website engine is unavailable. Reload to retry.');
  const manifest = await response.json();
  const runtime = new URL(manifest.pyodide.index_url, base);
  const { loadPyodide } = await import(new URL('pyodide.mjs', runtime).href);
  engine = await loadPyodide({ indexURL: runtime.href });
  progress('Loading the analysis engine…');
  // The local Pyodide lock pins these names to the wheel hashes. Its loader
  // checks the bytes it actually installs, without a separate unchecked fetch.
  await engine.loadPackage(
    manifest.wheels.map((wheel) => wheel.name),
    { checkIntegrity: true },
  );
  if (manifest.wheels.some((wheel) => !Object.hasOwn(engine.loadedPackages, wheel.name)))
    throw new Error('The analysis engine could not be verified. Reload to retry.');
  const source = await checkedBytes(base, manifest.engine);
  engine.FS.mkdirTree('/engine');
  engine.unpackArchive(source, 'zip', { extractDir: '/engine' });
  engine.FS.mkdirTree(WORKSPACE);
  engine.FS.mount(engine.FS.filesystems.IDBFS, {}, WORKSPACE);
  progress('Opening saved work…');
  await syncWorkspace(true);
  engine.runPython(`
import sys
sys.path.insert(0, '/engine')
from js import omphalosFetch
from omphalos.browser import BrowserApp
_browser_app = BrowserApp(root='${WORKSPACE}', transport=omphalosFetch)
`);
  bridge = engine.globals.get('_browser_app');
  dispatch = bridge.dispatch_json;
  exportBytes = bridge.export_bytes;
  await saveWorkspace();
  self.postMessage({ type: 'ready' });
}

async function handle(message) {
  if (message.type === 'initialize') {
    try {
      await initialize(message.appBase);
    } catch (error) {
      self.postMessage({
        type: 'startup-error',
        error: `omphalOS could not start: ${error.message}`,
      });
    }
    return;
  }
  try {
    if (!bridge) throw new Error('The engine has not started. Reload to retry.');
    if (message.type === 'request') {
      const mutation = message.body !== null && message.body !== undefined;
      // An omitted argument maps to Python None; JS null is a distinct JsNull
      // object in Pyodide and must not be passed as a GET request body.
      const result = JSON.parse(
        mutation ? dispatch(message.path, message.body) : dispatch(message.path),
      );
      if (mutation) await saveWorkspace();
      if (unsavedChanges && result.body_json?.storage) {
        result.body_json.storage.description =
          'Changes in this tab have not been saved. Download a workspace backup before closing.';
      }
      self.postMessage({ id: message.id, result });
    } else if (message.type === 'download') {
      const bytes = binaryResult(exportBytes(message.path));
      self.postMessage({ id: message.id, result: { name: message.path.split('/').pop(), bytes } });
    } else if (message.type === 'backup') {
      const bytes = binaryResult(bridge.backup_bytes());
      self.postMessage({
        id: message.id,
        result: { name: `omphalos-workspace-${new Date().toISOString().slice(0, 10)}.zip`, bytes },
      });
    } else if (message.type === 'restore') {
      const proxy = bridge.restore_bytes(message.bytes);
      let result;
      try {
        result = proxy.toJs({ dict_converter: Object.fromEntries });
      } finally {
        proxy.destroy();
      }
      // Failed validation can still clean up a restore journal. Persist the
      // final workspace state after either outcome without losing its result.
      await saveWorkspace();
      self.postMessage({ id: message.id, result });
    } else {
      throw new Error('Unknown workspace operation.');
    }
  } catch (error) {
    self.postMessage({ id: message.id, error: error.message });
  }
}

self.addEventListener('message', ({ data }) => {
  queue = queue.then(() => handle(data));
});
