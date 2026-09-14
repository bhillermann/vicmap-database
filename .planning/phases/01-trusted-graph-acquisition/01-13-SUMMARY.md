---
phase: 01-trusted-graph-acquisition
plan: 13
subsystem: acquisition
tags: [python, html-parser, candidate-recognition, dmarc, email, gap-closure]

requires:
  - phase: 01-12
    provides: Void-element-safe non-rendered suppression in _AnchorCollector (_VOID_ELEMENTS carve-out)
provides:
  - Self-closing syntax on a non-void element (script/style/head/noscript/template/title) no longer closes it, matching HTML5 tokenization
  - head implicitly closes on a <body> start tag, so an omitted </head> can never permanently strand suppression
  - DMARC header.from alignment fails closed on absence, symmetric with the existing dkim check
affects: [trusted-graph-acquisition, evidence]

actuals:
  tokens: 3374
  tasks: 3
  commits: 6

tech-stack:
  added: []
  patterns:
    - "handle_startendtag routes non-void tags through handle_starttag only (never handle_endtag): HTML5 ignores a trailing '/' on any non-void, non-foreign element, so the element stays open exactly as an ordinary unclosed start tag would"
    - "One-shot implicit-closure flag (_head_implicit_close_applied) on a <body> start tag: models the single insertion-mode transition a flat depth counter can safely express without a full tree-construction rewrite"
    - "Symmetric fail-closed alignment check: an absent, blank, or unparseable property takes the identical rejection branch as a present mismatched one (`not value or value != expected`), so absence is never more permissive than a mismatch"

key-files:
  created: []
  modified:
    - vicmap_acquire/candidates.py
    - vicmap_acquire/origin.py
    - tests/test_candidates.py
    - tests/test_origin.py

key-decisions:
  - "Task 2 tried approach (a) first (remove head from _NON_RENDERED entirely) as the plan preferred, but a regression proved it loses a guarantee: self-closing <head/> immediately followed by a URL (no <body> tag at all) would then leak unsuppressed, reopening exactly the CR-01 shape Task 1 had just closed for head. Switched to approach (b): head stays in _NON_RENDERED, and a <body> start tag decrements its contribution exactly once via a one-shot flag, mirroring the HTML5 'in head' insertion mode's implicit close without needing a full stack-based tree-construction rewrite."
  - "The one-shot flag fires on the first <body> start tag seen regardless of whether head was ever opened, and is clamped at zero (max(0, depth-1)) so it can never push the counter negative or matter more than once. This is a deliberate, narrower fix than a full open-container stack (which the review's own CR-02 finding names as the 'at minimum' complete fix) — accepted per the plan's explicit preference for the narrower approach unless a required regression fails."
  - "'Blank or whitespace-only header.from' collapses to a single reachable test shape: the Authentication-Results tokenizer splits each segment on whitespace before a token's value is ever read, so a value consisting purely of whitespace can never survive as non-empty token content — it is only reachable as an explicit empty-quoted value or a bare trailing '=' with nothing after, both of which resolve to the same empty string. Both spellings are asserted to hit the same rejection."
  - "DMARC header.from alignment stays an exact string-equality check (not DKIM's parent-domain suffix alignment) — unchanged from pre-existing behavior; the fix only closes the absence-is-more-permissive-than-mismatch gap, not the alignment semantics."

patterns-established:
  - "Any future self-closing-tag handling in _AnchorCollector must route through handle_starttag only for non-void elements — calling handle_endtag from handle_startendtag reintroduces the net-zero-depth leak this plan closed."
  - "Any future fail-closed alignment check (present-vs-absent asymmetry) should use the `not value or value != expected` shape established here and in the pre-existing dkim branch, rather than `value is not None and value != expected`, which silently skips validation when the property is absent."

requirements-completed: [MAIL-02]

coverage:
  - id: D1
    description: "Self-closing syntax on a non-void element (script, style, head, noscript, template, title) no longer closes it; a URL following such a tag with no real end tag yields zero archive links, matching the CR-01 reproduction exactly."
    requirement: MAIL-02
    verification:
      - kind: unit
        ref: "tests/test_candidates.py#CandidateRecognitionTest.test_self_closing_syntax_on_non_void_elements_does_not_close_them"
        status: pass
      - kind: unit
        ref: "tests/test_candidates.py#CandidateRecognitionTest.test_self_closing_script_with_src_and_real_end_tag_control_is_still_suppressed"
        status: pass
      - kind: unit
        ref: "tests/test_candidates.py#CandidateRecognitionTest.test_self_closing_anchor_still_contributes_its_href_attribute"
        status: pass
    human_judgment: false
  - id: D2
    description: "A document whose <head> is never explicitly closed still yields exactly one archive link from body content, because a <body> start tag implicitly closes head; script/style/title suppression inside an unclosed head, and genuine unclosed-script swallowing, are both retained."
    requirement: MAIL-02
    verification:
      - kind: unit
        ref: "tests/test_candidates.py#CandidateRecognitionTest.test_head_implicitly_closes_when_body_content_begins"
        status: pass
      - kind: unit
        ref: "tests/test_candidates.py#CandidateRecognitionTest.test_title_inside_unclosed_head_still_suppresses_its_own_content"
        status: pass
      - kind: unit
        ref: "tests/test_candidates.py#CandidateRecognitionTest.test_style_inside_unclosed_head_still_suppresses_its_own_content"
        status: pass
      - kind: unit
        ref: "tests/test_candidates.py#CandidateRecognitionTest.test_unclosed_mid_body_script_still_suppresses_the_remainder"
        status: pass
      - kind: unit
        ref: "tests/test_candidates.py#CandidateRecognitionTest.test_suppression_counter_returns_to_zero_after_well_formed_document"
        status: pass
    human_judgment: false
  - id: D3
    description: "DMARC header.from alignment fails closed symmetrically with dkim: absent, blank, and unparseable header.from are each rejected as OriginUnauthenticated, while a present correctly aligned value (matching the live-observed dkim=pass/dmarc=pass/compauth=pass shape) is still accepted."
    requirement: MAIL-02
    verification:
      - kind: unit
        ref: "tests/test_origin.py#HardenedOriginParserTest.test_dmarc_header_from_absent_entirely_is_rejected"
        status: pass
      - kind: unit
        ref: "tests/test_origin.py#HardenedOriginParserTest.test_dmarc_header_from_blank_or_whitespace_only_is_rejected"
        status: pass
      - kind: unit
        ref: "tests/test_origin.py#HardenedOriginParserTest.test_dmarc_header_from_unparseable_as_a_domain_is_rejected"
        status: pass
      - kind: unit
        ref: "tests/test_origin.py#HardenedOriginParserTest.test_dmarc_header_from_present_and_aligned_is_still_accepted"
        status: pass
      - kind: unit
        ref: "tests/test_origin.py#HardenedOriginParserTest.test_no_raised_error_leaks_seeded_private_mime_content"
        status: pass
    human_judgment: false

duration: 13min
completed: 2026-09-14
status: complete
---

# Phase 01 Plan 13: Gap-Closure — Self-Closing Suppression, Implicit Head Closure, Symmetric DMARC Summary

**Closed CR-01 (bogus self-closing syntax leaking suppressed content), CR-02 (omitted `</head>` stranding suppression), and WR-01 (DMARC `header.from` absence more permissive than a mismatch) from the phase 01 gap-closure code review, each independently reproduced and confirmed fixed against the exact review-reported markup.**

## Performance

- **Duration:** ~13 min
- **Started:** 2026-09-14T00:30:31Z
- **Completed:** 2026-09-14T00:43:18Z
- **Tasks:** 3
- **Files modified:** 4

## Accomplishments

- `_AnchorCollector.handle_startendtag` no longer treats self-closing syntax as an immediate close-then-open for non-void elements; a self-closed `script`/`style`/`head`/`noscript`/`template`/`title` now stays suppressed exactly like an ordinary unclosed start tag, closing CR-01.
- A `<body>` start tag now implicitly closes an open `head` (decremented once via a one-shot flag), so a `<head>` with no `</head>` at all no longer permanently silences the rest of the message body, closing CR-02.
- `verify_authenticated_origin`'s DMARC `header.from` alignment check is now symmetric with the pre-existing `dkim` check: absent, blank, or unparseable `header.from` all take the same fail-closed path as a present mismatched value, closing WR-01.
- 10 new regressions across `tests/test_candidates.py` and `tests/test_origin.py`, each built from realistic markup/header shapes (omitted end tags, self-closing spellings on non-void elements, the live-observed verdict/property shape) rather than tidy synthetic fixtures.
- Full suite: 184 tests, all green, no skips (up from the 171-test baseline; net +13 including 3 controls/retained-guarantee assertions added alongside the RED-proving tests).

## Task Commits

Each task was committed atomically (TDD RED/GREEN per task; no REFACTOR commit needed — each GREEN implementation was already minimal):

1. **Task 1: Self-closing syntax never closes a non-void element** - `3ac1fc6` (test, RED: 6 CR-01 shapes fail for the intended reason — no exception raised, meaning content leaked) then `69d4c58` (feat: `handle_startendtag` routes non-void tags through `handle_starttag` only)
2. **Task 2: Suppression cannot be stranded by an omitted end tag** - `a4d2b19` (test, RED: CR-02 repro raises `CandidateAmbiguous` unexpectedly; 5 retained-guarantee tests already pass, isolating exactly the CR-02 gap) then `036816c` (feat: one-shot `<body>`-triggered implicit head closure)
3. **Task 3: DMARC header.from alignment fails closed** - `f1cfd96` (test, RED: absent `header.from` returns a candidate instead of raising; blank/unparseable/aligned cases already pass) then `e38b03e` (feat: symmetric `not header_from or header_from != from_domain` check)

## Files Created/Modified

- `vicmap_acquire/candidates.py` - `handle_startendtag` no longer calls `handle_endtag` for non-void tags; `_AnchorCollector` gained a `_head_implicit_close_applied` one-shot flag consumed in `handle_starttag` on a `body` start tag
- `vicmap_acquire/origin.py` - DMARC `header.from` check changed from `header_from is not None and header_from != from_domain` to `not header_from or header_from != from_domain`
- `tests/test_candidates.py` - 9 new regressions: 6 CR-01 self-closing-leak proofs plus control and self-closing-anchor retention, and 6 CR-02 proofs (repro, explicit-close control, title/style-in-head retention, unclosed-script retention, counter-reset)
- `tests/test_origin.py` - 4 new regressions: absent/blank/unparseable `header.from` rejections plus a live-shape acceptance proof

## Decisions Made

See `key-decisions` in frontmatter. In short: Task 2 tried the plan's preferred approach (a) first (dropping `head` from `_NON_RENDERED` entirely), found via regression that it reopens CR-01's self-closing-`<head/>` guarantee (with no `<body>` tag ever appearing, there's no implicit-closure trigger to fall back on), and switched to approach (b) — a narrower, one-shot `<body>`-triggered decrement — exactly as the plan anticipated ("prefer (a) unless a regression shows it loses a guarantee").

## Deviations from Plan

None - plan executed exactly as written, including the explicit fallback from approach (a) to approach (b) in Task 2, which the plan itself pre-authorized ("Take the narrower of these two approaches... Prefer (a) unless a regression shows it loses a guarantee").

## Known Stubs

None - no stubs introduced by this plan.

## Issues Encountered

- Task 2's first attempt (approach a) briefly broke `test_self_closing_syntax_on_non_void_elements_does_not_close_them` (tag='head') — caught immediately by re-running the task 1 regression suite before committing, and resolved by switching to approach (b) per the plan's own guidance. No incorrect code was committed; the failing approach was reverted before any GREEN commit.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- All three findings from `01-REVIEW-GAP-CLOSURE.md` (CR-01, CR-02, WR-01) are closed and independently re-verified against the exact reproduction snippets recorded in that review and in this plan's "Reproductions, confirmed by the orchestrator" section.
- WR-02 (MSO conditional comments), WR-03 (missing SafeFailure correlation fields), IN-01, and IN-02 from the same review remain open — they were explicitly out of scope for this plan (Warnings/Info severity, not Critical) and are not blocking.
- `requirements-completed` lists `MAIL-02`, matching sibling gap-closure plans 01-11/01-12 in this phase; `REQUIREMENTS.md` will reflect completion once the shared-ID gate reports it ready.

---
*Phase: 01-trusted-graph-acquisition*
*Completed: 2026-09-14*

## Self-Check: PASSED

- FOUND: vicmap_acquire/candidates.py contains the updated `handle_startendtag` (routes through `handle_starttag` only) and `_head_implicit_close_applied`
- FOUND: vicmap_acquire/origin.py contains `not header_from or header_from != from_domain`
- FOUND commit: 3ac1fc6 (test, RED — Task 1)
- FOUND commit: 69d4c58 (feat, GREEN — Task 1)
- FOUND commit: a4d2b19 (test, RED — Task 2)
- FOUND commit: 036816c (feat, GREEN — Task 2)
- FOUND commit: f1cfd96 (test, RED — Task 3)
- FOUND commit: e38b03e (feat, GREEN — Task 3)
- Full deterministic suite: `OPNIX_ENV_DISABLE=1 nix develop --impure --no-write-lock-file path:. --command python -m unittest discover -s tests` → 184 tests, OK, no skips
- Re-ran the plan's exact CR-01 reproduction set (script/style/head/noscript/template self-closing + control) directly against `_extract_html_urls`: all five shapes → `[]`, control → `[]`
- Re-ran the plan's exact CR-02 reproduction directly against `extract_html_hrefs`: repro → exactly one archive link, explicit-`</head>` control → the same one link
- Re-ran the plan's exact WR-01 exploit directly against `verify_authenticated_origin`: now raises `OriginUnauthenticated` (previously returned the sender address)
- Re-ran all task-level `<acceptance_criteria>` assertions: all pass (see Task Commits and Accomplishments above)
