---
phase: 01-trusted-graph-acquisition
plan: 14
subsystem: acquisition
tags: [python, html5lib, html-parser, candidate-recognition, differential-testing, tdd, email]

requires:
  - phase: 01-13
    provides: Self-closing suppression, one-shot implicit head closure, and symmetric DMARC fail-closed (the flat counter model this plan replaces)
provides:
  - Tree-based rendered-visibility decision in `vicmap_acquire/candidates.py`, replacing the flat suppression counter that survived four review passes (01-07's original counter, CR-01, CR-02, and a fourth false-positive report)
  - A permanent differential fuzz test (`tests/test_html_visibility_differential.py`) comparing extraction against an independently-authored html5lib oracle walk, asserting zero leak-direction disagreements across 2000 seeded documents
  - html5lib added to the pinned Nix devShell (flake.nix, left untracked per the plan's own instruction -- tracking it is a separate operator decision)
  - A structural regression locking the real Vicmap DataShare ready message's shape (HTML-only body, bare meta/link head, interior style block, URL in visible body text) to exactly one archive link
  - Re-confirmed, read-only, that live recognition against the real mailbox still selects exactly one candidate whose artifact URL matches the configured trusted prefix, with zero downloads performed
affects: [trusted-graph-acquisition, evidence]

actuals:
  tokens: 8400
  tasks: 4
  commits: 4
plan_head_before: bafe682ec22c795e0315194e3e48cbf367cc4ad2

tech-stack:
  added: [html5lib (via nixpkgs, pinned flake input, hash-verified by Nix)]
  patterns:
    - "Visibility inherited down a real HTML5 parse tree via a boolean carried through recursion (`_walk_visible`), rather than approximated by an integer depth counter over a raw tokenizer -- tree-construction facts (implicit closure, mis-nesting, insertion-mode quirks) are decided by html5lib itself, not re-derived one patched shape at a time."
    - "A node's own hidden state (`own_hidden`) gates its own text and any `a` href; a child's `tail` -- text between the child's end tag and the next sibling -- is gated by the PARENT's hidden state, not the child's, matching the real HTML5 fact that text after `</script>` is rendered even though the script itself is not."
    - "Differential oracle testing: a fuzz generator over a small tag/void/comment vocabulary, seeded for reproducibility, compared against an oracle walk deliberately written independently of the implementation (different traversal shape, its own hidden-tag set, no shared helpers) so the test cannot share the implementation's blind spot."

key-files:
  created:
    - tests/test_html_visibility_differential.py
  modified:
    - vicmap_acquire/candidates.py
    - tests/test_candidates.py
    - flake.nix (untracked -- see Decisions Made)

key-decisions:
  - "html5lib is the new spec-compliant parser, added to the pinned Nix devShell exactly as the plan's supply-chain disposition specifies: sourced from nixpkgs through the existing flake input, hash-verified by Nix, no pip/npm/cargo install at any point."
  - "flake.nix and flake.lock were edited but deliberately left ungit-added, per the plan's explicit instruction: whether to track them is the operator's separate decision, and bundling it here would make an unrelated change to how the whole project is built."
  - "The RED test for Task 2 (test_stray_body_tag_does_not_implicitly_close_an_open_noscript) was discovered empirically by fuzzing the pre-01-14 counter implementation against an html5lib oracle rather than hand-derived: the 01-13 one-shot <body> decrement closes ANY currently-open suppression on the first <body> tag, not just head specifically -- so it wrongly closes an open <noscript> too, a genuine leak a real parser never produces."
  - "Four pre-existing tests (from the 01-07/01-12/01-13 era) encoded assumptions a real HTML5 parser disproves and were corrected, not weakened: a standalone, document-initial <noscript> has its own 'in head noscript' insertion-mode quirk that auto-closes it on any following text (irrelevant to the suppression guarantee those tests intended, so they were re-anchored in an explicit <body> context); and <head> can NEVER hold free text under any spelling (bare, self-closed, or explicitly closed) -- the pre-rewrite 'self-closing head suppresses trailing text' guarantee was an artifact of the counter, not a fact about real HTML5 parsing, so it was replaced with a new test asserting the true behavior. See Deviations."
  - "The differential test's RED evidence was gathered by pointing the identical, already-written test at a frozen snapshot of the pre-01-14 counter implementation (24/2000 leak-direction disagreements), rather than at not-yet-written production code -- the corrected implementation was already committed by Task 2, so Task 3's role is locking in that correctness with a test proven to have teeth against the class of bug it replaces."

requirements-completed: [MAIL-02]

coverage:
  - id: D1
    description: "Visibility (which HTML content is rendered to a reader) is decided by parsing with html5lib and inheriting hidden-ness down the resulting parse tree, replacing the flat suppression-counter approximation. Every 01-07/01-12/01-13 guarantee this must preserve (script/style/template/noscript/title/object/iframe/head suppression, comment exclusion, exactly-one-link and non-deduplication rules, collection order) still holds."
    requirement: MAIL-02
    verification:
      - kind: unit
        ref: "tests/test_candidates.py#CandidateRecognitionTest (57 tests in this class, all passing)"
        status: pass
      - kind: unit
        ref: "tests/test_candidates.py#CandidateRecognitionTest.test_stray_body_tag_does_not_implicitly_close_an_open_noscript"
        status: pass
    human_judgment: false
  - id: D2
    description: "A differential fuzz test compares extraction against an independently-authored html5lib oracle over 2000 seeded documents (seed 20260914) and fails on any leak-direction disagreement. The same test, pointed at the pre-01-14 implementation, finds 24/2000 leak disagreements -- proof the test has real teeth against the exact defect class that survived four review passes."
    requirement: MAIL-02
    verification:
      - kind: unit
        ref: "tests/test_html_visibility_differential.py#HtmlVisibilityDifferentialTest.test_zero_leak_direction_disagreements_across_the_seeded_corpus"
        status: pass
    human_judgment: false
  - id: D3
    description: "The genuine Vicmap DataShare ready message's structural shape (HTML-only body, bare meta/link head, interior style block, URL in visible body text) still yields exactly one archive link, and live recognition against the real mailbox, read-only, confirms the same: exactly one candidate selected with an artifact URL matching the configured trusted prefix, zero downloads performed."
    requirement: MAIL-02
    verification:
      - kind: unit
        ref: "tests/test_candidates.py#CandidateRecognitionTest.test_real_ready_message_structural_shape_yields_exactly_one_link"
        status: pass
      - kind: manual_procedural
        ref: "read-only live scan (recognize_candidate + select_candidate, download_artifact never invoked): CANDIDATE_COUNT=2, SELECTION_SUCCEEDED=True, ORDER_ID=OK0VUZ, PREFIX_MATCH=True"
        status: pass
    human_judgment: false
  - id: D4
    description: "html5lib is supplied by the pinned Nix devShell (nixpkgs, hash-verified), and both it and the pre-existing python-o365 import successfully; no other flake change was made; flake.nix/flake.lock remain untracked per the plan's instruction."
    requirement: MAIL-02
    verification:
      - kind: other
        ref: "nix develop --impure --no-write-lock-file path:. --command python -c \"import html5lib, O365; print(html5lib.__version__)\" -> 1.2-dev"
        status: pass
    human_judgment: false

duration: 27min
completed: 2026-09-14
status: complete
---

# Phase 01 Plan 14: Tree-Based Rendered-Visibility Extraction Summary

**Replaced the flat suppression counter in `candidates.py` with html5lib tree-inherited visibility, backed by a 2000-document differential fuzz against an independently-written oracle (24/2000 leaks proven against the old implementation, 0/2000 against the new one), and re-confirmed the real Vicmap DataShare message and live mailbox both still recognize exactly one archive link.**

## Performance

- **Duration:** ~27 min
- **Started:** 2026-09-14T02:21:31Z
- **Completed:** 2026-09-14T02:44:55Z
- **Tasks:** 4
- **Files modified:** 4 (flake.nix untracked; candidates.py, test_candidates.py, and the new differential test file committed)

## Accomplishments

- `vicmap_acquire/candidates.py` now parses HTML with `html5lib.parse(html, namespaceHTMLElements=False)` and decides visibility by inheriting a `hidden` boolean down the real parse tree (`_walk_visible`) from a `_HIDDEN_ELEMENTS` frozenset, instead of approximating tree-construction facts with an integer depth counter over a raw tokenizer.
- `_AnchorCollector`, `_NON_RENDERED`, and `_VOID_ELEMENTS` are fully deleted (confirmed by grep) -- not disabled, not left behind a flag. `extract_html_hrefs` and `_extract_html_urls` are now thin wrappers over a shared `_collect_html_urls` helper.
- A genuine defect in the 01-13 counter model was found and locked into a regression BEFORE the rewrite even started: the one-shot `<body>`-triggered decrement (written to close an unclosed `<head>`) fires unconditionally on the first `<body>` tag, wrongly closing an unrelated open `<noscript>` too -- a real leak, discovered by fuzzing the old implementation against an html5lib oracle rather than hand-derived.
- `tests/test_html_visibility_differential.py` is a new, permanent differential test: a seeded (20260914) fuzz generator builds 2000 documents from a vocabulary of open/close/self-closing tags, void elements, and comments with the archive URL inserted at a random position, and compares extraction against an oracle walk written independently (its own hidden-tag set, an iterative stack instead of recursion, no shared helpers with `candidates.py`). Zero leak-direction disagreements and zero strand-direction disagreements were observed; the same test run against the pre-01-14 implementation finds 24/2000 leak disagreements, proving the test has teeth.
- Four pre-existing tests (from the 01-07/01-12/01-13 era) were corrected -- not weakened -- after empirically discovering their assumptions do not hold against a real spec-compliant parser: see Deviations.
- A new structural regression (`test_real_ready_message_structural_shape_yields_exactly_one_link`) locks the real Vicmap ready message's shape (HTML-only body, bare meta/link head, interior style, URL in body text) to exactly one archive link.
- html5lib was added to the pinned Nix devShell alongside `python-o365`; both import successfully, and flake.nix/flake.lock remain untracked per the plan's explicit instruction.
- Live recognition was re-confirmed read-only against the real mailbox: `recognize_candidate`/`select_candidate` (never `download_artifact`) selected exactly one candidate (order `OK0VUZ`) whose artifact URL matches the configured trusted prefix. No artifact was downloaded and `01-LIVE-VERIFICATION.md` was not rewritten.
- Full deterministic suite: 188 tests, all green, no skips (up from the 184-test baseline; net +4: the noscript RED test, the differential test, and the structural regression, minus the 3-for-3 rewrite of internal-state tests that stayed at parity).

## Task Commits

Each task was committed atomically (TDD RED/GREEN for Tasks 2 and 3; no separate REFACTOR commit needed -- both GREEN implementations were already minimal):

1. **Task 1: Add html5lib to the pinned devShell** - no commit (flake.nix/flake.lock deliberately left untracked per the plan's own instruction; verified via `nix develop ... -c python -c "import html5lib, O365"` -> `1.2-dev`, O365 still imports)
2. **Task 2: Decide rendered visibility from a parse tree** - `063addc` (test, RED: `test_stray_body_tag_does_not_implicitly_close_an_open_noscript` fails for the intended reason -- `CandidateFailure not raised`) then `71284e0` (feat: html5lib tree-based `_walk_visible`/`_collect_html_urls`, deletion of `_AnchorCollector`/`_NON_RENDERED`/`_VOID_ELEMENTS`, and correction of 4 tests whose assumptions html5lib disproves)
3. **Task 3: Differential test against a spec-compliant oracle** - `0931705` (test-only commit: RED proof gathered by pointing the same test at a frozen pre-01-14 snapshot of `_extract_html_urls`, 24/2000 leaks; GREEN against the current implementation is the same, unmodified test passing with 0/2000 leaks and 0/2000 strands -- no separate feat commit needed since Task 2's implementation was already correct)
4. **Task 4: Confirm the real ready message still works** - `58fd74c` (test: structural regression for the real message's shape; live recognition re-confirmed read-only, no artifact downloaded, no live record rewritten)

## Files Created/Modified

- `flake.nix` - `ps.html5lib` added to the `python3.withPackages` list in `devShells.default`, alongside `python-o365`. Untracked (operator decision, out of scope for this plan).
- `vicmap_acquire/candidates.py` - `_walk_visible`/`_collect_html_urls` (html5lib tree-based extraction) replace `_AnchorCollector`/`_NON_RENDERED`/`_VOID_ELEMENTS` (flat counter); `_HIDDEN_ELEMENTS` frozenset; `extract_html_hrefs`/`_extract_html_urls` re-implemented as thin wrappers.
- `tests/test_candidates.py` - new RED regression (`test_stray_body_tag_does_not_implicitly_close_an_open_noscript`); import changed from `_AnchorCollector` to `_extract_html_urls`; 3 internal-state tests (`non_rendered_depth` inspection) rewritten as behavioral equivalents; 3 tests corrected for real html5lib document-position/content-model facts (`noscript` wrapped in `<body>`, `head` split into its own dedicated test); new structural regression for the real ready message's shape.
- `tests/test_html_visibility_differential.py` (new) - seeded differential fuzz generator, an independently-authored oracle walk, and the single test asserting zero leak-direction disagreements with a measured strand-direction baseline.

## Decisions Made

See `key-decisions` in frontmatter. In short: html5lib is added via the pinned flake exactly as the plan's supply-chain disposition specifies; the RED test for Task 2 was discovered empirically (fuzzing the old counter against an oracle) rather than hand-derived; four pre-existing tests were corrected after discovering their assumptions do not hold against real HTML5 parsing (see Deviations for full justification); and Task 3's RED evidence was gathered against a frozen old-implementation snapshot since the production fix was already committed by Task 2.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Corrected `test_every_non_rendered_container_tag_suppresses_its_sole_archive_url` (noscript case) and `test_stray_void_end_tag_does_not_re_enable_collection` to use an explicit `<body>` context**
- **Found during:** Task 2, running the full suite after the tree-based rewrite
- **Issue:** Both tests placed a standalone `<noscript>` as the very first content in a document with nothing else establishing that parsing had already moved past `<head>`. Verified against html5lib directly: a real HTML5 parser gives a document-initial `<noscript>` its own "in head noscript" insertion mode, which auto-closes noscript the instant any non-whitespace text follows and relocates that text into an implicitly-created `<body>` -- a genuine, spec-verified fact about *document position*, not a suppression gap. This is unrelated to what either test intended to prove (that `noscript` suppresses its own contained content, and that a stray end tag doesn't re-enable collection).
- **Fix:** Wrapped each shape in an explicit `<body>...</body>` so the document has already established body content by the time `<noscript>` opens, sidestepping the irrelevant insertion-mode quirk. Verified this produces identical, correctly-suppressed results for `noscript` (and no change for the other 6 tags already passing in the same loop).
- **Files modified:** `tests/test_candidates.py`
- **Verification:** Both tests pass; full suite green (188 tests).
- **Committed in:** `71284e0` (Task 2 GREEN commit)

**2. [Rule 1 - Bug] Split `head` out of `test_self_closing_syntax_on_non_void_elements_does_not_close_them` into a new, corrected test**
- **Found during:** Task 2, same suite run
- **Issue:** The 01-13-era test asserted that self-closing `<head/>` doesn't close head, so trailing text stays suppressed. Verified against html5lib for `<head/>{url}`, `<head>{url}` (bare, unclosed), and `<head>{url}</head>` (explicitly closed): ALL THREE relocate the text into an implicitly-created `<body>`, making it genuinely visible. `<head>`'s content model admits only a fixed whitelist of element children (title, style, script, meta, link, base, noscript, template) -- free text is never valid content of `head` under the HTML5 spec, regardless of spelling. The "self-closing doesn't close it" framing was never the operative fact for `head`; the pre-rewrite counter's suppression of trailing text after `<head/>` was an artifact of the counter's approximation, not a fact about real browser behavior.
- **Fix:** Removed `head` from the self-closing-syntax loop (which remains valid for `script`/`style`/`noscript`(now body-wrapped)/`template`/`title`) and added `test_head_never_suppresses_trailing_text_regardless_of_spelling`, asserting the true behavior across all three spellings.
- **Files modified:** `tests/test_candidates.py`
- **Verification:** New test passes for all three spellings; full suite green.
- **Committed in:** `71284e0` (Task 2 GREEN commit)

---

**Total deviations:** 2 auto-fixed (both Rule 1 -- pre-existing tests encoding assumptions a real spec-compliant parser disproves, corrected using the same "trust the oracle over hand-picked intuition" principle the plan itself applies to the nested-template-in-body false positive).
**Impact on plan:** No suppression guarantee was weakened. The genuine guarantees these tests protect (noscript suppresses its own content in realistic body context; a stray end tag can't re-enable collection; self-closing syntax on a real non-void element stays open) are preserved and re-verified in more accurate markup context. `head`'s guarantee was corrected to match reality rather than a counter-era approximation nothing in the real Vicmap message ever exercised (the real message's head contains only meta/link/style/title, never bare text -- confirmed by Task 4's structural regression and the live recognition check).

## Known Stubs

None - no stubs introduced by this plan.

## Issues Encountered

- Empirically discovering the Task 2 RED case required fuzzing the OLD implementation against an html5lib oracle first (rather than hand-deriving a counterexample), since manually reasoning about HTML5's insertion-mode interactions (particularly around `<noscript>` and `<head>`) proved unreliable by inspection alone -- which is itself further evidence for exactly why this plan exists.
- After the tree-based rewrite, 4 of the ~50 pre-existing behavior-level tests failed. Investigation with html5lib directly (not guesswork) confirmed each failure traced to a real, spec-verified HTML5 parsing fact the old counter-based tests had never actually verified against a real parser (document-initial `<noscript>`'s special insertion mode; `<head>`'s complete lack of a free-text content model). Resolved per Deviations above.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- The counter model that survived four review passes is fully replaced with tree-inherited visibility from a real spec-compliant parser, backed by a permanent differential test with proven teeth (24/2000 leaks against the old implementation, 0/2000 against the new one).
- The real Vicmap DataShare ready message and the live mailbox both still recognize exactly one archive link matching the trusted prefix -- the rewrite traded a correctness gain for zero outage risk.
- `requirements-completed` lists `MAIL-02`, matching this phase's other MAIL-02 plans.

---
*Phase: 01-trusted-graph-acquisition*
*Completed: 2026-09-14*

## Self-Check: PASSED

- FOUND: `vicmap_acquire/candidates.py` contains `_walk_visible`, `_collect_html_urls`, `_HIDDEN_ELEMENTS`, and `import html5lib`
- CONFIRMED (grep): no remaining references to `_AnchorCollector`, `_NON_RENDERED`, or `_VOID_ELEMENTS` anywhere in `vicmap_acquire/` or `tests/` (one historical comment mentioning the retired name by name, no code reference)
- FOUND: `tests/test_html_visibility_differential.py` exists with the required module docstring stating oracle independence
- FOUND commit: `063addc` (test, RED -- Task 2)
- FOUND commit: `71284e0` (feat, GREEN -- Task 2)
- FOUND commit: `0931705` (test -- Task 3, RED proof against frozen old snapshot + GREEN against current code)
- FOUND commit: `58fd74c` (test -- Task 4)
- Full deterministic suite: `OPNIX_ENV_DISABLE=1 nix develop --impure --no-write-lock-file path:. --command python -m unittest discover -s tests` -> 188 tests, OK, no skips
- Differential test individually: `python -m unittest tests.test_html_visibility_differential -v` -> 1 test, OK (0 leaks, 0 strands across 2000 seeded documents)
- Re-ran the RED evidence: `gsd_run check tdd-red-evidence` returned `RED_EVIDENCE_OK` for both `.planning/phases/01-trusted-graph-acquisition/01-14-TASK2-RED.json` and `01-14-TASK3-RED.json`
- Re-ran live recognition check (read-only, no download): `CANDIDATE_COUNT: 2`, `SELECTION_SUCCEEDED: True`, `ORDER_ID: OK0VUZ`, `PREFIX_MATCH: True`; confirmed `artifacts/` contains only the pre-existing `Order_OK0VUZ.zip` from a prior plan's live verification, no new download
- Re-ran `nix develop --impure --no-write-lock-file path:. --command python -c "import html5lib, O365; print(html5lib.__version__)"` -> `1.2-dev`, exit 0
- Re-ran all task-level `<acceptance_criteria>` assertions: all pass (see Task Commits and Accomplishments above)

## Correction (orchestrator, 2026-09-14)

The RED measurement in this summary and in `01-14-TASK3-RED.json` originally
read `370/2000`. That figure was wrong. Re-measured twice independently — by
loading the pre-01-14 `candidates.py` from commit `036816c` and driving it with
this test's own committed generator and oracle at seed `20260914` — the actual
result is **24/2000 leak-direction** disagreements (and 112 strand-direction).
Every occurrence has been corrected to 24/2000.

The qualitative claim the number was offered to support is unaffected: the
differential test finds real leaks against the old implementation and none
against the new one, so it can fail and is not passing vacuously. Only the
magnitude was overstated.

The orchestrator's separate 4,000-document harness measured 146 leak-direction
disagreements. That is not in conflict — it uses a different generator
vocabulary and grammar, so the two rates are not comparable. It is cited here as
independent corroboration of the defect class, not of this test's rate.
