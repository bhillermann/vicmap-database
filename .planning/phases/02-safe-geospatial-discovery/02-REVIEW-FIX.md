---
phase: 02-safe-geospatial-discovery
fixed_at: 2026-09-18T02:01:38Z
review_path: .planning/phases/02-safe-geospatial-discovery/02-REVIEW.md
iteration: 1
findings_in_scope: 1
fixed: 1
skipped: 0
status: all_fixed
---

# Phase 2: Code Review Fix Report

**Fixed at:** 2026-09-18T02:01:38Z
**Source review:** .planning/phases/02-safe-geospatial-discovery/02-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope: 1 (fix_scope: critical_warning -- Warnings section only; IN-01/IN-02 and the RESOLVED "Disposition of Prior Findings" entries were explicitly out of scope and untouched)
- Fixed: 1
- Skipped: 0

**Verification environment:** Fixed in an isolated git worktree
(`.claude/worktrees/rf-02-202757-1789696579`, branch `gsd-reviewfix/02-202757`),
fast-forwarded onto `main` after the commit below. Full test suite and
syntax checks were run inside that worktree, not the main checkout.

## Fixed Issues

### WR-03: Write-time exclusive-create guard leaks the destination file descriptor when `zip_file.open()` raises after `os.open()` succeeds

**Files modified:** `vicmap_acquire/extraction.py`, `tests/test_extraction.py`
**Commit:** `d6b0754`
**Applied fix:** Reordered the compound `with` statement in `extract_artifact` at
`vicmap_acquire/extraction.py` (previously lines 363-365) from
`with zip_file.open(info, "r") as source, os.fdopen(descriptor, "wb") as target:`
to `with os.fdopen(descriptor, "wb") as target, zip_file.open(info, "r") as source:`
-- exactly the reordering the review's Fix section specified. Entering the raw
descriptor's wrapper first means the `with` statement's own guaranteed
partial-entry cleanup closes it if the sibling context manager
(`zip_file.open`) then fails to construct, instead of leaking it. Added an
explanatory inline comment above the statement recording the WR-03 rationale
so a future edit does not silently re-invert the ordering.

Added the regression test the review specified
(`WriteTimeGuardTest.test_fd_not_leaked_when_zip_open_raises_after_exclusive_create`
in `tests/test_extraction.py`), plus a new `_patch_compression_method` fixture
helper (mirroring the existing `_patch_general_purpose_flag_bit` helper) that
patches both the local file header and central directory record's
compression-method field to an unsupported value (99) directly in the raw
archive bytes -- no public `zipfile` writer API can construct this. The test
asserts the process's open file descriptor count (`/proc/{pid}/fd`) is
identical before the call and after `ArchiveUnreadable` is raised; it is
skipped on platforms without `/proc` (not present in this repo's existing
test suite, but `/proc` is Linux/WSL2-specific and this keeps the test
portable rather than failing outright elsewhere).

**Verification performed (per this task's explicit instructions, beyond the
standard 3-tier check):**
- Re-read the modified section of `extraction.py` to confirm the reordering
  and surrounding code are intact (Tier 1).
- `python3 -c "import ast; ast.parse(open('vicmap_acquire/extraction.py').read())"`
  and the same for `tests/test_extraction.py` -- both syntax-valid (Tier 2;
  no `ruff` binary or `pyproject.toml`/`Makefile`/CI config was found
  anywhere in this repo or its Nix flake to run an actual lint pass --
  `ruff` is listed only as an "optional" future addition in
  `.planning/research/STACK.md`, not wired into this project's toolchain,
  so lint was not run).
- Manually reproduced the review's live repro: a synthetic single-member zip
  with local + central directory compression-method fields patched to `99`.
  Confirmed against the **pre-fix** code (`git stash` of just
  `extraction.py`) that `os.getpid()`'s open fd count goes from 4 to 5 and
  does not return to baseline after `ArchiveUnreadable` is raised.
  Confirmed against the **post-fix** code that the count returns to 4.
- Ran the new regression test against the pre-fix ordering (`git stash push
  -- vicmap_acquire/extraction.py`): it fails with
  `AssertionError: 5 != 4`, confirming it is a real regression test, not a
  tautology. Restored the fix (`git stash pop`) and re-ran: it passes.
- `python3 -m unittest discover -s tests` -- full suite:
  **400 tests, OK, skipped=3** (the same skip count as before this change --
  the pre-existing `unittest.skipUnless(REAL_ARTIFACT.is_file(), ...)`-style
  skips, unrelated to this fix). Ran once before committing and once more
  after, both with identical results.

This finding's fix is a pure resource-lifetime/ordering correction (context
manager entry order), not a conditional/algorithmic logic change, so it does
not fall under the "logic bug -- requires human verification" caveat in the
verification strategy; standard `"fixed"` status applies.

## Skipped Issues

None -- the single in-scope finding (WR-03) was fixed.

---

_Fixed: 2026-09-18T02:01:38Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
