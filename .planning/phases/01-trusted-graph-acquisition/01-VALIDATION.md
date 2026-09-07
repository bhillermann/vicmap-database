---
phase: "01"
slug: "trusted-graph-acquisition"
status: ready
nyquist_compliant: true
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
| 01-01-01 | 01 | 1 | MAIL-01–MAIL-05 | T-01-01–T-01-05 | Production tracer proves the complete redacted mail-to-artifact path | end-to-end with fakes | `nix develop path:. -c python -m unittest tests.test_graph.PipelineTracerTest -v` | ❌ W0 | ⬜ pending |
| 01-01-02 | 01 | 1 | MAIL-01–MAIL-05 | T-01-01, T-01-04 | Whole-policy validation and import/runtime-state safety | unit | `nix develop path:. -c python -m unittest tests.test_graph -v` | ❌ W0 | ⬜ pending |
| 01-02-01 | 02 | 2 | MAIL-01 | T-01-02-01, T-01-02-02 | Memory-only authentication and exact configured mailbox | unit + adapter | `nix develop path:. -c python -m unittest tests.test_graph -v` | ❌ W0 | ⬜ pending |
| 01-02-02 | 02 | 2 | MAIL-02 | T-01-02-03–T-01-02-05 | Inclusive metadata-only query and complete read-only pagination | unit + adapter | `nix develop path:. -c python -m unittest tests.test_graph -v` | ❌ W0 | ⬜ pending |
| 01-03-01 | 03 | 2 | MAIL-02 | T-01-03-01, T-01-03-02 | Exact sender/subject/MIME/link/order recognition | unit | `nix develop path:. -c python -m unittest tests.test_candidates -v` | ❌ W0 | ⬜ pending |
| 01-03-02 | 03 | 2 | MAIL-03 | T-01-03-03, T-01-03-05 | Full-stream newest/tie selection and safe empty failure | unit | `nix develop path:. -c python -m unittest tests.test_candidates -v` | ❌ W0 | ⬜ pending |
| 01-04-01 | 04 | 2 | MAIL-04 | T-01-04-01–T-01-04-03 | Validate-before-send clean HTTPS redirect boundary | unit + mocked integration | `nix develop path:. -c python -m unittest tests.test_download -v` | ❌ W0 | ⬜ pending |
| 01-04-02 | 04 | 2 | MAIL-04, MAIL-05 | T-01-04-03–T-01-04-05 | Exact byte ceiling, checksum, cleanup, and atomic publication | unit + mocked integration | `nix develop path:. -c python -m unittest tests.test_download -v` | ❌ W0 | ⬜ pending |
| 01-05-01 | 05 | 3 | MAIL-01, MAIL-03, MAIL-05 | T-01-05-01 | Closed evidence vocabulary and adversarial disclosure regression | unit | `nix develop path:. -c python -m unittest tests.test_evidence -v` | ❌ W0 | ⬜ pending |
| 01-05-02 | 05 | 3 | MAIL-01–MAIL-05 | T-01-05-02–T-01-05-06 | Complete orchestration and controlled live provenance proof | full suite + live | `nix develop path:. -c python -m unittest discover -s tests -p 'test_*.py' -v` | ❌ W0 | ⬜ pending |

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

- [x] All tasks have `<automated>` verify and Wave 0 test ownership
- [x] Sampling continuity: every task has automated verification
- [x] Wave 0 plans cover all MISSING test references
- [x] No watch-mode flags
- [x] Feedback latency target is < 60s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** ready for execution; `wave_0_complete` remains false until the planned tests exist and pass.
