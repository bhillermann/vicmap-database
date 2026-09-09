---
phase: 01-trusted-graph-acquisition
verified: 2026-09-09T02:24:34Z
status: gaps_found
score: 15/21 must-haves verified
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
  - .planning/phases/01-trusted-graph-acquisition/01-CONTEXT.md
  - .planning/phases/01-trusted-graph-acquisition/01-LIVE-VERIFICATION.md
  - .planning/phases/01-trusted-graph-acquisition/01-VALIDATION.md
  - .planning/phases/01-trusted-graph-acquisition/01-SECURITY.md
  - .planning/phases/01-trusted-graph-acquisition/01-REVIEW.md
  - read_mailbox.py
  - tests/__init__.py
  - tests/test_candidates.py
  - tests/test_download.py
  - tests/test_evidence.py
  - tests/test_graph.py
  - vicmap.toml
  - vicmap_acquire/__init__.py
  - vicmap_acquire/candidates.py
  - vicmap_acquire/download.py
  - vicmap_acquire/evidence.py
  - vicmap_acquire/graph.py
covered_digest: "v1:sha256:303a18b8f8bbb6a18c9da7fde279a2b879bc5cf31d553661ad4d3f04b3d9cab1"
behavior_unverified: 0
overrides_applied: 0
gaps:
  - truth: "The operator obtains an authentic Vicmap artifact rather than an attacker-controlled object that merely matches message text and the shared regional host."
    status: failed
    reason: "The trust chain accepts the provider From field, exact subject/filename text, and any path on a shared S3 regional hostname. No authenticated sender result, signature, trusted bucket/path constraint, or independently trusted expected digest binds the bytes to Vicmap. The retained live record is a composite of a prior executor report and a later mailbox-only recovery scan, not direct retained evidence of one connected authenticated transaction."
    artifacts:
      - path: vicmap_acquire/graph.py
        issue: "Lines 169-195 trust the provider From value as sender metadata without an authenticated-origin signal."
      - path: vicmap_acquire/download.py
        issue: "Lines 165-180 authorize the exact hostname but place no constraint on bucket/path ownership."
      - path: vicmap.toml
        issue: "Line 10 allowlists a shared regional authority only."
      - path: .planning/phases/01-trusted-graph-acquisition/01-LIVE-VERIFICATION.md
        issue: "The original correlation output was not retained; the recovery scan stopped before artifact transport."
    missing:
      - "Require an authoritative origin signal, such as a verified vendor signature or independently trusted expected digest."
      - "Constrain the initial target and every redirect to the expected bucket/path authority in addition to the hostname."
      - "Add an end-to-end rejection test for a matching message that points to a different bucket/path on the allowed host."
      - "Record a new controlled proof that directly links the authenticated message, authorized target, and finalized digest without retaining sensitive source data."
  - truth: "All accepted policy values are completely validated before authentication and remain compatible through final evidence rendering."
    status: failed
    reason: "The controller validator accepts malformed direct AcquisitionConfig values and permits fingerprint lengths 8-64, while the evidence schema accepts exactly 16. A valid non-default length can publish the artifact and only then become internal_failure."
    artifacts:
      - path: read_mailbox.py
        issue: "Lines 151-164 omit folder equality, allowlist element/syntax validation, output-root validation, and evidence compatibility; line 162 accepts 8-64 fingerprint characters."
      - path: vicmap_acquire/evidence.py
        issue: "Lines 158-161 require exactly 16 fingerprint characters."
      - path: tests/test_graph.py
        issue: "Loader tests do not exercise malformed direct AcquisitionConfig instances or compatible non-default fingerprint values."
    missing:
      - "Centralize one complete policy validator used by both load_config and run_acquisition."
      - "Make fingerprint length one shared contract: either fixed at 16 before I/O or consistently configurable end to end."
      - "Add direct-config tests and minimum/default/maximum fingerprint regressions that assert failure occurs before adapters or filesystem work."
  - truth: "A handled finalization failure cannot leave a published final artifact or private partial state while reporting failure."
    status: failed
    reason: "After os.link publishes the final path, failure of temp_path.unlink is translated to artifact_write_failed even though the final artifact exists. A deterministic injected-cleanup repro left both the final path and one private partial while reporting failure."
    artifacts:
      - path: vicmap_acquire/download.py
        issue: "Lines 442-466 keep post-publication temp cleanup inside the pre-commit failure path and silently ignore the second cleanup failure."
      - path: tests/test_download.py
        issue: "No test injects unlink failure after successful publication."
    missing:
      - "Define an explicit publication commit point and separate post-commit cleanup from the transfer failure result."
      - "Add an injected post-link unlink-failure regression asserting the reported result agrees with final-path state and no retry ambiguity remains."
  - truth: "Only a genuinely displayed or linked archive occurrence can make an exact header-qualified message a candidate."
    status: failed
    reason: "The HTML collector extracts URL-shaped text from every data node, including script/style content. A synthetic script-only archive URL was accepted as a candidate, so the configured marker and archive-link rule is broader than the visible-link policy."
    artifacts:
      - path: vicmap_acquire/candidates.py
        issue: "Lines 79-93 and 130-133 collect all HTML data text without tracking non-rendered element context."
      - path: tests/test_candidates.py
        issue: "No negative cases cover script, style, metadata, or malformed nested markup."
    missing:
      - "Ignore non-rendered/raw-text HTML elements or restrict extraction to the explicitly intended rendered/anchor contexts."
      - "Add negative script/style/metadata and malformed-nesting regressions."
  - truth: "Every controller/CLI failure is converted once to the closed machine-readable failure vocabulary without a raw exception escaping."
    status: failed
    reason: "_emit_failure calls the same event sink without protection. When that sink fails, the second exception escapes the except block as a raw RuntimeError instead of AcquisitionFailure; the CLI can therefore emit a traceback rather than the promised closed event."
    artifacts:
      - path: read_mailbox.py
        issue: "Lines 110-113 and 238-248 invoke the failure sink unguarded, including after the sink itself may have failed."
      - path: tests/test_evidence.py
        issue: "No tests use a sink that fails during candidate, progress, success, or failure emission."
    missing:
      - "Guard evidence delivery, emit at most once, and never retry a sink that just failed."
      - "Guarantee a fixed AcquisitionFailure/non-zero CLI result without interpolating sink exception text."
      - "Add failing-sink regressions for each event stage."
  - truth: "The three bespoke must-NOT constraints have an authoritative verification disposition."
    status: partial
    reason: "PROHIB-01 through PROHIB-03 remain status unresolved with verification null in every plan declaration. Source and tests suggest the intended controls, but the prohibition contract explicitly forbids silently treating descriptor-less LLM judgment as authoritative."
    artifacts:
      - path: .planning/phases/01-trusted-graph-acquisition/01-05-PLAN.md
        issue: "Lines 75-95 retain all three prohibitions as unresolved with no verification tier."
      - path: tests/test_graph.py
        issue: "The mailbox-mutation check is source-text inspection, not an authoritative runtime enforcement descriptor."
      - path: tests/test_download.py
        issue: "Clean-session and incomplete-publication tests cover important cases but do not resolve the declared prohibition metadata."
    missing:
      - "Assign each prohibition a supported verification tier and wire its enforcement evidence, or obtain explicit human acceptance for judgment-tier items."
---

# Phase 1: Trusted Graph Acquisition Verification Report

**Phase Goal:** The operator can obtain exactly one authentic Vicmap order artifact from the automation mailbox without leaking sensitive content or trusting an unsafe download path.

**Verified:** 2026-09-09T02:24:34Z

**Status:** gaps_found

**Re-verification:** No — initial verification

## Goal Achievement

The implementation is substantive and its deterministic happy paths are well tested, but the phase goal is not achieved. Most importantly, the code does not establish artifact authenticity: matching untrusted message fields and an object name on a shared regional host is not an authenticated chain of provenance. Four additional reproducible state/policy failures contradict plan-level must-haves.

### Observable Truths

The phase-level end-to-end truth from Plan 01 was deduplicated against the roadmap goal. More detailed plan truths remain because they add independently testable constraints.

| # | Source | Truth | Status | Evidence |
|---|---|---|---|---|
| 1 | Roadmap SC1 | Authenticate, confirm the configured mailbox, and inspect a bounded Inbox result without credential/body output | ✓ VERIFIED | `GraphMailbox` uses memory-only auth and exact resource selection; metadata paging and disclosure tests passed. Existing external tenant-scope evidence is an operator attestation. |
| 2 | Roadmap SC2 | Configured markers identify candidates and exactly one is selected with redacted identity | ✗ FAILED | Selection and redaction work, but script-only HTML URL text is accepted as a candidate. |
| 3 | Roadmap SC3 | The selected message yields one artifact through the approved HTTPS host with redirect, timeout, and size limits | ✓ VERIFIED | Exact-host preflight, manual redirect, independent timeout, and inclusive byte-limit tests passed. Authentic ownership of that approved-host path is a separate failed goal truth. |
| 4 | Roadmap SC4 | Completed download reports exact byte count and checksum | ✓ VERIFIED | Stream/hash and evidence value assertions passed; the default controlled record includes independently reproduced values. Non-default fingerprint policy remains a separate failure. |
| 5 | Plan 01 | Importing the CLI/package causes no auth, network, directory, or artifact side effect | ✓ VERIFIED | `test_import_constructs_no_clients_and_creates_no_output` passed. |
| 6 | Plan 01 | Policy is fully validated pre-auth; credentials remain environment-only; tokens remain memory-only | ✗ FAILED | Credential/token handling is correct, but direct config validation is incomplete and fingerprint compatibility fails after publication. |
| 7 | Plan 01 | Tracer output contains only redacted identity/download evidence | ✓ VERIFIED | Pipeline and disclosure tests use value-level negative assertions; no raw source values are renderer inputs. |
| 8 | Plan 02 | App-only memory auth confirms exact mailbox without body/raw-provider output | ✓ VERIFIED | Account constructor, scope, mailbox resource, and closed-exception assertions passed. |
| 9 | Plan 02 | One inclusive cutoff and four-field metadata query exhaust all pages without a count cap | ✓ VERIFIED | `receivedDateTime` query, selected fields, `limit=None`, `batch=999`, and later-page values are asserted. |
| 10 | Plan 02 | Only header-qualified messages trigger MIME retrieval and scanning remains read-only | ✓ VERIFIED | Controller lazily calls MIME after header qualification and no mutation API exists. The production MIME path makes one extra ordinary-message GET; see warning W-01. |
| 11 | Plan 03 | Only exact sender/order/subject/MIME/link-cardinality matches become candidates | ✗ FAILED | Non-rendered script data is treated as a visible archive occurrence. |
| 12 | Plan 03 | Complete-scan selection deterministically chooses one newest candidate and displays only a fingerprint | ✓ VERIFIED | Active behavioral tests cover shuffled input, UTC ordering, full-ID tie-breaks, and closed redaction. |
| 13 | Plan 03 | Empty/ambiguous/malformed/mismatched candidates fail closed | ✓ VERIFIED | Value-level tests cover each error family and passed. |
| 14 | Plan 04 | Every initial/redirect target is exact-host HTTPS and validated before request | ✓ VERIFIED | Target/redirect contact assertions passed. |
| 15 | Plan 04 | Connect/read timeouts remain independent with no total-transfer deadline | ✓ VERIFIED | Request call arguments and both timeout error paths are asserted. |
| 16 | Plan 04 | Exact inclusive ceiling, persisted-byte count/hash, and atomic no-overwrite publication | ✓ VERIFIED | Boundary, checksum, existing-destination, and concurrent-winner tests passed. |
| 17 | Plan 04 | Every handled failure removes private partial state and returns one coherent closed result | ✗ FAILED | Post-link unlink failure reports failure while final and partial names both exist. |
| 18 | Plan 05 | CLI renders only one closed machine-readable success/progress/failure vocabulary | ✗ FAILED | A failed event sink escapes as raw `RuntimeError`; no closed result is guaranteed. |
| 19 | Plan 05 | Exactly one selected candidate enters the downloader and no fallback occurs | ✓ VERIFIED | Controller behavioral tests assert one call and newest-candidate failure stops. |
| 20 | Plan 05 | A controlled live run proves one redacted authentic message-to-artifact transaction | ✗ FAILED | The live record relies on prior executor narration for download and a later recovery scan that stopped before transport; code also lacks an authoritative artifact-origin signal. |
| 21 | Plan 05 | Live record safely records scope/runtime/disclosure attestations without prohibited source values | ✓ VERIFIED | The record is redacted and distinguishes automated facts from operator attestations. No runtime credentials, raw mailbox data, full provider IDs/URLs, or artifact contents were accessed during this verification. |

**Score:** 15/21 truths verified (0 present-but-behavior-unverified)

## Required Artifacts

| Artifact | Expected | Status | Details |
|---|---|---|---|
| `read_mailbox.py` | Guarded configuration, orchestration, and CLI | ✗ PARTIAL | Substantive and wired; incomplete direct-config validation, incompatible fingerprint contract, and unguarded failure sink. |
| `vicmap_acquire/graph.py` | Memory-only Graph mailbox boundary | ⚠ PARTIAL | Substantive and wired; authentication/pagination work, but MIME-by-ID performs an extra ordinary-message fetch first. |
| `vicmap_acquire/candidates.py` | Pure recognition and deterministic selection | ✗ PARTIAL | Substantive and wired; non-rendered HTML data can supply the accepted archive URL. |
| `vicmap_acquire/download.py` | Constrained stream/hash/finalization boundary | ✗ PARTIAL | Substantive and wired; authenticity authority and post-commit cleanup semantics are incomplete. |
| `vicmap_acquire/evidence.py` | Closed safe event schema/renderers | ⚠ PARTIAL | Substantive and wired; fixed 16-character target fingerprint conflicts with accepted config values. |
| `vicmap.toml` | Reviewable non-secret policy | ⚠ PARTIAL | Wired through `load_config`; exact host is configured, but the shared host does not authenticate bucket/path ownership. |
| `.gitignore` | Runtime/token/artifact exclusions | ⚠ PARTIAL | Default `/artifacts/` is ignored; supported nested/renamed output directories are not. |
| `tests/test_graph.py` | Graph and tracer regressions | ✓ VERIFIED | Active, discovered, behavioral/value assertions; misses production-shaped MIME connection count. |
| `tests/test_candidates.py` | Recognition/selection regressions | ✓ VERIFIED | Active and discovered; missing non-rendered HTML negatives. |
| `tests/test_download.py` | Transport/stream/finalization regressions | ✓ VERIFIED | Active and discovered; missing post-link cleanup failure. |
| `tests/test_evidence.py` | Evidence/controller regressions | ✓ VERIFIED | Active and discovered; missing failing-sink cases and non-default fingerprint integration. |
| `vicmap_acquire/__init__.py`, `tests/__init__.py` | Side-effect-free package/test boundaries | ✓ VERIFIED | Minimal by design; imports are inert. |
| `01-LIVE-VERIFICATION.md` | Safe live proof | ✗ PARTIAL | Safe record exists, but direct message-to-transport correlation from the original run was not retained. |

## Key Link Verification

| From | To | Via | Status | Details |
|---|---|---|---|---|
| `read_mailbox.py` | `graph.py` | Validated config constructs Graph adapter | ⚠ PARTIAL | Construction is wired at lines 176-185, but direct `AcquisitionConfig` validation is incomplete. |
| `read_mailbox.py` | `candidates.py` | Metadata plus lazy MIME feed recognition and selection | ✗ PARTIAL | Wired at lines 185-197; candidate HTML extraction is over-broad. |
| `read_mailbox.py` | `download.py` | One selected candidate feeds one downloader call | ✓ WIRED | Lines 207-224; one-call/no-fallback test passed. |
| `graph.py` | O365/Inbox | Memory backend, exact resource, minimal query, pagination | ⚠ PARTIAL | Auth/query are correct; `Folder.get_message` performs an undocumented ordinary representation GET before MIME `$value`. |
| `validate_https_target` | Requests send | Validate initial and redirect target before `session.get` | ✓ WIRED | Validation precedes every send and rejected-hop tests assert no contact. |
| `iter_content` | `DownloadResult` | Persist/count/hash then no-overwrite publish | ⚠ PARTIAL | Happy path is wired; post-commit cleanup can reverse the reported result. |
| `DownloadResult` | success renderer | Host/path fingerprint, bytes, SHA-256 events | ✗ PARTIAL | Wired at `read_mailbox.py` lines 225-235; accepted non-16 fingerprint lengths fail at the event boundary. |

## Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|---|---|---|---|---|
| `read_mailbox.py` | `metadata` | Real O365 Inbox iterator | Yes | ✓ FLOWING |
| `candidates.py` | `Candidate` | Graph metadata plus selected MIME | Yes, but origin is not authenticated | ✗ FLOWING / UNTRUSTED |
| `download.py` | artifact stream | Real clean Requests session | Yes, but shared-host path ownership is not constrained | ✗ FLOWING / UNTRUSTED |
| `evidence.py` | candidate/target/final events | Selected candidate and `DownloadResult` | Yes on default path | ⚠ PARTIAL — non-default accepted fingerprint lengths disconnect after publication |
| `01-LIVE-VERIFICATION.md` | live provenance chain | Prior download report plus later pre-transport recovery | Two real observations, not one retained connected flow | ✗ DISCONNECTED PROVENANCE |

## Behavioral Spot-Checks

All commands used only synthetic values/fakes. No live mailbox, credentials, complete provider identifiers/URLs, or artifact contents were accessed.

| Behavior | Command | Result | Status |
|---|---|---|---|
| Full deterministic suite | `nix develop path:. -c python -m unittest discover -s tests -p 'test_*.py' -v` | 81 tests, 0 failures, 0 skips | ✓ PASS |
| Shared-host authenticity boundary | `python -c` synthetic `validate_https_target` repro | Different bucket/path on configured shared host accepted | ✗ FAIL |
| Fingerprint contract | `python -c` synthetic policy/evidence repro | Policy accepted length 8; evidence rejected it | ✗ FAIL |
| Hidden HTML URL | `python -c` synthetic MIME recognition repro | Script-only URL became a candidate | ✗ FAIL |
| Direct config preflight | `python -c` synthetic `run_acquisition` repro | Malformed config reached graph factory and became `internal_failure` | ✗ FAIL |
| Evidence sink failure | `python -c` synthetic empty-scan/failing-sink repro | Raw `RuntimeError` escaped with no closed code | ✗ FAIL |
| Post-publication cleanup | `python -c` fake transport + injected unlink failure | Reported `artifact_write_failed`; final exists; one partial remains | ✗ FAIL |

## Probe Execution

No executable `probe-*.sh` was declared or found. The plans' references to a “specless prohibition probe” are planning provenance, not runnable phase probes.

## Requirements Coverage

| Requirement | Source Plans | Description | Status | Evidence |
|---|---|---|---|---|
| MAIL-01 | 01-01, 01-02, 01-05 | Authenticate/confirm configured mailbox without credential/body disclosure | ✓ SATISFIED | Memory backend, exact mailbox, closed Graph failures, and active disclosure tests. Tenant resource scope remains operator-attested. |
| MAIL-02 | 01-01, 01-02, 01-03, 01-05 | Bounded Inbox scan and configured candidate recognition | ✗ BLOCKED | Time/page bounds work, but script-only HTML text can fabricate the accepted archive marker; the production MIME path also makes an extra ordinary-message GET. |
| MAIL-03 | 01-01, 01-03, 01-05 | Deterministically select exactly one and show redacted identity | ✓ SATISFIED | Complete-stream, tie-break, shuffle, ambiguity, and event-schema assertions pass. |
| MAIL-04 | 01-01, 01-04, 01-05 | Download one artifact only through approved bounded HTTPS | ✗ BLOCKED | Request/redirect/time/size mechanics work, but the shared hostname does not authenticate the object authority and post-commit failure state is incoherent. |
| MAIL-05 | 01-01, 01-04, 01-05 | Show exact artifact byte count and checksum | ✗ BLOCKED | Happy/default path works; accepted non-16 fingerprint settings can publish then fail before final byte/checksum evidence is emitted. |

No Phase 1 requirement is orphaned: MAIL-01 through MAIL-05 appear in plan frontmatter and REQUIREMENTS.md. No later milestone phase clearly owns these failed Phase 1 trust/config/transaction semantics, so none is deferred.

## Prohibition Gate

| Prohibition | Automated evidence | Disposition |
|---|---|---|
| PROHIB-01 — no mailbox mutation | Adapter exposes read calls only; source-text regression passes | ⚠ `unverified-prohibition` — descriptor remains null/unresolved; explicit human/tier resolution required |
| PROHIB-02 — no Graph/ambient authority at artifact host | Fake session proves auth/cookies cleared and `trust_env=False` | ⚠ `unverified-prohibition` — descriptor remains null/unresolved; explicit human/tier resolution required |
| PROHIB-03 — no incomplete/failed/over-limit final publication | Size/failure tests pass, but post-link unlink repro contradicts coherent failure state | ✗ UNVERIFIED and implicated in blocker F-03 |

## Test Quality Audit

| Test File | Linked Reqs | Active | Skipped | Circular | Assertion Level | Verdict |
|---|---|---:|---:|---:|---|---|
| `tests/test_graph.py` | MAIL-01, MAIL-02 | 18 | 0 | 0 | Behavioral/value | ⚠ Production O365 MIME path is not modeled at connection-request level |
| `tests/test_candidates.py` | MAIL-02, MAIL-03 | 25 | 0 | 0 | Behavioral/value | ⚠ Missing non-rendered HTML negative cases |
| `tests/test_download.py` | MAIL-04, MAIL-05 | 28 | 0 | 0 | Behavioral/value | ⚠ Missing post-commit cleanup failure |
| `tests/test_evidence.py` | MAIL-01, MAIL-03, MAIL-05, orchestration | 10 | 0 | 0 | Behavioral/value | ⚠ Missing failing-sink and configurable-fingerprint integration cases |

**Disabled tests on requirements:** 0  
**Circular patterns detected:** 0  
**Insufficient production-shaped assertions:** 4 gaps noted above

The misleading test is `test_selective_mime_fetches_by_complete_id_only_on_explicit_call`: its fake `Folder.get_message` returns an in-memory object, while installed O365 2.1.0 performs one ordinary message GET before `get_mime_content()` performs a second MIME GET. The passing test proves call order against the fake, not the asserted one-request production boundary.

## Anti-Patterns and Review Findings

| File | Line | Pattern | Severity | Impact |
|---|---:|---|---|---|
| `vicmap_acquire/graph.py`, `candidates.py`, `download.py` | multiple | CR-01: no cryptographically or independently authoritative origin signal | 🛑 BLOCKER | The word “authentic” in the phase goal is not achieved. |
| `read_mailbox.py` / `evidence.py` | 151-162 / 158-161 | CR-02: cross-layer validation mismatch | 🛑 BLOCKER | Valid policy can fail only after publication. |
| `vicmap_acquire/download.py` | 442-466 | CR-03: commit point mixed with cleanup | 🛑 BLOCKER | Failure can be reported for already-published state with leftover partial. |
| `read_mailbox.py` | 151-164 | WR-01: duplicated/incomplete configuration contract | 🛑 BLOCKER | Independently elevated from review warning because it directly falsifies the pre-auth validation must-have. |
| `vicmap_acquire/candidates.py` | 79-93 | WR-02: non-rendered HTML treated as visible text | 🛑 BLOCKER | Independently elevated because hidden source text can create a candidate and falsifies MAIL-02/Plan 03 recognition. |
| `read_mailbox.py` | 110-113 | WR-04: failure reporting calls failing sink again | 🛑 BLOCKER | Independently elevated because a raw exception escapes the closed controller/CLI must-have. |
| `vicmap_acquire/graph.py` | 207-219 | WR-03: SDK fake hides extra representation fetch | ⚠ WARNING | Kept as warning: it weakens the metadata-first boundary but does not by itself falsify the roadmap behavior. |
| `.gitignore` / `read_mailbox.py` | 19-21 / 283-318 | WR-05: output configurability exceeds ignore coverage | ⚠ WARNING | Kept as warning: the shipped default root is ignored, while supported non-default roots are not. |

No unreferenced `TBD`, `FIXME`, or `XXX` debt markers were found. The only empty-return match is the deliberate no-HTML-body branch in `candidates.py`, not a stub.

## Disconfirmation Pass

- **Partially met requirement:** MAIL-04 has strong request-boundary tests, but approved-host equality is not artifact provenance and cleanup can contradict the final reported state.
- **Passing but misleading test:** the selective-MIME fake does not model O365's extra message-representation GET.
- **Uncovered error paths:** post-link unlink failure, event-sink failure, non-default accepted fingerprint integration, and hidden script/style HTML extraction.

## Decision Coverage

All 20 trackable CONTEXT.md decisions were reported as honored by `check.decision-coverage-verify`. This is a non-blocking textual coverage result; it does not override the executable defects above.

## Human Verification Required

No additional sensitive live run should be attempted until the blockers are fixed. The Plan 05 human check is already represented by the redacted live record and operator attestations; this verifier did not reopen console output, token state, mailbox raw data, complete provider IDs/URLs, or artifact contents. After fixes, the operator must explicitly resolve the three descriptor-less prohibitions and perform a new controlled redacted proof that directly ties the authenticated message to the authorized artifact digest.

## Gaps Summary

The phase is blocked by five implementation concerns plus one unresolved prohibition contract. The primary root cause is that the implementation proves deterministic acquisition of bytes matching untrusted labels, not authenticity of those bytes. The remaining blockers are concrete policy and transaction inconsistencies reproduced independently despite the 81-test green suite. None is specifically assigned to a later roadmap phase.

---

_Verified: 2026-09-09T02:24:34Z_  
_Verifier: the agent (gsd-verifier)_
