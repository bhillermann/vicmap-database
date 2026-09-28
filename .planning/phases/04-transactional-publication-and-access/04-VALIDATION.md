---
phase: "04"
slug: "transactional-publication-and-access"
# status lifecycle: draft (seeded by plan-phase) → validated (set by validate-phase §6)
# audit-milestone §5.5 distinguishes NOT-VALIDATED (draft) from PARTIAL (validated + nyquist_compliant: false) (#2117)
status: validated
nyquist_compliant: true
wave_0_complete: true
created: "2026-09-23"
validated: "2026-09-28"
---

# Phase 04 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | Python stdlib `unittest` (run inside the Nix devshell) |
| **Config file** | none — `flake.nix` devshell provides the interpreter and `psycopg` |
| **Quick run command** | `nix develop path:. -c python -m unittest tests.test_evidence tests.test_publish tests.test_publish_order -v` |
| **Full suite command** | `nix develop path:. -c python -m unittest discover -s tests -p 'test_*.py'` |
| **Live DB run** | `VICMAP_TEST_POSTGRES_DSN=<dsn> VICMAP_TEST_POSTGRES_SUPERUSER_DSN=<superuser-dsn> nix develop path:. -c python -m unittest tests.test_publish tests.test_publish_order -v` |
| **Estimated runtime** | ~8 s phase modules offline; ~50 s full suite with live DSNs |

Live-DB test classes skip (not fail) when `VICMAP_TEST_POSTGRES_DSN` / `VICMAP_TEST_POSTGRES_SUPERUSER_DSN` are unset. Both are exported by the operator's gitignored `.envrc` (passwords from opnix); the loader DSN must be exported *after* `use flake` so `$VICMAP_DB_PASSWORD` is resolved.

---

## Sampling Rate

- **After every task commit:** Run the quick run command
- **After every plan wave:** Run the full suite command
- **Before `/gsd-verify-work`:** Full suite must be green with live DSNs set (0 skipped)
- **Max feedback latency:** ~50 seconds (live)

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 04-01-01 | 01 | 1 | EVID-02 | — | New reason codes map to a closed stage + hint | unit | `python -m unittest tests.test_evidence` | ✅ | ✅ green |
| 04-01-02 | 01 | 1 | EVID-02 | T-04-02 | `READER_WRITE_NOT_DENIED` hint says revoke, never retry | unit | `python -m unittest tests.test_evidence` | ✅ | ✅ green ¹ |
| 04-01-03 | 01 | 1 | EVID-01 | — | `publication_summary` rejects unsafe fields; no partial event | unit | `python -m unittest tests.test_evidence` | ✅ | ✅ green |
| 04-02-01 | 02 | 1 | PUB-04 | — | Reader role distinct from loader in config | unit | `python -m unittest tests.test_staging.DatabaseConfigTest` | ✅ | ✅ green |
| 04-02-02 | 02 | 1 | PUB-01, PUB-04 | T-04-02 | Loader append-only on audit; reader USAGE only, no write | static | plan inline `python -c` SQL checks (provision/least-privilege) | ✅ | ✅ green |
| 04-02-03 | 02 | 1 | PUB-04 | — | Reader password via opnix, never literal | static | plan inline `python -c` flake check | ✅ | ✅ green |
| 04-03-01 | 03 | 2 | PUB-01, EVID-01 | — | PASS row keyed by (run_ts, manifest_digest, target_table) | unit + live | `python -m unittest tests.test_manifest tests.test_staging` (`AuditValidationRecordTest` live) | ✅ | ✅ green |
| 04-03-02 | 03 | 2 | PUB-01 | — | Audit rows written only after successful `run_staging` | unit | `python -m unittest tests.test_staging` | ✅ | ✅ green |
| 04-04-01 | 04 | 3 | PUB-01, PUB-04 | T-04-04 | Catalog-discovered names; scoped drop, no CASCADE | unit + live | `python -m unittest tests.test_publish tests.test_staging.DriverImportPolicyTest` (`LivePromoteOneLayerTest`) | ✅ | ✅ green |
| 04-04-02 | 04 | 3 | PUB-01, PUB-02, PUB-03 | T-04-01, T-04-04 | All-or-nothing; prior tables survive failure; gate requires PASS rows | unit + live | `python -m unittest tests.test_publish` (`PromotionRollbackCompositionTest`, `LiveMultiLayerPromotionTest`, `LivePromotionRollbackTest`) | ✅ | ✅ green |
| 04-05-01 | 05 | 4 | PUB-05 | — | Real reader login discovers + spatially queries | unit + live | `python -m unittest tests.test_publish` (`ReaderVerificationTest`, `LiveReaderVerificationTest`) | ✅ | ✅ green |
| 04-05-02 | 05 | 4 | PUB-04 | T-04-02 | Writable reader hard-stops with `ReaderWriteNotDenied` | unit + live | `python -m unittest tests.test_publish` (`LiveReaderWriteDenialTest`, `LiveReaderWriteNotDeniedTest`) | ✅ | ✅ green |
| 04-06-01 | 06 | 5 | EVID-01 | — | Summary re-read from durable artifacts; redacted | unit | `python -m unittest tests.test_publish` | ✅ | ✅ green |
| 04-06-02 | 06 | 5 | EVID-01 | — | CLI composes promote → verify → summary | unit + live | `python -m unittest tests.test_publish` (`LivePublishOrderFullRunTest`) | ✅ | ✅ green |
| 04-06-03 | 06 | 5 | EVID-02 | — | Non-zero exit naming boundary; no secrets | unit | `python -m unittest tests.test_publish_order` | ✅ | ✅ green |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

¹ The plan's inline check for 04-01-02 hardcodes 16 stages / 41 reasons and fails (actual 20 / 54). This was a documented plan deviation (baseline was larger than estimated); the behavioral tests in `tests.test_evidence` are green. The stale literal is plan noise, not a code defect.

The 04-04 `checkpoint:decision` task (D-66/D-67 contract confirmation) is a human decision gate and has no automated verify by design.

---

## Wave 0 Requirements

Existing infrastructure covers all phase requirements.

---

## Manual-Only Verifications

All phase behaviors have automated verification.

The five `Live*` classes previously listed here (skip-stubs) were implemented as real fixture-provisioning tests on 2026-09-28 and run green against the live server.

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 60s (live)
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved 2026-09-28

---

## Validation Audit 2026-09-28

| Metric | Count |
|--------|-------|
| Gaps found | 5 |
| Resolved | 0 |
| Escalated | 5 (manual-only, by operator choice) |

Evidence: phase test modules `Ran 299 tests ... OK (skipped=42)` (skips are the live-DB classes, no DSN in this session); 15/16 plan inline checks pass, 1 stale literal (see ¹).

## Validation Audit 2026-09-28 (re-run)

| Metric | Count |
|--------|-------|
| Gaps found | 5 (prior manual-only live stubs) |
| Resolved | 5 |
| Escalated | 0 |

Evidence: full suite with both live DSNs set — `Ran 621 tests ... OK` (0 skipped). All seven `tests.test_publish` `Live*` classes and all four `AuditValidationRecordTest` cases executed and passed. Post-run catalog check: 0 `livetest%` schemas, 0 roles, 0 audit rows left behind.
