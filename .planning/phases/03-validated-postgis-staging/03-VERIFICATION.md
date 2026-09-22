---
phase: 03-validated-postgis-staging
verified: 2026-09-22T00:20:00Z
status: passed
score: 5/5 must-haves verified
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
covered_digest: "v1:sha256:a1e028169785de70459f3644083e45d3d2e7f65a904d167eb2f36ff2ddcc595c"
behavior_unverified: 0
overrides_applied: 0
re_verification:
  previous_status: human_needed
  previous_score: 4/5
  gaps_closed:
    - "DB-02: preflight_staging_privileges's four fail-closed branches (PrivilegeDenied on missing staging-schema CREATE, PrivilegeDenied on public-schema CREATE, PrivilegeDenied on superuser role, TargetSridUnresolved on unregistered SRID) have now executed for the first time ever, live, and raised as designed. A real defect (CREATE ROLE's password composed as a bind parameter, which PostgreSQL rejects in a utility statement) blocked all five PrivilegePreflightTest methods from ever running; fixed in ba3ef2b by composing the password as sql.Literal. With that fixed, the operator supplied VICMAP_TEST_POSTGRES_SUPERUSER_DSN per-shell (op:// references only, never in flake.nix) and ran the suite: 5/5 passed, 0 skipped, 0 errors. Teardown independently re-verified against the live catalogue: no staging_preflight% role/schema remain, public holds only PostGIS's own system tables."
  gaps_remaining: []
  regressions: []
---

# Phase 03: Validated PostGIS Staging Verification Report

**Phase Goal:** Every selected layer is safely loaded and spatially validated in isolated staging while existing production data remains unchanged.
**Verified:** 2026-09-22
**Status:** passed
**Re-verification:** Yes — after gap closure (prior pass: human_needed, 4/5, dated 2026-09-21)

## Goal Achievement

### Observable Truths (ROADMAP Success Criteria)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Operator connects to the configured PostGIS service on port 5432 and sees its non-secret database identity and PostGIS version. | ✓ VERIFIED (regression check — unchanged since prior pass) | No code touched by the DB-02 fix (`ba3ef2b` touched only `tests/test_staging.py` and `03-UAT.md`). Prior pass's live evidence stands: `read_database_identity`, live `ConnectionIdentityTest`, live `stage_order.py --preflight-only` capture. |
| 2 | The loader proves it has the necessary transaction, schema, and table privileges before any load starts. | ✓ VERIFIED | Both the PASS path (already live-demonstrated in the prior pass) and, now, all four FAIL-CLOSED branches have executed against a real superuser connection and a real throwaway role: `test_fail_path_no_create_on_staging_schema`, `test_fail_path_create_on_public`, `test_fail_path_superuser`, `test_fail_path_unknown_srid` — all `ok`, 0.416s, 0 skips, 0 errors (03-UAT.md, verbatim result reproduced by the orchestrator's independent instruction). This is the first execution of these branches ever, live or in CI — closing the one gap the prior pass identified. A real defect (`CREATE ROLE ... LOGIN PASSWORD %s` — PostgreSQL rejects bind params in utility statements) had silently blocked every prior attempt to run this fixture; fixed in `ba3ef2b` by composing the password with `sql.Literal`. Teardown independently re-verified against the live catalogue after the run: no `staging_preflight%` role or schema remain, `public` unchanged. |
| 3 | Every selected manifest layer loads into a uniquely named staging table, with no table created or modified in `public`. | ✓ VERIFIED (regression check — unchanged since prior pass) | No code path relevant to this truth changed. Prior pass's live evidence stands: three distinct staging tables from consecutive live runs, `LoadIntegrationTest`/`ProductionIsolationTest` live, orchestrator-confirmed `public` unchanged. |
| 4 | Blocking validation reports row counts, geometry columns and types, SRIDs, validity, and extents for all staging tables. | ✓ VERIFIED (regression check — unchanged since prior pass) | No code path relevant to this truth changed. Prior pass's live evidence stands: `ValidationTest` (11 live methods) and the independent `ogrinfo` oracle both ran live. |
| 5 | A failed load or validation leaves all existing production tables unchanged. | ✓ VERIFIED (regression check — unchanged since prior pass) | No code path relevant to this truth changed. Prior pass's live evidence stands: `ProductionIsolationTest` byte-identical catalog snapshots under two induced failures; no `DROP`/`TRUNCATE`/`RENAME` anywhere in the pipeline code. |

**Score:** 5/5 truths verified (0 present, behavior-unverified)

### What Changed Since the Prior Pass

The prior pass (2026-09-21) scored 4/5 and routed to `human_needed` because `preflight_staging_privileges`'s four fail-closed branches — the actual mechanism that rejects an under-privileged role — had never executed anywhere, live or in CI. The only test that manipulates real ACLs to exercise them, `PrivilegePreflightTest` (5 methods), unconditionally skipped for want of `VICMAP_TEST_POSTGRES_SUPERUSER_DSN`.

This session:

1. Discovered the actual reason the fixture had *never once run*: it wasn't only the missing DSN — `PrivilegePreflightTest.setUp` composed `CREATE ROLE {} LOGIN PASSWORD %s` with a bind parameter, which PostgreSQL rejects in a utility statement (`syntax error at or near "$1"`). Every one of the five methods would have errored the instant the DSN was ever supplied. This is the same defect class as `616d50a` (`staging._connect`'s `SET statement_timeout`) — it survived because the code path had zero executions to be caught by.
2. Fixed it in `ba3ef2b`, composing the password as `sql.Literal` instead.
3. The operator supplied the superuser DSN per-shell (via `op read` references, never a literal secret, never written to a file or passed as argv) and ran the five methods directly. Result, verbatim:

   ```
   test_fail_path_create_on_public ................................ ok
   test_fail_path_no_create_on_staging_schema ..................... ok
   test_fail_path_superuser ....................................... ok
   test_fail_path_unknown_srid .................................... ok
   test_pass_path_proves_capability_and_leaves_nothing_behind ..... ok
   Ran 5 tests in 0.416s -- OK
   ```

4. The orchestrator independently re-checked the live catalogue after the run: no `staging_preflight%` role or schema remain, and `public` holds only PostGIS's own `geography_columns`/`geometry_columns`/`spatial_ref_sys` — confirming the rolled-back probe genuinely leaves nothing behind, not merely that the test framework claims so.
5. Full suite re-run: 507 tests OK (32 skipped in a DSN-less shell — expected, since no live class can run without credentials in that context). Prior-phase regression gate: 425 tests OK, zero skips (unchanged from the prior pass).
6. `03-UAT.md` moved from its one pending item to `status: passed`, 1/1 passed, 0 pending, 0 gaps.

This is genuinely different from the prior pass's evidence class: the prior pass could only show the PASS branch executing (because every live exercise of `preflight_staging_privileges` happened to run against an already-correctly-privileged role). This pass shows all four FAIL-CLOSED branches raising their named exception against a role deliberately built to lack each specific privilege — the actual proof DB-02 requires.

### Required Artifacts

No artifact-level changes since the prior pass beyond the `tests/test_staging.py` fixture fix. All artifacts previously verified stand unchanged; see the prior pass's artifact table (reproduced by reference, not re-litigated here since no code under test changed):

| Artifact | Status |
|----------|--------|
| `vicmap_acquire/staging.py` | ✓ VERIFIED (unchanged) |
| `stage_order.py` | ✓ VERIFIED (unchanged) |
| `db/provision_vicmap_loader.sql` | ✓ VERIFIED, known non-blocking gap (WINDOWS.md #4, open, carried forward) |
| `vicmap_acquire/evidence.py` | ✓ VERIFIED (unchanged) |
| `vicmap_acquire/manifest.py` | ✓ VERIFIED (unchanged) |
| `flake.nix` | ✓ VERIFIED (unchanged) — deliberately still does NOT carry `VICMAP_TEST_POSTGRES_SUPERUSER_DSN`; confirmed correct design, see WINDOWS.md #6 discussion below |
| `tests/test_staging.py` | ✓ VERIFIED — `PrivilegePreflightTest`'s password-composition defect fixed (`ba3ef2b`); all 5 methods now execute and pass with a supplied DSN |
| `.planning/phases/03-validated-postgis-staging/COVERAGE.md` | ✓ VERIFIED (unchanged) |

### Key Link Verification

Unchanged since the prior pass — no key link touched by this round's fix. All six links previously verified `✓ WIRED` stand.

### Requirements Coverage

| Requirement | Status | Evidence |
|-------------|--------|----------|
| DB-01 | ✓ SATISFIED | Truth 1 |
| DB-02 | ✓ SATISFIED | Truth 2 — both PASS and all four FAIL-CLOSED branches now live-demonstrated |
| DB-03 | ✓ SATISFIED | Truth 3 |
| DB-04 | ✓ SATISFIED | Truth 4 |
| DB-05 | ✓ SATISFIED | Truth 5 |

REQUIREMENTS.md marks all five as `[x]` complete, status "Complete" in its traceability table. No orphaned requirements: REQUIREMENTS.md maps exactly DB-01..DB-05 to Phase 3, and all five appear in at least one plan's `requirements` frontmatter field.

### WINDOWS.md Reassessment

**#6 (PrivilegePreflightTest's 5 methods permanently skip for want of a superuser DSN) — CLOSED.** The underlying claim the ledger entry made — "these branches have never executed" — is no longer true: they executed, all five passed, and teardown was independently re-verified. Marked `fixed` in this session (`gsd-tools windows fixed 6`), `resolved_at: 2026-09-22T00:16:17.175Z`. `open_count` is now 4 (`waived_count: 0`, `fixed_count: 3`, `total_count: 7`).

Going forward, `PrivilegePreflightTest` will still skip by default in any shell that doesn't export `VICMAP_TEST_POSTGRES_SUPERUSER_DSN` — that is by design, not a regression: the DSN is supplied per-shell by the operator via `op://` references and dies with the shell, deliberately *not* added to `flake.nix`'s `opnixEnvConfig`. That config feeds every devshell; a superuser entry there would hand elevated access to every process in every `nix develop` session, directly contradicting D-59/DB-05 — the very invariant this phase exists to establish. This is correctly a documented, repeatable operator step (recorded in `03-UAT.md`'s "Option A"), not an unresolved defect. Closing #6 records that the step has now been *performed and demonstrated to work*, not that it has become unnecessary in future shells.

**Carried forward, unchanged, non-blocking to this phase's goal (per assessment instructions):**
- **#1** (`vicmap.toml` placeholder URL prefix, Phase 01, open) — out of scope for Phase 03.
- **#2 / #7** (vendored ICSM grid never selected — PROJ's own accuracy metadata ranks a grid-free Helmert transform higher) — a transform-accuracy question for one CRS pair, not a staging correctness defect; DB-01..DB-05's guarantees (row count, type, SRID, validity, extent) do not depend on which correct transform PROJ selects.
- **#4** (`provision_vicmap_loader.sql` assumes the database pre-exists) — operator-run, one-time provisioning script, documented gap.

### Anti-Patterns Found

No new anti-patterns introduced by this round's change. The fix itself (`ba3ef2b`) is test-only (`tests/test_staging.py` + `03-UAT.md`), adds an explanatory comment citing the same defect class as a prior fix (`616d50a`), and does not touch any pipeline code path. Code review `03-REVIEW.md` (0 critical, 6 warning, 2 info, all previously catalogued and non-blocking) stands unchanged.

### Behavioral Spot-Checks / Live Evidence (Executed, Not Merely Claimed)

| Behavior | Evidence | Status |
|----------|----------|--------|
| `PrivilegePreflightTest`'s 4 fail-closed branches + 1 pass-path method | Operator-run against a real superuser DSN, orchestrator-verified verbatim result: 5/5 `ok`, `Ran 5 tests in 0.416s -- OK` | ✓ PASS |
| Teardown leaves nothing behind | Orchestrator independently queried the live catalogue post-run: no `staging_preflight%` role or schema; `public` holds only PostGIS's own 3 system tables | ✓ PASS |
| Full test suite (DSN-less shell) | 507 tests, OK (32 skipped — expected without any live DSN) | ✓ PASS |
| Regression gate (15 prior-phase test files, excluding `test_staging.py`) | 425 tests, OK, zero skips | ✓ PASS |
| `03-UAT.md` | `status: passed`, 1/1, 0 pending, 0 gaps | ✓ PASS |

### Gaps Summary

None. The one item that routed this phase to `human_needed` in the prior pass — DB-02's fail-closed privilege branches lacking any executed evidence — has been closed with genuine, orchestrator-verified live evidence: all four negative branches raised their named exception against a real, deliberately under-privileged role, and the rolled-back probe left nothing behind on independent re-check. A real defect (bind parameter in a utility statement) that had silently prevented this test from ever running even once is fixed and documented. WINDOWS.md #6 is closed. Three WINDOWS.md items remain open (#1, #2/#7, #4) but are explicitly out of scope or non-blocking to this phase's goal per the assessment instructions and are carried forward unchanged, not re-litigated here.

---

_Verified: 2026-09-22_
_Verifier: Claude (gsd-verifier)_
