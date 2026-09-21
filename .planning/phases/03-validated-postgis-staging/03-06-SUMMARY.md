---
phase: 03-validated-postgis-staging
plan: 06
subsystem: database
tags: [postgis, ddl, gist-index, btree-index, ogr2ogr, proj, gda2020, gda94, staging]

# Dependency graph
requires:
  - phase: 03-validated-postgis-staging (03-04, 03-05)
    provides: "vicmap_acquire/staging.py's StagingPolicy, closed failure hierarchy, load_layer, and the full DB-04 validate_layer body (row count, SRID, geometry type, counted repair, extent)"
provides:
  - "vicmap_acquire/staging.py: apply_post_validation_ddl (D-62/D-63/D-64 primary key, typed non-null geometry column, GiST index, allowlisted btree indexes, one transaction), secondary_index_columns (pure D-64 allowlist decision), diagnostics_path (D-43), LoadFailed.diagnostics_file, run_staging's completed per-layer progress/DDL/failure-attribution orchestration"
  - "stage_order.py: manifest_unreadable failure mapping for a missing run directory, D-48 run-timestamp sourced from the discovery run directory's own name (not now()), staging_table/diagnostics_file surfaced on every StagingFailure"
  - "vicmap_acquire/evidence.py: SafeFailure gains staging_table and diagnostics_file fields (both bounded safe scalars, never a path or driver text)"
  - "tests/test_staging.py: SecondaryIndexAllowlistTest, PostValidationDdlTest (11 live methods), SequentialOrderTest, LoadDiagnosticsTest, ProductionIsolationTest -- all executable with only VICMAP_TEST_POSTGRES_DSN"
affects: [04]

# Actuals (#2632)
actuals:
  tokens: 14839
  tasks: 2
  commits: 2
plan_head_before: 9131971c245f457fd48d19efd8e5c66835b53ca

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Post-validation DDL (primary key, typed geometry, NOT NULL, GiST, secondary btree) runs as one psycopg transaction that commits once at the end and rolls back together on any failure -- never a half-constrained table."
    - "A per-layer try/except in run_staging attaches .staging_table (and LoadFailed additionally .diagnostics_file) onto whichever StagingFailure subclass propagates, so the CLI can surface which layer failed without any exception class needing its own constructor for the purpose."
    - "D-48's run-timestamp suffix is sourced from the discovery run directory's own name, not datetime.now() -- two staging attempts over the same manifest now reuse the same staging table name and the second fails loudly (ogr2ogr rejects an existing layer) rather than silently creating a near-duplicate."

key-files:
  created: []
  modified:
    - vicmap_acquire/staging.py
    - vicmap_acquire/evidence.py
    - stage_order.py
    - tests/test_staging.py

key-decisions:
  - "Task 1 and Task 2 were committed as two separate atomic commits despite both touching staging.py and tests/test_staging.py in the same file: the production-code split (apply_post_validation_ddl/secondary_index_columns vs. diagnostics_path/LoadFailed/run_staging's body) fell on a single clean git hunk boundary; the test-file split was done by temporarily truncating tests/test_staging.py to the Task-1-only state (SecondaryIndexAllowlistTest + PostValidationDdlTest), diffing, committing, then restoring the full file and diffing again for Task 2 -- verified against a copy of the fully-tested final file before and after, so no content was lost in the process."
  - "Research Open Question 1 is answered empirically, live, against the real 4,222,035-row ADDRESS table: GDAL's PostgreSQL driver (FID=gid, known geometry type, known -t_srs) already creates BOTH the primary key on gid AND a fully typed geometry(Point,7899) column -- apply_post_validation_ddl's Steps 1 and 2 both took their no-ALTER branch against this real table, confirmed via \\d and geometry_columns before any DDL ran."
  - "apply_post_validation_ddl's fixed tuple[str, ...] return contract (from this plan's own <interfaces> block) reports only what it actually created, in creation order -- it does not also encode the observed pre-ALTER geometry_columns type as a return value, since that would break the literal interface contract; the observed answer to Open Question 1 is instead recorded here in the SUMMARY and in the function's own docstring, which the plan's acceptance criterion for this point names as the required destination."
  - "The diagnostics file naming convention changed from 03-04's {staging_table}.load.stderr to this plan's own db_load_{staging_table}.stderr, per the <interfaces> block's diagnostics_path contract -- a breaking rename of an internal, git-ignored filename that only the operator's failure line and the run directory ever see."
  - "WINDOWS.md #3 (pyproj's TransformerGroup verification-method blindness) is marked fixed: pyproj.datadir.set_data_dir() called explicitly bypasses the internal-path precedence bug and correctly resolves the vendored PROJ_DATA grid. WINDOWS.md #2 (the grid is not selected as PROJ's best operation) remains open, now confirmed with decisive live evidence rather than a null result -- see 'Grid Question' below and new WINDOWS.md entry #7."

requirements-completed: [DB-03, DB-05]

coverage:
  - id: D1
    description: "Every validated staging table carries a primary key on gid, a typed geometry(Type,SRID) column, NOT NULL on that column, and a GiST index built after validation -- applied as one transaction that rolls back together on any failure"
    requirement: "DB-03"
    verification:
      - kind: unit
        ref: "tests/test_staging.py#PostValidationDdlTest (11 live methods: primary key add/idempotent, bare-column typing, already-typed no-op, NOT NULL, exactly-one GiST index, induced-failure rollback, no CONCURRENTLY)"
        status: pass
      - kind: manual_procedural
        ref: "live run: nix develop -c python stage_order.py against runs/OK0VUZ/20260921T060958Z/ -- psql \\d vicmap_staging.vmadd_address_20260921t060958z shows geometry(Point,7899) not null, gid PRIMARY KEY, one GiST index, one pfi btree index, over the real 4,222,035-row table"
        status: pass
    human_judgment: false
  - id: D2
    description: "A btree secondary index is created for every manifest-declared field that launders onto the configured index_columns allowlist, and for no other column; a layer declaring none gets nothing and nothing fails"
    requirement: "DB-03"
    verification:
      - kind: unit
        ref: "tests/test_staging.py#SecondaryIndexAllowlistTest (5 pure methods, never skips) and PostValidationDdlTest.test_allowlisted_column_gets_a_btree_index_and_undeclared_does_not / test_no_allowlisted_column_declared_creates_no_secondary_index"
        status: pass
    human_judgment: false
  - id: D3
    description: "Layers load one at a time in manifest order; a failure at any step stops the run at a named layer (staging_table attached to the propagating exception) with no later layer attempted; a zero-layer manifest is a no-op"
    requirement: "DB-03"
    verification:
      - kind: unit
        ref: "tests/test_staging.py#SequentialOrderTest (4 methods: 3-layer manifest order+progress, LoadFailed on layer 2 stops after 2 load calls, 1-layer, 0-layer)"
        status: pass
      - kind: manual_procedural
        ref: "live run: stage_order.py against a corrupted-feature_count manifest copy -- failure event carries staging_table:\"vmadd_address_20260921t060959z\", exit 1"
        status: pass
    human_judgment: false
  - id: D4
    description: "A failed load's complete stderr reaches a named local file inside the run directory and nothing of it reaches operator-facing output; the exception and rendered failure event carry only the closed reason code and the file's bare name"
    requirement: "DB-03"
    verification:
      - kind: unit
        ref: "tests/test_staging.py#LoadDiagnosticsTest.test_failed_load_writes_diagnostics_file_and_leaks_nothing (credential-shaped token in stderr reaches neither the exception message nor the rendered event)"
        status: pass
    human_judgment: false
  - id: D5
    description: "An induced load failure and an induced validation failure both leave every table outside vicmap_staging (and their row counts in public/the publish schema) provably unchanged"
    requirement: "DB-05"
    verification:
      - kind: unit
        ref: "tests/test_staging.py#ProductionIsolationTest (2 live methods: induced RowCountMismatch, induced LoadFailed -- both against the real database)"
        status: pass
      - kind: manual_procedural
        ref: "live run: stage_order.py against a corrupted-feature_count manifest -- psql \\dt public.* and spatial_ref_sys row count (8500) identical before/after; vicmap_staging's leftover table from the induced failure had no PK/GiST/pfi index (proving the DDL step never ran on it), then manually dropped as this session's own test artifact"
        status: pass
    human_judgment: false
  - id: D6
    description: "The GiST and allowlisted btree indexes are actually used by the query planner over the real 4.2M-row table, not merely present"
    verification:
      - kind: manual_procedural
        ref: "live EXPLAIN ANALYZE: a bounding-box query used Bitmap Index Scan on vmadd_address_20260921t060958z_geom_gist (0.7ms); a pfi equality query used Bitmap Index Scan on vmadd_address_20260921t060958z_pfi_idx (0.08ms); index sizes 167MB (GiST) and 127MB (btree) over 4,222,035 rows"
        status: pass
    human_judgment: false
  - id: D7
    description: "Research Open Question 1 (does GDAL's PostgreSQL driver create a typed geometry column and primary key itself) has a recorded empirical answer"
    verification:
      - kind: manual_procedural
        ref: "live: \\d vicmap_staging.vmadd_address_20260921t060958z before any DDL ran already showed geometry(Point,7899) and a gid PRIMARY KEY -- both apply_post_validation_ddl's PK and typed-column steps took their no-op branch"
        status: pass
    human_judgment: false
  - id: D8
    description: "The GDA94/GDA2020 grid-vs-Helmert question (WINDOWS.md #2/#3) is settled with decisive live evidence, not a null result"
    verification:
      - kind: manual_procedural
        ref: "pyproj.datadir.set_data_dir() (bypasses the internal-path bug) + a real ogr2ogr -ct_opt ONLY_BEST=YES ALLOW_BALLPARK=NO transform of a genuine ADDRESS point -- ogr2ogr's output matches pyproj's Helmert-operation result to 4 decimal places and differs from the grid-operation result by ~2mm; see 'Grid Question' section below"
        status: pass
    human_judgment: true
    rationale: "The numeric match is objective, but the practical significance (whether the confirmed Helmert selection over the ICSM grid meaningfully degrades address geometry accuracy across Victoria, beyond the ~2mm seen at this one point) is a spatial-data-quality judgment a human should weigh before deciding whether to force grid selection in a future plan."

duration: ~45min
completed: 2026-09-21
status: complete
---

# Phase 3 Plan 6: Post-Validation DDL, Sequential Orchestration, and a Decisive Grid Finding Summary

**Every validated staging table now carries a primary key, a typed non-null geometry column, a GiST index built after validation, and any allowlisted btree index -- applied as one transaction, live-verified over the real 4,222,035-row ADDRESS table with `EXPLAIN` proving both indexes are actually used -- and the long-open GDA94/GDA2020 grid-vs-Helmert question is settled with decisive evidence: `ogr2ogr`'s own `ONLY_BEST=YES` transform matches a grid-free Helmert computation to four decimal places, not the vendored ICSM grid.**

## Performance

- **Duration:** ~45 min
- **Started:** ~2026-09-21T08:27:00Z
- **Completed:** 2026-09-21T09:11:00Z
- **Tasks:** 2 (both `type="auto"`)
- **Files modified:** 4

## Accomplishments

- `apply_post_validation_ddl` (D-62/D-63/D-64): primary key on `gid` (skipping if GDAL's own `FID=gid` load already created one), a typed `geometry(Type,SRID)` column (conditional on `geometry_columns`, never assumed), `NOT NULL`, a GiST index built once after validation, and allowlisted btree secondary indexes -- all inside one transaction that rolls back together on any failure.
- `secondary_index_columns`: the pure D-64 allowlist decision, comparing casefolded manifest field names against `policy.index_columns`.
- `run_staging` completed: per-layer progress emitted before each `ogr2ogr` call, the post-validation DDL step running after validation (never before), and a per-layer `try/except` that attaches `.staging_table` (and, for `LoadFailed`, `.diagnostics_file`) onto whichever typed exception propagates, so the CLI can name the failing layer without carrying any driver text.
- `diagnostics_path`/`load_layer` (D-43): the complete unredacted `ogr2ogr` stderr always lands in a named local file (`db_load_{staging_table}.stderr`) inside the run directory; `LoadFailed` and the rendered `SafeFailure` carry only the file's bare name, never its content or directory.
- `stage_order.py`: a missing run directory now raises the closed `manifest_unreadable` failure (was `config_invalid`); D-48's run-timestamp suffix now comes from the discovery run directory's own name, not `datetime.now()`, so two staging attempts over one manifest collide loudly instead of silently duplicating.
- `vicmap_acquire/evidence.py`'s `SafeFailure` gained `staging_table` and `diagnostics_file` fields (both bounded safe scalars) -- the "no existing field carries a plain path" gap this plan's own action text flagged.
- Live-verified against the real PostgreSQL 17.5/PostGIS 3.5.2 server and the real 4,222,035-row `VMADD.gdb` ADDRESS delivery: a full successful `stage_order.py` run, an induced `RowCountMismatch` failure naming the failing layer with production provably untouched, `EXPLAIN ANALYZE` proving both new indexes are used by the planner, and a decisive resolution of the grid-vs-Helmert question that had been open since 03-01.

## Live-Database Test Execution

Precise counts, not just pass/fail:

**Without `VICMAP_TEST_POSTGRES_DSN`:**
```
nix develop -c python -m unittest discover -s tests -t . -p 'test_*.py'
-> Ran 507 tests, OK (skipped=32)
```

**With `VICMAP_TEST_POSTGRES_DSN` set to the real `vicmap_loader`/`vicmap` connection:**
```
-> Ran 507 tests, OK (skipped=5)
```

- **13 new live-database test methods actually EXECUTED** this session (not skipped, not errored): `PostValidationDdlTest` (11) and `ProductionIsolationTest` (2). All 13 passed.
- **5 still skip cleanly**: `PrivilegePreflightTest` (unchanged from 03-05, WINDOWS.md #6 -- needs `VICMAP_TEST_POSTGRES_SUPERUSER_DSN`, still unavailable; not this plan's or 03-05's to fix).
- 484 tests before this plan (03-05's own baseline) -> 507 now: 23 new tests added (5 `SecondaryIndexAllowlistTest`, 11 `PostValidationDdlTest`, 4 `SequentialOrderTest`, 1 `LoadDiagnosticsTest`, 2 `ProductionIsolationTest`). None of the 23 ever skip when a server is unreachable except the 13 genuinely live-database ones, which skip cleanly (not fail) and are proven above to actually execute against the real server.
- `db/provision_vicmap_loader.sql` was **not** touched and `vicmap_loader` was **not** granted any additional privilege.

## Live Verification -- `stage_order.py` Against the Real Delivery

```
nix develop path:. -c python stage_order.py
```
against `runs/OK0VUZ/20260921T060958Z/` (the real, digest-verified manifest -- `run_timestamp` is now sourced from this directory's own name, per this plan's D-48 change):

```json
{"event":"staging_table_loaded","order_id":"OK0VUZ","row_count":4222035,
 "staging_table":"vmadd_address_20260921t060958z","target_table":"vmadd_address"}
{"event":"staging_layer_validated","extent":[2126780.1966999993,2259755.3506000005,
 2934322.982000001,2826389.7540000007],"geometry_type":"POINT","order_id":"OK0VUZ",
 "repaired_count":0,"row_count":4222035,"spatial":true,"srid":7899,
 "staging_table":"vmadd_address_20260921t060958z"}
```
Exit code 0. Row count 4,222,035 (exact match to the manifest's declared `feature_count`). Ran in 53.9s.

**`psql \d vicmap_staging.vmadd_address_20260921t060958z`** afterward:
```
 geom | geometry(Point,7899) | not null
Indexes:
    "vmadd_address_20260921t060958z_pkey" PRIMARY KEY, btree (gid)
    "vmadd_address_20260921t060958z_geom_gist" gist (geom)
    "vmadd_address_20260921t060958z_pfi_idx" btree (pfi)
```
Every D-62/D-63/D-64 element present over the real 4.2M-row table.

**`EXPLAIN ANALYZE`** (per `<database_safety>`'s "measure, do not assert" instruction):
```sql
EXPLAIN ANALYZE SELECT gid FROM vicmap_staging.vmadd_address_20260921t060958z
  WHERE geom && ST_MakeEnvelope(2500000,2500000,2510000,2510000,7899);
-- Bitmap Index Scan on vmadd_address_20260921t060958z_geom_gist
--   (actual time=0.090..0.100 rows=280 loops=1); Execution Time: 0.739 ms

EXPLAIN ANALYZE SELECT gid FROM vicmap_staging.vmadd_address_20260921t060958z
  WHERE pfi = '12345678';
-- Bitmap Index Scan on vmadd_address_20260921t060958z_pfi_idx
--   (actual time=0.062..0.063 rows=0 loops=1); Execution Time: 0.077 ms
```
Both new indexes are genuinely used by the planner, not merely present. Index sizes: GiST 167 MB, `pfi` btree 127 MB, over 4,222,035 rows.

**`\dt public.*` and `\dt vicmap_staging.*`**, before and after: `public` holds only `spatial_ref_sys` (8,500 rows, unchanged, owner `gisuser`). `vicmap_staging` gained exactly one new table (`vmadd_address_20260921t060958z`), alongside the four pre-existing tables from 03-04/03-05 (`_070323z`, `_070443z`, `_071736z`, `_081946z`) -- none dropped or modified.

## Induced Failure -- Named Layer, Production Untouched

Rather than the plan's illustrative `target_srid` change (which, on inspection, would not reliably reproduce a `SridMismatch` through the real pipeline -- `ogr2ogr -t_srs` always tags the output column with the configured `target_srid` regardless of the source, so load and validate stay self-consistent by construction), this session used a corrupted `feature_count` in a duplicate copy of the real digest-verified manifest (`runs/OK0VUZ/20260921T060959Z/`, cleaned up afterward) -- a real, reachable D-56 blocking check, exercised against the real 4.2M-row delivery rather than a synthetic fixture:

```
nix develop path:. -c python stage_order.py
-> {"event":"failure","hint":"recheck_source_layer_against_manifest_feature_count",
    "order_id":"OK0VUZ","reason":"db_row_count_mismatch","stage":"db_validation",
    "staging_table":"vmadd_address_20260921t060959z"}
Exit code: 1
```

- The failing layer is named via the new `staging_table` field -- this plan's own D-43 attribution feature, exercised live for the first time.
- `\dt public.*` and `spatial_ref_sys`'s row count (8,500) were identical before and after.
- The load itself succeeded (real 4,222,035 rows landed in `vicmap_staging`); only validation blocked it. `\d` on the leftover table showed no GiST index, no `pfi` index, and `geom` still nullable -- proof the post-validation DDL step never ran, exactly as D-62/D-63 require (DDL only after validation passes).
- No password, connection string, or raw `ogr2ogr` stderr appeared anywhere in the operator output at any point.
- The leftover staging table and duplicate run directory were both artifacts of this manual test (not of the pipeline's own code), so both were removed afterward: `DROP TABLE vicmap_staging.vmadd_address_20260921t060959z` (explicit, single, qualified name) and `rm -rf runs/OK0VUZ/20260921T060959Z`. `vicmap_staging` now holds five real tables total (the four from 03-04/03-05 plus this plan's own `vmadd_address_20260921t060958z`); none were dropped.

## Grid Question -- Settled, Not Left Open

WINDOWS.md #2/#3 (carried from 03-01/03-04) asked whether the vendored ICSM GDA94/GDA2020 grid actually gets selected as PROJ's "best" operation under `ONLY_BEST=YES`/`ALLOW_BALLPARK=NO`, or whether a grid-free Helmert transform wins. Every prior attempt (03-01's `TransformerGroup` default call, 03-04's `PROJ_DEBUG` trace) was inconclusive: `pyproj.datadir.get_data_dir()`'s internal build-time path is checked *before* `PROJ_DATA`, so the default `TransformerGroup` call always misreports the grid as unavailable, and `PROJ_DEBUG` produced no usable trace through `ogr2ogr` in this environment.

This session used the alternative method WINDOWS.md #3 itself named as unexplored: `pyproj.datadir.set_data_dir()`, called explicitly, bypasses that internal-path precedence bug entirely.

```python
from pyproj import datadir
datadir.set_data_dir('/nix/store/.../proj-data-with-icsm-grid')  # the real PROJ_DATA
from pyproj.transformer import TransformerGroup
tg = TransformerGroup('EPSG:7899', 'EPSG:3111')
# best_available: True, 2 available, 1 unavailable (a second, non-vendored grid file)
```
With the grid genuinely resolvable, `pyproj` reports three real candidate operations by their actual PROJ pipeline:
1. **`+proj=helmert +x=0.06155 ...`** (grid-free 7-parameter transform) -- declared accuracy **0.01 m**, ranked best.
2. **`+proj=hgridshift +grids=au_icsm_GDA94_GDA2020_conformal_and_distortion.tif`** (the vendored ICSM grid) -- declared accuracy **0.05 m**.
3. A third, non-vendored grid file -- unavailable, declared accuracy 0.05 m.

To confirm `ogr2ogr` -- which links `libproj` natively, with no Python-level override -- makes the same choice, this session transformed one real `VMADD.gdb` ADDRESS coordinate (`X=2537307.0758, Y=2401846.5231`, `EPSG:7899`) through the exact flags `build_ogr2ogr_command` emits:

```
ogr2ogr ... -s_srs EPSG:7899 -t_srs EPSG:3111 -ct_opt ONLY_BEST=YES -ct_opt ALLOW_BALLPARK=NO
-> X=2537306.55479674, Y=2401845.06807695
```

This matches `pyproj`'s Helmert-operation result (`2537306.5548, 2401845.0681`) to **four decimal places**, and differs from the grid-operation result (`2537306.5530, 2401845.0684`) by **~2 mm** at this point -- decisively confirming `ogr2ogr` selects the grid-free Helmert transform, not the vendored ICSM grid, exactly matching what `pyproj` reports once its own resolution bug is bypassed.

**Root cause:** PROJ's own accuracy metadata ranks the generic Helmert transform (0.01 m claimed) above the actual measured ICSM distortion grid (0.05 m claimed) for this CRS pair. `ONLY_BEST` picks by *declared* accuracy, not real-world fidelity -- this happens regardless of whether `PROJ_DATA` resolves correctly, so 03-04's original hypothesis (that fixing the resolution bug would fix the selection) does not hold.

**Practical impact for this specific point: ~2 mm** -- much smaller than 03-01's research-flagged 0.5-1.5 m shift, though this is one point in Melbourne's CBD-adjacent area; distortion magnitude varies across Victoria and this session did not survey it. The question of whether this warrants forcing grid selection in a future plan (an explicit `-ct` pipeline override, or a stricter operation filter) is left as a judgment call -- recorded as `human_judgment: true` in this SUMMARY's coverage block.

**Disposition:** WINDOWS.md #3 (verification-method blindness) marked **fixed** -- a working method now exists and was used. WINDOWS.md #2 (grid not selected) remains **open**, now with decisive evidence rather than a null result; a new entry (#7) records the full finding. Neither `staging.py` nor `vicmap.toml` was changed to force grid selection -- that is out of this plan's scope and would be an architectural decision (Rule 4) for whichever future plan addresses it.

## Task Commits

Each task was committed atomically:

1. **Task 1: Constrain and index every validated staging table** - `01b2155` (feat)
2. **Task 2: Run the order's layers in manifest order with named diagnostics, and prove production is untouched** - `6d8c113` (feat)

**Plan metadata:** (this commit, following this SUMMARY)

## Files Created/Modified

- `vicmap_acquire/staging.py` - `apply_post_validation_ddl`, `secondary_index_columns`, `diagnostics_path`, `LoadFailed.diagnostics_file`, `run_staging`'s completed per-layer body.
- `vicmap_acquire/evidence.py` - `SafeFailure.staging_table`, `SafeFailure.diagnostics_file`, `_require_diagnostics_filename`.
- `stage_order.py` - `manifest_unreadable` on a missing run directory, `run_timestamp` sourced from the discovery run directory's name, `staging_table`/`diagnostics_file` surfaced on every `StagingFailure`.
- `tests/test_staging.py` - `SecondaryIndexAllowlistTest`, `PostValidationDdlTest`, `SequentialOrderTest`, `LoadDiagnosticsTest`, `ProductionIsolationTest`.

## Decisions Made

See `key-decisions` in frontmatter -- the Task 1/Task 2 commit-splitting method, Open Question 1's empirical answer, the `apply_post_validation_ddl` return-contract vs. SUMMARY-recording tradeoff, the diagnostics filename rename, and the WINDOWS.md #2/#3 disposition.

## Deviations from Plan

### Auto-fixed Issues

None - the plan's own DDL, orchestration, and CLI design worked as specified once implemented; no bug fixes were required this session.

### Adjustments within plan scope

**1. [Human-check step 5 re-scoped] Induced failure via corrupted `feature_count`, not `target_srid`**
- **Found during:** Task 2's live `<human-check>`, step 5
- **Issue:** The plan's illustrative example (temporarily changing `[database].target_srid`) would not reliably induce a `SridMismatch` through the real pipeline: `ogr2ogr -t_srs` tags its output geometry column with the *configured* `target_srid` regardless of source, so `build_ogr2ogr_command` (load) and `validate_layer` (check) stay self-consistent by construction whenever the transform itself succeeds.
- **Fix:** Used a corrupted `feature_count` in a duplicate copy of the real manifest instead -- a genuinely reachable D-56 blocking check (`RowCountMismatch`), exercised against the real 4.2M-row delivery.
- **Files modified:** None (test artifact only: a duplicate `runs/OK0VUZ/` directory, removed afterward).
- **Verification:** See "Induced Failure" section above -- exit 1, failing layer named, production untouched.
- **Commit:** N/A (no code change; a live verification method choice).

---

**Total deviations:** 0 auto-fixed. **Impact:** None -- the one adjustment was a live-verification methodology choice within this task's own `<human-check>` scope, not a code change.

## Issues Encountered

None beyond the human-check re-scoping above, fully documented.

## User Setup Required

None. `VICMAP_DB_PASSWORD` and the provisioned database were already available from prior plans.

## Next Phase Readiness

- Every validated staging table Phase 4 will promote now carries the complete D-62/D-63/D-64 contract (primary key, typed non-null geometry, GiST index, allowlisted btree indexes), live-verified over the real 4.2M-row delivery with `EXPLAIN` proving the indexes are used.
- `run_staging`'s sequential, named-failure orchestration and D-43's diagnostics-file contract are complete and live-verified, including the D-48 run-timestamp-from-discovery-directory change (two staging attempts over one manifest now collide loudly rather than silently duplicating).
- DB-03 and DB-05 are marked complete in REQUIREMENTS.md.
- The GDA94/GDA2020 grid-vs-Helmert question (WINDOWS.md #2) is no longer a research gap -- it is a confirmed, evidenced, unremediated behavior. Whichever future plan next needs grid-accurate cross-datum coordinates must explicitly force grid selection (an architectural decision, not an auto-fix); the evidence and root cause are recorded in WINDOWS.md #7 and above.
- This is the last plan of Phase 3. `vicmap_staging` holds five real staging tables from this phase's live verification work (03-04's three, 03-05's one, this plan's one); none were dropped, per PROHIB-10/D-65.
- WINDOWS.md open count: 5 (#1 mailbox placeholder, #2 grid selection, #4 provisioning script gap, #6 superuser test DSN, #7 grid finding detail). #3 and #5 are fixed.

## Self-Check: PASSED

- `vicmap_acquire/staging.py` contains `apply_post_validation_ddl`, `secondary_index_columns`, `diagnostics_path`, and `LoadFailed.diagnostics_file`: FOUND
- `vicmap_acquire/evidence.py` contains `SafeFailure`'s `staging_table`/`diagnostics_file` params and `_require_diagnostics_filename`: FOUND
- `stage_order.py` imports `ManifestUnreadable` and sources `run_timestamp` from `run_directory.name`: FOUND
- `tests/test_staging.py` contains `SecondaryIndexAllowlistTest`, `PostValidationDdlTest`, `SequentialOrderTest`, `LoadDiagnosticsTest`, `ProductionIsolationTest`: FOUND
- Commit `01b2155` (Task 1): FOUND in `git log --oneline --all`
- Commit `6d8c113` (Task 2): FOUND in `git log --oneline --all`
- Full suite with `VICMAP_TEST_POSTGRES_DSN` set: `507 tests, OK (skipped=5)` -- verified this session
- Full suite without any live DSN: `507 tests, OK (skipped=32)` -- confirms every new class skips cleanly, never fails, absent a server
- Live staging table `vmadd_address_20260921t060958z` present with `row_count=4222035`, PK, GiST index, `pfi` index, `geom` typed NOT NULL: FOUND (verified via `psql` and `stage_order.py`'s own event output)
- `public` schema unchanged (`spatial_ref_sys`, 8,500 rows) before and after both the successful run and the induced failure: FOUND
- WINDOWS.md #3 marked `fixed`; #7 added `open` recording the decisive grid finding: FOUND

---
*Phase: 03-validated-postgis-staging*
*Completed: 2026-09-21*
