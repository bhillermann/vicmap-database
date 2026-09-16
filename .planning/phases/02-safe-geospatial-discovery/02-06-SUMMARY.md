---
phase: 02-safe-geospatial-discovery
plan: 06
subsystem: geospatial-discovery
tags: [manifest, provenance, zipfile, pyogrio, live-verification, tdd]

# Dependency graph
requires:
  - phase: 02-safe-geospatial-discovery/02-01
    provides: ImportManifest/ManifestLayer/CompanionFile field names, discover_order.run_discovery's composition seam, ExtractionPolicy/DiscoveryPolicy field-name contracts
  - phase: 02-safe-geospatial-discovery/02-02
    provides: DiscoveryRunConfig, load_discovery_config, artifacts/Order_{id}.provenance.json sidecar, discover_order.main()'s config/provenance wiring
  - phase: 02-safe-geospatial-discovery/02-03
    provides: Hardened extract_artifact (D-26 guard chain, real-byte ceilings, atomic publication, full member accounting)
  - phase: 02-safe-geospatial-discovery/02-04
    provides: Complete find_datasets/profile_layer/discover_layers (D-33/D-36/D-38/D-39 hard stops), the independent ogrinfo oracle pattern
  - phase: 02-safe-geospatial-discovery/02-05
    provides: normalize_target_table_name/assign_target_table_names (D-21..D-24 complete)
provides:
  - Frozen ImportManifest contract with canonical manifest.json + sidecar digest persistence, provenance nested under its own payload key
  - Ordered discover_order.run_discovery composition proving every GEO-05 hard stop leaves no manifest.json/sidecar anywhere under the run root
  - Redacted, guarded (_EmitOnce-routed) operator evidence stream with no-socket/no-database-driver runtime proof
  - Opt-in live regression against the real Order_OK0VUZ.zip pinning the exact verified manifest values, including the corrected 61-field count
affects: []

# Actuals (#2632)
actuals:
  tokens: 13130
  tasks: 3
  commits: 3

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Provenance nested under a single payload-level 'provenance' key, distinct from the flat frozen-dataclass fields Phase 3 consumes in-process"
    - "manifest.json + sidecar written with O_CREAT|O_EXCL, fsynced, never overwritten -- a second run into the same run directory raises ManifestWriteFailed instead of silently replacing the first manifest"
    - "run_discovery routes every event through the reused read_mailbox._EmitOnce guard so a faulty sink can never turn a closed failure into a raw exception and is never retried"
    - "Opt-in live regression (skipUnless artifact+sidecar present) drives the complete run_discovery path against the real delivery and pins exact values as a pyogrio/GDAL-upgrade regression, verified against independent zipfile/ogrinfo/pyogrio oracles rather than the implementation's own output"

key-files:
  created: []
  modified:
    - vicmap_acquire/manifest.py
    - discover_order.py
    - tests/test_manifest.py

key-decisions:
  - "D-21 confirmed locked at the Wave 1 operator checkpoint (02-01): published target table name is {gdb_stem}_{layer} normalized; the real delivery's VMADD.gdb/ADDRESS publishes as vicmap.vmadd_address, proven end to end by this plan's live regression."
  - "Task 3's field-count assertion was corrected from 02-RESEARCH.md's stated 40 to the value independently verified this session (61) against the real VMADD.gdb/ADDRESS layer via ogrinfo -json -al -so -- the research figure was stale/wrong, and the live test's whole purpose is to pin the actual, current truth, not a prior session's possibly-mistaken number."
  - "Task 3's live test uses a test-local max_compression_ratio=200, not vicmap.toml's production default of 20 -- the real delivery's tiny .gdbtablx/.atx OpenFileGDB index members compress up to ~139x, the same shape 02-01's tracer fixture hit (raised there to 200 for the same reason). Flagging this: vicmap.toml's shipped default of 20 would hard-stop a real production run of this exact delivery; that config value is owned by 02-02 and out of this plan's files_modified scope, so it was not changed here -- see Deviations and Next Phase Readiness."

requirements-completed: [GEO-02, GEO-03, GEO-04, GEO-05]

coverage:
  - id: D1
    description: "manifest.json has a settled, versioned, byte-stable shape with provenance nested under its own key, spatial/non-spatial layers both represented, and field order preserved exactly as the driver declared it"
    requirement: GEO-02
    verification:
      - kind: unit
        ref: "tests/test_manifest.py::ManifestRoundTripTest (9 cases: payload shape, provenance nesting, field-order preservation, non-spatial nulls, byte-stability, sidecar digest, existing-manifest guard, OSError translation, fingerprint pass-through)"
        status: pass
    human_judgment: false
  - id: D2
    description: "Every GEO-05 hard stop (checksum mismatch, every archive guard, unsupported format, empty delivery, unreadable/empty layer, unresolved geometry/CRS, incomplete schema, invalid name, collision) leaves no manifest.json and no sidecar anywhere under the run root"
    requirement: GEO-05
    verification:
      - kind: unit
        ref: "tests/test_manifest.py::GeoO5HardStopTest (11 named hard-stop cases, each asserting exit, one SafeFailure, and an empty recursive glob for manifest.json/manifest.json.sha256)"
        status: pass
    human_judgment: false
  - id: D3
    description: "Stage ordering is real (instrumented call recording), a faulty event sink is isolated by the reused _EmitOnce guard, operator output is redacted, and the run opens no socket and imports no database driver"
    requirement: GEO-05
    verification:
      - kind: unit
        ref: "tests/test_manifest.py::StageOrderingTest::test_extraction_never_attempted_before_verify_artifact_returns"
        status: pass
      - kind: unit
        ref: "tests/test_manifest.py::FaultySinkTest::test_sink_that_raises_on_first_call_produces_exactly_one_attempt"
        status: pass
      - kind: unit
        ref: "tests/test_manifest.py::RedactionTest::test_successful_run_output_is_redacted"
        status: pass
      - kind: unit
        ref: "tests/test_manifest.py::NoSocketNoDatabaseTest (2 cases: socket.socket patched to raise; no db driver module in sys.modules)"
        status: pass
    human_judgment: false
  - id: D4
    description: "Every discovered layer flows automatically into the manifest with no filter, prompt, or allowlist between discovery and naming"
    requirement: GEO-04
    verification:
      - kind: unit
        ref: "tests/test_manifest.py::AutomaticSelectionTest::test_two_layer_delivery_produces_two_layer_manifest_with_no_filtering"
        status: pass
    human_judgment: false
  - id: D5
    description: "The complete path is proven against the real 233 MB Vicmap delivery: 46 archive members accounted for, 2 companions, exactly one ADDRESS layer (feature_count 4222035, EPSG 7899, Point, target vmadd_address), PFI width 10, EZI_ADDRESS width 80, UFI width None, the driver's own unrounded extent, manifest.json + sidecar present and digest-matched, and the real artifact's SHA-256 unchanged before/after"
    requirement: GEO-02
    verification:
      - kind: unit
        ref: "tests/test_manifest.py::LiveDeliveryRegressionTest::test_real_delivery_produces_the_pinned_manifest (opt-in, ran this session: 46 members, feature_count 4222035, EPSG 7899, target vmadd_address, 61 fields, extent matched pyogrio.read_info() exactly, elapsed ~4s)"
        status: pass
    human_judgment: false

duration: ~20min (Task 3 only; Tasks 1/2 completed by a prior executor across an earlier session -- see continuation note below)
completed: 2026-09-16
status: complete
---

# Phase 2 Plan 6: Manifest Finalization and Live Delivery Proof Summary

**Settled the frozen `ImportManifest` contract with canonical `manifest.json`+sidecar persistence, composed `discover_order.run_discovery`'s ordered pipeline proving every GEO-05 hard stop lands before any manifest exists, and pinned an opt-in live regression against the real 233 MB Vicmap delivery -- confirming `VMADD.gdb`/`ADDRESS` publishes as `vicmap.vmadd_address` with feature_count 4222035, EPSG 7899, and 61 real attribute fields.**

## Performance

- **Duration:** Task 1 + Task 2 completed by a prior executor in an earlier session; this continuation session covered Task 3 only (~20 min: reading required context, writing the live regression, diagnosing and fixing two real-delivery-specific test-construction issues, running the full suite, committing)
- **Started:** 2026-09-16 (Task 3 continuation)
- **Completed:** 2026-09-16T10:48:55Z
- **Tasks:** 3 (all complete)
- **Files modified:** 3 across the whole plan (`vicmap_acquire/manifest.py`, `discover_order.py`, `tests/test_manifest.py`)

## Accomplishments

- `vicmap_acquire/manifest.py` -- `manifest_payload` nests every run-identity field under a single `provenance` object; `write_manifest` creates `manifest.json` + `manifest.json.sha256` exclusively (`O_CREAT|O_EXCL`), fsynced before close, never overwriting an existing manifest; two calls over identical inputs produce byte-identical bytes
- `discover_order.py` -- `run_discovery` composes verify -> extract -> discover -> name -> build -> write -> render as one ordered pipeline, routing every event through the reused `read_mailbox._EmitOnce` guard so a faulty sink can never turn a closed failure into a raw exception; a failed sink converts an otherwise-successful run to `RunDiscoveryReportingFailed` (exit 1) without touching the already-written manifest
- `tests/test_manifest.py::GeoO5HardStopTest` -- all eleven GEO-05 hard-stop conditions proven to leave no `manifest.json`/sidecar anywhere under the run root, asserted by a recursive glob rather than one expected path
- `tests/test_manifest.py::StageOrderingTest`/`NoSocketNoDatabaseTest` -- instrumented call-order proof (never a timing assumption) and runtime proof (not just inspection) that a successful run opens no socket and imports no database driver
- `tests/test_manifest.py::LiveDeliveryRegressionTest` (Task 3, this session) -- opt-in regression (`skipUnless` both `artifacts/Order_OK0VUZ.zip` and its provenance sidecar are present) driving the complete `run_discovery` path against the real 233 MB delivery into a temp run root outside the repository, pinning: 46 archive members (independent `zipfile` oracle), 2 companions, one `ADDRESS` layer with `feature_count == 4222035`, `geometry_type == "Point"`, `epsg == 7899`, `fid_column == "OBJECTID"`, `geometry_column == "SHAPE"`, target table `vmadd_address`, `PFI` width 10, `EZI_ADDRESS` width 80, `UFI` width `None`, the driver's own unrounded extent (checked against `pyogrio.read_info()` called directly in the test), `manifest.json`+sidecar present with a matching digest, the real artifact's SHA-256 unchanged before/after, and the temp run root removed in a `finally` block

## Task Commits

Each task was committed atomically:

1. **Task 1: Settle the manifest contract and its canonical, hashable persistence** - `0ffe477` (feat, prior session)
2. **Task 2: Compose the ordered run and prove every hard stop lands before anything is written** - `3c9c4ef` (feat, prior session)
3. **Task 3: Record one live proof against the real Vicmap delivery** - `9523116` (test, this session)

**Plan metadata:** (this commit, recorded after SUMMARY.md is written)

## Files Created/Modified

- `vicmap_acquire/manifest.py` - Nested `provenance` payload key, exclusive fsynced `manifest.json`+sidecar writes, `ManifestWriteFailed` guard
- `discover_order.py` - `run_discovery`'s complete ordered composition, `_EmitOnce`-guarded evidence stream, `RunDiscoveryReportingFailed`
- `tests/test_manifest.py` - Manifest round-trip suite (Task 1), the eleven GEO-05 composition regressions plus stage-ordering/faulty-sink/redaction/no-socket/no-db proofs (Task 2), and the opt-in live-delivery regression (Task 3)

## Decisions Made

- **D-21 confirmed locked** (operator, 02-01 Wave 1 checkpoint): target table name is `{gdb_stem}_{layer}` normalized. This plan's live regression is the final, end-to-end confirmation: `VMADD.gdb`/`ADDRESS` publishes as `vicmap.vmadd_address` against the real delivery, not just fixtures.
- **Corrected the field-count assertion from 40 to 61** (this session). `02-RESEARCH.md` recorded "40 attribute fields" for the real `ADDRESS` layer. Running `ogrinfo -json -al -so` directly against the same real `VMADD.gdb`/`ADDRESS` layer this session -- an independent oracle, matching the project's established differential-testing discipline (MEMORY.md: "hand-written tests share the code's blind spot; use an independent oracle for parsing/visibility logic") -- returned 61 fields, all genuine Vicmap address schema attributes (`BLG_UNIT_*`, `FLOOR_*`, `HOUSE_*`, `DISP_*`, `ROAD_*`, etc.), not a parsing artifact. Since Task 3's entire purpose is pinning the *actual, currently verifiable* truth as a future-upgrade regression, the test asserts 61 (the live-verified value), not the stale research figure. `PFI`/`EZI_ADDRESS`/`UFI` widths from the original research were independently reconfirmed correct.
- **Test-local `max_compression_ratio=200`, not vicmap.toml's production default of 20.** The real delivery's tiny OpenFileGDB index members (`.gdbtablx`, `.atx`) compress up to ~139x (verified this session) -- the same shape 02-01's tracer fixture hit, worked around there the same way. See Deviations and Next Phase Readiness for the implication this carries for the production config.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Corrected the live test's field-count assertion from the plan's stated 40 to the actually-verified 61**
- **Found during:** Task 3, first live-test run against the real artifact
- **Issue:** The plan's action/acceptance-criteria text (sourced from `02-RESEARCH.md`) asserts "the layer has 40 attribute fields." Running the test as literally specified failed: `AssertionError: 40 != 61`.
- **Fix:** Independently re-verified the real `VMADD.gdb`/`ADDRESS` layer's field list via a standalone `ogrinfo -json -al -so` invocation (outside the test, as a manual oracle check) -- 61 fields, all genuine schema attributes, not double-counted or spurious. Updated the test assertion to 61 with an inline comment documenting the discrepancy and its evidence, so a future reader isn't confused by the mismatch with `02-RESEARCH.md`.
- **Files modified:** `tests/test_manifest.py`
- **Verification:** `nix develop path:. -c python -m unittest tests.test_manifest.LiveDeliveryRegressionTest -v` -- passes; `PFI`/`EZI_ADDRESS`/`UFI` width assertions (from the original, correct research) still hold.
- **Committed in:** `9523116`

**2. [Rule 1 - Bug] Test-local `max_compression_ratio` raised from vicmap.toml's production default (20) to 200**
- **Found during:** Task 3, first live-test run, `ArchiveCeilingExceeded` before any dataset was discovered
- **Issue:** The real delivery's smallest OpenFileGDB index members (e.g. `a00000006.gdbtablx`: 5152 bytes uncompressed from 37 bytes compressed, ratio ~139x) exceed vicmap.toml's shipped `max_compression_ratio = 20` by a wide margin -- the same pitfall 02-01's tracer fixture hit and worked around (raised to 200 there, documented as test-local, not a production default).
- **Fix:** Built the live test's `ExtractionPolicy` with `max_compression_ratio=200` (well below any zip-bomb-scale ratio) instead of loading `vicmap.toml`'s real value, with an inline comment explaining why and citing the measured ratios. `vicmap.toml` itself was not touched -- it is owned by 02-02 and out of this plan's `files_modified` scope; see Next Phase Readiness for the flagged consequence.
- **Files modified:** `tests/test_manifest.py`
- **Verification:** `nix develop path:. -c python -m unittest tests.test_manifest -v` -- 31/31 pass; full suite 374/374 pass.
- **Committed in:** `9523116`

---

**Total deviations:** 2 auto-fixed (both Rule 1 -- correcting a test assertion to match live-verified reality, and correcting a test's ceiling to a real value the archive genuinely needs)
**Impact on plan:** Both were necessary for the live test to prove anything true rather than assert a stale or too-tight number. No scope creep -- `vicmap.toml` (2's production default) was deliberately left unchanged since it is a sibling plan's file; the discrepancy is flagged below for whoever next touches production ceiling defaults.

## Issues Encountered

- **`vicmap.toml`'s production `max_compression_ratio = 20` would hard-stop a real production run of `Order_OK0VUZ.zip` today**, because several tiny OpenFileGDB index members compress at ratios up to ~139x. This is a genuine finding, not a code bug: D-26's ceilings are explicitly "Claude's discretion... calibrated off one real delivery" per `02-CONTEXT.md`, and the calibration recorded in `02-RESEARCH.md` used only the *overall* (~4.18x) and *largest-member* (~4.26x) ratios, missing the small-index-file case entirely -- the exact same blind spot 02-01's tracer test already surfaced and worked around locally. This was not fixed here: `vicmap.toml` is owned by 02-02 (a completed sibling plan) and is outside this plan's `files_modified` (`vicmap_acquire/manifest.py`, `discover_order.py`, `tests/test_manifest.py`), and raising a production ceiling is a policy decision, not a test-construction one. Flagged explicitly for the operator/next plan that runs `discover_order.py` against a real delivery.

## User Setup Required

None - no external service configuration required. Note: a real production run of `discover_order.py` against `artifacts/Order_OK0VUZ.zip` under the *current* `vicmap.toml` will fail with `archive_ceiling_exceeded` until `max_compression_ratio` is raised (see Issues Encountered above and Next Phase Readiness).

## Next Phase Readiness

- The Phase 2 -> Phase 3 handoff contract (`manifest.json`'s settled schema, `ImportManifest`'s frozen field names) is complete and live-proven against the real delivery; Phase 3 can build its loader against these exact keys with no further discovery-side changes expected.
- **Action item, not this plan's to fix:** `vicmap.toml`'s `[extraction].max_compression_ratio = 20` should be raised (200+ recommended, matching both this plan's and 02-01's test-local value) before running `discover_order.py` for real against `Order_OK0VUZ.zip` -- the current default will hard-stop on the real delivery's small OpenFileGDB index files. This is a one-line config change in a file 02-02 owns.
- GEO-02, GEO-03, GEO-04, and GEO-05 are all declared complete by this plan and its siblings (`GEO-02`/`GEO-03`: 02-01/02-06; `GEO-04`: 02-01/02-05/02-06; `GEO-05`: 02-01/02-04/02-05/02-06). `requirements.ready-ids` reports all 4 ready now that this, the last declaring plan, has a SUMMARY -- marked complete in `REQUIREMENTS.md` as part of this plan's close-out.
- Full suite green: `nix develop path:. -c python -m unittest discover -s tests -p 'test_*.py' -v` reports 374 tests, `OK` (373 baseline after Task 2 + 1 new live regression from Task 3, zero regressions).
- Phase 2 (Safe Geospatial Discovery) is now complete: this is its last plan.

---
*Phase: 02-safe-geospatial-discovery*
*Completed: 2026-09-16*

## Self-Check: PASSED

All 3 key files found on disk (`vicmap_acquire/manifest.py`, `discover_order.py`,
`tests/test_manifest.py`). All 3 referenced commits (`0ffe477`, `3c9c4ef`, `9523116`)
found in `git log`. Full suite re-run: 374 tests, `OK` (373 baseline + 1 new).
Live regression re-confirmed: `tests.test_manifest.LiveDeliveryRegressionTest` --
1 test, `OK`, real artifact SHA-256 unchanged before/after.
plan_head_before: 2b5910b6bf57f6322042ff6733a9c3a748055b00
