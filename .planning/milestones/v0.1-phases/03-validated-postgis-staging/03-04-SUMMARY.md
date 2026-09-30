---
phase: 03-validated-postgis-staging
plan: 04
subsystem: database
tags: [postgis, ogr2ogr, psycopg, staging, gdal, proj, privilege-preflight]

# Dependency graph
requires:
  - phase: 03-validated-postgis-staging (03-01, 03-02, 03-03)
    provides: psycopg dependency, vendored ICSM grid mechanism, [database] policy schema, evidence.py DB-01..DB-04 event/reason-code vocabulary, manifest reader
provides:
  - "vicmap_acquire/staging.py: StagingPolicy, DatabaseIdentity, LayerValidation, the closed staging failure hierarchy, staging_table_name, read_database_identity, preflight_staging_privileges (full DB-02 proof), build_ogr2ogr_command, load_layer, validate_layer, run_staging"
  - "stage_order.py: guarded --config/--preflight-only CLI"
  - "db/provision_vicmap_loader.sql: operator-run, superuser-only provisioning script"
  - "A real, live-verified end-to-end load: config -> manifest -> connection -> privilege proof -> ogr2ogr -> row-count check -> operator output, against the real vicmap_loader role and the real 4,222,035-row VMADD.gdb ADDRESS delivery"
affects: [03-05, 03-06]

# Actuals (#2632)
actuals:
  tokens: 16263
  tasks: 3
  commits: 5
plan_head_before: 81f4987bbc0bb04946a8edb5e914b5ea08d8c900

# Tech tracking
tech-stack:
  added: [psycopg 3.3.4 (already added in 03-01; first real usage here)]
  patterns:
    - "Closed staging failure hierarchy: one StagingFailure(RuntimeError) subclass per D-61/DB-0x failure mode, .code equals evidence.ReasonCode, no interpolated text"
    - "Rolled-back real CREATE TABLE/CREATE INDEX probe for privilege proof (has_table_privilege cannot be used pre-existence)"
    - "GDAL coordinate-transform safety flags must be passed as -ct_opt NAME=VALUE, not --config OGR_CT_* -- --config only reaches CPL configuration options, and OGR_CT_ONLY_BEST/OGR_CT_ALLOW_BALLPARK are not CPL options at all"

key-files:
  created:
    - vicmap_acquire/staging.py
    - stage_order.py
    - db/provision_vicmap_loader.sql
  modified:
    - tests/test_staging.py
    - vicmap_acquire/evidence.py
    - tests/test_evidence.py

key-decisions:
  - "Task 1 checkpoint: operator confirmed option A -- geom/gid column names and the single target_srid=7899 estate locked as CONTEXT.md specified (D-45/D-46/D-49), before Task 2 wrote them into a real table."
  - "Live verification found three real bugs in the code Task 2/3 had already committed (SET statement bind parameter, a 200-char server-version-text bound, and the wrong GDAL flag syntax for the fail-closed transform guard); all three were auto-fixed under Rule 1 with regression tests, not deferred, because the checkpoint's own human-check could not otherwise complete."
  - "db/provision_vicmap_loader.sql's missing CREATE DATABASE step is documented as a known gap (WINDOWS.md #4) rather than silently patched into the script -- the script's authorized scope (Task 3) is exactly the five items D-59/DB-02 need, and adding CREATE DATABASE is an operator-prerequisite decision, not a Rule 1/2/3 auto-fix, since it changes what the script assumes about who runs it and when."

requirements-completed: [DB-01, DB-02, DB-03]

coverage:
  - id: D1
    description: "One operator command (stage_order.py --preflight-only) reports the six D-61 identity fields and exits 0 without loading anything, with no password/connection-string anywhere in the output"
    requirement: "DB-01"
    verification:
      - kind: manual_procedural
        ref: "live run: nix develop -c python stage_order.py --preflight-only against the real vicmap/vicmap_loader database"
        status: pass
    human_judgment: false
  - id: D2
    description: "The DB-02 privilege preflight proves capability with a rolled-back real CREATE, proves the loader cannot write to public, and leaves nothing behind"
    requirement: "DB-02"
    verification:
      - kind: unit
        ref: "tests/test_staging.py#PrivilegePreflightTest (skips without VICMAP_TEST_POSTGRES_SUPERUSER_DSN, per plan design)"
        status: unknown
      - kind: manual_procedural
        ref: "live run: stage_order.py --preflight-only succeeded against the real vicmap_loader role (non-superuser, USAGE+CREATE on vicmap_staging, no CREATE on public -- operator-supplied psql verification block, all five facts pass)"
        status: pass
    human_judgment: true
    rationale: "PrivilegePreflightTest's fail-path assertions require VICMAP_TEST_POSTGRES_SUPERUSER_DSN, not available in this session; DB-02's real proof was exercised live instead (see Live Verification below), which is stronger evidence than the unit test alone but was not captured by an automated status."
  - id: D3
    description: "A manifest layer (VMADD.gdb ADDRESS, 4,222,035 features) loads into a uniquely, run-timestamped staging table with geom/gid columns and SRID 7899, public provably untouched, across three consecutive live runs"
    requirement: "DB-03"
    verification:
      - kind: manual_procedural
        ref: "live run: stage_order.py executed three times against runs/OK0VUZ/20260921T060958Z/, producing vmadd_address_20260921t070323z, _070443z, _071736z, each row_count=4222035, geom SRID=7899, public schema byte-identical to baseline before/after"
        status: pass
    human_judgment: false
  - id: D4
    description: "The fail-closed transform posture (D-51/PROHIB-09) is actually enforced by GDAL, not silently accepted as an unknown option"
    verification:
      - kind: unit
        ref: "tests/test_staging.py#Ogr2ogrFlagOracleTest.test_only_best_and_allow_ballpark_flags_are_recognized_by_the_real_binary"
        status: pass
    human_judgment: false
  - id: D5
    description: "The GDA94-Vicgrid-to-GDA2020-Vicgrid grid-vs-Helmert question (carried from 03-01) remains open; this run's null result (source SRID already equals target) does not answer it, and a second, more specific verification-method gap was found and recorded"
    verification: []
    human_judgment: true
    rationale: "Requires a layer with a genuinely different source SRID to settle, plus a verification method other than pyproj's TransformerGroup (shown here to be structurally blind to PROJ_DATA in this pyproj build). Recorded as open in STATE.md and WINDOWS.md; not this plan's task to close."

duration: 95min
completed: 2026-09-21
status: complete
---

# Phase 3 Plan 4: Staging Tracer, Live-Verified Against the Real Database Summary

**A digest-verified 4.2M-feature ADDRESS layer loads three times into distinctly timestamped `vicmap_staging` tables via the real `vicmap_loader` role, with `public` provably untouched -- after live verification caught and fixed three real bugs the original commits had shipped, including a fail-closed transform guard that GDAL was silently ignoring.**

## Performance

- **Duration:** ~95 min total across the original build (Tasks 1-3, prior session) and this continuation's live human-check
- **This continuation:** ~55 min (bug discovery, three fixes, three live loads, grid investigation, SUMMARY)
- **Tasks:** 3 (Task 1 checkpoint:decision, Task 2 tracer, Task 3 auto) -- all complete
- **Commits this continuation:** 3 fix commits (`616d50a`, `e53d950`, `d55544a`), on top of the prior session's 2 (`4cea5f9`, `b900a2f`)
- **Files modified:** 6 (2 created new in prior session, 4 touched by this continuation's fixes)

## Accomplishments

- Confirmed the published staging contract (`geom`/`gid`/SRID 7899) as CONTEXT.md locked it -- operator approved option A at the Task 1 checkpoint.
- Built `vicmap_acquire/staging.py`: policy, identity, the closed failure hierarchy, `ogr2ogr` command construction, load, row-count validation, and orchestration.
- Built `stage_order.py`: a guarded CLI with `--preflight-only`.
- Built `db/provision_vicmap_loader.sql`: the operator's superuser-only provisioning script.
- Made the DB-02 privilege preflight prove capability with a real, rolled-back `CREATE TABLE`/`CREATE INDEX`, not grant-metadata inference.
- **Live-verified all of the above against the real, newly-provisioned PostgreSQL 17.5/PostGIS 3.5.2 server** and found three real bugs that the unit-test suite's design (deliberately no-database for the pure-construction classes, skip-not-fail for the live classes) could not catch on its own -- fixed all three under Rule 1, each with a regression test that does not depend on a live server.
- Ran the real 4,222,035-row `VMADD.gdb` ADDRESS layer through the pipeline three times, proving idempotent-by-timestamp naming and `public` non-interference on real production-shaped data, not just fixtures.

## Live Verification (Task 2 human-check, executed for real)

This is the substantive record the plan's `<human-check>` asked for, executed after the operator finished provisioning (see Deviations for the provisioning gap found along the way).

**1. `stage_order.py --preflight-only`:**
```
{"dbname":"vicmap","event":"database_identity","host":"127.0.0.1","port":5432,
 "postgis_version":"POSTGIS=\"3.5.2 dea6d0a\" ... PROJ=\"7.2.1 ...\" ...",
 "role":"vicmap_loader",
 "server_version":"PostgreSQL 17.5 (Debian 17.5-1.pgdg110+1) ..."}
```
Exit code 0. All six D-61 fields present (host, port, dbname, role, server_version, postgis_version). Confirmed no `password` substring and no `PG:dbname=` connection-string fragment anywhere in stdout.

**2. Real load, run twice, then a third time after the `-ct_opt` fix, against `runs/OK0VUZ/20260921T060958Z/` (the real VMADD.gdb ADDRESS layer, 4,222,035 features per the digest-verified manifest):**

| Run | Staging table | row_count | Duration |
|---|---|---|---|
| 1 | `vmadd_address_20260921t070323z` | 4222035 | 39.2s |
| 2 | `vmadd_address_20260921t070443z` | 4222035 | 39.0s |
| 3 (post `-ct_opt` fix) | `vmadd_address_20260921t071736z` | 4222035 | 39.4s |

**Row count: matches the manifest's declared `feature_count=4222035` exactly, on all three runs.** No mismatch, no `RowCountMismatch`.

Each run produced a distinctly timestamp-suffixed table; the earlier run's table was left completely untouched by the later run (verified via `\dt vicmap_staging.*` showing all three tables present simultaneously with the same row count each).

**3. `psql \dt public.*`, before and after all three runs:**
```
 Schema |      Name       | Type  |  Owner
--------+-----------------+-------+---------
 public | spatial_ref_sys | table | gisuser
(1 row)
```
Byte-identical before and after. `spatial_ref_sys` is PostGIS's own extension table (owned by `gisuser`, not `vicmap_loader`); no new table, view, or object appeared in `public` at any point.

**4. Columns and SRID**, checked directly on the first staged table: `gid integer NOT NULL` (primary key, `nextval` sequence default), `geom` present (D-46), and `ST_SRID(geom) = 7899` (D-49) confirmed across sampled rows.

**5. `ConnectionIdentityTest` and `LoadIntegrationTest` (`VICMAP_TEST_POSTGRES_DSN` pointed at the real `vicmap_loader`/`vicmap` connection, ephemeral for this check only -- not persisted to any config):**
- `ConnectionIdentityTest` **no longer skips and passes** (it failed with a raw `ValueError` before the server-version-text bound fix below; the fix cleared that and it now genuinely un-skips and asserts against real server output).
- `LoadIntegrationTest` **still does not run to completion** -- it `ERROR`s with `psycopg.errors.InsufficientPrivilege: permission denied for database vicmap`, not a clean skip. Its fixture calls `CREATE SCHEMA <throwaway>`, which requires database-level `CREATE` privilege. `vicmap_loader` deliberately does **not** have that privilege (D-59: it owns exactly `vicmap_staging` and `vicmap`, nothing else) -- this is the role behaving correctly, not a pipeline bug. I did not work around this by granting elevated privilege or creating a schema outside `vicmap_staging`/`vicmap`, since doing so would exceed this task's own database-safety confinement. The equivalent live proof was instead obtained directly through `stage_order.py` itself (table 2 above), which only ever touches `vicmap_staging`. Recorded as WINDOWS.md #5 (`unrun-verify`) so this gap does not silently reappear as "passing" later.

## Task Commits

Each task was committed atomically (Tasks 1-3 from the original session; the three fixes below are this continuation's contribution):

1. **Task 2: stage one manifest layer end to end** - `4cea5f9` (feat) -- prior session
2. **Task 3: DB-02 privilege capability proof + provisioning script** - `b900a2f` (feat) -- prior session
3. **Fix: SET timeout bind-parameter bug** - `616d50a` (fix) -- this continuation
4. **Fix: server-version text bound** - `e53d950` (fix) -- this continuation
5. **Fix: `-ct_opt` flag syntax for the fail-closed transform guard** - `d55544a` (fix) -- this continuation

**Plan metadata:** (this commit, following this SUMMARY)

## Files Created/Modified

- `vicmap_acquire/staging.py` - StagingPolicy, DatabaseIdentity, LayerValidation, closed failure hierarchy, connect/identity/preflight/build-command/load/validate/orchestrate. Fixed in this continuation: `_connect`'s `SET` statements, `build_ogr2ogr_command`'s transform-safety flags.
- `stage_order.py` - `--config`/`--preflight-only` CLI, unchanged this continuation.
- `db/provision_vicmap_loader.sql` - operator provisioning script, unchanged this continuation (see Deviations for the documented gap).
- `vicmap_acquire/evidence.py` - widened `_SERVER_VERSION_TEXT`'s bound from 200 to 1024 characters.
- `tests/test_staging.py` - added `ConnectionSetupTest`, `test_fail_closed_flags_use_the_ct_opt_form_gdal_actually_accepts`, `Ogr2ogrFlagOracleTest`.
- `tests/test_evidence.py` - replaced the 200-char boundary test with a 1024-char one; added a 345-char real-world PostGIS-string regression fixture.

## Decisions Made

- Locked the staging contract at the Task 1 checkpoint: `geom`/`gid`/single `target_srid=7899` (option A), as CONTEXT.md specified.
- All three bugs found during the live human-check were auto-fixed under Rule 1 (broken behavior blocking the very checkpoint verifying it), not deferred -- see Deviations.
- The missing `CREATE DATABASE` step in the provisioning script is recorded as a known gap, not silently patched in -- see Deviations and Next Phase Readiness.
- Did not attempt to make `LoadIntegrationTest` pass against the real `vicmap_loader` role by granting it schema-creation privilege or by creating a throwaway schema outside `vicmap_staging`/`vicmap` -- both would have exceeded this task's explicit database-safety confinement.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] `_connect`'s `SET statement_timeout`/`SET lock_timeout` used a bind parameter, which PostgreSQL's `SET` statement does not support**
- **Found during:** Task 2's live human-check, step 1 (`stage_order.py --preflight-only` against the real database)
- **Issue:** Every live connection attempt failed with `DatabaseConnectionFailed`. Root cause: `cursor.execute("SET statement_timeout = %s", (value,))` -- PostgreSQL's `SET` is a utility statement, not DML, and rejects a bind parameter outright (`syntax error at or near "$1"`). This had never been caught because every test exercising `_connect` either mocks it or is a live-database test that skips without a server -- no unit test previously existed for `_connect`'s own SQL construction.
- **Fix:** Compose both `SET` statements with `psycopg.sql.SQL(...).format(sql.Literal(value))` instead of a bind parameter. Both values are already validated positive integers (`StagingPolicy.__post_init__`), so this is exactly as safe as the bind parameter would have been.
- **Files modified:** `vicmap_acquire/staging.py`, `tests/test_staging.py`
- **Verification:** New `ConnectionSetupTest` (no database) mocks `psycopg.connect` and asserts the composed `SET` statements carry no `%s`/`$1` placeholder. Live-verified: `stage_order.py --preflight-only` now connects and reports identity successfully.
- **Commit:** `616d50a`

**2. [Rule 1 - Bug] `_SERVER_VERSION_TEXT`'s 200-character bound rejected real server output**
- **Found during:** Task 2's live human-check, step 1, after fixing deviation 1
- **Issue:** `read_database_identity` succeeded, but rendering the event via `evidence.SuccessEvent.database_identity(...)` raised `ValueError: server version text is not a safe scalar`. The real `PostGIS_Full_Version()` string on this server is 345 characters (it enumerates GEOS/PROJ/LIBXML/LIBJSON/LIBPROTOBUF/WAGYU versions plus PROJ's writable-directory and database paths) -- `evidence.py`'s `_SERVER_VERSION_TEXT = re.compile(r"[ -~]{1,200}")` had never been checked against a real PostGIS server's actual output.
- **Fix:** Widened the bound to 1024 characters -- still a finite, bounded cap (satisfying D-61's anti-smuggling intent), just one wide enough for real banners.
- **Files modified:** `vicmap_acquire/evidence.py`, `tests/test_evidence.py`
- **Verification:** New `test_postgis_version_at_real_world_length_is_accepted` pins the exact 345-character real-world string observed live; the old 200-char boundary test was updated to assert against the new 1024 bound instead of silently continuing to test a since-abandoned limit.
- **Commit:** `e53d950`

**3. [Rule 1 - Bug, security-relevant] `build_ogr2ogr_command`'s fail-closed transform flags used a GDAL config-option syntax that does not exist**
- **Found during:** Independent investigation of the grid-vs-Helmert question (below), while running `ogr2ogr` directly with `CPL_DEBUG=ON`
- **Issue:** `--config OGR_CT_ONLY_BEST YES` / `--config OGR_CT_ALLOW_BALLPARK NO` are not real GDAL CPL configuration options. Running the exact constructed command with `CPL_DEBUG=ON` printed `Warning 1: Unknown configuration option 'OGR_CT_ONLY_BEST'.` and the same for `OGR_CT_ALLOW_BALLPARK` -- GDAL silently ignored both and proceeded with its own default (non-fail-closed) coordinate-operation selection. This meant **D-51's fail-closed posture and PROHIB-09's transparency requirement (T-03-19 in the threat model) were never actually enforced** by any load this plan or 03-01's testing performed -- confirmed via `strings` on `libgdal.so.39`, which lists `ONLY_BEST` and `ALLOW_BALLPARK` only as sub-options of the `-ct_opt <NAME>=<VALUE>` flag (`ogr2ogr --help` confirms `-ct_opt` is the real flag), never as bare `--config` option names.
- **Fix:** Changed the two flags to `-ct_opt ONLY_BEST=YES` and `-ct_opt ALLOW_BALLPARK=NO`.
- **Files modified:** `vicmap_acquire/staging.py`, `tests/test_staging.py`
- **Verification:** Updated `LoadCommandConstructionTest` to assert the new flag values; added `test_fail_closed_flags_use_the_ct_opt_form_gdal_actually_accepts` (asserts `-ct_opt` immediately precedes each value, and that the old bare names are absent); added `Ogr2ogrFlagOracleTest` -- a differential oracle that pulls the exact `-ct_opt` pair `build_ogr2ogr_command` emits and runs it through the real installed `ogr2ogr` binary against the tracer fixture with `CPL_DEBUG=ON`, asserting no "Unknown configuration option" warning appears. Live-verified: ran the corrected command against the real 4.2M-row delivery a third time (table 2, run 3) -- load still succeeds, row count still matches exactly.
- **Commit:** `d55544a`

---

**Total deviations:** 3 auto-fixed (all Rule 1 - bugs blocking the live human-check this task exists to run). **Impact:** All three were necessary for the pipeline to function against a real database at all (deviations 1-2) or for a security-relevant correctness guarantee to actually hold (deviation 3, PROHIB-09). None were scope creep -- each was discovered strictly while executing this task's own verification steps, on the exact code Task 2/3 had already committed, and none touches files outside `staging.py`/`evidence.py`/their tests.

### Provisioning gap found, not fixed (recorded, per plan_gap_to_record)

`db/provision_vicmap_loader.sql` assumes the target database already exists -- its usage comment says `psql -f db/provision_vicmap_loader.sql -d <dbname>` and its first statement is `CREATE ROLE`, not `CREATE DATABASE`. The operator's first provisioning attempt failed with `FATAL: database "vicmap" does not exist` and required running `CREATE DATABASE vicmap;` by hand as a superuser before the script itself would run.

**Disposition:** documented as a known gap (`WINDOWS.md` #4), not silently added to the script. Task 3's authorized scope was exactly the five items D-59/DB-02 need (role, extension, two schemas, no public grant) -- adding `CREATE DATABASE` changes what the script assumes about who runs it and in what order, which is an operator-facing provisioning-story decision, not a Rule 1/2/3 in-scope auto-fix for this plan. **03-05 and 03-06 must not assume `vicmap` already exists** when they document or automate any provisioning-adjacent step; the honest first step of provisioning this pipeline is "create the database," and neither this plan nor the script says so today.

## Grid Question (carried from 03-01, still open)

The plan asked: does `ogr2ogr -t_srs EPSG:7899` under `OGR_CT_ONLY_BEST=YES`/`OGR_CT_ALLOW_BALLPARK=NO` (now correctly `-ct_opt ONLY_BEST=YES`/`-ct_opt ALLOW_BALLPARK=NO`, per the fix above) actually use the vendored ICSM grid, or does a grid-free Helmert transform win?

**This run's null result does not answer the question**, exactly as flagged: `VMADD.gdb` ADDRESS's source SRID is already `EPSG:7899` (matches `target_srid`), so `ogr2ogr` performs zero coordinate transform -- `-t_srs` is a byte-identical passthrough. Confirmed live: `ST_SRID(geom) = 7899` on all three staged tables, with no distortion evidence obtainable one way or the other.

To investigate further (beyond what the null result could show), I constructed a synthetic test: reprojected the small `Order_TRACER1.zip` ADDRESS fixture from `EPSG:7899` to `EPSG:3111` (GDA94 Vicgrid) using `ogr2ogr`, then ran it back through `EPSG:3111 -> EPSG:7899` -- a genuine datum-crossing transform this time. Two independent findings resulted:

1. **`pyproj`'s `TransformerGroup` -- the exact method 03-01's `RESEARCH.md` cites as proof the grid resolves -- cannot see `PROJ_DATA` at all in this pyproj build.** `pyproj.datadir.get_data_dir()`'s own documented precedence order checks an "internal proj directory" (a literal nix-store path baked into the pyproj package at build time, `.../proj-9.8.1/share/proj` -- valid but grid-less) at priority 2, **before** `PROJ_DATA`/`PROJ_LIB` at priority 3. Since that internal directory always exists and always contains a valid (grid-less) `proj.db`, `PROJ_DATA` is never even consulted. Consequently `TransformerGroup('EPSG:3111', 'EPSG:7899')` reports `best_available=True` for `"GDA94 to GDA2020 (1)"` (the real, EPSG-registered 7-parameter conformal transform, accuracy 0.01m -- not a "ballpark" op) and lists the two grid-based variants `"(2)"`/`"(3)"` as **unavailable**, regardless of what `PROJ_DATA` is set to. This directly contradicts the literal wording of 03-01's own stated acceptance criterion ("`TransformerGroup(...)` reports `best_available` true with **no unavailable operations**") when re-run today in this dev shell.
2. **`ogr2ogr` links the identical `libproj.so.25` natively** (confirmed via `ldd`), without pyproj's Python-level override, so PROJ's own documented native precedence (env var before compiled-in default) should apply -- but I could not obtain a decisive trace. `PROJ_DEBUG=2`/`3` produced no stderr output through `ogr2ogr` in this environment, and a round-trip numeric comparison (`3111 -> 7899` with vs without `PROJ_DATA` set) is structurally unable to discriminate between candidate operations, since forward+inverse of *any* single consistent operation cancels to the same result regardless of which real operation was used.

**Disposition:** the blocker stays **open** in `STATE.md` and `WINDOWS.md` (`#2` original + `#3` this refined finding). It is not closed by this run. Whichever plan next processes a genuinely different-source-SRID layer (03-05 or 03-06, per the existing `STATE.md` blocker) must settle it using a verification method that does not go through `pyproj.datadir`'s default resolution (e.g. `pyproj.datadir.set_data_dir()` called explicitly, or a decisive `ogr2ogr`-side trace/ground-truth-coordinate comparison) -- `TransformerGroup`'s default call, as currently documented in `03-RESEARCH.md`, is now known to always misreport the grid as unavailable in this dev shell.

## Issues Encountered

None beyond the three deviations and the grid-question investigation above, both fully documented.

## User Setup Required

None further -- the operator already completed `db/provision_vicmap_loader.sql`'s provisioning (plus the undocumented `CREATE DATABASE` prerequisite, see Deviations) and confirmed all five verification facts pass before this continuation began.

## Next Phase Readiness

- `vicmap_acquire.staging`'s DB-01/DB-02/DB-03 contracts are now live-verified against the real database and the real 4.2M-row delivery, not just fixtures -- 03-05 and 03-06 can build on `StagingPolicy`, the failure hierarchy, `staging_table_name`, and `run_staging`'s signature exactly as declared, with real-world confidence.
- **03-05 and 03-06 must not assume the target database already exists** -- the provisioning gap above is real and unresolved in the script itself.
- **The grid-vs-Helmert question is still open** and must be settled by whichever plan first stages a layer with a genuinely different source SRID, using a verification method that accounts for pyproj's `PROJ_DATA` blindness discovered here.
- `tests/test_staging.py#LoadIntegrationTest` cannot be exercised against the real `vicmap_loader` production role without either violating D-59's privilege boundary or this task's own database-safety confinement; 03-05/03-06 should decide whether its fixture needs a different (more privileged, clearly-labeled test-only) DSN convention, separate from the production role's own `VICMAP_DB_PASSWORD`.

## Self-Check: PASSED

- `vicmap_acquire/staging.py` exists and contains the fixed `_connect`/`build_ogr2ogr_command`: FOUND
- `stage_order.py` exists: FOUND
- `db/provision_vicmap_loader.sql` exists: FOUND
- `vicmap_acquire/evidence.py` contains `_SERVER_VERSION_TEXT = re.compile(r"[ -~]{1,1024}")`: FOUND
- Commit `4cea5f9` (Task 2): FOUND in `git log --oneline --all`
- Commit `b900a2f` (Task 3): FOUND in `git log --oneline --all`
- Commit `616d50a` (fix 1): FOUND in `git log --oneline --all`
- Commit `e53d950` (fix 2): FOUND in `git log --oneline --all`
- Commit `d55544a` (fix 3): FOUND in `git log --oneline --all`
- Full suite: `nix develop -c python -m unittest discover -s tests -t . -p 'test_*.py'` -> `OK (skipped=8)`, 464 tests, no skip among `StagingTableNameTest`/`LoadCommandConstructionTest`/`DatabaseConfigTest`/`DriverImportPolicyTest`
- Live staging tables `vicmap_staging.vmadd_address_20260921t070323z`, `_070443z`, `_071736z` all present with `row_count=4222035`, `ST_SRID(geom)=7899`: FOUND (verified via `psql`)
- `public` schema unchanged (`spatial_ref_sys` only, owner `gisuser`): FOUND

---
*Phase: 03-validated-postgis-staging*
*Completed: 2026-09-21*
