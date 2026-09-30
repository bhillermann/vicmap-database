---
phase: 03-validated-postgis-staging
verified: 2026-09-30T00:00:00Z
status: passed
score: 5/5 must-haves verified
covered_files:
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
  - ".planning/phases/03-validated-postgis-staging/03-VALIDATION.md"
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
covered_digest: "v2:sha256:a5554a981df8b88b7ef932f112279fdcfe115adb25e26b1788fc12139afef736"
behavior_unverified: 0
overrides_applied: 1
overrides:
  - must_have: "PROHIB-09 (DB-03, plan 03-04): MUST NOT report a layer as successfully staged when its coordinates were produced by a grid-free, Helmert, or ballpark fallback operation"
    reason: "The prohibition's actual fail-closed enforcement mechanism (-ct_opt ONLY_BEST=YES/ALLOW_BALLPARK=NO) was a silent no-op until 03-04 fixed it (the string had been passed as a bogus --config option); since that fix it correctly blocks true ballpark-accuracy operations. What remains is that PROJ's own accuracy metadata ranks the grid-free Helmert 7-parameter transform as more accurate (0.01 m claimed) than the vendored ICSM grid (0.05 m claimed) for GDA94<->GDA2020 Vicgrid, so ONLY_BEST selects Helmert instead of the grid -- a ~2 mm difference on a real ADDRESS point (WINDOWS.md #2/#7). This was explicitly assessed and closed as an architectural decision, not a code defect, in 03-06-SUMMARY.md ('Grid Question -- Settled, Not Left Open', human_judgment: true) and is tracked as ROADMAP.md backlog Phase 999.1. It is not remediated by any Phase 3 code and is deliberately out of this phase's scope."
    accepted_by: "bhillermann (2026-09-21 architectural decision in 03-06-SUMMARY.md; reconfirmed as non-blocking backlog item 999.1 during 2026-09-30 v0.1-close re-verification)"
    accepted_at: "2026-09-21T00:00:00Z"
re_verification:
  previous_status: passed
  previous_score: 5/5
  gaps_closed:
    - "Documentation inconsistency: prior VERIFICATION.md body read 'Status: human_needed' at line 59 while its own frontmatter said status: passed and its Human Sign-Off section confirmed both prohibitions HELD and signed off. Corrected in this round -- body now reads Status: passed, matching frontmatter."
    - "Coverage gap: prior VERIFICATION.md's Prohibitions/human_verification sections covered only PROHIB-08 and PROHIB-10, omitting PROHIB-09 (DB-03, plan 03-04) entirely. This round adds PROHIB-09 to the Prohibitions table and resolves it via an explicit override (see overrides above), referencing the pre-existing 2026-09-21 architectural decision -- it does not reopen human_needed."
  gaps_remaining: []
  regressions: []
---

# Phase 03: Validated PostGIS Staging Verification Report

**Phase Goal:** Every selected layer is safely loaded and spatially validated in isolated staging while existing production data remains unchanged.
**Verified:** 2026-09-30
**Status:** passed
**Re-verification:** Yes -- the prior 03-VERIFICATION.md (2026-09-23T00:00:00Z, status: passed, 5/5) went stale because later phases 04 and 05.1 edited shared modules this phase's `covered_files` list also covers (`vicmap_acquire/evidence.py`, `db/provision_vicmap_loader.sql`, `tests/test_staging.py`, `stage_order.py`, `vicmap_acquire/staging.py`, `read_mailbox.py`, `vicmap.toml`, `flake.nix`), and `03-UAT.md` received a v0.1 audit-acknowledgement marker. This round confirms nothing regressed any Phase 03 must-have and issues a fresh `covered_digest`.

## What This Round Did Differently

Every change to a shared file since the prior round's digest was diffed line-by-line (`git diff 86ab35b..HEAD -- <file>` for each). All of it is additive Phase 4/05.1 scope layered on top of Phase 3's surface -- new `Stage`/`ReasonCode` members, a new `record_validation`/`AuditPrivilegeDenied`/`AuditRecordFailed` function+exceptions in `staging.py` that write to the new `vicmap_audit` schema (not `public`, not `vicmap_staging`), a new `reader_user` config field and its validation in `read_mailbox.py`, a new `VICMAP_READER_PASSWORD` opnix entry in `flake.nix`, and new `vicmap_audit.*` DDL/grants in `provision_vicmap_loader.sql`. No hunk in any diff modifies a Phase-3-owned function's existing body (`read_database_identity`, `preflight_staging_privileges`, `build_ogr2ogr_command`, `load_layer`, `validate_layer`, `apply_post_validation_ddl`, `run_staging`'s per-layer loop) beyond `stage_order.py`'s `main()` adding one new call to `record_validation` strictly *after* `run_staging` has already returned successfully for that layer.

This environment has both `VICMAP_TEST_POSTGRES_DSN` (non-superuser `vicmap_loader`) and, unlike the prior round, `VICMAP_TEST_POSTGRES_SUPERUSER_DSN` set. Every live test class this phase owns -- including `PrivilegePreflightTest`'s 5 fail-closed-branch methods, which the prior round had to carry forward from an even earlier session -- was re-run fresh, live, this session. This is strictly stronger evidence than the prior round had for DB-02.

## Goal Achievement

### Observable Truths (ROADMAP Success Criteria)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Operator connects to the configured PostGIS service on port 5432 and sees its non-secret database identity and PostGIS version. | ✓ VERIFIED | `read_database_identity` unchanged since the last verification (confirmed via `git diff 86ab35b..HEAD -- vicmap_acquire/staging.py`, no hunk touches it). Re-run live this session: `ConnectionIdentityTest.test_identity_reports_all_six_fields_lowercase_and_no_fingerprint_key` -- `ok`. |
| 2 | The loader proves it has the necessary transaction, schema, and table privileges before any load starts. | ✓ VERIFIED | `preflight_staging_privileges` unchanged (same diff check). Both DSNs are set this session, so unlike the prior round, all 5 `PrivilegePreflightTest` methods (4 fail-closed branches + 1 pass path) were re-run live this session, fresh, not carried forward: `ok` x5. |
| 3 | Every selected manifest layer loads into a uniquely named staging table, with no table created or modified in `public`. | ✓ VERIFIED | Re-run live this session: `LoadIntegrationTest.test_load_creates_table_with_expected_rows_columns_and_no_public_leak` -- `ok`. Independently queried the live catalogue directly: `public` holds exactly PostGIS's own 3 built-in objects (`spatial_ref_sys` table, `geography_columns`/`geometry_columns` views) -- nothing this phase's code created. |
| 4 | Blocking validation reports row counts, geometry columns and types, SRIDs, validity, and extents for all staging tables. | ✓ VERIFIED | Re-run live this session: `ValidationTest` (10/10 `ok`) + `ValidationOgrinfoOracleTest` (1/1 `ok`, independent `ogrinfo` oracle) + `PostValidationDdlTest` (10/10 `ok`). `staging_layer_validated`'s `ValueError` guard (PROHIB-08's mechanism) confirmed unchanged and passing via `tests/test_evidence.py` (83/83 `ok`). |
| 5 | A failed load or validation leaves all existing production tables unchanged. | ✓ VERIFIED | Re-run live this session: `ProductionIsolationTest` (2/2 `ok` -- both induced-failure methods). `grep -inE "\bDROP\b|\bTRUNCATE\b|\bRENAME\b|\bCASCADE\b" vicmap_acquire/staging.py stage_order.py` matches only the English word "drop" inside a docstring ("connection drop mid-insert") -- zero executable destructive SQL. Live catalogue independently confirmed clean: `public` holds only the 3 PostGIS system objects; `vicmap` holds one legitimately promoted Phase-4 table (`vmadd_address`); `vicmap_audit` holds only the two Phase-4/05.1 audit tables; `vicmap_staging` currently has no leftover tables (prior runs were legitimately promoted or cleaned, not evidence of a leak). |

**Score:** 5/5 truths verified (0 present, behavior-unverified)

### PLAN-level Must-Haves (all six plans)

Re-checked against the current tree:

- `flake.nix` still carries `psycopg`, `psql`, PROJ grid resolution, and `VICMAP_DB_PASSWORD` in `opnixEnvConfig.vars`, plus an additive Phase-4 `VICMAP_READER_PASSWORD` entry -- confirmed by direct read.
- `vicmap.toml`'s `[database]` section still carries all 12 Phase-3 keys (no password key), plus one additive Phase-4 key (`reader_user`) -- confirmed.
- `read_mailbox.py` still exports `DatabaseRunConfig`, `load_database_config`, `validate_database_policy`; the five-section closed key-set check (`{"mailbox", "download", "extraction", "discovery", "database"}`) is unchanged; the only diff is one additive field (`reader_user`) and its Phase-4 validation rule (reader must not equal loader) -- confirmed by direct read.
- `vicmap_acquire/evidence.py` still exports the full Phase 3 vocabulary unchanged; new `Stage`/`ReasonCode` members are additive (Phase 4/05.1 stages: `DB_AUDIT`, `DB_PUBLISH`, `DB_READER_VERIFY`, `PUBLICATION_SUMMARY`) -- confirmed by direct read and by `tests/test_evidence.py` passing (83/83).
- `vicmap_acquire/manifest.py` exports `read_manifest`, `ManifestUnreadable`, `ManifestDigestMismatch`; still imports no PostgreSQL driver -- unchanged since prior verification, confirmed by `git diff` (no hunk).
- `vicmap_acquire/staging.py` exports the complete Phase 3 API surface (`StagingPolicy`, `DatabaseIdentity`, the closed failure hierarchy, `staging_table_name`, `read_database_identity`, `preflight_staging_privileges`, `build_ogr2ogr_command`, `load_layer`, `validate_layer`, `apply_post_validation_ddl`, `run_staging`) unchanged; the only addition is `record_validation` plus `AuditPrivilegeDenied`/`AuditRecordFailed`, a self-contained Phase-4 function that writes only to `vicmap_audit.staging_validation` -- confirmed by direct read of the full module.
- `stage_order.py` exports `main`, includes `--preflight-only`; the only diff is `main()` calling the new `record_validation` once per layer strictly after `run_staging` has already returned all layers' validations without raising -- confirmed by direct read.
- `db/provision_vicmap_loader.sql` remains the documented, superuser-only, operator-run D-60 script; it still issues no grant on `public`; the additions are Phase-4 `vicmap_audit` schema/tables/grants and the `vicmap_reader` role, appended after the Phase-3 sections -- confirmed by direct read.

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `flake.nix` | psycopg/psql/PROJ/VICMAP_DB_PASSWORD in dev shell | ✓ VERIFIED | Direct read confirms all four; unchanged. |
| `vicmap.toml` | Complete `[database]` policy, no password key | ✓ VERIFIED | 12 Phase-3 keys present, no password/secret key. |
| `read_mailbox.py` | Five-section contract, `DatabaseRunConfig`, validator | ✓ VERIFIED | All three present and correctly wired; unchanged Phase-3 behavior. |
| `vicmap_acquire/evidence.py` | Phase 3 vocabulary | ✓ VERIFIED | All required exports present; exhaustive vocabulary test passes (83/83). |
| `vicmap_acquire/manifest.py` | Digest-verified, driver-free reader | ✓ VERIFIED | No `psycopg` import; digest check present; byte-identical since prior round. |
| `vicmap_acquire/staging.py` | Full staging/validation/DDL surface | ✓ VERIFIED | All declared exports present, unchanged; live-tested this session. |
| `stage_order.py` | Guarded CLI, preflight-only mode | ✓ VERIFIED | `--preflight-only` present; Phase-3 exception handling unchanged. |
| `db/provision_vicmap_loader.sql` | Documented D-60 script | ✓ VERIFIED, known non-blocking gap carried forward (WINDOWS.md #4 / backlog 999.2: assumes DB pre-exists) |
| `tests/test_staging.py` | Full Phase 3 test module | ✓ VERIFIED | Grew from 82 to well over that with Phase-4 additions; all Phase-3-owned classes re-run live this session, all `ok`. |

### Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| `flake.nix` | `vicmap_acquire/staging.py` | psycopg is the dev shell's only source | ✓ WIRED | Unchanged. |
| `read_mailbox.py` | `vicmap.toml` | `load_database_config` reads `[database]` | ✓ WIRED | Confirmed by direct read; `reader_user` addition does not disturb Phase-3 fields. |
| `read_mailbox.py` | `vicmap_acquire/staging.py` | `DatabaseRunConfig` is the sole connection/schema/SRID source | ✓ WIRED | `stage_order.py` maps every Phase-3 `DatabaseRunConfig` field onto `StagingPolicy`, no literal values. |
| `vicmap_acquire/manifest.py` | `vicmap_acquire/discovery.py` | `read_manifest` rebuilds `LayerProfile`/`FieldProfile` | ✓ WIRED | Unchanged; confirmed by import and passing tests. |
| `vicmap_acquire/evidence.py` | `vicmap_acquire/staging.py` | Typed failures map onto reason codes/success events | ✓ WIRED | Every Phase-3 `StagingFailure` subclass's `.code` still matches a `ReasonCode`; unaffected by Phase-4 additions. |
| `vicmap_acquire/staging.py` | `vicmap_acquire/manifest.py` | `run_staging` iterates `manifest.layers` in order | ✓ WIRED | Confirmed by direct read; unchanged. |
| `stage_order.py` | `vicmap_acquire/staging.py` | Every `StagingFailure` maps to a reason code + non-zero exit | ✓ WIRED | Confirmed by direct read; live-tested this session (`ProductionIsolationTest`). |

### Live Behavioral Evidence (Executed This Session, Not Merely Claimed)

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Connection identity (DB-01) | `python -m unittest tests.test_staging.ConnectionIdentityTest -v` (real DSN) | 1/1 `ok` | ✓ PASS |
| Privilege preflight, all 5 methods including fail-closed branches (DB-02) | `python -m unittest tests.test_staging.PrivilegePreflightTest -v` (real superuser DSN, available this session) | 5/5 `ok` | ✓ PASS |
| Load + no-public-leak (DB-03) | `python -m unittest tests.test_staging.LoadIntegrationTest -v` (real DSN) | 1/1 `ok` | ✓ PASS |
| Blocking validation (DB-04) | `python -m unittest tests.test_staging.ValidationTest -v` (real DSN) | 10/10 `ok` | ✓ PASS |
| Independent ogrinfo oracle (DB-04) | `python -m unittest tests.test_staging.ValidationOgrinfoOracleTest -v` (real DSN) | 1/1 `ok` | ✓ PASS |
| Post-validation DDL (DB-04) | `python -m unittest tests.test_staging.PostValidationDdlTest -v` (real DSN) | 10/10 `ok` | ✓ PASS |
| Production isolation on induced failure (DB-05) | `python -m unittest tests.test_staging.ProductionIsolationTest -v` (real DSN) | 2/2 `ok` | ✓ PASS |
| PROHIB-08 mechanism (not_applicable ValueError guard) | `python -m unittest tests.test_evidence -v` | 83/83 `ok` | ✓ PASS |
| Full test suite, both live DSNs set | `python -m unittest discover -s tests` | 704 tests, OK, 0 skipped | ✓ PASS |
| Live catalogue check: `public` unchanged | `psql \dt public.*` / `\dv public.*` against the real server | Exactly `spatial_ref_sys` (table) + `geography_columns`/`geometry_columns` (views) -- PostGIS's own objects, nothing else | ✓ PASS |
| Live catalogue check: `vicmap` holds only legitimately promoted tables | `psql \dt vicmap.*` | 1 table (`vmadd_address`), a Phase-4 promotion, not a Phase-3 leak | ✓ PASS |
| Live catalogue check: `vicmap_audit` holds only Phase-4/05.1 audit tables | `psql \dt vicmap_audit.*` | `publication`, `staging_validation` -- both additive, neither touches `public` | ✓ PASS |
| Destructive-SQL grep: `staging.py`/`stage_order.py` | `grep -inE "\bDROP\b\|\bTRUNCATE\b\|\bRENAME\b\|\bCASCADE\b"` | 1 hit, English prose "connection drop" in a docstring -- zero executable SQL | ✓ PASS |
| Diff check: shared-file changes since prior digest are additive only | `git diff 86ab35b..HEAD -- vicmap_acquire/staging.py vicmap_acquire/evidence.py stage_order.py read_mailbox.py vicmap.toml flake.nix db/provision_vicmap_loader.sql` | No hunk modifies a Phase-3-owned function's existing body; `stage_order.py`'s one new call to `record_validation` runs strictly after `run_staging` succeeds | ✓ PASS |

### Anti-Patterns Found

`grep -n -E "TBD|FIXME|XXX|TODO|HACK|PLACEHOLDER"` across every file this phase's `covered_files` list marks as an impl file (`vicmap_acquire/staging.py`, `vicmap_acquire/evidence.py`, `vicmap_acquire/manifest.py`, `stage_order.py`, `read_mailbox.py`, `db/provision_vicmap_loader.sql`, `vicmap.toml`, `flake.nix`) returns one hit: a docstring's literal wording ("ASCII-escaped `\uXXXX`" in `manifest.py`, JSON escape syntax, not a debt marker) -- unchanged since the prior round, no referenced follow-up needed.

`grep -inE "\bDROP\b|\bTRUNCATE\b|\bRENAME\b|\bCASCADE\b"` across `vicmap_acquire/staging.py` and `stage_order.py` returns one hit, the English word "drop" inside a Phase-4 docstring ("connection drop mid-insert") -- not executable SQL.

Code review (`03-REVIEW.md`/`03-REVIEW-FIX.md`): 0 critical, 6 warning (WR-01..WR-06, all fixed, re-confirmed live this session), 2 info (IN-01/IN-02, explicitly out of scope). No new anti-patterns found in this round's re-read.

**Info -- open backlog ledger items (out of scope for Phase 3, not blockers):**

| Ledger ID | Backlog | Description |
|-----------|---------|--------------|
| WINDOWS.md #2 + #7 | Phase 999.1 | GDA94<->GDA2020 Vicgrid transform selects the grid-free Helmert operation, not the vendored ICSM grid, because PROJ's own accuracy metadata ranks Helmert higher (~2 mm difference on a real ADDRESS point). Explicitly assessed as an architectural decision in 03-06-SUMMARY.md, not a code defect; see PROHIB-09 override below. |

**Warning -- open backlog ledger item (out of scope for Phase 3, not a blocker):**

| Ledger ID | Backlog | Description |
|-----------|---------|--------------|
| WINDOWS.md #4 | Phase 999.2 | `db/provision_vicmap_loader.sql` assumes the target database already exists; a fresh server needs a manual `CREATE DATABASE` first. Documented deviation, tracked for a future plan, not a Phase 3 must-have. |

### Requirements Coverage

| Requirement | Status | Evidence |
|-------------|--------|----------|
| DB-01 | ✓ SATISFIED | Truth 1 |
| DB-02 | ✓ SATISFIED | Truth 2 |
| DB-03 | ✓ SATISFIED | Truth 3 |
| DB-04 | ✓ SATISFIED | Truth 4 |
| DB-05 | ✓ SATISFIED | Truth 5 |

REQUIREMENTS.md marks all five `[x]` complete, status "Complete" in its traceability table. No orphaned requirements: REQUIREMENTS.md maps exactly DB-01..DB-05 to Phase 3, and all five appear across the six plans' `requirements` frontmatter fields (03-01: DB-01/03/04; 03-02: DB-01/02/05; 03-03: DB-01/02/03; 03-04: DB-01/02/03; 03-05: DB-04; 03-06: DB-03/05) -- every requirement ID is claimed by at least one plan, and each of DB-01..DB-05 is claimed by at least two.

### Prohibitions (must_haves.prohibitions)

Three judgment-tier prohibitions across the six plans, all self-flagged `status: "unresolved"`, `verification: null` ("Flagged-unverified by the spec-less prohibition probe; no wired-check descriptor is available"). Per ADR-550's mode-dependent soft gate, an LLM-judge verdict is non-authoritative for each; PROHIB-08 and PROHIB-10 already carry a human sign-off from the prior verification round (preserved below, and re-confirmed by fresh live evidence this session). PROHIB-09 is resolved this round via a formal override referencing the pre-existing 2026-09-21 architectural decision (see `overrides` in frontmatter) -- it does not require a fresh human sign-off because the underlying deviation was already decided by a human and is tracked as a non-blocking backlog item, per this round's explicit scope instruction.

| ID | Requirement | Statement | Verdict | Basis |
|----|-------------|-----------|---------|-------|
| PROHIB-08 | DB-04 | MUST NOT present a validation result as complete when a check was skipped or a geometry was repaired | **HELD** -- human sign-off (2026-09-23), reconfirmed live this session | `SuccessEvent.staging_layer_validated`'s `ValueError` guard; `tests/test_evidence.py` 83/83 `ok` this session |
| PROHIB-09 | DB-03 | MUST NOT report a layer as successfully staged when coordinates were produced by a grid-free, Helmert, or ballpark fallback operation | **PASSED (override)** -- ballpark fallback IS blocked (fixed 03-04); Helmert-vs-grid selection is an accepted architectural deviation, backlog 999.1 | 03-06-SUMMARY.md "Grid Question -- Settled, Not Left Open" (`human_judgment: true`, 2026-09-21); WINDOWS.md #2/#7 |
| PROHIB-10 | DB-05 | MUST NOT drop, truncate, rename, or otherwise destroy any existing table, index, or schema | **HELD** -- human sign-off (2026-09-23), reconfirmed live this session | Zero destructive-SQL keywords in code; live catalogue independently checked clean this session; `ProductionIsolationTest` 2/2 `ok` |

### Gaps Summary

No functional gaps. All 5 roadmap success criteria and every plan-level must-have across all six plans were re-verified against the current tree, with fresh live evidence gathered this session for every Phase-3-owned function -- including, for the first time in this phase's verification history, `PrivilegePreflightTest`'s fail-closed branches run live in the same session as everything else (both DSNs were available). Every change to a shared file since the prior digest (Phase 4 and 05.1 work) was diffed line-by-line and confirmed additive, touching no Phase-3-owned function body.

Two documentation gaps in the prior round are corrected here: (1) the prior report's body said "Status: human_needed" while its own frontmatter and Human Sign-Off section said passed -- this round's body is consistent with its frontmatter; (2) the prior report's Prohibitions/human_verification sections omitted PROHIB-09 entirely -- this round adds it and resolves it via an override that references the pre-existing, dated architectural decision, so it does not reopen human sign-off. Both are recorded under `re_verification.gaps_closed` above.

---

## Human Sign-Off (ADR-550 judgment-tier gate) -- carried forward verbatim

- **Signed off:** 2026-09-23 by operator (bhillermann@vegetationlink.com.au), during autonomous re-verification.
- **Items:** PROHIB-08 (DB-04) and PROHIB-10 (DB-05) -- both accepted as HELD.
- **Basis:** LLM-judge verdict HELD/high-confidence plus the live evidence recorded above (real PostGIS run, 507 tests at the time, zero destructive-SQL keywords, clean live catalogue). This is a human sign-off on a judgment-tier soft gate, **not** a wired machine check -- no automated descriptor exists for these two prohibitions. Status advanced to `passed` on the strength of that sign-off.
- **This round:** both prohibitions independently reconfirmed HELD against a larger live test surface (704 tests, both DSNs, `PrivilegePreflightTest` included) and a freshly re-checked live catalogue. No regression found. Sign-off is not downgraded.

---

_Verified: 2026-09-30_
_Verifier: Claude (gsd-verifier)_
