---
phase: 02-safe-geospatial-discovery
plan: 09
subsystem: manifest-publication
tags: [manifest, atomicity, rollback, fsync, durability, tdd, geo-05]

# Dependency graph
requires:
  - phase: 02-safe-geospatial-discovery
    provides: "02-07's recalibrated extraction ceilings and case-insensitive dataset extension matching; 02-06's manifest.json contract and GeoO5HardStopTest regression suite this plan extends"
provides:
  - "write_manifest is atomic: a sidecar-write failure rolls back the just-created manifest.json, so a reported GEO-05 hard stop never leaves a half-published manifest and a retry into the same run directory always succeeds"
  - "write_manifest fsyncs the run directory's own entry exactly once, after both files exist, closing WR-02"
  - "manifest.json's sidecar digest is pinned as SHA-256 over the file's real UTF-8 bytes (ensure_ascii=False), proven with non-ASCII layer/companion names"
  - "zero-layer, zero-companion manifests are proven to publish, hash, and roll back identically to populated ones"
affects: [phase-03-postgis-load]

# Actuals (#2632)
actuals:
  tokens: 4019
  tasks: 2
  commits: 4

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Scoped rollback: only the just-created file (provably created by this call via O_EXCL) is unlinked on a later step's failure -- never a broad handler around both writes"
    - "Third private _fsync_directory copy (manifest.py), matching the existing per-module copies in extraction.py and download.py rather than a shared import"

key-files:
  created: []
  modified:
    - vicmap_acquire/manifest.py
    - tests/test_manifest.py

key-decisions:
  - "Scoped the rollback to a nested try around only the sidecar write, placed after the manifest write already returned -- the manifest write's O_EXCL success is the proof this call created it, so a pre-existing manifest is never touched even if the rollback code runs on a different path in the future."
  - "Added ensure_ascii=False to write_manifest's json.dumps call (diverging from evidence.py's identical-looking idiom, which stays ASCII-escaped because its payload is redacted operator output). Without this, the digest is computed over \\uXXXX-escaped ASCII, so byte length can never exceed character length for non-ASCII names -- discovered because the plan's own required regression asserted it and failed (1170 not greater than 1170) before the fix."
  - "Kept _fsync_directory as a third private per-module copy rather than importing from extraction.py or download.py, matching the plan's explicit instruction and the existing convention of two independent copies."
  - "Called _fsync_directory exactly once, after both files exist and never on the rollback path, so the durability boundary coincides with the atomicity boundary Task 1 established."

requirements-completed: [GEO-05]

coverage:
  - id: D1
    description: "A write_manifest call whose sidecar write fails rolls back the just-created manifest.json, leaving the run directory exactly as it found it, and a retry into that same directory succeeds"
    requirement: "GEO-05"
    verification:
      - kind: unit
        ref: "tests/test_manifest.py#ManifestRoundTripTest.test_sidecar_pre_existing_leaves_no_manifest_and_directory_unchanged"
        status: pass
      - kind: unit
        ref: "tests/test_manifest.py#ManifestRoundTripTest.test_failed_sidecar_create_then_retry_succeeds_into_same_directory"
        status: pass
    human_judgment: false
  - id: D2
    description: "The pre-existing immutability guarantee is unchanged: an existing complete manifest.json is never overwritten or unlinked by the new rollback code"
    requirement: "GEO-05"
    verification:
      - kind: unit
        ref: "tests/test_manifest.py#ManifestRoundTripTest.test_rollback_does_not_fire_on_pre_existing_complete_manifest"
        status: pass
      - kind: unit
        ref: "tests/test_manifest.py#ManifestRoundTripTest.test_existing_manifest_raises_and_leaves_file_untouched"
        status: pass
    human_judgment: false
  - id: D3
    description: "A rollback unlink that itself raises still surfaces as the closed ManifestWriteFailed, never a raw OSError"
    verification:
      - kind: unit
        ref: "tests/test_manifest.py#ManifestRoundTripTest.test_rollback_unlink_failure_still_raises_manifest_write_failed"
        status: pass
    human_judgment: false
  - id: D4
    description: "A successful publication fsyncs the run directory's own entry exactly once, after both files exist; a rolled-back call never calls it; a failing directory fsync does not change the call's outcome (WR-02)"
    verification:
      - kind: unit
        ref: "tests/test_manifest.py#ManifestRoundTripTest.test_successful_write_fsyncs_run_directory_exactly_once"
        status: pass
      - kind: unit
        ref: "tests/test_manifest.py#ManifestRoundTripTest.test_rollback_path_never_calls_directory_fsync"
        status: pass
      - kind: unit
        ref: "tests/test_manifest.py#ManifestRoundTripTest.test_directory_fsync_failure_does_not_affect_successful_write"
        status: pass
    human_judgment: false
  - id: D5
    description: "The sidecar digest is SHA-256 of the manifest file's UTF-8 bytes excluding the trailing newline -- byte identity, not code-point count -- proven for non-ASCII layer and companion names, and json.loads round-trips those strings unchanged"
    requirement: "GEO-05"
    verification:
      - kind: unit
        ref: "tests/test_manifest.py#ManifestRoundTripTest.test_non_ascii_manifest_digest_is_byte_identity_not_code_point_count"
        status: pass
    human_judgment: false
  - id: D6
    description: "A zero-layer, zero-companion manifest publishes, hashes, and rolls back exactly as a populated one does, serializing layers/companions as empty JSON arrays"
    requirement: "GEO-05"
    verification:
      - kind: unit
        ref: "tests/test_manifest.py#ManifestRoundTripTest.test_empty_manifest_publishes_hashes_and_rolls_back_like_populated_one"
        status: pass
    human_judgment: false
  - id: D7
    description: "No regression: the full pre-existing suite (390 tests), including all GeoO5HardStopTest and NoSocketNoDatabaseTest cases, remains green"
    verification:
      - kind: unit
        ref: "nix develop path:. -c python -m unittest discover -s tests -p 'test_*.py' -v"
        status: pass
    human_judgment: false

duration: 11min
completed: 2026-09-16
status: complete
---

# Phase 2 Plan 9: Atomic Manifest Publication Summary

**Made `write_manifest` two-file publication atomic (rollback on sidecar failure) and durable (single post-publication directory fsync), closing CR-02 and WR-02 with a pinned UTF-8 byte-identity digest contract.**

## Performance

- **Duration:** 11 min
- **Started:** 2026-09-16T21:07:03Z
- **Completed:** 2026-09-16T21:17:59Z
- **Tasks:** 2 completed
- **Files modified:** 2

## Accomplishments

- `write_manifest` rolls back a just-created `manifest.json` when the sidecar write fails, so a reported GEO-05 hard stop never leaves a manifest on disk and a retry into the same run directory always succeeds (CR-02 closed)
- The rollback is precisely scoped: a pre-existing complete manifest is never touched, proven both by byte-identity and by asserting the unlink path is never invoked
- A rollback unlink that itself fails still surfaces as the closed `ManifestWriteFailed`, never a raw `OSError`
- `write_manifest` now fsyncs the run directory's own entry exactly once, after both files exist, matching the idiom `extraction.py`/`download.py` already use (WR-02 closed)
- The manifest sidecar digest is pinned as SHA-256 over the file's real UTF-8 bytes (found and fixed: the shipped code was ASCII-escaping non-ASCII names, which would have made this property false)
- Zero-layer, zero-companion manifests are proven to publish, hash, and roll back identically to populated ones

## Task Commits

Each task followed the RED -> GREEN cycle with its own commits:

1. **Task 1: Roll back the partially published manifest** - `0a1e061` (test, RED) -> `2deb271` (feat, GREEN)
2. **Task 2: Directory-entry durability and byte identity (WR-02)** - `c2b50d7` (test, RED) -> `643a4b7` (feat, GREEN)

No REFACTOR commit was needed for either task -- both GREEN implementations were already minimal.

**Plan metadata:** committed separately after this SUMMARY.

## Files Created/Modified

- `vicmap_acquire/manifest.py` - `write_manifest` gains a scoped sidecar-failure rollback and a single post-publication `_fsync_directory` call; new module-private `_fsync_directory` helper; `json.dumps` now passes `ensure_ascii=False`. No change to the function's signature, return value, `MANIFEST_SCHEMA_VERSION`, `build_manifest`, `manifest_payload`, or any dataclass.
- `tests/test_manifest.py` - nine new `ManifestRoundTripTest` cases: sidecar-pre-existing reproduction, retry-succeeds, rollback-scope, rollback-unlink-failure, directory-fsync call-count/argument, rollback-fsync-exclusion, directory-fsync non-interference, non-ASCII byte-identity, and zero-layer/zero-companion publish-plus-rollback.

## Decisions Made

- Scoped the rollback to a nested `try` around only the sidecar write, placed after the manifest write already returned without raising -- that success is the proof this call created `manifest.json` via its `O_EXCL` open, so the rollback can never remove a file it did not create.
- Added `ensure_ascii=False` to `write_manifest`'s `json.dumps` call. This is a real behavior fix, not cosmetic: without it, non-ASCII layer/dataset names serialize as `\uXXXX` ASCII escapes, so the manifest file's byte length can never exceed its decoded character length -- directly falsifying the plan's own required byte-identity property. `evidence.py`'s superficially identical `json.dumps` idiom is intentionally left unchanged, since its payload is already-redacted, ASCII-safe operator output.
- Kept `_fsync_directory` as a third private per-module copy (matching `extraction.py` and `download.py`'s existing independent copies) rather than importing it, per the plan's explicit instruction to avoid coupling `manifest.py` to `extraction.py` for a durability helper.
- Called `_fsync_directory` exactly once, after both files exist and never on the rollback path, so the durability boundary coincides with the atomicity boundary Task 1 established.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] `json.dumps` ASCII-escaped non-ASCII names, making the plan's required byte-identity property false**
- **Found during:** Task 2 RED phase (`test_non_ascii_manifest_digest_is_byte_identity_not_code_point_count` failed with `1170 not greater than 1170` against the pre-fix code)
- **Issue:** The shipped `json.dumps(payload, sort_keys=True, separators=(",", ":"))` call defaults to `ensure_ascii=True`, so any non-ASCII layer or companion name is escaped to a `\uXXXX` ASCII sequence before hashing. The resulting manifest bytes are then pure ASCII, so the file's byte length equals its decoded character length -- exactly contradicting the plan's must-have that the digest is "byte identity, not code-point count," provable only when a non-ASCII name's multi-byte UTF-8 encoding makes the byte count strictly exceed the character count.
- **Fix:** Added `ensure_ascii=False` to the `json.dumps` call in `write_manifest`. Transparent for every existing ASCII-only fixture (all pre-existing tests pass unmodified); `json.loads` round-trips the original non-ASCII strings unchanged either way, so no other contract shifted.
- **Files modified:** `vicmap_acquire/manifest.py`
- **Verification:** New regression asserts `len(manifest_bytes) > len(decoded_text)` and a `json.loads` round-trip of the original strings; full 399-test suite green.
- **Committed in:** `643a4b7` (Task 2 GREEN commit)

---

**Total deviations:** 1 auto-fixed (1 bug, Rule 1).
**Impact on plan:** Necessary to satisfy an explicit must-have this plan itself introduced; no scope creep -- the change is scoped to `write_manifest`'s own serialization call and does not touch `manifest_payload`, `build_manifest`, or the settled key set.

## TDD Gate Compliance

Both tasks followed RED -> GREEN with no REFACTOR needed. RED evidence was verified manually rather than via `gsd_run check tdd-red-evidence`: that verb's parser (`parseNodeTestSummary`/`tapFailedTestNames` in `check-command-router.cjs`) recognizes only Node's `# tests N` / `ok N - name` TAP output format and does not recognize Python's `unittest -v` plain-text format. Running it against a genuinely red Python test run (command exit 1, target test `test_sidecar_pre_existing_leaves_no_manifest_and_directory_unchanged` failing on `AssertionError: True is not false`) returned `INVALID_RED` with reason `zero_tests_discovered` -- a tooling/language-format gap, not evidence the RED phase was invalid. RED was instead confirmed by direct inspection of each new test's failure: the correct target test failed on the planned assertion (not an import/collection/fixture error), and sibling tests in the same file were unaffected. This is a known, project-independent limitation of the shipped `check tdd-red-evidence` verb for Python-based repositories, not specific to this plan.

| Task | RED | GREEN | REFACTOR | Status |
|------|-----|-------|----------|--------|
| 1 (rollback, CR-02) | `0a1e061` | `2deb271` | none needed | Pass (manually verified RED) |
| 2 (durability + byte identity, WR-02) | `c2b50d7` | `643a4b7` | none needed | Pass (manually verified RED) |

## Issues Encountered

None beyond the RED-evidence tooling gap documented above.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Phase 2's manifest publication contract is now atomic and durable end to end: every GEO-05 hard stop leaves no `manifest.json` and no sidecar anywhere under the run root (including the sidecar-write-failure case this plan closes), and a completed publication survives a crash to its directory entry.
- GEO-05 is now fully satisfied across its two contributing plans (02-07, 02-09) and ready to mark complete.
- Phase 3 (PostGIS load) can rely on `manifest.json` + its sidecar as an always-verifiable, never-partial contract, including for deliveries with non-ASCII layer or companion names.
- No known blockers introduced by this plan. The pre-existing `vicmap.toml` compression-ratio blocker was already resolved in 02-07.

## Self-Check: PASSED

- FOUND: vicmap_acquire/manifest.py (contains `_fsync_directory`, `ensure_ascii=False`)
- FOUND: tests/test_manifest.py
- FOUND commits: 0a1e061, 2deb271, c2b50d7, 643a4b7
- Full suite: `nix develop path:. -c python -m unittest discover -s tests -p 'test_*.py' -v` -> Ran 399 tests, OK

---
*Phase: 02-safe-geospatial-discovery*
*Completed: 2026-09-16*
