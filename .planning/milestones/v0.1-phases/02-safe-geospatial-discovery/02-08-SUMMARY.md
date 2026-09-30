---
phase: 02-safe-geospatial-discovery
plan: 08
subsystem: geospatial-discovery
tags: [extraction, aliasing, provenance, security, gap-closure, tdd]

# Dependency graph
requires:
  - phase: 02-safe-geospatial-discovery/02-03
    provides: extract_artifact's D-25/D-26 guard set, _reject_unsafe_member's resolved-destination computation, the MemberGuardRejectionTest fixture helpers this plan extends
  - phase: 02-safe-geospatial-discovery/02-07
    provides: the shipped vicmap.toml [extraction] ceilings (via read_mailbox.load_discovery_config) this plan's real-delivery oracle sources without a test-local override
provides:
  - "_validate_members' D-26 aliasing guard keyed on _reject_unsafe_member's resolved destination Path plus its case-folded form, closing the CR-01 destination-identity bypass (d/f.txt vs d//f.txt, a/b vs a/./b, case-only aliases)"
  - "extract_artifact's per-member output handle is now an exclusive create (os.open O_EXCL), making the filesystem the last oracle against any alias the pre-pass guard might miss"
  - "An independent provenance-integrity oracle (ProvenanceIntegrityTest) that recomputes every recorded member's byte count and SHA-256 from disk and asserts file-set equality, run unconditionally against the tracer fixture and, when present, against the real 46-member Order_OK0VUZ.zip delivery"
  - "Ordering-independence and zero/single-member regressions pinning the guard's behavior at its edges"
affects: [02-safe-geospatial-discovery/02-09]

# Actuals (#2632)
actuals:
  tokens: 3983
  tasks: 2
  commits: 4

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "A destination-identity aliasing guard derives its collision key from the already-computed resolved Path (and its case-folded string form) rather than from the archive-supplied name string, closing the exact axis a hand-written test using byte-identical names structurally cannot exercise"
    - "Exclusive-create output handles (os.open with O_EXCL) are the write-time filesystem-truth complement to a pre-pass guard, reusing manifest.py's _write_new_file_fsync idiom rather than inventing a second one"
    - "A provenance-integrity oracle test is written from the extraction result's own contract (every member's relative path, byte count, and SHA-256 matches disk) rather than from the guard's implementation, so it fails for any future defect that lets recorded provenance drift from disk regardless of mechanism"

key-files:
  created: []
  modified:
    - vicmap_acquire/extraction.py
    - tests/test_extraction.py

key-decisions:
  - "Rejected 02-REVIEW.md's suggested destination.exists() aliasing check: _validate_members is a pre-pass that runs to completion before any output handle opens, and extract_artifact creates temp_dir immediately beforehand and raises if it already exists -- so destination.exists() is False for every member and would have detected nothing. The resolved-Path and case-folded-string keys used instead work because they compare members against each other, not against a filesystem that is guaranteed empty at validation time."
  - "Kept both a pre-pass identity key (Task 1) and a write-time exclusive-create (Task 2) as deliberately separate, complementary guards rather than picking one: the pre-pass check is order-independent and catches nearly everything before any bytes are written, but the exclusive create is the filesystem's own truth and defends against any identity-key edge case (e.g. Unicode normalization forms) the two Python-level keys did not anticipate."
  - "Added the destination-identity aliasing test fixtures to the existing MemberGuardRejectionTest class rather than a new class, since they reuse its _member/_write_archive/_extract/_assert_nothing_written helpers verbatim and are conceptually one more guard in that same reject-before-write family."
  - "The provenance-integrity oracle recomputes strictly from the published run_directory via hashlib.sha256 and Path.rglob, never from ExtractionResult's own fields, mirroring the differential-oracle discipline tests/test_discovery_differential.py already applies to ogrinfo -- so it stays a check against reality rather than a check against the code's own bookkeeping."

requirements-completed: [GEO-01]

coverage:
  - id: D1
    description: "Two archive members with different literal names that resolve to one destination (path separators, dot segments, or letter case) are rejected as a single aliasing violation before any output handle opens, in either archive order, and the existing exact-duplicate-name case is unaffected"
    requirement: GEO-01
    verification:
      - kind: unit
        ref: "tests/test_extraction.py#MemberGuardRejectionTest.test_double_slash_path_alias_rejected"
        status: pass
      - kind: unit
        ref: "tests/test_extraction.py#MemberGuardRejectionTest.test_dot_segment_path_alias_rejected"
        status: pass
      - kind: unit
        ref: "tests/test_extraction.py#MemberGuardRejectionTest.test_case_alias_rejected"
        status: pass
      - kind: unit
        ref: "tests/test_extraction.py#MemberGuardRejectionTest.test_aliased_pair_rejected_when_colliding_name_appears_first"
        status: pass
      - kind: unit
        ref: "tests/test_extraction.py#MemberGuardRejectionTest.test_aliased_pair_rejected_when_colliding_name_appears_second"
        status: pass
      - kind: unit
        ref: "tests/test_extraction.py#MemberGuardRejectionTest.test_duplicate_member_name_rejected"
        status: pass
    human_judgment: false
  - id: D2
    description: "Recorded extraction provenance (byte count, SHA-256, and the set of non-directory paths) is independently checked against the published run directory's actual bytes for both the tracer fixture and the real 46-member delivery, and a destination claimed at write time fails its exclusive create instead of truncating already-hashed bytes"
    requirement: GEO-01
    verification:
      - kind: unit
        ref: "tests/test_extraction.py#WriteTimeGuardTest.test_preexisting_destination_file_fails_exclusive_create"
        status: pass
      - kind: integration
        ref: "tests/test_extraction.py#ProvenanceIntegrityTest.test_tracer_fixture_provenance_matches_disk"
        status: pass
      - kind: integration
        ref: "tests/test_extraction.py#ProvenanceIntegrityTest.test_real_delivery_provenance_matches_disk"
        status: pass
      - kind: unit
        ref: "tests/test_extraction.py#MemberAcceptanceTest.test_zero_member_archive_extracts_to_empty_result"
        status: pass
      - kind: unit
        ref: "tests/test_extraction.py#MemberAcceptanceTest.test_single_member_archive_extracts_normally"
        status: pass
    human_judgment: false

# Metrics
duration: 12min
completed: 2026-09-16
status: complete
---

# Phase 2 Plan 08: Extraction Destination-Identity Aliasing Guard Summary

**Closed the CR-01 extraction bypass by keying the D-26 aliasing guard on resolved destination identity instead of the raw archive-supplied name, and made the filesystem the final oracle with exclusive-create writes plus an independent disk-provenance check.**

## Performance

- **Duration:** 12 min
- **Started:** 2026-09-16T20:51:00Z
- **Completed:** 2026-09-16T21:02:54Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments
- `_validate_members` now rejects two archive members that resolve to the same on-disk destination (via `pathlib.resolve()` collapsing `//` and `.` segments) or the same case-folded destination string, whatever literal names the archive spells them with — closing the exact CR-01 reproduction (`d/f.txt` vs `d//f.txt`) where the shipped guard compared only the raw `ZipInfo.filename` string.
- Per-member guards (`_reject_unsafe_member`) still run first, so a traversal or symlink member fails with its own specific exception rather than being absorbed into the aliasing check.
- `extract_artifact`'s per-member output handle is now an exclusive create (`os.open(..., O_EXCL)`, mirroring `manifest.py`'s existing idiom), so a destination that already exists at write time raises `RunDirectoryWriteFailed` instead of silently truncating already-written, already-hashed bytes.
- A new independent provenance-integrity oracle recomputes every recorded member's length and SHA-256 directly from the published run directory and asserts the recorded non-directory path set equals the files actually on disk — proven against the tracer fixture unconditionally and against the real 46-member `Order_OK0VUZ.zip` delivery when present, doubling as the non-regression proof that the real delivery still extracts cleanly.
- Added ordering-independence and zero/single-member regressions pinning the guard's behavior at its edges.

## Task Commits

Each task followed the RED-GREEN TDD cycle and was committed atomically:

1. **Task 1 RED: destination-identity aliasing tests** - `6fd4e84` (test)
2. **Task 1 GREEN: key aliasing guard on resolved destination** - `4580a22` (feat)
3. **Task 2 RED: write-time exclusive-create + oracle tests** - `c024bdb` (test)
4. **Task 2 GREEN: exclusive-create output handles** - `7f93213` (feat)

No REFACTOR commit was needed for either task — both GREEN implementations were minimal and required no follow-up cleanup.

## Files Created/Modified
- `vicmap_acquire/extraction.py` - `_validate_members` keys D-26 aliasing on resolved `Path` plus `os.path.normcase(...).casefold()`; `extract_artifact`'s write loop uses an exclusive-create output handle
- `tests/test_extraction.py` - new path/dot-segment/case aliasing tests, ordering regressions, zero/single-member regressions, a write-time exclusive-create regression, and a new `ProvenanceIntegrityTest` class with tracer-fixture and real-delivery disk-provenance oracles

## Decisions Made
- Rejected `02-REVIEW.md`'s suggested `destination.exists()` aliasing check as a false-positive-free mechanism: `_validate_members` runs to completion before any output handle opens and `temp_dir` is freshly created immediately beforehand, so `destination.exists()` is `False` for every member in the same archive and would have caught nothing. Recorded this correction explicitly, per the plan's instruction, since `02-REVIEW.md`'s diagnosis of the defect was correct even though its proposed mechanism was not.
- Kept the pre-pass identity key (Task 1) and the write-time exclusive create (Task 2) as two deliberately separate, complementary guards rather than consolidating into one: the pre-pass catches the vast majority of cases before any bytes are written and is provably order-independent, while the exclusive create is the filesystem's own truth and defends against any identity-key edge case the two Python-level keys did not anticipate.
- Added the new aliasing fixtures to the existing `MemberGuardRejectionTest` class (reusing its helpers verbatim) rather than a new class, since they are conceptually one more member in that same reject-before-write guard family.

## Deviations from Plan

None - plan executed exactly as written. The two production-code changes were the ones the plan specified precisely (destination-Path/case-fold key in `_validate_members`; `os.open(O_EXCL)` in `extract_artifact`'s write loop), and every test the plan asked for was added.

## Issues Encountered

The write-time exclusive-create regression (`WriteTimeGuardTest`) needed one iteration: the first `unittest.mock.patch` `side_effect` signature required all three of `os.open`'s positional arguments, but `_fsync_directory` in `extraction.py` calls `os.open(directory, os.O_RDONLY)` with only two — this raised a `TypeError` that the outer catch-all mapped to `ArchiveUnreadable`, masking the intended `RunDirectoryWriteFailed` RED failure. Giving the mock's `mode` parameter a default value fixed it; the underlying production code was already correct, so this is a test-fixture-only fix and not tracked as a Rule 1-3 deviation against production code.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- GEO-01 is now closed end-to-end: `_validate_members` and `extract_artifact` both defend destination identity, and an independent oracle proves recorded provenance never drifts from disk, for both the tracer fixture and the real 46-member delivery.
- Verification gap 1 (CR-01) from `02-VERIFICATION.md` is resolved; no other extraction guard, ceiling, or failure type changed.
- Plan 02-09 (GEO-05) is unaffected by and does not depend on this plan's changes.

## Self-Check: PASSED

- FOUND: vicmap_acquire/extraction.py
- FOUND: tests/test_extraction.py
- FOUND: .planning/phases/02-safe-geospatial-discovery/02-08-SUMMARY.md
- FOUND commits: 6fd4e84, 4580a22, c024bdb, 7f93213
- Re-ran all acceptance criteria for both tasks: PASS
- Re-ran plan-level verification (`python -m unittest discover -s tests -p 'test_*.py' -v`): 390 tests, OK

---
*Phase: 02-safe-geospatial-discovery*
*Completed: 2026-09-16*
