---
phase: 02-safe-geospatial-discovery
plan: 07
subsystem: geospatial-discovery
tags: [extraction, compression-ratio, calibration, discovery, case-insensitive, live-verification]

# Dependency graph
requires:
  - phase: 02-safe-geospatial-discovery/02-01
    provides: ExtractionPolicy/DiscoveryPolicy field-name contracts, the shared discovery_tracer fixture pattern
  - phase: 02-safe-geospatial-discovery/02-02
    provides: read_mailbox.load_discovery_config, the complete four-section vicmap.toml contract, artifacts/Order_OK0VUZ.provenance.json sidecar
  - phase: 02-safe-geospatial-discovery/02-03
    provides: extract_artifact's per-member compression-ratio guard (the code this plan recalibrates and pins)
  - phase: 02-safe-geospatial-discovery/02-04
    provides: find_datasets' _EXTENSION_DRIVERS map and the pyogrio.read_info driver re-check this plan makes case-insensitive
  - phase: 02-safe-geospatial-discovery/02-06
    provides: discover_order.run_discovery composition, the LiveDeliveryRegressionTest this plan converts to prove the shipped config
provides:
  - vicmap.toml's shipped [extraction].max_compression_ratio recalibrated from 20 to 200, evidence-justified against both the real delivery (139.2432x measured) and the tracer fixture (122.6667x measured)
  - A live regression proving discover_order.run_discovery processes the real 233 MB delivery under the shipped vicmap.toml with zero test-local ceiling overrides anywhere in the call path
  - A deterministic calibration regression deriving each archive's worst-case ratio independently via zipfile and asserting the shipped ceiling strictly exceeds it, so lowering the ceiling or a more-compressible future delivery both fail in CI
  - The ratio comparison's accept-at-equality / reject-one-above boundary pinned by test in both directions
  - Case-insensitive dataset extension recognition in find_datasets (WR-01), closed without widening the recognized extension set or weakening the driver re-check
affects: [02-safe-geospatial-discovery/02-09]

# Actuals (#2632)
actuals:
  tokens: 3410
  tasks: 3
  commits: 3

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "A live/opt-in regression sources its policy ceilings from the repository's own shipped vicmap.toml via read_mailbox.load_discovery_config rather than constructing a hand-built ExtractionPolicy, so the test proves the shipped config works rather than a private copy of it"
    - "A calibration test derives its pass/fail threshold from an independent zipfile walk of the real archive at test time, never from a number copied into the test, so the regression goes red both if the ceiling regresses and if a future delivery's data shape changes"
    - "Case-insensitive extension matching normalizes the probe (path.suffix.casefold()) rather than the lookup table, keeping the recognized-extension set closed and unchanged"

key-files:
  created: []
  modified:
    - vicmap.toml
    - tests/test_manifest.py
    - tests/test_discovery_config.py
    - vicmap_acquire/discovery.py
    - tests/test_discovery.py

key-decisions:
  - "Raised vicmap.toml's max_compression_ratio from 20 to 200 -- the smallest round value clearing both the real delivery's measured worst-case per-member ratio (139.2432x, VMADD.gdb/a00000006.gdbtablx) and the tracer fixture's (122.6667x) with headroom, and the same value both existing test-local overrides had already independently chosen. max_total_bytes and max_member_bytes are unchanged and remain the binding resource bound (enforced per 1 MiB chunk during streaming); the ratio check runs after a member is fully written, so it is an anomaly detector, not a resource guard, and the worst-case bytes any archive can cause to be written is identical before and after this change."
  - "Rejected adding a size-floor exemption to the ratio check (a new [extraction] key) as a design alternative: the config contract is strict and complete (_EXTRACTION_KEYS rejects unknown and missing keys), so a new key would touch read_mailbox.py, vicmap_acquire/extraction.py, discover_order.py, vicmap.toml, and at least four test modules' fixtures for no proportionate benefit over the evidence-justified value change 02-VERIFICATION.md already named as the accepted closure."
  - "LiveDeliveryRegressionTest now sources max_total_bytes/max_member_bytes/max_member_count/max_compression_ratio from read_mailbox.load_discovery_config against the repository's own vicmap.toml instead of hardcoding a test-local max_compression_ratio=200; run_root stays test-local (a temp directory outside the repository working tree) because it is the one field that must never point at the repository's own runs/ directory."
  - "tests/test_discovery_tracer.py's own max_compression_ratio=200 was deliberately left untouched -- every other ceiling in that policy is also fixture-scaled for a synthetic 22-member archive, so it is a fixture-sized policy, not a workaround for the shipped value, and rewriting it would add churn without adding proof."
  - "Case-insensitive extension recognition normalizes path.suffix.casefold() at the lookup call site in find_datasets rather than duplicating _EXTENSION_DRIVERS' keys in both cases, keeping the map's keys exactly {.gdb, .shp, .gpkg, .tab, .dxf} and matching the casefold-based normalization vicmap_acquire/naming.py already applies elsewhere."

requirements-completed: [GEO-05]

coverage:
  - id: D1
    description: "The real Vicmap delivery (artifacts/Order_OK0VUZ.zip) is processed end to end by discover_order.run_discovery under the shipped vicmap.toml, with zero test-local extraction-ceiling overrides anywhere in the call path, publishing a manifest naming target table vmadd_address"
    requirement: GEO-05
    verification:
      - kind: integration
        ref: "tests/test_manifest.py#LiveDeliveryRegressionTest.test_real_delivery_produces_the_pinned_manifest"
        status: pass
      - kind: unit
        ref: "command: python -c \"read_mailbox.load_discovery_config(...).max_compression_ratio >= 200 and other ceilings unchanged\""
        status: pass
    human_judgment: false
  - id: D2
    description: "The shipped max_compression_ratio ceiling is provably above both archives' independently measured worst-case per-member ratio, and lowering it below 200 fails a test"
    requirement: GEO-05
    verification:
      - kind: unit
        ref: "tests/test_discovery_config.py#ShippedCeilingCalibrationTest.test_shipped_ceiling_exceeds_the_tracer_fixtures_worst_case_ratio"
        status: pass
      - kind: unit
        ref: "tests/test_discovery_config.py#ShippedCeilingCalibrationTest.test_shipped_ceiling_exceeds_the_real_deliverys_worst_case_ratio"
        status: pass
    human_judgment: false
  - id: D3
    description: "The compression-ratio comparison's accept/reject boundary is pinned by test in both directions: exactly-at-ceiling accepts, one-step-above rejects"
    requirement: GEO-05
    verification:
      - kind: unit
        ref: "tests/test_discovery_config.py#CompressionRatioThresholdDirectionTest.test_ratio_exactly_at_ceiling_extracts_successfully"
        status: pass
      - kind: unit
        ref: "tests/test_discovery_config.py#CompressionRatioThresholdDirectionTest.test_ratio_one_step_above_ceiling_raises_archive_ceiling_exceeded"
        status: pass
    human_judgment: false
  - id: D4
    description: "A geodatabase directory with an uppercase extension is recognized by find_datasets, and an uppercase unsupported extension is diagnosed by name rather than falling through to the generic empty-delivery failure (WR-01)"
    verification:
      - kind: unit
        ref: "tests/test_discovery.py#FindDatasetsTest.test_uppercase_geodatabase_extension_is_recognized"
        status: pass
      - kind: unit
        ref: "tests/test_discovery.py#FindDatasetsTest.test_uppercase_unsupported_extension_raises_unsupported_format"
        status: pass
      - kind: integration
        ref: "tests/test_discovery_differential.py (ogrinfo oracle agreement, unaffected)"
        status: pass
    human_judgment: false

duration: ~15min
completed: 2026-09-16
status: complete
---

# Phase 2 Plan 7: Shipped Compression Ceiling Recalibration and Case-Insensitive Dataset Recognition Summary

**Raised vicmap.toml's max_compression_ratio from 20 to 200 with a live end-to-end regression against the real 233 MB delivery, pinned the ceiling calibration and threshold direction by test, and made dataset extension recognition case-insensitive (WR-01).**

## Performance

- **Duration:** ~15 min
- **Started:** 2026-09-16
- **Completed:** 2026-09-16
- **Tasks:** 3
- **Files modified:** 5

## Accomplishments
- `vicmap.toml`'s shipped `[extraction].max_compression_ratio` recalibrated from `20` to `200`, the only line changed in the file, evidence-justified against both the real delivery's measured worst-case per-member ratio (139.2432x) and the tracer fixture's (122.6667x)
- `LiveDeliveryRegressionTest` now sources every extraction ceiling from `read_mailbox.load_discovery_config` against the repository's own shipped `vicmap.toml`, proving the shipped policy processes the real delivery rather than a private test copy of it, and still passes end to end (46 members, one layer, `feature_count == 4222035`, target table `vmadd_address`)
- A new calibration test class derives each archive's worst-case ratio independently via a bare `zipfile` walk and asserts the shipped ceiling strictly exceeds it -- confirmed to fail when the ceiling is reverted to `20`
- The ratio comparison's accept-at-equality and reject-one-above boundary is now pinned by test in both directions
- `find_datasets` recognizes dataset extensions in any letter case by normalizing the lookup probe (`path.suffix.casefold()`), closing WR-01, while the recognized extension set and the downstream `pyogrio.read_info` driver re-check are both unchanged

## Task Commits

Each task was committed atomically:

1. **Task 1: One real end-to-end run under the shipped configuration, with no test-local ceiling override** - `8715853` (feat)
2. **Task 2: Pin the calibration and the threshold's direction** - `0312ba3` (test)
3. **Task 3: Recognize dataset extensions in any letter case (WR-01)** - `64226ea` (fix)

**Plan metadata:** commit follows this Summary

## Files Created/Modified
- `vicmap.toml` - `[extraction].max_compression_ratio` recalibrated 20 -> 200; exactly one line changed
- `tests/test_manifest.py` - `LiveDeliveryRegressionTest` sources ceilings from the shipped `vicmap.toml` via `load_discovery_config` instead of a hardcoded override
- `tests/test_discovery_config.py` - new `ShippedCeilingCalibrationTest` and `CompressionRatioThresholdDirectionTest` classes
- `vicmap_acquire/discovery.py` - `find_datasets`'s `_EXTENSION_DRIVERS` lookup now keys on `path.suffix.casefold()`
- `tests/test_discovery.py` - two new `FindDatasetsTest` regressions for uppercase-extension recognition and uppercase unsupported-format diagnosis

## Decisions Made
- Recalibrated the shipped ceiling to `200` rather than adding a size-floor exemption mechanism; see key-decisions above for the full rejected-alternative analysis carried into `vicmap.toml`'s history.
- Kept `tests/test_discovery_tracer.py`'s local `max_compression_ratio=200` untouched -- it is a fixture-scaled policy for a synthetic archive, not a workaround for the shipped value.
- Normalized the extension lookup's probe, not `_EXTENSION_DRIVERS`' table, to keep the recognized-extension set trivially auditable as exactly five lowercase keys.

## Deviations from Plan

None - plan executed exactly as written. Task 1's `type="tracer"` feedback gate was evaluated per the executor's tracer-feedback protocol (auto-chain inactive, `human_verify_mode` at its `end-of-phase` default, Task 1's `<verify>` carries only `<automated>` checks): the tracer `<verify>` was re-run and passed, so execution proceeded directly to Task 2 without a synthesized checkpoint.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- 02-09 depends on this plan and also modifies `tests/test_manifest.py`; that plan's own `write_manifest` rewrite will land on top of this plan's `LiveDeliveryRegressionTest` change with no expected conflict since 02-09 touches a different test class in the same file.
- 02-VERIFICATION.md's gap 3 and WARNING WR-01 are both closed by this plan. WR-02 (unfsynced manifest directory entries) remains open, deliberately deferred to 02-09 per this plan's objective note.
- The full 380-test suite is green after this plan's changes, with no absolute byte ceiling (`max_total_bytes`, `max_member_bytes`) loosened.

---
*Phase: 02-safe-geospatial-discovery*
*Completed: 2026-09-16*

## Self-Check: PASSED

All created/modified files verified present on disk; all three task commits (`8715853`, `0312ba3`, `64226ea`) verified in `git log`. All acceptance criteria re-verified passing, including the negative check (reverting `max_compression_ratio` to `20` makes `ShippedCeilingCalibrationTest` fail). Full suite: `nix develop path:. -c python -m unittest discover -s tests -p 'test_*.py' -v` -> 380 tests, OK.
