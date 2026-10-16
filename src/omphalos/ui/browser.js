'use strict';

// This file is included only by the static website build. The desktop app keeps
// its local HTTP transport; the website runs the same engine in a worker.
(() => {
  const appBase = new URL('.', document.currentScript.src);
  const pending = new Map();
  let worker;
  let sequence = 0;
  let bootError = null;
  let unsavedChanges = false;
  let restoring = false;
  let resolveReady;
  let rejectReady;
  const ready = new Promise((resolve, reject) => {
    resolveReady = resolve;
    rejectReady = reject;
  });
  // Startup can fail before app.js attaches its own error handler.
  ready.catch(() => {});

  function fail(message) {
    bootError = new Error(message);
    rejectReady(bootError);
    for (const request of pending.values()) request.reject(bootError);
    pending.clear();
  }

  function storageState(saved) {
    unsavedChanges = !saved;
    let warning = document.getElementById('browser-storage-warning');
    if (!warning && unsavedChanges) {
      warning = document.createElement('div');
      warning.id = 'browser-storage-warning';
      warning.className = 'notice browser-storage-warning';
      warning.setAttribute('role', 'alert');
      const message = document.createElement('span');
      message.textContent =
        'Changes are only in this tab. Download a workspace backup before closing.';
      const backup = document.createElement('button');
      backup.type = 'button';
      backup.className = 'secondary';
      backup.setAttribute('data-browser-backup', '');
      backup.textContent = 'Download backup';
      warning.append(message, backup);
      const main = document.getElementById('main');
      main.parentNode.insertBefore(warning, main);
    }
    if (warning) warning.hidden = !unsavedChanges;
  }

  function startWorker() {
    worker = new Worker(new URL('browser-worker.js', appBase), { type: 'module' });
    worker.addEventListener('message', ({ data }) => {
      if (data.type === 'progress') {
        const loading = document.querySelector('#main .loading');
        if (loading) loading.textContent = data.message;
        return;
      }
      if (data.type === 'storage') {
        storageState(data.saved === true);
        return;
      }
      if (data.type === 'ready') {
        resolveReady();
        return;
      }
      if (data.type === 'startup-error') {
        fail(data.error);
        return;
      }
      const request = pending.get(data.id);
      if (!request) return;
      pending.delete(data.id);
      if (data.error) request.reject(new Error(data.error));
      else request.resolve(data.result);
    });
    worker.addEventListener('error', () => {
      fail('The investigation engine stopped. Reload to reopen your saved work.');
    });
    worker.postMessage({ type: 'initialize', appBase: appBase.href });
  }

  // IDBFS is a single-writer filesystem. A second tab must not overwrite the
  // first tab's retained evidence with an older in-memory filesystem snapshot.
  if (!navigator.locks || !window.indexedDB) {
    fail(
      'This browser cannot safely save investigations. Use an up-to-date browser with website storage enabled.',
    );
  } else {
    navigator.locks
      .request('omphalos-workspace-v2', { ifAvailable: true }, async (lock) => {
        if (!lock) {
          fail(
            'omphalOS is already open in another tab. Continue there, or close it and reload this page.',
          );
          return;
        }
        startWorker();
        await new Promise(() => {});
      })
      .catch(() => fail('Browser storage is unavailable. Enable website storage and reload.'));
  }

  async function send(type, payload) {
    await ready;
    if (bootError) throw bootError;
    if (restoring && type !== 'restore')
      throw new Error('Wait for the workspace restore to finish.');
    const id = ++sequence;
    return new Promise((resolve, reject) => {
      pending.set(id, { resolve, reject });
      worker.postMessage({ id, type, ...payload });
    });
  }

  function download(result) {
    const blobUrl = URL.createObjectURL(new Blob([result.bytes], { type: 'application/zip' }));
    const link = document.createElement('a');
    link.href = blobUrl;
    link.download = result.name;
    document.body.append(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(blobUrl), 60000);
  }

  function confirmRestore() {
    const dialog = document.createElement('dialog');
    dialog.className = 'browser-restore-confirmation';
    dialog.setAttribute('aria-labelledby', 'browser-restore-title');
    dialog.innerHTML = `<h2 id="browser-restore-title">Replace this browser’s workspace?</h2>
      <p>The selected backup will replace the investigations currently saved in this browser.</p>
      <p><button type="button" class="secondary" data-browser-backup>Download current workspace</button></p>
      <div class="actions"><button type="button" class="secondary" data-restore-cancel>Cancel</button>
      <button type="button" class="primary" data-restore-confirm>Replace workspace</button></div>`;
    document.body.append(dialog);
    return new Promise((resolve) => {
      let confirmed = false;
      dialog.querySelector('[data-restore-confirm]').addEventListener('click', () => {
        confirmed = true;
        dialog.close();
      });
      dialog.querySelector('[data-restore-cancel]').addEventListener('click', () => dialog.close());
      dialog.addEventListener(
        'close',
        () => {
          dialog.remove();
          resolve(confirmed);
        },
        { once: true },
      );
      dialog.showModal();
      dialog.querySelector('[data-restore-cancel]').focus();
    });
  }

  function restoreProgress() {
    const dialog = document.createElement('dialog');
    dialog.className = 'browser-restore-confirmation browser-restore-progress';
    dialog.setAttribute('aria-labelledby', 'browser-restore-progress-title');
    dialog.setAttribute('aria-busy', 'true');
    dialog.innerHTML =
      '<h2 id="browser-restore-progress-title" role="status">Restoring workspace…</h2>';
    dialog.addEventListener('cancel', (event) => event.preventDefault());
    document.body.append(dialog);
    dialog.showModal();
    return dialog;
  }

  function restoreFeedback(input, message = '') {
    const region = input.closest('.saved-work') || input.parentNode || document.body;
    let error = region.querySelector('[data-browser-restore-error]');
    if (!error && message) {
      error = document.createElement('p');
      error.className = 'notice error browser-restore-error';
      error.setAttribute('data-browser-restore-error', '');
      error.setAttribute('role', 'alert');
      region.prepend(error);
    }
    if (error) {
      error.textContent = message;
      error.hidden = !message;
    }
  }

  window.omphalosBrowser = {
    async request(path, body) {
      const response = await send('request', {
        path: `/api/${path}`,
        body: body === undefined ? null : JSON.stringify(body),
      });
      if (response.status >= 400) {
        const error = new Error(
          response.body_json.error || 'The operation could not be completed.',
        );
        error.status = response.status;
        throw error;
      }
      return response.body_json;
    },
  };

  document.addEventListener('click', async (event) => {
    const backup = event.target.closest('[data-browser-backup]');
    if (backup) {
      event.preventDefault();
      if (backup.disabled) return;
      backup.disabled = true;
      try {
        download(await send('backup', {}));
      } catch (error) {
        window.dispatchEvent(new CustomEvent('omphalos-browser-error', { detail: error.message }));
      } finally {
        backup.disabled = false;
      }
      return;
    }
    const link = event.target.closest('a[href]');
    if (!link) return;
    const url = new URL(link.href, appBase);
    if (url.origin !== appBase.origin || !url.pathname.startsWith('/api/exports/')) return;
    event.preventDefault();
    if (link.getAttribute('aria-busy') === 'true') return;
    link.setAttribute('aria-busy', 'true');
    try {
      download(await send('download', { path: url.pathname }));
    } catch (error) {
      window.dispatchEvent(new CustomEvent('omphalos-browser-error', { detail: error.message }));
    } finally {
      link.removeAttribute('aria-busy');
    }
  });

  document.addEventListener('change', async (event) => {
    const input = event.target.closest('[data-browser-restore]');
    const file = input?.files?.[0];
    if (!file || input.disabled) return;
    input.disabled = true;
    restoreFeedback(input);
    let progressDialog;
    let ownsRestore = false;
    const closeProgress = () => {
      progressDialog?.close();
      progressDialog?.remove();
      progressDialog = null;
      if (ownsRestore) restoring = false;
      ownsRestore = false;
    };
    try {
      if (pending.size || restoring)
        throw new Error('Wait for the current operation to finish before restoring a backup.');
      if (file.size > 512 * 1024 * 1024)
        throw new Error('Workspace backups must be smaller than 512 MiB.');
      if (!(await confirmRestore())) return;
      if (pending.size)
        throw new Error('Wait for the current operation to finish before restoring a backup.');
      restoring = true;
      ownsRestore = true;
      progressDialog = restoreProgress();
      const result = await send('restore', { bytes: new Uint8Array(await file.arrayBuffer()) });
      if (result.status >= 400)
        throw new Error(result.body_json?.error || 'The backup could not be restored.');
      closeProgress();
      window.dispatchEvent(
        new CustomEvent('omphalos-browser-restored', { detail: result.body_json }),
      );
    } catch (error) {
      closeProgress();
      restoreFeedback(input, error.message);
      window.dispatchEvent(new CustomEvent('omphalos-browser-error', { detail: error.message }));
    } finally {
      closeProgress();
      input.value = '';
      input.disabled = false;
    }
  });

  window.addEventListener('beforeunload', (event) => {
    if (pending.size || unsavedChanges || restoring) {
      event.preventDefault();
      event.returnValue = '';
    }
  });
})();
