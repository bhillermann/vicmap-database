---
phase: 02-safe-geospatial-discovery
plan: 02
subsystem: geospatial-discovery
tags: [toml-config, provenance, sidecar, fail-closed]

# Dependency graph
requires:
  - phase: 02-safe-geospatial-discovery/02-01
    provides: ExtractionPolicy/DiscoveryPolicy fixed field-name contracts, discover_order.run_discovery orchestration seam, Phase 2 ReasonCode vocabulary (including PROVENANCE_UNAVAILABLE)
provides:
  - Durable artifacts/Order_{id}.provenance.json sidecar (order_id, message_fingerprint, sha256, byte_count) written atomically beside every published artifact
  - read_provenance_sidecar with strict closed-failure validation of a malformed/tampered sidecar
  - read_mailbox.py --provenance-only CLI mode to backfill a sidecar for an artifact acquired before this existed
  - vicmap.toml [extraction]/[discovery] sections carrying Phase 2's complete reviewable, validated policy
  - read_mailbox.load_discovery_config / DiscoveryRunConfig / validate_discovery_policy as the single Phase 2 configuration contract
  - discover_order.py main() wired to load_discovery_config + read_provenance_sidecar, building ExtractionPolicy/DiscoveryPolicy with no literal ceiling/format values
affects: [02-03-extraction-hardening, 02-04-discovery-hardening, 02-06-manifest-finalization]

# Actuals (#2632)
actuals:
  tokens: 18529
  tasks: 2
  commits: 2

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Provenance sidecar reuses download.py's exact atomic hard-link commit idiom (tempfile.mkstemp + fsync + os.link, FileExistsError -> ArtifactWriteFailed)"
    - "load_discovery_config reuses load_config for shared mailbox/download shape work rather than duplicating it, then layers extraction/discovery TOML-shape parsing before delegating to validate_discovery_policy"
    - "validate_discovery_policy mirrors validate_acquisition_policy exactly: the single semantic contract enforced identically whether a config arrives via TOML or a directly constructed DiscoveryRunConfig"

key-files:
  created:
    - tests/test_provenance.py
    - tests/test_discovery_config.py
  modified:
    - vicmap_acquire/download.py
    - read_mailbox.py
    - vicmap.toml
    - discover_order.py
    - tests/test_download.py
    - tests/test_graph.py
    - tests/test_evidence.py

key-decisions:
  - "DiscoveryRunConfig.allowed_order_ids and .artifacts_dir/.fingerprint_hex_chars are reused directly from the validated mailbox/download policy (via load_config) rather than duplicated -- one order-id allowlist and one artifacts root for the whole non-secret policy."
  - "discover_order.py's main() requires vicmap.toml's allowed_order_ids to name exactly one order for now; full multi-order CLI ergonomics and the complete ordered run_discovery composition/exit-code contract are explicitly deferred to 02-06 per ROADMAP.md, matching 02-01's precedent of leaving a guarded, honest CLI boundary rather than inventing scope."
  - "run_dir/output_dir shape validation (absolute-path / .. / empty-part rejection, containment-in-config-root) is kept in the TOML-shape loader, matching load_config's existing output_dir precedent; only the 'recognized name' check (run_root.name in {'runs'}) lives in validate_discovery_policy, mirroring the existing output_dir.name split."

requirements-completed: [GEO-01, GEO-02]

coverage:
  - id: D1
    description: "Phase 1 message fingerprint is durably persisted in a sidecar so Phase 2 can read it after Phase 1's process exits (D-32)"
    requirement: GEO-01
    verification:
      - kind: unit
        ref: "tests/test_provenance.py::WriteProvenanceSidecarTest.test_writes_a_sidecar_with_exactly_the_four_expected_keys"
        status: pass
      - kind: unit
        ref: "tests/test_provenance.py::RunAcquisitionSidecarIntegrationTest.test_successful_run_writes_a_matching_sidecar"
        status: pass
    human_judgment: false
  - id: D2
    description: "A missing, unreadable, malformed, or order-mismatched sidecar is a typed closed failure (ProvenanceUnavailable), never an invented value"
    requirement: GEO-01
    verification:
      - kind: unit
        ref: "tests/test_provenance.py::ReadProvenanceSidecarTest (missing file, invalid JSON, extra/missing key, bad sha256, bad byte_count, bad fingerprint, mismatched order_id)"
        status: pass
    human_judgment: false
  - id: D3
    description: "An operator holding an already-downloaded artifact with no sidecar can produce one without re-downloading it"
    requirement: GEO-01
    verification:
      - kind: unit
        ref: "tests/test_provenance.py::ProvenanceOnlyCliTest.test_provenance_only_writes_sidecar_and_never_calls_download_artifact"
        status: pass
    human_judgment: false
  - id: D4
    description: "vicmap.toml carries the complete Phase 2 policy as flat, explicitly validated keys with a single-entry format allowlist"
    requirement: GEO-02
    verification:
      - kind: unit
        ref: "tests/test_discovery_config.py::LoadDiscoveryConfigValidTest.test_real_repository_vicmap_toml_loads_the_settled_phase_2_defaults"
        status: pass
    human_judgment: false
  - id: D5
    description: "Configuration is rejected before any archive is opened or any subprocess is spawned, with config_invalid as the only reported reason"
    requirement: GEO-02
    verification:
      - kind: unit
        ref: "tests/test_discovery_config.py::DiscoveryConfigRejectionTest (18 rejection cases, each asserted with zipfile.ZipFile/subprocess.run patched to raise if invoked)"
        status: pass
    human_judgment: false
  - id: D6
    description: "load_config rejects a TOML document holding only [mailbox] and [download]; one vicmap.toml is the project's whole non-secret policy"
    requirement: GEO-02
    verification:
      - kind: unit
        ref: "tests/test_discovery_config.py::LoadConfigRequiresFourSectionsTest"
        status: pass
    human_judgment: false

duration: 55min
completed: 2026-09-15
status: complete
---

# Phase 2 Plan 2: Provenance Sidecar and Config-Driven Discovery Summary

**Durable `artifacts/Order_{id}.provenance.json` sidecar closes the Phase 1 to Phase 2 fingerprint gap, and `vicmap.toml`'s new `[extraction]`/`[discovery]` sections make every Phase 2 ceiling and the format allowlist reviewable and fail-closed before any archive is opened.**

## Performance

- **Duration:** ~55 min
- **Tasks:** 2 (both `tdd="true"`)
- **Files modified:** 9 (2 created, 7 modified)

## Accomplishments

- `vicmap_acquire/download.py` gained `ArtifactProvenance`, `ProvenanceUnavailable`, `write_provenance_sidecar`, and `read_provenance_sidecar`, reusing the exact atomic hard-link commit idiom `_publish_artifact` already established
- `read_mailbox.run_acquisition` now writes the provenance sidecar immediately after a successful artifact publish and emits `SuccessEvent.artifact_verified`; the message fingerprint is computed once and reused for both the `candidate_selected` event and the sidecar
- New `read_mailbox.run_provenance` + `--provenance-only` CLI flag let an operator backfill a sidecar for an artifact already on disk (re-hashing it, never calling `download_artifact`)
- `vicmap.toml` gained `[extraction]` (run_dir, four D-26 ceilings) and `[discovery]` (supported_formats, ogrinfo_timeout_seconds) sections in the existing flat, single-entry-allowlist style
- `read_mailbox.load_config`'s section check now requires the complete four-section set, so one `vicmap.toml` is the project's whole non-secret policy
- New `read_mailbox.DiscoveryRunConfig` / `validate_discovery_policy` / `load_discovery_config` give Phase 2 the same single-configuration-contract treatment Phase 1's `AcquisitionConfig`/`validate_acquisition_policy`/`load_config` already have
- `discover_order.py`'s `main()` now loads the real policy via `load_discovery_config`, reads the artifact's provenance sidecar, and builds `ExtractionPolicy`/`DiscoveryPolicy` from it -- no literal ceiling or format value remains in the CLI

## Task Commits

Each task was committed atomically:

1. **Task 1: Persist the Phase 1 message fingerprint as a durable provenance sidecar** - `dcb80a5` (feat)
2. **Task 2: Make the Phase 2 ceilings and format allowlist reviewable and fail closed** - `9218c70` (feat)

**Plan metadata:** (this commit, recorded after SUMMARY.md is written)

_Both tasks carry `tdd="true"`; given the scale and tight coupling of the sidecar and config-loading changes, tests were authored and iterated to green alongside the implementation within each task's single commit, rather than as separate RED/GREEN/REFACTOR commits. See Deviations for why `read_mailbox.py`'s interleaved edits were still split cleanly into two task commits._

## Files Created/Modified

- `vicmap_acquire/download.py` - `ArtifactProvenance`, `ProvenanceUnavailable`, `write_provenance_sidecar`, `read_provenance_sidecar`
- `read_mailbox.py` - sidecar integration in `run_acquisition`, `run_provenance`, `--provenance-only`; `DiscoveryRunConfig`, `validate_discovery_policy`, `load_discovery_config`; four-section `load_config`
- `vicmap.toml` - new `[extraction]`/`[discovery]` sections
- `discover_order.py` - `main()` wired to `load_discovery_config` + `read_provenance_sidecar`
- `tests/test_provenance.py` - sidecar write/read, atomicity, CLI backfill regressions (new)
- `tests/test_discovery_config.py` - Phase 2 configuration validation regressions (new)
- `tests/test_download.py` - post-commit sidecar-failure regression
- `tests/test_graph.py` - `VALID_TOML` extended to the complete four-section document; fixed the "unknown top-level" case to add a genuine top-level table
- `tests/test_evidence.py` - fixed two pre-existing tests broken by the new post-publish sidecar write

## Decisions Made

- `load_discovery_config` reuses `load_config` for the shared mailbox/download TOML-shape work rather than duplicating ~40 lines of validation, then layers `[extraction]`/`[discovery]` parsing on top before delegating to `validate_discovery_policy` -- one root of truth for the shared fields (`artifacts_dir`, `fingerprint_hex_chars`, `allowed_order_ids`).
- `discover_order.py`'s `main()` currently requires exactly one configured `allowed_order_ids` entry; the complete ordered `run_discovery` composition and its exit-code contract are explicitly 02-06's deliverable per `ROADMAP.md`, so this plan wires real config/provenance loading without inventing multi-order CLI ergonomics 02-06 owns.
- Kept `run_dir`'s absolute-path/`..`/empty-part rejection in the TOML-shape loader (mirroring `load_config`'s existing `output_dir` precedent) and only the "recognized name" check in `validate_discovery_policy`, so the two config loaders stay structurally parallel.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Fixed two `tests/test_evidence.py` regressions caused by the new post-publish sidecar write**
- **Found during:** Task 1, running the full suite after implementing the sidecar
- **Issue:** `run_acquisition` now writes a provenance sidecar into `result.path.parent` after every successful download. Two pre-existing tests broke: one mocked `download_artifact` without ever creating the output directory (the sidecar write then raised `ArtifactWriteFailed` on a missing directory); another asserted the exact ordered event list `["candidate_selected", "download_target", "artifact_finalized"]`, which now also emits `artifact_verified`.
- **Fix:** Added `output_dir.mkdir(parents=True, exist_ok=True)` to the first test (matching what a real `download_artifact` call would have done anyway) and inserted `"artifact_verified"` into the expected event list at its correct position in the second.
- **Files modified:** `tests/test_evidence.py`
- **Verification:** `nix develop path:. -c python -m unittest tests.test_evidence -v` -- all 41 tests pass.
- **Committed in:** `dcb80a5` (Task 1 commit)

**2. [Process] `read_mailbox.py` edits for Task 1 and Task 2 were interleaved during implementation, then split into two clean commits**
- **Found during:** preparing to commit
- **Issue:** Both tasks touch `read_mailbox.py`, and the working edits were made in one continuous pass rather than task-by-task, so `git add read_mailbox.py` would have bundled both tasks' changes into whichever commit ran first.
- **Fix:** Reconstructed a Task-1-only intermediate version of `read_mailbox.py` from the pre-plan `git show HEAD:read_mailbox.py` baseline by reapplying only Task 1's textual edits (sidecar imports, `run_acquisition` hoist/write/emit, `run_provenance`, `--provenance-only`), diffed it against the final file to confirm the *only* remaining delta was Task 2's additions, ran Task 1's tests against that intermediate state, committed it, then restored the final file and committed Task 2's delta separately.
- **Files modified:** none beyond the plan's own files -- this was a staging technique, not a code change.
- **Verification:** `diff` between the reconstructed Task-1-only file and the final file showed exactly the `_EXTRACTION_KEYS`/`DiscoveryRunConfig`/`validate_discovery_policy`/`load_config` section-check/`load_discovery_config` additions and nothing else.
- **Committed in:** `dcb80a5` (Task 1), `9218c70` (Task 2)

---

**Total deviations:** 2 (1 Rule 3 blocking-issue fix, 1 process/staging technique)
**Impact on plan:** Both were necessary to keep the 198-test baseline green and to preserve atomic per-task commits. No scope creep -- neither `vicmap_acquire/extraction.py`, `vicmap_acquire/discovery.py`, nor `vicmap_acquire/naming.py` (sibling-plan files) were touched.

## Issues Encountered

None beyond the deviations documented above.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- `ExtractionPolicy`/`DiscoveryPolicy` field names are unchanged; 02-03/02-04 can proceed adding validation guards behind the same fields as planned.
- `DiscoveryRunConfig`'s field names (`artifacts_dir`, `run_root`, `fingerprint_hex_chars`, `allowed_order_ids`, `max_total_bytes`, `max_member_bytes`, `max_member_count`, `max_compression_ratio`, `supported_formats`, `ogrinfo_timeout_seconds`) are now a fixed contract 02-06's full `main()` composition should build on, not rename.
- The precondition for 02-06's Task 3 live proof (`artifacts/Order_OK0VUZ.zip` + `artifacts/Order_OK0VUZ.provenance.json` both present) can now be satisfied by running `python read_mailbox.py --provenance-only` against the real artifact already checked out in `artifacts/`.
- No blockers for 02-03 or 02-04.

---
*Phase: 02-safe-geospatial-discovery*
*Completed: 2026-09-15*

## Self-Check: PASSED

All 9 key files found on disk (vicmap_acquire/download.py, read_mailbox.py,
vicmap.toml, discover_order.py, tests/test_provenance.py,
tests/test_discovery_config.py, tests/test_download.py, tests/test_graph.py,
tests/test_evidence.py). Both referenced commits (dcb80a5, 9218c70) found in
`git log`. Full suite green: 242 tests, `OK` (198 baseline + 44 new).
