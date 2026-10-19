/* Detached review receipts. A verified signature proves control of a pinned key,
 * not a person's employment, authority, or independence. Private keys are
 * encrypted at rest and never included in case packages or workspace backups. */
(() => {
  'use strict';
  const RECEIPT = 'omphalos-independent-review/1';
  const CARD = 'omphalos-reviewer-key/1';
  const encoder = new TextEncoder();
  const hex = /^[a-f0-9]{64}$/;
  const identifier = /^[A-Za-z0-9][A-Za-z0-9_-]{0,79}$/;
  const algorithm = { name: 'ECDSA', namedCurve: 'P-256' };
  const signing = { name: 'ECDSA', hash: 'SHA-256' };

  function fail(message) {
    throw new Error(message);
  }
  function fields(value, names) {
    if (
      !value ||
      typeof value !== 'object' ||
      Array.isArray(value) ||
      Object.keys(value).sort().join(',') !== [...names].sort().join(',')
    ) {
      fail('The review file has an unsupported structure.');
    }
  }
  function text(value, label, min = 1, max = 10000) {
    if (
      typeof value !== 'string' ||
      value !== value.trim() ||
      value.length < min ||
      value.length > max ||
      [...value].some((ch) => ch.charCodeAt(0) < 32 && !['\t', '\n', '\r'].includes(ch))
    ) {
      fail(`${label} is missing or invalid.`);
    }
    return value;
  }
  function canonical(value) {
    if (value && typeof value === 'object') {
      return `{${Object.keys(value)
        .sort()
        .map((key) => `${JSON.stringify(key)}:${canonical(value[key])}`)
        .join(',')}}`;
    }
    return JSON.stringify(value);
  }
  function bytes(value) {
    if (typeof value !== 'string' || !/^[A-Za-z0-9_-]+$/.test(value))
      fail('Invalid signature encoding.');
    const result = Uint8Array.from(atob(value.replace(/-/g, '+').replace(/_/g, '/')), (ch) =>
      ch.charCodeAt(0),
    );
    if (base64(result) !== value) fail('Invalid signature encoding.');
    return result;
  }
  function base64(value) {
    return btoa(String.fromCharCode(...new Uint8Array(value)))
      .replace(/\+/g, '-')
      .replace(/\//g, '_')
      .replace(/=+$/, '');
  }
  function publicKey(value) {
    fields(value, ['kty', 'crv', 'x', 'y']);
    if (
      value.kty !== 'EC' ||
      value.crv !== 'P-256' ||
      bytes(value.x).length !== 32 ||
      bytes(value.y).length !== 32
    )
      fail('Unsupported reviewer key.');
    return { kty: 'EC', crv: 'P-256', x: value.x, y: value.y };
  }
  function contextFields(context) {
    for (const name of ['package_sha256', 'analysis_digest']) {
      if (!hex.test(context?.[name])) fail('Open a verified case package before reviewing it.');
    }
    for (const name of ['run_id', 'review_id']) {
      if (!identifier.test(context?.[name])) fail('The package review identity is invalid.');
    }
    return {
      package_sha256: context.package_sha256,
      analysis_digest: context.analysis_digest,
      run_id: context.run_id,
      review_id: context.review_id,
    };
  }
  const normalizedName = (name) =>
    name
      .normalize('NFKC')
      .toLocaleLowerCase('en-US')
      .replace(/[^\p{L}\p{N}]/gu, '');

  function indexedStore() {
    let connection;
    async function db() {
      if (!connection)
        connection = new Promise((resolve, reject) => {
          if (!window.indexedDB)
            return reject(new Error('This browser cannot retain reviewer keys.'));
          const request = window.indexedDB.open('omphalos-independent-reviews-v1', 1);
          request.onupgradeneeded = () => request.result.createObjectStore('records');
          request.onsuccess = () => resolve(request.result);
          request.onerror = () => reject(new Error('Reviewer storage could not be opened.'));
          request.onblocked = () =>
            reject(new Error('Close other omphalOS tabs before opening reviewer storage.'));
        });
      return connection;
    }
    async function operation(mode, run) {
      const database = await db();
      return new Promise((resolve, reject) => {
        const transaction = database.transaction('records', mode);
        let result;
        const request = run(transaction.objectStore('records'));
        request.onsuccess = () => {
          result = request.result;
        };
        transaction.oncomplete = () => resolve(result);
        transaction.onerror = transaction.onabort = () =>
          reject(new Error('Reviewer storage could not be saved.'));
      });
    }
    return {
      get: (key) => operation('readonly', (store) => store.get(key)),
      add: (key, value) => operation('readwrite', (store) => store.add(value, key)),
      put: (key, value) => operation('readwrite', (store) => store.put(value, key)),
      delete: (key) => operation('readwrite', (store) => store.delete(key)),
      async list(prefix) {
        const database = await db();
        return new Promise((resolve, reject) => {
          const transaction = database.transaction('records', 'readonly');
          const result = [];
          const request = transaction.objectStore('records').openCursor();
          request.onsuccess = () => {
            const cursor = request.result;
            if (!cursor) return;
            if (String(cursor.key).startsWith(prefix)) result.push(cursor.value);
            cursor.continue();
          };
          transaction.oncomplete = () => resolve(result);
          transaction.onerror = transaction.onabort = () =>
            reject(new Error('Reviewer storage could not be read.'));
        });
      },
    };
  }

  function create({ store = indexedStore(), cryptography = window.crypto } = {}) {
    const channel = window.BroadcastChannel
      ? new window.BroadcastChannel('omphalos-reviewer-trust-v1')
      : null;
    function announceTrustChange(broadcast = true) {
      if (window.dispatchEvent && window.CustomEvent)
        window.dispatchEvent(new window.CustomEvent('omphalos-reviewer-trust-changed'));
      if (broadcast) channel?.postMessage('changed');
    }
    if (channel) channel.onmessage = () => announceTrustChange(false);
    async function digest(value) {
      if (!cryptography?.subtle)
        fail('Independent review requires HTTPS and browser cryptography.');
      return Array.from(
        new Uint8Array(await cryptography.subtle.digest('SHA-256', encoder.encode(value))),
        (byte) => byte.toString(16).padStart(2, '0'),
      ).join('');
    }
    async function card(name, key) {
      text(name, 'Reviewer name', 2, 120);
      key = publicKey(key);
      await cryptography.subtle.importKey('jwk', key, algorithm, false, ['verify']);
      return {
        schema_version: CARD,
        name,
        public_key: key,
        key_sha256: await digest(`omphalos-reviewer-key-v1\n${canonical(key)}\n`),
      };
    }
    async function profile() {
      const saved = await store.get('profile');
      return saved ? card(saved.name, saved.public_key) : null;
    }
    async function wrappingKey(passphrase, salt) {
      text(passphrase, 'Signing passphrase (at least 14 characters)', 14, 1024);
      const material = encoder.encode(passphrase);
      try {
        const key = await cryptography.subtle.importKey('raw', material, 'PBKDF2', false, [
          'deriveKey',
        ]);
        return await cryptography.subtle.deriveKey(
          { name: 'PBKDF2', hash: 'SHA-256', salt, iterations: 600000 },
          key,
          { name: 'AES-GCM', length: 256 },
          false,
          ['encrypt', 'decrypt'],
        );
      } finally {
        material.fill(0);
      }
    }
    async function unlock(saved, passphrase) {
      const identity = await card(saved.name, saved.public_key);
      if (identity.key_sha256 !== saved.key_sha256) fail('The saved reviewer identity is damaged.');
      const protectedKey = saved.protected_key;
      fields(protectedKey, ['format', 'salt', 'iv', 'ciphertext']);
      if (protectedKey.format !== 'pbkdf2-sha256-600000-aes256gcm/1')
        fail('Unsupported protected signing key.');
      const salt = bytes(protectedKey.salt);
      const iv = bytes(protectedKey.iv);
      const ciphertext = bytes(protectedKey.ciphertext);
      if (salt.length !== 16 || iv.length !== 12 || ciphertext.length > 1024)
        fail('Invalid protected signing key.');
      const wrapping = await wrappingKey(passphrase, salt);
      let raw;
      try {
        raw = new Uint8Array(
          await cryptography.subtle.decrypt(
            { name: 'AES-GCM', iv, additionalData: encoder.encode(canonical(identity)) },
            wrapping,
            ciphertext,
          ),
        );
        return await cryptography.subtle.importKey('pkcs8', raw, algorithm, false, ['sign']);
      } catch {
        fail('The signing key could not be unlocked. Check your passphrase.');
      } finally {
        raw?.fill(0);
      }
    }
    async function createProfile(name, passphrase) {
      name = text(name.trim(), 'Reviewer name', 2, 120);
      const existing = await profile();
      if (existing) {
        if (existing.name !== name)
          fail('This browser already has a reviewer identity. Use your own browser profile.');
        await unlock(await store.get('profile'), passphrase);
        return existing;
      }
      if (!cryptography?.subtle)
        fail('Independent review requires HTTPS and browser cryptography.');
      const salt = cryptography.getRandomValues(new Uint8Array(16));
      const iv = cryptography.getRandomValues(new Uint8Array(12));
      const wrapping = await wrappingKey(passphrase, salt);
      const pair = await cryptography.subtle.generateKey(algorithm, true, ['sign', 'verify']);
      const jwk = await cryptography.subtle.exportKey('jwk', pair.publicKey);
      const identity = await card(name, { kty: jwk.kty, crv: jwk.crv, x: jwk.x, y: jwk.y });
      const raw = new Uint8Array(await cryptography.subtle.exportKey('pkcs8', pair.privateKey));
      let protectedKey;
      try {
        protectedKey = {
          format: 'pbkdf2-sha256-600000-aes256gcm/1',
          salt: base64(salt),
          iv: base64(iv),
          ciphertext: base64(
            await cryptography.subtle.encrypt(
              { name: 'AES-GCM', iv, additionalData: encoder.encode(canonical(identity)) },
              wrapping,
              raw,
            ),
          ),
        };
      } finally {
        raw.fill(0);
      }
      try {
        await store.add('profile', { ...identity, protected_key: protectedKey });
      } catch (error) {
        const winner = await profile();
        if (winner?.name === name) {
          await unlock(await store.get('profile'), passphrase);
          return winner;
        }
        throw error;
      }
      return identity;
    }
    async function trustReviewer(identity, confirmedFingerprint) {
      fields(identity, ['schema_version', 'name', 'public_key', 'key_sha256']);
      if (identity.schema_version !== CARD) fail('Unsupported reviewer identity.');
      const checked = await card(identity.name, identity.public_key);
      const confirmed = String(confirmedFingerprint).replace(/\s/g, '').toLowerCase();
      if (
        checked.key_sha256 !== identity.key_sha256 ||
        !hex.test(confirmed) ||
        confirmed !== checked.key_sha256
      )
        fail('The separately confirmed fingerprint does not match this reviewer.');
      if ((await profile())?.key_sha256 === confirmed)
        fail('Your own key cannot be an independent reviewer.');
      await store.put(`trust:${confirmed}`, checked);
      announceTrustChange();
      return checked;
    }
    async function inspect(receipt, context) {
      fields(receipt, ['schema_version', 'payload', 'public_key', 'signature']);
      if (receipt.schema_version !== RECEIPT) fail('Unsupported review receipt.');
      const payload = receipt.payload;
      fields(payload, [
        'package_sha256',
        'analysis_digest',
        'run_id',
        'review_id',
        'reviewer_name',
        'reviewer_key_sha256',
        'decision',
        'note',
        'created_at',
      ]);
      const expected = contextFields(context);
      if (Object.keys(expected).some((key) => payload[key] !== expected[key])) {
        fail(
          'This review belongs to a different package or decision. Open the exact reviewed package.',
        );
      }
      if (!['approve', 'request_changes'].includes(payload.decision))
        fail('Unsupported review decision.');
      text(payload.note, 'Review reason', 12);
      if (!/[\p{L}\p{N}]/u.test(payload.note)) fail('Add a case-specific review reason.');
      if (
        typeof payload.created_at !== 'string' ||
        !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/.test(payload.created_at) ||
        !Number.isFinite(Date.parse(payload.created_at)) ||
        new Date(payload.created_at).toISOString() !== payload.created_at
      ) {
        fail('Invalid review timestamp.');
      }
      const reviewer = await card(payload.reviewer_name, receipt.public_key);
      if (reviewer.key_sha256 !== payload.reviewer_key_sha256)
        fail('The reviewer key does not match the receipt.');
      const key = await cryptography.subtle.importKey(
        'jwk',
        reviewer.public_key,
        algorithm,
        false,
        ['verify'],
      );
      const signature = bytes(receipt.signature);
      if (
        signature.length !== 64 ||
        !(await cryptography.subtle.verify(
          signing,
          key,
          signature,
          encoder.encode(`${RECEIPT}\n${canonical(payload)}\n`),
        ))
      )
        fail('Review signature verification failed.');
      const trusted = await store.get(`trust:${reviewer.key_sha256}`);
      const ownKey = (await profile())?.key_sha256 === reviewer.key_sha256;
      const sameName =
        context.analyst && normalizedName(context.analyst) === normalizedName(reviewer.name);
      return {
        receipt,
        id: await digest(`${canonical(receipt)}\n`),
        signature_valid: true,
        trusted: Boolean(
          !ownKey &&
          !sameName &&
          trusted &&
          trusted.name === reviewer.name &&
          canonical(trusted.public_key) === canonical(reviewer.public_key),
        ),
        own_key: ownKey,
        same_analyst_name: Boolean(sameName),
        reviewer,
      };
    }
    async function sign(context, decision, note, passphrase) {
      const saved = await store.get('profile');
      if (!saved) fail('Create your reviewer identity first.');
      if (context.analyst && normalizedName(context.analyst) === normalizedName(saved.name)) {
        fail('The analyst cannot sign their own independent review.');
      }
      const identity = await card(saved.name, saved.public_key);
      const payload = {
        ...contextFields(context),
        reviewer_name: identity.name,
        reviewer_key_sha256: identity.key_sha256,
        decision,
        note: note.trim(),
        created_at: new Date().toISOString(),
      };
      const signature = await cryptography.subtle.sign(
        signing,
        await unlock(saved, passphrase),
        encoder.encode(`${RECEIPT}\n${canonical(payload)}\n`),
      );
      const receipt = {
        schema_version: RECEIPT,
        payload,
        public_key: identity.public_key,
        signature: base64(signature),
      };
      const checked = await inspect(receipt, context);
      await store.put(`issued:${context.package_sha256}:${checked.id}`, receipt);
      return receipt;
    }
    async function receive(receipt, context) {
      const checked = await inspect(receipt, context);
      if (!checked.trusted)
        fail(
          'Confirm the reviewer key through a separate trusted channel before accepting this review.',
        );
      await store.put(`receipt:${context.package_sha256}:${checked.id}`, receipt);
      return checked;
    }
    async function receipts(context) {
      contextFields(context);
      const stored = await store.list(`receipt:${context.package_sha256}:`);
      return Promise.all(stored.map((receipt) => inspect(receipt, context)));
    }
    return {
      profile,
      createProfile,
      trustReviewer,
      sign,
      inspect,
      receive,
      receipts,
      trustedReviewers: () => store.list('trust:'),
      async forgetReviewer(fingerprint) {
        if (!hex.test(fingerprint)) fail('Invalid reviewer fingerprint.');
        await store.delete(`trust:${fingerprint}`);
        announceTrustChange();
      },
      async issued(context) {
        contextFields(context);
        const stored = await store.list(`issued:${context.package_sha256}:`);
        return Promise.all(stored.map((receipt) => inspect(receipt, context)));
      },
    };
  }
  window.OmphalosReviewer = { ...create(), create };
})();
