---
phase: "3"
slug: "validated-postgis-staging"
# status lifecycle: draft (seeded by plan-phase) → validated (set by validate-phase §6)
# audit-milestone §5.5 distinguishes NOT-VALIDATED (draft) from PARTIAL (validated + nyquist_compliant: false) (#2117)
status: validated
nyquist_compliant: true
wave_0_complete: true
created: "2026-09-21"
validated: "2026-09-28"
---

# Phase 3 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | `unittest` (Python standard library) |
| **Config file** | none — direct module execution / `discover` |
| **Quick run command** | `nix develop path:. -c python -m unittest tests.test_staging -v` |
| **Full suite command** | `nix develop path:. -c python -m unittest discover -s tests -p 'test_*.py'` |
| **Estimated runtime** | ~4 s staging module; ~24 s full suite (621 tests, 2026-09-28) |
| **Live DB env (skip-not-fail)** | `VICMAP_TEST_POSTGRES_DSN` (non-superuser `vicmap_loader`; password must be inside the DSN — `PGPASSWORD` is overridden by `staging._connect`) and `VICMAP_TEST_POSTGRES_SUPERUSER_DSN` (superuser, supplied per-shell via `op read`, see 03-UAT.md Option A). Without them the live classes skip, never fail. |

---

## Sampling Rate

- **After every task commit:** Run `nix develop path:. -c python -m unittest tests.test_staging -v`
- **After every plan wave:** Run `nix develop path:. -c python -m unittest discover -s tests -p 'test_*.py'`
- **Before `/gsd-verify-work`:** Full suite must be green, with both live DSNs set so the live classes run rather than skip
- **Max feedback latency:** 20 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 03-01-T1 | 03-01 | 1 | DB-01 | — | psycopg package legitimacy confirmed before entering flake | checkpoint (human-verify) | — (gate, resolved in 03-01-SUMMARY) | n/a | ✅ green |
| 03-01-T2 | 03-01 | 1 | DB-04 | — | GDA94→GDA2020 grid mechanism chosen; no runtime network fetch | checkpoint (decision) | — (decision, resolved in 03-01-SUMMARY) | n/a | ✅ green |
| 03-01-T3 | 03-01 | 1 | DB-01, DB-03, DB-04 | — | Dev shell carries psycopg, psql, vendored grid, password secret by reference | smoke | `nix develop path:. -c python -c "import psycopg"` + TransformerGroup/PROJ_DATA grid checks (03-01-PLAN) | ✅ | ✅ green |
| 03-02-T1 | 03-02 | 1 | DB-01, DB-02, DB-05 | — | `[database]` policy loads; five-section closed key set; no password key | unit | `nix develop path:. -c python -m unittest tests.test_graph tests.test_discovery_config tests.test_evidence -v` | ✅ | ✅ green |
| 03-02-T2 | 03-02 | 1 | DB-02, DB-05 | — | Config contract fails closed (e.g. `public` as staging schema rejected by validator) | unit | `nix develop path:. -c python -m unittest tests.test_staging.DatabaseConfigTest -v` | ✅ | ✅ green |
| 03-03-T1 | 03-03 | 1 | DB-01..DB-04 | — | Every DB reason code has one fixed stage + remediation hint | unit | `nix develop path:. -c python -m unittest tests.test_evidence -v` | ✅ | ✅ green |
| 03-03-T2 | 03-03 | 1 | DB-03 | — | Manifest read back digest-verified; reader imports no DB driver | unit | `nix develop path:. -c python -m unittest tests.test_manifest -v` | ✅ | ✅ green |
| 03-04-T1 | 03-04 | 2 | DB-03 | — | Staging contract (geom/gid/target SRID) confirmed | checkpoint (decision) | — (decision, resolved in 03-04-SUMMARY) | n/a | ✅ green |
| 03-04-T2 | 03-04 | 2 | DB-01, DB-03 | — | Uniquely named `vicmap_staging` table; no `public` leak; identity reported without credential | unit + integration (live) | `nix develop path:. -c python -m unittest tests.test_staging.StagingTableNameTest tests.test_staging.LoadCommandConstructionTest tests.test_staging.Ogr2ogrFlagOracleTest tests.test_staging.DriverImportPolicyTest tests.test_staging.ConnectionSetupTest tests.test_staging.ConnectionIdentityTest tests.test_staging.LoadIntegrationTest -v` | ✅ | ✅ green |
| 03-04-T3 | 03-04 | 2 | DB-02 | — | Preflight passes for provisioned role; fails closed for superuser, no staging CREATE, CREATE on `public`, unknown SRID; leaves nothing behind | unit + integration (live, superuser DSN) | `nix develop path:. -c python -m unittest tests.test_staging.ProvisionScriptTest tests.test_staging.PrivilegePreflightTest -v` | ✅ | ✅ green |
| 03-05-T1 | 03-05 | 3 | DB-04 | — | Declared geometry type normalized; spatial vs non-spatial query shapes | unit | `nix develop path:. -c python -m unittest tests.test_staging.GeometryTypeNormalizationTest tests.test_staging.ValidationQueryShapeTest -v` | ✅ | ✅ green |
| 03-05-T2 | 03-05 | 3 | DB-04 | — | Row count, type, SRID, dimensionality, null geom, repair-changes-type are hard stops; repair counted; non-spatial → `not_applicable` | integration (live) + independent `ogrinfo` oracle | `nix develop path:. -c python -m unittest tests.test_staging.ValidationTest tests.test_staging.ValidationOgrinfoOracleTest -v` | ✅ | ✅ green |
| 03-06-T1 | 03-06 | 4 | DB-03, DB-04 | — | PK, typed/NOT NULL geom, single post-load GiST, allowlisted btree only; induced failure leaves no DDL | unit + integration (live) | `nix develop path:. -c python -m unittest tests.test_staging.SecondaryIndexAllowlistTest tests.test_staging.PostValidationDdlTest -v` | ✅ | ✅ green |
| 03-06-T2 | 03-06 | 4 | DB-05 | — | Layers run in manifest order; named diagnostics; induced load/validation failure leaves catalog unchanged | unit + integration (live) | `nix develop path:. -c python -m unittest tests.test_staging.SequentialOrderTest tests.test_staging.LoadDiagnosticsTest tests.test_staging.ProductionIsolationTest -v` | ✅ | ✅ green |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [x] `tests/test_staging.py` — covers DB-01 through DB-05 via `_LivePostgresMixin` skip-not-fail pattern (`VICMAP_TEST_POSTGRES_DSN`, driver-import guard, connection-failure guard).
- [x] Throwaway staging schema + deliberately under-privileged role fixture — `PrivilegePreflightTest` exercises pass path and all four fail-closed paths.
- [x] Deliberately-invalid-geometry fixture — `ValidationTest.test_repair_preserving_type_is_repaired_and_counted` / `test_repair_changing_type_raises_and_writes_nothing`.
- [x] Framework install: none — `unittest` is stdlib; `psycopg` via `flake.nix`.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Live PostGIS service identity and version against the operator's real database | DB-01 | Requires an operator-provisioned server and credentials that cannot exist in CI | Run the connect command against the configured DSN; confirm the printed database name, server version, and PostGIS version, and that no password appears in output or logs. Done in 03-UAT.md. |
| End-to-end load of a real Vicmap layer into staging | DB-03, DB-04 | Requires the live delivery artifact and a real PostGIS server | Load one manifest layer; confirm the staging table exists under the staging schema, `public` is untouched, and the validation report lists row count, geometry type, SRID, validity, and extent. Done in 03-UAT.md. |

These are operator acceptance checks on real data; every requirement also has automated coverage above.

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 20s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved 2026-09-28

---

## Validation Audit 2026-09-28

| Metric | Count |
|--------|-------|
| Gaps found | 1 |
| Resolved | 1 |
| Escalated | 0 |

- **Gap:** DB-02 `PrivilegePreflightTest` (5 methods) was PARTIAL. The test existed but skipped without `VICMAP_TEST_POSTGRES_SUPERUSER_DSN`.
- **Resolution:** The operator ran it live with the superuser DSN supplied per-shell via `op read`: `Ran 5 tests in 0.226s — OK` (5/5 `ok`, 0 skipped). No new test files were needed.
- **Live run, `vicmap_loader` DSN:** `tests.test_staging` gave 98 tests, OK, 9 skipped. The 9 skips are the 5 above plus 4 `AuditValidationRecordTest`, which belongs to Phase 4 and is out of scope.
- **Full suite, loader DSN:** 621 tests, OK, 16 skipped.
- **Note:** The `op` CLI is not signed in inside the agent's shell. Superuser-DSN runs must be done from an operator terminal.
