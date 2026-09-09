---
phase: "01"
slug: "trusted-graph-acquisition"
status: verified
threats_open: 0
asvs_level: 1
created: "2026-09-09"
---

# Phase 01 — Security

> ASVS L1 verification of the plan-time STRIDE register against the implementation, tests, and controlled live evidence.

## Trust Boundaries

| Boundary | Control |
|----------|---------|
| Environment/TOML → CLI | Closed schema validation, environment-only credentials, memory-only OAuth tokens |
| Microsoft Graph → candidate policy | Exact mailbox, sender, subject, order, MIME cardinality, and deterministic selection |
| Message URL → artifact HTTPS | Separate clean session, exact HTTPS host allowlist, manual redirect validation |
| HTTPS stream → filesystem | Time/byte bounds, mode-0600 temporary state, hashing, atomic no-overwrite publication |
| Runtime → operator evidence | Closed event vocabulary with masked identities and bounded fingerprints |

## Threat Register

| Threat IDs | Category | Severity | Disposition | Verified mitigation | Status |
|------------|----------|----------|-------------|---------------------|--------|
| T-01-01–T-01-05 | disclosure, spoofing, DoS, tampering | high–medium | mitigate | Memory-only auth, exact candidate policy, isolated HTTPS, bounded streaming, atomic publication | closed |
| T-01-06 | repudiation | low | accept | Redacted fingerprints and full artifact digest are sufficient for the one-run proof; durable audit state is deferred | closed |
| T-01-02-01–T-01-02-04 | disclosure, elevation of privilege, DoS | high–medium | mitigate | MemoryTokenBackend, exact mailbox selection, bounded metadata iteration, and the required operator-attested read-only resource scope | closed |
| T-01-02-05 | tampering | low | accept | The adapter exposes only read operations; server-side mutation auditing is outside Phase 01 | closed |
| T-01-03-01–T-01-03-03, T-01-03-05 | spoofing, tampering, repudiation, disclosure | high–medium | mitigate | Exact sender/subject/order/link recognition, total ordering, and closed errors | closed |
| T-01-03-04 | denial of service | low | accept | Processing is bounded by the configured lookback and incremental parsing | closed |
| T-01-04-01–T-01-04-05 | spoofing, disclosure, DoS, tampering | high–medium | mitigate | Validate-before-send, clean session, redirects/timeouts/limits, exact hashing, private no-overwrite finalization | closed |
| T-01-04-06 | repudiation | low | accept | Local digest/evidence is sufficient for Phase 01; durable remote audit state is deferred | closed |
| T-01-05-01–T-01-05-06 | disclosure, spoofing, elevation of privilege, repudiation, tampering, DoS | high–medium | mitigate | Closed evidence, one-call orchestration, operator-attested tenant scope, live provenance, independent integrity check, inherited bounds | closed |

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| AR-01 | T-01-06 | Durable audit state is outside Phase 01; redacted run correlation and SHA-256 meet this phase's proof goal | plan disposition | 2026-09-09 |
| AR-02 | T-01-02-05 | Read-only adapter surface is enforced locally; external mailbox mutation auditing is outside scope | plan disposition | 2026-09-09 |
| AR-03 | T-01-03-04 | Current bounded-window and incremental parsing controls are proportionate to the low-severity risk | plan disposition | 2026-09-09 |
| AR-04 | T-01-04-06 | Local final digest and redacted evidence meet Phase 01; remote audit persistence is deferred | plan disposition | 2026-09-09 |

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-09-09 | 28 | 28 | 0 | gsd-security-auditor |

The deterministic suite passed 81 tests with no failures or skips. No unregistered SUMMARY threat flags were found.

## Sign-Off

- [x] All threats have a disposition
- [x] Accepted risks are documented
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-09-09
