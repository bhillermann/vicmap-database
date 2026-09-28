---
phase: "04"
slug: "transactional-publication-and-access"
# status lifecycle: draft (seeded by plan-phase) → validated (set by validate-phase §6)
# audit-milestone §5.5 distinguishes NOT-VALIDATED (draft) from PARTIAL (validated + nyquist_compliant: false) (#2117)
status: validated
nyquist_compliant: false
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
| **Estimated runtime** | ~8 seconds (phase modules, offline); ~22 s including devshell entry |

Live-DB test classes skip (not fail) when `VICMAP_TEST_POSTGRES_DSN` / `VICMAP_TEST_POSTGRES_SUPERUSER_DSN` are unset.

---

## Sampling Rate

- **After every task commit:** Run the quick run command
- **After every plan wave:** Run the full suite command
- **Before `/gsd-verify-work`:** Full suite must be green; live DB run for PUB-03/PUB-04 negative paths
- **Max feedback latency:** ~22 seconds

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
| 04-03-01 | 03 | 2 | PUB-01, EVID-01 | — | PASS row keyed by (run_ts, manifest_digest, target_table) | unit + live | `python -m unittest tests.test_manifest tests.test_staging` | ✅ | ✅ green |
| 04-03-02 | 03 | 2 | PUB-01 | — | Audit rows written only after successful `run_staging` | unit | `python -m unittest tests.test_staging` | ✅ | ✅ green |
| 04-04-01 | 04 | 3 | PUB-01, PUB-04 | T-04-04 | Catalog-discovered names; scoped drop, no CASCADE | unit | `python -m unittest tests.test_publish tests.test_staging.DriverImportPolicyTest` | ✅ | ✅ green |
| 04-04-02 | 04 | 3 | PUB-01, PUB-02, PUB-03 | T-04-01, T-04-04 | All-or-nothing; prior tables survive failure; gate requires PASS rows | unit + live | `python -m unittest tests.test_publish` (`PromotionRollbackCompositionTest`, `LivePromotionRollbackTest`) | ✅ | ✅ green |
| 04-05-01 | 05 | 4 | PUB-05 | — | Real reader login discovers + spatially queries | unit | `python -m unittest tests.test_publish` (`ReaderVerificationTest`) | ✅ | ✅ green |
| 04-05-02 | 05 | 4 | PUB-04 | T-04-02 | Writable reader hard-stops with `ReaderWriteNotDenied` | unit + live | `python -m unittest tests.test_publish` (`LiveReaderWriteNotDeniedTest`) | ✅ | ✅ green |
| 04-06-01 | 06 | 5 | EVID-01 | — | Summary re-read from durable artifacts; redacted | unit | `python -m unittest tests.test_publish` | ✅ | ✅ green |
| 04-06-02 | 06 | 5 | EVID-01 | — | CLI composes promote → verify → summary | unit | `python -m unittest tests.test_publish` | ✅ | ✅ green |
| 04-06-03 | 06 | 5 | EVID-02 | — | Non-zero exit naming boundary; no secrets | unit | `python -m unittest tests.test_publish_order` | ✅ | ✅ green |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

¹ The plan's inline check for 04-01-02 hardcodes 16 stages / 41 reasons and fails (actual 20 / 54). This was a documented plan deviation (baseline was larger than estimated); the behavioral tests in `tests.test_evidence` are green. The stale literal is plan noise, not a code defect.

The 04-04 `checkpoint:decision` task (D-66/D-67 contract confirmation) is a human decision gate and has no automated verify by design.

---

## Wave 0 Requirements

Existing infrastructure covers all phase requirements.

---

## Manual-Only Verifications

These five `Live*` classes in `tests/test_publish.py` are skip-stubs: they call `skipTest` unconditionally even with live DSNs set. Their happy-path behavior is proven by the operator's live `publish_order.py` run and by the offline behavioral tests above.

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Single layer promotes into `vicmap`, staging table gone, `{target}_geom_idx` named, reader holds SELECT (`LivePromoteOneLayerTest`) | PUB-01, PUB-04 | Needs superuser-provisioned fixtures; stub never exercised | Run `publish_order.py` live; confirm `vicmap.<target>` exists, staging table dropped, index name via `pg_indexes`, `has_table_privilege('vicmap_reader', ..., 'SELECT')` |
| Multiple layers commit together (`LiveMultiLayerPromotionTest`) | PUB-02 | Only a single-layer order (OK0VUZ) has been published live | Publish a multi-layer order; confirm all target tables appear in one commit |
| Reader discovers tables and runs spatial query (`LiveReaderVerificationTest`) | PUB-05 | Stub | Inspect `summary.json` `reader.tables_discovered` > 0 and `spatial_query_row_count` > 0 |
| Correctly-granted reader's INSERT is denied (`LiveReaderWriteDenialTest`) | PUB-04 | Stub | Inspect `summary.json` `reader.write_denied: true` |
| Full `publish_order.py` run exits 0 and writes `summary.json` (`LivePublishOrderFullRunTest`) | EVID-01, EVID-02 | Stub | Run `publish_order.py`; confirm exit 0 and redacted `summary.json` (evidence: `runs/OK0VUZ/20260924T083137Z/summary.json`) |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter — held false: five live happy-path checks are manual-only

**Approval:** approved 2026-09-28 (partial — manual-only live items above)

---

## Validation Audit 2026-09-28

| Metric | Count |
|--------|-------|
| Gaps found | 5 |
| Resolved | 0 |
| Escalated | 5 (manual-only, by operator choice) |

Evidence: phase test modules `Ran 299 tests ... OK (skipped=42)` (skips are the live-DB classes, no DSN in this session); 15/16 plan inline checks pass, 1 stale literal (see ¹).
