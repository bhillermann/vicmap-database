---
phase: 03-validated-postgis-staging
verified: 2026-09-21T00:00:00Z
status: human_needed
score: 4/5 must-haves verified
covered_files:
  - ".planning/REQUIREMENTS.md"
  - ".planning/WINDOWS.md"
  - ".planning/phases/03-validated-postgis-staging/03-01-PLAN.md"
  - ".planning/phases/03-validated-postgis-staging/03-01-SUMMARY.md"
  - ".planning/phases/03-validated-postgis-staging/03-02-PLAN.md"
  - ".planning/phases/03-validated-postgis-staging/03-02-SUMMARY.md"
  - ".planning/phases/03-validated-postgis-staging/03-03-PLAN.md"
  - ".planning/phases/03-validated-postgis-staging/03-03-SUMMARY.md"
  - ".planning/phases/03-validated-postgis-staging/03-04-PLAN.md"
  - ".planning/phases/03-validated-postgis-staging/03-04-SUMMARY.md"
  - ".planning/phases/03-validated-postgis-staging/03-05-PLAN.md"
  - ".planning/phases/03-validated-postgis-staging/03-05-SUMMARY.md"
  - ".planning/phases/03-validated-postgis-staging/03-06-PLAN.md"
  - ".planning/phases/03-validated-postgis-staging/03-06-SUMMARY.md"
  - ".planning/phases/03-validated-postgis-staging/03-REVIEW.md"
  - "db/provision_vicmap_loader.sql"
  - "flake.nix"
  - "read_mailbox.py"
  - "stage_order.py"
  - "tests/test_evidence.py"
  - "tests/test_manifest.py"
  - "tests/test_staging.py"
  - "vicmap.toml"
  - "vicmap_acquire/evidence.py"
  - "vicmap_acquire/manifest.py"
  - "vicmap_acquire/staging.py"
covered_digest: "v1:sha256:d649fe2099f30d2648da714dfe211df7a1bd0f42bc4612a003bdb233a3e4717b"
behavior_unverified: 1
overrides_applied: 0
behavior_unverified_items:
  - truth: "DB-02: the loader proves it has the necessary transaction, schema, and table privileges before any load starts — specifically, that `preflight_staging_privileges` correctly RAISES `PrivilegeDenied`/`TargetSridUnresolved` when the connected role actually lacks the required privilege (is superuser, lacks USAGE/CREATE on the staging schema, holds CREATE on public, or the target SRID is unknown)."
    test: "Run `tests/test_staging.py::PrivilegePreflightTest`'s 4 fail-path methods (`test_fail_path_no_create_on_staging_schema`, `test_fail_path_create_on_public`, `test_fail_path_superuser`, `test_fail_path_unknown_srid`) against a real superuser connection, or otherwise manually induce each of the four negative conditions against a throwaway role and confirm `preflight_staging_privileges` raises the expected exception."
    expected: "Each of the four negative conditions raises its named exception (`PrivilegeDenied` or `TargetSridUnresolved`) rather than silently passing."
    why_human: "These are state-transition / fail-closed invariants that no executed test currently exercises. `PrivilegePreflightTest`'s 5 methods (the only tests that call `preflight_staging_privileges` with real ACL manipulation) unconditionally skip — they require `VICMAP_TEST_POSTGRES_SUPERUSER_DSN`, which has never been set (WINDOWS.md #6, open). Every other live exercise of `preflight_staging_privileges` (`ProductionIsolationTest`, `LoadIntegrationTest`, and the operator's live `stage_order.py --preflight-only` run recorded in 03-04-SUMMARY.md) runs it against the real `vicmap_loader` role, which already has correct privileges — so only the PASS branch has ever executed, live or in CI. Grep/presence checks cannot distinguish 'the code that would reject bad privilege' from 'code that happens never to be given bad privilege to reject.'"
---

# Phase 03: Validated PostGIS Staging Verification Report

**Phase Goal:** Every selected layer is safely loaded and spatially validated in isolated staging while existing production data remains unchanged.
**Verified:** 2026-09-21
**Status:** human_needed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths (ROADMAP Success Criteria)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Operator connects to the configured PostGIS service on port 5432 and sees its non-secret database identity and PostGIS version. | ✓ VERIFIED | `read_database_identity` (staging.py:327-358) opens one connection, returns host/port/dbname/role/server_version/postgis_version. `stage_order.py --preflight-only` prints this and exits 0 (03-04-SUMMARY.md live capture: `{"dbname":"vicmap",...,"role":"vicmap_loader","server_version":"PostgreSQL 17.5...","postgis_version":"POSTGIS=\"3.5.2...\""}`, no password/connection-string substring). `ConnectionIdentityTest` is a live test class (not among the 5 permanently-skipping methods — orchestrator-confirmed `skipped=5` with DSN set, and the orchestrator independently queried the live server: PostgreSQL 17.5/PostGIS 3.5.2 at 127.0.0.1:5432, db `vicmap`, role `vicmap_loader`). |
| 2 | The loader proves it has the necessary transaction, schema, and table privileges before any load starts. | ⚠️ PRESENT_BEHAVIOR_UNVERIFIED | Code exists and is wired (`preflight_staging_privileges`, staging.py:361-452, called unconditionally as the second step of `run_staging` before any layer load, staging.py:1093). The **positive** path is live-demonstrated twice: (a) `ProductionIsolationTest`'s two live methods call `run_staging` unmocked against the real `vicmap_loader` role and reach later pipeline stages, meaning preflight passed for real; (b) the operator ran `stage_order.py --preflight-only` against the real database and independently verified via `psql` all five underlying facts (non-superuser, USAGE+CREATE on `vicmap_staging`, no CREATE on `public`, SRID 7899 known) — 03-04-SUMMARY.md D2. But the **negative/fail-closed** branches — the actual mechanism that would catch a role that lacks privilege — have never executed, live or in CI: see `behavior_unverified_items`. |
| 3 | Every selected manifest layer loads into a uniquely named staging table, with no table created or modified in `public`. | ✓ VERIFIED | `staging_table_name` (staging.py:263-277) composes `{target_table}_{run_timestamp}`; three consecutive live runs against the real ADDRESS layer produced three distinct tables (`vmadd_address_20260921t070323z`, `_070443z`, `_071736z`, each `row_count=4222035`) per 03-04-SUMMARY.md. `LoadIntegrationTest` and `ProductionIsolationTest` (both live, both ran — not among the 5 skips) assert `public` holds no matching table and that a full catalog snapshot of every schema except `vicmap_staging` is byte-identical before/after. Orchestrator independently confirmed live: `public` holds only PostGIS's own `geography_columns`/`geometry_columns`/`spatial_ref_sys`; `vicmap_staging` holds real staged tables matching the manifest's declared `feature_count` exactly. |
| 4 | Blocking validation reports row counts, geometry columns and types, SRIDs, validity, and extents for all staging tables. | ✓ VERIFIED | `validate_layer` (staging.py:731-878) runs a single-pass query covering row count, null-geometry, invalid-geometry, type-change-on-repair, SRID set, geometry-type set, ZM-flag set, and extent; each disagreement raises its own named exception (`RowCountMismatch`, `SridMismatch`, `GeometryTypeMismatch`, `GeometryRepairChangedType`, `GeometryRepairIncomplete`). `ValidationTest` (11 live methods covering clean/mismatch/repair/dimensionality cases) and `ValidationOgrinfoOracleTest` (an *independent* oracle — runs `ogrinfo` against the loaded table through a separate code path and asserts agreement with `validate_layer`'s own report) both ran live, not skipped. Non-spatial layers report the four geometry fields as the literal `not_applicable`, enforced structurally by a `ValueError` guard in `SuccessEvent.staging_layer_validated` (evidence.py:678-690) and unit-tested (`tests/test_evidence.py:1792-1810`). |
| 5 | A failed load or validation leaves all existing production tables unchanged. | ✓ VERIFIED | `ProductionIsolationTest` (staging.py test module) induces a real `RowCountMismatch` and a real `LoadFailed` against the live `vicmap_loader` role, snapshotting the full catalog (every schema except `vicmap_staging`, with row counts for `public`/`vicmap`) before and after each induced failure and asserting byte-identical equality — this class ran live (not among the 5 permanent skips). No code path in `staging.py` or `stage_order.py` contains `DROP`, `TRUNCATE`, or `RENAME` (grep-confirmed empty). `preflight_staging_privileges`'s probe `CREATE TABLE`/`CREATE INDEX` is unconditionally rolled back on both pass and fail paths (staging.py:440-446). PROHIB-10 ("must not drop/truncate/rename/destroy any existing table") is satisfied structurally and empirically, despite being tagged `status: unresolved` in 03-06-PLAN.md's frontmatter — that tag reflects an automated probe finding "no wired-check descriptor," not an actual gap; the code and live test both demonstrate the prohibition holds. |

**Score:** 4/5 truths verified (1 present, behavior-unverified)

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `vicmap_acquire/staging.py` | StagingPolicy, DatabaseIdentity, closed failure hierarchy, identity/preflight/load/validate/DDL, `run_staging` orchestration | ✓ VERIFIED | All 26 declared exports present (AST-checked); the sole module in `vicmap_acquire` importing `psycopg` (`DriverImportPolicyTest`, staging.py test module, structural + import-timing proof, non-live, always runs). |
| `stage_order.py` | Guarded CLI with `--preflight-only` | ✓ VERIFIED | `main` present; loads `read_mailbox.load_database_config`, invokes `staging.run_staging`; maps every `StagingFailure` subclass onto a `ReasonCode` and non-zero exit. |
| `db/provision_vicmap_loader.sql` | D-60's operator-run superuser-only provisioning script | ✓ VERIFIED (with known gap) | Creates `vicmap_loader` (non-superuser), owns `vicmap_staging`+`vicmap`, grants nothing on `public`. WINDOWS.md #4 (open, non-blocking): assumes the target database already exists — operator had to run `CREATE DATABASE` manually first. Documented, not silently patched. |
| `vicmap_acquire/evidence.py` | Stages, ReasonCode, SuccessEvent/ProgressEvent/SafeFailure, `reason_stage_vocabulary`, `NOT_APPLICABLE` | ✓ VERIFIED | All 7 declared exports present; `reason_stage_vocabulary()` completeness is asserted by 3 test call sites in `tests/test_evidence.py`. |
| `vicmap_acquire/manifest.py` | Digest-verified manifest reader | ✓ VERIFIED | `read_manifest`, `ManifestUnreadable`, `ManifestDigestMismatch` all present; grep confirms no `psycopg`/`psycopg2`/`sqlalchemy`/`asyncpg`/`pg8000` token anywhere in the file — driver-free by construction, matching `DriverImportPolicyTest`'s structural proof. |
| `flake.nix` | psycopg driver, psql client, PROJ grid resolution, `VICMAP_DB_PASSWORD` opnix var | ✓ VERIFIED | `VICMAP_DB_PASSWORD` named in `opnixEnvConfig.vars` (line 31, referencing `op://nixos-services/vicmap_loader_credentials/password`); `ps.psycopg` and `postgresql` (for `psql`) both present in the dev shell. |
| `.planning/phases/03-validated-postgis-staging/COVERAGE.md` | Reasoned no-external-API declaration | ✓ VERIFIED | Present, contains `"No external API integration:"`, correctly scopes PostGIS/`ogr2ogr` as local, not a vendor API surface. |

### Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| `flake.nix` | `vicmap_acquire/staging.py` | psycopg is the dev-shell-supplied driver | ✓ WIRED | `staging.py` imports `psycopg`/`psycopg.sql`/`psycopg.errors` at module top; no other package module does. |
| `stage_order.py` | `read_mailbox.py` | `load_database_config` maps `[database]` onto `StagingPolicy` | ✓ WIRED | `stage_order.py:86` calls `read_mailbox.load_database_config(args.config)`. |
| `stage_order.py` | `vicmap_acquire/manifest.py` | `read_manifest` rebuilds the frozen handoff | ✓ WIRED | Imported and called (via `_most_recent_run_directory` + `read_manifest`). |
| `vicmap_acquire/staging.py` | `vicmap_acquire/manifest.py` | `ImportManifest`/`ManifestLayer` are the run_staging input | ✓ WIRED | `from vicmap_acquire.manifest import ImportManifest, ManifestLayer` (staging.py:38). |
| `vicmap_acquire/staging.py` | `vicmap_acquire/evidence.py` | `NOT_APPLICABLE`, `ProgressEvent`, `SuccessEvent` render staging events | ✓ WIRED | `from vicmap_acquire.evidence import NOT_APPLICABLE, ProgressEvent, SuccessEvent` (staging.py:37); used throughout `run_staging`. |
| `read_mailbox.py` | `vicmap.toml` | `load_database_config` reads `[database]` | ✓ WIRED | `vicmap.toml` carries a complete `[database]` section (host/port/dbname/user/staging_schema/publish_schema/target_srid/index_columns/gt/timeouts), no password key. |

### Behavioral Spot-Checks / Live Evidence (Executed, Not Merely Claimed)

| Behavior | Evidence | Status |
|----------|----------|--------|
| Full test suite, driver+server reachable | Orchestrator-verified: 507 tests, `OK (skipped=5)` — the 5 skips are exactly `PrivilegePreflightTest`'s 5 methods (independently confirmed here: that class needs `VICMAP_TEST_POSTGRES_SUPERUSER_DSN`, which per WINDOWS.md #6 has never been set) | ✓ PASS |
| Regression gate (15 prior-phase test files, excluding `test_staging.py`) | Orchestrator-verified: 425 tests, OK, zero skips | ✓ PASS |
| `tests/test_staging.py` without any live DSN (re-run here) | `python -m unittest discover -s tests -p test_staging.py` → `Ran 82 tests ... OK (skipped=31)` — confirms every live class skips cleanly, never fails, absent a server | ✓ PASS |
| `Ogr2ogrFlagOracleTest` (differential oracle vs. real `ogr2ogr` binary) | Confirmed present and non-mocked: invokes the real GDAL binary and asserts `-ct_opt ONLY_BEST=YES`/`ALLOW_BALLPARK=NO` are recognized (not the earlier no-op `--config OGR_CT_*` bug); this is the regression guard for the D-51/PROHIB-09 defect the project's own history flagged | ✓ PASS (structural review) |
| `ValidationOgrinfoOracleTest` (independent oracle vs. `ogrinfo`) | Confirmed present, live-tagged, compares `validate_layer`'s report against `ogrinfo -json` reading the same table through a different code path | ✓ PASS (structural review, live-run confirmed by orchestrator's skip count) |
| Live load of real 4,222,035-row ADDRESS layer, 3 consecutive runs | 03-04-SUMMARY.md: 3 distinct staging tables, `row_count=4222035` each, 39.0-39.4s per run; orchestrator independently confirmed `vicmap_staging` holds real tables at `4,222,035` rows matching manifest `feature_count` exactly at SRID 7899 | ✓ PASS |
| Production isolation under induced failure | `ProductionIsolationTest` live methods (ran, not skipped): catalog snapshot outside `vicmap_staging` byte-identical before/after both an induced `RowCountMismatch` and an induced `LoadFailed`; orchestrator confirmed `public` holds only PostGIS system tables | ✓ PASS |
| No destructive SQL in production code | `grep -in "DROP \|TRUNCATE\|RENAME " vicmap_acquire/staging.py stage_order.py` | no matches (✓ PASS) |
| No unreferenced debt markers | `grep -n "TODO\|FIXME\|XXX\|TBD\|placeholder"` across all 8 Phase-3-modified files | only `db/provision_vicmap_loader.sql`'s documented, IN-02-flagged placeholder password comment (info-level, operator-run script, not a pipeline code path) | ℹ️ non-blocking |

### Requirements Coverage

| Requirement | Source Plan(s) | Description | Status | Evidence |
|-------------|-----------------|-------------|--------|----------|
| DB-01 | 03-01, 03-02, 03-03, 03-04 | Connect and verify non-secret identity + PostGIS version | ✓ SATISFIED | Truth 1 above |
| DB-02 | 03-02, 03-03, 03-04 | Verify required transaction/schema/table privileges before loading | ? NEEDS HUMAN | Truth 2 above — fail-closed branches unexercised |
| DB-03 | 03-01, 03-03, 03-04, 03-06 | Load into uniquely named staging tables, no `public` mutation | ✓ SATISFIED | Truth 3 above |
| DB-04 | 03-01, 03-03, 03-05 | Blocking validation: row counts, geometry columns/types, SRIDs, validity, extents | ✓ SATISFIED | Truth 4 above |
| DB-05 | 03-02, 03-06 | Failed load/validation leaves production unchanged | ✓ SATISFIED | Truth 5 above |

No orphaned requirements: REQUIREMENTS.md maps exactly DB-01..DB-05 to Phase 3, and all five appear in at least one plan's `requirements` frontmatter field (cross-checked above).

### Prohibitions (must_haves.prohibitions)

| ID | Requirement | Statement | PLAN-declared status | Actual verification |
|----|-------------|-----------|----------------------|----------------------|
| PROHIB-08 | DB-04 | Must not present a skipped/repaired check as passed; non-spatial layers report `not_applicable`, never `passed` | `unresolved` (verification: null — flagged by an automated "spec-less prohibition probe" for lacking a wired-check descriptor pattern) | Actually enforced: `SuccessEvent.staging_layer_validated` raises `ValueError` if a spatial layer carries `not_applicable` or a non-spatial layer carries anything else (evidence.py:678-690); unit-tested at `tests/test_evidence.py:1792-1810`. The PLAN-frontmatter "unresolved" tag reflects tooling gaps, not an actual code gap. |
| PROHIB-10 | DB-05 | Must not drop/truncate/rename/destroy any existing table, including a staging table left behind by a failed run | `unresolved` (same automated-probe caveat) | Actually enforced: no `DROP`/`TRUNCATE`/`RENAME` token anywhere in `staging.py`/`stage_order.py` (grep-confirmed); empirically proven by live `ProductionIsolationTest`. |

Both prohibitions hold in the codebase despite their PLAN-frontmatter `status: unresolved` tag — that tag is an artifact of an automated probe that could not find a named "wired-check descriptor," not evidence of an actual violation. Recorded here for transparency, not treated as a gap.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `db/provision_vicmap_loader.sql` | 16-18 | Placeholder password (`REPLACE_WITH_1PASSWORD_VALUE`) is valid SQL and would run as-is if not edited | Info (IN-02, 03-REVIEW.md) | Operator-run, superuser-only script, never executed by any Phase 3 code path. Documented risk, not a pipeline defect. |
| `vicmap_acquire/staging.py` | 1140-1146 | `apply_post_validation_ddl`'s return value (created constraint/index names) discarded by `run_staging` | Warning (WR-01) | Observability gap, not correctness. |
| `vicmap_acquire/staging.py` | 957-1042 | DDL identifier names composed by string-concatenation onto an already-63-byte-capable staging table name, with no bound check | Warning (WR-02) | Edge case for long layer names near the identifier limit; could cause a spurious `StagingDdlFailed` on an otherwise valid load. Not exercised by current Vicmap layer names but a real risk. |
| `vicmap_acquire/staging.py` | 758-763, 837-849 | `validate_layer` maps unrelated DB errors onto `LoadFailed`, pointing at a diagnostics file that was never written for those paths | Warning (WR-03) | Misleading operator diagnostics on an already-rare failure path. |
| `vicmap_acquire/staging.py` | 994-1005 | Geometry-type modifier composed as raw SQL text (`sql.SQL(declared_type)`), safe today only because a separate function's vocabulary constrains it | Warning (WR-04) | Defense-in-depth gap, not currently reachable with untrusted input. |
| `stage_order.py` | 145-175 | `AcquisitionFailure` branch omits `order_id` unlike the other two failure branches | Warning (WR-05) | Minor operator-output inconsistency. |
| `vicmap_acquire/evidence.py` | 21, 384 | Redaction-safety regexes (`_HOST`, `_TARGET_TABLE`) looser than the validators that are their only current callers | Warning (WR-06) | Defense-in-depth gap; not reachable with untrusted input today. |

None of the above rise to Critical (0 Critical per 03-REVIEW.md, independently corroborated by this review of the same files) and none block the phase goal.

### Human Verification Required

### 1. DB-02's fail-closed privilege check has never actually rejected a bad privilege — live or in CI

**Test:** Either (a) provision a throwaway test-only superuser DSN (`VICMAP_TEST_POSTGRES_SUPERUSER_DSN`, as `PrivilegePreflightTest` already expects) and run its 5 methods, or (b) manually create a throwaway role lacking `CREATE` on the staging schema (or lacking on `public`, or a superuser role, or point at an unregistered SRID) and confirm `staging.preflight_staging_privileges` raises `PrivilegeDenied`/`TargetSridUnresolved` as designed, and leaves nothing behind (rolled-back probe).

**Expected:** Each of the four negative conditions raises its named closed exception; the probe `CREATE TABLE`/`CREATE INDEX` is rolled back regardless of outcome.

**Why human:** This is DB-02's actual proof mechanism — the code that must correctly detect *absence* of privilege, not merely execute correctly when privilege is present. It is present, wired into `run_staging`, and has demonstrated its PASS branch live twice (an unmocked `run_staging` call in `ProductionIsolationTest`, and the operator's manual `stage_order.py --preflight-only` run with independent `psql` verification). But its 4 FAIL branches have zero executed test coverage anywhere — `PrivilegePreflightTest`'s 5 methods (the only code that manipulates real ACLs to exercise them) unconditionally skip for want of a superuser test DSN that has never existed (WINDOWS.md #6, open). Given this phase's own documented history of three near-misses from illusory verification (a no-op GDAL flag, a wrong assumption about `GeometryType()`'s Z-suffix behavior, and live tests reporting OK by skipping), presence-and-wiring is not sufficient evidence that the fail-closed branch actually fails closed. A human/operator decision is needed: either provision the superuser test credential to close this gap with an automated regression test, or accept the risk and record an explicit override.

### Gaps Summary

No `gaps_found`-tier defects were identified — every artifact exists, is substantive, is wired, and 4 of the 5 ROADMAP success criteria have direct live evidence (not merely mocked or unit-level). The one item routed to human verification (DB-02's fail-closed privilege proof) is not a code gap: the mechanism exists, is correctly positioned in the orchestration order (before any load), and its pass path is live-demonstrated. What's missing is executed evidence that its negative branches actually reject bad privilege — a gap in test infrastructure (a missing superuser test credential, WINDOWS.md #6, open), not in the shipped code. Two other WINDOWS.md items are open but non-blocking to the phase goal: #4 (provisioning script assumes the database already exists — an operator-run, one-time script, documented) and #2/#7 (the vendored ICSM grid is never selected because PROJ's own accuracy metadata ranks a grid-free Helmert transform higher — this affects transform *accuracy* for one CRS pair, not the correctness of DB-01..DB-05's staging/validation/isolation guarantees, since validation checks row count/type/SRID/validity/extent against whatever transform actually ran, and none of those checks were shown to fail because of it).

---

_Verified: 2026-09-21_
_Verifier: Claude (gsd-verifier)_
