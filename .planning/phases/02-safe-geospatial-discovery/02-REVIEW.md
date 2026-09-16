---
phase: 02-safe-geospatial-discovery
reviewed: 2026-09-16T21:26:36Z
depth: standard
files_reviewed: 8
files_reviewed_list:
  - vicmap_acquire/discovery.py
  - vicmap_acquire/extraction.py
  - vicmap_acquire/manifest.py
  - vicmap.toml
  - tests/test_discovery.py
  - tests/test_discovery_config.py
  - tests/test_extraction.py
  - tests/test_manifest.py
findings:
  critical: 0
  warning: 1
  info: 1
  total: 2
status: issues_found
---

# Phase 2: Code Review Report (incremental re-review after gap closure)

**Reviewed:** 2026-09-16T21:26:36Z
**Depth:** standard
**Files Reviewed:** 8
**Status:** issues_found

## Summary

This is a re-review of everything changed since commit `5d3a21e` (the commit the prior `02-REVIEW.md` was produced against): plans 02-07, 02-08, and 02-09 closing the gaps that review raised. All four prior findings (CR-01, CR-02, WR-01, WR-02) are **RESOLVED**, each with a targeted regression that fails against the pre-fix code and passes against the fix (verified by reading the fix and its accompanying test, and by live-reproducing the compression-ratio calibration numbers against both the checked-in fixture and the real 233 MB delivery). IN-01 (`naming.py`'s hand-transcribed keyword set) was out of this incremental scope's changed-file list and is untouched — carried forward unresolved for completeness, not re-audited this pass.

One new defect was found in the 02-08 hardening itself: the write-time exclusive-create guard added to close CR-01 (`os.open(destination, O_WRONLY|O_CREAT|O_EXCL, ...)` immediately followed by a compound `with zip_file.open(info, "r") as source, os.fdopen(descriptor, "wb") as target:`) leaks the raw file descriptor whenever `zip_file.open(info, "r")` raises — which it legitimately can, for a corrupt or adversarially malformed member (bad local-header compression method, header/CRC mismatch), squarely inside this module's own adversarial-input threat model. This is live-reproduced below (WR-03). It also contradicts the function's own `finally`-block comment, which claims "every other resource this function opens... is already scoped to a `with` block above and closes itself" — that claim is false for this specific ordering. Severity is Warning rather than Critical because the process is short-lived per invocation (no observed data corruption, security bypass, or crash), but it is a genuine regression introduced by the very fix meant to harden this path, so it belongs in this incremental review rather than being deferred.

One new Info-level observation is also recorded: the recalibrated `max_compression_ratio = 200` (02-07) clears the real delivery's measured worst-case per-member ratio (~139.24, independently re-measured this session) by only ~1.44x headroom — tighter than the fixture's ~1.6x headroom. The shipped regression test (`ShippedCeilingCalibrationTest`) will catch a future regression below the currently-measured worst case, but the margin itself is thin enough that a future delivery with one more-compressible member could reopen the exact WR-class hard-stop this recalibration was meant to close.

## Disposition of Prior Findings

### CR-01 (RESOLVED): Archive duplicate-member guard compares raw filenames, not resolved destinations

**Prior file/lines:** `vicmap_acquire/extraction.py` `_validate_members`

**Fix verified:** `_validate_members` (extraction.py:221-267) now keys the aliasing guard on `_reject_unsafe_member`'s *resolved* destination `Path`, plus a second `os.path.normcase(str(destination)).casefold()` key for case-only aliasing on case-insensitive filesystems. Both `d/f.txt` vs `d//f.txt` and `d/f.txt` vs `d/F.txt` are now rejected pre-write, in either archive order. Regressions added and read: `test_double_slash_path_alias_rejected`, `test_dot_segment_path_alias_rejected`, `test_aliased_pair_rejected_when_colliding_name_appears_{first,second}`, `test_case_alias_rejected` (`tests/test_extraction.py:269-323`) — all target the exact reproduction from the prior CR-01 report and would fail against the reverted (raw-filename) guard, per their own inline comments.

A complementary write-time hardening was also added (`os.open(..., O_EXCL)` per member, `tests/test_extraction.py::WriteTimeGuardTest`), making the filesystem the last oracle for any alias the pre-pass guard might still miss. This hardening itself introduces a new regression — see **WR-03** below — but the CR-01 defect as originally reported (the aliasing guard silently bypassed by path-alias members) is fully closed.

**Status: RESOLVED.**

### CR-02 (RESOLVED): `write_manifest` publishes `manifest.json` and its sidecar as two independent, non-atomic commits

**Prior file/lines:** `vicmap_acquire/manifest.py` `write_manifest`

**Fix verified:** `write_manifest` (manifest.py:201-256) now wraps the sidecar's `_write_new_file_fsync` call in its own `try/except OSError`, best-effort unlinking `manifest_path` before re-raising on sidecar failure. The unlink is provably scoped to a manifest this exact call created (reached only after the `O_EXCL` manifest create returned without raising). Regressions read and traced: `test_sidecar_pre_existing_leaves_no_manifest_and_directory_unchanged` (the literal CR-02 reproduction — sidecar pre-exists, manifest create succeeds, sidecar create fails, rollback removes the manifest, directory listing is unchanged before/after), `test_failed_sidecar_create_then_retry_succeeds_into_same_directory` (proves the previously-permanent stuck state is now retryable), `test_rollback_does_not_fire_on_pre_existing_complete_manifest` (proves the rollback path is never reached for a genuinely pre-existing manifest, via an `unlink` spy that raises `AssertionError` if called), and `test_rollback_unlink_failure_still_raises_manifest_write_failed` (a failing rollback unlink itself still surfaces as the closed `ManifestWriteFailed`, never a raw `OSError`). Traced the control flow by hand: there is no code path between the two `_write_new_file_fsync` calls, so a `manifest.json` create failure (e.g., a pre-existing manifest) can never reach the rollback branch, and only a sidecar-create failure can.

**Status: RESOLVED.**

### WR-01 (RESOLVED): `find_datasets` matches archive suffixes case-sensitively

**Prior file/lines:** `vicmap_acquire/discovery.py:35-43`, `:168`

**Fix verified:** `find_datasets` now does `_EXTENSION_DRIVERS.get(path.suffix.casefold())` (discovery.py:169) against a table whose keys are already lowercase; the docstring comment was updated to state the probe, not the table, is casefolded. Regressions read: `test_uppercase_geodatabase_extension_is_recognized` (renames the real extracted `VMADD.gdb` to `VMADD.GDB` and asserts it is still found and profiled) and `test_uppercase_unsupported_extension_raises_unsupported_format` (an uppercase `.SHP` now correctly raises `UnsupportedFormat`, not a generic `DeliveryEmpty`) — both tests' own comments state they fail at pre-02-07 HEAD.

**Status: RESOLVED.**

### WR-02 (RESOLVED): `manifest.json`'s directory entry is never fsynced

**Prior file/lines:** `vicmap_acquire/manifest.py`

**Fix verified:** A private `_fsync_directory` (manifest.py:171-198), copied to match `extraction.py`'s/`download.py`'s idiom exactly (swallows its own `OSError` on open/fsync/close), is now called once on `run_directory` after both files are confirmed written (manifest.py:253). Regressions read: `test_successful_write_fsyncs_run_directory_exactly_once` (spy assert-called-once-with `run_dir`), `test_rollback_path_never_calls_directory_fsync` (a failed/rolled-back call must never fsync), and `test_directory_fsync_failure_does_not_affect_successful_write` (a failing directory fsync must not change the outcome, distinguishing the directory's own non-`O_CREAT` open from the two file creates).

**Status: RESOLVED.**

### IN-01 (CARRIED FORWARD, UNCHANGED): `_RESERVED_KEYWORDS` in `naming.py` has no independent PostgreSQL oracle

`naming.py` and `test_naming.py` are not in this incremental review's file list and were not touched by 02-07/02-08/02-09. No new information; carried forward at Info severity, unresolved, exactly as previously reported.

## Warnings

### WR-03: The write-time exclusive-create guard added to close CR-01 leaks the destination file descriptor when `zip_file.open()` raises after `os.open()` succeeds

**File:** `vicmap_acquire/extraction.py:360-365` (the `os.open(...)` call and the following compound `with` statement)

**Issue:**

```python
descriptor = os.open(
    destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644
)
with zip_file.open(info, "r") as source, os.fdopen(
    descriptor, "wb"
) as target:
    ...
```

In a compound `with A() as a, B() as b:` statement, Python constructs and enters `A`'s context manager first, then constructs and enters `B`'s. Here `A` is `zip_file.open(info, "r")` and `B` is `os.fdopen(descriptor, "wb")`. If `zip_file.open(info, "r")` raises — which it legitimately can, for a member whose local file header declares an unsupported/mismatched compression method, or whose local header otherwise fails `zipfile`'s own consistency check against the central directory — the previously-opened raw descriptor from `os.open(destination, ...)` is never passed to `os.fdopen()` and is therefore never closed by anything in this function. The descriptor leaks for the remaining lifetime of the process, and an empty (0-byte) orphaned file is left at `destination` inside the `.tmp-` directory with no corresponding `ExtractedMember` entry.

Live-reproduced this session: a synthetic single-member zip with its local *and* central-directory compression-method fields patched to an unsupported value (`99`) raises `ArchiveUnreadable` as expected, but the process's open file descriptor count increases by one and does not decrease, and `run_root/ORD1/.tmp-.../a.bin` is left on disk as a 0-byte file:

```
raised: <class 'vicmap_acquire.extraction.ArchiveUnreadable'> archive_unreadable
fds before: 4 after: 5
/tmp/.../ORD1 dir
/tmp/.../ORD1/.tmp-20260101T000000Z dir
/tmp/.../ORD1/.tmp-20260101T000000Z/a.bin 0
```

This directly contradicts the function's own `finally`-block comment (extraction.py:407-417): "Every other resource this function opens (the zip archive, each output file) is already scoped to a `with` block above and closes itself" — for this exact ordering, the raw descriptor from `os.open()` is *not* scoped to a `with` block until `os.fdopen()` succeeds, and that call never happens if the sibling context manager's construction fails first.

No existing regression exercises this path: `tests/test_extraction.py::WriteTimeGuardTest::test_preexisting_destination_file_fails_exclusive_create` only tests the case where `os.open()` itself fails (`O_EXCL` collision) — it never exercises `os.open()` succeeding followed by `zip_file.open()` failing.

Severity is Warning rather than Critical: this is a per-invocation CLI script (`discover_order.py`), so the leaked descriptor and orphaned file do not survive past process exit, and no data corruption or security bypass results. It is nonetheless a genuine, live-reproduced regression introduced by the very hardening meant to close CR-01, and it would matter in any future context that calls `extract_artifact` more than once per process (already true of this codebase's own test suite, which calls it hundreds of times in a single `unittest` process).

**Fix:**

Reorder the compound `with` statement so the destination file descriptor's context manager is entered *first* — the `with` statement's guaranteed partial-entry cleanup then closes it correctly if the zip member's context manager subsequently fails to construct:

```python
with os.fdopen(descriptor, "wb") as target, zip_file.open(info, "r") as source:
    while True:
        chunk = source.read(1024 * 1024)
        ...
```

Re-run the reproduction above (patch the local + central directory compression-method fields to an unsupported value) as a regression, asserting the open file descriptor count returns to its pre-call value after `ArchiveUnreadable` is raised.

## Info

### IN-01: `_RESERVED_KEYWORDS` in naming.py is a hand-transcribed constant with no independent oracle (carried forward, unchanged — see Disposition above)

### IN-02: The recalibrated `max_compression_ratio = 200` clears the real delivery's worst-case ratio by only ~1.44x

**File:** `vicmap.toml:26`

**Issue:** Re-measured independently this session with a bare `zipfile` walk (never through `vicmap_acquire.extraction`, matching `ShippedCeilingCalibrationTest`'s own discipline):

- `tests/fixtures/Order_TRACER1.zip` worst-case per-member ratio: ~122.67 (headroom to 200: ~1.63x)
- `artifacts/Order_OK0VUZ.zip` (the real 233 MB delivery) worst-case per-member ratio: ~139.24 (headroom to 200: ~1.44x)

Both are comfortably above 1.0 and both are guarded by `ShippedCeilingCalibrationTest`, which will go red the moment a future delivery's worst-case ratio regresses past whatever is shipped — so this is not an unguarded regression risk. It is, however, a thinner margin than it might appear: the worst-case members driving this ratio are the tiny `.gdbtablx`/`.spx`/`.atx` GDB index files (4–5 KB each, compressing to 35–90 bytes), and a future Vicmap delivery tool version producing a slightly more redundant index file could plausibly push the real worst case past 200 again, reproducing the exact "known issue" this recalibration was meant to close. `max_member_bytes`/`max_total_bytes` remain the actual bound on how much any single compressible member can inflate before extraction aborts regardless of ratio, so this is not a security gap — only a note that the calibration, while now correct, is not calibrated with a large safety margin.

**Fix:** No action required now; the existing `ShippedCeilingCalibrationTest` already catches a regression. If a future delivery trips this ceiling again, consider widening the margin further (e.g., 2–3x the currently-measured worst case) rather than the minimum value that merely clears today's numbers, since GDB index file compressibility is a Vicmap/GDAL implementation detail this project does not control.

---

_Reviewed: 2026-09-16T21:26:36Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
