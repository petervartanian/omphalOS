# Contributing to omphalOS

Thank you for your interest in contributing to omphalOS. This document outlines how to contribute code, investigations, documentation, and bug reports.

## Code of Conduct

Be professional, respectful, and constructive. This is a tool for serious analytical work—maintain that standard in all interactions.

## How to Contribute

### 1. Bug Reports

Use GitHub Issues to report bugs. Include:
- What you did (exact commands, case definitions)
- What you expected
- What actually happened
- System information (OS, Python version, omphalOS commit SHA)

### 2. Investigation Contributions

Have a novel pattern for detecting evasion/proliferation? Contribute it:

**Steps**:
1. Write SQL investigation following catalog conventions (Canon/Margin headers, CTE structure, LIMIT clause)
2. Place in `core/sql/investigations/custom/custom_<initials>_<date>_<description>.sql`
3. Create test case with synthetic data showing the pattern
4. Document false positive scenarios
5. Submit pull request with investigation + test + docs

**Example**:
```sql
-- Investigation: custom_jd_20260123_circular_flows
-- Domain: all
-- Intent: Detect circular shipment patterns (A→B→A)
-- [Canon 01-60 + Margin 001-045]
WITH ...
```

### 3. Documentation Improvements

Found unclear docs? Submit PR with improvements. Follow existing tone (technical but accessible).

### 4. Code Contributions

**Before coding**:
- Open an issue describing what you want to build
- Discuss approach with maintainers
- Get approval before significant work

**Code standards**:
- Python: Follow PEP 8, use `black` formatter
- Rust: Use `rustfmt`
- Go: Use `gofmt`
- All code must include docstrings/comments
- No external dependencies without approval (offline-first requirement)

**Testing**:
- All new investigations must have test cases
- All code changes must not break existing tests
- Run `pytest` before submitting

### 5. Security Contributions

Found a vulnerability? See SECURITY.md for responsible disclosure process.

**Do NOT** open public issues for security vulnerabilities.

## Contribution Requirements

### What You Can Submit

✅ **Allowed**:
- SQL investigations using synthetic data
- Documentation improvements
- Bug fixes
- Performance optimizations
- New verifiers (additional languages)
- UI enhancements
- Test cases

❌ **Prohibited**:
- Real trade data, PII, BCI, or classified information
- Credentials, API keys, or secrets (even fake ones that look real)
- Copyrighted material without attribution
- Malicious code or backdoors

### Data Requirements

**CRITICAL**: All contributed data must be **synthetic and non-identifiable**.

- Do NOT include real company names, addresses, or transaction records
- Do NOT include data derived from classified sources
- Do NOT include proprietary data from commercial providers

When in doubt, generate synthetic test data using omphalOS's world builder.

## Pull Request Process

1. **Fork** the repository
2. **Create branch**: `git checkout -b feature/your-feature-name`
3. **Make changes**: Follow code standards above
4. **Test**: Ensure `pytest` passes, run verification on sample cases
5. **Commit**: Use clear commit messages explaining *why*, not just *what*
6. **Push**: `git push origin feature/your-feature-name`
7. **Open PR**: Describe changes, link to related issues, explain testing performed

**PR Requirements**:
- Passes all CI checks (linting, tests, pack verification)
- Includes documentation updates if changing user-facing behavior
- Includes test cases for new functionality
- No merge conflicts with `main`

## Review Process

Maintainers will review within 7 days. Expect:
- Questions about design choices
- Requests for additional tests or documentation
- Style/formatting feedback

**Be patient**. This is a system used for national security work—thoroughness matters more than speed.

## License

By contributing, you agree that your contributions will be licensed under CC0 (public domain). You affirm that:
- You have the right to submit the contribution
- The contribution is your original work or properly attributed
- The contribution contains no classified, proprietary, or sensitive information

## Recognition

Contributors will be acknowledged in:
- `CONTRIBUTORS.md` file (if substantial contribution)
- Release notes for version where contribution appears
- Academic publications citing omphalOS (if contribution is methodologically significant)

## Questions?

Open a GitHub Discussion (not an Issue) for:
- How to implement a feature
- Design questions
- General usage questions

Use Issues only for bugs and concrete feature requests.

---

**Thank you for helping make intelligence analysis more transparent, reproducible, and defensible.**
