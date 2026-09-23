---
phase: 04-transactional-publication-and-access
plan: 03
subsystem: database
tags: [postgis, psycopg, audit, validation-gate, manifest-digest]

# Dependency graph
requires:
  - phase: 04-transactional-publication-and-access
    plan: 01
    provides: "Stage.DB_AUDIT and ReasonCode.DB_AUDIT_PRIVILEGE_DENIED/DB_AUDIT_RECORD_FAILED reserved by 04-01, wired to record_validation's new exceptions"
  - phase: 04-transactional-publication-and-access
    plan: 02
    provides: "the vicmap_audit.staging_validation table contract (columns + PRIMARY KEY (run_ts, manifest_digest, target_table)) this plan's record_validation writer targets exactly"
  - phase: 03-validated-postgis-staging
    provides: "staging.py's _connect/apply_post_validation_ddl connection-lifecycle pattern, LayerValidation, and stage_order.py's run_staging call site this plan back-fills"
provides:
  - "manifest.manifest_digest(run_directory) -- a thin, ManifestUnreadable-guarded sidecar read returning the same 64-hex digest read_manifest verifies"
  - "staging.record_validation -- durable, idempotent PASS-row writer into vicmap_audit.staging_validation, with AuditPrivilegeDenied/AuditRecordFailed closed failures"
  - "stage_order.py's D-70 back-fill: one audit row per layer written only after run_staging returns every LayerValidation without raising"
affects: [04-04, 04-05, 04-06]

# Actuals (#2632)
actuals:
  tokens: 7489
  tasks: 2
  commits: 2
plan_head_before: 446514816041783930c989581a9cedbcd2d75fd6

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "record_validation follows apply_post_validation_ddl's exact connection lifecycle (_connect, one implicit transaction, commit on success, rollback+closed exception on failure) -- no new lifecycle pattern introduced for the audit write path."
    - "ON CONFLICT DO NOTHING is this codebase's idempotency idiom for a durable audit/gate row keyed by a natural composite primary key, rather than a pre-check SELECT."

key-files:
  created: []
  modified:
    - vicmap_acquire/manifest.py
    - vicmap_acquire/staging.py
    - stage_order.py
    - tests/test_manifest.py
    - tests/test_staging.py

key-decisions:
  - "record_validation lives in staging.py, not a new module -- it is the one module permitted to import a PostgreSQL driver (D-41), and this keeps the audit write beside apply_post_validation_ddl's identical connection-lifecycle pattern it copies."
  - "The non-spatial NOT_APPLICABLE sentinel (evidence.NOT_APPLICABLE, an in-process string) is translated to SQL NULL for srid/geometry_type/repaired_count when validation.spatial is False -- the durable row uses the table's own nullable columns (D-69), never leaking the in-process sentinel string into the database."
  - "Idempotency is ON CONFLICT DO NOTHING on the table's existing (run_ts, manifest_digest, target_table) primary key (04-02), not a pre-check SELECT -- a repeated back-fill (re-running Phase 3 staging over the same manifest) silently no-ops rather than raising a raw duplicate-key error."
  - "manifest_digest is placed directly above read_manifest in manifest.py and documented as a thin read that must never substitute for read_manifest's full verification -- callers needing manifest content still call read_manifest first."

patterns-established:
  - "AuditValidationRecordTest (tests/test_staging.py) -- the live-DB test pattern for a plan that both back-fills an existing 04-02-provisioned table and never drops it if already present, only ever creating it (and only then dropping it) when its own setUp had to create it first, and always scoping row cleanup to a per-process-unique key."

requirements-completed: [PUB-01, EVID-01]

coverage:
  - id: D1
    description: "manifest.manifest_digest(run_directory) returns the same 64-hex digest read_manifest verified for that run directory, raising ManifestUnreadable on a missing or malformed sidecar (never reading manifest.json itself)"
    requirement: EVID-01
    verification:
      - kind: unit
        ref: "tests/test_manifest.py#ManifestDigestTest.test_matches_the_digest_write_manifest_returned"
        status: pass
      - kind: unit
        ref: "tests/test_manifest.py#ManifestDigestTest.test_matches_read_manifest_own_verified_digest"
        status: pass
      - kind: unit
        ref: "tests/test_manifest.py#ManifestDigestTest.test_missing_sidecar_raises_manifest_unreadable"
        status: pass
      - kind: unit
        ref: "tests/test_manifest.py#ManifestDigestTest.test_truncated_sidecar_raises_manifest_unreadable"
        status: pass
      - kind: unit
        ref: "tests/test_manifest.py#ManifestDigestTest.test_does_not_read_manifest_json_itself"
        status: pass
    human_judgment: false
  - id: D2
    description: "record_validation composes vicmap_audit.staging_validation via sql.Identifier plus bind parameters only (no string-formatted SQL), and exposes AuditPrivilegeDenied/AuditRecordFailed with the exact db_audit_privilege_denied/db_audit_record_failed codes 04-01 reserved"
    requirement: PUB-01
    verification:
      - kind: unit
        ref: "python -c contract check: record_validation source contains 'staging_validation' and bind-parameter syntax; AuditPrivilegeDenied/AuditRecordFailed subclass StagingFailure with the exact codes (plan Task 1 verify command)"
        status: pass
    human_judgment: false
  - id: D3
    description: "record_validation durably writes one PASS row per layer into the real vicmap_audit.staging_validation table, keyed by (run_ts, manifest_digest, target_table), reads back correctly, is idempotent on a repeated call for the same key, writes NULL for the non-spatial fields on a non-spatial layer, and raises AuditPrivilegeDenied when the connecting role lacks INSERT"
    requirement: PUB-01
    verification:
      - kind: integration
        ref: "tests/test_staging.py#AuditValidationRecordTest (4 tests: write+read-back, idempotent repeat, non-spatial NULLs, privilege-denied)"
        status: unknown
    human_judgment: true
    rationale: "This plan is code-only per the operator's explicit instruction (no live database, superuser access, or 1Password secrets available in this session). AuditValidationRecordTest skips cleanly without VICMAP_TEST_POSTGRES_SUPERUSER_DSN -- it has never been run against a live server, so its status cannot be asserted pass here. Logged as WINDOWS.md #8 (kind: unrun-verify). Resume: set VICMAP_TEST_POSTGRES_DSN and VICMAP_TEST_POSTGRES_SUPERUSER_DSN (after 04-02's db/provision_vicmap_loader.sql has been run once by the operator) and re-run `nix develop path:. -c python -m unittest tests.test_staging.AuditValidationRecordTest -v`."
  - id: D4
    description: "stage_order.py's main() calls staging.record_validation once per manifest layer, zipping manifest.layers with run_staging's returned validations, only after run_staging returns without raising, and before returning 0; a failed run_staging leaves the audit table untouched and exits non-zero via the existing StagingFailure/SafeFailure path"
    requirement: PUB-01
    verification:
      - kind: unit
        ref: "python -c contract check: record_validation/manifest_digest referenced in stage_order.main, and run_staging is called before record_validation in source order (plan Task 2 verify command)"
        status: pass
      - kind: unit
        ref: "tests/test_staging.py#StageOrderAuditBackfillTest.test_success_path_records_one_row_per_layer_after_run_staging"
        status: pass
      - kind: unit
        ref: "tests/test_staging.py#StageOrderAuditBackfillTest.test_failed_run_staging_records_nothing_and_exits_nonzero"
        status: pass
      - kind: unit
        ref: "tests/test_staging.py#StageOrderAuditBackfillTest.test_audit_record_failure_after_a_successful_run_exits_nonzero"
        status: pass
    human_judgment: false

duration: ~35min
completed: 2026-09-23
status: complete
---

# Phase 04 Plan 03: Persist and Back-fill the Phase 3 Validation PASS Record Summary

**Added `manifest.manifest_digest` (a thin, verified sidecar read) and `staging.record_validation` (a driver-isolated, idempotent PASS-row writer into 04-02's `vicmap_audit.staging_validation`), then wired `stage_order.py` to call it once per layer only after a fully validated `run_staging` returns — closing the D-68 cross-phase handoff gap so the Phase 4 publish gate (04-04) will have a durable record to trust.**

This plan is code-only per the operator's explicit instruction: no live PostgreSQL database, superuser access, or 1Password/env secrets were available or used in this session. Every fully offline-verifiable claim (contract shape, safe-SQL composition, digest agreement, the success/failure wiring in `stage_order.py`) was proven with a passing automated test in this session. The one genuinely live-dependent fact — `record_validation` actually writing to and reading back from a real `vicmap_audit.staging_validation` table — is written, tested, and structurally sound, but its test class (`AuditValidationRecordTest`) has never executed against a live server; see "Deferred to Operator / Live" below.

## Performance

- **Duration:** ~35 min
- **Tasks:** 2/2 completed
- **Files modified:** 5 (`vicmap_acquire/manifest.py`, `vicmap_acquire/staging.py`, `stage_order.py`, `tests/test_manifest.py`, `tests/test_staging.py`)
- **Tests:** 548 in the full `tests` suite (up from 534 baseline: +7 `ManifestDigestTest`, +4 `AuditValidationRecordTest` (all skip, no live DSN), +3 `StageOrderAuditBackfillTest`), all passing, 36 skipped (up from 32 — the 4 new live audit-record tests correctly join the existing live-DB-only skip set)

## Accomplishments

- `manifest.manifest_digest(run_directory)` reads `manifest.json.sha256` directly, validates its shape against the existing `_SIDECAR_DIGEST` pattern, and returns exactly the digest `read_manifest` already verifies for that run directory — proven to agree with both `write_manifest`'s own return value and an independent SHA-256 oracle recomputed over `manifest.json`'s bytes, and proven to never need `manifest.json` to exist (a thin sidecar read, not a re-verification).
- `staging.record_validation(policy, password, *, run_timestamp, manifest_digest, target_table, validation)` opens one connection (reusing `apply_post_validation_ddl`'s exact lifecycle) and inserts one row into `vicmap_audit.staging_validation` with `verdict='pass'` and the D-56 metrics from the layer's `LayerValidation`, composed entirely via `sql.Identifier`/bind parameters. A non-spatial layer's `srid`/`geometry_type`/`repaired_count` are written as SQL `NULL` (the table's own nullable columns), not the in-process `NOT_APPLICABLE` sentinel string. `ON CONFLICT DO NOTHING` on the table's existing `(run_ts, manifest_digest, target_table)` primary key makes a repeated call idempotent rather than raising a raw duplicate-key error.
- Two new closed `StagingFailure` subclasses — `AuditPrivilegeDenied` (`db_audit_privilege_denied`) and `AuditRecordFailed` (`db_audit_record_failed`) — map exactly to the `ReasonCode` values 04-01 already reserved; `AuditPrivilegeDenied` is raised specifically on `psycopg.errors.InsufficientPrivilege`, `AuditRecordFailed` on any other write failure. Neither carries driver or SQL text.
- `stage_order.py`'s `main()` now captures `run_staging`'s returned `tuple[LayerValidation, ...]`, computes `manifest_digest(run_directory)`, and calls `record_validation` once per layer (zipping `manifest.layers` with the returned validations in `run_staging`'s preserved order) — placed after `run_staging` returns without raising and before the function's final `return 0`. A failed `run_staging` call raises before this code is ever reached, so a failed layer leaves no audit row (T-04-06); `AuditPrivilegeDenied`/`AuditRecordFailed` are routed through the existing `except staging.StagingFailure` handler unchanged, rendering as closed `SafeFailure` lines with a non-zero exit.
- New `tests/test_manifest.py::ManifestDigestTest` (7 tests, all pass, no database) proves `manifest_digest`'s contract in isolation. New `tests/test_staging.py::AuditValidationRecordTest` (4 tests, live-DB, skip cleanly without `VICMAP_TEST_POSTGRES_SUPERUSER_DSN`) proves the real write/read-back/idempotency/non-spatial-NULL/privilege-denied behavior against a real `vicmap_audit.staging_validation` table — creating that schema/table only if absent, never dropping a pre-existing operator-provisioned one, and scoping all cleanup to a per-process-unique `run_ts` key. New `tests/test_staging.py::StageOrderAuditBackfillTest` (3 tests, all pass, no database) proves `stage_order.main`'s success/failure wiring by mocking every boundary below `run_staging`/`record_validation`.

## Task Commits

Each task was committed atomically:

1. **Task 1: Persist one PASS validation row end-to-end and read it back** - `f9282f7` (feat)
2. **Task 2: Write the audit rows from stage_order.py after a full validated run** - `ef93d78` (feat)

**Plan metadata:** commit pending (SUMMARY.md docs commit, made by this executor's `<final_commit>` step)

## Files Created/Modified

- `vicmap_acquire/manifest.py` - adds `manifest_digest(run_directory) -> str`, a thin `ManifestUnreadable`-guarded sidecar read
- `vicmap_acquire/staging.py` - adds `record_validation`, `AuditPrivilegeDenied`, `AuditRecordFailed`
- `stage_order.py` - imports `manifest_digest`; `main()` captures `run_staging`'s return value and calls `record_validation` per layer after a successful run, before returning 0
- `tests/test_manifest.py` - adds `ManifestDigestTest` (7 tests)
- `tests/test_staging.py` - imports `stage_order`; adds `AuditValidationRecordTest` (4 live-DB tests) and `StageOrderAuditBackfillTest` (3 tests)

## Decisions Made

- `record_validation` lives in `staging.py` (the one driver-importing module, D-41) rather than a new module, reusing `apply_post_validation_ddl`'s exact connection lifecycle rather than inventing a new one.
- The non-spatial `NOT_APPLICABLE` in-process sentinel is translated to SQL `NULL` at the `record_validation` boundary — the durable row never carries the string `"not_applicable"`, only real `NULL`s in the table's nullable columns.
- Idempotency is `ON CONFLICT DO NOTHING` on the natural composite primary key 04-02 already provisioned, not a pre-check `SELECT` — matches the plan's explicit "ON CONFLICT DO NOTHING is acceptable" guidance.
- `manifest_digest` is documented and tested as strictly a thin read: it must never substitute for `read_manifest`'s full verification, and any caller needing the manifest's actual content still calls `read_manifest` first (proven by a test that deletes `manifest.json` and confirms `manifest_digest` is unaffected).

## Deviations from Plan

None - plan executed exactly as written. Every task's `<action>` and `<verify>` commands ran without modification and passed on the first attempt.

## Issues Encountered

None. The one adaptation was mechanical, not a deviation: `tests/test_staging.py`'s two new test classes (`AuditValidationRecordTest` for Task 1, `StageOrderAuditBackfillTest` for Task 2) share one file, so the file's edits were applied and committed in two passes (Task 1's portion first, then Task 2's `import stage_order` line and its test class) to keep each task's commit scoped to exactly its own `<files>` list — no code or test content differs from a single-pass edit.

## Deferred to Operator / Live

This plan is code-only per the operator's explicit instruction; the following is deferred and was **not** performed by this executor:

1. **Run `AuditValidationRecordTest` against a live PostgreSQL server.**
   - **What:** Proves `record_validation` durably writes one PASS row to the real `vicmap_audit.staging_validation` table, reads it back correctly, is idempotent on a repeated call, writes `NULL` for the non-spatial fields on a non-spatial layer, and raises `AuditPrivilegeDenied` when the connecting role's `INSERT` grant is revoked. Depends on 04-02's deferred operator steps (the 1Password `VICMAP_READER_PASSWORD` item and running `db/provision_vicmap_loader.sql` as superuser) having completed first, since the test needs a reachable ordinary connection plus a superuser connection.
   - **Resume:** `VICMAP_TEST_POSTGRES_DSN=<ordinary-role-dsn> VICMAP_TEST_POSTGRES_SUPERUSER_DSN=<superuser-dsn> nix develop path:. -c python -m unittest tests.test_staging.AuditValidationRecordTest -v`. Logged as `WINDOWS.md` entry #8 (`kind: unrun-verify`), owned by this deferred step.

2. **Re-run Phase 3 staging (`stage_order.py`) against the proof delivery once the operator's live database is reachable.**
   - **What:** Populates the real `vicmap_audit.staging_validation` table with the actual PASS row(s) for the `VMADD.gdb`/`ADDRESS` proof delivery — the record 04-04's publish gate will read.
   - **Resume:** `VICMAP_DB_PASSWORD=<value> nix develop path:. -c python stage_order.py --config vicmap.toml` (after 04-02's provisioning script has run and the 1Password items exist). No code change is needed for this — `stage_order.py`'s wiring is already code-complete and tested above.

Neither step was attempted, simulated, or partially run against any database in this session. `tests/test_manifest.py::ManifestDigestTest` and `tests/test_staging.py::StageOrderAuditBackfillTest` prove the fully offline-provable contract is correct and internally consistent without requiring either operator step to complete first.

## User Setup Required

See "Deferred to Operator / Live" above — this plan names no new `user_setup` step of its own; it depends on 04-02's already-recorded two operator steps (1Password item + running the provisioning script) before its own live verification (item 1 above) can run.

## Next Phase Readiness

- `vicmap_audit.staging_validation` now has a code-complete, offline-tested writer (`record_validation`) and a real call site (`stage_order.py`) that persists exactly one PASS row per layer only after a fully validated run — 04-04's publish gate can be built against this contract now, reading the same table by the same `(run_ts, manifest_digest, target_table)` key `record_validation` writes.
- `manifest_digest` gives 04-04 (the publish gate) and any later phase needing the frozen digest a cheap, already-tested way to obtain it without re-parsing the whole manifest.
- `tests/test_staging.py::DriverImportPolicyTest` was reconfirmed passing as part of the full-suite run — `stage_order.py` (this plan's other touched file) imports no driver; only `staging.py` does, unchanged.
- The one live gap (item 1 above, `WINDOWS.md` #8) blocks 04-04's live verification specifically, not its code — 04-04 can be planned and implemented code-only against this plan's tested contract, with its own live gate read deferred the same way this plan's live write was.

---
*Phase: 04-transactional-publication-and-access*
*Completed: 2026-09-23*

## Self-Check: PASSED

All 5 modified files (`vicmap_acquire/manifest.py`, `vicmap_acquire/staging.py`, `stage_order.py`, `tests/test_manifest.py`, `tests/test_staging.py`) and this SUMMARY.md confirmed present on disk. Both task commits (`f9282f7`, `ef93d78`) confirmed present in `git log`.
