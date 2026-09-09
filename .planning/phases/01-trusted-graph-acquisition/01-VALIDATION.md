---
phase: "01"
slug: "trusted-graph-acquisition"
status: validated
nyquist_compliant: true
wave_0_complete: true
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
| 01-01-01 | 01 | 1 | MAIL-01–MAIL-05 | T-01-01–T-01-05 | Production tracer proves the complete redacted mail-to-artifact path | end-to-end with fakes | `nix develop path:. -c python -m unittest tests.test_graph.PipelineTracerTest -v` | ✅ | ✅ green |
| 01-01-02 | 01 | 1 | MAIL-01–MAIL-05 | T-01-01, T-01-04 | Whole-policy validation and import/runtime-state safety | unit | `nix develop path:. -c python -m unittest tests.test_graph -v` | ✅ | ✅ green |
| 01-02-01 | 02 | 2 | MAIL-01 | T-01-02-01, T-01-02-02 | Memory-only authentication and exact configured mailbox | unit + adapter | `nix develop path:. -c python -m unittest tests.test_graph -v` | ✅ | ✅ green |
| 01-02-02 | 02 | 2 | MAIL-02 | T-01-02-03–T-01-02-05 | Inclusive metadata-only query and complete read-only pagination | unit + adapter | `nix develop path:. -c python -m unittest tests.test_graph -v` | ✅ | ✅ green |
| 01-03-01 | 03 | 2 | MAIL-02 | T-01-03-01, T-01-03-02 | Exact sender/subject/MIME/link/order recognition | unit | `nix develop path:. -c python -m unittest tests.test_candidates -v` | ✅ | ✅ green |
| 01-03-02 | 03 | 2 | MAIL-03 | T-01-03-03, T-01-03-05 | Full-stream newest/tie selection and safe empty failure | unit | `nix develop path:. -c python -m unittest tests.test_candidates -v` | ✅ | ✅ green |
| 01-04-01 | 04 | 2 | MAIL-04 | T-01-04-01–T-01-04-03 | Validate-before-send clean HTTPS redirect boundary | unit + mocked integration | `nix develop path:. -c python -m unittest tests.test_download -v` | ✅ | ✅ green |
| 01-04-02 | 04 | 2 | MAIL-04, MAIL-05 | T-01-04-03–T-01-04-05 | Exact byte ceiling, checksum, cleanup, and atomic publication | unit + mocked integration | `nix develop path:. -c python -m unittest tests.test_download -v` | ✅ | ✅ green |
| 01-05-01 | 05 | 3 | MAIL-01, MAIL-03, MAIL-05 | T-01-05-01 | Closed evidence vocabulary and adversarial disclosure regression | unit | `nix develop path:. -c python -m unittest tests.test_evidence -v` | ✅ | ✅ green |
| 01-05-02 | 05 | 3 | MAIL-01–MAIL-05 | T-01-05-02–T-01-05-06 | Complete orchestration and controlled live provenance proof | full suite + live | `nix develop path:. -c python -m unittest discover -s tests -p 'test_*.py' -v` | ✅ | ✅ green |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [x] `tests/test_graph.py` — authentication, cutoff query, pagination, and metadata-only behavior
- [x] `tests/test_candidates.py` — sender, subject, order, link, and deterministic-selection policy
- [x] `tests/test_download.py` — URL authority, redirect, timeout, streaming-limit, cleanup, and hashing behavior
- [x] `tests/test_evidence.py` — stdout/stderr disclosure contract and redacted evidence
- [x] Shared fake message, response, and transport helpers local to tests
- [x] No framework install; `unittest` is part of the verified Nix runtime

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

**Approval:** validated after execution; all Wave 0 tests exist and pass.

---

## Requirement Coverage Audit

| Requirement | Automated behavioral evidence | Status |
|-------------|-------------------------------|--------|
| MAIL-01 | `PipelineTracerTest`, `ConfigurationTest`, `GraphAuthenticationBoundaryTest`, `ControllerDisclosureTest`, and `EvidenceContractTest` | ✅ covered |
| MAIL-02 | `GraphMetadataBoundaryTest` and `CandidateRecognitionTest`, including complete pagination, selective MIME, exact matching, and read-only source checks | ✅ covered |
| MAIL-03 | `CandidateSelectionTest`, `ControllerCompositionTest`, and redacted identity evidence tests | ✅ covered |
| MAIL-04 | `DownloadTargetPolicyTest`, `DownloadTransportBoundaryTest`, `DownloadStreamingBoundaryTest`, and no-fallback controller tests | ✅ covered |
| MAIL-05 | exact-limit, persisted-byte checksum/progress, tracer finalization, and final success evidence tests | ✅ covered |

## Validation Audit 2026-09-09

| Metric | Count |
|--------|-------|
| Phase tasks mapped | 10/10 |
| Requirements mapped | 5/5 |
| Deterministic tests run | 81 |
| Test failures or skips | 0 |
| Gaps found | 0 |
| Resolved | 0 |
| Escalated | 0 |

Audit commands:

- `nix develop path:. -c python -m unittest discover -s tests -p 'test_*.py' -v` — PASS, 81 tests in 0.093s.
- `nix develop path:. -c python -c "...01-LIVE-VERIFICATION.md..."` — PASS for controlled acquisition, tenant scope, artifact bytes/SHA-256, and redaction markers.

Conclusion: no missing or partial automated requirement coverage was found. The external tenant-scope and authentic-artifact observations remain recorded as complementary manual evidence; they do not replace the green deterministic coverage above.
