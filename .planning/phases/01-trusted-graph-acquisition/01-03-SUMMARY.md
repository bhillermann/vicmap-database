---
phase: 01-trusted-graph-acquisition
plan: 03
subsystem: acquisition
tags: [python, mime, html-parser, url-parsing, deterministic-selection]
requires:
  - phase: 01-01
    provides: Guarded acquisition controller, candidate seams, and closed failure vocabulary
  - phase: 01-02
    provides: Immutable UTC Graph metadata and explicit MIME-by-ID retrieval
provides:
  - Exact whole-value sender and ready-subject candidate recognition
  - Text-first MIME archive-link extraction with occurrence-preserving cardinality
  - Strict canonical order consistency with a reviewable mismatch override
  - Full-stream deterministic newest-candidate selection with complete Graph-ID ties
affects: [01-05, trusted-graph-acquisition, acquisition-evidence]
actuals:
  tokens: 5557
  tasks: 2
  commits: 4
commits: 4
plan_head_before: 8cae20fd544a9fc38c99d3565583f3e4ba4cf1b1
tech-stack:
  added: []
  patterns: [pure trust policy, closed typed failures, MIME precedence, stable total ordering]
key-files:
  created:
    - tests/test_candidates.py
    - .planning/phases/01-trusted-graph-acquisition/01-03-TASK1-RED.json
    - .planning/phases/01-trusted-graph-acquisition/01-03-TASK2-RED.json
  modified:
    - vicmap_acquire/candidates.py
key-decisions:
  - "Preserve the Plan 01 lazy MIME-loader and keyword-policy call while also exposing the direct bytes-plus-CandidatePolicy interface required by Plan 03."
  - "Use typed closed candidate failures so ordinary header non-matches return None while malformed, ambiguous, mismatched, or empty selection states remain distinguishable."
  - "Normalize selection timestamps to UTC only for the total key and retain the complete case-sensitive Unicode Graph ID internally as the deterministic tie-breaker."
patterns-established:
  - "MIME precedence: archive-shaped plain-text URL occurrences suppress HTML fallback even when plain text is ambiguous."
  - "Candidate ordering: consume the complete iterable, coalesce identical records, and reject conflicting records sharing one normalized total key."
requirements-completed: [MAIL-02, MAIL-03]
coverage:
  - id: D1
    description: "Only exact configured senders and whole ready subjects can reach occurrence-preserving plain-first or HTML-fallback archive recognition."
    requirement: MAIL-02
    verification:
      - kind: unit
        ref: "tests/test_candidates.py#CandidateRecognitionTest"
        status: pass
    human_judgment: false
  - id: D2
    description: "Filename order consistency, duplicate cardinality, malformed MIME, and reviewed mismatch behavior fail through closed policy outcomes."
    requirement: MAIL-02
    verification:
      - kind: unit
        ref: "tests/test_candidates.py#CandidateRecognitionTest"
        status: pass
    human_judgment: false
  - id: D3
    description: "The complete candidate stream yields one newest record with normalized UTC and complete Graph-ID ordering or one closed safe failure."
    requirement: MAIL-03
    verification:
      - kind: unit
        ref: "tests/test_candidates.py#CandidateSelectionTest"
        status: pass
    human_judgment: false
duration: 17min
completed: 2026-09-08
status: complete
---

# Phase 1 Plan 3: Trusted Candidate Policy Summary

**Exact MIME-aware Vicmap ready-order recognition now feeds one full-stream deterministic newest-message selection through closed, source-safe failures.**

## Performance

- **Duration:** 17 minutes
- **Started:** 2026-09-08T02:27:38Z
- **Completed:** 2026-09-08T02:45:04Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments

- Enforced exact whole-address sender and complete case-insensitive ready-subject templates across the configured canonical order allowlist, without Unicode normalization or adjacency acceptance.
- Parsed MIME with the standard email parser, preferred archive-shaped plain-text URL occurrences over HTML anchor fallback, retained duplicate occurrences, and decoded the final filename segment exactly once with strict UTF-8.
- Selected exactly one newest candidate only after complete iterable consumption, with UTC-normalized instants and the complete case-sensitive Unicode Graph ID forming a stable total key.
- Converted malformed MIME, missing or duplicate links, unapproved order mismatches, empty selection, null records, invalid timestamps, and conflicting total keys into closed typed failures.

## Task Commits

Each TDD gate and implementation step was committed atomically:

1. **Task 1 RED: failing candidate recognition regressions** - `b7c5c82` (test)
2. **Task 1 GREEN: trusted candidate recognition policy** - `7dc0334` (feat)
3. **Task 2 RED: failing deterministic selection regressions** - `2e230b0` (test)
4. **Task 2 GREEN: full-stream deterministic candidate selection** - `fa21492` (feat)

## Files Created/Modified

- `vicmap_acquire/candidates.py` - Defines pure recognition, MIME URL extraction, typed failures, candidate policy, and stable total-key selection.
- `tests/test_candidates.py` - Covers sender/subject adjacency, MIME precedence, occurrence cardinality, order consistency, shuffled selection, full-ID ties, invalid inputs, and duplicate conflicts.
- `.planning/phases/01-trusted-graph-acquisition/01-03-TASK1-RED.json` - Machine-verified fail-first evidence for candidate recognition.
- `.planning/phases/01-trusted-graph-acquisition/01-03-TASK2-RED.json` - Machine-verified fail-first evidence for deterministic selection.

## Decisions Made

- Kept the existing lazy MIME callback and keyword allowlist API for the production controller while supporting direct MIME bytes plus an immutable `CandidatePolicy` for the Plan 03 domain interface.
- Reserved `None` for ordinary sender or subject non-qualification; once headers qualify, malformed or ambiguous source content raises a closed typed failure.
- Compared archive filename order IDs case-sensitively after exactly one strict percent-decoding pass, while whole ready subjects use `casefold()` and return the configured canonical order ID.
- Used normalized UTC timestamps only inside the stable selection key, retaining complete opaque Graph IDs internally without adding any rendering surface.

## TDD Gate Compliance

- Task 1 RED: `RED_EVIDENCE_OK` for qualifying empty MIME returning `None` instead of `candidate_ambiguous`, committed before `7dc0334`.
- Task 2 RED: `RED_EVIDENCE_OK` for empty selection returning `None` and null input exposing a raw type error, committed before `fa21492`.
- No refactor commit was needed; the minimal GREEN implementation remained clear and the latest full project verification passed 42 tests with no skips.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

- One post-commit acceptance rerun could not reach the local Nix daemon inside the filesystem sandbox; the same checks were rerun with approved daemon access and passed.

## User Setup Required

None - candidate policy verification is pure and uses synthetic metadata and MIME. Live tenant access remains reserved for Plan 01-05.

## Next Phase Readiness

- Plan 01-05 can consume exact typed candidate failures and one deterministic selection without inspecting raw MIME or rendering full Graph IDs.
- No blocker remains for Plan 01-04 or the later controlled live acquisition.

## Self-Check: PASSED

- The candidate module, test module, and both RED evidence artifacts exist.
- All four RED/GREEN commits are present in order after the recorded plan base.
- Both RED evidence records report `RED_EVIDENCE_OK`.
- Candidate-policy verification passes 24 tests; the complete project suite passes 42 tests with no skips.

---
*Phase: 01-trusted-graph-acquisition*
*Completed: 2026-09-08*
