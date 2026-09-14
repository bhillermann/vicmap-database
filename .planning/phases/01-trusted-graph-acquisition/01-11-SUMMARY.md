---
phase: 01-trusted-graph-acquisition
plan: 11
subsystem: acquisition
tags: [python, live-verification, prohibition-disposition, redaction, o365, s3]

requires:
  - phase: 01-06
    provides: Authenticated-origin policy and the fail-closed bucket/path prefix placeholder this plan replaces with a real value
  - phase: 01-07
    provides: Rendered-context-aware archive-link extraction, later found to have a void-element defect this plan's live re-proof surfaced
  - phase: 01-08
    provides: The explicit publication commit point backing PROHIB-03's enforcement evidence
  - phase: 01-09
    provides: The shared validate_acquisition_policy contract and the emit-at-most-once evidence sink backing PROHIB-04's evidence
  - phase: 01-10
    provides: Connection-level MIME retrieval and PROHIB-01's runtime enforcement evidence
provides:
  - Real committed trusted bucket/path authority in vicmap.toml, replacing the fail-closed placeholder
  - One connected, redacted live-transaction proof correlating one authenticated message, one authorized download target, and one finalized artifact digest from a single uninterrupted invocation, superseding the prior composite record and closing verification gap G-01 bullet 4
  - Corrected, factually accurate tenant-scope and legacy-checkout-token records distinguishing operator-attested facts, code-verified facts, and an openly recorded accepted residual risk
  - Explicit operator dispositions (all five accepted) for PROHIB-01 through PROHIB-05 with named enforcement evidence and residual risk, closing verification gap G-06
  - Five new COVERAGE.md rows for the MIME direct-request, authentication-headers, and bucket/path-prefix capabilities this gap-closure wave added
affects: [02-safe-geospatial-discovery, trusted-graph-acquisition]

actuals:
  tokens: 4127
  tasks: 3
  commits: 10
commits: 10
plan_head_before: 3a8c977f797dc3311d9245848a19b0f05f83699c

tech-stack:
  added: []
  patterns:
    - "A live acquisition failure is recorded and escalated, never retried with a relaxed policy — PROHIB-05 enforced procedurally, not just in code, when the first live invocation closed candidate_ambiguous"
    - "Security-relevant attestations separate operator-attested facts from code-verified facts and openly record an accepted residual risk rather than omitting or softening it"

key-files:
  created: []
  modified:
    - vicmap.toml
    - .planning/phases/01-trusted-graph-acquisition/01-LIVE-VERIFICATION.md
    - .planning/phases/01-trusted-graph-acquisition/COVERAGE.md
    - .planning/STATE.md

key-decisions:
  - "Applied the operator's three Task 1 answers (real bucket/path prefix, unchanged required_authentication_results, cleared re-proof destination) to vicmap.toml only, changing no other key."
  - "When the first live invocation closed candidate_ambiguous, halted per the plan's explicit instruction rather than retrying or relaxing any policy, and escalated to the orchestrator instead of guessing at a code fix for security-hardened link-recognition logic."
  - "The root cause (void HTML elements meta/link permanently raising _AnchorCollector's non-rendered suppression counter, introduced by 01-07) was fixed under its own auditable gap-closure plan (01-12), not worked around inside this plan."
  - "Rewrote the tenant-scope record to state the true condition (tenant-wide Mail.Read, not per-mailbox) as three separate facts: operator-attested credential scope, code-verified single-mailbox behavior, and an openly recorded accepted residual risk — rather than the superseded per-mailbox claim."
  - "Moved the legacy-checkout-token record out of Operator attestations into the verified-checks section, since MemoryTokenBackend usage and the absence/gitignoring of token/ are code facts, not operator claims."
  - "Recorded the operator's explicit disposition (accepted, for all five PROHIB identifiers) as a table with residual risk carried forward from the checkpoint evidence, rather than inferring any disposition from a passing test."

patterns-established:
  - "A checkpoint:human-verify gate reviewing prohibition dispositions distinguishes 'evidence exists' from 'a human accepted it' — the executor assembles and presents evidence but never records a disposition itself."

requirements-completed: [MAIL-01, MAIL-02, MAIL-03, MAIL-04, MAIL-05]

coverage:
  - id: D1
    description: "vicmap.toml carries a real, non-placeholder trusted bucket/path authority (https://s3.ap-southeast-2.amazonaws.com/cl-isd-prd-datashare-s3-delivery/), and loads cleanly through the shared policy validator."
    requirement: MAIL-04
    verification:
      - kind: other
        ref: "nix develop --command python -c \"read_mailbox.load_config(...)\" exits 0"
        status: pass
      - kind: unit
        ref: "tests/test_download.py#DownloadTargetPolicyTest (prefix authority tests, unchanged, still pass against the real value's shape)"
        status: pass
    human_judgment: false
  - id: D2
    description: "One connected, uninterrupted live invocation produced candidate_selected, download_target, and artifact_finalized together, and both sha256sum and an independent Python streaming calculation reproduced the recorded byte count and SHA-256, superseding the prior composite record."
    requirement: MAIL-04
    verification:
      - kind: manual_procedural
        ref: ".planning/phases/01-trusted-graph-acquisition/01-LIVE-VERIFICATION.md#Connected transaction proof"
        status: pass
    human_judgment: true
    rationale: "This is a live, redacted, security-sensitive record correlating a real authenticated message to a real artifact digest. I ran the automated grep-based redaction review and it passed, and the deterministic suite and independent digest reproduction both back it, but the disclosure correctness of a live sensitive record is the kind of judgment call that benefits from a human read beyond automated pattern checks."
  - id: D3
    description: "COVERAGE.md gained five new capability rows (graph.mime-value-direct-request, graph.ordinary-message-representation-get, graph.internet-message-headers-property, graph.authentication-results-headers, artifact.authorized-bucket-path-prefix) with every OPT-OUT row carrying a reason, and no existing row was removed."
    verification:
      - kind: other
        ref: "grep -c '^| ' COVERAGE.md -> 43 (>= 40 threshold)"
        status: pass
    human_judgment: false
  - id: D4
    description: "All five declared prohibitions (PROHIB-01..05) carry an explicit operator-stated disposition (accepted), named enforcement evidence, and a residual risk recorded as known-and-accepted rather than unresolved."
    verification:
      - kind: manual_procedural
        ref: ".planning/phases/01-trusted-graph-acquisition/01-LIVE-VERIFICATION.md#Prohibition Disposition"
        status: pass
    human_judgment: true
    rationale: "Prohibition acceptance is inherently a human trust decision the plan's own gate (blocking-human) requires; no test can substitute for it, and none was inferred here."
  - id: D5
    description: "The tenant-scope and legacy-checkout-token records in 01-LIVE-VERIFICATION.md state the true, code-verified conditions (tenant-wide Mail.Read credential; MemoryTokenBackend with no on-disk token) rather than a superseded per-mailbox claim or an unverifiable attestation, with the tenant-wide credential's residual risk recorded openly."
    verification:
      - kind: other
        ref: "vicmap_acquire/graph.py:12,119,146; tests/test_graph.py::GraphReadOnlyEnforcementTest::test_prohib_01_non_inbox_folder_rejected_before_any_request; .gitignore:3"
        status: pass
    human_judgment: false

duration: ~90min active (across three work sessions spanning 2026-09-09 to 2026-09-14, interrupted twice by required halts)
completed: 2026-09-14
status: complete
---

# Phase 01 Plan 11: Connected Live Re-Proof and Prohibition Disposition Summary

**Committed the real trusted bucket/path prefix, produced one connected redacted live-transaction proof after a live parser defect was found and fixed in a separate gap-closure plan, corrected two attestation records to state their true conditions, and recorded the operator's explicit accepted disposition for all five declared prohibitions.**

## Performance

- **Duration:** ~90 min active work, across three sessions (2026-09-09 initial run through the Task 2 blocker; 2026-09-09 continuation after the 01-12 fix landed; 2026-09-14 final session applying the operator's corrections and dispositions)
- **Started:** 2026-09-09T05:56:00Z (approx.)
- **Completed:** 2026-09-14T00:14:00Z
- **Tasks:** 3
- **Files modified:** 4 (`vicmap.toml`, `01-LIVE-VERIFICATION.md`, `COVERAGE.md`, `STATE.md`)

## Accomplishments

- `vicmap.toml`'s `allowed_url_prefixes` now names the real trusted authority `https://s3.ap-southeast-2.amazonaws.com/cl-isd-prd-datashare-s3-delivery/`, replacing the fail-closed placeholder committed in 01-06; `required_authentication_results` is unchanged (`dkim`, `dmarc`, `compauth`), all three confirmed passing on the genuine message.
- Task 2 required **two live invocations** of `read_mailbox.py`, not one:
  1. The first invocation (against the newly real trust policy) closed with `candidate_ambiguous` at the `candidate` stage, before any artifact host was contacted. Per the plan's explicit instruction, this was recorded and not retried with a relaxed policy — instead escalated as a blocker.
  2. The coordinator diagnosed the root cause read-only against the live message: Plan 01-07 had placed the void HTML elements `meta`/`link` into `_AnchorCollector`'s non-rendered suppression set. Void elements never emit an end tag, so bare `<meta>`/`<link>` tags in the message's `<head>` raised the suppression counter with nothing to lower it, permanently suppressing the entire body. This was fixed under its own gap-closure plan, **01-12** (`_VOID_ELEMENTS` carve-out), with no policy or allowlist relaxed.
  3. The second invocation, run after 01-12 landed against the same unmodified `vicmap.toml`, succeeded end to end: `candidate_selected` → `download_target` → `artifact_finalized`, all captured from one uninterrupted process. The finalized artifact (`artifacts/Order_OK0VUZ.zip`, 233,089,097 bytes, SHA-256 `6a7868094ccab5b01fed11aec34587bd7e92bacdc35935b3c2835df21665411b`) was independently reproduced by both `sha256sum` and a Python streaming calculation.
- `01-LIVE-VERIFICATION.md` was rewritten with a `## Connected transaction proof` section correlating the authenticated message, authorized target, and finalized digest from that single invocation, an `## Authenticated origin` note recording the passing DKIM/DMARC/compauth verdicts, and a historical note that the prior composite record (a Plan 01-05 executor narration plus a later mailbox-only recovery scan) is superseded — while confirming its message fingerprint, order ID, path fingerprint, and byte count/SHA-256 all agree with the same underlying transaction.
- Two factual corrections requested by the coordinator (after operator review) were applied:
  - **Tenant scope:** the prior record incorrectly claimed the Microsoft application was resource-scoped to `automations@vegetationlink.com.au`. It is not — the operator attests the credential is tenant-wide `Mail.Read`, and per-mailbox scoping was attempted and is unavailable. The record now states this plainly as three separate facts: the operator-attested tenant-wide scope, the code-verified fact that this code path only ever reads the one pinned mailbox (`vicmap_acquire/graph.py:146`) and rejects any non-`Inbox` folder before any request (`GraphReadOnlyEnforcementTest::test_prohib_01_non_inbox_folder_rejected_before_any_request`), and the residual risk — anyone holding the credential can read every mailbox in the tenant — recorded openly as known and accepted, not omitted.
  - **Legacy checkout token:** moved out of "Operator attestations" into the verified-checks section, since it is a directly verifiable code fact (`MemoryTokenBackend` at `vicmap_acquire/graph.py:12,119`; `token/` absent from the working tree; `/token/` gitignored at `.gitignore:3`), not something only the operator could attest to.
- `COVERAGE.md` gained five new rows: `graph.mime-value-direct-request` (INTEGRATE), `graph.ordinary-message-representation-get` (OPT-OUT), `graph.internet-message-headers-property` (OPT-OUT), `graph.authentication-results-headers` (INTEGRATE), `artifact.authorized-bucket-path-prefix` (INTEGRATE) — 43 total rows, no existing row removed or changed.
- A `## Prohibition Disposition` table was appended to `01-LIVE-VERIFICATION.md`: the operator (`bhillermann@vegetationlink.com.au`, 2026-09-14) explicitly accepted all five prohibitions (PROHIB-01 through PROHIB-05), each with its named enforcement evidence and its residual risk recorded as known and accepted rather than unresolved. No disposition was inferred by the executor from a passing test.
- Full deterministic suite: 171 tests, 0 failures, 0 skips, confirmed multiple times across the plan's life (before and after the 01-12 fix, and again before this final commit).

## Task Commits

Each task was committed atomically. Because Task 2 was blocked mid-execution by a live parser defect that required its own gap-closure plan (01-12) to fix, this plan's commit history interleaves with 01-12's on the shared sequential branch:

1. **Task 1: Operator supplies the real trusted bucket/path prefix** - `9611ad2` (feat)
2. **Task 2, first attempt (blocked):** `7a2ab6a` (docs: record the `candidate_ambiguous` blocker in STATE.md)
   - *(interleaving gap-closure plan 01-12, not part of this plan's own tasks: `f1498ed`, `05cfc9b`, `ca014ba`, `da633a8`, `b437c9d`)*
3. **Task 2, completed:** `a9b97e2` (feat: record the connected live re-proof and update COVERAGE.md), `43168e9` (docs: resolve the Task 2 blocker in STATE.md)
4. **Task 3: Prohibition dispositions and attestation corrections:** `425bc75` (feat)

**Plan metadata:** committed separately (see final commit below).

`actuals.commits: 10` is the measured count from `plan_head_before` to `HEAD` at SUMMARY time (`git rev-list --count`). Five of those ten commits (`9611ad2`, `7a2ab6a`, `a9b97e2`, `43168e9`, `425bc75`) are this plan's own; the other five (`f1498ed`, `05cfc9b`, `ca014ba`, `da633a8`, `b437c9d`) belong to the interleaved sibling gap-closure plan 01-12, which has its own SUMMARY and its own actuals. Both plans share one sequential branch, so the measured range necessarily includes both.

## Files Created/Modified

- `vicmap.toml` - `allowed_url_prefixes` now names the real trusted bucket/path authority
- `.planning/phases/01-trusted-graph-acquisition/01-LIVE-VERIFICATION.md` - Rewritten with the connected transaction proof, authenticated-origin note, two-invocations history, corrected attestation/verified-fact split, and the Prohibition Disposition table
- `.planning/phases/01-trusted-graph-acquisition/COVERAGE.md` - Five new capability rows for this gap-closure wave
- `.planning/STATE.md` - Blocker recorded, then resolved, after the 01-12 fix landed

## Decisions Made

See `key-decisions` in frontmatter. In short: applied the operator's Task 1 answers verbatim and touched no other config key; on the first live invocation's `candidate_ambiguous` failure, halted and escalated per the plan's own instruction rather than guessing at a fix to security-hardened link-recognition code; the actual defect (a void-element parser bug from 01-07) was fixed in its own auditable plan (01-12) with no policy relaxed; corrected two attestation records to state their true, code-verified conditions rather than a superseded or unverifiable claim, recording the resulting residual risk openly; and recorded the operator's explicit disposition for all five prohibitions rather than inferring any of them.

## Deviations from Plan

### Auto-fixed Issues

None — no Rule 1-3 auto-fixes were made directly by this plan's execution. The one substantive defect encountered (the void-element suppression bug) was explicitly *not* auto-fixed inline; it was escalated and repaired under its own separate, auditable gap-closure plan (01-12), consistent with this plan's "do not retry with a relaxed policy" instruction and with not making inline code changes to security-hardened link-recognition logic without review.

### Corrections Applied at Coordinator's Direction

**1. [Factual correction] Tenant-scope attestation was inaccurate**
- **Found during:** Task 3 follow-up, after operator review of the drafted record
- **Issue:** The record (drafted during Task 2) claimed the Microsoft application was "resource-scoped to automations@vegetationlink.com.au." This is not true — the operator confirmed the credential is tenant-wide `Mail.Read`, and per-mailbox scoping was attempted and is unavailable.
- **Fix:** Rewrote the record as three separate facts (operator-attested tenant-wide scope; code-verified single-mailbox behavior at `vicmap_acquire/graph.py:146` and non-Inbox rejection; the resulting residual risk recorded openly as known and accepted).
- **Files modified:** `.planning/phases/01-trusted-graph-acquisition/01-LIVE-VERIFICATION.md`
- **Verification:** Citations checked directly against `vicmap_acquire/graph.py` and the named test before writing.
- **Committed in:** `425bc75`

**2. [Factual correction] Legacy-checkout-token line was framed as an attestation but is a verifiable code fact**
- **Found during:** Task 3 follow-up
- **Issue:** The record placed the legacy-token claim under "Operator attestations," implying it required the operator's word, when `MemoryTokenBackend` usage and the absence/gitignoring of `token/` are directly verifiable in code.
- **Fix:** Moved the line into the deterministic/runtime-state checks section, worded as verified with file:line citations.
- **Files modified:** `.planning/phases/01-trusted-graph-acquisition/01-LIVE-VERIFICATION.md`
- **Verification:** Confirmed `vicmap_acquire/graph.py:12` (`MemoryTokenBackend` import) and `:119` (use), `token/` absent via `ls`, `.gitignore:3` (`/token/`).
- **Committed in:** `425bc75`

---

**Total deviations:** 0 auto-fixed; 2 factual corrections applied at the coordinator's explicit direction after operator review.
**Impact on plan:** Both corrections improve the accuracy of a security-relevant disclosure record. No scope creep — no code behavior was changed by either correction.

## Known Stubs

None - the fail-closed placeholder tracked as a known stub in 01-06's SUMMARY is resolved by this plan's Task 1.

## Issues Encountered

- Task 2's first live invocation failed with `candidate_ambiguous` due to a real parser defect (void elements permanently raising the non-rendered suppression counter, from 01-07). This was not an issue with this plan's own work — it was a live-environment discovery that required a separate gap-closure plan (01-12) to resolve before Task 2 could complete. See Task Commits and Accomplishments above for the full trace.

## User Setup Required

None — Task 1's `user_setup` items (reading the ready message for the trusted prefix, confirming Entra/Exchange scope) were completed by the operator before this plan resumed; the Task 1 checkpoint answers are recorded in this plan's commit `9611ad2` and in `01-LIVE-VERIFICATION.md`'s attestations.

## Next Phase Readiness

- Verification gap G-01's `missing` bullet 4 (disconnected message-to-transport provenance) is closed: `01-LIVE-VERIFICATION.md` now records one connected, redacted proof from a single invocation.
- Verification gap G-06 (descriptor-less prohibition judgment) is closed: all five prohibitions carry an explicit, operator-stated, dated disposition with named enforcement evidence and an openly recorded residual risk.
- `requirements-completed` lists `MAIL-01..05`; the shared-ID gate reports 5/5 ready to mark complete (no sibling plan in this phase still declares them undone).
- The tenant-wide `Mail.Read` credential scope is now visible in the record as a known, accepted residual risk rather than an inaccurate per-mailbox claim — any future phase relying on this credential's scope should read `01-LIVE-VERIFICATION.md`'s corrected tenant-scope entry rather than assuming per-mailbox isolation.
- Phase 01 (Trusted Graph Acquisition) has no open plans after this one; `01-VERIFICATION.md`'s `gaps_found` status should be re-evaluated against the now-closed gaps in a follow-up verification pass.

---
*Phase: 01-trusted-graph-acquisition*
*Completed: 2026-09-14*

## Self-Check: PASSED

- FOUND: vicmap.toml contains the real prefix, no placeholder
- FOUND: .planning/phases/01-trusted-graph-acquisition/01-LIVE-VERIFICATION.md contains "## Connected transaction proof" and "## Prohibition Disposition"
- FOUND: .planning/phases/01-trusted-graph-acquisition/COVERAGE.md has 43 rows
- FOUND commit: 9611ad2 (feat, Task 1)
- FOUND commit: 7a2ab6a (docs, blocker recorded)
- FOUND commit: a9b97e2 (feat, Task 2 connected proof)
- FOUND commit: 43168e9 (docs, blocker resolved)
- FOUND commit: 425bc75 (feat, Task 3 dispositions + corrections)
- Full deterministic suite: `OPNIX_ENV_DISABLE=1 nix develop --impure --no-write-lock-file path:. --command python -m unittest discover -s tests` -> 171 tests, OK, no skips
- Re-ran all task-level acceptance-criteria greps and behavioral assertions from the plan: all pass
- `grep -c '^| PROHIB-' 01-LIVE-VERIFICATION.md` -> 5
