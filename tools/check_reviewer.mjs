// Execute the shipped review protocol with real WebCrypto and isolated stores.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import { webcrypto, createPublicKey, verify } from 'node:crypto';

const sandbox = { window: { crypto: webcrypto }, TextEncoder, Uint8Array, atob, btoa };
vm.createContext(sandbox);
vm.runInContext(readFileSync(new URL('../src/omphalos/ui/reviewer.js', import.meta.url), 'utf8'), sandbox);
const factory = sandbox.window.OmphalosReviewer.create;
function store() {
  const records = new Map();
  return {
    records,
    async get(key) { return structuredClone(records.get(key)); },
    async put(key, value) { records.set(key, structuredClone(value)); },
    async add(key, value) { assert.ok(!records.has(key)); records.set(key, structuredClone(value)); },
    async delete(key) { records.delete(key); },
    async list(prefix) { return [...records].filter(([key]) => key.startsWith(prefix)).map(([, value]) => structuredClone(value)); },
  };
}
const reviewerStore = store();
const analystStore = store();
const reviewer = factory({ store: reviewerStore, cryptography: webcrypto });
const analyst = factory({ store: analystStore, cryptography: webcrypto });
const context = { package_sha256: '1'.repeat(64), analysis_digest: '2'.repeat(64), run_id: 'run-001', review_id: 'review-001', analyst: 'Morgan Analyst' };
const note = 'The retained invoices support the explanation; obtain the missing end-user statement.';
const passphrase = 'Fictional reviewer testing passphrase 42';
const card = await reviewer.createProfile('Alex Reviewer', passphrase);
assert.equal((await reviewer.profile()).key_sha256, card.key_sha256);
assert.equal((await reviewer.createProfile('Alex Reviewer', passphrase)).key_sha256, card.key_sha256);
await assert.rejects(reviewer.createProfile('Another Name', passphrase), /already has/);
await analyst.createProfile('Morgan Analyst', passphrase);
const storedProfile = reviewerStore.records.get('profile');
assert.equal(storedProfile.private_key, undefined);
assert.equal(storedProfile.protected_key.format, 'pbkdf2-sha256-600000-aes256gcm/1');
assert.ok(!JSON.stringify(storedProfile).includes(passphrase));
await assert.rejects(reviewer.sign(context, 'approve', note, 'Incorrect passphrase 123'), /unlocked/);
assert.ok(!Object.keys(card).some(name => name.includes('private')));

const receipt = await reviewer.sign(context, 'request_changes', note, passphrase);
assert.equal((await reviewer.issued(context)).length, 1);
assert.equal((await reviewer.receipts(context)).length, 0);
const untrusted = await analyst.inspect(receipt, context);
assert.equal(untrusted.signature_valid, true);
assert.equal(untrusted.trusted, false);
await assert.rejects(analyst.receive(receipt, context), /separate trusted channel/);
await assert.rejects(analyst.trustReviewer(card, '0'.repeat(64)), /does not match/);
await assert.rejects(reviewer.trustReviewer(card, card.key_sha256), /own key/);
await analyst.trustReviewer(card, card.key_sha256);
const accepted = await analyst.receive(receipt, context);
assert.equal(accepted.trusted, true);
assert.equal((await analyst.receipts(context)).length, 1);
await analyst.receive(receipt, context);
assert.equal((await analyst.receipts(context)).length, 1, 'Repeated import is idempotent');

function canonical(value) {
  if (value && typeof value === 'object') return `{${Object.keys(value).sort().map(key => `${JSON.stringify(key)}:${canonical(value[key])}`).join(',')}}`;
  return JSON.stringify(value);
}
assert.equal(verify('sha256', Buffer.from(`omphalos-independent-review/1\n${canonical(receipt.payload)}\n`),
  { key: createPublicKey({ key: structuredClone(card.public_key), format: 'jwk' }), dsaEncoding: 'ieee-p1363' },
  Buffer.from(receipt.signature, 'base64url')), true, 'Independent Node/OpenSSL verification accepts protocol');

for (const field of ['package_sha256', 'analysis_digest', 'run_id', 'review_id']) {
  const changed = { ...context, [field]: field.endsWith('digest') || field.endsWith('sha256') ? 'a'.repeat(64) : 'another' };
  await assert.rejects(analyst.inspect(receipt, changed), /different package or decision/);
}
const alteredNote = structuredClone(receipt);
alteredNote.payload.note = 'All evidence has been confirmed and the case is approved.';
await assert.rejects(analyst.inspect(alteredNote, context), /signature verification failed/);
const alteredDecision = structuredClone(receipt);
alteredDecision.payload.decision = 'approve';
await assert.rejects(analyst.inspect(alteredDecision, context), /signature verification failed/);
await assert.rejects(analyst.inspect({ ...receipt, trusted: true }, context), /unsupported structure/);
await assert.rejects(analyst.inspect({ ...receipt, signature: receipt.signature + '=' }, context), /encoding/);
const attacker = factory({ store: store(), cryptography: webcrypto });
await attacker.createProfile('Alex Reviewer', passphrase);
const forgery = await attacker.sign(context, 'approve', 'This signature comes from a different key with the same display name.', passphrase);
assert.equal((await analyst.inspect(forgery, context)).trusted, false, 'Matching name cannot impersonate pinned key');
await assert.rejects(analyst.receive(forgery, context), /separate trusted channel/);
await assert.rejects(reviewer.sign({ ...context, analyst: 'ALEX REVIEWER' }, 'approve', note, passphrase), /own independent review/);
assert.equal((await analyst.inspect(receipt, { ...context, analyst: 'Alex Reviewer' })).trusted, false);
await assert.rejects(reviewer.sign(context, 'approve', '', passphrase), /reason/);
await assert.rejects(reviewer.sign(context, 'whatever', note, passphrase), /decision/);

const revised = await reviewer.sign(context, 'approve', 'The subsequently supplied end-user statement now resolves the recorded request.', passphrase);
await analyst.receive(revised, context);
assert.equal((await analyst.receipts(context)).length, 2, 'Contradictory receipts must both remain visible');
assert.equal((await analyst.receipts({ ...context, package_sha256: '3'.repeat(64) })).length, 0, 'Reviews cannot carry into changed artifacts');
await analyst.forgetReviewer(card.key_sha256);
assert.ok((await analyst.receipts(context)).every(item => !item.trusted), 'Revocation must immediately remove trusted status');
await analyst.trustReviewer(card, card.key_sha256);
const reopened = factory({ store: analystStore, cryptography: webcrypto });
assert.ok((await reopened.receipts(context)).every(item => item.trusted), 'Trust and receipts survive service reopen');
analystStore.records.set(`receipt:${context.package_sha256}:damaged`, alteredNote);
await assert.rejects(reopened.receipts(context), /signature verification failed/, 'Corrupt stored receipts fail closed');
console.log(JSON.stringify({ ok: true, protocol: 'omphalos-independent-review/1', cryptography: 'WebCrypto ECDSA P-256 / SHA-256', tests: ['key persistence', 'encrypted private key and passphrase unlock', 'external fingerprint trust', 'independent OpenSSL verification', 'exact package binding', 'tamper rejection', 'same-name impersonation', 'self-review rejection', 'conflicting receipts retained', 'revocation', 'reopen', 'corrupt storage'] }));
