# Case handoffs and independent review

omphalOS supports case exchange without an application server or subscription. Each participant works in their own browser or local workspace. It does not provide simultaneous editing, a central case database, organization accounts, or centrally enforced supervisor roles.

## Receive and continue a case

1. The analyst creates and downloads the evidence package in VI, Package.
2. The recipient chooses **Open → Open a case package** and inspects the verified preview.
3. **Add to my workspace** retains the original package, run, analysis, and assessment without changing their bytes. It creates separate local records and, when supported, a continuation case. Existing local work is not overwritten.
4. The recipient can inspect the findings and supporting records, or choose **Continue with these records** to begin new work. Source acceptance, plan authorization, results review, and assessment are not inherited as new approvals.

An identical import is idempotent. A conflicting run, local assessment, or current package is rejected; the application does not guess which colleague's work should win. Packages are exchanged using the organization's existing approved channel. Importing a package checks its inventory and bytes, not its author's identity or the truth of its contents. Archived code is never executed.

## Return a signed review

In Package, **Independent review** lets a reviewer create a signing identity and sign either **Approve this package** or **Request changes**, with one reason and next-step note. The signing key is encrypted in browser storage. A passphrase of at least 14 characters unlocks each signature; it is not sent to a server or retained by the application.

The reviewer downloads the signed receipt and public key card. The analyst opens the receipt against the same package and independently confirms the reviewer's complete key fingerprint through a trusted channel, such as an established phone call or organization directory. Copying a fingerprint from the untrusted receipt itself does not establish identity. An embedded key is never automatically trusted.

The signature binds the package's SHA-256 digest, run, analysis digest, assessment revision, decision, reviewer name, note, and claimed signing time. Any change fails verification. The same display name with a different key is untrusted. The interface rejects the current browser's key and the analyst's normalized name as independent review; these checks cannot prove that two different people are involved. A person can create multiple keys or misstate their name. Organizational identity, authority, and separation of duties still require external enrollment and policy.

Receipts remain separate from the original package so the reviewed bytes do not change. Send the original ZIP and signed receipt together. The original report's statement about absent supervisory approval describes the package when created; a later receipt does not rewrite it. A new assessment or regenerated package needs a review bound to its own exact digest. Multiple and conflicting receipts remain visible; claimed timestamps do not decide which one wins. Removing a trusted key immediately removes trusted status from its retained receipts.

## Storage and recovery

Case packages and workspace backups contain investigation records. Signing keys, reviewer trust, and signed receipts use a separate browser store and are not included in those backups. Download the signed receipt after signing or accepting it. Keep the public key card with your organization's reviewer records. Clearing browser storage removes these local records; forgetting the passphrase makes the signing key unusable. Establish a new key and confirm its fingerprint again if that happens. Existing downloaded signatures remain verifiable against the old public key.

Case files and receipts are not encrypted by the handoff feature. The encrypted signing key protects against reading the stored private key without the passphrase; it does not encrypt investigation evidence or defend a compromised device or malicious code served from the same origin. There is no remote recovery service, global revocation directory, trusted timestamp service, or organization login.

## Protocol and verification

The browser uses WebCrypto ECDSA P-256 with SHA-256. Public key fingerprints hash the domain-separated, canonical public JWK. Receipts use `omphalos-independent-review/1` and signatures over the domain-separated canonical payload. Canonical objects have sorted keys and JSON string encoding; the protocol does not claim RFC 8785 equivalence. Signatures use 64-byte IEEE P1363 encoding. Unknown fields and noncanonical base64url are rejected.

At rest, the private PKCS#8 key is encrypted using AES-256-GCM with a random 96-bit IV, a random 128-bit salt, and a PBKDF2-HMAC-SHA-256 key derived with 600,000 iterations. Public identity metadata is authenticated as additional data. On unlock, the private key is imported as nonexportable for signing; temporary plaintext byte arrays are cleared. JavaScript cannot guarantee erasure of all internal copies or strings.

`node tools/check_reviewer.mjs` exercises the shipped protocol with real WebCrypto, independently checks the signature with Node/OpenSSL, and tests tampering, wrong passphrases, key impersonation, changed packages, revoked trust, conflicting receipts, and corrupt local data. Browser testing additionally checks IndexedDB persistence and the visible workflow.

## Research basis

- [CIGIE's July 2025 investigation standards](https://www.ignet.gov/sites/default/files/files/Quality%20Standards%20for%20Investigations%20July-2025.pdf) address independence, balanced reporting, and recurring supervisory review. They apply to the specified OIG community; this feature is not a claim of agency compliance or a replacement for its review system.
- [BIS Know Your Customer guidance](https://www.bis.gov/node/1533) requires inquiry and reevaluation of red flags. A software observation or reviewer signature is not transaction clearance.
- [W3C Web Cryptography](https://www.w3.org/TR/webcrypto/) defines the browser primitives and key behavior used here.
- [OWASP cryptographic storage guidance](https://cheatsheetseries.owasp.org/cheatsheets/Cryptographic_Storage_Cheat_Sheet.html) describes deriving a key-encryption key from a passphrase. The [password storage guidance](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html) documents the selected PBKDF2 work factor. This choice is not a security certification.
