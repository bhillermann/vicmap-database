---
phase: 01-trusted-graph-acquisition
plan: 04
subsystem: acquisition
tags: [python, requests, ssrf, streaming, sha256, atomic-publication]
requires:
  - phase: 01-01
    provides: Guarded artifact-download seam, clean Requests session pattern, and private no-overwrite publication tracer
provides:
  - Exact HTTPS authority validation before the initial request and every bounded manual redirect
  - Clean artifact-only Requests sessions with independent connect and stalled-read timeouts
  - Exact inclusive byte ceilings, persisted-byte SHA-256, and integer-derived progress
  - Private mode-0600 temporary storage with atomic hard-link no-overwrite publication
  - Closed safe download failures and approved-host/path-only result provenance
affects: [01-05, trusted-graph-acquisition, acquisition-evidence]
actuals:
  tokens: 12425
  tasks: 2
  commits: 4
commits: 4
plan_head_before: 7046ed2fbede69871cf6fa842f661db7c5230b76
tech-stack:
  added: []
  patterns: [validate-before-send, clean authority-specific sessions, prospective byte accounting, atomic no-overwrite publication]
key-files:
  created:
    - tests/test_download.py
    - .planning/phases/01-trusted-graph-acquisition/01-04-TASK1-RED.json
    - .planning/phases/01-trusted-graph-acquisition/01-04-TASK2-RED.json
  modified:
    - vicmap_acquire/download.py
key-decisions:
  - "Translate the Plan 01 tracer call into the explicit DownloadPolicy internally while exposing the final-path policy-first API required by Plan 04."
  - "Treat URL identity as normalized hostname, effective port, path, and query so redirect loops are rejected before recontact without disclosing source URLs."
  - "Derive one-decimal progress with integer tenths and fingerprint only the final approved URL path, never its query or complete URL."
  - "Publish with a same-directory hard link so pre-existing and concurrent destinations cannot be overwritten."
patterns-established:
  - "Outbound authorization: validate exact HTTPS scheme, authority, hostname, port, userinfo absence, and fragment absence before every session.get call."
  - "Artifact provenance: count and hash only complete chunks successfully written to private storage, then expose a final path after atomic publication."
requirements-completed: [MAIL-04, MAIL-05]
coverage:
  - id: D1
    description: "Only exact allowlisted HTTPS targets are contacted through clean one-hop Requests calls with bounded manual redirects and separate connect/read timeouts."
    requirement: MAIL-04
    verification:
      - kind: integration
        ref: "tests/test_download.py#DownloadTargetPolicyTest and DownloadTransportBoundaryTest"
        status: pass
    human_judgment: false
  - id: D2
    description: "Remote bodies are streamed through declared and observed inclusive ceilings into private state and atomically published without overwrite."
    requirement: MAIL-04
    verification:
      - kind: integration
        ref: "tests/test_download.py#DownloadStreamingBoundaryTest"
        status: pass
    human_judgment: false
  - id: D3
    description: "Final results report exact persisted bytes, full SHA-256, approved normalized hostname, and a path-only fingerprint with exact periodic progress."
    requirement: MAIL-05
    verification:
      - kind: unit
        ref: "tests/test_download.py#test_missing_content_length_streams_and_returns_safe_provenance and test_format_progress_uses_exact_integer_tenths"
        status: pass
    human_judgment: false
duration: 22min
completed: 2026-09-08
status: complete
---

# Phase 1 Plan 4: Constrained Artifact Download Summary

**Every artifact hop is now independently authorized before contact, and exact persisted bytes are privately hashed and atomically published without overwrite.**

## Performance

- **Duration:** 22 minutes
- **Started:** 2026-09-08T02:51:37Z
- **Completed:** 2026-09-08T03:13:43Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments

- Enforced exact case-normalized HTTPS host and authority checks before the initial request and every manually resolved redirect, including userinfo, fragment, port, downgrade, off-host, malformed-authority, loop, and hop-exhaustion rejection.
- Removed Graph and ambient credential state from a separately owned artifact session, disabled environment proxy/netrc inheritance, retained certificate verification, and passed independent connect/stalled-read timeouts without a total transfer deadline.
- Enforced strict declared-length parsing plus a prospective observed-byte ceiling before each write, updating byte count and SHA-256 only after each complete chunk was persisted.
- Added interval-based known/unknown-total progress, private mode-0600 temporary state, cleanup for failures and interrupts, and atomic same-filesystem publication that permits exactly one concurrent winner.
- Returned only local final path, exact byte count, full artifact SHA-256, approved normalized hostname, and a SHA-256 prefix of the URL path without retaining the query or complete URL.

## Task Commits

Each TDD gate and implementation step was committed atomically:

1. **Task 1 RED: failing HTTPS transport regressions** - `f2c53b6` (test)
2. **Task 1 GREEN: trusted HTTPS request boundary** - `0ab1105` (feat)
3. **Task 2 RED: failing stream/finalization regressions** - `92de973` (test)
4. **Task 2 GREEN: exact bounded artifact finalization** - `bd93002` (feat)

## Files Created/Modified

- `vicmap_acquire/download.py` - Defines explicit validated download policy, closed failure types, exact target authorization, manual redirects, bounded streaming, progress, safe provenance, and atomic publication while retaining Plan 01 caller compatibility.
- `tests/test_download.py` - Covers URL/authority policy, clean transport state, redirects, timeouts, status handling, headers, byte ceilings, checksum, progress, cleanup, interruption, temp privacy, no-overwrite, and concurrent finalization.
- `.planning/phases/01-trusted-graph-acquisition/01-04-TASK1-RED.json` - Machine-verified Task 1 fail-first evidence.
- `.planning/phases/01-trusted-graph-acquisition/01-04-TASK2-RED.json` - Machine-verified Task 2 fail-first evidence.

## Decisions Made

- Preserved the existing `read_mailbox.py` integration without expanding Plan 04 scope by translating its legacy keyword call into the new immutable `DownloadPolicy`; new callers use the final-path policy-first interface directly.
- Explicitly pass `verify=True`, `allow_redirects=False`, `stream=True`, identity encoding, and the two-value timeout tuple on every outbound request so security-relevant defaults remain test-visible.
- Detect redirect loops by normalized target identity before contact and close every prior response before resolving the next hop.
- Use Python integer arithmetic for all byte-limit and percent-threshold decisions; conversion to a one-decimal number occurs only after exact tenths are calculated and capped.

## TDD Gate Compliance

- Task 1 RED: `RED_EVIDENCE_OK` for the absent explicit `DownloadPolicy` contract, committed before `0ab1105`.
- Task 2 RED: `RED_EVIDENCE_OK` for the absent exact `format_progress` contract, committed before `bd93002`.
- No refactor commit was needed; the minimal GREEN implementation remained clear.
- Latest focused verification: 28 downloader tests passed with no skips.
- Latest full verification: 70 project tests passed with no skips.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

- One final verification attempt could not access the Nix daemon socket inside the filesystem sandbox; the identical focused and full commands were rerun with approved daemon access and both passed.

## User Setup Required

None - deterministic tests use synthetic responses and transport doubles. The controlled tenant-backed acquisition remains reserved for Plan 01-05.

## Next Phase Readiness

- Plan 01-05 can construct `DownloadPolicy`, pass progress directly into the closed evidence renderer, and render `DownloadResult.approved_hostname` plus `path_fingerprint` without inspecting any source URL.
- No implementation blocker remains for composing the complete acquisition or conducting the controlled live proof.

## Known Stubs

None.

## Self-Check: PASSED

- The downloader, downloader tests, and both RED evidence records exist.
- All four RED/GREEN commits are present in order after the recorded plan base.
- Both RED evidence records report `RED_EVIDENCE_OK`.
- No tracked files were deleted and no skipped tests remain.
- Downloader verification passes 28 tests; the complete project suite passes 70 tests.

---
*Phase: 01-trusted-graph-acquisition*
*Completed: 2026-09-08*
