---
phase: 01-trusted-graph-acquisition
plan: 05
subsystem: acquisition
tags: [python, o365, microsoft-graph, json-lines, redaction, sha256]
requires:
  - phase: 01-02
    provides: Memory-only Graph authentication, exact mailbox confirmation, and bounded complete metadata/MIME access
  - phase: 01-03
    provides: Exact ready-message recognition and deterministic newest-candidate selection
  - phase: 01-04
    provides: Constrained HTTPS streaming, atomic finalization, exact bytes, and SHA-256 provenance
provides:
  - Closed disclosure-safe success, progress, and failure JSON Lines evidence
  - One-call fail-closed orchestration from bounded Graph scan through artifact finalization
  - Controlled live acquisition proof for Order OK0VUZ with independently reproduced artifact integrity
affects: [02-safe-geospatial-discovery, evidence, trusted-graph-acquisition]
actuals:
  tokens: 12735
  tasks: 2
  commits: 9
commits: 9
plan_head_before: d14a8a4f11c084ea57f8a067d1eb503d7aa43513
tech-stack:
  added: []
  patterns: [closed safe event schemas, fixed failure vocabulary, controller-owned boundary translation, redacted correlation recovery]
key-files:
  created:
    - vicmap_acquire/evidence.py
    - tests/test_evidence.py
    - .planning/phases/01-trusted-graph-acquisition/01-LIVE-VERIFICATION.md
  modified:
    - read_mailbox.py
    - vicmap_acquire/graph.py
    - vicmap_acquire/candidates.py
    - tests/test_graph.py
    - tests/test_candidates.py
key-decisions:
  - "Render operator output only from typed project-owned safe events; unexpected exceptions map to one fixed internal failure without interpolation."
  - "Pass exactly one fully selected candidate into one complete DownloadPolicy call and never fall back after the chosen download fails."
  - "Request Graph's from field because O365 2.1.0 hydrates Message.sender from that provider property."
  - "Treat a visible direct archive URL independently from an opaque tracking href while preserving exact-one-link ambiguity rules."
patterns-established:
  - "Closed evidence boundary: renderers accept only exact typed safe-event classes and compact sorted JSON Lines."
  - "Recovery evidence: post-run correlation recovery is explicitly distinguished from the original controlled download and stops before artifact transport."
requirements-completed: [MAIL-01, MAIL-02, MAIL-03, MAIL-04, MAIL-05]
coverage:
  - id: D1
    description: "The configured mailbox is authenticated and scanned read-only through a bounded complete Graph metadata/MIME boundary without disclosing provider content."
    requirement: MAIL-01
    verification:
      - kind: integration
        ref: "tests/test_graph.py#GraphAuthenticationBoundaryTest and GraphMetadataBoundaryTest"
        status: pass
      - kind: manual_procedural
        ref: ".planning/phases/01-trusted-graph-acquisition/01-LIVE-VERIFICATION.md#operator-attestations"
        status: pass
    human_judgment: true
    rationale: "Read-only Mail.Read resource scope is an external tenant setting confirmed by the operator."
  - id: D2
    description: "Exact ready-message policy consumes the complete bounded scan and deterministically selects one newest redacted candidate."
    requirement: MAIL-03
    verification:
      - kind: integration
        ref: "tests/test_candidates.py#CandidateRecognitionTest and CandidateSelectionTest"
        status: pass
      - kind: integration
        ref: "tests/test_evidence.py#ControllerCompositionTest"
        status: pass
    human_judgment: false
  - id: D3
    description: "One selected candidate automatically reaches the bounded downloader exactly once, and a selected failure never falls back to an older candidate."
    requirement: MAIL-04
    verification:
      - kind: integration
        ref: "tests/test_evidence.py#ControllerCompositionTest"
        status: pass
      - kind: integration
        ref: "tests/test_download.py#DownloadTargetPolicyTest, DownloadTransportBoundaryTest, and DownloadStreamingBoundaryTest"
        status: pass
    human_judgment: false
  - id: D4
    description: "The finalized Order OK0VUZ artifact has exact independently reproduced bytes and SHA-256 linked to redacted message and target provenance."
    requirement: MAIL-05
    verification:
      - kind: manual_procedural
        ref: ".planning/phases/01-trusted-graph-acquisition/01-LIVE-VERIFICATION.md#final-artifact"
        status: pass
      - kind: unit
        ref: "tests/test_evidence.py#EvidenceContractTest"
        status: pass
    human_judgment: true
    rationale: "The controlled artifact and tenant-backed acquisition are external operational evidence, recorded and reviewed with strict redaction."
duration: 21h 15m elapsed
completed: 2026-09-09
status: complete
---

# Phase 1 Plan 5: Closed Evidence and Controlled Acquisition Summary

**Closed JSON Lines evidence and fail-closed orchestration acquired one authentic Order OK0VUZ archive with independently reproduced 233089097-byte SHA-256 provenance.**

## Performance

- **Duration:** 21 hours 15 minutes elapsed, including a quota pause between successful acquisition and documentation closeout
- **Started:** 2026-09-08T04:22:40Z
- **Completed:** 2026-09-09T01:37:41Z
- **Tasks:** 2
- **Files modified:** 11
- **Deterministic verification:** 81 tests passed in 0.098 seconds with no skips

## Accomplishments

- Added a closed success/progress/failure vocabulary with deterministic masking, fingerprints, fixed remediation hints, exact progress arithmetic, and strict JSON Lines rendering that cannot accept raw exception or provider text.
- Composed validation, Graph authentication/mailbox access, complete scan and selective MIME retrieval, deterministic selection, exactly one bounded download, and final safe evidence behind an injectable controller.
- Proved the live `Order_OK0VUZ.zip` artifact at 233089097 bytes with SHA-256 `6a7868094ccab5b01fed11aec34587bd7e92bacdc35935b3c2835df21665411b`; two independent local calculations matched the successful controlled-run report.
- Recovered only the permitted redacted message and target correlation fields in one explicitly approved read-only mailbox pass that stopped before artifact transport.

## Task Commits

Each TDD gate, implementation step, live-fix deviation, and controlled evidence result was committed atomically:

1. **Task 1 RED: failing closed evidence regressions** - `2f37422` (test)
2. **Task 1 GREEN: closed acquisition evidence renderer** - `ce62013` (feat)
3. **Task 2 RED: failing controller composition regressions** - `e9e993a` (test)
4. **Task 2 GREEN: final bounded acquisition composition** - `7676ad2` (feat)
5. **Task 2 deviation RED: O365 sender hydration regression** - `8a59f9a` (test)
6. **Task 2 deviation GREEN: Graph sender hydration fix** - `b5b5123` (fix)
7. **Task 2 deviation RED: visible direct archive-link regression** - `45f8333` (test)
8. **Task 2 deviation GREEN: visible direct archive-link parser fix** - `d570a7d` (fix)
9. **Task 2 evidence: controlled live acquisition record** - `3e64e72` (docs)

## Files Created/Modified

- `vicmap_acquire/evidence.py` - Defines the closed stage/reason vocabulary, safe typed events, masking/fingerprinting, exact progress conversion, and compact JSON Lines renderers.
- `tests/test_evidence.py` - Covers all reason/stage mappings, strict schemas, seeded disclosure rejection, exact progress, one-call orchestration, no candidate, no fallback, and unexpected failures.
- `read_mailbox.py` - Composes the complete acquisition order, complete downloader policy, safe event conversion, and non-zero failure exits.
- `vicmap_acquire/graph.py` - Selects Graph's `from` property so O365 2.1.0 hydrates the project-owned sender field.
- `vicmap_acquire/candidates.py` - Recognizes a direct archive URL displayed as HTML anchor text while retaining opaque wrapper rejection and exact ambiguity rules.
- `tests/test_graph.py` - Locks the O365-compatible four-field metadata query.
- `tests/test_candidates.py` - Locks visible-direct-link acceptance without trusting wrapper hrefs.
- `.planning/phases/01-trusted-graph-acquisition/01-05-TASK1-RED.json` - Machine-readable Task 1 fail-first evidence.
- `.planning/phases/01-trusted-graph-acquisition/01-05-TASK2-RED.json` - Machine-readable Task 2 fail-first evidence.
- `.planning/phases/01-trusted-graph-acquisition/01-05-TASK2-SENDER-RED.json` - Machine-readable sender-hydration fail-first evidence.
- `.planning/phases/01-trusted-graph-acquisition/01-LIVE-VERIFICATION.md` - Redacted controlled-run, integrity, runtime-state, and operator-attestation evidence.

## Decisions Made

- Render only exact typed project-owned events. Provider exceptions and unknown objects cannot cross the operator-output boundary; unexpected failures become the fixed `internal_failure` event.
- Construct and pass the complete configured `DownloadPolicy` only after the newest valid candidate is selected, then stop after any selected-candidate failure instead of attempting older mail.
- Use Graph's `from` property in the minimal provider query because O365 2.1.0 maps it to `Message.sender`; the scan remains four-field and metadata-first.
- Parse visible HTML text as a separate direct-URL source. An opaque Safe Links href is never unwrapped or trusted, and messages with zero or multiple direct archive occurrences remain ambiguous.
- Preserve the live record's provenance boundary: automated local checks and the user-approved redacted recovery scan are distinguished from operator attestations about tenant scope and legacy-token handling.

## TDD Gate Compliance

- Task 1 RED was committed in `2f37422` with `RED_EVIDENCE_OK` evidence before GREEN commit `ce62013`.
- Task 2 RED was committed in `e9e993a` with `RED_EVIDENCE_OK` evidence before GREEN commit `7676ad2`.
- The live O365 sender mismatch received a focused failing regression in `8a59f9a` and machine-readable RED evidence before fix `b5b5123`.
- The visible direct-link mismatch received a focused failing regression in `45f8333` before fix `d570a7d`.
- No refactor-only commit was needed; the GREEN changes remained focused.
- Latest full verification passes 81 tests with no skips.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Hydrated sender from the O365 2.1.0 Graph field**

- **Found during:** Task 2 controlled live acquisition
- **Issue:** Selecting Graph's `sender` property left `O365.Message.sender` empty in the live scan because O365 2.1.0 hydrates it from Graph's `from` property.
- **Fix:** Kept the four-field metadata boundary but selected `from`, with a focused regression proving sender hydration.
- **Files modified:** `vicmap_acquire/graph.py`, `tests/test_graph.py`, `.planning/phases/01-trusted-graph-acquisition/01-05-TASK2-SENDER-RED.json`
- **Verification:** Full Graph boundary tests and complete 81-test suite pass.
- **Committed in:** `8a59f9a`, `b5b5123`

**2. [Rule 1 - Bug] Recognized the visible direct archive URL without trusting its wrapper**

- **Found during:** Task 2 controlled live acquisition
- **Issue:** The ready notification placed an opaque Safe Links wrapper in the anchor href and displayed the approved direct archive URL as anchor text; href-only parsing rejected the otherwise valid message.
- **Fix:** Extracted visible text URLs as an independent source, retained the exact archive filename/order policy, and left wrapper-only or ambiguous messages rejected.
- **Files modified:** `vicmap_acquire/candidates.py`, `tests/test_candidates.py`
- **Verification:** Focused visible-link regression and complete 81-test suite pass.
- **Committed in:** `45f8333`, `d570a7d`

**3. [Rule 3 - Blocking] Recovered redacted correlation fields after documentation interruption**

- **Found during:** Task 2 closeout
- **Issue:** The original controlled run and independent artifact verification succeeded, but its safe message/target correlation fields were not retained before the previous executor hit quota.
- **Fix:** With explicit operator approval, ran exactly one bounded read-only Graph recovery scan through production recognition/selection and local URL validation, emitting only allowlisted redacted fields and stopping before artifact transport.
- **Files modified:** `.planning/phases/01-trusted-graph-acquisition/01-LIVE-VERIFICATION.md`
- **Verification:** The recovered order and approved host align with configuration and the existing artifact; the live-record schema check rejects prohibited raw categories.
- **Committed in:** `3e64e72`

---

**Total deviations:** 3 auto-fixed (2 Rule 1 bugs, 1 Rule 3 closeout blocker).
**Impact on plan:** Both live-shape fixes were required for correct candidate recognition without broadening trust. The approved recovery was read-only and stopped before the artifact host, preserving the existing artifact and disclosure boundary.

## Issues Encountered

- The prior executor hit its quota after the controlled acquisition and independent checksum comparison succeeded but before documentation was written. Closeout resumed from committed code and the existing artifact without repeating the download.
- One Nix verification invocation could not access the daemon socket inside the filesystem sandbox; the identical command passed with approved daemon access.

## Authentication Gates

None during closeout. The controlled run used the existing configured Graph credentials without printing or persisting them.

## User Setup Required

None remaining. The operator attested that the Microsoft application is limited to read-only `Mail.Read` for `automations@vegetationlink.com.au` and that the legacy checkout token was revoked and quarantined or removed under operator control.

## Known Stubs

None.

## Next Phase Readiness

- Phase 1 now provides one immutable, integrity-checked `Order_OK0VUZ.zip` for isolated geospatial discovery in Phase 2.
- Downstream evidence can link the artifact through exact bytes/SHA-256 and the safe order, message, and target correlation fields in `01-LIVE-VERIFICATION.md`.
- No Phase 1 blocker or open stub remains.

## Self-Check: PASSED

- All 11 created or modified plan paths and the final artifact exist.
- All nine pre-summary plan commits exist after recorded base `d14a8a4f11c084ea57f8a067d1eb503d7aa43513`.
- The measured pre-summary commit count is 9 and matches frontmatter.
- The final artifact is the sole configured archive, has no partial companion, and reproduces 233089097 bytes plus SHA-256 `6a7868094ccab5b01fed11aec34587bd7e92bacdc35935b3c2835df21665411b`.
- Summary coverage metadata parses successfully; stub, skipped-test, whitespace, and disclosure checks pass.
- The complete deterministic suite passes 81 tests with no skips.

---
*Phase: 01-trusted-graph-acquisition*
*Completed: 2026-09-09*
