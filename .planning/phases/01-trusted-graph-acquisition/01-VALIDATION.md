---
phase: "01"
slug: "trusted-graph-acquisition"
status: draft
nyquist_compliant: false
wave_0_complete: false
created: "2026-09-07"
---

# Phase 01 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | Python 3.14.7 standard-library `unittest` / `unittest.mock` |
| **Config file** | none required |
| **Quick run command** | `nix develop path:. -c python -m unittest tests.test_candidates tests.test_evidence -v` |
| **Full suite command** | `nix develop path:. -c python -m unittest discover -s tests -p 'test_*.py' -v` |
| **Estimated runtime** | <60 seconds |

---

## Sampling Rate

- **After every task commit:** Run the touched test modules with `nix develop path:. -c python -m unittest <modules> -v`
- **After every plan wave:** Run `nix develop path:. -c python -m unittest discover -s tests -p 'test_*.py' -v`
- **Before `$gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 60 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 01-01-01 | 01 | 1 | MAIL-01 | T-01-01 | Memory-only token handling and disclosure-safe failures | unit + adapter | `nix develop path:. -c python -m unittest tests.test_graph tests.test_evidence -v` | ❌ W0 | ⬜ pending |
| 01-01-02 | 01 | 1 | MAIL-02, MAIL-03 | T-01-02 | Bounded metadata scan and deterministic redacted selection | unit + adapter | `nix develop path:. -c python -m unittest tests.test_graph tests.test_candidates tests.test_evidence -v` | ❌ W0 | ⬜ pending |
| 01-02-01 | 02 | 2 | MAIL-04 | T-01-03 | Redirect and size checks occur before data is trusted | unit + mocked integration | `nix develop path:. -c python -m unittest tests.test_download -v` | ❌ W0 | ⬜ pending |
| 01-02-02 | 02 | 2 | MAIL-05 | T-01-04 | Final artifact reports verified byte count and SHA-256 | unit + mocked integration | `nix develop path:. -c python -m unittest tests.test_download tests.test_evidence -v` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_graph.py` — authentication, cutoff query, pagination, and metadata-only behavior
- [ ] `tests/test_candidates.py` — sender, subject, order, link, and deterministic-selection policy
- [ ] `tests/test_download.py` — URL authority, redirect, timeout, streaming-limit, cleanup, and hashing behavior
- [ ] `tests/test_evidence.py` — stdout/stderr disclosure contract and redacted evidence
- [ ] Shared fake message, response, and transport helpers local to tests
- [ ] No framework install; `unittest` is part of the verified Nix runtime

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Controlled live acquisition from the configured mailbox | MAIL-01–MAIL-05 | Requires tenant credentials and an authentic Vicmap order | Run once with the configured environment, confirm exactly one artifact is finalized, and review stdout/stderr for credentials, message bodies, full message IDs, subjects, and complete URLs/query strings. |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 60s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
