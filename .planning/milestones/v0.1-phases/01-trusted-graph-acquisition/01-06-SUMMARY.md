---
phase: 01-trusted-graph-acquisition
plan: 06
subsystem: acquisition
tags: [python, dkim, dmarc, authentication-results, email, ssrf, trust-boundary]

requires:
  - phase: 01-03
    provides: Exact ready-message recognition and deterministic newest-candidate selection
  - phase: 01-04
    provides: Constrained HTTPS streaming, atomic finalization, exact bytes, and SHA-256 provenance
  - phase: 01-05
    provides: Closed disclosure-safe evidence and one-call fail-closed orchestration
provides:
  - Pure `vicmap_acquire/origin.py` policy binding D-01's sender allowlist to a passing DKIM/DMARC/compauth verdict recorded by the trusted receiving mail infrastructure, rather than to any provider-supplied label
  - An exact configured URL-prefix authority narrowing the D-13 host allowlist on every initial and redirect hop
  - A new closed reason code `origin_unauthenticated` mapped to the `candidate` stage
  - Committed end-to-end positive and negative regressions closing verification gap G-01 bullets 1-3
affects: [02-safe-geospatial-discovery, trusted-graph-acquisition, evidence]

actuals:
  tokens: 14436
  tasks: 3
  commits: 4
commits: 4
plan_head_before: 5573dd97e86a9e6f83249e1e80b89c6350838803

tech-stack:
  added: []
  patterns:
    - "Authenticated origin as a pure policy module with total exception conversion (any parsing/evaluation failure becomes OriginUnauthenticated, never a raw exception)"
    - "Every present Authentication-Results header must independently satisfy all required verdicts, so a forged extra passing header cannot mask a genuine failing one"
    - "Exact URL-prefix authority narrows an already-allowlisted host, applied identically to the initial hop and every redirect hop"

key-files:
  created:
    - vicmap_acquire/origin.py
    - tests/test_origin.py
  modified:
    - vicmap_acquire/candidates.py
    - vicmap_acquire/download.py
    - vicmap_acquire/evidence.py
    - read_mailbox.py
    - vicmap.toml
    - tests/test_candidates.py
    - tests/test_download.py
    - tests/test_evidence.py
    - tests/test_graph.py

key-decisions:
  - "Chose the trusted receiving mail infrastructure's DKIM/DMARC/compauth Authentication-Results verdict as the authenticity signal because Vicmap DataShare publishes no artifact signature or out-of-band digest, and this project already trusts that verdict for mailbox access itself."
  - "Bound D-01's sender allowlist to the DKIM-covered From header (not Graph's provider-supplied from field), and additionally required the Graph metadata sender to agree with it."
  - "Required every present Authentication-Results header to independently pass, defeating a forged extra passing header that would otherwise mask a genuine failing one."
  - "Narrowed the D-13 host allowlist with an exact configured URL prefix applied to both the initial target and every redirect hop, not just the first request."
  - "Left vicmap.toml's allowed_url_prefixes value as a deliberately fail-closed placeholder pending operator confirmation of the exact trusted bucket/path at the 01-11 checkpoint."

patterns-established:
  - "Pure policy module with no I/O and no imports from candidates/download/read_mailbox — dependency direction stays leaf-ward."
  - "Closed-error total wrapping: verify_authenticated_origin converts every internal exception to OriginUnauthenticated with `from None`, constructed with no arguments so no untrusted text can enter it."

requirements-completed: []

coverage:
  - id: D1
    description: "A ready-order message is only accepted when the trusted receiving mail infrastructure recorded a passing DKIM verdict and the DKIM-covered From header matches the configured sender allowlist."
    requirement: MAIL-04
    verification:
      - kind: unit
        ref: "tests/test_origin.py#VerifyAuthenticatedOriginTest and HardenedOriginParserTest"
        status: pass
      - kind: integration
        ref: "tests/test_candidates.py#CandidateRecognitionTest.test_malformed_mime_fails_origin_verification_before_link_extraction"
        status: pass
      - kind: e2e
        ref: "tests/test_evidence.py#ControllerCompositionTest.test_authenticated_origin_completes_end_to_end_with_expected_events"
        status: pass
    human_judgment: false
  - id: D2
    description: "A message whose archive link points at a different bucket/path on the allowed regional host is rejected before any byte of that target is fetched."
    requirement: MAIL-04
    verification:
      - kind: unit
        ref: "tests/test_download.py#DownloadTargetPolicyTest.test_prefix_authority_narrows_the_allowed_host"
        status: pass
      - kind: unit
        ref: "tests/test_download.py#DownloadTransportBoundaryTest.test_redirect_leaving_the_configured_prefix_is_rejected_after_one_contact"
        status: pass
      - kind: e2e
        ref: "tests/test_evidence.py#ControllerCompositionTest.test_matching_message_pointing_outside_the_configured_prefix_is_rejected"
        status: pass
    human_judgment: false
  - id: D3
    description: "Forging an extra passing Authentication-Results header cannot make an otherwise unauthenticated message acceptable, because every present header must satisfy the required verdicts."
    requirement: MAIL-04
    verification:
      - kind: e2e
        ref: "tests/test_evidence.py#ControllerCompositionTest.test_injected_passing_header_cannot_rescue_a_genuine_failing_verdict"
        status: pass
    human_judgment: false
  - id: D4
    description: "An unauthenticated origin is reported as the closed reason code origin_unauthenticated at the candidate stage, and no artifact host is contacted."
    requirement: MAIL-04
    verification:
      - kind: unit
        ref: "tests/test_evidence.py#EvidenceContractTest.test_every_reason_has_one_fixed_stage_and_remediation_hint"
        status: pass
      - kind: e2e
        ref: "tests/test_evidence.py#ControllerCompositionTest.test_unauthenticated_dkim_verdict_is_rejected_before_any_download_contact"
        status: pass
    human_judgment: false
  - id: D5
    description: "vicmap.toml carries a reviewable non-secret trust policy including the required authentication verdicts and a fail-closed placeholder authorized URL prefix awaiting operator confirmation."
    verification: []
    human_judgment: true
    rationale: "The placeholder bucket/path prefix is intentionally non-functional until an operator replaces it with the exact trusted value at the 01-11 blocking-human checkpoint; no automated test can confirm the real-world value."

duration: 20min
completed: 2026-09-09
status: complete
---

# Phase 01 Plan 06: Authenticated Origin and Bucket-Prefix Authority Summary

**New `vicmap_acquire/origin.py` binds D-01's sender allowlist to a passing DKIM/DMARC/compauth Authentication-Results verdict, and an exact configured URL prefix narrows the D-13 host allowlist on every hop, closing verification gap G-01 bullets 1-3.**

## Performance

- **Duration:** ~20 min
- **Started:** 2026-09-09T14:18:16+10:00
- **Completed:** 2026-09-09T14:34:33+10:00
- **Tasks:** 3
- **Files modified:** 11 (2 created, 9 modified)

## Accomplishments

- Authenticated-origin policy (`vicmap_acquire/origin.py`) parses `Authentication-Results` headers, requires every present header to independently pass all required verdicts, aligns `header.d`/`header.from` to the `From` domain on label boundaries, and is total (never raises anything but `OriginUnauthenticated`).
- `vicmap_acquire/candidates.py` now calls `verify_authenticated_origin` on every candidate's loaded MIME before any archive link is extracted, and uses the authenticated address (not the provider label) as `Candidate.sender`.
- `vicmap_acquire/download.py` gained `allowed_url_prefixes` on `DownloadPolicy` and a `_normalize_url_prefix` validator; `validate_https_target` now requires every initial and redirect target to satisfy both the D-13 host allowlist and the configured bucket/path prefix.
- `vicmap_acquire/evidence.py` and `read_mailbox.py` wire the new `origin_unauthenticated` closed reason code (stage `candidate`) end to end, including through the typed-failure translation in `run_acquisition`.
- End-to-end positive proof (authenticated origin + in-prefix target completes with `candidate_selected`, `download_target`, `artifact_finalized`) and four negative proofs (wrong-bucket, unauthenticated origin, forged extra header, sender/From mismatch) committed in `tests/test_evidence.py`, plus a dedicated redirect-out-of-prefix regression in `tests/test_download.py`.
- Hardening suite in `tests/test_origin.py` (15 tests total) covers malformed/empty/unterminated-comment headers, absent required methods, the full non-`pass` verdict table, label-boundary domain alignment (`evilmaps.vic.gov.au` correctly rejected, `maps.vic.gov.au` correctly accepted), `From` cardinality violations, non-bytes/empty/unparseable MIME, case-insensitive comparison, and a disclosure regression proving no raised error leaks seeded private MIME content.

## Task Commits

Each task was committed atomically (TDD RED/GREEN per the tracer + hardening structure):

1. **Task 1: End-to-end authenticated origin to authorized target** - `2a75329` (test, RED: failing origin module regressions) then `b8ee4b1` (feat: bind trust to DKIM-verified origin and bucket prefix)
2. **Task 2: The negative twin — matching message, wrong bucket, rejected before transport** - `e8aa981` (test: reject wrong-bucket and unauthenticated origin messages)
3. **Task 3: Harden the authenticated-origin parser against malformed and adversarial headers** - `e4f82f6` (test: harden origin parser against adversarial headers)

_Note: Tasks 2 and 3 produced test-only commits because Task 1's implementation, written directly against the full behavioral specification (total exception wrapping, label-boundary domain alignment, `From` cardinality, every-header-must-pass), already satisfied every case those tasks specify. Each task's tests were run immediately after being written; all passed without further implementation changes, so no separate GREEN commit was needed for Tasks 2 or 3._

## Files Created/Modified

- `vicmap_acquire/origin.py` - Pure authenticated-origin policy: `OriginPolicy`, `OriginUnauthenticated`, `parse_authentication_results`, `verify_authenticated_origin`
- `tests/test_origin.py` - 15 regressions covering the happy path, negative cases, and hardening
- `vicmap_acquire/candidates.py` - Calls `verify_authenticated_origin` before archive-link extraction; uses authenticated address as `Candidate.sender`
- `vicmap_acquire/download.py` - `DownloadPolicy.allowed_url_prefixes`, `_normalize_url_prefix`, prefix check in `validate_https_target`
- `vicmap_acquire/evidence.py` - `ReasonCode.ORIGIN_UNAUTHENTICATED` mapped to `Stage.CANDIDATE`
- `read_mailbox.py` - `AcquisitionConfig.required_authentication_results` / `.allowed_url_prefixes`, config parsing/validation, wiring into `recognize_candidate` and `DownloadPolicy`, `OriginUnauthenticated` added to the typed-failure translation tuple
- `vicmap.toml` - `required_authentication_results` under `[mailbox]`, `allowed_url_prefixes` (fail-closed placeholder) under `[download]`
- `tests/test_candidates.py`, `tests/test_download.py`, `tests/test_evidence.py`, `tests/test_graph.py` - Updated fixtures/helpers for the new authentication header and prefix policy; new end-to-end and negative regressions

## Decisions Made

See `key-decisions` in frontmatter. In short: DKIM/DMARC/compauth verdicts from the trusted receiving mailbox infrastructure are the authenticity signal (no artifact signature exists to use instead); the sender allowlist is now bound to the authenticated `From` header, not any provider label; every present `Authentication-Results` header must pass (defeats header injection); the URL-prefix authority applies to every hop, not just the first request.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Corrected the prefix-authority normalization to strip the port before comparison**
- **Found during:** Task 1 verification (`tests.test_download` full run)
- **Issue:** The initial `validate_https_target` prefix check built `normalized_target` from `target.netloc.casefold()`, which includes an explicit port (e.g. `:443`). A URL like `https://host:443/archive.zip` then failed to match a prefix of `https://host/`, even though it is the same authority as the bare-host form already accepted by the existing host-allowlist check.
- **Fix:** Built `normalized_target` from `normalized_hostname` (already port-stripped) instead of `target.netloc`.
- **Files modified:** `vicmap_acquire/download.py`
- **Verification:** `tests/test_download.py::DownloadTargetPolicyTest.test_accepts_only_exact_https_host_and_normalizes_case` passes for the `:443` case.
- **Committed in:** `b8ee4b1` (Task 1 GREEN commit)

**2. [Rule 1 - Bug] Updated pre-existing redirect-loop/ceiling test fixtures to stay within the newly-configured prefix**
- **Found during:** Task 1 verification (`tests.test_download` full run)
- **Issue:** `test_relative_redirect_is_resolved_and_each_response_is_closed`, `test_redirect_loop_stops_without_recontacting_a_seen_target`, and `test_default_ceiling_rejects_sixth_redirect_without_contact` used `Location` values (`../final.zip`, `/second.zip`, `/hop-N.zip`) that predate the prefix constraint and now legitimately leave the configured `/orders/` prefix, causing them to fail for the (correct, new) reason of a prefix violation instead of testing what they were designed to test (redirect-loop and ceiling handling).
- **Fix:** Adjusted the `Location` values to stay within `/orders/` so each test again exercises only its intended boundary.
- **Files modified:** `tests/test_download.py`
- **Verification:** Full `tests.test_download` suite green (29/29).
- **Committed in:** `b8ee4b1` (Task 1 GREEN commit)

**3. [Rule 2 - Missing Critical] Added defensive non-empty/`dkim`-presence validation for the two new config fields to `_validate_config_object`**
- **Found during:** Task 1 implementation review
- **Issue:** `_validate_config_object` (invoked at the top of every `run_acquisition` call, not just via `load_config`) validated non-emptiness of `allowed_senders`/`allowed_order_ids`/`allowed_hosts` but not the two new fields. A directly-constructed `AcquisitionConfig` with an empty `required_authentication_results` would silently disable all authentication-verdict requirements (only the "at least one header present" check would remain).
- **Fix:** Added `required_authentication_results`/`allowed_url_prefixes` non-emptiness and `"dkim" in required_authentication_results` to the same defensive check already used for the other allowlists.
- **Files modified:** `read_mailbox.py`
- **Verification:** Full suite green; existing directly-constructed test configs all supply valid non-empty values for both fields.
- **Committed in:** `b8ee4b1` (Task 1 GREEN commit)

---

**Total deviations:** 3 auto-fixed (2 bugs found via test execution, 1 missing-critical defensive validation)
**Impact on plan:** All three are necessary for correctness (port-stripped prefix comparison) or defense-in-depth (config validation); the redirect-fixture updates preserve each test's original intent under the new prefix constraint. No scope creep.

## Known Stubs

- `vicmap.toml` `[download].allowed_url_prefixes` is set to `["https://s3.ap-southeast-2.amazonaws.com/REPLACE-WITH-EXACT-TRUSTED-BUCKET-PREFIX/"]` — a syntactically valid but deliberately non-functional placeholder. This is intentional and documented in the plan: the value fails closed (rejects every real target) until an operator replaces it with the exact trusted bucket/path at the blocking-human checkpoint in plan 01-11. Recorded in `.planning/WINDOWS.md` (kind: stub, phase 01).

## Issues Encountered

None beyond the auto-fixed deviations above.

## User Setup Required

None - no external service configuration required. (The `vicmap.toml` prefix placeholder requires an *operator decision*, not setup automation, and is gated by the 01-11 checkpoint per the plan's own design.)

## Next Phase Readiness

- Verification gap G-01 bullets 1-3 (unauthenticated sender origin, unconstrained bucket/path on an allowlisted host, header-injection bypass) are closed with committed automated regressions.
- `requirements-completed` is intentionally empty: `MAIL-01..05` remain in "Gaps Found" status in `REQUIREMENTS.md` because sibling gap-closure plans 01-07 through 01-11 in this phase have not yet produced summaries (`gsd-tools requirements ready-ids` returned 0/5 ready). The shared-ID gate will mark them complete once the last declaring plan finishes.
- Remaining phase 01 gap-closure work (edge-case row authoring in 01-07/01-08/01-09, prohibition dispositions in 01-11, and the operator's `vicmap.toml` prefix confirmation) is unblocked and can proceed.

---
*Phase: 01-trusted-graph-acquisition*
*Completed: 2026-09-09*

## Self-Check: PASSED

- FOUND: vicmap_acquire/origin.py
- FOUND: tests/test_origin.py
- FOUND commit: 2a75329 (test, RED)
- FOUND commit: b8ee4b1 (feat, GREEN)
- FOUND commit: e8aa981 (test)
- FOUND commit: e4f82f6 (test)
- Full deterministic suite: `nix develop path:. -c python -m unittest discover -s tests -p 'test_*.py' -v` → 103 tests, OK, no skips
- `tests.test_origin` alone → 15 tests, OK
- Re-ran all task-level `<acceptance_criteria>` greps and behavioral assertions: all pass (see plan verification above)
