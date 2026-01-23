# Security Policy

## Reporting a Vulnerability

**DO NOT** open public GitHub issues for security vulnerabilities.

Instead, report privately via one of these channels:

1. **GitHub Security Advisories**: Use the "Security" tab → "Report a vulnerability"
2. **Email**: Contact the repository owner directly (see profile)
3. **Encrypted email**: PGP key available on request

### What to Include

- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if you have one)
- Whether you plan to publicly disclose (and timeline)

### Response Timeline

- **Acknowledgment**: Within 72 hours
- **Initial assessment**: Within 7 days
- **Fix and disclosure**: Coordinated with reporter (typically 30-90 days)

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| main    | ✅ Yes             |
| 1.x     | ✅ Yes             |
| < 1.0   | ❌ No (pre-release)|

## Security Considerations

### What omphalOS Protects Against

✅ **Defended**:
- Packet tampering (checksums detect modifications)
- SQL injection (investigations are static files, not dynamic queries)
- Credential leakage (export gates block known patterns)
- Supply chain attacks (pack signing, polycentric verification)

⚠️ **Partially Defended**:
- Insider threats (audit logging helps, but authorized users can access data)
- Data poisoning (synthetic worlds are safe, but real data imports need validation)
- Timing side-channels (not currently mitigated)

❌ **Not Defended**:
- Physical access attacks (if attacker has physical access to system, assume compromise)
- Social engineering (can't prevent users from being tricked into running malicious commands)
- Zero-day OS/Python vulnerabilities (omphalOS relies on underlying platform security)

### Security Assumptions

omphalOS assumes:
1. **Secure environment**: Deployed on trusted hardware in controlled facilities
2. **Authorized users**: All users have appropriate clearances and need-to-know
3. **Network isolation**: Air-gapped or heavily firewalled
4. **Physical security**: SCIF-level protections for classified deployments

### Known Limitations

1. **SQLite security**: Warehouses are not encrypted. Apply filesystem-level encryption.
2. **Export gates**: Pattern-based, not semantic. Novel encoding schemes may evade detection.
3. **Polycentric verification**: Only as secure as the most vulnerable verifier implementation.
4. **Pack signing**: Requires proper key management (HSMs recommended for production).

## Security Best Practices

### For Analysts

- **Never** commit real data to version control
- **Never** embed credentials in case definitions or SQL queries
- **Always** verify runs before exporting packets
- **Use** export gates before transferring packets across classification boundaries
- **Enable** full-disk encryption on workstations

### For Administrators

- Apply OS-level security hardening (CIS benchmarks, STIGs)
- Use mandatory access controls (SELinux, AppArmor)
- Enable audit logging (`auditd` on Linux)
- Rotate pack signing keys annually
- Require two-factor authentication for system access
- Implement principle of least privilege (analysts can run cases, only admins install packs)

### For Developers

- Review all SQL for injection vulnerabilities before merging
- Scan dependencies for known CVEs (even though we minimize dependencies)
- Use static analysis tools (`bandit` for Python, `cargo audit` for Rust)
- Never disable export gates in production builds
- Document all cryptographic operations and key management procedures

## Vulnerability Disclosure Policy

We follow **coordinated disclosure**:

1. Reporter notifies maintainers privately
2. Maintainers acknowledge and assess severity
3. Fix is developed and tested
4. Fix is released (patch version bump)
5. Security advisory is published with attribution to reporter (if desired)
6. Public disclosure occurs **after** fix is available

**Timeline**: Typically 30-90 days from report to disclosure. Can be extended if fix is complex or requires coordination with other projects.

## Security Hall of Fame

Contributors who responsibly disclose vulnerabilities will be acknowledged here (with permission):

- *No vulnerabilities reported yet*

## Cryptographic Controls

### Current Implementation

- **Checksumming**: SHA-256 for artifact integrity
- **Pack signing**: GPG/PGP (RSA 4096 or Ed25519)
- **Verification**: Multiple independent implementations

### Planned Enhancements

- Formal verification of Rust verifier (machine-checked proofs)
- Hardware security module (HSM) integration for signing keys
- Transparency logs for pack releases (Merkle tree append-only)
- Secure enclaves (Intel SGX, ARM TrustZone) for sensitive computations

## Compliance

omphalOS is designed to support:

- **FISMA**: Federal Information Security Management Act
- **NIST SP 800-53**: Security and Privacy Controls
- **FIPS 140-2**: Cryptographic Module Validation (when using FIPS-mode Python/OpenSSL)
- **DISA STIGs**: Security Technical Implementation Guides

Certification artifacts available on request for government deployments.

## Contact

For security inquiries: See repository owner's contact information in GitHub profile.

For general questions: Use GitHub Discussions.

---

**Security is a shared responsibility. Report issues promptly, protect sensitive data, and help keep omphalOS trustworthy.**
