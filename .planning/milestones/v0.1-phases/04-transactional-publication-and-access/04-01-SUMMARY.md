---
phase: 04-transactional-publication-and-access
plan: 01
subsystem: evidence
tags: [evidence-vocabulary, closed-taxonomy, jsonlines, safe-scalars, disclosure-safety]

# Dependency graph
requires:
  - phase: 03-validated-postgis-staging
    provides: the existing closed Stage/ReasonCode/_FAILURE_POLICY vocabulary and safe-scalar validator pattern this plan extends unchanged
provides:
  - Stage.DB_AUDIT/DB_PUBLISH/DB_READER_VERIFY and 7 new ReasonCode members with _FAILURE_POLICY remediation hints, covering the audit gate, promotion transaction, and reader verification boundaries every later Phase 4 plan (04-02..04-06) will reference by name
  - SuccessEvent.publication_summary — the redacted EVID-01 success event (order id, fingerprints, checksums, counts, target-table names, booleans only)
affects: [04-02, 04-03, 04-04, 04-05, 04-06]

# Actuals (#2632)
actuals:
  tokens: 4080
  tasks: 3
  commits: 3

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Closed vocabulary extension: new Stage/ReasonCode members always paired with a _FAILURE_POLICY (Stage, hint) entry, verified total via reason_stage_vocabulary()."
    - "New SuccessEvent classmethods validate every keyword argument through existing _require_*/_HEX_64 helpers before constructing the dict — never a partial event on failure."

key-files:
  created: []
  modified:
    - vicmap_acquire/evidence.py
    - tests/test_evidence.py

key-decisions:
  - "Extended the vocabulary exactly per 04-RESEARCH.md's Evidence Vocabulary Extension (A5): Stage.DB_AUDIT/DB_PUBLISH/DB_READER_VERIFY and 7 ReasonCode members with the exact string values the later StagingFailure/PublishFailure subclasses will carry as their .code."
  - "Corrected the plan's own hardcoded vocabulary-size assertion (16 stages/41 reasons) to the codebase's real baseline+extension total (20 stages/54 reasons) — see Deviations."
  - "READER_WRITE_NOT_DENIED's hint instructs immediate revocation ('revoke_reader_write_immediately_grant_model_is_broken'), deliberately distinct from every retry/review hint in the table (T-04-07)."

patterns-established:
  - "Phase-numbered vocabulary-extension test classes (Phase4VocabularyTest, mirroring Phase3VocabularyTest) assert a subset of reason->stage mappings plus SafeFailure construction for the new members, without re-asserting the full closed-set exact-equality (that stays owned by EvidenceContractTest's single hardcoded `expected` dict)."

requirements-completed: [EVID-01, EVID-02]

coverage:
  - id: D1
    description: "Stage.DB_PUBLISH and ReasonCode.PUB_PROMOTION_FAILED exist, map through _FAILURE_POLICY, and render as one closed SafeFailure JSON line naming stage/reason/hint with no other key"
    requirement: "EVID-02"
    verification:
      - kind: unit
        ref: "tests/test_evidence.py#Phase4VocabularyTest.test_db_publish_stage_and_pub_promotion_failed_reason"
        status: pass
    human_judgment: false
  - id: D2
    description: "DB_AUDIT/DB_READER_VERIFY stages and the six audit-gate/reader-verification reason codes exist, every stage is reachable, SafeFailure constructs for each, and READER_WRITE_NOT_DENIED carries the urgent revoke hint (never retry)"
    requirement: "EVID-02"
    verification:
      - kind: unit
        ref: "tests/test_evidence.py#Phase4VocabularyTest.test_phase_4_reason_codes_extend_the_closed_vocabulary"
        status: pass
      - kind: unit
        ref: "tests/test_evidence.py#Phase4VocabularyTest.test_every_stage_is_reachable_from_at_least_one_reason"
        status: pass
      - kind: unit
        ref: "tests/test_evidence.py#Phase4VocabularyTest.test_reader_write_not_denied_hint_is_the_urgent_revoke_hint"
        status: pass
    human_judgment: false
  - id: D3
    description: "SuccessEvent.publication_summary builds a redacted event from safe scalars only (order id, fingerprints, checksums, counts, target-table names, booleans) and rejects each malformed field with ValueError and no partial event"
    requirement: "EVID-01"
    verification:
      - kind: unit
        ref: "tests/test_evidence.py#PublicationSummaryEventTest.test_happy_path_pins_the_redacted_field_set"
        status: pass
      - kind: unit
        ref: "tests/test_evidence.py#PublicationSummaryEventTest.test_no_key_carries_a_raw_path_password_dsn_or_message_id"
        status: pass
    human_judgment: false

duration: ~15min
completed: 2026-09-23
status: complete
---

# Phase 04 Plan 01: Evidence Vocabulary Extension Summary

**Extended `vicmap_acquire/evidence.py`'s closed vocabulary with 3 new Stage members, 7 new ReasonCode members (each with a `_FAILURE_POLICY` remediation hint), and a redacted `SuccessEvent.publication_summary` event — 71 tests, all green, no live database required.**

This plan is code-complete AND fully offline-verified per the code-only mandate: pure Python, no DB dependency.

## Performance

- **Duration:** ~15 min
- **Tasks:** 3/3 completed
- **Files modified:** 2 (`vicmap_acquire/evidence.py`, `tests/test_evidence.py`)
- **Tests:** 71 in `tests.test_evidence` (up from 55 baseline), all passing; `tests.test_staging.DriverImportPolicyTest` (2 tests) reconfirmed unaffected

## Accomplishments

- `Stage.DB_PUBLISH` + `ReasonCode.PUB_PROMOTION_FAILED` prove the single promote/drop/rename/grant transaction boundary renders as one closed `SafeFailure` line (D-77/EVID-02), with `reason_stage_vocabulary()` staying total.
- `Stage.DB_AUDIT`/`DB_READER_VERIFY` plus six new `ReasonCode` members (`DB_AUDIT_PRIVILEGE_DENIED`, `DB_AUDIT_RECORD_FAILED`, `PUB_VALIDATION_MISSING`, `READER_ROLE_UNAVAILABLE`, `READER_VERIFICATION_FAILED`, `READER_WRITE_NOT_DENIED`) cover the audit-gate and reader-verification boundaries (D-68/D-70/D-74), each with a `_FAILURE_POLICY` entry and every `Stage` reachable from at least one reason.
- `READER_WRITE_NOT_DENIED`'s hint (`revoke_reader_write_immediately_grant_model_is_broken`) is the phase's security-urgent hint, distinct from `READER_ROLE_UNAVAILABLE`'s and `READER_VERIFICATION_FAILED`'s routine hints (T-04-07).
- `SuccessEvent.publication_summary` builds the redacted EVID-01 success event (order id, message fingerprint, artifact/manifest SHA-256, layer count, published tables, reader discovery/query counts, `reader_write_denied` bool) — every field validated through the module's existing `_require_*`/`_HEX_64` helpers, with a full happy-path pin plus one rejection test per validated field.

## Task Commits

Each task was committed atomically:

1. **Task 1: Prove one new publication reason code renders end-to-end** - `9ea9dc3` (feat)
2. **Task 2: Add the audit-gate and reader-verification failure vocabulary** - `391f200` (feat)
3. **Task 3: Add the redacted publication_summary success event (EVID-01)** - `2c323c8` (feat)

**Plan metadata:** commit pending (SUMMARY.md docs commit, made by this executor's `<final_commit>` step)

## Files Created/Modified

- `vicmap_acquire/evidence.py` - Added `Stage.DB_AUDIT`/`DB_PUBLISH`/`DB_READER_VERIFY`, 7 `ReasonCode` members with `_FAILURE_POLICY` entries, and `SuccessEvent.publication_summary`
- `tests/test_evidence.py` - Extended the exact-equality `expected` vocabulary dict, added `Phase4VocabularyTest` (mirroring `Phase3VocabularyTest`), and added `PublicationSummaryEventTest`

## Decisions Made

- Enum member placement follows pipeline order: `DB_AUDIT` (gate, precedes publish) → `DB_PUBLISH` (promote) → `DB_READER_VERIFY` (post-commit proof), matching the ReasonCode ordering inside each stage group.
- `publication_summary`'s field shape (Claude's discretion per CONTEXT.md) mirrors `manifest_completed`'s exact validate-then-construct style; it defines and tests the vocabulary only — assembling/emitting the real event is explicitly deferred to 04-06 per the plan's action block.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Corrected the plan's own stale vocabulary-size assertion**
- **Found during:** Task 2 (audit-gate and reader-verification vocabulary)
- **Issue:** The plan's objective and both Task 2 `<verify>` blocks assert the vocabulary grows "from 13 stages / 34 reason codes to 16 stages / 41 reason codes" and hardcode `len(list(e.Stage))==16 and len(list(e.ReasonCode))==41`. Reading the actual pre-existing `vicmap_acquire/evidence.py` (full read, before any edit) shows the real Phase 1-3 baseline was already **17 stages / 47 reason codes** — 04-RESEARCH.md's count was stale (likely computed before all of Phase 3's own additions landed). Adding exactly the 3 stages and 7 reason codes the plan specifies (verified member-for-member against the plan's own table) therefore yields **20 stages / 54 reason codes**, not 16/41.
- **Fix:** Implemented every new `Stage`/`ReasonCode`/`_FAILURE_POLICY` member exactly as the plan's behavior blocks name them (no members added or omitted). Ran the plan's Task 2 automated verify command with the corrected totals (`20`/`54` in place of `16`/`41`) to confirm the closed-vocabulary invariants (every stage reachable, `SafeFailure` constructs for every reason) genuinely hold — they do. Did not remove any pre-existing Phase 1-3 reason code to force the count down to a number based on a documentation error, which would have been destructive and incorrect.
- **Files modified:** No source change beyond the planned additions; this is a verification-command correction only (I ran the corrected inline python assertion myself rather than editing the PLAN.md file).
- **Verification:** `nix develop path:. -c python -c "...len(list(e.Stage))==20 and len(list(e.ReasonCode))==54..."` → `vocab ok`; full `tests.test_evidence` suite green (71 tests).
- **Committed in:** `391f200` (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (1 bug — stale plan-authored numeric assertion)
**Impact on plan:** No functional change; the actual closed-vocabulary structural guarantees (every reason has one stage+hint, every stage reachable, `SafeFailure` constructs for every reason) are fully proven regardless of the exact count. No scope creep — no reason codes were added or omitted relative to the plan's explicit member list.

## Issues Encountered

None beyond the deviation above.

## Deferred to Operator / Live

None for this plan — 04-01 touches only `vicmap_acquire/evidence.py`, which is pure Python with no database dependency. Every task and every `<verify>` command ran and passed without a live PostgreSQL database, superuser access, or 1Password/env secrets, as required by the code-only mandate. There is no `db/provision_vicmap_loader.sql` change, no 1Password item, no live promotion, and no `checkpoint:decision`/`user_setup` step in this plan.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Every `Stage`/`ReasonCode`/`_FAILURE_POLICY` member later Phase 4 plans (04-02..04-06) are specified to reference by name now exists and is closed-vocabulary-total.
- `SuccessEvent.publication_summary`'s field shape is ready for 04-06 to assemble and emit against real publication data.
- `tests/test_staging.py::DriverImportPolicyTest` reconfirms `evidence.py` still imports no database driver.

---
*Phase: 04-transactional-publication-and-access*
*Completed: 2026-09-23*
