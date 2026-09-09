---
phase: 01-trusted-graph-acquisition
plan: 07
subsystem: acquisition
tags: [python, html-parser, candidate-recognition, xss-adjacent, email]

requires:
  - phase: 01-06
    provides: Authenticated-origin policy and bucket-prefix authority wired into candidate recognition
provides:
  - Rendered-context-aware HTML archive-link extraction in `vicmap_acquire/candidates.py` — a `script`/`style`/`template`/`noscript`/`head`/`title`/`meta`/`link`/`object`/`iframe`/`applet`/`xmp` element or an HTML comment can never contribute the accepted archive URL
  - Committed regressions closing verification gap G-04's two `missing` bullets (non-rendered HTML negatives, malformed-nesting shapes)
  - Committed regressions for all six MAIL-02/MAIL-03 edge-probe rows this plan owns (adjacency, empty, encoding, ordering, selection-empty, selection-encoding)
affects: [trusted-graph-acquisition, evidence]

actuals:
  tokens: 2602
  tasks: 2
  commits: 3
commits: 3
plan_head_before: 8892b86f7cf0334cb15ce6249dbe00f6be928fc5

tech-stack:
  added: []
  patterns:
    - "Non-rendered-element suppression via an integer depth counter on _AnchorCollector, clamped at zero on handle_endtag so an unmatched or mismatched closing tag can never escape suppression"
    - "html.parser's built-in CDATA scanning for script/style (searching only for that tag's own literal closing sequence) is relied on, not re-implemented: an unclosed or mismatched-closed script/style element simply never reaches handle_data because feed() alone does not flush unresolved CDATA without close()"

key-files:
  created: []
  modified:
    - vicmap_acquire/candidates.py
    - tests/test_candidates.py

key-decisions:
  - "Suppressed archive-link collection with a depth counter gating both handle_starttag (href collection) and handle_data (visible-text collection), rather than filtering the returned URL list after the fact, so a nested non-rendered element can never leak text through an outer rendered scope."
  - "Left extract_text_urls, _archive_order_id, _archive_links, _mime_archive_links, recognize_candidate, and select_candidate behaviorally unchanged, confining this plan's change to _AnchorCollector exactly as scoped."
  - "For a literal empty-bytes MIME message, asserted the real system behavior (OriginUnauthenticated, since 01-06 already fails closed on missing Authentication-Results before any link extraction) rather than forcing a CandidateAmbiguous assertion the plan's <behavior> text implied — both are closed failures, and the must_haves.truths wording ('fail closed rather than producing a candidate') is satisfied by either."

patterns-established:
  - "html.parser CDATA-mode reliance for script/style suppression: no manual raw-text re-scanning is needed because the stdlib parser already defers un-terminated or mismatched-terminated CDATA content past the point where handle_data would run."

requirements-completed: [MAIL-02, MAIL-03]

coverage:
  - id: D1
    description: "An archive URL that only exists inside a non-rendered HTML element (script, style, template, noscript, head, title, meta, link, object, iframe) or an HTML comment cannot make a message a candidate; the same URL as ordinary displayed text still can."
    requirement: MAIL-02
    verification:
      - kind: unit
        ref: "tests/test_candidates.py#CandidateRecognitionTest.test_archive_url_only_inside_script_element_yields_no_candidate"
        status: pass
      - kind: unit
        ref: "tests/test_candidates.py#CandidateRecognitionTest.test_every_non_rendered_tag_suppresses_its_sole_archive_url"
        status: pass
      - kind: unit
        ref: "tests/test_candidates.py#CandidateRecognitionTest.test_anchor_href_nested_inside_script_yields_no_archive_link"
        status: pass
      - kind: unit
        ref: "tests/test_candidates.py#CandidateRecognitionTest.test_archive_url_inside_html_comment_yields_no_archive_link"
        status: pass
      - kind: unit
        ref: "tests/test_candidates.py#CandidateRecognitionTest.test_malformed_non_rendered_nesting_never_yields_an_archive_link"
        status: pass
      - kind: unit
        ref: "tests/test_candidates.py#CandidateRecognitionTest.test_same_archive_url_moved_to_rendered_text_still_qualifies"
        status: pass
    human_judgment: false
  - id: D2
    description: "Two occurrences of the identical archive URL in one message, whether in plain text or rendered HTML text, count as two links and fail closed as candidate_ambiguous rather than being deduplicated."
    requirement: MAIL-02
    verification:
      - kind: unit
        ref: "tests/test_candidates.py#CandidateRecognitionTest.test_repeated_identical_archive_urls_are_counted_as_two_occurrences"
        status: pass
      - kind: unit
        ref: "tests/test_candidates.py#CandidateRecognitionTest.test_repeated_identical_archive_url_in_rendered_html_text_is_ambiguous"
        status: pass
    human_judgment: false
  - id: D3
    description: "Empty MIME bytes, a message with no body part, and an HTML body with no archive URL each fail closed rather than producing a candidate."
    requirement: MAIL-02
    verification:
      - kind: unit
        ref: "tests/test_candidates.py#CandidateRecognitionTest.test_empty_bytes_mime_fails_closed_before_any_link_extraction"
        status: pass
      - kind: unit
        ref: "tests/test_candidates.py#CandidateRecognitionTest.test_missing_mime_body_fails_closed_as_ambiguous"
        status: pass
      - kind: unit
        ref: "tests/test_candidates.py#CandidateRecognitionTest.test_html_body_with_no_archive_url_fails_closed_as_ambiguous"
        status: pass
    human_judgment: false
  - id: D4
    description: "Archive filename equality is decided on the strictly percent-decoded final path segment compared case-sensitively against the exact literal Order_{ORDER_ID}.zip; an undecodable percent sequence is not treated as an archive link."
    requirement: MAIL-02
    verification:
      - kind: unit
        ref: "tests/test_candidates.py#CandidateRecognitionTest.test_filename_comparison_percent_decodes_once_and_is_case_sensitive"
        status: pass
      - kind: unit
        ref: "tests/test_candidates.py#CandidateRecognitionTest.test_non_strictly_decodable_percent_encoding_is_not_an_archive_link"
        status: pass
    human_judgment: false
  - id: D5
    description: "Archive-link collection order is stable: plain-text occurrences take precedence over HTML, and within HTML, anchor hrefs are collected before rendered-text occurrences."
    requirement: MAIL-02
    verification:
      - kind: unit
        ref: "tests/test_candidates.py#CandidateRecognitionTest.test_plain_text_archive_occurrence_takes_precedence_over_html"
        status: pass
      - kind: unit
        ref: "tests/test_candidates.py#CandidateRecognitionTest.test_html_only_prefers_anchor_hrefs_over_rendered_text"
        status: pass
      - kind: unit
        ref: "tests/test_candidates.py#CandidateRecognitionTest.test_html_only_falls_back_to_rendered_text_when_no_anchor_matches"
        status: pass
    human_judgment: false
  - id: D6
    description: "A complete scan yielding zero candidates fails closed as candidate_none, and a scan yielding exactly one candidate selects that one."
    requirement: MAIL-03
    verification:
      - kind: unit
        ref: "tests/test_candidates.py#CandidateSelectionTest.test_empty_iterable_and_null_input_fail_candidate_none"
        status: pass
      - kind: unit
        ref: "tests/test_candidates.py#CandidateSelectionTest.test_single_element_input_selects_that_element"
        status: pass
    human_judgment: false
  - id: D7
    description: "Equal-timestamp ties are broken on the complete case-sensitive Unicode Graph message ID compared code point by code point, with no normalization, regardless of input order."
    requirement: MAIL-03
    verification:
      - kind: unit
        ref: "tests/test_candidates.py#CandidateSelectionTest.test_equal_timestamp_uses_complete_unicode_graph_id"
        status: pass
      - kind: unit
        ref: "tests/test_candidates.py#CandidateSelectionTest.test_tie_break_ordering_is_stable_across_case_and_normalization_variants"
        status: pass
    human_judgment: false

duration: 15min
completed: 2026-09-09
status: complete
---

# Phase 01 Plan 07: Rendered-Context-Aware Archive-Link Extraction Summary

**`_AnchorCollector` now gates href and text collection behind a clamped non-rendered-element depth counter, closing the `<script>`-content acceptance gap the verifier reproduced, backed by 15 new regressions covering all six MAIL-02/MAIL-03 edge-probe rows this plan owns.**

## Performance

- **Duration:** ~15 min
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments

- `vicmap_acquire/candidates.py`'s `_AnchorCollector` gained `_NON_RENDERED` (a frozenset of 12 non-rendered tag names), a `non_rendered_depth` counter incremented on entering one of those elements and decremented (clamped at zero) on exit, gating both `handle_starttag`'s href collection and `handle_data`'s visible-text collection.
- `handle_comment`, `handle_decl`, `handle_pi`, and `unknown_decl` are explicit no-op overrides so comment and declaration content is never routed into `visible_urls`.
- `extract_html_hrefs`'s docstring now documents the rendered-context restriction it always effectively had for text but previously lacked for hrefs.
- 15 new regressions in `tests/test_candidates.py`: 5 for the core non-rendered suppression behavior (Task 1), and 10 more closing the MAIL-02/MAIL-03 edge-probe rows this plan owns — the 8-tag non-rendered table, 4 malformed-nesting shapes, HTML-rendered-text adjacency, the literal-`b""` and no-archive-URL empty cases, the undecodable-percent-encoding case, anchor-vs-text ordering, `select_candidate`'s single-element case, and permutation-invariant case/normalization tie-break ordering.
- Full suite: 118 tests, all green, no skips (up from the 103-test baseline).

## Task Commits

Each task was committed atomically (TDD RED/GREEN per task):

1. **Task 1: Collect archive URLs only from rendered HTML context** - `a992f6a` (test, RED: 3 of 5 new regressions failed for the intended reason) then `807a291` (feat: `_NON_RENDERED` depth-counter suppression)
2. **Task 2: Non-rendered negatives, malformed nesting, and the MAIL-02/MAIL-03 edge regressions** - `bd7fd35` (test: all 10 new regressions passed immediately against Task 1's implementation; no separate GREEN commit needed)

_Note: Task 2 produced a test-only commit because Task 1's implementation, written directly against the full behavioral specification (non_rendered_depth clamping, CDATA-mode reliance for script/style, comment/declaration no-ops), already satisfied every edge case Task 2 specifies._

## Files Created/Modified

- `vicmap_acquire/candidates.py` - `_NON_RENDERED` frozenset; `_AnchorCollector.non_rendered_depth`, `handle_endtag`, `handle_startendtag`, `handle_comment`, `handle_decl`, `handle_pi`, `unknown_decl`; gated `handle_starttag`/`handle_data`
- `tests/test_candidates.py` - 15 new regressions across `CandidateRecognitionTest` and `CandidateSelectionTest`

## Decisions Made

See `key-decisions` in frontmatter. In short: suppression is a depth counter gating collection at the source (not a post-hoc filter); the change is scoped exactly to `_AnchorCollector`; and the literal-`b""` MIME test asserts the real system behavior (`OriginUnauthenticated`, since 01-06's origin check runs before link extraction) rather than the more generic `CandidateAmbiguous` the plan's `<behavior>` prose implied — both are closed failures satisfying the `must_haves.truths` wording.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Asserted the actual exception class for literal-`b""` MIME instead of the plan's implied one**
- **Found during:** Task 2 test authoring
- **Issue:** The plan's `<behavior>`/`<acceptance_criteria>` text for Task 2 states `b""` MIME "raises `CandidateAmbiguous`". Given 01-06's `verify_authenticated_origin` call runs before `_mime_archive_links` in `recognize_candidate`, and empty bytes fail that check first (no `Authentication-Results` header can exist), the actual raised exception is `OriginUnauthenticated` (code `origin_unauthenticated`), not `CandidateAmbiguous`. This mirrors the pre-existing `test_malformed_mime_fails_origin_verification_before_link_extraction` pattern from 01-06.
- **Fix:** Wrote the test (`test_empty_bytes_mime_fails_closed_before_any_link_extraction`) asserting the real, correctly fail-closed behavior (`OriginUnauthenticated`) rather than forcing an incorrect assertion to match the plan's literal wording. The plan's authoritative `must_haves.truths` bullet only requires the message "fail closed rather than producing a candidate" — satisfied by either exception class.
- **Files modified:** `tests/test_candidates.py`
- **Verification:** Test passes against the actual (unmodified in this regard) `recognize_candidate` call order.
- **Committed in:** `bd7fd35` (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (1 bug in the plan's prose, not the implementation)
**Impact on plan:** No code behavior was changed to accommodate this; the fix was in test authorship to match the codebase's actual (and correctly designed) fail-closed order of checks established in 01-06. No scope creep.

## Known Stubs

None - no stubs introduced by this plan.

## Issues Encountered

None beyond the auto-fixed deviation above.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Verification gap G-04's two `missing` bullets (non-rendered HTML negatives, malformed-nesting regressions) are closed with committed automated regressions.
- All six MAIL-02/MAIL-03 edge-probe rows this plan owns (adjacency, empty, encoding, ordering, selection-empty, selection-encoding) are each backed by a passing test.
- `requirements-completed` lists `MAIL-02`/`MAIL-03` per this plan's frontmatter, but `REQUIREMENTS.md` will not flip them to `Complete` yet: the shared-ID gate (`gsd-tools requirements ready-ids`) returned 0/2 ready, since sibling gap-closure plans 01-08 through 01-11 in this phase also declare these IDs and have not yet produced summaries. They will mark complete once the last declaring plan finishes.
- Remaining phase 01 gap-closure work (01-08 through 01-11) is unblocked and can proceed; this plan touched only `vicmap_acquire/candidates.py` and `tests/test_candidates.py` per its declared scope.

---
*Phase: 01-trusted-graph-acquisition*
*Completed: 2026-09-09*

## Self-Check: PASSED

- FOUND: vicmap_acquire/candidates.py contains `_NON_RENDERED` and `def handle_endtag(`
- FOUND commit: a992f6a (test, RED)
- FOUND commit: 807a291 (feat, GREEN)
- FOUND commit: bd7fd35 (test, Task 2 edge coverage)
- `tests.test_candidates` alone → 40 tests, OK
- Full deterministic suite: `nix develop path:. -c python -m unittest discover -s tests -p 'test_*.py' -v` → 118 tests, OK, no skips
- Re-ran all task-level `<acceptance_criteria>` greps and behavioral assertions: all pass (see plan verification above)
- `vicmap_acquire/candidates.py` confirmed to import nothing from `read_mailbox` or `vicmap_acquire/download`
