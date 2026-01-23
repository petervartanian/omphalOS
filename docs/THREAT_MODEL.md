# omphalOS Threat Model

## Overview

This document articulates the security assumptions, threat actors, attack vectors, and mitigations for omphalOS. The system is designed for adversarial environments where analytical integrity is paramount and multiple actors have incentives to compromise, manipulate, or discredit the analytical process.

## Threat Actors

### Sanctions Evaders / Proliferators (External Adversaries)

Motivation: Avoid detection, continue illicit trade.

Capabilities include (i) sophisticated understanding of detection techniques, (ii) resources to develop evasion strategies, (iii) ability to adapt tradecraft in response to enforcement actions.

Attack vectors include (i) data poisoning submitting false trade declarations to corrupt world-states, (ii) adversarial evasion structuring transactions to avoid triggering investigations, (iii) social engineering attempting to learn investigation logic through FOIA, litigation discovery, insider recruitment.

Out of Scope for omphalOS: The system does not defend against evasion—it surfaces patterns for human review. Evasion is an analytical challenge, not a system security vulnerability.

### Malicious Insiders (Internal Adversaries)

Motivation: Sabotage, espionage, corruption.

Capabilities include (i) legitimate access to systems and data, (ii) knowledge of investigative priorities, (iii) ability to modify code, data, or packets.

Attack vectors include (i) result manipulation altering packets to hide findings or fabricate evidence, (ii) investigation sabotage modifying SQL to produce false negatives (hide evaders) or false positives (harm competitors), (iii) data exfiltration exporting sensitive data disguised as legitimate analytical products.

omphalOS mitigations include (i) checksumming where any packet modification invalidates verification, (ii) polycentric verification requiring multiple independent implementations to agree such that compromising one is insufficient, (iii) export gates scanning for exfiltration of credentials or sensitive data patterns, (iv) audit logs recording all case runs, verifications, and exports with timestamps and operator IDs (implementation-dependent).

### Compromised Dependencies (Supply Chain Attacks)

Motivation: Espionage, sabotage by nation-states or organized crime.

Capabilities include (i) injecting malicious code into upstream dependencies (Python packages, system libraries), (ii) distributing backdoored toolchains.

Attack vectors include (i) dependency confusion tricking pip into installing malicious package with same name as internal package, (ii) compromised PyPI packages where widely-used libraries (e.g., requests, pandas) are backdoored, (iii) compiler backdoors where toolchain itself injects malicious code (cf. Ken Thompson's "Reflections on Trusting Trust").

omphalOS mitigations include (i) minimal dependencies where reference Python runtime uses only stdlib + SQLite (no external packages), (ii) offline operation with no runtime network calls preventing dependencies from phoning home, (iii) pack signing where all distributed packs are cryptographically signed enabling tampering detection, (iv) polycentric verification where Rust and Go verifiers use different toolchains making simultaneous compromise of all three harder.

Residual Risk: If the entire toolchain (Python interpreter, Rust compiler, Go compiler, OS) is compromised, omphalOS cannot defend. This is accepted risk—defenses at this level require hardware-root-of-trust (e.g., TPM, secure enclaves).

### 4. Adversarial Legal Challenges (Procedural Attacks)

**Motivation**: Overturn enforcement actions, delegitimize analytical process

**Capabilities**:
- Skilled defense attorneys
- Expert witnesses challenging methodology
- Discovery requests for source code, training data, analyst notes

**Attack Vectors**:
- **Algorithmic bias claims**: Argue that investigations disproportionately flag certain countries/ethnicities/industries
- **Black-box opacity**: Argue that analytical process is inscrutable and therefore unfair
- **Non-reproducibility**: Demand re-execution of investigations; if results differ, claim unreliability

**omphalOS Mitigations**:
- **Transparency**: All SQL is human-readable and version-controlled
- **Reproducibility**: Checksummed artifacts enable bit-identical re-execution
- **Epistemic humility**: Canon/Margin headers document analytical restraint; packets explicitly record unknowns
- **Audit trails**: Run manifests capture exact versions of code/data used; adversaries can verify

**Design Philosophy**: omphalOS assumes that analytical methods *will* be disclosed in adversarial proceedings. Rather than security through obscurity, the system is designed to be **defensible under full disclosure**.

### 5. Congressional Oversight / IG Audits (Accountability Mechanisms)

**Motivation**: Ensure lawful, effective use of government resources

**Capabilities**:
- Subpoena power
- Access to classified systems and data
- Expert staff and contracted auditors

**Attack Vectors** (in the sense of stress-testing the system):
- **Waste, fraud, abuse claims**: Investigate whether system is cost-effective, whether false positives harm businesses unjustly
- **Privacy concerns**: Examine whether PII or BCI is improperly retained or disclosed
- **Methodological challenges**: Hire statisticians to assess whether investigations are analytically sound

**omphalOS Response**:
- **Auditability**: Every claim is traceable to SQL queries; every SQL query is traceable to domain expertise
- **Privacy by design**: Packets contain aggregates, not raw individual records
- **Cost transparency**: Open-source system; no vendor lock-in; computational costs measurable

**Design Philosophy**: Oversight is **not a threat**—it is a requirement. omphalOS is designed to make oversight *easy* by structuring all decisions as auditable artifacts.

## Attack Scenarios and Mitigations

### Scenario 1: Malicious Insider Fabricates Evidence

**Attack**: Analyst modifies `packet.json` to falsely claim that Entity X has unusual payment patterns, then exports it to justify an enforcement action against a competitor.

**Detection**:
1. Verification (`omphalos.cli case verify`) recomputes checksums
2. Checksums don't match manifest → FAIL
3. Supervisor reviewing packet sees verification failure, investigates

**Mitigation Robustness**: Strong. Modification requires either:
- Recomputing checksums (requires modifying run.json, which is also checksummed)
- Compromising verification logic (requires code changes that would be visible in version control)

**Residual Risk**: If insider has commit access and can modify both packet and run manifest atomically, detection requires code review of commits. This is accepted risk—defense requires separation of duties (analyst role vs. code maintainer role).

### Scenario 2: SQL Injection via Case Definition

**Attack**: Analyst defines a case with malicious SQL embedded in case_id or investigation selection:

```json
{
  "case_id": "'; DROP TABLE shipments; --",
  "investigations": ["cat_00001"]
}
```

**Mitigation**:
- Case IDs are used only in file paths, not SQL queries
- Investigation IDs are validated against catalog before execution
- SQL investigations are **static files**, not dynamically constructed strings

**Mitigation Robustness**: Strong. omphalOS does not construct SQL dynamically from user input. SQL injection vectors do not exist in the reference implementation.

**Residual Risk**: If analysts write custom investigations with dynamic SQL (e.g., using Python f-strings to inject parameters), SQL injection becomes possible. This is a *code quality* issue, not a *system design* issue. Mitigation: code review of custom investigations.

### Scenario 3: Data Poisoning via Corrupted World Packs

**Attack**: Adversary distributes a malicious world pack that contains backdoored data (e.g., all their transactions are missing, competitor transactions are duplicated).

**Mitigation**:
1. Packs are cryptographically signed by release manager
2. Pack verification checks signatures before installation
3. Unsigned or invalid-signature packs are rejected

**Mitigation Robustness**: Strong, assuming key management is sound. If release manager's signing key is compromised, adversary can sign malicious packs.

**Residual Risk**: Key compromise. Mitigation requires:
- Hardware security modules (HSMs) for key storage
- Multi-party signing (require 2-of-3 signatures for pack release)
- Transparency logs (public append-only log of all pack releases)

### Scenario 4: Adversarial Evasion Based on Leaked Investigation Logic

**Attack**: Adversary obtains catalog SQL (via FOIA, litigation discovery, or GitHub). They structure transactions to avoid triggering known patterns (e.g., if `payment_count >= 3` triggers alerts, they ensure `payment_count = 2`).

**Mitigation**:
- Investigations are **diverse**: 20,000 patterns covering multiple hypotheses
- Investigations **evolve**: Catalog is continuously updated as evasion techniques become known
- Investigations are **hypothesis-generating**: Even if one pattern is evaded, others may surface related signals

**Mitigation Robustness**: Moderate. Evasion is fundamentally an arms race. omphalOS cannot prevent evasion, but it can make evasion *costly* by requiring adversaries to evade thousands of patterns simultaneously.

**Design Philosophy**: omphalOS assumes investigation logic *will* be disclosed. Rather than relying on secrecy, the system is designed for **rapid evolution**. The cost to adversaries of adapting to 20,000 patterns is higher than the cost to defenders of generating new patterns.

### Scenario 5: Timing Side-Channel Attack

**Attack**: Adversary submits trade declarations and measures system response time. Faster response suggests their transactions didn't trigger complex investigations; slower response suggests they did. This leaks information about which patterns they triggered.

**Mitigation**: None in current implementation.

**Mitigation Robustness**: Weak. Timing side-channels are difficult to eliminate without constant-time operations, which are impractical for complex SQL queries.

**Residual Risk**: Accepted. Timing side-channels may leak *whether* an entity was flagged, but not *why* or *what the findings were*. This is considered low-severity. Mitigation in future versions could include:
- Constant-time query execution (add dummy work to equalize runtime)
- Batched processing (all cases run at fixed intervals, adversary cannot correlate submission time with execution time)

### Scenario 6: Packet Exfiltration via Steganography

**Attack**: Malicious analyst embeds sensitive data (e.g., full warehouse contents) in packet using steganography (e.g., encoding data in whitespace, unicode homoglyphs, or JSON field ordering).

**Mitigation**:
- Export gates scan for known credential patterns
- Packets are JSON (limited steganographic capacity compared to images/binaries)
- Checksums make covert channels detectable (any modification changes checksum)

**Mitigation Robustness**: Moderate. Export gates catch *known* patterns but cannot detect *novel* encoding schemes. Deep inspection (analyzing file size, entropy, structural anomalies) would be needed for robust defense.

**Residual Risk**: Accepted. Defending against all steganographic channels requires prohibitive inspection costs. Mitigation: audit logs + anomaly detection (flag packets with unusual file sizes or structural complexity).

## Security Properties

omphalOS provides the following security properties:

### 1. Integrity (Strong)

**Property**: Packets are tamper-evident. Any modification is detectable via checksum verification.

**Guarantees**: If verification succeeds, the packet matches the declared run artifacts.

**Limitations**: Does not prevent tampering, only *detects* it. If verification is skipped, tampering is undetected.

### 2. Authenticity (Moderate)

**Property**: Packs are signed by release manager. Only authorized releases can be installed.

**Guarantees**: If pack verification succeeds, the pack was signed by holder of signing key.

**Limitations**: Depends on key management. If signing key is compromised, adversary can sign malicious packs.

### 3. Confidentiality (Weak)

**Property**: Packets contain aggregates, not raw records, reducing disclosure risk.

**Guarantees**: Individual transaction details are not directly included in exported packets.

**Limitations**:
- Aggregates can be inverted if adversary has auxiliary information (e.g., "Top 3 entities by shipment volume" + knowledge that adversary is #1 → adversary learns #2 and #3)
- Warehouses contain full raw data; if warehouse is exfiltrated, confidentiality is lost

**Design Philosophy**: omphalOS is not designed for multi-party computation or differential privacy. It assumes data is *already* classified and system operates within a secure perimeter. Packets are designed to minimize disclosure when crossing classification boundaries, but this is *risk reduction*, not *guarantee*.

### 4. Availability (Moderate)

**Property**: System operates offline; no dependency on external services.

**Guarantees**: If system is installed, it remains operational even if disconnected from internet/network.

**Limitations**: Denial-of-service via resource exhaustion (e.g., malicious case that runs queries consuming all disk/CPU) is possible. Mitigation: resource quotas, query timeouts.

### 5. Auditability (Strong)

**Property**: Every analytical decision is traceable to versioned code and checksummed data.

**Guarantees**: Given a packet, auditors can reconstruct the exact conditions under which it was produced and verify the results.

**Limitations**: Requires that version control and run manifests are preserved. If commit history is lost or manifests are deleted, auditability is compromised.

## Operational Security Recommendations

### For Analysts

1. **Never embed credentials in cases or SQL queries**: Even synthetic credentials trigger export gates and cause packet rejection.

2. **Use version control for custom investigations**: All custom SQL should be committed with descriptive messages explaining the hypothesis.

3. **Verify before exporting**: Always run `omphalos.cli case verify` before `omphalos.cli export`. Don't export packets with failed verification.

4. **Document unknowns**: When packet claims omit expected information, note why (data unavailable, investigation not designed for this scenario, etc.).

5. **Review verification logs**: If verification fails unexpectedly, investigate before assuming system bug—may indicate tampering attempt.

### For System Administrators

1. **Protect signing keys**: Store pack signing keys in HSMs or encrypted vaults. Use multi-party signing for production releases.

2. **Enable audit logging**: Log all case runs, verifications, and exports with operator IDs and timestamps.

3. **Separate roles**: Analysts should not have commit access to investigation catalog. Catalog changes should go through code review.

4. **Monitor for anomalies**: Flag unusual patterns (analyst running 1000 cases in a day, packet sizes suddenly 10x larger, verification failure rates spiking).

5. **Secure world data**: Warehouses contain raw sensitive data. Apply appropriate filesystem ACLs, encryption at rest, and access auditing.

### For Oversight Bodies

1. **Request verification reports**: When reviewing packets, demand verification output confirming checksums match.

2. **Audit investigation logic**: Randomly sample investigations from catalog and have independent statisticians review for methodological soundness.

3. **Test reproducibility**: Select closed cases, obtain original run artifacts, re-execute, confirm results match.

4. **Assess false positive rates**: Require agencies to report how many flagged entities were ultimately determined to be false positives. High rates suggest investigations need refinement.

## Non-Goals

The following are explicitly **not** security goals of omphalOS:

### 1. Prevention of Adversarial Evasion

omphalOS surfaces patterns; it does not prevent adversaries from structuring transactions to avoid those patterns. Evasion is an analytical challenge addressed through continuous evolution of investigation catalog, not a security vulnerability.

### 2. Multi-Party Computation

omphalOS does not enable secure computation over data from multiple mutually-distrusting parties (e.g., US + allies pooling trade data without revealing individual records). This requires cryptographic MPC techniques (homomorphic encryption, secure enclaves) beyond current scope.

### 3. Real-Time Threat Prevention

omphalOS is batch-oriented (load world, run cases, produce packets). It does not operate as a real-time firewall blocking transactions. Real-time prevention requires different architecture (streaming event processing, low-latency decision logic).

### 4. Differential Privacy

Packets contain aggregates that may enable reconstruction of individual records given auxiliary information. True differential privacy (formal guarantees of indistinguishability) is not provided.

## Future Security Enhancements

### 1. Formal Verification (Planned)

Extend Rust verifier to generate machine-checked proofs that investigations satisfy security properties:
- **No SQL injection**: Query construction is provably safe
- **Deterministic results**: Same input always produces same output
- **Bounded disclosure**: Packets provably omit PII/BCI beyond specified aggregates

### 2. Transparency Logs (Planned)

Maintain append-only public log of all pack releases:
- Each release hashed and timestamped
- Log is Merkle-tree-structured for efficient verification
- Adversaries cannot retroactively "unpublish" packs to hide vulnerabilities

### 3. Multi-Party Signing (Planned)

Require 2-of-3 signatures for pack releases:
- Release manager + senior analyst + compliance officer
- Prevents single compromised key from poisoning packs

### 4. Secure Enclaves (Research)

Investigate running omphalOS inside Intel SGX or ARM TrustZone:
- Protect world data and queries even from OS/hypervisor
- Enable MPC-like properties (analyst sees packets, not raw data)

## Conclusion

omphalOS operates in a threat environment with sophisticated adversaries, insider risk, supply chain concerns, and adversarial legal challenges. The system's security properties are designed for **transparency, auditability, and tamper-evidence** rather than secrecy or prevention.

The core security insight: In adversarial settings, the best defense is not obscurity but **legibility**. Make the analytical process so transparent that tampering is obvious, evasion is costly, and challenges are addressable. omphalOS enables oversight by making every analytical decision auditable, reproducible, and contestable.

Security is not a feature list—it is a design philosophy. omphalOS embodies the principle that intelligence analysis must be **strong enough to withstand scrutiny**, not hidden to avoid it.
