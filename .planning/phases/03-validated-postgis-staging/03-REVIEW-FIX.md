---
phase: 03-validated-postgis-staging
fixed_at: 2026-09-22T00:38:57Z
review_path: .planning/phases/03-validated-postgis-staging/03-REVIEW.md
iteration: 1
findings_in_scope: 6
fixed: 6
skipped: 0
status: all_fixed
---

# Phase 03: Code Review Fix Report

**Fixed at:** 2026-09-22T00:38:57Z
**Source review:** .planning/phases/03-validated-postgis-staging/03-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope: 6 (fix_scope: critical_warning — WR-01..WR-06; IN-01/IN-02 out of scope)
- Fixed: 6
- Skipped: 0

**Verification:** worked in an isolated git worktree
(`.claude/worktrees/rf-03-26997-1790036820`, branch `gsd-reviewfix/03-26997`,
fast-forwarded onto `main` at cleanup). Every fix was syntax-checked
(`ast.parse`) and re-read (Tier 1/2). Additionally ran the full non-DB test
suite (`python3 -m unittest discover -s tests`) after each fix and once more
at the end: 507 tests passed, 35 skipped (pre-existing — no reachable
PostgreSQL server in this environment), 0 failures, both before and after
all six fixes.

## Fixed Issues

### WR-01: `apply_post_validation_ddl`'s return value was discarded

**Files modified:** `vicmap_acquire/evidence.py`, `vicmap_acquire/staging.py`
**Commit:** `aa4aa92`
**Applied fix:** Added an optional `ddl_objects_created: tuple[str, ...] = ()`
parameter to `SuccessEvent.staging_layer_validated`, validated element-wise
with the same `_require_target_table` redaction check `staging_table`
already uses, and rendered as a `list` field. `run_staging` now captures
`apply_post_validation_ddl`'s return value and threads it through. Existing
`StagingEventRedactionTest` cases (which construct `staging_layer_validated`
without the new kwarg) still pass because the field defaults to `()`.

### WR-02: DDL identifier names had no bound against PostgreSQL's 63-byte limit

**File modified:** `vicmap_acquire/staging.py`
**Commit:** `bd9ac7b`
**Applied fix:** Added `_bounded_composed_identifier(name)`: returns `name`
unchanged when it is within 63 UTF-8 bytes, otherwise deterministically
truncates and appends an 8-hex-char SHA-256-derived suffix so the composed
name stays within the limit and two distinct over-length names cannot
collide. Applied it to every identifier `apply_post_validation_ddl` composes
by string-concatenation: the `_pkey`/`_geom_typed`/`_geom_not_null` labels,
the GiST index name, and every allowlisted secondary-index name. Verified
manually that a 74-byte input truncates to exactly 63 bytes and that two
different 74-byte inputs produce two different bounded names (no collision).

### WR-03: Validation-query and repair-query failures were mapped onto `LoadFailed`

**Files modified:** `vicmap_acquire/staging.py`, `vicmap_acquire/evidence.py`,
`tests/test_evidence.py`
**Commit:** `d7c4950`
**Applied fix:** Added a new closed exception `ValidationQueryFailed`
(`code = "db_validation_query_failed"`) and a matching `ReasonCode` /
`_FAILURE_POLICY` entry (`Stage.DB_VALIDATION`, hint
`retry_validation_or_review_staging_table_directly` — no diagnostics-file
reference). Both `except Exception` blocks in `validate_layer` that
previously raised `LoadFailed()` (the validation `SELECT` and the repair
`UPDATE`/recheck) now raise `ValidationQueryFailed()`, and the function's
outer re-raise tuple was extended to include it. Updated
`test_every_reason_has_one_fixed_stage_and_remediation_hint` in
`tests/test_evidence.py` (an exhaustive-equality assertion over the reason/
stage vocabulary) to include the new entry — required for the suite to stay
green after adding a `ReasonCode` member; the pre-existing
`test_phase_3_reason_codes_extend_the_closed_vocabulary` uses a subset check
and needed no change.

### WR-04: The typed-column `ALTER`'s raw-SQL type modifier had no local re-validation

**File modified:** `vicmap_acquire/staging.py`
**Commit:** `c2f16be`
**Applied fix:** Added `_VALID_TYPED_COLUMN_NAMES`, the closed 28-member
vocabulary (`_BASE_GEOMETRY_NAMES` x `_ZM_SUFFIX_FLAGS`, i.e. every base name
concatenated with every ZM suffix token) that `normalize_declared_geometry_type`
can ever produce as `declared_type`. `apply_post_validation_ddl` now raises
`StagingDdlFailed()` (rather than a bare `assert`, to stay consistent with
this function's existing invariant-violation style and to avoid the
assertion being silently stripped under `python -O`) if `declared_type` is
not a member, immediately before the `sql.SQL(declared_type)` composition.
Verified the vocabulary set has exactly 28 members as expected.

### WR-05: `stage_order.py` dropped `order_id` from the `AcquisitionFailure` failure event

**File modified:** `stage_order.py`
**Commit:** `49a166f`
**Applied fix:** Changed `render_failure(error.failure)` to
`render_failure(SafeFailure(error.failure.reason, order_id=order_id))` in the
`AcquisitionFailure` except branch, matching the pattern the sibling
`StagingFailure`/`ManifestFailure` branches already use.
`SafeFailure.reason` is a `@property` returning the underlying `ReasonCode`
(confirmed by reading `evidence.py`), so this rebuild is type-correct;
verified interactively that it renders `order_id` into the payload.

### WR-06: `evidence.py`'s redaction-safety regexes were looser than upstream validators

**File modified:** `vicmap_acquire/evidence.py`
**Commit:** `86ab35b`
**Applied fix:** Replaced `_HOST`'s pattern with the exact
`staging._HOSTNAME`/`read_mailbox._HOSTNAME` pattern (253-byte total bound,
per-label DNS structure, at least two labels) and replaced `_TARGET_TABLE`'s
pattern with `staging._identifier`'s exact 63-byte bound
(`[a-z][a-z0-9_]{0,62}`). Confirmed both regexes' only current callers
(`download_target`'s FQDN hostnames, `_require_database_host`'s upstream-
validated db hosts, and every `target_table`/`staging_table` value, all of
which are already validated by a stricter upstream check) still pass under
the tightened patterns.

## Skipped Issues

None — all six in-scope findings (WR-01 through WR-06) were fixed. IN-01 and
IN-02 were out of scope for this run (`fix_scope: critical_warning`).

---

_Fixed: 2026-09-22T00:38:57Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
