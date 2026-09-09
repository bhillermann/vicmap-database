---
phase: 01-trusted-graph-acquisition
plan: 08
subsystem: acquisition
tags: [python, ssrf, download, atomicity, concurrency, filesystem-durability]

requires:
  - phase: 01-06
    provides: Exact configured URL-prefix authority applied to the initial hop and every redirect hop
provides:
  - A single named publication commit point (`_publish_artifact`) so a post-commit temporary-name cleanup failure can never be reported as a transfer failure for state that is already published
  - `DownloadResult.temp_cleanup_deferred` making a deferred cleanup condition observable to callers instead of silently converting success into `artifact_write_failed`
  - A result/state agreement invariant proven across all five pre-commit failure families (timeout, over-limit, short write, declared-length mismatch, existing final path)
  - Committed concurrency, interruption, boundary, and floor-division-precision regressions closing the three MAIL-04/MAIL-05 edge-probe rows this plan owns
  - Committed proof that every redirect hop (not just the initial target) is authorized against both the host allowlist and the configured URL prefix, with byte-exact path case sensitivity and PROHIB-02 evidence
affects: [02-safe-geospatial-discovery, trusted-graph-acquisition]

actuals:
  tokens: 4347
  tasks: 3
  commits: 3
commits: 3
plan_head_before: 7d3673d091510de0e9a15ba24025b33f0da8d4d6

tech-stack:
  added: []
  patterns:
    - "One named commit point (`_publish_artifact`): everything before it can still fail the transfer; nothing after it can turn a committed success back into a reported failure"
    - "Post-commit cleanup failure is recorded as an observable result field (`temp_cleanup_deferred`), never re-raised as an exception"
    - "Directory fsync after a successful hard-link publish, best-effort and platform-tolerant (swallows OSError)"

key-files:
  created: []
  modified:
    - vicmap_acquire/download.py
    - tests/test_download.py

key-decisions:
  - "Made os.link's success the exact commit boundary: temp_path is set to None unconditionally once _publish_artifact returns, so the outer finally block can never re-decide an outcome this function already committed."
  - "Post-commit temp-name cleanup failure is absorbed inside _publish_artifact and surfaced only as DownloadResult.temp_cleanup_deferred, never as ArtifactWriteFailed — closing verification gap G-03's exact deterministic repro."
  - "Left the existing FileExistsError-to-ArtifactWriteFailed translation and the pre-commit failure paths completely unchanged, so the fix is additive and does not touch already-verified behavior."
  - "Verified (not re-implemented) that _request_final_response already passed allowed_url_prefixes at both the initial and post-redirect validate_https_target call sites from 01-06; this plan's Task 3 work was proving that with regressions, not new production code."

patterns-established:
  - "Commit-point separation: a function that performs an irreversible action returns a boolean for its own best-effort post-action cleanup rather than raising, so callers can never mistake a committed action for a failed one."

requirements-completed: [MAIL-04, MAIL-05]

coverage:
  - id: D1
    description: "A post-commit temp-name cleanup failure after a successful os.link publish is reported as a successful DownloadResult with temp_cleanup_deferred=True, never as artifact_write_failed for state that is already published (closes gap G-03)."
    requirement: MAIL-04
    verification:
      - kind: unit
        ref: "tests/test_download.py#DownloadCommitPointTest.test_post_link_cleanup_failure_still_reports_a_committed_success"
        status: pass
      - kind: unit
        ref: "tests/test_download.py#DownloadCommitPointTest.test_post_link_cleanup_success_reports_deferred_false"
        status: pass
    human_judgment: false
  - id: D2
    description: "Whenever download_artifact raises, the final path was not created by that call: proven independently across all five pre-commit failure families."
    requirement: MAIL-04
    verification:
      - kind: unit
        ref: "tests/test_download.py#DownloadCommitPointTest.test_pre_commit_timeout_family_leaves_no_final_path"
        status: pass
      - kind: unit
        ref: "tests/test_download.py#DownloadCommitPointTest.test_pre_commit_over_limit_family_leaves_no_final_path"
        status: pass
      - kind: unit
        ref: "tests/test_download.py#DownloadCommitPointTest.test_pre_commit_short_write_family_leaves_no_final_path"
        status: pass
      - kind: unit
        ref: "tests/test_download.py#DownloadCommitPointTest.test_pre_commit_declared_length_mismatch_family_leaves_no_final_path"
        status: pass
      - kind: unit
        ref: "tests/test_download.py#DownloadCommitPointTest.test_pre_commit_existing_final_path_family_is_left_untouched"
        status: pass
    human_judgment: false
  - id: D3
    description: "Exactly one of two concurrent finalizers publishes and leaves no readable private partial; an interrupted run leaves neither a final path nor a readable partial under the final name (MAIL-04 concurrency edge row)."
    requirement: MAIL-04
    verification:
      - kind: unit
        ref: "tests/test_download.py#DownloadStreamingBoundaryTest.test_two_concurrent_finalizers_have_exactly_one_complete_winner"
        status: pass
      - kind: unit
        ref: "tests/test_download.py#DownloadStreamingBoundaryTest.test_keyboard_interrupt_cleans_private_state_and_reraises"
        status: pass
      - kind: unit
        ref: "tests/test_download.py#DownloadStreamingBoundaryTest.test_in_progress_state_is_private_mode_and_never_final"
        status: pass
    human_judgment: false
  - id: D4
    description: "A transfer of exactly max_bytes is accepted, max_bytes plus one byte is rejected, and a declared Content-Length above max_bytes is rejected before any body chunk is consumed (MAIL-05 boundary edge row)."
    requirement: MAIL-05
    verification:
      - kind: unit
        ref: "tests/test_download.py#DownloadStreamingBoundaryTest.test_exact_ceiling_byte_count_succeeds"
        status: pass
      - kind: unit
        ref: "tests/test_download.py#DownloadStreamingBoundaryTest.test_ceiling_plus_one_byte_is_rejected_and_leaves_no_final_path"
        status: pass
      - kind: unit
        ref: "tests/test_download.py#DownloadStreamingBoundaryTest.test_over_declared_content_length_rejected_before_any_chunk_consumed"
        status: pass
    human_judgment: false
  - id: D5
    description: "Progress percentage is floor-divided integer tenths capped at 100.0, and every emitted byte_count is an exact Python int, never a bool or float (MAIL-05 precision edge row)."
    requirement: MAIL-05
    verification:
      - kind: unit
        ref: "tests/test_download.py#DownloadStreamingBoundaryTest.test_precision_table_uses_floor_division_and_never_exceeds_cap"
        status: pass
      - kind: unit
        ref: "tests/test_download.py#DownloadStreamingBoundaryTest.test_emitted_progress_byte_counts_are_always_int_never_float"
        status: pass
    human_judgment: false
  - id: D6
    description: "Every redirect hop (not just the initial target) is authorized against both the host allowlist and the exact configured URL prefix before the next request, with byte-exact path case sensitivity and no ambient/Graph authority reaching the artifact host across a redirect chain."
    requirement: MAIL-04
    verification:
      - kind: unit
        ref: "tests/test_download.py#DownloadTransportBoundaryTest.test_relative_redirect_leaving_the_configured_prefix_is_rejected_before_recontact"
        status: pass
      - kind: unit
        ref: "tests/test_download.py#DownloadTargetPolicyTest.test_prefix_path_case_difference_is_rejected_byte_exact"
        status: pass
      - kind: unit
        ref: "tests/test_download.py#DownloadPolicyValidationTest.test_allowed_url_prefixes_rejects_seven_invalid_shapes"
        status: pass
      - kind: unit
        ref: "tests/test_download.py#DownloadTransportBoundaryTest.test_prohib_02_no_ambient_or_graph_authority_reaches_artifact_host"
        status: pass
    human_judgment: false

duration: 40min
completed: 2026-09-09
status: complete
---

# Phase 01 Plan 08: Publication Commit Point and Redirect Prefix Authorization Summary

**Separated `download_artifact`'s publication into one named commit point (`_publish_artifact`) so a post-commit cleanup failure now returns a successful `DownloadResult` with `temp_cleanup_deferred=True` instead of the previous `artifact_write_failed` misreport, and committed the deterministic G-03 repro plus MAIL-04/MAIL-05 concurrency, boundary, precision, and every-redirect-hop-prefix-authorized regressions.**

## Performance

- **Duration:** ~40 min
- **Started:** 2026-09-09T04:25:00+00:00 (approx.)
- **Completed:** 2026-09-09T05:05:04Z
- **Tasks:** 3
- **Files modified:** 2

## Accomplishments

- `_publish_artifact` (new) makes `os.link` the single commit point: a `FileExistsError` still propagates and is translated to `ArtifactWriteFailed` exactly as before, but any exception from the post-commit temporary-name unlink is absorbed and reported via the new `DownloadResult.temp_cleanup_deferred` field instead.
- `_fsync_directory` (new) fsyncs the containing directory immediately after a successful `os.link`, before the result is constructed, swallowing `OSError` on platforms without directory-fsync support.
- `download_artifact` now sets `temp_path = None` unconditionally the instant `_publish_artifact` returns, so the surrounding `finally` block's guarded cleanup can never re-decide an already-committed outcome — the exact mechanism behind verification gap G-03 is now structurally impossible.
- Reproduced gap G-03 deterministically before the fix (injected `Path.unlink` failure on the private-prefix name → `artifact_write_failed` with the final path already on disk) and confirmed the fix converts it to a successful, agreement-preserving result.
- Added `DownloadCommitPointTest` (7 tests): the injected post-link cleanup failure, a clean-cleanup control case, and one dedicated test per pre-commit failure family (timeout, over-limit, short write, declared-length mismatch, existing final path) proving the final path is never created — or, for the pre-existing case, never altered — by a raising call.
- Extended the existing concurrency test to additionally assert no `.vicmap-download-*` partial remains readable after the race resolves.
- Added dedicated boundary tests (`test_exact_ceiling_byte_count_succeeds`, `test_ceiling_plus_one_byte_is_rejected_and_leaves_no_final_path`, `test_over_declared_content_length_rejected_before_any_chunk_consumed` — the last counting `iter_content` invocations to prove zero body chunks are ever consumed) and precision tests (`test_precision_table_uses_floor_division_and_never_exceeds_cap`, `test_emitted_progress_byte_counts_are_always_int_never_float`).
- Confirmed (without needing a code change) that `_request_final_response` already applies `allowed_url_prefixes` at both the initial-hop and post-redirect `validate_https_target` call sites from 01-06, then proved it with new regressions: a relative redirect resolving outside the configured prefix is rejected before a second contact; a byte-exact path-case mismatch is rejected even though scheme/host are casefolded; `DownloadPolicy` rejects all seven invalid `allowed_url_prefixes` shapes (empty, disallowed host, query, fragment, userinfo, missing trailing slash, empty path segment, duplicates); and a dedicated `test_prohib_02_...` regression proves no `Authorization`/`Cookie` header or ambient `trust_env`/`auth` reaches the artifact host across a two-hop redirect chain.
- `tests/test_download.py` grew from 30 to 47 tests (full suite 118 → 135), all green, no skips.

## Task Commits

Each task was committed atomically:

1. **Task 1: Define the publication commit point and move cleanup outside the failure path** - `2bc9d67` (feat)
2. **Task 2: Injected post-link cleanup-failure, concurrency, and interruption regressions** - `060bc34` (test)
3. **Task 3: Authorize every redirect hop against the configured URL prefix** - `ef259cb` (test)

**Plan metadata:** commit follows in this same operation.

_Note: Tasks 1-3 are all `tdd="true"` per the plan. Task 1's RED phase was proven via an uncommitted scratch reproduction of gap G-03 against the pre-fix code (not committed, since Task 1's declared file scope is `vicmap_acquire/download.py` only); the implementation commit is a single `feat` commit. Tasks 2 and 3 are test-only commits: Task 2's regressions exercise Task 1's already-complete implementation, and Task 3's regressions prove behavior that 01-06 had already implemented correctly, so no further `feat` commit was needed for either._

## Files Created/Modified

- `vicmap_acquire/download.py` - Added `_publish_artifact`, `_fsync_directory`, `DownloadResult.temp_cleanup_deferred`; restructured `download_artifact`'s tail so publication is one named commit point
- `tests/test_download.py` - New `DownloadCommitPointTest` class (7 tests); extended `DownloadStreamingBoundaryTest`, `DownloadTargetPolicyTest`, `DownloadTransportBoundaryTest`, and `DownloadPolicyValidationTest` with commit-point, concurrency, boundary, precision, and redirect-prefix regressions (10 more tests); suite grew 30 → 47 tests

## Decisions Made

See `key-decisions` in frontmatter. In short: `os.link`'s success is the exact, structural commit boundary (`temp_path = None` set unconditionally once past it); post-commit cleanup failure is an observable result field, never an exception; the pre-commit failure paths and the `FileExistsError` translation are untouched; and Task 3's redirect-prefix authorization was already correctly implemented in 01-06, so this plan's contribution there is proof, not new production code.

## Deviations from Plan

None - plan executed exactly as written. Task 3 required no production-code change because the acceptance criterion it names ("passes `policy.allowed_url_prefixes` at every `validate_https_target` call site") was already true from 01-06's implementation; the plan's own action text anticipated this ("if either call site still omits it, add it") and no addition was needed.

## Known Stubs

None introduced by this plan. (The pre-existing `vicmap.toml` `allowed_url_prefixes` placeholder is 01-06's documented stub, tracked in `.planning/WINDOWS.md`, unaffected by this plan's tests, which construct their own in-test policies.)

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Verification gap G-03's `missing` bullets 1 and 2 are both closed with committed implementation and regressions.
- Verification gap G-01's `missing` bullet 2 "and every redirect" clause is proven by automated redirect regressions.
- The three MAIL-04/MAIL-05 edge-probe rows this plan owns (concurrency, boundary, precision) are each backed by passing tests.
- `requirements-completed` lists `MAIL-04`/`MAIL-05` as this plan's own contribution; both remain shared across sibling plans 01-01, 01-04, 01-05, 01-06, 01-09, and 01-11 in `REQUIREMENTS.md`, so the shared-ID gate will mark them `Complete` only once every declaring plan in this phase has produced a summary.
- Sibling gap-closure plans 01-09, 01-10, and 01-11 remain unblocked and can proceed; this plan touched no files they own (`evidence.py`, `read_mailbox.py`, `candidates.py`, `graph.py`).

---
*Phase: 01-trusted-graph-acquisition*
*Completed: 2026-09-09*

## Self-Check: PASSED

- FOUND: vicmap_acquire/download.py
- FOUND: tests/test_download.py
- FOUND: .planning/phases/01-trusted-graph-acquisition/01-08-SUMMARY.md
- FOUND commit: 2bc9d67 (feat, Task 1)
- FOUND commit: 060bc34 (test, Task 2)
- FOUND commit: ef259cb (test, Task 3)
- `nix develop path:. -c python -m unittest tests.test_download -v` → 47 tests, OK, no skips (Task 1 required ≥28, Task 2 required ≥40, Task 3 required ≥47)
- `nix develop path:. -c python -m unittest discover -s tests -p 'test_*.py' -v` → 135 tests, OK, no failures, no skips
- Re-ran all task-level `<acceptance_criteria>` greps and behavioral assertions: all pass (see plan verification above)
