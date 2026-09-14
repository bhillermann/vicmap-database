---
phase: 01-trusted-graph-acquisition
verified: 2026-09-14T12:00:00Z
status: gaps_found
score: 19/21 must-haves verified
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
  - tests/test_origin.py
  - tests/test_repository_policy.py
  - vicmap.toml
  - vicmap_acquire/__init__.py
  - vicmap_acquire/candidates.py
  - vicmap_acquire/download.py
  - vicmap_acquire/evidence.py
  - vicmap_acquire/graph.py
  - vicmap_acquire/origin.py
covered_digest: "v1:sha256:25dc1fe6ad9c9aba39384d908e924ab232edfde26bf6c837e0d8ea4c9e62d20f"
behavior_unverified: 0
overrides_applied: 0
re_verification:
  previous_status: gaps_found
  previous_score: 15/21
  gaps_closed:
    - "G-01: Authenticity chain now binds acquisition to a verified DKIM/DMARC/compauth origin verdict (vicmap_acquire/origin.py::verify_authenticated_origin) plus an exact bucket/path prefix constraint (vicmap_acquire/download.py::_normalize_url_prefix, DownloadPolicy.allowed_url_prefixes), applied to every redirect hop, with a rejection test (test_prefix_authority_narrows_the_allowed_host) and a single connected controlled live proof."
    - "G-02: One shared policy validator (read_mailbox.py::validate_acquisition_policy) is now called identically by both load_config and run_acquisition, and fingerprint_hex_chars is bounded 8-64 consistently across AcquisitionConfig, DownloadPolicy, and evidence.py's _MIN/_MAX_FINGERPRINT_HEX_CHARS."
    - "G-03: download.py::_publish_artifact is now the single, well-documented commit point (os.link then best-effort cleanup); a post-commit unlink failure is reported via DownloadResult.temp_cleanup_deferred, never as a transfer failure. Verified by test_post_link_cleanup_failure_still_reports_a_committed_success."
    - "G-05: read_mailbox.py::_EmitOnce guards every event emission; a failing sink is marked failed and never retried, and no raw exception can escape run_acquisition — verified by direct reproduction (guarded sink returns INTERNAL_FAILURE, no RuntimeError escapes)."
    - "G-06 / three-plus-two prohibition dispositions: 01-LIVE-VERIFICATION.md now records PROHIB-01 through PROHIB-05 each accepted by the operator (bhillermann@vegetationlink.com.au, 2026-09-14) against named enforcement tests, all of which exist and were independently confirmed to test the claimed property."
    - "W-01/WR-03 (extra Graph representation GET before MIME fetch): vicmap_acquire/graph.py::get_message_mime now builds the $value URL directly through the confirmed folder's own connection and issues exactly one connection-level GET; test_selective_mime_fetches_by_complete_id_only_on_explicit_call and test_scan_plus_one_mime_retrieval_issues_one_request_per_page_plus_one assert this at the connection-request level."
    - "01-12 defect (void elements stranding suppression): _VOID_ELEMENTS carve-out confirmed present and passing."
    - "CR-01 (self-closing non-void tags leak suppressed content) and CR-02 (omitted </head> strands suppression) from 01-REVIEW-GAP-CLOSURE.md: both independently reproduced against the pre-01-13 exploit snippets and confirmed fixed against the current code."
    - "WR-01 (DMARC header.from absence more permissive than a mismatch): independently reproduced against the review's exact exploit MIME and confirmed the same input is now rejected with OriginUnauthenticated."
  gaps_remaining:
    - "A third instance of the same defect class (see gap below): a <body> start tag nested inside any non-void, non-rendered container that is not itself a raw-text element (template, object, iframe, applet) fires the one-shot head-closure decrement prematurely, permanently under-counting suppression for the remainder of the document."
  regressions: []
gaps:
  - truth: "Only a genuinely displayed or linked archive occurrence can make an exact header-qualified message a candidate (Roadmap SC2 / MAIL-02 / Plan 03)."
    status: failed
    reason: >
      This is the third independently-discovered instance of the same defect class that produced
      the 01-12 outage and the CR-01/CR-02 findings 01-13 just closed. `_AnchorCollector`'s
      suppression model is still a flat integer depth counter with a single-shot special case for
      `<body>` implicitly closing `<head>`. That special case fires unconditionally on the FIRST
      `<body>` start tag `HTMLParser` tokenizes, regardless of whether that tag is the document's
      real body or a literal `<body>...</body>` pair nested inside another still-open non-rendered,
      non-void, non-raw-text container (`template`, `object`, `iframe`, `applet` — none of these
      put the tokenizer into CDATA/raw-text mode the way `script`/`style` do, so a literal nested
      `<body>` tag inside them is tokenized as an ordinary start tag). The premature decrement
      leaves `non_rendered_depth` under-counted for the rest of the document, so content that is
      still lexically inside the real, still-open `<head>` (or inside the outer container) — text
      or an anchor href — is collected as "visible" even though no mail reader would ever display
      it. Verified by direct execution against the real pipeline entry points
      (`vicmap_acquire.candidates._extract_html_urls` / `extract_html_hrefs`), not a reconstruction:
      `<html><head><template><body></body></template>http://evil.example.com/Order_U.zip</head><body>real</body></html>`
      yields `['http://evil.example.com/Order_U.zip']` instead of `[]`, and the anchor-href variant
      (`<a href="...">` in the same position) reproduces identically. A third structurally-different
      container (`object`) reproduces the same leak. No test in `tests/test_candidates.py` (818
      lines, including the 15 CR-01/CR-02 regressions 01-13 just added) exercises a `<body>` tag
      nested inside any non-raw-text non-rendered container — every existing regression's `<body>`
      tag is the document's own real body. This directly falsifies MAIL-02's recognition invariant
      the same way CR-01 and CR-02 did, via a third trigger. It indicates the one-shot
      `_head_implicit_close_applied` flag is not a sound general fix for "implicit closure" — the
      flat depth-counter model itself needs the stack-based, tag-aware rewrite CR-02's own review
      named as the complete fix ("track a stack of currently-open non-rendered container tag
      names... so an end tag only closes the container it actually names"), not another
      single-shot special case.
    artifacts:
      - path: vicmap_acquire/candidates.py
        issue: "_AnchorCollector.handle_starttag (lines 130-142): the body-triggered one-shot head-closure decrement fires on ANY <body> start tag the tokenizer sees, including one nested inside an already-open non-void, non-rendered, non-raw-text container, permanently under-counting non_rendered_depth for the remainder of the document."
      - path: tests/test_candidates.py
        issue: "No regression exercises a <body> tag nested inside template/object/iframe/applet while a genuinely-still-open non-rendered container (head, or the outer container itself) surrounds later content."
    missing:
      - "Replace the flat non_rendered_depth integer with a stack of currently-open non-rendered container tag names (or otherwise make the head special-case aware of whether the <body> tag it is reacting to is nested inside another already-open non-rendered container), so an end tag or an implicit-closure trigger can only affect the container it actually names/closes."
      - "Add a regression for a <body> start/end pair nested inside each of template, object, iframe, and applet, asserting that content genuinely still inside the outer container (or inside a still-open <head>) after the nested pair remains suppressed."
---

# Phase 1: Trusted Graph Acquisition Verification Report (Re-verification)

**Phase Goal:** The operator can obtain exactly one authentic Vicmap order artifact from the automation mailbox without leaking sensitive content or trusting an unsafe download path.

**Verified:** 2026-09-14T12:00:00Z

**Status:** gaps_found

**Re-verification:** Yes — after gap-closure plans 01-06 through 01-13, superseding the 2026-09-09T02:24:34Z initial verification (preserved in `re_verification` above and in the Prior Findings section below).

## Goal Achievement

Six of the six original gaps (G-01 through G-06) and the W-01/WR-03 warning are genuinely closed, each independently re-derived from the code rather than taken on SUMMARY.md's word — every fix was reproduced directly against the real pipeline entry points, every named test cited as evidence was read and confirmed to test the claim it is cited for, and every cited commit exists in git history with a timestamp consistent with the narrated sequence of events (the first live invocation failing under the pre-01-12 defect, 01-12 landing, the second live invocation succeeding). The authenticity chain the original verification found entirely missing — a verified DKIM/DMARC/compauth origin signal plus an exact bucket/path prefix constraint enforced on every redirect hop — is now real, tested, and exercised by one connected, retained, redacted live transaction.

However, the phase has a demonstrated pattern: two independent code-review findings (CR-01, CR-02) survived a full TDD gap-closure plan (01-07) and were only caught by a subsequent deep code review, because the test suite kept proving the fix against tidy, hand-written HTML rather than markup shaped the way `html.parser`'s real tokenizer (and real mail clients) actually behave. This re-verification actively hunted for a third instance of that same pattern per the stated verification priority, and found one: a `<body>` tag nested inside `template`/`object`/`iframe`/`applet` (any non-void, non-rendered container that is not itself raw-text like `script`/`style`) fires 01-13's own `<body>`-triggered implicit-head-closure fix prematurely, permanently under-counting suppression for the rest of the document. This is reproduced directly against the real code (see the gap above) and is not covered by any of the 818 lines in `tests/test_candidates.py`, including the 15 regressions 01-13 just added for CR-01/CR-02.

This is the third instance of the same defect class in this phase. Per the standing instruction to say so plainly: the targeted, one-fix-per-finding approach is not converging on this parser. `_AnchorCollector`'s flat integer depth counter cannot express "which container is actually open," and every fix applied so far (`_VOID_ELEMENTS` in 01-12, self-closing routing in 01-13 Task 1, the one-shot `<body>` decrement in 01-13 Task 2) has patched a specific symptom of that same structural gap rather than replacing the model. CR-02's own review text already named the complete fix — a stack of currently-open non-rendered container names — and 01-13 explicitly declined it in favor of a narrower one-shot flag ("a deliberate, narrower fix than a full open-container stack... accepted per the plan's explicit preference for the narrower approach unless a required regression fails"). The regression that should have caught this did not exist, because it was never written for a shape one level more adversarial than the review's own two findings. The recommendation is to replace the flat counter with a container-name stack rather than add a fourth special case.

Everything else — the finalization commit point, the shared policy/fingerprint contract, the evidence-sink guard, the connection-level MIME fetch, the prohibition dispositions, and the live transaction record's redaction — is genuinely fixed and independently confirmed below.

### Observable Truths

| # | Source | Truth | Status | Evidence |
|---|---|---|---|---|
| 1 | Roadmap SC1 | Authenticate, confirm the configured mailbox, and inspect a bounded Inbox result without credential/body output | ✓ VERIFIED | Unchanged from initial verification; memory-only auth, exact resource selection, redaction tests pass. |
| 2 | Roadmap SC2 | Configured markers identify candidates and exactly one is selected with redacted identity | ✗ FAILED | Selection/redaction logic itself is sound, but candidate *recognition* remains defeatable — see the gap above (third instance of the suppression-leak class). |
| 3 | Roadmap SC3 | The selected message yields one artifact through the approved HTTPS host with redirect, timeout, and size limits, **and that host/path is bound to an authenticated origin** | ✓ VERIFIED | `validate_https_target` now enforces an exact bucket/path prefix (`allowed_url_prefixes`) on every hop including redirects (`test_prefix_authority_narrows_the_allowed_host`, `test_default_ceiling_rejects_sixth_redirect_without_contact` — 6 hops, each independently validated), and `verify_authenticated_origin` requires a passing DKIM/DMARC/compauth verdict bound to the allowlisted sender domain before any candidate is recognized. Independently reproduced against the review's exact exploit MIME (now rejected). |
| 4 | Roadmap SC4 | Completed download reports exact byte count and checksum | ✓ VERIFIED | Unchanged; plus the fingerprint-length contract is now consistent end to end (8-64 in `AcquisitionConfig`, `DownloadPolicy`, and `evidence._MIN/_MAX_FINGERPRINT_HEX_CHARS`). |
| 5 | Plan 01 | Importing the CLI/package causes no auth, network, directory, or artifact side effect | ✓ VERIFIED | Unchanged. |
| 6 | Plan 01 | Policy is fully validated pre-auth; credentials remain environment-only; tokens remain memory-only | ✓ VERIFIED | `validate_acquisition_policy` is now the single contract called identically by `load_config` and `run_acquisition`; `ControllerPolicyContractTest.test_malformed_policy_is_rejected_identically_by_both_entry_points` asserts zero adapter/filesystem side effects for every malformed case through both entry points. |
| 7 | Plan 01 | Tracer output contains only redacted identity/download evidence | ✓ VERIFIED | Unchanged. |
| 8 | Plan 02 | App-only memory auth confirms exact mailbox without body/raw-provider output | ✓ VERIFIED | Unchanged. |
| 9 | Plan 02 | One inclusive cutoff and four-field metadata query exhaust all pages without a count cap | ✓ VERIFIED | Unchanged. |
| 10 | Plan 02 | Only header-qualified messages trigger MIME retrieval and scanning remains read-only, **with exactly one connection-level GET per MIME fetch** | ✓ VERIFIED | `get_message_mime` now builds the `$value` URL directly through the confirmed folder's own connection (`vicmap_acquire/graph.py:216-253`) instead of calling the SDK's `Folder.get_message`; `test_selective_mime_fetches_by_complete_id_only_on_explicit_call` and `test_scan_plus_one_mime_retrieval_issues_one_request_per_page_plus_one` assert this at the connection-request level, closing the W-01/WR-03 warning. |
| 11 | Plan 03 | Only exact sender/order/subject/MIME/link-cardinality matches become candidates | ✗ FAILED | Same defect as #2 — see the gap above. |
| 12 | Plan 03 | Complete-scan selection deterministically chooses one newest candidate and displays only a fingerprint | ✓ VERIFIED | Unchanged. |
| 13 | Plan 03 | Empty/ambiguous/malformed/mismatched candidates fail closed | ✓ VERIFIED | Unchanged. |
| 14 | Plan 04 | Every initial/redirect target is exact-host HTTPS **and exact bucket/path prefix**, validated before request | ✓ VERIFIED | `validate_https_target` checks `allowed_url_prefixes` in addition to host; every hop of a 6-hop redirect chain is independently validated before contact. |
| 15 | Plan 04 | Connect/read timeouts remain independent with no total-transfer deadline | ✓ VERIFIED | Unchanged. |
| 16 | Plan 04 | Exact inclusive ceiling, persisted-byte count/hash, and atomic no-overwrite publication | ✓ VERIFIED | Unchanged. |
| 17 | Plan 04 | Every handled failure removes private partial state and returns one coherent closed result | ✓ VERIFIED | `_publish_artifact` is now the single documented commit point; a post-link `unlink` failure sets `temp_cleanup_deferred=True` and is still reported as success, never as `artifact_write_failed`. `test_post_link_cleanup_failure_still_reports_a_committed_success` reproduces exactly the scenario the original gap described and asserts the result agrees with on-disk state. |
| 18 | Plan 05 | CLI renders only one closed machine-readable success/progress/failure vocabulary | ✓ VERIFIED | `_EmitOnce` marks a sink `failed` on the first exception and never retries it; `emit_failure` delivers at most one failure. Independently reproduced: a raising sink now produces `INTERNAL_FAILURE` with no raw exception escaping, closing the previous `RuntimeError` leak. |
| 19 | Plan 05 | Exactly one selected candidate enters the downloader and no fallback occurs | ✓ VERIFIED | `test_expired_newest_download_stops_after_one_attempt_without_fallback` asserts `download_artifact` is called exactly once with the newest candidate's URL — read and confirmed to actually assert `assert_called_once()`, not merely execute without error. |
| 20 | Plan 05 | A controlled live run proves one redacted authentic message-to-artifact transaction | ✓ VERIFIED | `01-LIVE-VERIFICATION.md` now records one connected invocation producing `candidate_selected` → `download_target` → `artifact_finalized` from the same process, plus an "Authenticated origin" section recording the live message's passing `dkim`/`dmarc`/`compauth` verdicts. Git history corroborates the narrated timeline (first invocation failed under the pre-01-12 defect at 2026-09-09T16:3x, 01-12 landed at 16:43-16:58, the successful second invocation was recorded at 17:07, same day) — this is not a composite of unrelated runs. |
| 21 | Plan 05 | Live record safely records scope/runtime/disclosure attestations without prohibited source values | ✓ VERIFIED | Re-read in full: no message subject, body, complete Graph message ID, complete URL/query, credential, token, cookie, or raw exception text present. The 2026-09-14 edit that added the prohibition-disposition table and corrected the tenant-scope attestation (from a false "scoped to automations@..." claim to an honest "tenant-wide, mitigated by code-level mailbox pinning" one) touched only attestation/disposition text, not the underlying transaction facts (order ID, fingerprints, byte count, SHA-256 are byte-identical across both versions in git history). |

**Score:** 19/21 truths verified (0 present-but-behavior-unverified)

## Prior Findings (2026-09-09 initial verification, for the record)

The initial verification found 15/21 truths verified and 6 gaps (G-01 authenticity chain missing entirely, G-02 policy validator incomplete/fingerprint-incompatible, G-03 finalization failure state incoherent, G-04 non-rendered HTML treated as visible, G-05 failure sink could leak a raw exception, G-06 three prohibitions left with no verification tier), plus warning W-01/WR-03 (an SDK fake hid an extra Graph GET). All six gaps and the warning are independently confirmed closed above. G-04's underlying defect class (non-rendered HTML content escaping suppression) reopened twice more after that initial closure — once as a production outage fixed in gap-closure plan 01-12, and twice more as CR-01/CR-02 found by a subsequent code review and closed in plan 01-13 — before the fourth (this verification's) instance was found here, still open.

## Required Artifacts

| Artifact | Expected | Status | Details |
|---|---|---|---|
| `read_mailbox.py` | Guarded configuration, orchestration, and CLI | ✓ VERIFIED | Single shared `validate_acquisition_policy` contract; `_EmitOnce` guard; no unguarded failure sink remains. |
| `vicmap_acquire/graph.py` | Memory-only Graph mailbox boundary | ✓ VERIFIED | Connection-level MIME fetch closes the extra-GET warning; non-Inbox folder rejected before any request (`test_prohib_01_non_inbox_folder_rejected_before_any_request`). |
| `vicmap_acquire/origin.py` | Authenticated-origin policy (new module, gap-closure) | ⚠ PARTIAL | DKIM/DMARC/compauth verification, address/domain alignment, and total exception handling are sound and independently reproduced; module itself introduces no new gap. |
| `vicmap_acquire/candidates.py` | Pure recognition and deterministic selection | ✗ PARTIAL | Selection logic is sound; recognition is defeatable a third time — see gap above. |
| `vicmap_acquire/download.py` | Constrained stream/hash/finalization boundary | ✓ VERIFIED | Publication commit point, bucket/path prefix, and per-hop redirect authorization all independently confirmed. |
| `vicmap_acquire/evidence.py` | Closed safe event schema/renderers | ✓ VERIFIED | Fingerprint length bounds (8-64) now match the policy/download contract exactly. |
| `vicmap.toml` | Reviewable non-secret policy | ✓ VERIFIED | `allowed_url_prefixes` now present and enforced; `required_authentication_results` present. |
| `.gitignore` | Runtime/token/artifact exclusions | ✓ VERIFIED | `artifacts/` pattern (unanchored) covers root-level and nested output roots; `output_dir.name` is restricted to `{"artifacts"}` by policy, so no supported output root escapes the ignore pattern. Confirmed by `tests/test_repository_policy.py` calling real `git check-ignore` against root-level, nested, and partial-file cases. |
| `tests/test_graph.py` | Graph and tracer regressions | ✓ VERIFIED | Connection-level MIME assertions close the prior production-shape gap. |
| `tests/test_candidates.py` | Recognition/selection regressions | ✗ PARTIAL | 818 lines, 15 new CR-01/CR-02 regressions added by 01-13, but still no coverage for a `<body>` nested inside a non-raw-text non-rendered container. |
| `tests/test_download.py` | Transport/stream/finalization regressions | ✓ VERIFIED | Commit-point, concurrency, and per-hop redirect-authorization regressions all read and confirmed to test the claimed property. |
| `tests/test_evidence.py` | Evidence/controller regressions | ✓ VERIFIED | Failing-sink and shared-policy-contract cases now present and confirmed to assert the specific behavior claimed. |
| `tests/test_origin.py` | Authenticated-origin regressions (new) | ✓ VERIFIED | DMARC absence/blank/unparseable regressions independently reproduced against the live-observed header shape. |
| `tests/test_repository_policy.py` | Ignore-coverage regressions (new) | ✓ VERIFIED | Exercises real `git check-ignore`, not pattern text inspection. |
| `01-LIVE-VERIFICATION.md` | Safe live proof | ✓ VERIFIED | One connected transaction, authenticated-origin evidence, redaction confirmed, tenant-scope attestation corrected. |

## Key Link Verification

| From | To | Via | Status | Details |
|---|---|---|---|---|
| `read_mailbox.py` | `graph.py` | Validated config constructs Graph adapter | ✓ WIRED | `validate_acquisition_policy` runs before adapter construction in both entry points. |
| `read_mailbox.py` | `candidates.py` | Metadata plus lazy MIME feed recognition and selection | ⚠ PARTIAL | Wiring itself is sound; the fed candidate can still be a false positive from the recognition defect above. |
| `candidates.py` | `origin.py` | `recognize_candidate` calls `verify_authenticated_origin` before accepting a link match | ✓ WIRED | Confirmed at `candidates.py:316-323`; a failing origin check raises before any link extraction result is trusted. |
| `read_mailbox.py` | `download.py` | One selected candidate feeds one downloader call | ✓ WIRED | Unchanged; one-call/no-fallback test passed. |
| `validate_https_target` | Requests send | Validate initial and every redirect target, including bucket/path prefix, before `session.get` | ✓ WIRED | 6-hop chain test confirms validation precedes every hop's contact. |
| `iter_content` | `DownloadResult` | Persist/count/hash then no-overwrite publish with one commit point | ✓ WIRED | `_publish_artifact` isolates the commit; post-commit cleanup failure cannot flip the reported result. |
| `DownloadResult` | success renderer | Host/path fingerprint, bytes, SHA-256 events | ✓ WIRED | Fingerprint length is now a single consistent contract from config through evidence rendering. |
| `run_acquisition` | event sink | Every emission routed through `_EmitOnce`, never retried after failure | ✓ WIRED | Reproduced directly: a raising sink yields `INTERNAL_FAILURE`, no raw exception escapes. |

## Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|---|---|---|---|---|
| `read_mailbox.py` | `metadata` | Real O365 Inbox iterator | Yes | ✓ FLOWING |
| `candidates.py` | `Candidate` | Graph metadata plus selected MIME plus authenticated origin | Yes, origin now authenticated, but recognition still admits some non-genuinely-displayed URLs | ⚠ FLOWING / PARTIALLY TRUSTED |
| `download.py` | artifact stream | Real clean Requests session, bucket/path constrained | Yes, ownership constrained to the configured prefix | ✓ FLOWING / TRUSTED |
| `evidence.py` | candidate/target/final events | Selected candidate and `DownloadResult` | Yes, fingerprint contract consistent end to end | ✓ FLOWING |
| `01-LIVE-VERIFICATION.md` | live provenance chain | One connected process invocation | Yes — retained, connected, corroborated by commit timestamps | ✓ FLOWING |

## Behavioral Spot-Checks

All commands used only synthetic values. No live mailbox, credentials, complete provider identifiers/URLs, or artifact contents were accessed.

| Behavior | Command | Result | Status |
|---|---|---|---|
| Full deterministic suite | `OPNIX_ENV_DISABLE=1 nix develop --impure --no-write-lock-file path:. --command python -m unittest discover -s tests` | 184 tests, 0 failures, 0 skips | ✓ PASS |
| CR-01 repro (self-closing script/style leak) | `python3 -c` against `_extract_html_urls`/`extract_html_hrefs` | `[]` for both text-in-script and anchor-in-style shapes | ✓ PASS (fixed) |
| CR-02 repro (omitted `</head>` strands suppression) | `python3 -c` against `extract_html_hrefs` | Archive link recovered | ✓ PASS (fixed) |
| WR-01 repro (DMARC `header.from` absence) | `python3 -c` against `verify_authenticated_origin` | `OriginUnauthenticated` raised (was previously accepted) | ✓ PASS (fixed) |
| Named prohibition-disposition tests exist and assert the claimed property | direct file read of each cited test | All 15 named tests across 4 files exist; spot-read 5 of them line-by-line and confirmed they assert the specific claim (e.g. `downloader.assert_called_once()` with the newest URL, `construction.assert_not_called()` for non-Inbox rejection) | ✓ PASS |
| Multi-hop redirect authorization | direct file read of `test_default_ceiling_rejects_sixth_redirect_without_contact` | 6 hops, each independently validated, 6th never contacted | ✓ PASS |
| Post-commit cleanup failure reporting | direct file read of `test_post_link_cleanup_failure_still_reports_a_committed_success` | Asserts `temp_cleanup_deferred=True`, final path exists, byte count/hash correct | ✓ PASS |
| Third-instance suppression-leak hunt (verification priority #2) | `python3 -c` against `_extract_html_urls`/`extract_html_hrefs`, `<body>` nested inside `template`/`object` | Archive link/URL leaked (`['http://evil.example.com/Order_U.zip']` instead of `[]`) for three variants (bare text, anchor href, and via `object` instead of `template`) | ✗ FAIL — new gap |
| Git commit provenance for all cited gap-closure commits | `git cat-file -t <hash>` for 10 commits cited across 01-11/01-12/01-13 SUMMARY.md | All 10 resolve as real commits with timestamps consistent with the narrated sequence | ✓ PASS |
| Debt-marker scan | `grep -rn "TBD\|FIXME\|XXX"` across all modified source files | No matches | ✓ PASS |

## Probe Execution

No executable `probe-*.sh` was declared or found for this phase. N/A.

## Requirements Coverage

| Requirement | Source Plans | Description | Status | Evidence |
|---|---|---|---|---|
| MAIL-01 | 01-01, 01-02, 01-05, 01-09, 01-10, 01-11 | Authenticate/confirm configured mailbox without credential/body disclosure | ✓ SATISFIED | Unchanged plus tenant-scope attestation now honestly recorded as a mitigated residual risk rather than a false "scoped" claim. |
| MAIL-02 | 01-01, 01-02, 01-03, 01-05, 01-06, 01-07, 01-09, 01-10, 01-11, 01-12, 01-13 | Bounded Inbox scan and configured candidate recognition | ✗ BLOCKED | A third instance of the non-rendered-content suppression-leak defect remains open (see gap above). `REQUIREMENTS.md` marks MAIL-02 Complete; this marking is not earned. |
| MAIL-03 | 01-01, 01-03, 01-05, 01-09, 01-11 | Deterministically select exactly one and show redacted identity | ✓ SATISFIED | Selection algorithm itself (given a correct candidate set) is sound and independently confirmed. |
| MAIL-04 | 01-01, 01-04, 01-05, 01-08 | Download one artifact only through approved bounded HTTPS | ✓ SATISFIED | Bucket/path binding, per-hop authorization, and finalization commit-point are all independently confirmed. |
| MAIL-05 | 01-01, 01-04, 01-05, 01-09 | Show exact artifact byte count and checksum | ✓ SATISFIED | Fingerprint contract now consistent end to end; policy validator prevents publish-then-fail. |

No Phase 1 requirement is orphaned. MAIL-02 is the only requirement whose `REQUIREMENTS.md` "Complete" marking is not currently earned by the codebase.

## Prohibition Gate

| Prohibition | Automated evidence | Disposition |
|---|---|---|
| PROHIB-01 — no mailbox mutation | 4 named tests in `tests/test_graph.py::GraphReadOnlyEnforcementTest`, all read and confirmed to test the claim (read-only calls only, no mutation endpoint touched, no mutation callable exposed, non-Inbox folder rejected pre-request) | ✓ accepted, bhillermann@vegetationlink.com.au, 2026-09-14 |
| PROHIB-02 — no Graph/ambient authority at artifact host | 2 named tests in `tests/test_download.py`, read and confirmed (auth/cookies cleared, `trust_env=False`, manual redirects, TLS verify, timeout tuple) | ✓ accepted, bhillermann@vegetationlink.com.au, 2026-09-14 |
| PROHIB-03 — no incomplete/failed/over-limit final publication | 8 named tests in `tests/test_download.py`, read and confirmed (concurrent-winner, post-link cleanup, pre-commit timeout/over-limit/short-write/length-mismatch/existing-path families, keyboard-interrupt cleanup) | ✓ accepted, bhillermann@vegetationlink.com.au, 2026-09-14 |
| PROHIB-04 — no substitution of an older/different order's artifact after failure | 1 named test in `tests/test_evidence.py`, read line-by-line and confirmed it asserts `download_artifact` is called exactly once with the *newest* candidate's URL, not the older one | ✓ accepted, bhillermann@vegetationlink.com.au, 2026-09-14 |
| PROHIB-05 — no automatic widening of the trust policy from a received message | 4 named tests plus `test_origin.py`'s unauthenticated-origin rejections, read and confirmed; also corroborated by 01-11/01-12's own history (the ready message initially failed recognition and was fixed without relaxing any trust value) | ✓ accepted, bhillermann@vegetationlink.com.au, 2026-09-14 |

All five dispositions are genuinely evidenced — this is a real improvement over the initial verification's finding of three descriptor-less, unresolved prohibitions.

## Test Quality Audit

| Test File | Linked Reqs | Active | Skipped | Circular | Assertion Level | Verdict |
|---|---|---:|---:|---:|---|---|
| `tests/test_candidates.py` | MAIL-02, MAIL-03 | ~65 | 0 | 0 | Behavioral/value | ✗ Still incomplete — the 15 new CR-01/CR-02 regressions raise coverage against known-realistic markup, but no test covers a `<body>` nested inside a non-raw-text non-rendered container (the third instance found in this verification). This is the same "tidy fixture" class flagged twice before. |
| `tests/test_download.py` | MAIL-04, MAIL-05 | ~50 | 0 | 0 | Behavioral/value | ✓ Commit-point and per-hop redirect authorization now covered with production-realistic shapes. |
| `tests/test_evidence.py` | MAIL-01, MAIL-03, MAIL-05, orchestration | ~55 | 0 | 0 | Behavioral/value | ✓ Failing-sink and shared-policy-contract cases now covered. |
| `tests/test_graph.py` | MAIL-01, MAIL-02 | ~40 | 0 | 0 | Behavioral/value | ✓ Connection-level MIME request-count assertions close the prior production-shape gap. |
| `tests/test_origin.py` | MAIL-02 (authenticity) | 19 | 0 | 0 | Behavioral/value | ✓ DMARC absence/blank/unparseable and live-shape acceptance all covered. |
| `tests/test_repository_policy.py` | none (infra hygiene) | 3 | 0 | 0 | Behavioral (real `git check-ignore`) | ✓ Exercises the real tool, not pattern text. |

**Disabled tests on requirements:** 0
**Circular patterns detected:** 0
**New defect class instance found in this audit:** 1 (see gap above) — this is the third occurrence of "the fix is correct against every markup shape a human wrote as a test, but the underlying model has no concept of nested/foreign tokenizer contexts, so a shape one step more adversarial than the existing regressions defeats it again."

## Anti-Patterns and Review Findings

| Finding | Status | Verdict |
|---|---|---|
| CR-01 (self-closing non-void tags leak content) | ✅ CLOSED | Independently reproduced fixed against the review's exact exploit snippets. |
| CR-02 (omitted `</head>` strands suppression) | ✅ CLOSED | Independently reproduced fixed against the review's exact exploit snippet. |
| WR-01 (DMARC `header.from` absence more permissive than mismatch) | ✅ CLOSED | Independently reproduced fixed against the review's exact exploit MIME. |
| **New: `<body>` nested in template/object/iframe/applet prematurely unwinds suppression** | 🛑 OPEN — BLOCKER | Third instance of the same class; see gap above. `candidates.py` was modified by 01-07/01-12/01-13, all after the prior `verified:` timestamp, so this is in-scope for this re-verification round regardless of the convergence-gate's evidence bar — and deterministic reproduction is provided regardless. |
| WR-02 (MSO conditional comments unconditionally suppressed) | ⚠ OPEN — not blocking | Explicitly deferred by 01-13 as availability-only (fail-closed, no security exposure); consistent with the review's own severity assessment. |
| WR-03/new (SafeFailure events never carry `order_id`/fingerprints) | ⚠ OPEN — not blocking | Explicitly deferred by 01-13; audit/operability concern only, no disclosure risk (errs toward under-sharing). |
| IN-01 (duplicated provider-logger suppression lists) | ℹ OPEN — informational | No functional impact today; maintenance hazard only. |
| IN-02 (`_fsync_directory` non-`OSError` exception assumption) | ℹ OPEN — informational | Not reachable with current call sites. |

No unreferenced `TBD`, `FIXME`, or `XXX` debt markers were found in any file modified across the gap-closure plans.

## Disconfirmation Pass

- **The one thing that should have been re-tested most aggressively — HTML suppression — is exactly where a new defect was found.** Three separate, structurally distinct triggers (void elements in 01-12, self-closing spellings in CR-01, omitted `</head>` in CR-02, and now nested `<body>` in a non-raw-text container) have each defeated the same guarantee. This is not a coincidence of unlucky test selection; it is evidence that a flat integer depth counter cannot soundly model HTML's tree-construction rules, and each fix so far has narrowed the class of adversarial input rather than eliminating the structural cause.
- **Everything downstream of "authentic origin" is now solid.** The DKIM/DMARC/compauth check, the bucket/path prefix constraint on every redirect hop, and the finalization commit point were all independently reproduced and hold up under direct scrutiny — this is genuine, substantial progress since the initial verification, not narrative dressing.
- **The live record's redaction and provenance both hold up.** The 2026-09-14 edit to `01-LIVE-VERIFICATION.md` only touched attestation/disposition text (correcting a previously false tenant-scope claim), not the underlying transaction facts, confirmed by diffing the two committed versions.

## Decision Coverage

Not independently re-derived line-by-line in this pass (non-blocking gate); the initial verification's finding that all 20 trackable CONTEXT.md decisions were honored was not contradicted by anything found in this re-verification, and no new decision was introduced that appears abandoned.

## Human Verification Required

None beyond what the operator has already performed. No additional live mailbox run is recommended until the newly-found gap is closed — per PROHIB-05's own established discipline, do not relax any trust value to force a message through; fix the parser model, add the missing regression class, then perform (or reuse, since no policy value needs to change) a controlled proof.

## Gaps Summary

The phase has made genuine, substantial, independently-verified progress: five of six original gaps plus the extra-GET warning are closed with real fixes and real tests, not narrative. The authenticity chain the initial verification found completely absent is now real. The one remaining gap is a third instance of the exact defect class the phase has now produced three times (a production outage, two code-review Criticals, and now this): the HTML suppression model in `vicmap_acquire/candidates.py` is a flat counter that cannot express which non-rendered container is actually open, and each targeted fix has closed one specific trigger rather than the structural cause. This blocks the phase goal because it falsifies "only a genuinely displayed archive occurrence can qualify a candidate" (roadmap SC2 / MAIL-02) via a reproducible, deterministic exploit against the current code. `REQUIREMENTS.md` marking MAIL-02 Complete is not currently earned.

---

_Verified: 2026-09-14T12:00:00Z_
_Verifier: Claude (gsd-verifier)_
