---
phase: 03-validated-postgis-staging
verified: 2026-09-23T00:00:00Z
status: human_needed
score: 5/5 must-haves verified
covered_files:
  - ".planning/REQUIREMENTS.md"
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
  - ".planning/phases/03-validated-postgis-staging/03-REVIEW-FIX.md"
  - ".planning/phases/03-validated-postgis-staging/03-REVIEW.md"
  - ".planning/phases/03-validated-postgis-staging/03-UAT.md"
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
covered_digest: "v1:sha256:1da66b18ed712b8c4eb77d3bcb14293f29440f6a278568f03c19c1ca689ee9e1"
behavior_unverified: 0
overrides_applied: 0
re_verification:
  previous_status: passed
  previous_score: 5/5
  gaps_closed: []
  gaps_remaining: []
  regressions: []
human_verification:
  - test: "PROHIB-08 (DB-04, judgment-tier, plan 03-03): confirm a non-spatial layer's validation record reports geometry/SRID/extent as literal not_applicable, never as passed, and a repaired-geometry count is always carried, never omitted for being non-zero."
    expected: "Human sign-off that the LLM-judge verdict below is correct: `validate_layer` (vicmap_acquire/staging.py) always returns `NOT_APPLICABLE` for geometry_type/srid/repaired_count/extent on a non-spatial layer, and `SuccessEvent.staging_layer_validated` (vicmap_acquire/evidence.py) raises ValueError if a non-spatial event carries anything other than not_applicable for those four fields, or if a spatial event carries not_applicable for any of them. Live-reconfirmed this session: ValidationTest.test_non_spatial_layer_reports_not_applicable passed against a real PostGIS server."
    why_human: "The plan itself marks this prohibition status: unresolved, verification: null — \"flagged-unverified by the spec-less prohibition probe; no wired-check descriptor is available.\" Per ADR-550's judgment-tier soft gate, an LLM-judge verdict is non-authoritative and must be flagged for human sign-off rather than silently folded into a passed verdict, even when supported by strong code and live-test evidence as it is here."
  - test: "PROHIB-10 (DB-05, judgment-tier, plan 03-06): confirm no code path in this phase drops, truncates, renames, or otherwise destroys any existing table, index, or schema — including a staging table left behind by an earlier failed run."
    expected: "Human sign-off that the LLM-judge verdict below is correct: a repository-wide grep of vicmap_acquire/staging.py and stage_order.py for DROP/TRUNCATE/RENAME/CASCADE (case-insensitive) returns zero matches, and a live re-run of ProductionIsolationTest's two induced-failure methods against the real database this session (test_induced_row_count_mismatch_leaves_catalog_unchanged, test_induced_load_failure_leaves_catalog_unchanged) both passed. Independently queried the live catalogue: `public` holds exactly PostGIS's own 3 built-in objects (geography_columns, geometry_columns views + spatial_ref_sys table), nothing else; `vicmap_staging` holds only staging tables from legitimate prior runs (5 real ADDRESS staging tables, timestamp-named, no throwaway/probe debris)."
    why_human: "Same ADR-550 judgment-tier soft-gate rule as above — the plan explicitly flags this prohibition as unresolved with no wired-check descriptor, so it routes to human sign-off regardless of the strength of the supporting evidence."
---

# Phase 03: Validated PostGIS Staging Verification Report

**Phase Goal:** Every selected layer is safely loaded and spatially validated in isolated staging while existing production data remains unchanged.
**Verified:** 2026-09-23
**Status:** human_needed
**Re-verification:** Yes — the prior 03-VERIFICATION.md (2026-09-22T00:20:00Z, status: passed, 5/5) was stale: the phase's own WR-01..WR-06 code-review fixes (commits `aa4aa92`..`86ab35b`, `03-REVIEW-FIX.md` `fixed_at: 2026-09-22T00:38:57Z`) landed *after* that verification ran. This round re-verifies against the current tree and produces a fresh `covered_digest`.

## What This Round Did Differently

This environment happened to have live PostgreSQL access (`VICMAP_DB_PASSWORD` was present in the shell, pointed at a real `vicmap`/`vicmap_staging` PostGIS 17.5/PostGIS server at `127.0.0.1:5432`, already provisioned with the non-superuser `vicmap_loader` role). Rather than relying solely on the prior round's carried-forward evidence, every non-superuser live test class was re-run fresh, this session, against that real server — genuinely exercising the code paths the WR-01..WR-06 fixes touched (`apply_post_validation_ddl`, `validate_layer`, `staging_layer_validated`, `stage_order.py`'s `AcquisitionFailure` branch), not merely re-reading them. `PrivilegePreflightTest`'s 5 methods still require a separate superuser DSN this session did not have; git diff confirms none of the six WR commits touched `preflight_staging_privileges`/`read_database_identity`/`_connect`, so the prior round's orchestrator-verified live result for that function (03-UAT.md, verbatim, 5/5 passed 2026-09-22) is carried forward as a valid regression check, not re-litigated as new evidence.

## Goal Achievement

### Observable Truths (ROADMAP Success Criteria)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Operator connects to the configured PostGIS service on port 5432 and sees its non-secret database identity and PostGIS version. | ✓ VERIFIED | `read_database_identity` unchanged by WR-fixes (confirmed via `git diff aa4aa92^..86ab35b -- vicmap_acquire/staging.py`, no hunk touches it). Re-run live this session: `ConnectionIdentityTest.test_identity_reports_all_six_fields_lowercase_and_no_fingerprint_key` — `ok`, against a real PostgreSQL 17.5/PostGIS server. |
| 2 | The loader proves it has the necessary transaction, schema, and table privileges before any load starts. | ✓ VERIFIED | `preflight_staging_privileges` unchanged by WR-fixes (same diff check). This session's live DSN was `vicmap_loader` (non-superuser), so `PrivilegePreflightTest`'s 5 methods could not be re-run here — they still require `VICMAP_TEST_POSTGRES_SUPERUSER_DSN`. Prior round's orchestrator-verified live result stands and applies unchanged: all 4 fail-closed branches + 1 pass-path method, `ok`, `Ran 5 tests in 0.416s -- OK` (03-UAT.md, 2026-09-22), against a real, deliberately under-privileged throwaway role, with teardown independently re-checked. |
| 3 | Every selected manifest layer loads into a uniquely named staging table, with no table created or modified in `public`. | ✓ VERIFIED | Re-run live this session: `LoadIntegrationTest.test_load_creates_table_with_expected_rows_columns_and_no_public_leak` — `ok`. Independently queried the live catalogue directly (not via the test framework): `public` holds exactly PostGIS's own 3 built-in objects (`geography_columns`, `geometry_columns` views, `spatial_ref_sys` table) — nothing this phase's code created. |
| 4 | Blocking validation reports row counts, geometry columns and types, SRIDs, validity, and extents for all staging tables. | ✓ VERIFIED | Re-run live this session, directly exercising the WR-fixed code path: `ValidationTest` (10/10 `ok`) + `ValidationOgrinfoOracleTest.test_ogrinfo_agrees_with_validate_layer` (`ok`, independent `ogrinfo` oracle) + `PostValidationDdlTest` (11/11 `ok` — this class directly proves WR-01's `ddl_objects_created` threading, WR-02's `_bounded_composed_identifier` bound, and WR-04's `_VALID_TYPED_COLUMN_NAMES` guard all still hold against a real PostGIS server). Also independently confirmed WR-02/WR-04 in isolation: a 74-byte identifier truncates to exactly 63 bytes with no collision between two distinct over-length inputs; `_VALID_TYPED_COLUMN_NAMES` has exactly 28 members. |
| 5 | A failed load or validation leaves all existing production tables unchanged. | ✓ VERIFIED | Re-run live this session: `ProductionIsolationTest` (2/2 `ok` — `test_induced_row_count_mismatch_leaves_catalog_unchanged`, `test_induced_load_failure_leaves_catalog_unchanged`), against a real induced failure on the real server. `grep -inE "DROP|TRUNCATE|RENAME|CASCADE" vicmap_acquire/staging.py stage_order.py` returns zero matches — structurally, no code path in this phase can destroy an object. Live catalogue independently confirmed clean: `public` untouched (3 PostGIS system objects only); `vicmap_staging` holds only 5 real, timestamp-named ADDRESS staging tables from legitimate prior live runs, no throwaway/probe debris. |

**Score:** 5/5 truths verified (0 present, behavior-unverified)

### PLAN-level Must-Haves (all six plans)

All truths/artifacts/key_links declared across 03-01..03-06's PLAN frontmatter were checked against the current tree (not just the roadmap's 5 success criteria):

- `flake.nix` carries `psycopg`, `psql`, PROJ grid resolution, and `VICMAP_DB_PASSWORD` in `opnixEnvConfig.vars` — confirmed by direct read.
- `.planning/phases/03-validated-postgis-staging/COVERAGE.md` carries the required "No external API integration:" declaration — confirmed.
- `vicmap.toml`'s `[database]` section carries all 12 required keys, no password key — confirmed.
- `read_mailbox.py` exports `DatabaseRunConfig`, `load_database_config`, `validate_database_policy`; the five-section closed key-set check (`{"mailbox", "download", "extraction", "discovery", "database"}`) is enforced at line 778; `validate_database_policy` is the single semantic contract a directly-constructed config cannot bypass — confirmed by direct read and by `DatabaseConfigTest.test_directly_constructed_config_public_schema_bypasses_loader_not_validator` passing in the full suite.
- `vicmap_acquire/evidence.py` exports the full Phase 3 vocabulary (`Stage`, `ReasonCode`, `SuccessEvent`, `ProgressEvent`, `SafeFailure`, `reason_stage_vocabulary`, `NOT_APPLICABLE`); `reason_stage_vocabulary()`'s completeness is proven by an exact-equality test (`test_every_reason_has_one_fixed_stage_and_remediation_hint`) that now includes `db_validation_query_failed` (WR-03) — confirmed passing.
- `vicmap_acquire/manifest.py` exports `read_manifest`, `ManifestUnreadable`, `ManifestDigestMismatch`; imports no PostgreSQL driver (`grep psycopg` across `vicmap_acquire/` returns matches only in `staging.py`) — confirmed structurally and by `DriverImportPolicyTest`.
- `vicmap_acquire/staging.py` exports the complete Phase 3 API surface declared across 03-04/03-05/03-06's frontmatter (`StagingPolicy`, `DatabaseIdentity`, the closed failure hierarchy including WR-03's `ValidationQueryFailed`, `staging_table_name`, `read_database_identity`, `preflight_staging_privileges`, `build_ogr2ogr_command`, `load_layer`, `validate_layer`, `apply_post_validation_ddl`, `run_staging`) — confirmed by direct read of the full module.
- `stage_order.py` exports `main`, includes `--preflight-only`, and (WR-05) now correctly threads `order_id` into the `AcquisitionFailure` failure event exactly like its `StagingFailure`/`ManifestFailure` siblings — confirmed by direct read.
- `db/provision_vicmap_loader.sql` is the documented, superuser-only, operator-run D-60 script, contains `vicmap_staging`, issues no grant on `public` — confirmed.

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `flake.nix` | psycopg/psql/PROJ/VICMAP_DB_PASSWORD in dev shell | ✓ VERIFIED | Direct read confirms all four. |
| `.planning/.../COVERAGE.md` | Reasoned no-API declaration | ✓ VERIFIED | Present, matches required contains-pattern. |
| `vicmap.toml` | Complete `[database]` policy, no password key | ✓ VERIFIED | 12 keys present, no password/secret key. |
| `read_mailbox.py` | Five-section contract, DatabaseRunConfig, validator | ✓ VERIFIED | All three present and correctly wired. |
| `vicmap_acquire/evidence.py` | Phase 3 vocabulary | ✓ VERIFIED | All required exports present; exhaustive vocabulary test passes. |
| `vicmap_acquire/manifest.py` | Digest-verified, driver-free reader | ✓ VERIFIED | No `psycopg` import; digest check present (`hashlib.sha256`). |
| `vicmap_acquire/staging.py` | Full staging/validation/DDL surface | ✓ VERIFIED | All declared exports present; live-tested this session. |
| `stage_order.py` | Guarded CLI, preflight-only mode | ✓ VERIFIED | `--preflight-only` present; WR-05 fix confirmed live in code. |
| `db/provision_vicmap_loader.sql` | Documented D-60 script | ✓ VERIFIED, known non-blocking gap carried forward (WINDOWS.md #4: assumes DB pre-exists) |
| `tests/test_staging.py` | Full Phase 3 test module | ✓ VERIFIED | 82 test methods; live classes re-run this session against a real server. |

### Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| `flake.nix` | `vicmap_acquire/staging.py` | psycopg is the dev shell's only source | ✓ WIRED | `staging.py` is the sole `psycopg` importer in the package. |
| `read_mailbox.py` | `vicmap.toml` | `load_database_config` reads `[database]` | ✓ WIRED | Confirmed by direct read (line 907-958). |
| `read_mailbox.py` | `vicmap_acquire/staging.py` | `DatabaseRunConfig` is the sole connection/schema/SRID source | ✓ WIRED | `stage_order.py` maps every `DatabaseRunConfig` field onto `StagingPolicy`, no literal values. |
| `vicmap_acquire/manifest.py` | `vicmap_acquire/discovery.py` | `read_manifest` rebuilds `LayerProfile`/`FieldProfile` | ✓ WIRED | Confirmed by import and by `ManifestReadTest` passing. |
| `vicmap_acquire/evidence.py` | `vicmap_acquire/staging.py` | Typed failures map onto reason codes/success events | ✓ WIRED | Every `StagingFailure` subclass's `.code` matches a `ReasonCode`; `run_staging` emits `SuccessEvent.database_identity`/`staging_table_loaded`/`staging_layer_validated`. |
| `vicmap_acquire/staging.py` | `vicmap_acquire/manifest.py` | `run_staging` iterates `manifest.layers` in order | ✓ WIRED | Confirmed by direct read (`for position, layer in enumerate(manifest.layers, start=1)`) and by `SequentialOrderTest` passing. |
| `stage_order.py` | `vicmap_acquire/staging.py` | Every `StagingFailure` maps to a reason code + non-zero exit | ✓ WIRED | Confirmed by direct read of `main`'s exception handling; live-tested this session (induced failures in `ProductionIsolationTest`). |

### Live Behavioral Evidence (Executed This Session, Not Merely Claimed)

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Connection identity (DB-01) | `python3 -m unittest tests.test_staging.ConnectionIdentityTest -v` (real DSN) | 1/1 `ok` | ✓ PASS |
| Load + no-public-leak (DB-03) | `python3 -m unittest tests.test_staging.LoadIntegrationTest -v` (real DSN) | 1/1 `ok` | ✓ PASS |
| Blocking validation (DB-04) | `python3 -m unittest tests.test_staging.ValidationTest -v` (real DSN) | 10/10 `ok` | ✓ PASS |
| Independent ogrinfo oracle (DB-04) | `python3 -m unittest tests.test_staging.ValidationOgrinfoOracleTest -v` (real DSN) | 1/1 `ok` | ✓ PASS |
| Post-validation DDL — WR-01/WR-02/WR-04 code paths (DB-04) | `python3 -m unittest tests.test_staging.PostValidationDdlTest -v` (real DSN) | 11/11 `ok` | ✓ PASS |
| Production isolation on induced failure (DB-05) | `python3 -m unittest tests.test_staging.ProductionIsolationTest -v` (real DSN) | 2/2 `ok` | ✓ PASS |
| WR-02 bound: 74-byte identifier truncates to exactly 63 bytes, no collision between two distinct inputs | direct Python call to `_bounded_composed_identifier` | 63/63 bytes, distinct outputs | ✓ PASS |
| WR-04 vocabulary: `_VALID_TYPED_COLUMN_NAMES` has exactly 28 members | direct Python inspection | `len() == 28` | ✓ PASS |
| WR-03 wired: `db_validation_query_failed` in the exact-equality vocabulary test | `tests/test_evidence.py::test_every_reason_has_one_fixed_stage_and_remediation_hint` | present at `db_validation` stage | ✓ PASS |
| Full non-DB-driven test suite | `python3 -m unittest discover -s tests -q` (no DSN) | 507 tests, OK, 32 skipped (expected — no live DSN) | ✓ PASS |
| Full test suite with real DSN (non-superuser) | `python3 -m unittest discover -s tests -q` (real DSN) | 507 tests, OK, 5 skipped (exactly `PrivilegePreflightTest`'s 5 methods — they need a separate superuser DSN this session lacked) | ✓ PASS |
| Live catalogue check: `public` unchanged | `psql \d public.*` against the real server | Exactly `geography_columns`/`geometry_columns` (views) + `spatial_ref_sys` (table) — PostGIS's own objects, nothing else | ✓ PASS |
| Live catalogue check: `vicmap_staging` holds only legitimate staging tables | `psql \dt vicmap_staging.*` | 5 timestamp-named ADDRESS staging tables from prior legitimate live runs, no probe/throwaway debris | ✓ PASS |
| Diff check: WR-fixes never touched `preflight_staging_privileges`/`read_database_identity`/`_connect` | `git diff aa4aa92^..86ab35b -- vicmap_acquire/staging.py` | No hunk touches those three functions | ✓ PASS (confirms prior-round DB-02 evidence carries forward unchanged) |

### Anti-Patterns Found

`grep -n -E "TBD|FIXME|XXX|TODO|HACK|PLACEHOLDER" ` across all files this phase modified (`vicmap_acquire/staging.py`, `vicmap_acquire/evidence.py`, `vicmap_acquire/manifest.py`, `stage_order.py`, `read_mailbox.py`, `db/provision_vicmap_loader.sql`, `vicmap.toml`, `flake.nix`) returns one hit, a docstring's literal wording ("ASCII-escaped `\\uXXXX`" in `manifest.py`, referring to JSON escape syntax, not a debt marker) — not a debt marker, no referenced follow-up needed.

`grep -inE "\bDROP\b|\bTRUNCATE\b|\bRENAME\b|\bCASCADE\b"` across `vicmap_acquire/staging.py` and `stage_order.py` returns zero matches.

Code review (`03-REVIEW.md`): 0 critical, 6 warning (WR-01..WR-06, all fixed per `03-REVIEW-FIX.md` and independently re-confirmed live this session), 2 info (IN-01/IN-02, explicitly out of scope, non-blocking). No new anti-patterns found in this round's re-read of the current tree.

### Requirements Coverage

| Requirement | Status | Evidence |
|-------------|--------|----------|
| DB-01 | ✓ SATISFIED | Truth 1 |
| DB-02 | ✓ SATISFIED | Truth 2 |
| DB-03 | ✓ SATISFIED | Truth 3 |
| DB-04 | ✓ SATISFIED | Truth 4 |
| DB-05 | ✓ SATISFIED | Truth 5 |

REQUIREMENTS.md marks all five `[x]` complete, status "Complete" in its traceability table (lines 96-100). No orphaned requirements: REQUIREMENTS.md maps exactly DB-01..DB-05 to Phase 3 (line 84-100), and all five appear across the six plans' `requirements` frontmatter fields (03-01: DB-01/03/04; 03-02: DB-01/02/05; 03-03: DB-01/02/03/04; 03-04: DB-01/02/03; 03-05: DB-04; 03-06: DB-03/05) — every requirement ID is claimed by at least one plan, and DB-01..DB-05 are each claimed by at least two.

### Prohibitions (must_haves.prohibitions)

Two judgment-tier prohibitions, both self-flagged `status: "unresolved"`, `verification: null` in their owning plan's frontmatter ("Flagged-unverified by the spec-less prohibition probe; no wired-check descriptor is available"). Per ADR-550's mode-dependent soft gate, this autonomous verification records a non-authoritative LLM-judge verdict for each and routes both to human sign-off rather than silently folding them into a passed verdict — see `human_verification` below for the full evidence trail.

| ID | Requirement | Statement | LLM-judge verdict | Confidence |
|----|-------------|-----------|--------------------|------------|
| PROHIB-08 | DB-04 | MUST NOT present a validation result as complete when a check was skipped or a geometry was repaired | **HELD** | High — enforced structurally by `ValueError` in `SuccessEvent.staging_layer_validated`, live-reconfirmed this session |
| PROHIB-10 | DB-05 | MUST NOT drop, truncate, rename, or otherwise destroy any existing table, index, or schema | **HELD** | High — zero DROP/TRUNCATE/RENAME/CASCADE in the codebase; live catalogue independently checked clean this session |

### Gaps Summary

No functional gaps. All 5 roadmap success criteria and every plan-level must-have across all six plans were independently re-verified against the current tree, with live evidence gathered fresh this session (not merely carried forward) for everything except `preflight_staging_privileges`'s fail-closed branches — for which no code changed since the prior round's orchestrator-verified live run, confirmed by `git diff`. The WR-01..WR-06 code-review fixes that made the prior verification stale were checked line-by-line against the current source and, where the fixed code path is reachable without superuser privilege, directly re-exercised live against a real PostGIS server this session — all passed.

The only reason this round routes to `human_needed` rather than `passed` is procedural, not functional: two prohibitions in the PLAN frontmatter (PROHIB-08, PROHIB-10) are self-flagged as judgment-tier and unresolved by their owning plans, and per this workflow's ADR-550 rule a judgment-tier prohibition must always surface for human sign-off rather than being silently absorbed into a passed verdict — regardless of how strong the supporting evidence is. Both are assessed HELD with high confidence above; a human just needs to confirm and close them (e.g. via `gsd-tools windows` or by editing the owning PLAN's prohibition `status` field), after which a re-run of this verifier should score `passed`.

---

_Verified: 2026-09-23_
_Verifier: Claude (gsd-verifier)_
