---
phase: 02-safe-geospatial-discovery
fixed_at: 2026-09-18T02:11:04Z
review_path: .planning/phases/02-safe-geospatial-discovery/02-REVIEW.md
iteration: 1
findings_in_scope: 2
fixed: 1
skipped: 1
status: partial
---

# Phase 2: Code Review Fix Report

**Fixed at:** 2026-09-18T02:11:04Z
**Source review:** .planning/phases/02-safe-geospatial-discovery/02-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope: 2 (`fix_scope: all` -- both carried-forward Info findings
  IN-01 and IN-02. WR-03 is already marked RESOLVED in the source review's
  "Disposition of Prior Findings" section and was correctly excluded from
  scope, not re-fixed.)
- Fixed: 1
- Skipped: 1 (by design, per the review's own recommendation -- see below)

**Verification environment:** Fixed in an isolated git worktree
(`.claude/worktrees/rf-02-233001-1789697335`, branch `gsd-reviewfix/02-233001`),
fast-forwarded onto `main` (`b6d3165..835ea13`) after the commit below, then
the worktree and temp branch were removed. Both the intermediate full-suite
run inside the worktree and a final full-suite run in the main checkout
(after fast-forward) are reported below; the numbers are reproducible from
the tree you are currently looking at (`main`, commit `835ea13`).

## Fixed Issues

### IN-01: `_RESERVED_KEYWORDS` in naming.py is a hand-transcribed constant with no independent oracle

**Files modified:** `tests/test_naming.py`
**Commit:** `835ea13`
**Applied fix:** Added `PostgresKeywordOracleTest`, a new test class in
`tests/test_naming.py`, implementing the independent-oracle fix the finding
called for -- not another hand-written assertion against the same
transcribed list (per the differential-oracle-testing project convention:
hand-written tests share the code's blind spot).

The test connects to a live PostgreSQL server (using `psycopg` if
importable, falling back to `psycopg2`; DSN from the
`VICMAP_TEST_POSTGRES_DSN` environment variable if set, else a local
`dbname=postgres` default with a 2-second connect timeout), queries
`SELECT word, catcode FROM pg_get_keywords()`, and asserts that the set of
words with `catcode` in `('R', 'T')` -- `RESERVED_KEYWORD` and
`TYPE_FUNC_NAME_KEYWORD`, the server's own two blocking categories,
corresponding exactly to the "reserved" and "reserved (can be function or
type)" Appendix C categories `naming.py`'s own comment cites -- is equal to
`naming_module._RESERVED_KEYWORDS`. This is a real independent oracle: the
server's `catcode` values are generated at build time from its own grammar
tables (`src/include/parser/kwlist.h`), not re-typed from the documentation
page a second time.

**No new hard dependency was added.** Both `psycopg` and `psycopg2` are
imported inside a `try`/`except ImportError`, and the test calls
`self.skipTest(...)` (not a failure) if neither is importable, or if
connecting raises any exception (no server reachable). This repo has no
`requirements*.txt` or `pyproject.toml` dependency list to modify, and none
was added -- the test is opportunistic only.

**Applied constraint check (per this task's explicit instructions):**
"the test suite must pass with no network and no required live database."
In this environment, neither `psycopg` nor `psycopg2` is importable and no
`psql`/`pg_config` is present, so the test exercises exactly the no-driver
skip path (verified below) rather than the live-comparison path. The
live-comparison path (connecting to a real server and diffing
`pg_get_keywords()`) was written correctly to the best of available
PostgreSQL documentation knowledge but could not be executed end-to-end in
this environment, since no PostgreSQL server or driver is available here to
connect to.

**Verification performed:**
- Re-read the modified section of `tests/test_naming.py` to confirm the new
  class and imports are present and the surrounding tests are intact
  (Tier 1).
- `python3 -c "import ast; ast.parse(open('tests/test_naming.py').read())"`
  -- syntax-valid (Tier 2).
- `python3 -m unittest tests.test_naming -v`: **41 tests, OK, skipped=1** --
  the new `test_reserved_keywords_match_live_server_pg_get_keywords` skipped
  with reason `"no PostgreSQL driver (psycopg or psycopg2) installed -- IN-01
  oracle check skipped, not failed"`, confirming the skip-clean behavior
  required by this task's constraints. All 40 pre-existing tests in this
  module still pass.
- `python3 -m unittest discover -s tests` (full suite):
  - Before this change, in the worktree: **400 tests, OK, skipped=3**
  - After this change, in the worktree: **401 tests, OK, skipped=4** (the
    one new skip is the oracle test's clean no-driver skip; no other skip
    count changed, no failures introduced)
  - After fast-forward, re-run once more in the main checkout on `main`
    (commit `835ea13`): **401 tests, OK, skipped=1** (the skip count for
    unrelated, environment-dependent fixtures varies run to run in this
    repo -- e.g. a live-delivery integration test reports an internal
    diagnostic event and is not counted as a failure -- but the oracle
    test's own skip/pass behavior and the overall `OK` result are
    consistent across all three runs)

This finding's fix is a new test addition (an independent verification
mechanism), not a change to any conditional/algorithmic logic in shipped
code, so it does not fall under the "logic bug -- requires human
verification" caveat in the verification strategy; standard `"fixed"`
status applies.

## Skipped Issues

### IN-02: The recalibrated `max_compression_ratio = 200` clears the real delivery's worst-case ratio by only ~1.44x

**File:** `vicmap.toml:26`
**Reason:** Skipped by design, per the review's own explicit disposition.
The review states this finding is "not a security gap -- only a note that
the calibration, while correct, has a thin safety margin," is already
guarded by the shipped `ShippedCeilingCalibrationTest`, and concludes "No
action required now; if a future delivery trips this ceiling again,
consider widening the margin further ... rather than the minimum value that
merely clears today's numbers." Per this task's explicit instructions, a
finding whose own text says no action is required now should not be
speculatively "fixed" by widening the ceiling just to close it -- doing so
would trade a documented, tested, deliberately-calibrated value for an
arbitrary one with no new measurement behind it. Re-read `vicmap.toml:21-26`
to confirm the current value (`max_compression_ratio = 200`,
`max_member_bytes = 4294967296`, `max_total_bytes = 10737418240`, both
byte-count bounds unchanged and still the actual bound on total inflation
regardless of ratio) before deciding to skip; no code or config was
changed for this finding.
**Original issue:** Independently re-measured with a bare `zipfile` walk,
`tests/fixtures/Order_TRACER1.zip`'s worst-case per-member compression
ratio is ~122.67 (headroom to 200: ~1.63x) and the real 233 MB delivery
`artifacts/Order_OK0VUZ.zip`'s worst case is ~139.24 (headroom to 200:
~1.44x). Both are guarded by the shipped `ShippedCeilingCalibrationTest`.
The worst-case members driving this ratio are tiny GDB index files
(`.gdbtablx`/`.spx`/`.atx`, 4-5 KB each, compressing to 35-90 bytes), and a
future Vicmap delivery tool version producing a slightly more redundant
index file could plausibly push the real worst case past 200 again.

---

_Fixed: 2026-09-18T02:11:04Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
