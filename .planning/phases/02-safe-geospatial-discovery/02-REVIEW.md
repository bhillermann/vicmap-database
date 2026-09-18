---
phase: 02-safe-geospatial-discovery
reviewed: 2026-09-18T02:30:00Z
depth: standard
files_reviewed: 2
files_reviewed_list:
  - vicmap_acquire/extraction.py
  - tests/test_extraction.py
findings:
  critical: 0
  warning: 0
  info: 2
  total: 2
status: issues_found
---

# Phase 2: Code Review Report (incremental re-review of WR-03 fix)

**Reviewed:** 2026-09-18T02:30:00Z
**Depth:** standard
**Files Reviewed:** 2
**Status:** issues_found

## Summary

This is a re-review scoped to what changed since the prior `02-REVIEW.md` (commit
`679b07c`): commit `d6b0754`, which was supposed to fix WR-03 (the file-descriptor
leak in `extract_artifact`'s compound `with` statement when `zip_file.open()`
raises after `os.open(..., O_EXCL)` has already succeeded) and add a regression
test for it.

**WR-03 is verified RESOLVED.** The diff against `679b07c` touches exactly the
compound `with` statement identified in the prior report — reordering
`with zip_file.open(info, "r") as source, os.fdopen(descriptor, "wb") as target:`
to `with os.fdopen(descriptor, "wb") as target, zip_file.open(info, "r") as source:`
— plus an explanatory inline comment and one new test
(`WriteTimeGuardTest.test_fd_not_leaked_when_zip_open_raises_after_exclusive_create`)
with its supporting `_patch_compression_method` fixture helper. No other lines in
either file changed. This was independently confirmed three ways this session,
not just by reading the fix:

1. **Live reproduction against the fixed code**, outside the test suite: a
   synthetic single-member zip with both the local file header's and central
   directory record's compression-method field patched to an unsupported value
   (99, unreachable through any public `zipfile` writer API) was extracted
   through `extraction.extract_artifact` directly. Open file descriptor count
   (`/proc/<pid>/fd`) was identical before the call and after `ArchiveUnreadable`
   was raised (`before 4 after 4`).
2. **Full test suite run**, `python3 -m unittest discover -s tests`: 400 tests,
   OK, matching the fix report's claimed count.
3. **Targeted module run**, `python3 -m unittest tests.test_extraction -v`: 40
   tests, OK, including the new regression test passing.

No new defect was introduced by commit `d6b0754` itself. The reordering is a
pure context-manager entry-order correction: `os.fdopen(descriptor, "wb")` is
constructed from an already-valid descriptor (`os.open` succeeded moments
earlier under the same lock of control flow), so its own construction cannot
plausibly fail in a way that would re-leak the descriptor, and no other code
path, exception type, or control-flow branch changed. The new test is
appropriately scoped (`@unittest.skipUnless(Path("/proc/self/fd").is_dir(), ...)`
for portability) and is a real regression test, not a tautology — the fix
report's own verification log shows it failing (`AssertionError: 5 != 4`)
against the pre-fix ordering and passing against the fix, which this review
independently re-confirmed via `git show <pre-fix commit>` diffing.

Two prior Info findings were out of this incremental review's scope (neither
`naming.py` nor `vicmap.toml` changed in commit `d6b0754`) and are carried
forward verbatim, unresolved, below.

## Disposition of Prior Findings

### WR-03 (RESOLVED): Write-time exclusive-create guard leaked the destination file descriptor when `zip_file.open()` raised after `os.open()` succeeded

**Prior file/lines:** `vicmap_acquire/extraction.py:360-365` (pre-fix, at commit `679b07c`)

**Fix verified:** `extract_artifact`'s compound `with` statement (now
`vicmap_acquire/extraction.py:373-375`) enters `os.fdopen(descriptor, "wb")`
first and `zip_file.open(info, "r")` second — the reverse of the pre-fix
ordering. Python's compound `with A() as a, B() as b:` statement enters `A`
before constructing `B`; if `B`'s construction then raises, the `with`
statement's own guaranteed partial-entry cleanup exits `A`. With the fix,
`A` is the already-open descriptor's wrapper, so a `zip_file.open()` failure
(e.g., a member declaring an unsupported/malformed compression method) now
correctly closes the descriptor instead of leaking it. An inline comment was
added directly above the statement recording the WR-03 rationale, which
matches the actual code exactly (verified by reading, not just the comment's
own claim).

Regression added and independently re-run this session:
`WriteTimeGuardTest.test_fd_not_leaked_when_zip_open_raises_after_exclusive_create`
(`tests/test_extraction.py:584-615`), using a new `_patch_compression_method`
helper (`tests/test_extraction.py:123-145`) that patches both the local file
header and central directory record's compression-method field to an
unsupported value (99) directly in the raw archive bytes, since no public
`zipfile` writer API can construct such a member. The test asserts the
process's `/proc/<pid>/fd` count is identical before the call and after
`ArchiveUnreadable` is raised, and is skipped on platforms without `/proc`.

Live-reproduced independently this session (not merely re-reading the fix
report's claim): extracting the same 99-method fixture through the fixed
`extract_artifact` leaves the open-fd count unchanged (`before 4 after 4`).
Full suite (`python3 -m unittest discover -s tests`) and the module alone
(`python3 -m unittest tests.test_extraction -v`) both pass in full (400 and 40
tests respectively, no failures, no unexpected skips).

**Status: RESOLVED.**

### IN-01 (CARRIED FORWARD, UNCHANGED): `_RESERVED_KEYWORDS` in `naming.py` has no independent PostgreSQL oracle

`naming.py` and `tests/test_naming.py` are not in this incremental review's
file list (`vicmap_acquire/extraction.py`, `tests/test_extraction.py` only)
and were not touched by commit `d6b0754`. Not re-audited this pass. Carried
forward verbatim at Info severity, unresolved, exactly as previously
reported: the hand-transcribed reserved-keyword set has no independent
oracle verifying it against PostgreSQL's actual reserved-word list, so a
transcription error (a missing or extra keyword) would not be caught by any
existing test, since the tests were written against the same hand-transcribed
list they are meant to check.

### IN-02 (CARRIED FORWARD, UNCHANGED): The recalibrated `max_compression_ratio = 200` clears the real delivery's worst-case ratio by only ~1.44x

`vicmap.toml` is not in this incremental review's file list and was not
touched by commit `d6b0754`. Not re-audited this pass. Carried forward
verbatim at Info severity, unresolved, exactly as previously reported:
independently re-measured in the prior review with a bare `zipfile` walk
(never through `vicmap_acquire.extraction`), `tests/fixtures/Order_TRACER1.zip`'s
worst-case per-member compression ratio is ~122.67 (headroom to 200: ~1.63x)
and the real 233 MB delivery `artifacts/Order_OK0VUZ.zip`'s worst case is
~139.24 (headroom to 200: ~1.44x). Both are guarded by the shipped
`ShippedCeilingCalibrationTest`, so this is not an unguarded regression risk,
but the margin is thin: the worst-case members driving this ratio are tiny
GDB index files (`.gdbtablx`/`.spx`/`.atx`, 4-5 KB each, compressing to
35-90 bytes), and a future Vicmap delivery tool version producing a slightly
more redundant index file could plausibly push the real worst case past 200
again. `max_member_bytes`/`max_total_bytes` remain the actual bound on total
inflation regardless of ratio, so this is not a security gap — only a note
that the calibration, while correct, has a thin safety margin. No action
required now; if a future delivery trips this ceiling again, consider
widening the margin further (e.g., 2-3x the currently-measured worst case)
rather than the minimum value that merely clears today's numbers.

## Narrative Findings (AI reviewer)

No new Critical or Warning findings were introduced by commit `d6b0754`. The
change is minimal (a two-line reorder plus a comment and a new test), and
line-by-line comparison against the pre-fix version at commit `679b07c`
confirms no other code in either file was touched.

One residual observation, not risen to Info severity because it does not
represent a defect: the fix leaves a 0-byte orphaned file at `destination`
inside the `.tmp-` directory when `zip_file.open()` raises after
`os.open(..., O_EXCL)` succeeds (the descriptor's file object is now closed
correctly, but the already-created file itself is not removed). This is
consistent with, and required by, this module's own documented D-25
contract ("a guard trip during extraction leaves the private `.tmp-`
directory behind for inspection -- nothing is auto-deleted") and was already
true before the WR-03 fix; the fix only changes whether the *descriptor*
leaks, not whether the on-disk 0-byte artifact remains. No action needed.

## Info

### IN-01: `_RESERVED_KEYWORDS` in naming.py is a hand-transcribed constant with no independent oracle (carried forward, unchanged — see Disposition above)

### IN-02: The recalibrated `max_compression_ratio = 200` clears the real delivery's worst-case ratio by only ~1.44x (carried forward, unchanged — see Disposition above)

---

_Reviewed: 2026-09-18T02:30:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
