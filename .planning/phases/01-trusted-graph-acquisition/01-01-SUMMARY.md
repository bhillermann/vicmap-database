---
phase: 01-trusted-graph-acquisition
plan: 01
subsystem: acquisition
tags: [python, o365, microsoft-graph, requests, toml, sha256]
requires: []
provides:
  - Guarded Graph-to-artifact acquisition tracer with injectable external boundaries
  - Exact sender, order, subject, MIME-link, hostname, and deterministic-selection policy
  - Bounded clean-session HTTPS streaming with private temporary files and atomic publication
  - Closed reviewable TOML configuration and credential/runtime ignore policy
affects: [01-02, 01-03, 01-04, 01-05, trusted-graph-acquisition]
actuals:
  tokens: 12233
  tasks: 2
  commits: 4
commits: 4
plan_head_before: 4a43c147e2d48b93cf52b7a27945be0495cae295
tech-stack:
  added: []
  patterns: [injectable I/O seams, closed failure codes, validate-before-send, memory-only OAuth]
key-files:
  created:
    - read_mailbox.py
    - vicmap.toml
    - vicmap_acquire/graph.py
    - vicmap_acquire/candidates.py
    - vicmap_acquire/download.py
    - tests/test_graph.py
  modified: []
key-decisions:
  - "Keep Graph and artifact HTTP authority in separate adapters; artifact sessions clear auth, cookies, and ambient netrc behavior."
  - "Represent every operator-visible failure with a closed reason code and expose message/URL identities only through bounded fingerprints."
  - "Reject any TOML key or policy value outside the complete Phase 1 schema before credentials or network adapters are used."
patterns-established:
  - "Boundary injection: run_acquisition accepts Graph, Requests-session, and event-sink factories for production-shaped tests without live services."
  - "Private publication: downloads stream into a mode-0600 temporary file and become final through atomic no-overwrite linking only after hashing succeeds."
requirements-completed: [MAIL-01, MAIL-02, MAIL-03, MAIL-04, MAIL-05]
coverage:
  - id: D1
    description: "One configured Graph message is recognized, selected, streamed, checksummed, and atomically finalized with redacted evidence."
    requirement: MAIL-01
    verification:
      - kind: e2e
        ref: "tests/test_graph.py#PipelineTracerTest.test_pipeline_streams_one_candidate_and_emits_only_redacted_evidence"
        status: pass
    human_judgment: false
  - id: D2
    description: "An unsafe newest artifact target fails closed before transport and never falls back to an older candidate."
    requirement: MAIL-04
    verification:
      - kind: integration
        ref: "tests/test_graph.py#PipelineTracerTest.test_rejected_newest_target_is_closed_and_never_falls_back"
        status: pass
    human_judgment: false
  - id: D3
    description: "The complete non-secret policy is validated before credentials, Graph, HTTP, or output creation."
    requirement: MAIL-01
    verification:
      - kind: unit
        ref: "tests/test_graph.py#ConfigurationTest"
        status: pass
    human_judgment: false
duration: 25min
completed: 2026-09-08
status: complete
---

# Phase 1 Plan 1: Trusted Acquisition Tracer Summary

**A production-shaped, redaction-safe Graph mailbox tracer now selects one trusted Vicmap message and atomically publishes its bounded SHA-256-verified artifact.**

## Performance

- **Duration:** 25 minutes
- **Started:** 2026-09-08T01:31:25Z
- **Completed:** 2026-09-08T01:56:02Z
- **Tasks:** 2
- **Files modified:** 11

## Accomplishments

- Split Microsoft Graph metadata/MIME access, pure candidate policy, and artifact HTTPS into separate project-owned trust boundaries.
- Proved one end-to-end fake-backed acquisition through real parsing, selection, streaming, hashing, private temporary storage, and no-overwrite publication.
- Added exact locked allowlists and operational defaults in `vicmap.toml`, with closed-schema validation before any credential or adapter use.
- Removed import-time authentication and checkout token persistence from the production path while ensuring evidence excludes seeded secrets and raw source content.

## Task Commits

Each TDD gate and implementation step was committed atomically:

1. **Task 1 RED: failing production tracer** - `d31da90` (test)
2. **Task 1 GREEN: trusted acquisition path** - `a0e7a8d` (feat)
3. **Task 2 RED: failing policy boundary tests** - `9eaf026` (test)
4. **Task 2 GREEN: reviewable startup policy** - `05c0301` (feat)

## Files Created/Modified

- `.gitignore` - Excludes OAuth tokens, local environment state, caches, private partial downloads, and finalized artifacts without hiding policy or tests.
- `vicmap.toml` - Stores the exact initial mailbox, sender, order, host, transfer, timeout, redirect, and fingerprint policy.
- `read_mailbox.py` - Defines immutable configuration, closed orchestration failures, safe evidence, TOML loading, and a guarded CLI.
- `vicmap_acquire/graph.py` - Authenticates through `MemoryTokenBackend`, performs read-only metadata scans, and selectively retrieves MIME.
- `vicmap_acquire/candidates.py` - Applies exact header/MIME/order checks and complete deterministic ordering.
- `vicmap_acquire/download.py` - Validates every HTTPS target, isolates HTTP authority, bounds the stream, hashes exact bytes, and atomically finalizes.
- `tests/test_graph.py` - Covers the end-to-end tracer, no-fallback failure, configuration rejection, credential ordering, and import safety.
- `.planning/phases/01-trusted-graph-acquisition/01-01-TASK1-RED.json` - Machine-verified fail-first evidence for the tracer.
- `.planning/phases/01-trusted-graph-acquisition/01-01-TASK2-RED.json` - Machine-verified fail-first evidence for configuration policy.

## Decisions Made

- Construct O365 only inside `GraphMailbox`, using `MemoryTokenBackend` and the installed 2.1 `requested_scopes` API.
- Keep the artifact Requests session unauthenticated and disable ambient credential discovery before its first request.
- Use SHA-256 prefixes of configurable length for message and URL-path correlation, while retaining the full digest only for artifact bytes.
- Resolve output directories relative to the policy file and reject traversal, symlink escape, non-directory targets, unknown keys, and unsafe scalar types before authentication.

## TDD Gate Compliance

- Task 1 RED: `RED_EVIDENCE_OK` for the missing callable acquisition tracer, committed before `a0e7a8d`.
- Task 2 RED: `RED_EVIDENCE_OK` for the exact valid policy failing to load, committed before `05c0301`.
- Latest full verification: 7 tests passed with `python -m unittest discover`; no tests were skipped.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - this plan uses injected fakes for automated acceptance. The controlled tenant-backed acquisition remains deliberately scheduled for Plan 01-05.

## Next Phase Readiness

- Stable `AcquisitionConfig`, `MessageMetadata`, `Candidate`, `DownloadResult`, and `run_acquisition` seams are ready for Plans 01-02 through 01-04 to harden independently.
- No implementation blocker remains for Plan 01-02.

## Self-Check: PASSED

- All created artifacts exist.
- All four RED/GREEN task commits are present.
- Coverage metadata classifies all three deliverables as fully automated and passing.

---
*Phase: 01-trusted-graph-acquisition*
*Completed: 2026-09-08*
