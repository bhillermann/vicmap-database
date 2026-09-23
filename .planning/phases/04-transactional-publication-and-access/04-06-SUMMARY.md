---
phase: 04-transactional-publication-and-access
plan: 06
subsystem: database
tags: [postgis, psycopg, evidence, cli, redaction]

# Dependency graph
requires:
  - phase: 04-transactional-publication-and-access (04-04)
    provides: promote_order/PublishPolicy/PromotionResult, the D-68 gate, and vicmap_audit.staging_validation
  - phase: 04-transactional-publication-and-access (04-05)
    provides: verify_reader_access/ReaderVerification (PUB-04/PUB-05 reader proof)
  - phase: 04-transactional-publication-and-access (04-01)
    provides: SuccessEvent.publication_summary's redaction vocabulary and Stage/ReasonCode enums this plan maps against
provides:
  - assemble_summary/write_summary/read_layer_validations/summary_to_publication_event in vicmap_acquire/publish.py
  - publish_order.py -- the fourth one-CLI-per-phase entry point (read_mailbox -> discover_order -> stage_order -> publish_order)
  - EVID-02's exit-code contract proven for every publish_order.py failure boundary
affects: [gsd-ship, milestone-summary, phase-05-legacy-cleanup]

# Actuals (#2632)
actuals:
  tokens: 13705
  tasks: 3
  commits: 3

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Summary assembly re-reads durable per-phase artifacts (provenance sidecar, manifest, vicmap_audit rows) rather than threading an in-memory record across phase invocations (D-76)"
    - "A library function's own dedicated exception classes cover named failure boundaries; an unexpected exception (e.g. write_summary's bare OSError) is deliberately left unwrapped for the CLI's catch-all INTERNAL_FAILURE mapping rather than inventing an unlisted reason code"

key-files:
  created:
    - publish_order.py
    - tests/test_publish_order.py
  modified:
    - vicmap_acquire/publish.py
    - tests/test_publish.py

key-decisions:
  - "assemble_summary re-reads Phase 1's provenance sidecar directly via download.read_provenance_sidecar, even though manifest.json also carries artifact_sha256/message_fingerprint copies -- an independent second read, never trusting the manifest's own copy (D-76's explicit re-read-every-durable-artifact contract)"
  - "read_layer_validations is a second, independent SELECT against vicmap_audit.staging_validation, separate from assert_all_layers_validated's own gate query -- the gate's in-memory pass/fail result is never threaded into the summary"
  - "promote_order already runs the D-68 gate as its own first action, so publish_order.py composes it as a single call (not a separate assert_all_layers_validated call before promote_order) -- 'gate then promote' is one composed step, not two"
  - "A missing VICMAP_READER_PASSWORD is deliberately NOT checked before promotion in publish_order.py -- it is left to verify_reader_access's own guard, which fails closed with READER_ROLE_UNAVAILABLE only after the promotion transaction has already durably committed (D-66..D-73's metadata-move publish does not depend on the reader proof that follows it)"
  - "write_summary lets a bare OSError propagate unwrapped rather than inventing a new reason code -- there is no dedicated Stage/ReasonCode for a summary-write failure in evidence.py's closed vocabulary, so it is deliberately left for the CLI's catch-all INTERNAL_FAILURE mapping, exactly as an unexpected failure should be handled"
  - "summary_to_publication_event reconstructs the SuccessEvent purely from the already-assembled summary dict's own fields, re-running the same redaction validators, so the rendered event is provably the summary.json file's own mirror rather than a second independently-built payload"

requirements-completed: [EVID-01, EVID-02]

coverage:
  - id: D1
    description: "assemble_summary/write_summary link message fingerprint, artifact checksum, discovered layers, staging validation, published tables, and reader verification into a redacted summary.json, rejecting malformed or non-PASS inputs"
    requirement: "EVID-01"
    verification:
      - kind: unit
        ref: "tests/test_publish.py#SummaryAssemblyTest (7 cases)"
        status: pass
      - kind: unit
        ref: "tests/test_publish.py#WriteSummaryTest.test_writes_canonical_json_into_the_run_directory"
        status: pass
      - kind: unit
        ref: "tests/test_publish.py#ReadLayerValidationsTest (3 cases)"
        status: pass
    human_judgment: false
  - id: D2
    description: "publish_order.py composes load-config -> gate+promote -> reader-verify -> summary as one ordered CLI, reading both passwords from the environment only, and exits 0 on success"
    requirement: "EVID-01"
    verification:
      - kind: unit
        ref: "tests/test_publish_order.py#SuccessPathTest.test_successful_run_returns_zero_and_renders_the_summary_event"
        status: pass
    human_judgment: false
  - id: D3
    description: "Every publish_order.py failure boundary (config, manifest, D-68 gate/audit, promotion, reader-verify, unexpected exception) returns a non-zero, boundary-named, secret-free exit"
    requirement: "EVID-02"
    verification:
      - kind: unit
        ref: "tests/test_publish_order.py#ConfigInvalidTest, ManifestFailureTest, PublicationGateFailureTest, PromotionFailureTest, ReaderVerificationFailureTest, InternalFailureTest, ExitContractShapeTest (15 cases)"
        status: pass
    human_judgment: false
  - id: D4
    description: "A live end-to-end publish_order.py run against a real, fully-provisioned order, proving the whole pipeline against a real database"
    verification: []
    human_judgment: true
    rationale: "Requires an operator-provisioned vicmap_audit schema (D-70), a vicmap_reader LOGIN role plus a resolvable VICMAP_READER_PASSWORD (D-72/D-74), and a completed Phase 3 staging run over a real order. This is a code-only phase delivery per the operator's instruction; not performed in this session. See 'Deferred to operator' below for exact resume steps."

# Metrics
duration: ~20min
completed: 2026-09-23
status: complete
---

# Phase 4 Plan 6: Assemble the EVID-01 Summary and Wire publish_order.py Summary

**Redacted `summary.json` + `publication_summary` event assembled by re-reading Phase 1-3's durable artifacts, plus `publish_order.py`, the fourth one-CLI-per-phase entry point composing gate→promote→reader-verify→summary with a fully-proven EVID-02 exit-code contract.**

## Performance

- **Duration:** ~20 min
- **Completed:** 2026-09-23
- **Tasks:** 3
- **Files modified:** 4 (2 created, 2 modified)

## Accomplishments

- `assemble_summary`/`write_summary`/`read_layer_validations` in `publish.py` re-read Phase 1's provenance sidecar, Phase 2's manifest, and Phase 3's `vicmap_audit` rows into one redacted `summary.json` linking all six EVID-01 facts (message fingerprint, artifact checksum, discovered layers, staging validation, published tables, reader verification), rejecting malformed or non-PASS inputs before returning anything.
- `summary_to_publication_event` rebuilds the D-75 `publication_summary` event from the already-assembled summary dict, so the emitted event is provably the file's own mirror.
- `publish_order.py` — the fourth and final one-CLI-per-phase entry point (D-77) — composes `load_database_config`/`load_discovery_config` → `promote_order` (which runs the D-68 gate internally) → `verify_reader_access` → `read_layer_validations` → `assemble_summary`/`write_summary`, reading `VICMAP_DB_PASSWORD`/`VICMAP_READER_PASSWORD` from the environment only.
- EVID-02's exit-code contract is fully proven offline: every failure boundary (config invalid, manifest unreadable, `PublicationValidationMissing`/`AuditPrivilegeDenied`, `PromotionFailed`, `ReaderRoleUnavailable`/`ReaderVerificationFailed`/`ReaderWriteNotDenied`, and an unexpected-exception catch-all) returns exit code 1 with one boundary-named, secret-free `SafeFailure` line; success returns 0 with exactly one rendered `publication_summary` event.

## Task Commits

Each task was committed atomically:

1. **Task 1: Assemble the redacted summary from durable artifacts (D-75/D-76)** - `300afff` (feat)
2. **Task 2: Wire publish_order.py to run the phase end-to-end** - `6f40313` (feat)
3. **Task 3: EVID-02 exit-code contract for publish_order.py** - `a368b23` (test)

## Files Created/Modified

- `vicmap_acquire/publish.py` — adds `LayerValidationRecord`, `read_layer_validations`, `assemble_summary`, `summary_to_publication_event`, `write_summary`, and `READER_PASSWORD_ENV_VAR`
- `publish_order.py` — new; the fourth CLI, mirroring `stage_order.py`'s shape
- `tests/test_publish.py` — adds `ReadLayerValidationsTest`, `SummaryAssemblyTest`, `WriteSummaryTest`, and `LivePublishOrderFullRunTest` (skip-guarded)
- `tests/test_publish_order.py` — new; 16 offline tests proving the full exit-code contract and the redacted success path

## Decisions Made

See `key-decisions` in the frontmatter above — summarized:
- `assemble_summary` performs its own independent re-read of the Phase 1 provenance sidecar rather than trusting the manifest's copy of the same facts (D-76).
- `read_layer_validations` is a second, independent read of `vicmap_audit.staging_validation`, never the gate's in-memory result.
- `promote_order` already runs the D-68 gate internally, so `publish_order.py` composes it as a single call.
- A missing reader password is intentionally left to `verify_reader_access`'s own guard, surfacing only after promotion has already committed.
- `write_summary`'s `OSError` is left unwrapped, falling through to the CLI's `INTERNAL_FAILURE` catch-all rather than inventing a new reason code not present in evidence.py's closed vocabulary.

## Deviations from Plan

None - plan executed exactly as written. The plan's given `assemble_summary` parameter list (`run_directory, order_id, manifest, manifest_digest, validation_rows, publication_result, reader_verification`) was adapted to `order_id, artifact_path, manifest, manifest_digest, validation_rows, publication_result, reader_verification` because the Phase 1 provenance sidecar lives beside `artifacts_dir`'s `Order_{id}.zip`, not inside the per-run `run_directory` (confirmed by tracing `discover_order.py`'s own `read_provenance_sidecar(artifact_path, ...)` call and `DiscoveryRunConfig.artifacts_dir`); this is Claude's-discretion parameter shaping explicitly allowed by the plan ("module layout ... is Claude's discretion"), not a deviation from any must-have — every must-have truth, artifact, and verify command in the plan is satisfied unchanged.

## Issues Encountered

None. The devshell prints the same anticipated opnix `itemNotFound` warning for `VICMAP_READER_PASSWORD` documented in 04-02/04-04/04-05-SUMMARY.md (the 1Password item still does not exist); it does not block `nix develop` or any offline test.

## User Setup Required

None new. Carried unchanged from 04-02/04-04/04-05: the `VICMAP_READER_PASSWORD` 1Password item and `db/provision_vicmap_loader.sql` (run as superuser) are still outstanding — see those SUMMARYs for exact steps. No new environment variable or external service was introduced by this plan.

## Deferred to operator

**Live end-to-end `publish_order.py` run (D4 above; deferred per this run's code-only instruction).** Everything is code-complete and offline-verified (71 tests green across `test_publish.py`/`test_publish_order.py`, full suite 619 tests green with 43 skipped, `DriverImportPolicyTest` still green). The live run itself needs:

1. Create the `VICMAP_READER_PASSWORD` 1Password item (`op://nixos-services/vicmap_reader_credentials/password`) if not already done in a prior phase.
2. Run `db/provision_vicmap_loader.sql` as a PostgreSQL superuser against the `vicmap` database (creates `vicmap_audit.staging_validation`, grants the loader `SELECT`/`INSERT` on it, and creates the `vicmap_reader` LOGIN role with `USAGE ON SCHEMA vicmap`) — if not already done.
3. Confirm both secrets resolve in the devshell: `nix develop path:. -c bash -c 'echo present: ${VICMAP_DB_PASSWORD:+yes} ${VICMAP_READER_PASSWORD:+yes}'` (never echo the values).
4. Run `stage_order.py` against a real order so a validated staging run (with its `vicmap_audit` PASS rows) exists.
5. Run `nix develop path:. -c python publish_order.py` and confirm exit 0, a `summary.json` in the run directory, and one `publication_summary` event on stdout.
6. Un-skip `LivePromoteOneLayerTest`, `LiveMultiLayerPromotionTest`, `LivePromotionRollbackTest`, `LiveReaderVerificationTest`, `LiveReaderWriteDenialTest`, `LiveReaderWriteNotDeniedTest`, and `LivePublishOrderFullRunTest` in `tests/test_publish.py` (set `VICMAP_TEST_POSTGRES_DSN`/`VICMAP_TEST_POSTGRES_SUPERUSER_DSN`) to run the corresponding live proofs recorded as open items in `.planning/WINDOWS.md` (ids 12-15).

## Next Phase Readiness

- The four-CLI-per-phase architecture (`read_mailbox.py` → `discover_order.py` → `stage_order.py` → `publish_order.py`) is complete; no OPS-05 top-level orchestrator was built, matching D-77's explicit scope boundary.
- Phase 4's full success-criteria set (PUB-01..05, EVID-01, EVID-02) is code-complete; only the live database proof remains, tracked in `.planning/WINDOWS.md` and above.
- Ready for Phase 5 (legacy `public` WFS-table cleanup) once the live publish has run at least once.

## Self-Check: PASSED

All created files (`publish_order.py`, `tests/test_publish_order.py`, `.planning/phases/04-transactional-publication-and-access/04-06-SUMMARY.md`) and all three task commits (`300afff`, `6f40313`, `a368b23`) verified present.

---
*Phase: 04-transactional-publication-and-access*
*Completed: 2026-09-23*
