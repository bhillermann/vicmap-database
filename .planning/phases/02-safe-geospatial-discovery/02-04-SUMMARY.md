---
phase: 02-safe-geospatial-discovery
plan: 04
subsystem: geospatial-discovery
tags: [pyogrio, pyproj, ogrinfo, differential-testing, tdd]

# Dependency graph
requires:
  - phase: 02-safe-geospatial-discovery/02-01
    provides: ExtractionPolicy/DiscoveryPolicy and LayerProfile/FieldProfile fixed field-name contracts, plus the three checked-in OpenFileGDB fixtures (Order_TRACER1.zip, geometryless_gdb.zip, point_z_gdb.zip)
provides:
  - Complete dataset enumeration behind a closed extension-to-driver allowlist (D-34), with the driver GDAL itself reports re-checked against the allowlist
  - Full per-layer profiling combining pyogrio.read_info() and one ogrinfo -json subprocess per dataset, landing every D-36/D-38/D-39 hard stop
  - Deterministic (dataset_relative_path, layer_name) discovery ordering with no merging/deduplication of identical profiles
  - An independent ogrinfo-based oracle proving discovery's feature count, field schema, geometry type (after vocabulary normalization), and EPSG agree with GDAL's own answer for all three fixtures
affects: [02-05-naming-hardening, 02-06-manifest-finalization]

# Actuals (#2632)
actuals:
  tokens: 11108
  tasks: 3
  commits: 2

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "find_datasets(run_directory, policy) -> tuple[(Path, driver), ...]: a closed _EXTENSION_DRIVERS MappingProxyType gates format recognition; a recognized-but-unlisted driver is rejected with zero I/O; a recognized-and-allowed candidate is opened once to confirm >=1 layer and to re-check pyogrio's own reported driver against the allowlist"
    - "profile_layer's hard-stop order is schema completeness -> feature count -> geometry type -> CRS, so each check only runs once the work it depends on is already known-good"
    - "Differential-oracle test derives expected values from ogrinfo's own JSON independently (own subprocess call, own parsing, own geometry-vocabulary normalization), never from vicmap_acquire.discovery's output -- enforced by an ast self-check restricting imports to discover_layers/DiscoveryPolicy"

key-files:
  created:
    - tests/test_discovery.py
    - tests/test_discovery_differential.py
  modified:
    - vicmap_acquire/discovery.py

key-decisions:
  - "Combined Task 1 (enumeration) and Task 2 (profiling) into one commit: both rewrite the same find_datasets/read_field_schema/profile_layer/discover_layers call chain in discovery.py, and 02-01 had already left the module substantially complete rather than empty, matching 02-02/02-03's documented precedent for this codebase."
  - "profile_layer now takes the enumeration-confirmed driver as an explicit keyword argument instead of re-deriving and re-validating it from read_info() internally -- find_datasets is now the single place UnsupportedFormat can be raised for a dataset's driver, avoiding duplicated allowlist logic."
  - "read_field_schema raises LayerSchemaIncomplete directly (rather than deferring to profile_layer) for a field missing name/type/nullable or a layer with an empty field list, since it already owns the ogrinfo JSON parsing and is the earliest point those facts are known."
  - "test_discovery_differential.py imports exactly two names from vicmap_acquire.discovery: discover_layers (the entry point under test) and DiscoveryPolicy (a required config container the entry point's signature demands, not parsing/computation logic). The plan's wording names three specific forbidden helpers (read_field_schema, profile_layer, _EXTENSION_DRIVERS) but never forbids the config dataclass; the ast self-check enforces this exact two-name set so the exemption is deliberate and machine-checked, not an oversight."

requirements-completed: []  # GEO-02/GEO-03/GEO-05 are shared with sibling plans 02-05/02-06 still in flight -- requirements.ready-ids reported 0/3 ready; marked complete once every declaring plan has a SUMMARY.

coverage:
  - id: D1
    description: "Every supported dataset and layer in a delivery is discovered and selected automatically; an unsupported format is a named typed failure, never a silent skip"
    requirement: GEO-02
    verification:
      - kind: unit
        ref: "tests/test_discovery.py::FindDatasetsTest (11 cases: real fixture, unsupported .shp, empty/companions-only DeliveryEmpty, zero-layer dataset, driver-lie re-check, injected exception, nested-directory skip)"
        status: pass
    human_judgment: false
  - id: D2
    description: "Every layer carries the exact feature count, full ordered field schema, declared geometry type, and resolved EPSG that GEO-03 promises"
    requirement: GEO-03
    verification:
      - kind: unit
        ref: "tests/test_discovery.py::ProfileLayerTest::test_address_profile_full_fields"
        status: pass
      - kind: unit
        ref: "tests/test_discovery.py::ReadFieldSchemaTest (9 cases: real schema, missing name/type/nullable, absent width/precision, empty field list, subprocess failure/timeout/invalid JSON)"
        status: pass
    human_judgment: false
  - id: D3
    description: "The geometry-less path (spatial=False, all geometry/CRS fields None, CRS resolver never invoked) and the Unknown-geometry hard stop are provably distinct"
    requirement: GEO-05
    verification:
      - kind: unit
        ref: "tests/test_discovery.py::ProfileLayerTest::test_geometryless_profile_never_invokes_crs_resolver"
        status: pass
      - kind: unit
        ref: "tests/test_discovery.py::ProfileLayerTest::test_unknown_geometry_type_raises_geometry_type_unresolved"
        status: pass
    human_judgment: false
  - id: D4
    description: "Zero-feature layers hard-stop, one-feature layers are accepted, and unresolvable CRS hard-stops with no substituted SRID"
    requirement: GEO-05
    verification:
      - kind: unit
        ref: "tests/test_discovery.py::ProfileLayerTest::test_zero_features_raises_layer_empty"
        status: pass
      - kind: unit
        ref: "tests/test_discovery.py::ProfileLayerTest::test_one_feature_returns_a_profile"
        status: pass
      - kind: unit
        ref: "tests/test_discovery.py::ProfileLayerTest::test_unresolvable_crs_raises_and_records_no_substituted_srid"
        status: pass
    human_judgment: false
  - id: D5
    description: "Discovery output is deterministically ordered by (dataset_relative_path, layer_name), and identical profiles from two datasets are never merged or deduplicated"
    verification:
      - kind: unit
        ref: "tests/test_discovery.py::DiscoverLayersTest::test_ordering_and_no_dedup_over_two_dataset_tree"
        status: pass
    human_judgment: false
  - id: D6
    description: "An independently authored ogrinfo oracle agrees with discovery on feature count, ordered field names/types, normalized geometry type, and EPSG for all three fixtures, including the Point-Z vocabulary-normalization case"
    verification:
      - kind: unit
        ref: "tests/test_discovery_differential.py::DiscoveryOracleAgreementTest (3 fixture-agreement tests)"
        status: pass
      - kind: unit
        ref: "tests/test_discovery_differential.py::ImportIndependenceTest::test_only_the_allowed_names_are_imported_from_discovery"
        status: pass
    human_judgment: false

duration: 40min
completed: 2026-09-16
status: complete
---

# Phase 2 Plan 4: Discovery Profiling and Differential Oracle Summary

**Complete dataset enumeration behind a closed format allowlist, full pyogrio+ogrinfo layer profiling landing every D-36/D-38/D-39 hard stop, and an independent ogrinfo oracle proving discovery's answers agree with GDAL's own JSON output across all three fixtures.**

## Performance

- **Duration:** ~40 min
- **Started:** 2026-09-16 (session start)
- **Completed:** 2026-09-16
- **Tasks:** 3 (Task 1 + Task 2 committed together, Task 3 separate)
- **Files modified:** 3 (2 created, 1 modified)

## Accomplishments

- `find_datasets` now walks the run directory against a closed `_EXTENSION_DRIVERS` map (`.gdb`/`.shp`/`.gpkg`/`.tab`/`.dxf`), rejects a recognized-but-unlisted format as `UnsupportedFormat` before ever opening the file, and re-checks the driver `pyogrio.read_info()` itself reports against the allowlist so an extension that lies about its format is still rejected
- `find_datasets` raises `DeliveryEmpty` for a run directory with zero allowlisted datasets or a dataset that opens with zero layers, and never descends into a recognized dataset directory looking for further datasets
- `read_field_schema` requires `name`/`type`/`nullable` on every field (`LayerSchemaIncomplete` otherwise) while treating an absent `width`/`precision` as normal (verified against the real `UFI`/`SOURCE_VERIFIED` fields, which OpenFileGDB never reports either for), and rejects an empty field list
- `profile_layer` now takes the enumeration-confirmed driver as an explicit keyword argument and orders its hard stops schema-completeness → feature-count → geometry-type → CRS, keeping `geometry_type is None` (D-35, non-spatial) and `geometry_type == "Unknown"` (D-38, hard stop) as two distinct checks that can never be conflated; the CRS resolver is proven never invoked for a non-spatial layer
- `discover_layers` returns profiles ordered by `(dataset_relative_path, layer_name)` under plain code-point comparison, computed as an explicit post-hoc sort so driver-reported layer order never leaks through, and two byte-identical profiles from different datasets are proven to remain two distinct entries
- `tests/test_discovery.py` — 28 new regressions: `FindDatasetsTest` (real fixture, unsupported format, empty/companions-only, zero-layer, driver-lie re-check, injected exception, nested-directory skip), `ReadFieldSchemaTest` (real schema plus 8 injected-payload cases), `ProfileLayerTest` (real ADDRESS/geometryless/Point-Z fixtures plus 5 injected-seam branches), `DiscoverLayersTest` (end-to-end plus two-dataset ordering/no-dedup)
- `tests/test_discovery_differential.py` — an independent `ogrinfo -json -al -so` oracle (own subprocess call, own JSON parsing, own geometry-vocabulary normalization) cross-checking feature count, ordered field names/types, normalized geometry type, and EPSG across all three fixtures, with an `ast`-based self-check enforcing that only `discover_layers`/`DiscoveryPolicy` are ever imported from `vicmap_acquire.discovery`

## Task Commits

Task 1 and Task 2 are committed together (see Deviations for why):

1. **Task 1 + Task 2: Complete dataset enumeration and layer profiling** - `7d911bc` (feat)
2. **Task 3: Cross-check discovery against an independently authored ogrinfo oracle** - `803cfec` (test)

**Plan metadata:** (this commit, recorded after SUMMARY.md is written)

## Files Created/Modified

- `vicmap_acquire/discovery.py` - `_EXTENSION_DRIVERS`, rewritten `find_datasets`/`read_field_schema`/`profile_layer`/`discover_layers`
- `tests/test_discovery.py` - GEO-02/GEO-03 regression suite (new)
- `tests/test_discovery_differential.py` - independent `ogrinfo` oracle plus `ast` independence self-check (new)

## Decisions Made

- **Combined commit (process deviation), same precedent as 02-02/02-03.** Task 1 and Task 2 both rewrite the same `find_datasets`/`read_field_schema`/`profile_layer`/`discover_layers` call chain in `discovery.py`, which 02-01 had already left substantially complete. Splitting into an artificial Task-1-only intermediate commit would misrepresent the real incremental history rather than reflect it. Both tasks' `<verify>` commands were run against the final state (28/28 `tests.test_discovery`, plus `tests.test_discovery_tracer` unaffected) and are recorded in this SUMMARY's coverage block.
- **`profile_layer` takes `driver` as an explicit keyword argument.** Rather than re-deriving and re-validating the driver from `read_info()` inside `profile_layer` (as 02-01's version did), `find_datasets` is now the single place `UnsupportedFormat` can be raised for a dataset's driver — no duplicated allowlist-comparison logic between enumeration and profiling.
- **`read_field_schema` owns `LayerSchemaIncomplete` for field-completeness and empty-field-list failures directly**, rather than deferring the empty-list check to `profile_layer` as 02-01's version did — it already owns the `ogrinfo` JSON parsing and is the earliest point those facts are known.
- **`test_discovery_differential.py`'s two-name import exemption.** The plan's wording explicitly forbids `read_field_schema`, `profile_layer`, and `_EXTENSION_DRIVERS` (parsing/computation helpers) but never forbids `DiscoveryPolicy` (a required config dataclass `discover_layers`'s signature demands as an argument, carrying no parsing logic of its own). The `ast` self-check enforces exactly `{discover_layers, DiscoveryPolicy}` as the allowed import set, so this is a deliberate, machine-checked exemption rather than an unenforced comment.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Consistency] Combined Task 1 and Task 2 into one commit**
- **Found during:** Preparing to commit after both tasks' implementation was complete
- **Issue:** Both tasks' actions are described against the same `find_datasets`/`profile_layer` call chain in `discovery.py`; the enumeration rewrite (Task 1) and the profiling rewrite (Task 2) were made in one continuous pass because `find_datasets`'s new `(Path, driver)` return contract is what `profile_layer`'s new `driver=` keyword argument consumes — splitting them cleanly would require reconstructing an artificial intermediate state, exactly the tension 02-02's and 02-03's SUMMARYs already documented for this same codebase.
- **Fix:** Committed both tasks together with a commit message itemizing each task's changes, ran both tasks' `<verify>` commands against the final state, and recorded both results in this SUMMARY's coverage block.
- **Files modified:** none beyond the plan's own files — this was a commit-sequencing decision, not a code change.
- **Verification:** `nix develop path:. -c python -m unittest tests.test_discovery -v` (28 tests, `OK`) and the pre-existing `tests.test_discovery_tracer` (4 tests, `OK`, confirming `discover_order.py`'s unchanged `discover_layers(run_directory, policy)` call site still works end to end).
- **Committed in:** `7d911bc`

---

**Total deviations:** 1 (process/commit-sequencing decision, no code-behavior change)
**Impact on plan:** No scope creep — `vicmap_acquire/extraction.py`, `vicmap_acquire/naming.py`, `vicmap_acquire/manifest.py`, `discover_order.py`, `read_mailbox.py`, and `vicmap.toml` (sibling-plan files) were not touched. `discover_order.py`'s only discovery import (`discover_layers`, `DiscoveryPolicy`, `DiscoveryFailure`) is unaffected by the internal `find_datasets`/`profile_layer` signature changes.

## Issues Encountered

None beyond the deviation documented above.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- `LayerProfile`/`FieldProfile` field names are unchanged from the 02-01 contract — 02-05 (naming hardening) and 02-06 (manifest finalization) can proceed against the same fields as planned.
- `find_datasets`'s public signature changed from `(run_directory) -> tuple[Path, ...]` to `(run_directory, policy) -> tuple[tuple[Path, str], ...]`, and `profile_layer` gained a required `driver` keyword argument. Neither `discover_order.py` nor any sibling-plan module calls either function directly (both import only `discover_layers`/`DiscoveryPolicy`/`DiscoveryFailure`), so this is not a breaking change for 02-05/02-06, but any future direct caller of `find_datasets`/`profile_layer` must use the new signatures.
- GEO-02, GEO-03, and GEO-05 remain unmarked in REQUIREMENTS.md: each is also declared by a sibling plan (02-06 for GEO-02/GEO-03, 02-05 for GEO-05) that has not yet produced a SUMMARY. `requirements.ready-ids` reported 0/3 ready at this plan's completion; they will be marked complete automatically once every declaring plan finishes, per the shared-ID gate (#2388).
- Full suite green: `nix develop path:. -c python -m unittest discover -s tests -p 'test_*.py' -v` reports 303 tests, `OK` (271 baseline + 28 `test_discovery` + 4 `test_discovery_differential`, zero regressions).
- No blockers for 02-05 or 02-06.

---
*Phase: 02-safe-geospatial-discovery*
*Completed: 2026-09-16*

## Self-Check: PASSED

All 3 key files found on disk (`vicmap_acquire/discovery.py`, `tests/test_discovery.py`,
`tests/test_discovery_differential.py`). Both referenced commits (`7d911bc`, `803cfec`)
found in `git log`. Full suite green: 303 tests, `OK` (271 baseline + 32 new).
plan_head_before: da121ba182f6158722f67e4555554e50c30dbf8d
