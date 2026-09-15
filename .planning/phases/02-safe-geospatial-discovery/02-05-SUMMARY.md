---
phase: 02-safe-geospatial-discovery
plan: 05
subsystem: geospatial-discovery
tags: [postgresql, naming, tdd, ast, differential-testing]

# Dependency graph
requires:
  - phase: 02-safe-geospatial-discovery/02-01
    provides: naming.py's pure charset/separator-collapse core, the NamingFailure/TableNameInvalid/TableNameCollision public contract, and LayerProfile's fixed dataset_stem/layer_name fields this plan reads verbatim
provides:
  - Complete D-21/D-22 strict normalization -- separator collapse-and-strip, charset, leading-digit, PostgreSQL reserved-word (both blocking categories), and 63-byte rules, each a small composed validation helper
  - A version-pinned 101-word PostgreSQL 18.6 reserved-keyword frozenset transcribed from the live Appendix C table, covering both the "reserved" and "reserved (can be function or type)" categories
  - D-23/D-24 same-delivery collision detection with a guaranteed invalid-before-collision precedence, and structural proof (ast) the module never contacts a database
affects: [02-06-manifest-finalization]

# Actuals (#2632)
actuals:
  tokens: 6184
  tasks: 2
  commits: 2

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "One small validation helper per D-22 rule (compose/casefold, collapse+strip, charset, leading-digit, reserved-keyword, byte-length), composed in a fixed order in normalize_target_table_name -- charset always runs before the byte-length measurement so a non-ASCII character never reaches that check"
    - "assign_target_table_names normalizes every profile in one pass before any collision comparison, so a delivery with both an invalid name and a collision always reports TableNameInvalid regardless of input order"

key-files:
  created: []
  modified:
    - vicmap_acquire/naming.py
    - tests/test_naming.py

key-decisions:
  - "Fetched and parsed the live PostgreSQL 18.6 Appendix C HTML table to transcribe the 101-word reserved-keyword frozenset (56 reserved + 22 reserved-requires-AS + 20 reserved-can-be-function-or-type + 3 reserved-can-be-function-or-type-requires-AS), rather than retyping from memory or a shortlist -- matches the project's stated differential-oracle/no-hand-rolling discipline and the plan's explicit warning that a hand-typed shortlist misses the second blocking category."
  - "Treated the 'requires AS' annotation PostgreSQL's own table attaches to some entries as orthogonal to blocking status -- it governs column-label use, not table-name validity -- so both 'reserved' and 'reserved, requires AS' collapse into one blocking set, and likewise for the can-be-function-or-type category."
  - "Drove the reserved-word test cases through the real normalize_target_table_name(dataset_stem, layer_name) API by pairing each bare keyword with a lone '-' as the other argument (the joiner underscore and the lone hyphen collapse into one separator run that the trailing-strip rule then removes), rather than testing a private helper directly -- keeps the tests behavior-focused per tdd.md's 'test behavior, not implementation' guidance."
  - "Wrapped assign_target_table_names's normalization pass in except NamingFailure: raise / except Exception: raise TableNameInvalid() from None, per the plan's total-function-with-catch-all pattern, so a malformed profile object (missing dataset_stem/layer_name) fails closed rather than leaking a bare AttributeError."

patterns-established:
  - "PostgreSQL keyword classification checks compare against a version-pinned, appendix-transcribed frozenset (POSTGRES_KEYWORD_SNAPSHOT documents the exact source and date) rather than any hand-typed or runtime-queried list -- the correct pattern for any future PostgreSQL-identifier validation in this codebase."

requirements-completed: [GEO-04, GEO-05]

coverage:
  - id: D1
    description: "Every target table name is {gdb_stem}_{layer} normalized, deterministic, and predictable by inspection -- charset, leading-digit, reserved-word (both blocking categories), and 63-byte rules are all typed closed failures with no truncation or hash suffix"
    requirement: GEO-04
    verification:
      - kind: unit
        ref: "tests/test_naming.py::NormalizeTargetTableNameTest (23 cases: happy path, each separator, mixed runs, leading/trailing strip, charset/accent/full-width-digit, leading digit, reserved-word categories, 63/64-byte boundary, empty/whitespace/non-string inputs)"
        status: pass
      - kind: unit
        ref: "tests/test_naming.py::PostgresKeywordSnapshotTest (snapshot non-empty and names version/appendix; all 13 shortlist-trap words from the plan raise)"
        status: pass
      - kind: unit
        ref: "command: nix develop path:. -c python -c \"from vicmap_acquire import naming as n; assert n.normalize_target_table_name('VMADD','ADDRESS')=='vmadd_address'; assert n.POSTGRES_KEYWORD_SNAPSHOT\""
        status: pass
    human_judgment: false
  - id: D2
    description: "A same-delivery collision (CRS-folder variant, format-folder variant, or case-only difference) is a hard TableNameCollision stop, an invalid name always takes precedence over a collision regardless of input order, and no code path ever treats an existing published table as a collision"
    requirement: GEO-05
    verification:
      - kind: unit
        ref: "tests/test_naming.py::AssignTargetTableNamesTest (10 cases: two-CRS-folder collision, two-format-folder collision, case-only collision, invalid-before-collision both orders, empty sequence, cross-call isolation, malformed-profile wrapping, order preservation, no-collision case)"
        status: pass
      - kind: unit
        ref: "tests/test_naming.py::NamingModulePurityTest (ast: no import of discovery/manifest/extraction/read_mailbox; no database driver or socket import)"
        status: pass
      - kind: unit
        ref: "command: nix develop path:. -c python -m unittest tests.test_discovery_tracer -v"
        status: pass
    human_judgment: false

duration: 25min
completed: 2026-09-16
status: complete
---

# Phase 2 Plan 5: Naming Hardening Summary

**Complete D-21 through D-24 target-table normalization and collision detection: strict charset/leading-digit/reserved-word/byte-length rules against a version-pinned 101-word PostgreSQL 18.6 keyword snapshot, plus same-delivery collision detection with a guaranteed invalid-before-collision precedence.**

## Performance

- **Duration:** ~25 min
- **Completed:** 2026-09-16
- **Tasks:** 2 (Task 1: normalization rules; Task 2: collision detection)
- **Files modified:** 2 (`vicmap_acquire/naming.py`, `tests/test_naming.py`)

## Accomplishments

- `normalize_target_table_name` now composes six small validation helpers (compose/casefold, separator collapse-and-strip, charset, leading-digit, reserved-keyword, byte-length) in a fixed order where charset validation always runs before the byte-length measurement, so a non-ASCII character fails on charset rather than producing a byte length that disagrees with its character length
- `POSTGRES_KEYWORD_SNAPSHOT` and a 101-word `_RESERVED_KEYWORDS` frozenset, transcribed directly from the live PostgreSQL 18.6 Appendix C table (fetched and parsed programmatically, not retyped from memory), covering both the `reserved` and `reserved (can be function or type)` categories -- including all 13 shortlist-trap words the plan calls out (`binary`, `concurrently`, `cross`, `current_schema`, `freeze`, `ilike`, `isnull`, `natural`, `notnull`, `outer`, `overlaps`, `similar`, `verbose`)
- `assign_target_table_names` normalizes every profile in one pass, wrapped in the codebase's total-function-with-catch-all shape, before any collision comparison -- guaranteeing a delivery with both an invalid name and a collision always reports `TableNameInvalid`, and a malformed profile object fails closed instead of leaking a bare `AttributeError`
- `tests/test_naming.py` -- 40 new regressions: full normalization matrix (23 cases), keyword-snapshot proof (2 cases), collision matrix (10 cases), and `ast`-based structural purity proofs (2 cases) that the module never imports a sibling pipeline module or a database driver/`socket`

## Task Commits

Both tasks followed the RED -> GREEN TDD cycle; no REFACTOR commit was needed (the GREEN implementation required no post-hoc cleanup):

1. **Task 1 + Task 2 RED: Add failing tests for D-21..D-24 naming rules** - `3e59423` (test)
2. **Task 1 + Task 2 GREEN: Implement complete D-21..D-24 naming and collision rules** - `be7d96d` (feat)

**Plan metadata:** (this commit, recorded after SUMMARY.md is written)

_Both tasks share the same two files (`vicmap_acquire/naming.py`, `tests/test_naming.py`) and their test/implementation work was done in one continuous RED/GREEN cycle spanning both tasks -- see Deviations for why they were committed together rather than as four separate commits._

## Files Created/Modified

- `vicmap_acquire/naming.py` - Complete D-21/D-22 normalization helpers, `POSTGRES_KEYWORD_SNAPSHOT`, 101-word reserved-keyword frozenset, hardened `assign_target_table_names`
- `tests/test_naming.py` - GEO-04/GEO-05 regression suite (new file, 40 tests) plus `ast` purity self-checks

## Decisions Made

- **Reserved-keyword list fetched from the live PostgreSQL 18.6 documentation, not retyped from memory.** Parsed the Appendix C HTML table programmatically (101 keywords across the two blocking categories, including the "requires AS" variants which are orthogonal to blocking status) to guarantee completeness against the actual categorization the plan warns a hand-typed shortlist misses.
- **Reserved-word test cases drive the real public API rather than a private helper.** Each bare keyword is tested by pairing it with a lone `-` as the other `normalize_target_table_name` argument -- the joiner underscore and the lone hyphen collapse into one separator run that the trailing-strip rule then removes, leaving the keyword as the exact composed result. Keeps tests behavior-focused per `tdd.md`'s "test behavior, not implementation" guidance.
- **`assign_target_table_names` wraps its normalization pass in `except NamingFailure: raise` / `except Exception: raise TableNameInvalid() from None`**, matching the plan's specified total-function shape, so a malformed profile object cannot produce an untyped error.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Consistency] Combined Task 1 and Task 2 into one RED and one GREEN commit**
- **Found during:** Preparing to commit after both tasks' test and implementation work was complete
- **Issue:** Both tasks modify the same two files (`vicmap_acquire/naming.py`, `tests/test_naming.py`) in the same continuous RED/GREEN TDD cycle -- Task 1's normalization helpers and Task 2's `assign_target_table_names` hardening were designed and tested together because Task 2's acceptance criteria (invalid-before-collision precedence) depend directly on Task 1's normalization behavior being complete first. Splitting into four artificial intermediate commits would misrepresent the real incremental history, matching the precedent 02-02/02-03/02-04's SUMMARYs already documented for this codebase.
- **Fix:** Committed one RED commit (`test(02-05)`, 40 failing/erroring tests against the pre-existing tracer-only implementation) and one GREEN commit (`feat(02-05)`, all 40 passing), with both tasks' `<verify>` commands run against the final state and recorded in this SUMMARY's coverage block.
- **Files modified:** none beyond the plan's own two files -- this was a commit-sequencing decision, not a code-behavior change.
- **Verification:** `nix develop path:. -c python -m unittest tests.test_naming -v` (40 tests, `OK`) and `nix develop path:. -c python -m unittest discover -s tests -p 'test_*.py'` (343 tests, `OK` -- 303 baseline + 40 new, zero regressions).
- **Committed in:** `3e59423` (RED), `be7d96d` (GREEN)

**2. [Rule 3 - Blocking] Added minimal keyword-snapshot constants to the RED commit so the test module could import**
- **Found during:** First RED-phase test run
- **Issue:** `tests/test_naming.py` imports `POSTGRES_KEYWORD_SNAPSHOT` from `vicmap_acquire.naming`, which did not exist yet -- an unqualified RED run therefore failed at module import (zero-test discovery), not on a specific behavioral assertion, which the TDD gate rules classify as `INVALID_RED` rather than a legitimate target-test failure.
- **Fix:** Added `POSTGRES_KEYWORD_SNAPSHOT` and the 101-word `_RESERVED_KEYWORDS` frozenset (pure data, no normalization/collision logic change) to `naming.py` as part of the RED commit, so the test module imports successfully and the RED run fails on real assertions (26 failures + 1 error against the not-yet-implemented leading-digit/reserved-word/byte-length/strip/malformed-profile-wrapping rules) rather than an import error.
- **Files modified:** `vicmap_acquire/naming.py` (data-only addition, no behavior change)
- **Verification:** Captured the RED run's output showing genuine assertion failures (e.g. `test_leading_digit_raises: AssertionError: TableNameInvalid not raised`), confirming valid RED per the `check tdd-red-evidence` "target test fails on an assertion for the planned behavior" standard.
- **Committed in:** `3e59423`

---

**Total deviations:** 2 (1 commit-sequencing decision, 1 blocking-issue fix for a valid RED state). No scope creep -- only `vicmap_acquire/naming.py` and `tests/test_naming.py` were touched, matching the plan's declared `files_modified`.
**Impact on plan:** Both were necessary for TDD discipline and codebase consistency. No behavior beyond what the plan specifies was added.

## Issues Encountered

None beyond the deviations documented above.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- `vicmap_acquire/naming.py`'s public contract (`NamingFailure`, `TableNameInvalid`, `TableNameCollision`, `normalize_target_table_name`, `assign_target_table_names`, `POSTGRES_KEYWORD_SNAPSHOT`) is unchanged from the 02-01 tracer's exported names -- 02-06 (manifest finalization) can consume it as planned with no signature changes.
- GEO-04 and GEO-05 are each also declared by sibling plans (`GEO-04`: 02-01, 02-06; `GEO-05`: 02-04, 02-06) that have not yet produced a `02-06-SUMMARY.md`. Per the shared-ID gate (#2388), neither will be marked complete in `REQUIREMENTS.md` until 02-06 finishes, even though this plan's own work on both is done.
- Full suite green: `nix develop path:. -c python -m unittest discover -s tests -p 'test_*.py' -v` reports 343 tests, `OK` (303 baseline + 40 new, zero regressions).
- No blockers for 02-06.

---
*Phase: 02-safe-geospatial-discovery*
*Completed: 2026-09-16*
