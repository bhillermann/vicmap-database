---
phase: 01-trusted-graph-acquisition
plan: 12
subsystem: acquisition
tags: [python, html-parser, candidate-recognition, void-elements, email, defect-fix]

requires:
  - phase: 01-07
    provides: Rendered-context-aware HTML archive-link extraction and the non-rendered depth-counter design being repaired
provides:
  - Void-element-safe non-rendered suppression in `_AnchorCollector`, so a bare (unclosed) `<meta>`/`<link>` in a document `<head>` can no longer leave the suppression counter permanently raised
  - Committed regressions built from realistic bare-spelling email head markup, proving the live-message defect traced during 01-11 Task 2 is closed
affects: [trusted-graph-acquisition, evidence]

actuals:
  tokens: 2562
  tasks: 2
  commits: 3

tech-stack:
  added: []
  patterns:
    - "Void-element carve-out on the existing non-rendered depth counter: a tag is suppression-raising only when it is in _NON_RENDERED AND NOT in _VOID_ELEMENTS, applied identically in handle_starttag, handle_endtag, and handle_startendtag so bare and self-closing spellings of the same void element behave identically"

key-files:
  created: []
  modified:
    - vicmap_acquire/candidates.py
    - tests/test_candidates.py

key-decisions:
  - "Kept meta and link in _NON_RENDERED and added a separate _VOID_ELEMENTS frozenset rather than removing them from _NON_RENDERED — the two facts (never rendered; cannot contain content) are independent and stay independently testable."
  - "Applied the combined _NON_RENDERED-and-not-_VOID_ELEMENTS test in handle_endtag as well as handle_starttag/handle_startendtag, so a stray void end tag (malformed markup) can never lower the counter and expose enclosing suppressed content."
  - "Narrowed the pre-existing 01-07 8-tag parametrized negative (test_every_non_rendered_tag_suppresses_its_sole_archive_url, renamed to test_every_non_rendered_container_tag_suppresses_its_sole_archive_url) to exclude meta: a void element has no content model, so <meta>text</meta> can no longer be read as 'text contained inside meta' the way <script>text</script> genuinely contains text. This exact narrowing is what the plan's own must_haves.truths bullet 3 specifies (its retained-guarantee list already omits meta and link). A new test (test_void_elements_do_not_suppress_paired_content_even_when_explicitly_closed) replaces the removed coverage with the corrected assertion."
  - "The 'stray </meta> exposes enclosing content' regression nests the stray end tag inside <noscript> rather than the plan's literal <script> wording: Python's html.parser scans script/style content as raw CDATA text searching only for the tag's own literal terminator, so a </meta> written inside <script>...</script> is never parsed as a real end tag at all (handle_endtag is never called) — it is inert by construction, proven directly against cpython's parser before writing the test. <noscript> is a genuine (non-CDATA) non-rendered container that actually exercises handle_endtag's void-element test, which is what the regression needs to prove anything."

patterns-established:
  - "Void-element carve-out on non-rendered suppression: any future non-rendered tag added to _NON_RENDERED must also be checked against _VOID_ELEMENTS before it is allowed to gate the counter, or the same permanent-suppression defect recurs for the next void tag added to the set."

requirements-completed: [MAIL-02]

coverage:
  - id: D1
    description: "Void elements (meta, link) named in the non-rendered set no longer raise the suppression counter in bare-spelling form, so a document head with several bare meta/link tags no longer permanently suppresses the message body."
    requirement: MAIL-02
    verification:
      - kind: unit
        ref: "tests/test_candidates.py#CandidateRecognitionTest.test_bare_void_elements_in_realistic_head_do_not_suppress_the_body"
        status: pass
      - kind: unit
        ref: "tests/test_candidates.py#CandidateRecognitionTest.test_suppression_counter_returns_to_zero_after_realistic_bare_head"
        status: pass
      - kind: unit
        ref: "tests/test_candidates.py#CandidateRecognitionTest.test_bare_and_self_closing_void_spellings_are_equivalent"
        status: pass
    human_judgment: false
  - id: D2
    description: "A stray void end tag (malformed markup) cannot lower the suppression counter and expose content inside an enclosing non-rendered container."
    requirement: MAIL-02
    verification:
      - kind: unit
        ref: "tests/test_candidates.py#CandidateRecognitionTest.test_stray_void_end_tag_does_not_lower_the_counter"
        status: pass
    human_judgment: false
  - id: D3
    description: "Every 01-07 non-rendered suppression guarantee for genuine containers (script, style, template, noscript, title, object, iframe, head, comments, malformed nesting) is retained unchanged, and a void element cannot suppress paired-looking content it structurally cannot contain."
    requirement: MAIL-02
    verification:
      - kind: unit
        ref: "tests/test_candidates.py#CandidateRecognitionTest.test_every_non_rendered_container_tag_suppresses_its_sole_archive_url"
        status: pass
      - kind: unit
        ref: "tests/test_candidates.py#CandidateRecognitionTest.test_void_elements_do_not_suppress_paired_content_even_when_explicitly_closed"
        status: pass
      - kind: unit
        ref: "tests/test_candidates.py#CandidateRecognitionTest.test_archive_url_inside_title_or_style_within_head_still_yields_no_link"
        status: pass
    human_judgment: false

duration: 20min
completed: 2026-09-09
status: complete
---

# Phase 01 Plan 12: Void-Element-Safe Non-Rendered Suppression Summary

**Excluding HTML void elements (`meta`, `link`) from the `_AnchorCollector` suppression counter closes the permanent-suppression defect 01-07 introduced, verified against the exact bare-spelling counter trace recorded from the live Vicmap DataShare ready message.**

## Performance

- **Duration:** ~20 min
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments

- Added `_VOID_ELEMENTS` (the 14 HTML void elements) to `vicmap_acquire/candidates.py`; `_AnchorCollector.handle_starttag`, `handle_endtag`, and `handle_startendtag` now treat a tag as suppression-raising only when it is in `_NON_RENDERED` **and not** in `_VOID_ELEMENTS`.
- A bare (unclosed) `<meta>`/`<link>` in a document `<head>` no longer increments `non_rendered_depth`; the counter now returns to zero after a well-formed document exactly as it did against the live message's actual head markup (reproduced and re-verified directly: `final depth after parse: 0`).
- A stray void end tag can no longer decrement the counter and expose enclosing suppressed content (`handle_endtag` applies the same combined test).
- 6 new regressions in `tests/test_candidates.py`: the RED defect proof (bare-spelling head suppresses the body — pre-fix), a void-paired-content proof (replacing narrowed coverage), a counter-returns-to-zero proof, a bare/self-closing equivalence proof, a stray-end-tag proof, and a head-nested title/style retained-suppression proof.
- Full suite: 171 tests, all green, no skips (up from the 165-test baseline).

## Task Commits

Each task was committed atomically (TDD RED/GREEN per task):

1. **Task 1: Void elements never raise the suppression counter** - `05cfc9b` (test, RED: bare-spelling head defect proof failed for the intended reason — `CandidateAmbiguous` raised) then `ca014ba` (feat: `_VOID_ELEMENTS` carve-out; narrowed and replaced the affected pre-existing 01-07 negative)
2. **Task 2: Regressions built from realistic email head markup** - `da633a8` (test: 4 new regressions; 3 of 4 confirmed to fail against the pre-Task-1 implementation before being restored to the fixed state, the 4th is a retention proof not expected to fail pre-fix)

_Note: Task 2 produced a test-only commit, following the same pattern as 01-07 Task 2 — Task 1's implementation already satisfied every additional case Task 2 specifies._

## Files Created/Modified

- `vicmap_acquire/candidates.py` - `_VOID_ELEMENTS` frozenset; combined non-rendered-and-not-void test applied in `handle_starttag`, `handle_endtag`, `handle_startendtag`
- `tests/test_candidates.py` - `_bare_email_head()` helper; 6 new regressions; one pre-existing 01-07 test narrowed and its removed coverage replaced by a corrected assertion

## Decisions Made

See `key-decisions` in frontmatter. In short: `meta`/`link` stay in `_NON_RENDERED` (they are still non-rendered) with a new, independent `_VOID_ELEMENTS` test controlling suppression; the combined test is applied uniformly across all three HTMLParser hooks; the pre-existing 8-tag negative was narrowed to real containers per the plan's own must_haves narrowing, with replacement coverage added; and the "stray end tag" regression uses `<noscript>` rather than `<script>` because Python's `html.parser` scans script/style as raw CDATA and never calls `handle_endtag` for tags written inside them.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Narrowed the 01-07 8-tag non-rendered negative to exclude `meta`**
- **Found during:** Task 1 GREEN phase, running the full suite after implementing `_VOID_ELEMENTS`
- **Issue:** `test_every_non_rendered_tag_suppresses_its_sole_archive_url` asserted `<meta>{url}</meta>` suppresses the URL as "contained" content. With the corrected void-element semantics, `meta` cannot contain anything, so this specific assertion encoded exactly the incorrect assumption the defect fix is repairing (the plan's own `must_haves.truths` bullet 3 already omits `meta`/`link` from the retained-guarantee list, so this narrowing was anticipated, not incidental).
- **Fix:** Removed `meta` from the tag tuple (renaming the test to `test_every_non_rendered_container_tag_suppresses_its_sole_archive_url` for accuracy), and added `test_void_elements_do_not_suppress_paired_content_even_when_explicitly_closed` asserting the corrected, opposite behavior for `meta` and `link` — net test coverage increased, not decreased.
- **Files modified:** `tests/test_candidates.py`
- **Verification:** Full suite green (171 tests) after the change; the new test explicitly proves the corrected behavior it replaces coverage for.
- **Committed in:** `ca014ba` (Task 1 GREEN commit)

**2. [Rule 1 - Bug] Used `<noscript>` instead of the plan's literal `<script>` wording for the stray-end-tag regression**
- **Found during:** Task 2, while designing the stray-`</meta>`-end-tag regression
- **Issue:** The plan's Task 2 behavior bullet asks for a regression proving a stray `</meta>` cannot lower the counter and expose content "inside an enclosing `script`". Empirically verifying against `html.parser` (cpython's `CDATA_CONTENT_ELEMENTS = ("script", "style")`) shows that content inside `<script>...</script>` is scanned as raw text searching only for the literal `</script>` terminator — a `</meta>` written there is never parsed as a tag at all, so `handle_endtag("meta")` is never called and the scenario cannot exercise the code path under test.
- **Fix:** Used `<noscript>` — a genuine, non-CDATA non-rendered container also in `_NON_RENDERED` — which Python's `html.parser` confirmed does parse a nested `</meta>` as a real end tag, correctly exercising `handle_endtag`'s combined test.
- **Files modified:** `tests/test_candidates.py`
- **Verification:** Confirmed via direct interactive testing of `html.parser` behavior for both `<script>` and `<noscript>` containers before writing the test; the resulting test fails against the pre-Task-1 implementation and passes against the fix.
- **Committed in:** `da633a8` (Task 2 commit)

---

**Total deviations:** 2 auto-fixed (2 bugs in a pre-existing test's assumption and the plan's illustrative wording, not the corrected implementation)
**Impact on plan:** Both auto-fixes were necessary to make the fix internally consistent and to make the stray-end-tag regression actually exercise the code path it claims to test. No scope creep — no other recognition behavior (D-04 plain-text-first/HTML-fallback, D-05 exactly-one-link, non-dedup of repeated identical URLs) was touched.

## Known Stubs

None - no stubs introduced by this plan.

## Issues Encountered

None beyond the two auto-fixed deviations above.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- The defect confirmed live during 01-11 Task 2 (a genuine ready message closing `candidate_ambiguous` due to the permanently-raised counter) is closed: the exact live-message counter trace from the plan's evidence section (`final depth after parse: 0` after excluding void elements) was independently reproduced and verified against the fixed implementation.
- `requirements-completed` lists `MAIL-02` per this plan's frontmatter; `REQUIREMENTS.md` will only flip it to `Complete` once the shared-ID gate (`gsd-tools requirements ready-ids`) reports it ready — sibling plan 01-11 in this phase also declares `MAIL-02` and has not yet produced a summary (it is the blocked plan this fix unblocks).
- 01-11 Task 2/3 can now be retried against the corrected implementation; no policy/allowlist was relaxed and no artifact host was contacted by this plan.

---
*Phase: 01-trusted-graph-acquisition*
*Completed: 2026-09-09*

## Self-Check: PASSED

- FOUND: vicmap_acquire/candidates.py contains `_VOID_ELEMENTS` and the combined test in `handle_endtag`
- FOUND commit: 05cfc9b (test, RED)
- FOUND commit: ca014ba (feat, GREEN)
- FOUND commit: da633a8 (test, Task 2 broader regressions)
- `tests.test_candidates` alone → 46 tests, OK
- Full deterministic suite: `OPNIX_ENV_DISABLE=1 nix develop --impure --no-write-lock-file path:. --command python -m unittest discover -s tests` → 171 tests, OK, no skips
- Re-ran the plan's exact live-message counter-trace shape directly against `_AnchorCollector`: `final depth after parse: 0` (matches plan's stated post-fix expectation)
- Re-ran all task-level `<acceptance_criteria>` assertions: all pass (see Deviations and Task Commits above)
