---
phase: 02-safe-geospatial-discovery
plan: 03
subsystem: geospatial-discovery
tags: [zipfile, fail-closed, extraction, tdd]

# Dependency graph
requires:
  - phase: 02-safe-geospatial-discovery/02-01
    provides: ExtractionPolicy/ExtractedMember/ExtractionResult fixed field-name contracts and the initial extract_artifact/verify_artifact implementation this plan hardens
provides:
  - Complete D-26 reject-before-write guard chain, including the archive-wide duplicate-member-name check 02-01 had not yet added
  - A single top-level exception wrap on extract_artifact mirroring download_artifact exactly (ArchiveFailure passthrough, OSError -> RunDirectoryWriteFailed, catch-all Exception -> ArchiveUnreadable), closing a gap where a corrupt central directory could leak raw zipfile text
  - Per-chunk write-length verification and per-file fsync before close in the streaming loop
  - Full D-27 member accounting: every archive member (including directory entries) recorded in ExtractionResult, sorted by relative_path
  - verify_artifact correctly raising ArtifactChecksumMismatch (not ArchiveUnreadable) for an absent artifact file
  - 29 adversarial regressions in tests/test_extraction.py covering every guard, real-byte ceiling enforcement, atomic publication, and the real Order_TRACER1.zip fixture
affects: [02-04-discovery-hardening, 02-05-naming-hardening, 02-06-manifest-finalization]

# Actuals (#2632)
actuals:
  tokens: 9042
  tasks: 2
  commits: 1

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Total-function-with-catch-all exception wrap on extract_artifact, mirroring download_artifact's own except <TypedFailure> / except OSError / finally shape exactly, now including a catch-all except Exception for anything neither narrow catch already converted"
    - "_validate_members(infolist, destination_root, policy) as one archive-wide validation pass -- member-count ceiling, then per-member path/mode/encryption guards, then duplicate-name detection -- completing entirely before the write phase begins"
    - "Directory entries recorded as zero-byte ExtractedMember rows (sha256 of empty bytes) so D-27's 'every member accounted for' claim covers zip structural entries, not just file content"

key-files:
  created:
    - tests/test_extraction.py
  modified:
    - vicmap_acquire/extraction.py

key-decisions:
  - "Task 1 and Task 2 are committed together as one commit (process deviation, same precedent as 02-02's SUMMARY): both tasks modify the same extract_artifact function body -- the validation phase and the write/publish phase share one exception wrap -- and 02-01 had already left extraction.py substantially complete, so forcing an artificial Task-1-only intermediate commit would misrepresent the actual incremental history rather than reflect it."
  - "Fixed verify_artifact's absent-file case to raise ArtifactChecksumMismatch instead of ArchiveUnreadable (Rule 1 bug fix) -- the plan's Task 2 behavior bullet is explicit that a missing artifact file is one of verify_artifact's three ArtifactChecksumMismatch paths, and the pre-existing 02-01 code raised the wrong typed failure for it."
  - "Documented, rather than literally implemented, the plan's 'member declaring a small file_size that decompresses beyond max_member_bytes' acceptance criterion as written: verified directly against CPython 3.14's zipfile source (ZipExtFile._read1's `data = data[:self._left]`) that decompressed output is architecturally capped at ZipInfo.file_size through the public ZipFile.open()/.read() API, regardless of CRC-32 or compress_size manipulation, so a 'declared small, decompresses to more' fixture cannot be constructed through that API at all. The test suite instead proves the equivalent, constructible property -- a member whose on-disk compressed footprint is tiny but whose real, accurately-declared decompressed size legitimately exceeds the ceiling still trips it from bytes actually streamed, never from a metadata short-circuit."
  - "Encrypted-member and small-file_size-lie fixtures cannot be built via ZipFile.writestr()/open(mode='w') -- both unconditionally recompute flag_bits (and file_size/CRC) at write time (verified this session). The encrypted-member test instead patches the raw archive bytes' general-purpose flag field directly after construction."

requirements-completed: [GEO-01]

coverage:
  - id: D1
    description: "Every D-26 reject-before-write guard (leading slash/backslash, .. component, colon/drive component, resolved-path escape, Unix symlink, non-regular member, duplicate name, encrypted member, member-count ceiling) has a named adversarial test asserting the exact exception type, and none of them ever open an output handle before the whole member list validates"
    requirement: GEO-01
    verification:
      - kind: unit
        ref: "tests/test_extraction.py::MemberGuardRejectionTest (13 cases)"
        status: pass
      - kind: unit
        ref: "tests/test_extraction.py::MemberGuardRejectionTest::test_extractall_and_extract_are_never_called"
        status: pass
    human_judgment: false
  - id: D2
    description: "create_system-gated mode-bit check is scoped correctly: a Windows-authored (create_system=0) member carrying the same external_attr bit pattern as a Unix symlink is accepted on its path, not misjudged on borrowed Unix mode semantics"
    requirement: GEO-01
    verification:
      - kind: unit
        ref: "tests/test_extraction.py::MemberAcceptanceTest::test_non_unix_create_system_with_symlink_bit_pattern_is_accepted_on_path"
        status: pass
    human_judgment: false
  - id: D3
    description: "Byte ceilings (per-member, cumulative, compression ratio) are measured against bytes actually produced by decompression as they stream, not a declared-metadata shortcut, and a zero-compress_size member never divides by zero"
    requirement: GEO-01
    verification:
      - kind: unit
        ref: "tests/test_extraction.py::CeilingEnforcementTest (4 cases)"
        status: pass
    human_judgment: false
  - id: D4
    description: "The run directory has exactly one atomic commit point (os.rename); a ceiling breach leaves the .tmp- directory inspectable and no final run directory, and a pre-existing final run directory is never overwritten"
    requirement: GEO-01
    verification:
      - kind: unit
        ref: "tests/test_extraction.py::CeilingEnforcementTest (three ceiling cases each assert _assert_run_not_published)"
        status: pass
      - kind: unit
        ref: "tests/test_extraction.py::PublicationTest::test_existing_final_directory_is_never_overwritten"
        status: pass
    human_judgment: false
  - id: D5
    description: "verify_artifact raises ArtifactChecksumMismatch (never ArchiveUnreadable) for a flipped byte, a correct digest with wrong byte count, and an absent file, and never constructs zipfile.ZipFile in any of those paths"
    requirement: GEO-01
    verification:
      - kind: unit
        ref: "tests/test_extraction.py::VerifyArtifactTest (4 cases, each asserting zip_ctor.assert_not_called())"
        status: pass
    human_judgment: false
  - id: D6
    description: "Every member of the real delivered archive is accounted for with path, byte count, and SHA-256, including both non-geospatial companion files, and totals reconcile"
    requirement: GEO-01
    verification:
      - kind: unit
        ref: "tests/test_extraction.py::RealFixtureAccountingTest::test_every_member_of_the_real_delivery_is_accounted_for"
        status: pass
    human_judgment: false

duration: ~50min
completed: 2026-09-16
status: complete
---

# Phase 2 Plan 3: Extraction Hardening Summary

**Completed the D-26 fail-closed guard chain in `vicmap_acquire/extraction.py` -- archive-wide duplicate-name detection, a single `download_artifact`-style exception wrap, per-chunk write verification with per-file fsync, full D-27 member accounting (including directory entries and a deterministic sort), and a `verify_artifact` bug fix -- backed by 29 new adversarial regressions.**

## Performance

- **Duration:** ~50 min
- **Started:** 2026-09-16 (session start)
- **Completed:** 2026-09-16
- **Tasks:** 2 (both `tdd="true"`, committed together -- see Deviations)
- **Files modified:** 2 (1 created, 1 modified)

## Accomplishments

- `_validate_members(infolist, destination_root, policy)` now runs the complete archive-wide validation pass -- member-count ceiling, then every member's path/mode/encryption checks, then the new duplicate-member-name guard (D-26's hardlink-style aliasing closure) -- entirely before the write phase begins
- `extract_artifact`'s exception handling is now one top-level wrap mirroring `download_artifact` exactly: its own typed failures pass through, any other `OSError` becomes `RunDirectoryWriteFailed`, and a catch-all `except Exception` becomes `ArchiveUnreadable` -- closing a real gap where a `zipfile.BadZipFile` raised from `infolist()` (a corrupt central directory) could previously escape as raw, uncaught library text
- The per-member streaming loop now verifies `target.write(chunk)` returned the full chunk length (raising `RunDirectoryWriteFailed` on a short write) and calls `target.flush()` + `os.fsync(target.fileno())` on every extracted file before it closes
- `ExtractionResult.members` now includes directory entries as zero-byte members (SHA-256 of empty bytes) and is sorted by `relative_path` for deterministic, code-point ordering, closing the D-27 "every member accounted for" gap
- `verify_artifact` now raises `ArtifactChecksumMismatch` (previously the wrong `ArchiveUnreadable`) for an absent artifact file, matching this plan's explicit behavior bullet
- `tests/test_extraction.py`: 29 new tests in six classes (`MemberGuardRejectionTest`, `MemberAcceptanceTest`, `CeilingEnforcementTest`, `PublicationTest`, `VerifyArtifactTest`, `RealFixtureAccountingTest`), built on a `_build_archive`/`_member` fixture helper in `tests/test_download.py`'s explicit-`ZipInfo` style

## Task Commits

Both tasks are committed together in one commit (see Deviations for why a clean Task-1-only intermediate was not attempted):

1. **Task 1 + Task 2: Complete the D-26 guard chain, real-byte ceilings, atomic publication, and full member accounting** - `f643110` (feat)

**Plan metadata:** (this commit, recorded after SUMMARY.md is written)

_Both tasks carry `tdd="true"`; tests were authored and iterated to green alongside the implementation, matching 02-02's precedent for tightly-coupled same-file changes rather than separate RED/GREEN/REFACTOR commits._

## Files Created/Modified

- `vicmap_acquire/extraction.py` - `_validate_members`, unified exception wrap, write-length/fsync, directory-entry accounting, sorted members, `verify_artifact` fix
- `tests/test_extraction.py` - 29 adversarial regressions (new file)

## Decisions Made

- **Combined commit (process deviation).** Task 1 and Task 2 both modify the same `extract_artifact` function body -- the validation phase and the write/publish phase share one exception wrap -- and 02-01 had already left `extraction.py` substantially complete (not a greenfield two-phase build). Splitting into a genuinely independent Task-1-only intermediate commit would require an artificial reconstruction that does not correspond to real incremental development, exactly the tension 02-02's SUMMARY already documented for this same codebase. Both tasks' `<verify>` commands were run against the final state (29/29 `tests.test_extraction`, full suite 271/271) and both are recorded in this SUMMARY's coverage block.
- **`verify_artifact` absent-file fix (Rule 1 bug).** The pre-existing 02-01 code raised `ArchiveUnreadable` for a missing artifact file; this plan's Task 2 behavior bullet explicitly lists "a missing artifact file" as one of `verify_artifact`'s three `ArtifactChecksumMismatch` paths. Fixed to match: a missing file cannot match a supplied digest either.
- **The "declares a small `file_size`, decompresses beyond it" acceptance criterion cannot be constructed through Python's public `zipfile` reading API.** Verified directly against CPython 3.14's `zipfile.py` source: `ZipExtFile._read1` truncates all decompressed output to `zinfo.file_size` (`data = data[:self._left]`) regardless of how `compress_size` or CRC-32 are crafted, so the total bytes a caller can ever receive from `ZipFile.open().read()` is architecturally capped at the declared value -- there is no way to make real streamed bytes exceed it. The tests instead prove the equivalent, constructible property: a member whose on-disk compressed footprint is tiny but whose real, *accurately declared* decompressed size legitimately exceeds the ceiling still trips it from bytes measured as they stream, never from a metadata short-circuit on `info.file_size`. Full reasoning is documented in `tests/test_extraction.py`'s module docstring.
- **Encrypted-member fixtures require raw byte patching, not `ZipInfo.flag_bits`.** Verified this session that `ZipFile.writestr()` and `ZipFile.open(info, mode="w")` both unconditionally recompute `flag_bits` at write time, discarding a pre-set encryption bit. `tests/test_extraction.py::_patch_general_purpose_flag_bit` patches the on-disk general-purpose flag field directly after construction to build a genuinely adversarial encrypted-member fixture.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] `verify_artifact` raised the wrong exception for an absent artifact file**
- **Found during:** Task 2, reading the plan's explicit `verify_artifact` behavior bullet against 02-01's existing implementation
- **Issue:** The pre-existing code caught `OSError` (including `FileNotFoundError`) around the artifact read and raised `ArchiveUnreadable`, contradicting the plan's explicit requirement that a missing artifact file is one of `verify_artifact`'s three `ArtifactChecksumMismatch` cases
- **Fix:** Changed the `except OSError:` clause in `verify_artifact` to raise `ArtifactChecksumMismatch` instead
- **Files modified:** `vicmap_acquire/extraction.py`
- **Verification:** `tests/test_extraction.py::VerifyArtifactTest::test_absent_artifact_file_raises_checksum_mismatch`
- **Committed in:** `f643110`

**2. [Process] Combined Task 1 and Task 2 into one commit**
- **Found during:** Preparing to commit
- **Issue:** Both tasks' actions are described against the same `extract_artifact` function; the validation-phase and write-phase changes were made in one continuous restructuring pass (the function's single exception wrap spans both), and 02-01 had already left the file substantially complete rather than empty, unlike a typical greenfield two-task split
- **Fix:** Committed both tasks together with a commit message itemizing each task's changes separately, and ran both tasks' `<verify>` commands against the final state, recording both results here rather than fabricating an artificial intermediate commit
- **Files modified:** none beyond the plan's own two files -- this was a commit-sequencing decision, not a code change
- **Verification:** `nix develop path:. -c python -m unittest tests.test_extraction -v` (29 tests, `OK`) and `nix develop path:. -c python -m unittest tests.test_discovery_tracer -v` (part of the full suite run below)
- **Committed in:** `f643110`

**3. [Documentation] "Declares a small `file_size`" acceptance criterion adapted to a constructible equivalent**
- **Found during:** Task 2, attempting to construct the literal fixture the acceptance criterion describes
- **Issue:** Empirically verified (reading CPython 3.14's `zipfile.py` source and testing directly) that `ZipExtFile.read()` architecturally caps total decompressed output at `zinfo.file_size` for any archive, so a member whose declared `file_size` understates its real decompressed size cannot be constructed through the public `ZipFile.open()` API -- any attempt either truncates the real output to the declared size or fails CRC-32 validation, never exceeds it
- **Fix:** Wrote the closest constructible equivalent instead -- a member whose on-disk *compressed* footprint is tiny (high genuine ratio) but whose real, accurately declared decompressed size legitimately exceeds `max_member_bytes`, proving the ceiling trips from bytes measured as they stream rather than from any `info.file_size`/`info.compress_size` shortcut. Documented the finding in the test module's docstring for future readers
- **Files modified:** `tests/test_extraction.py`
- **Verification:** `tests/test_extraction.py::CeilingEnforcementTest::test_per_member_ceiling_trips_on_real_streamed_bytes`
- **Committed in:** `f643110`

---

**Total deviations:** 3 (1 Rule 1 bug fix, 1 process/commit-sequencing decision, 1 documented test-construction finding)
**Impact on plan:** The bug fix was necessary for correctness against the plan's own explicit wording. The commit-sequencing decision reflects the actual code structure honestly rather than fabricating history. The test-construction finding is a genuine, verified property of CPython's `zipfile` module, not a shortcut taken to avoid work -- the implemented ceiling logic still never references `info.file_size` for its decision, matching the plan's underlying intent even though the literal fixture as worded is unconstructable. No scope creep -- `vicmap_acquire/discovery.py`, `vicmap_acquire/naming.py`, `read_mailbox.py`, and `vicmap.toml` (sibling-plan files) were not touched.

## Issues Encountered

None beyond the deviations documented above.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- `ExtractionPolicy`/`ExtractedMember`/`ExtractionResult` field names are unchanged from the 02-01/02-02 contract -- 02-04 (discovery hardening) and 02-05 (naming hardening) can proceed against the same fields as planned.
- The plan's flagged planner assumption (EDGE-02-01, "GEO-01's real edge surface is fully covered by this plan's explicit guard and ceiling truths") held: no extraction edge was found during implementation that fell outside the `must_haves.truths` list in the plan's frontmatter.
- Full suite green: `nix develop path:. -c python -m unittest discover -s tests -p 'test_*.py' -v` reports 271 tests, `OK` (242 baseline + 29 new, zero regressions).
- No blockers for 02-04 or 02-05.

---
*Phase: 02-safe-geospatial-discovery*
*Completed: 2026-09-16*

## Self-Check: PASSED

Both key files found on disk (`vicmap_acquire/extraction.py`, `tests/test_extraction.py`).
Referenced commit `f643110` found in `git log`. Full suite green: 271 tests, `OK`
(242 baseline + 29 new).
