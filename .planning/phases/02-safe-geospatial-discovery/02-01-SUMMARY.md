---
phase: 02-safe-geospatial-discovery
plan: 01
subsystem: geospatial-discovery
tags: [pyogrio, pyproj, gdal, ogrinfo, zipfile, nix, tdd]

# Dependency graph
requires:
  - phase: 01-trusted-graph-acquisition
    provides: DownloadResult path/byte_count/sha256 provenance and the SuccessEvent/SafeFailure/_SafeEvent evidence machinery this plan extends
provides:
  - Reproducible dev shell supplying pyogrio, pyproj, and the GDAL ogrinfo/ogr2ogr CLI
  - Three checked-in OpenFileGDB fixtures (delivery-shaped, geometry-less, 3D point) with a deterministic re-runnable generator
  - Fail-closed archive extraction (ExtractionPolicy/verify_artifact/extract_artifact) mirroring download.py's atomic-publish idiom
  - pyogrio + ogrinfo layer discovery and profiling (DiscoveryPolicy/discover_layers) with the field-width gap closed
  - D-21/D-22 target-table normalization and D-23/D-24 collision detection (naming.py)
  - Frozen ImportManifest contract plus canonical manifest.json + sidecar digest persistence (manifest.py)
  - discover_order.run_discovery orchestration seam proving one verified artifact becomes one manifest naming vmadd_address end to end
  - 17 new closed Stage/ReasonCode vocabulary entries and 3 new redacted SuccessEvent classmethods
affects: [02-02-config-driven-discovery, 02-03-extraction-hardening, 02-04-discovery-hardening, 02-05-naming-hardening, 02-06-manifest-finalization]

# Actuals (#2632)
actuals:
  tokens: 18358
  tasks: 3
  commits: 3

# Tech tracking
tech-stack:
  added: [pyogrio, pyproj, gdal (ogrinfo/ogr2ogr CLI)]
  patterns:
    - "Reject-before-write member validation before opening any output handle (Pattern 1)"
    - "Streamed extraction with per-member and cumulative byte-ceiling enforcement against actual decompressed bytes"
    - "os.rename from a private .tmp- sibling directory into the published run directory as the sole commit point; failed guard trips leave the .tmp- directory behind for inspection (D-25), never delete it"
    - "Total-function-with-catch-all: every discovery entry point collapses unexpected exceptions to one typed closed failure, never raw driver/subprocess text"
    - "geometry_type is None (non-spatial, D-35) vs geometry_type == 'Unknown' (D-38 hard stop) kept as two distinct checks, never conflated"

key-files:
  created:
    - vicmap_acquire/extraction.py
    - vicmap_acquire/discovery.py
    - vicmap_acquire/naming.py
    - vicmap_acquire/manifest.py
    - discover_order.py
    - tests/test_discovery_tracer.py
    - tests/fixtures/build_fixtures.py
    - tests/fixtures/Order_TRACER1.zip
    - tests/fixtures/geometryless_gdb.zip
    - tests/fixtures/point_z_gdb.zip
  modified:
    - flake.nix
    - .gitignore
    - vicmap_acquire/evidence.py
    - tests/test_evidence.py
    - tests/test_repository_policy.py

key-decisions:
  - "D-21 confirmed as locked by the operator at the Task 2 checkpoint: target table name is {gdb_stem}_{layer} normalized, no configurable prefix -- VMADD.gdb/ADDRESS publishes as vmadd_address."
  - "Added ProvenanceUnavailable (Stage.ARTIFACT_VERIFY) to extraction.py's exception hierarchy, distinct from ArtifactChecksumMismatch: a missing/malformed expected_sha256 or expected_byte_count is 'Phase 1 provenance not supplied', not 'artifact fails to match a supplied value'. This was the cleanest place to make the plan's 17th ReasonCode (PROVENANCE_UNAVAILABLE) reachable from a defined exception class."
  - "run_discovery re-raises the original typed exception (e.g. ArtifactChecksumMismatch) after emitting one redacted SafeFailure event, rather than wrapping it in an orchestration-specific failure type -- matches the plan's literal acceptance criterion wording and keeps 'no stage swallows another stage's exception' exact."
  - "discover_order.main() is a guarded stub returning 1 with a CONFIG_INVALID SafeFailure: full vicmap.toml-driven configuration is explicitly deferred to 02-02, so main() stays complete/importable/zero-side-effect without inventing a config format this plan doesn't own."

patterns-established:
  - "ExtractionPolicy/DiscoveryPolicy field names are now the fixed contracts 02-02 maps vicmap.toml keys onto; 02-03/02-04 only add validation, never rename."
  - "LayerProfile/FieldProfile field names are now the fixed contracts 02-04 fills and 02-05/02-06 read verbatim (dataset_stem, layer_name, etc.)."

requirements-completed: [GEO-01, GEO-02, GEO-03, GEO-04, GEO-05]

coverage:
  - id: D1
    description: "Reproducible dev shell supplies pyogrio/pyproj/ogrinfo without relying on the operator's ambient profile"
    requirement: GEO-01
    verification:
      - kind: unit
        ref: "command: nix develop path:. -c python -c \"import pyogrio, pyproj\"; nix develop path:. -c ogrinfo --version"
        status: pass
    human_judgment: false
  - id: D2
    description: "Three checked-in OpenFileGDB fixtures with a deterministic, byte-identical-on-rerun generator"
    verification:
      - kind: unit
        ref: "tests/test_repository_policy.py (git-ignore coverage) plus manual two-run byte-identical proof in Task 1"
        status: pass
    human_judgment: false
  - id: D3
    description: "Fail-closed archive extraction re-verifies the artifact and rejects unsafe members before any write"
    requirement: GEO-01
    verification:
      - kind: unit
        ref: "tests/test_discovery_tracer.py#test_checksum_mismatch_stops_before_any_extraction"
        status: pass
      - kind: unit
        ref: "tests/test_discovery_tracer.py#test_correct_hash_with_wrong_byte_count_also_rejected"
        status: pass
    human_judgment: false
  - id: D4
    description: "One verified artifact becomes one manifest end to end, naming target table vmadd_address with the exact GEO-03 profile"
    requirement: GEO-02
    verification:
      - kind: unit
        ref: "tests/test_discovery_tracer.py#OrderManifestTracerTest.test_verified_artifact_becomes_one_manifest_end_to_end"
        status: pass
    human_judgment: false
  - id: D5
    description: "Every discovered layer's fields, feature count, geometry type, and source CRS are captured, including the field-width gap pyogrio itself does not expose"
    requirement: GEO-03
    verification:
      - kind: unit
        ref: "tests/test_discovery_tracer.py#test_verified_artifact_becomes_one_manifest_end_to_end (asserts EZI_ADDRESS width == 80, feature_count == 2, epsg == 7899, geometry_type == 'Point')"
        status: pass
    human_judgment: false
  - id: D6
    description: "Deterministic source-layer-to-table-name mapping is visible in the manifest before any database mutation"
    requirement: GEO-04
    verification:
      - kind: unit
        ref: "tests/test_discovery_tracer.py#test_verified_artifact_becomes_one_manifest_end_to_end (asserts layer.target_table == 'vmadd_address')"
        status: pass
    human_judgment: false
  - id: D7
    description: "Checksum mismatch stops the run before database work with no directory left under the run root"
    requirement: GEO-05
    verification:
      - kind: unit
        ref: "tests/test_discovery_tracer.py#test_checksum_mismatch_stops_before_any_extraction"
        status: pass
    human_judgment: false
  - id: D8
    description: "reason_stage_vocabulary() is complete for all 17 new Phase 2 reason codes, each reachable from a defined exception class's code"
    verification:
      - kind: unit
        ref: "tests/test_evidence.py#test_phase_2_reason_codes_extend_the_closed_vocabulary"
        status: pass
      - kind: unit
        ref: "tests/test_evidence.py#test_every_reason_has_one_fixed_stage_and_remediation_hint"
        status: pass
    human_judgment: false
  - id: D9
    description: "Operator-facing evidence stays redacted: order ID, counts, target table names, digests, and path fingerprints only -- never the run directory's absolute path or a raw companion filename"
    requirement: GEO-03
    verification:
      - kind: unit
        ref: "tests/test_discovery_tracer.py#test_verified_artifact_becomes_one_manifest_end_to_end (redaction boundary assertions)"
        status: pass
    human_judgment: false
  - id: D10
    description: "Importing discover_order and every new vicmap_acquire module creates no directory as a side effect"
    verification:
      - kind: unit
        ref: "tests/test_discovery_tracer.py#test_importing_every_new_module_creates_no_directory"
        status: pass
    human_judgment: true
    rationale: "The test proves 'no directory created' via a fresh-interpreter subprocess check, which is a real but partial proxy for the full 'no filesystem, subprocess, or network work' claim in the plan's must_haves.truths -- subprocess-spawn and socket-open cannot be proven negative by this same mechanism without a heavier instrumentation harness 02-01 did not build."

duration: 55min
completed: 2026-09-15
status: complete
---

# Phase 2 Plan 1: Safe Geospatial Discovery Tracer Summary

**Fail-closed extraction + pyogrio/ogrinfo layer profiling + D-21 naming wired end to end, proving one checksum-verified `Order_TRACER1.zip` becomes one immutable `manifest.json` naming `vmadd_address`.**

## Performance

- **Duration:** ~55 min active work across two sessions (Task 1 in a prior session, Task 2's checkpoint decision resolved by the operator, Task 3 in this continuation session; wall-clock between sessions excluded)
- **Tasks:** 3 (Task 1: toolchain + fixtures; Task 2: checkpoint:decision, no commit; Task 3: TDD tracer)
- **Files modified:** 15 (10 created, 5 modified) across the whole plan

## Accomplishments

- `flake.nix`'s dev shell now supplies `pyogrio`, `pyproj`, and the GDAL `ogrinfo`/`ogr2ogr` CLI reproducibly, with the reviewed supply-chain waiver recorded inline
- Three deterministic, checked-in OpenFileGDB fixtures (delivery-shaped, geometry-less, 3D point) with a re-runnable, byte-identical generator
- `vicmap_acquire/extraction.py` — fail-closed zip extraction: reject-before-write member validation, streamed per-member/cumulative byte ceilings against actual decompressed bytes, atomic `os.rename` publish, D-28 checksum re-verification distinct from D-32's provenance-availability check
- `vicmap_acquire/discovery.py` — `pyogrio.read_info()` for bulk metadata plus one `ogrinfo -json -al -so` subprocess per dataset for the field width/precision/nullability gap; D-35/D-38's `None`-vs-`"Unknown"` geometry distinction kept intact
- `vicmap_acquire/naming.py` — pure `{gdb_stem}_{layer}` normalization (D-21/D-22) and same-delivery collision detection (D-23/D-24)
- `vicmap_acquire/manifest.py` — frozen `ImportManifest` contract plus canonical `manifest.json` + `manifest.json.sha256` persistence, reusing `evidence.py`'s one existing deterministic-JSON idiom
- `discover_order.py` — `run_discovery` orchestration seam composing verify → extract → discover → name → build → write → render, mirroring `read_mailbox.run_acquisition`'s shape
- `vicmap_acquire/evidence.py` extended in place: 5 new `Stage` members, 17 new `ReasonCode` members (each with a `_FAILURE_POLICY` entry), a `_require_target_table` validator, and 3 new redacted `SuccessEvent` classmethods (`artifact_verified`, `archive_extracted`, `manifest_completed`)
- `tests/test_discovery_tracer.py::OrderManifestTracerTest` — the Wave 0 end-to-end regression, run through a genuine RED → GREEN TDD cycle

## Task Commits

Task 1 was completed and committed by a prior executor; this session (continuation) covers Task 2 (resolved, no commit) and Task 3 (RED/GREEN).

1. **Task 1: Make the geospatial toolchain reproducible and record the integration declaration** - `8517e7f` (feat, prior session)
2. **Task 2: Confirm the published target-table naming contract** - checkpoint:decision, resolved "confirm" (D-21 locked), no commit
3. **Task 3 RED: Add failing tracer test for discovery path** - `3011e12` (test)
4. **Task 3 GREEN: Implement artifact-to-manifest discovery path** - `e419540` (feat)

**Plan metadata:** (this commit, recorded after SUMMARY.md is written)

_TDD tasks may have multiple commits (test → feat → refactor); no REFACTOR commit was needed here -- the GREEN implementation required no post-hoc cleanup._

## Files Created/Modified

- `vicmap_acquire/extraction.py` - Fail-closed zip extraction, `ExtractionPolicy`, `verify_artifact`, `extract_artifact`
- `vicmap_acquire/discovery.py` - pyogrio + ogrinfo layer profiling, `DiscoveryPolicy`, `discover_layers`
- `vicmap_acquire/naming.py` - D-21/D-22 normalization, D-23/D-24 collision detection
- `vicmap_acquire/manifest.py` - Frozen `ImportManifest`, `manifest.json` + sidecar persistence
- `discover_order.py` - `run_discovery` orchestration seam and guarded CLI stub
- `vicmap_acquire/evidence.py` - Extended `Stage`/`ReasonCode`/`_FAILURE_POLICY`, 3 new `SuccessEvent` classmethods
- `tests/test_discovery_tracer.py` - `OrderManifestTracerTest`, the Wave 0 tracer regression
- `tests/test_evidence.py` - Vocabulary-completeness and unsafe-scalar-rejection cases for the Phase 2 additions
- `flake.nix`, `.gitignore`, `tests/fixtures/*` - Task 1 toolchain/fixture work (prior session)

## Decisions Made

- **D-21 locked** (operator, Task 2 checkpoint): target table name is `{gdb_stem}_{layer}` normalized, no configurable prefix. `VMADD.gdb`/`ADDRESS` publishes as `vmadd_address`, verified end to end by the tracer.
- Added `ProvenanceUnavailable` to `extraction.py`'s exception hierarchy (Rule 2 — the plan's 17th reason code, `PROVENANCE_UNAVAILABLE`, needed a reachable exception class; a missing/malformed expected checksum is a distinct condition from a well-formed one the artifact fails to match).
- `run_discovery` re-raises the original typed exception after emitting a redacted failure event, rather than wrapping it in a new orchestration-specific type — keeps the acceptance criterion's literal wording ("raises the closed `ArtifactChecksumMismatch`") true and "no stage swallows another stage's exception" exact.
- `discover_order.main()` is a guarded stub (returns 1, no config format invented) since full `vicmap.toml` loading is explicitly 02-02's responsibility.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Added `ProvenanceUnavailable` exception to extraction.py**
- **Found during:** Task 3 (implementing `evidence.py`'s 17-reason-code vocabulary)
- **Issue:** The plan lists `PROVENANCE_UNAVAILABLE` among the 17 new `ReasonCode` members but does not name a corresponding exception class in `extraction.py`'s hierarchy bullet list, and the acceptance criterion requires every reason code be "reachable from a defined exception class's `code`."
- **Fix:** Added `ProvenanceUnavailable(ArchiveFailure)` and made `verify_artifact` raise it when `expected_sha256`/`expected_byte_count` are missing or malformed, distinct from `ArtifactChecksumMismatch` (well-formed expected values that don't match). This is exactly D-28's "takes them as required input" requirement given a concrete typed failure.
- **Files modified:** `vicmap_acquire/extraction.py`
- **Verification:** `tests/test_evidence.py::test_phase_2_reason_codes_extend_the_closed_vocabulary` confirms all 17 codes are present and stage-mapped.
- **Committed in:** `e419540`

**2. [Rule 1 - Consistency] Added a `ManifestFailure` base class**
- **Found during:** Task 3 (implementing `manifest.py`)
- **Issue:** The plan names only `ManifestWriteFailed` as the exported failure type, but every other new module (`extraction.py`, `discovery.py`, `naming.py`) follows a base-plus-subclass exception hierarchy per the established `download.py` pattern.
- **Fix:** Added `ManifestFailure(RuntimeError)` as the base, with `ManifestWriteFailed` as its sole subclass, matching the codebase-wide pattern.
- **Files modified:** `vicmap_acquire/manifest.py`
- **Verification:** No behavior change — `ManifestWriteFailed.code` is unchanged; existing tests unaffected.
- **Committed in:** `e419540`

**3. [Rule 1 - Bug] Raised the tracer test's `max_compression_ratio` from 100 to 200**
- **Found during:** Task 3 GREEN phase, first test run
- **Issue:** `Order_TRACER1.zip`'s smallest `.gdbtablx` index members legitimately compress at ratios up to ~123x (tiny, highly-repetitive fixed-size index records), which exceeded the test's initial 100x ceiling and raised `ArchiveCeilingExceeded` on a fully legitimate fixture.
- **Fix:** Raised the test-local `max_compression_ratio` to 200, still far below any zip-bomb-scale ratio, and specific to this test's `ExtractionPolicy` construction (not a production default — D-26's real ceiling defaults remain Claude's discretion for a later plan).
- **Files modified:** `tests/test_discovery_tracer.py`
- **Verification:** All 4 tracer tests pass.
- **Committed in:** `e419540`

---

**Total deviations:** 3 auto-fixed (1 missing critical, 2 bug/consistency)
**Impact on plan:** All three were necessary for correctness (reachable exception class, ceiling calibration) or codebase consistency. No scope creep — `naming.py`'s reserved-word/leading-digit/63-byte rules and `discovery.py`'s full adversarial matrix remain explicitly deferred to 02-05/02-03/02-04 as the plan specifies.

## Issues Encountered

None beyond the deviations documented above.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- `ExtractionPolicy`/`DiscoveryPolicy` field names and `LayerProfile`/`FieldProfile` field names are now fixed contracts; 02-02 maps `vicmap.toml` keys onto the policies, and 02-03/02-04/02-05/02-06 fill in validation, adversarial-matrix tests, and the manifest's remaining detail without renaming anything this plan established.
- `tests/fixtures/geometryless_gdb.zip` and `tests/fixtures/point_z_gdb.zip` exist and are ready for 02-04's D-35/D-38 expansion tests; this plan's tracer only exercised `Order_TRACER1.zip`'s single `ADDRESS` layer.
- The Phase 1 → Phase 2 message-fingerprint handoff gap flagged in `02-RESEARCH.md` (Pitfall 5) remains open for 02-02 to resolve via the `artifacts/Order_{id}.provenance.json` sidecar; this plan's tracer accepts `message_fingerprint` as an explicit `DiscoveryConfig` field for now.
- No blockers for 02-02.

---
*Phase: 02-safe-geospatial-discovery*
*Completed: 2026-09-15*

## Self-Check: PASSED

All 8 key files found on disk (extraction.py, discovery.py, naming.py,
manifest.py, discover_order.py, test_discovery_tracer.py, COVERAGE.md,
flake.nix). All 3 referenced commits (8517e7f, 3011e12, e419540) found in
`git log`. Full suite green: 198 tests, `OK`.
