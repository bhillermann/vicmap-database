---
phase: 01-trusted-graph-acquisition
verified: 2026-09-14T13:10:00Z
status: passed
score: 21/21 must-haves verified
covered_files:
  - .gitignore
  - .planning/REQUIREMENTS.md
  - .planning/ROADMAP.md
  - .planning/phases/01-trusted-graph-acquisition/01-01-PLAN.md
  - .planning/phases/01-trusted-graph-acquisition/01-01-SUMMARY.md
  - .planning/phases/01-trusted-graph-acquisition/01-02-PLAN.md
  - .planning/phases/01-trusted-graph-acquisition/01-02-SUMMARY.md
  - .planning/phases/01-trusted-graph-acquisition/01-03-PLAN.md
  - .planning/phases/01-trusted-graph-acquisition/01-03-SUMMARY.md
  - .planning/phases/01-trusted-graph-acquisition/01-04-PLAN.md
  - .planning/phases/01-trusted-graph-acquisition/01-04-SUMMARY.md
  - .planning/phases/01-trusted-graph-acquisition/01-05-PLAN.md
  - .planning/phases/01-trusted-graph-acquisition/01-05-SUMMARY.md
  - .planning/phases/01-trusted-graph-acquisition/01-06-PLAN.md
  - .planning/phases/01-trusted-graph-acquisition/01-06-SUMMARY.md
  - .planning/phases/01-trusted-graph-acquisition/01-07-PLAN.md
  - .planning/phases/01-trusted-graph-acquisition/01-07-SUMMARY.md
  - .planning/phases/01-trusted-graph-acquisition/01-08-PLAN.md
  - .planning/phases/01-trusted-graph-acquisition/01-08-SUMMARY.md
  - .planning/phases/01-trusted-graph-acquisition/01-09-PLAN.md
  - .planning/phases/01-trusted-graph-acquisition/01-09-SUMMARY.md
  - .planning/phases/01-trusted-graph-acquisition/01-10-PLAN.md
  - .planning/phases/01-trusted-graph-acquisition/01-10-SUMMARY.md
  - .planning/phases/01-trusted-graph-acquisition/01-11-PLAN.md
  - .planning/phases/01-trusted-graph-acquisition/01-11-SUMMARY.md
  - .planning/phases/01-trusted-graph-acquisition/01-12-PLAN.md
  - .planning/phases/01-trusted-graph-acquisition/01-12-SUMMARY.md
  - .planning/phases/01-trusted-graph-acquisition/01-13-PLAN.md
  - .planning/phases/01-trusted-graph-acquisition/01-13-SUMMARY.md
  - .planning/phases/01-trusted-graph-acquisition/01-14-PLAN.md
  - .planning/phases/01-trusted-graph-acquisition/01-14-SUMMARY.md
  - .planning/phases/01-trusted-graph-acquisition/01-CONTEXT.md
  - .planning/phases/01-trusted-graph-acquisition/01-LIVE-VERIFICATION.md
  - .planning/phases/01-trusted-graph-acquisition/01-REVIEW-GAP-CLOSURE.md
  - .planning/phases/01-trusted-graph-acquisition/01-REVIEW.md
  - .planning/phases/01-trusted-graph-acquisition/01-SECURITY.md
  - .planning/phases/01-trusted-graph-acquisition/01-VALIDATION.md
  - read_mailbox.py
  - tests/__init__.py
  - tests/test_candidates.py
  - tests/test_download.py
  - tests/test_evidence.py
  - tests/test_graph.py
  - tests/test_html_visibility_differential.py
  - tests/test_origin.py
  - tests/test_repository_policy.py
  - vicmap.toml
  - vicmap_acquire/__init__.py
  - vicmap_acquire/candidates.py
  - vicmap_acquire/download.py
  - vicmap_acquire/evidence.py
  - vicmap_acquire/graph.py
  - vicmap_acquire/origin.py
covered_digest: "v1:sha256:21c30934a3ef6e4304cc14564bb6c76076ee46dd01a5de12d15df2feabe06e8b"
behavior_unverified: 0
overrides_applied: 0
re_verification:
  previous_status: gaps_found
  previous_score: 19/21
  gaps_closed:
    - "SC2/MAIL-02/Plan-03 recognition invariant: the flat integer depth-counter suppression model in `vicmap_acquire/candidates.py` (`_AnchorCollector`) is fully replaced by an html5lib parse-tree walk (`_walk_visible`/`_collect_html_urls`) that inherits hidden-ness down a real HTML5 tree instead of approximating tree-construction facts with a counter. The specific reported trigger (a `<body>` nested inside `template`/`object`/`applet`) is confirmed, independently, to have been a FALSE POSITIVE -- html5lib relocates that container into `<body>`, so the following text is genuinely rendered and collecting it was correct. The underlying structural claim the false-positive was offered in support of -- that a flat counter cannot soundly model HTML nesting -- was independently true and far larger in scope; it is what this closure actually fixed."
  gaps_remaining: []
  regressions: []
gaps: []
---

# Phase 1: Trusted Graph Acquisition Verification Report (Re-verification after 01-14)

**Phase Goal:** The operator can obtain exactly one authentic Vicmap order artifact from the automation mailbox without leaking sensitive content or trusting an unsafe download path.

**Verified:** 2026-09-14T13:10:00Z

**Status:** passed

**Re-verification:** Yes — after gap-closure plan 01-14, superseding the 2026-09-14T12:00:00Z re-verification (`gaps_found`, 19/21), which itself superseded the 2026-09-09T02:24:34Z initial verification.

## Goal Achievement

The single blocking gap from the prior round — a third reported instance of the non-rendered-content suppression-leak defect class — is now closed, but not in the way the prior report described it. Both parts of the correction were independently re-derived from the code, not taken on SUMMARY.md's word.

**Correcting the record on the reported false positive.** The prior verification's cited exploit — `<html><head><template><body></body></template>{url}</head><body>real</body></html>` — was investigated directly against html5lib's own parse tree (dumped, not inferred): a real spec-compliant parser relocates `<template>` (and `<object>`/`<applet>`/`<iframe>`, tested identically) out of `<head>` and into `<body>` the moment it contains a literal `<body>` start tag, and the text following the container becomes that container's `tail` — which belongs to `<body>`'s (not the container's) rendered flow. A real mail reader running this markup through any spec-compliant HTML engine would genuinely display that URL. Collecting it was correct behavior, not a leak; the prior verification's "third instance" finding was a false positive, exactly as flagged for this round. This is now recorded here, not silently dropped, per the standing instruction that a future reader needs to know the shape was investigated and why it was not a vulnerability.

**The structural claim the false positive was offered in support of was true anyway, and much larger.** `01-14-PLAN.md` reports the orchestrator's own differential fuzz (seed `20260914`, 4,000 generated documents) found 287 disagreements against a spec parser, 146 of them leak-direction, against the pre-01-14 counter. I independently confirmed this class of defect is real (see Behavioral Spot-Checks) and confirmed it is now closed, using three independent lines of evidence: (1) the project's own new differential test, re-run directly; (2) reconstructing that same test's generator+oracle against the actual pre-01-14 commit (`036816c`) to confirm it fails there; and (3) writing an entirely separate fuzz harness (different vocabulary, different nesting grammar, different oracle traversal, 15,000 documents across five seeds, including the exact false-positive shape generalized across `template`/`object`/`applet`/`iframe`/`noscript`) against the current code, finding zero leak-direction disagreements.

**One evidentiary discrepancy found and corrected here.** `01-14-TASK3-RED.json` and `01-14-SUMMARY.md` both claim the differential test found "370/2000 leak-direction disagreements" when pointed at the pre-01-14 implementation. I reproduced this measurement two independent ways — importing the actual `036816c` commit's `candidates.py` as a standalone module, and monkeypatching `_extract_html_urls` inside the real, unmodified `tests/test_html_visibility_differential.py` exactly as the RED evidence describes doing — and both give **24 leak-direction disagreements out of 2000**, not 370, against the exact same seed, generator, oracle, and commit. This is a real inaccuracy in the executor's TDD evidence trail (the claimed number is roughly 15x the reproducible one), and it is being flagged rather than passed through. It does **not** change the goal-achievement verdict: 24 is still nonzero, meaning the RED evidence's substantive claim — the differential test can and does fail against the real pre-01-14 code, and passes at 0/2000 against the current code — holds up under independent reproduction. The magnitude is wrong; the property being proved is not. See Anti-Patterns for disposition.

**Everything else** — the finalization commit point, the shared policy/fingerprint contract, the evidence-sink guard, the connection-level MIME fetch, the authenticated-origin chain, the bucket/path prefix constraint, the prohibition dispositions, and the live transaction record — is unchanged since the prior round (01-14 touched only `vicmap_acquire/candidates.py`, `tests/test_candidates.py`, and the new `tests/test_html_visibility_differential.py`, confirmed by `git diff --stat` between the last 01-13 commit and the last 01-14 commit) and continues to pass the full deterministic suite.

### Observable Truths

| # | Source | Truth | Status | Evidence |
|---|---|---|---|---|
| 1 | Roadmap SC1 | Authenticate, confirm the configured mailbox, and inspect a bounded Inbox result without credential/body output | ✓ VERIFIED | Unchanged; regression-checked via full suite (188/188 pass). |
| 2 | Roadmap SC2 | Configured markers identify candidates and exactly one is selected with redacted identity | ✓ VERIFIED | Recognition is no longer defeatable by the reported class. `vicmap_acquire/candidates.py::_walk_visible` inherits hidden-ness down a real html5lib parse tree instead of approximating it with a counter. Independently confirmed by (a) re-running `tests/test_html_visibility_differential.py` (2000 seeded docs, 0 leaks), (b) reproducing 24/2000 leaks against the real pre-01-14 commit with the identical test, and (c) an independently-written 15,000-document fuzz across 5 seeds with a different generator/oracle, 0 leaks including the false-positive shape generalized across 5 hidden-container tags. |
| 3 | Roadmap SC3 | Selected message yields one artifact through the approved HTTPS host with redirect/timeout/size limits, bound to an authenticated origin | ✓ VERIFIED | Unchanged from prior round; `vicmap_acquire/origin.py` and `download.py` untouched by 01-14; full suite green. |
| 4 | Roadmap SC4 | Completed download reports exact byte count and checksum | ✓ VERIFIED | Unchanged. |
| 5 | Plan 01 | Importing the CLI/package causes no auth, network, directory, or artifact side effect | ✓ VERIFIED | Unchanged. |
| 6 | Plan 01 | Policy is fully validated pre-auth; credentials remain environment-only; tokens remain memory-only | ✓ VERIFIED | Unchanged. |
| 7 | Plan 01 | Tracer output contains only redacted identity/download evidence | ✓ VERIFIED | Unchanged. |
| 8 | Plan 02 | App-only memory auth confirms exact mailbox without body/raw-provider output | ✓ VERIFIED | Unchanged. |
| 9 | Plan 02 | One inclusive cutoff and four-field metadata query exhaust all pages without a count cap | ✓ VERIFIED | Unchanged. |
| 10 | Plan 02 | Only header-qualified messages trigger MIME retrieval; scanning stays read-only, one connection-level GET per MIME fetch | ✓ VERIFIED | Unchanged; `graph.py` untouched by 01-14. |
| 11 | Plan 03 | Only exact sender/order/subject/MIME/link-cardinality matches become candidates | ✓ VERIFIED | Same fix as #2. `tests/test_candidates.py::CandidateRecognitionTest` (58 tests, all passing) covers script/style/template/noscript/title/object/iframe/head suppression, comment exclusion, self-closing syntax, void elements, omitted `</head>`, the corrected nested-`<body>`-in-`<noscript>` case, and the real message's structural shape. |
| 12 | Plan 03 | Complete-scan selection deterministically chooses one newest candidate and displays only a fingerprint | ✓ VERIFIED | Unchanged; `CandidateSelectionTest` (13 tests) unaffected by 01-14. |
| 13 | Plan 03 | Empty/ambiguous/malformed/mismatched candidates fail closed | ✓ VERIFIED | Unchanged. |
| 14 | Plan 04 | Every initial/redirect target is exact-host HTTPS and exact bucket/path prefix, validated before request | ✓ VERIFIED | Unchanged; `download.py` untouched by 01-14. |
| 15 | Plan 04 | Connect/read timeouts remain independent with no total-transfer deadline | ✓ VERIFIED | Unchanged. |
| 16 | Plan 04 | Exact inclusive ceiling, persisted-byte count/hash, and atomic no-overwrite publication | ✓ VERIFIED | Unchanged. |
| 17 | Plan 04 | Every handled failure removes private partial state and returns one coherent closed result | ✓ VERIFIED | Unchanged. |
| 18 | Plan 05 | CLI renders only one closed machine-readable success/progress/failure vocabulary | ✓ VERIFIED | Unchanged. |
| 19 | Plan 05 | Exactly one selected candidate enters the downloader and no fallback occurs | ✓ VERIFIED | Unchanged. |
| 20 | Plan 05 | A controlled live run proves one redacted authentic message-to-artifact transaction | ✓ VERIFIED | `01-LIVE-VERIFICATION.md` untouched by 01-14 (`git log` shows its last edit was the 01-11 commit `425bc75`, before this round); `artifacts/Order_OK0VUZ.zip` on disk still carries its original 2026-09-09 17:03 timestamp with no newer download, corroborating the SUMMARY's claim that Task 4's live recognition check downloaded nothing new. |
| 21 | Plan 05 | Live record safely records scope/runtime/disclosure attestations without prohibited source values | ✓ VERIFIED | Unchanged; not touched by 01-14. |

**Score:** 21/21 truths verified (0 present, behavior-unverified)

### Gap-Closure Plan 01-14 Must-Haves (verified individually)

| Must-have (from `01-14-PLAN.md` frontmatter) | Status | Evidence |
|---|---|---|
| Visibility decided from a real HTML5 parse tree, not a flat depth counter | ✓ VERIFIED | `_AnchorCollector`, `_NON_RENDERED`, `_VOID_ELEMENTS` fully deleted (`grep` confirms only one historical comment mentions the retired name); `_walk_visible` recurses `html5lib.parse(..., namespaceHTMLElements=False)`'s ElementTree, inheriting a `hidden` boolean. |
| A differential test compares extraction against a spec-compliant oracle over thousands of documents and fails on any leak-direction disagreement | ✓ VERIFIED, with one evidentiary correction | `tests/test_html_visibility_differential.py` exists, its oracle (`_oracle_url_is_visible`) is genuinely independent (own hidden-tag set, iterative stack instead of recursion, existence check instead of ordered lists, does not import from `candidates.py`), asserts zero leak-direction disagreements over 2000 seeded documents, and currently passes. Its claimed proof-of-teeth number (370/2000 leaks against the pre-01-14 code) is **not reproducible** — I independently measured 24/2000 leaks using the identical test, generator, oracle, and seed against the actual pre-01-14 commit (`036816c`), both via a standalone re-import and via the exact monkeypatch method described in `01-14-TASK3-RED.json`. The test still has real teeth (24 > 0), just not the claimed magnitude. See Anti-Patterns. |
| The genuine ready message's structural shape still yields exactly one archive link | ✓ VERIFIED | `test_real_ready_message_structural_shape_yields_exactly_one_link` passes; asserts `candidate.artifact_url == archive_url` for an HTML-only body with bare meta/link head and interior style block. |
| Every 01-07/01-12/01-13 guarantee survives | ✓ VERIFIED | All 58 tests in `CandidateRecognitionTest`/`CandidateSelectionTest` pass; the 4 tests the executor corrected (2 `noscript`-position tests, 1 `head`-content-model test split out, 1 self-closing-loop adjustment) were independently re-verified against a direct html5lib parse-tree dump to confirm each correction reflects a real spec fact (a standalone document-initial `<noscript>` is auto-closed by html5lib's "in head noscript" insertion mode; `<head>` never admits free text under any spelling) rather than a weakening. |
| html5lib supplied by the pinned Nix flake, hash-verified, no pip/npm install | ✓ VERIFIED | `flake.nix` adds `ps.html5lib` to the same `python3.withPackages` list as the existing `python-o365` derivation in `devShells.default`; no other flake change. `flake.nix`/`flake.lock` remain untracked per the plan's explicit instruction (confirmed via `git status`). |

### Required Artifacts

| Artifact | Expected | Status | Details |
|---|---|---|---|
| `vicmap_acquire/candidates.py` | Pure recognition and deterministic selection | ✓ VERIFIED | Tree-based visibility (`_walk_visible`/`_collect_html_urls`/`_HIDDEN_ELEMENTS`) replaces the flat counter; `extract_html_hrefs`, `_extract_html_urls`, `recognize_candidate`, `select_candidate` all present and behaviorally unchanged in contract. |
| `tests/test_html_visibility_differential.py` | Seeded differential fuzz with an independent oracle | ✓ VERIFIED | Present, oracle independence confirmed by direct read, passes (0/2000 leaks). Proof-of-teeth number in its RED evidence is inflated (see Anti-Patterns) but the property (fails on real old code, passes on new code) is independently reproduced. |
| `flake.nix` | html5lib added to the pinned devShell | ✓ VERIFIED | Confirmed by direct read; `import html5lib, O365` both succeed in the devShell. |
| `tests/test_candidates.py` | Recognition/selection regressions | ✓ VERIFIED | 58 tests, all passing; new/corrected tests reflect real html5lib behavior, independently re-checked against a parse-tree dump. |
| `vicmap_acquire/origin.py`, `download.py`, `graph.py`, `evidence.py`, `read_mailbox.py` | Unchanged supporting modules | ✓ VERIFIED | Untouched since 01-13 (confirmed by `git diff --stat`); full suite regression-passes. |
| `01-LIVE-VERIFICATION.md` | Safe live proof | ✓ VERIFIED | Untouched by 01-14; last edited by 01-11. |

### Key Link Verification

| From | To | Via | Status | Details |
|---|---|---|---|---|
| `read_mailbox.py` | `candidates.py` | Metadata plus lazy MIME feed recognition and selection | ✓ WIRED | Unchanged wiring; the fed candidate is no longer a false positive from the reported recognition defect. |
| `candidates.py` | `origin.py` | `recognize_candidate` calls `verify_authenticated_origin` before accepting a link match | ✓ WIRED | Unchanged; confirmed present in current `candidates.py` (lines ~275-283). |
| `candidates.py::_walk_visible` | html5lib parse tree | Visibility inherited down the tree from `_HIDDEN_ELEMENTS`, rather than counted | ✓ WIRED | Confirmed by direct read and by tree-dump reproduction of the exact shape that motivated the rewrite. |
| `tests/test_html_visibility_differential.py::_oracle_url_is_visible` | html5lib parse tree | Independent walk, no shared helpers with `candidates.py` | ✓ WIRED, independence confirmed | Read line-by-line: own hidden-tag set, own traversal (stack, not recursion), own existence check; only the implementation-under-test import (`_extract_html_urls`) touches `candidates.py`, which is expected and necessary for a differential test. |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|---|---|---|---|---|
| `candidates.py` | `Candidate` | Graph metadata plus selected MIME plus authenticated origin plus tree-based recognition | Yes — recognition no longer admits the reported non-genuinely-displayed shape | ✓ FLOWING / TRUSTED |
| (all others) | — | — | Unchanged from prior round | ✓ FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|---|---|---|---|
| Full deterministic suite | `OPNIX_ENV_DISABLE=1 nix develop --impure --no-write-lock-file path:. --command python -m unittest discover -s tests` | 188 tests, 0 failures, 0 skips | ✓ PASS |
| Differential test alone | `python -m unittest tests.test_html_visibility_differential -v` | 1 test, OK | ✓ PASS |
| Reported false positive, re-investigated | html5lib tree dump of `<head><template><body></body></template>{url}</head><body>real</body></html>` (and `object`/`applet`/`iframe` variants) | `template`/`object`/`applet` are relocated into `<body>`; the URL becomes the container's `tail`, which belongs to `<body>`'s (visible) flow. `iframe` keeps its own text (`<body></body>` literal) but the URL is still in its visible `tail`. All four variants: genuinely rendered. | ✓ CONFIRMED false positive, not a leak |
| Same shapes against current code | `_extract_html_urls` on all four variants | URL present in output for all four (correctly, since it is genuinely rendered) | ✓ PASS — correct behavior |
| Genuinely-hidden containers still suppressed | `_extract_html_urls` on `script`/`style`/`template`/`noscript`/`title`/`object`/`applet`/`iframe` each independently wrapping the URL in `<body>` | `[]` for all eight | ✓ PASS |
| Comment exclusion, text-after-`</script>` rendering | `_extract_html_urls` on each shape | `[]` for the comment; URL recovered for text after `</script>` | ✓ PASS |
| `<head>` never suppresses trailing text (3 spellings) | html5lib tree dump of `<head/>`, bare unclosed `<head>`, explicit `<head></head>` | All three relocate the following text into `<body>` | ✓ PASS, confirms `test_head_never_suppresses_trailing_text_regardless_of_spelling` is correct, not a weakening |
| Standalone vs. body-wrapped `<noscript>` document-position quirk | html5lib tree dump of both shapes | Standalone, document-initial `<noscript>` is auto-closed and its text is relocated to `<body>` (an unrelated insertion-mode quirk); body-wrapped `<noscript>` keeps its text inside itself (hidden) | ✓ PASS, confirms the 4 corrected tests reflect a real spec fact, not a convenient rewrite |
| Old-code reproduction of the closed noscript leak | `_extract_html_urls` on `<p>x</p><noscript/><body>{url}</body>` against pre-01-14 (`036816c`) vs current code | Old: leaks the URL. New: `[]` | ✓ PASS — regression genuinely closed |
| **Independent differential fuzz, same generator/oracle as the committed test, against the real pre-01-14 commit (`036816c`)** | Standalone re-import of `036816c:vicmap_acquire/candidates.py`, run through the committed test's generator+oracle, seed 20260914, 2000 docs | **24 leak-direction disagreements**, 112 strand-direction | ⚠️ Confirms the test has teeth (nonzero), but **contradicts** the "370/2000" figure in `01-14-TASK3-RED.json`/`01-14-SUMMARY.md` by ~15x. Reproduced twice (fresh module import, and exact monkeypatch of the real test file) with identical results. See Anti-Patterns. |
| **Independent adversarial fuzz, different harness** (different vocabulary, recursive nesting grammar to depth 5, different oracle traversal, generalized false-positive shape at 20% frequency) | 5 seeds × 3000 docs = 15,000 documents against current code | 0 leak-direction disagreements across all 15,000; strand counts high (as expected — the generator deliberately omits closing tags and nests aggressively, and strands fail closed, which is a correctness/availability concern only, per the plan's own framing) | ✓ PASS — corroborates the leak class is closed at a scale larger than the project's own test |
| Debt-marker scan | `grep -rn "TBD\|FIXME\|XXX"` across `vicmap_acquire/candidates.py`, `tests/test_candidates.py`, `tests/test_html_visibility_differential.py` | No matches | ✓ PASS |
| Old model fully deleted, not disabled | `grep -rn "_AnchorCollector\|_NON_RENDERED\|_VOID_ELEMENTS\|non_rendered_depth" vicmap_acquire/ tests/` | One historical comment only, no code reference | ✓ PASS |
| Scope of 01-14's file changes | `git diff --stat` between last 01-13 commit (`90a7ad7`) and last 01-14 commit (`58fd74c`) | Only `vicmap_acquire/candidates.py`, `tests/test_candidates.py`, `tests/test_html_visibility_differential.py` (new) changed | ✓ PASS — no guarantee-bearing module outside `candidates.py` was touched |

### Probe Execution

No probes declared for this phase; none found under `scripts/*/tests/probe-*.sh`. Skipped.

### Requirements Coverage

| Requirement | Source Plans | Description | Status | Evidence |
|---|---|---|---|---|
| MAIL-01 | 01-01, 01-02, 01-05, 01-09, 01-10, 01-11 | Authenticate/confirm configured mailbox without credential/body disclosure | ✓ SATISFIED | Unchanged. |
| MAIL-02 | 01-01–01-14 | Bounded Inbox scan and configured candidate recognition | ✓ SATISFIED | The recognition defect class is closed (tree-based visibility, differential-fuzz-verified per above). `REQUIREMENTS.md` marks MAIL-02 Complete again (commit `a677a3f`, executor's own restoration after this plan) — this marking is now earned. |
| MAIL-03 | 01-01, 01-03, 01-05, 01-09, 01-11 | Deterministically select exactly one and show redacted identity | ✓ SATISFIED | Unchanged. |
| MAIL-04 | 01-01, 01-04, 01-05, 01-08 | Download one artifact only through approved bounded HTTPS | ✓ SATISFIED | Unchanged. |
| MAIL-05 | 01-01, 01-04, 01-05, 01-09 | Show exact artifact byte count and checksum | ✓ SATISFIED | Unchanged. |

REQUIREMENTS.md already reflects MAIL-02 as `[x]` Complete (restored by the executor in commit `a677a3f`, "docs(01-14): update state and roadmap after plan completion"). No further edit to REQUIREMENTS.md is needed from this verification.

## Prohibition Gate

Unchanged from the prior round; `origin.py`, `download.py`, `graph.py`, `evidence.py` were not touched by 01-14 and the full suite (including `test_graph.py`, `test_download.py`, `test_evidence.py`, `test_origin.py`) remains green.

| Prohibition | Automated evidence | Disposition |
|---|---|---|
| PROHIB-01 — no mailbox mutation | 4 named tests in `tests/test_graph.py::GraphReadOnlyEnforcementTest` | ✓ accepted, bhillermann@vegetationlink.com.au, 2026-09-14 (carried forward) |
| PROHIB-02 — no Graph/ambient authority at artifact host | 2 named tests in `tests/test_download.py` | ✓ accepted, bhillermann@vegetationlink.com.au, 2026-09-14 (carried forward) |
| PROHIB-03 — no incomplete/failed/over-limit final publication | 8 named tests in `tests/test_download.py` | ✓ accepted, bhillermann@vegetationlink.com.au, 2026-09-14 (carried forward) |
| PROHIB-04 — no substitution of an older/different order's artifact after failure | 1 named test in `tests/test_evidence.py` | ✓ accepted, bhillermann@vegetationlink.com.au, 2026-09-14 (carried forward) |
| PROHIB-05 — no automatic widening of the trust policy from a received message | 4 named tests plus `test_origin.py`'s unauthenticated-origin rejections | ✓ accepted, bhillermann@vegetationlink.com.au, 2026-09-14 (carried forward) |

## Test Quality Audit

| Test File | Linked Reqs | Active | Skipped | Assertion Level | Verdict |
|---|---|---|---|---|---|
| `tests/test_candidates.py` | MAIL-02, MAIL-03 | 58 | 0 | Behavioral/value | ✓ Complete — the recognition guarantee is now backed by a real spec-compliant parser rather than hand-picked cases, and a differential fuzz closes the class the hand-picked cases couldn't reach. |
| `tests/test_html_visibility_differential.py` (new) | MAIL-02 | 1 (2000-document fuzz inside it) | 0 | Property/differential | ⚠ Passes and the oracle is genuinely independent, but its own recorded proof-of-teeth measurement (370/2000) is not reproducible (24/2000 measured independently) — see Anti-Patterns. |
| `tests/test_download.py` | MAIL-04, MAIL-05 | ~50 | 0 | Behavioral/value | ✓ Unchanged, carried forward. |
| `tests/test_evidence.py` | MAIL-01, MAIL-03, MAIL-05 | ~55 | 0 | Behavioral/value | ✓ Unchanged, carried forward. |
| `tests/test_graph.py` | MAIL-01, MAIL-02 | ~40 | 0 | Behavioral/value | ✓ Unchanged, carried forward. |
| `tests/test_origin.py` | MAIL-02 (authenticity) | 19 | 0 | Behavioral/value | ✓ Unchanged, carried forward. |
| `tests/test_repository_policy.py` | none | 3 | 0 | Behavioral (real `git check-ignore`) | ✓ Unchanged, carried forward. |

## Anti-Patterns and Review Findings

| Finding | Status | Verdict |
|---|---|---|
| Nested `<body>` inside `template`/`object`/`applet` (prior round's "third instance") | ✅ CLOSED, record corrected | The specific cited example was a false positive (html5lib genuinely renders that content); the broader structural claim (flat counter can't model HTML nesting) was true and is what this plan fixed via a full tree-based rewrite. |
| **RED-evidence quantitative discrepancy**: `01-14-TASK3-RED.json` and `01-14-SUMMARY.md` claim 370/2000 leak-direction disagreements against the pre-01-14 implementation; independently reproduced (twice, two methods) as 24/2000 against the same seed/generator/oracle/commit | ⚠ OPEN — non-blocking | Does not change the goal-achievement verdict (the property proved — nonzero leaks pre-fix, zero post-fix — holds), but the specific number in the TDD evidence trail is materially wrong (~15x) and should not be relied upon uncorrected. Recorded here as the authoritative correction. Recommend the executor re-measure and correct `01-14-TASK3-RED.json`/`01-14-SUMMARY.md`, or record an explicit override if the discrepancy's origin is understood and accepted. |
| CR-01, CR-02, WR-01 (all prior findings) | ✅ CLOSED | Unchanged from prior round; regression-checked via full suite. |
| WR-02 (MSO conditional comments unconditionally suppressed) | ⚠ OPEN — not blocking | Unchanged, still explicitly deferred (availability-only, fail-closed). |
| WR-03/new (SafeFailure events never carry `order_id`/fingerprints) | ⚠ OPEN — not blocking | Unchanged, still explicitly deferred. |
| IN-01, IN-02 (informational) | ℹ OPEN | Unchanged. |

No unreferenced `TBD`, `FIXME`, or `XXX` debt markers were found in any file modified by 01-14.

## Disconfirmation Pass

- **The false-positive correction was verified against html5lib's own parse tree, not accepted on narrative.** All four hidden-container variants (`template`, `object`, `applet`, `iframe`) were dumped directly; each relocates its content such that the trailing URL is genuinely part of `<body>`'s rendered flow.
- **The "370/2000" claim did not survive independent reproduction.** This is exactly the kind of unverified quantitative claim the adversarial stance exists to catch — it was checked by execution, not by re-reading the SUMMARY, and found wrong by roughly an order of magnitude. The underlying qualitative claim (test has teeth) survived a stricter, independently-authored 15,000-document fuzz.
- **Scope of change was verified structurally, not assumed.** `git diff --stat` between the last commit of 01-13 and the last commit of 01-14 confirms exactly three files changed in the trust path (`candidates.py`, `test_candidates.py`, the new differential test file); every other guarantee-bearing module was untouched, which is why their re-verification here is a regression check (full suite green) rather than a full re-derivation.

## Decision Coverage

Not independently re-derived line-by-line in this pass (non-blocking gate, consistent with the prior round). Nothing found in this re-verification contradicts the prior finding that all trackable CONTEXT.md decisions were honored, and 01-14 introduced no new decision that appears abandoned; its own key-decisions (html5lib via pinned nixpkgs, flake.nix left untracked, RED evidence gathered empirically) are all confirmed above.

## Human Verification Required

None. The live mailbox check was not re-run live in this verification pass (per the task's explicit instruction not to download an artifact); its "no new download" claim is corroborated indirectly but strongly: `01-LIVE-VERIFICATION.md` is untouched since 01-11, and `artifacts/Order_OK0VUZ.zip` on disk still carries its original 2026-09-09 timestamp. This is the same evidentiary posture the prior verification round accepted for this class of claim.

## Gaps Summary

None. The one blocking gap from the prior round is closed: the flat suppression-counter model that had been patched three times (01-12, CR-01/CR-02 via 01-13, and this round's reported fourth instance) is now replaced wholesale with a real html5lib parse-tree walk, backed by a permanent differential test against an independent oracle and corroborated by a much larger independent fuzz run for this verification. The specific example that triggered this round's gap-closure plan was a false positive, now corrected in the record; the structural defect class it stood in for was real and is now closed. One non-blocking evidentiary finding is recorded (an inflated RED-evidence figure) for the executor to correct going forward, but it does not reopen the gap.

---

_Verified: 2026-09-14T13:10:00Z_
_Verifier: Claude (gsd-verifier)_
