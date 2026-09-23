---
phase: 04-transactional-publication-and-access
plan: 04
subsystem: database
tags: [postgres, postgis, psycopg, ddl, transaction, publication, grant, catalog-discovery]

# Dependency graph
requires:
  - phase: 04-01
    provides: evidence.py publication Stage/ReasonCode vocabulary (DB_PUBLISH, DB_READER_VERIFY, PUB_VALIDATION_MISSING, PUB_PROMOTION_FAILED, DB_AUDIT_PRIVILEGE_DENIED)
  - phase: 04-02
    provides: reader_user config key (vicmap.toml) and the vicmap_reader LOGIN role / VICMAP_READER_PASSWORD provisioning wiring
  - phase: 04-03
    provides: vicmap_audit.staging_validation table + record_validation back-fill writing the PASS rows the D-68 gate reads; manifest_digest helper
provides:
  - vicmap_acquire/publish.py — the second (and only other) driver-isolated module (D-41 extended)
  - PublishPolicy (frozen, up-front-validated; adds reader_user over StagingPolicy)
  - promote_order — one-transaction, commit-or-rollback atomic promotion (D-66/D-67/D-71/D-73)
  - assert_all_layers_validated — the D-68 PASS gate that hard-stops before any DDL (PUB-01)
  - catalog-driven canonical renaming (pg_constraint contype in p,n + pg_attribute/conkey; pg_indexes) — version-agnostic across PG17/18
  - PublishFailure closed hierarchy (PromotionFailed, PublicationValidationMissing)
affects: [04-05, 04-06, publish_order.py, reader-verification, summary-assembly]

# Actuals
actuals:
  tokens: 10200
  tasks: 2
  commits: 2

plan_head_before: 2815d14c51f25eaabc5f8dbb0692a39d58c341fb

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Driver-isolated sibling module (publish.py) — the closed {staging.py, publish.py} driver-exemption pair"
    - "Catalog-discovery of object names at promotion time (Pattern 1), never string-derived"
    - "Single-connection / single-transaction promotion mirroring apply_post_validation_ddl (Pattern 2)"
    - "Read-only pre-DDL gate on its own short-lived connection (fail-closed)"

key-files:
  created:
    - vicmap_acquire/publish.py
    - tests/test_publish.py
  modified:
    - tests/test_staging.py

key-decisions:
  - "Module layout: sibling publish.py (research option B) — DriverImportPolicyTest exemption widened to a closed {staging.py, publish.py} set in the same commit as the psycopg import (Pitfall 5)"
  - "Canonical index naming is uniform {target}_{column}_idx (geom index becomes {target}_geom_idx), resolved from pg_index/pg_attribute via pg_indexes — the PK's backing index is renamed implicitly by RENAME CONSTRAINT and excluded (NOT indisprimary)"
  - "NOT NULL constraints discovered with contype IN ('p','n') and the column resolved from conkey[1] via pg_attribute — a no-op on PG17, canonical rename on PG18, no version branch"
  - "SELECT version() is the first statement of the promotion transaction (Open Q1); the D-68 gate is a read-only preflight on a separate connection before it"

patterns-established:
  - "PublishPolicy adds reader_user and re-checks reader_user != loader (T-04-09)"
  - "Offline SQL-composition testing via a recording fake cursor (query.as_string(None)), mirroring ConnectionSetupTest"

requirements-completed: []  # PUB-01..04 are CODE-COMPLETE + offline-verified; live closure is DEFERRED to the operator's live promotion run (one-way door) — see Deferred section

# Coverage
coverage:
  - id: D1
    description: "publish.py is a driver-isolated module and DriverImportPolicyTest exemption is the closed {staging.py, publish.py} set"
    verification:
      - kind: unit
        ref: "tests/test_staging.py::DriverImportPolicyTest.test_staging_is_the_only_module_referencing_a_database_driver"
        status: pass
    human_judgment: false
  - id: D2
    description: "PublishPolicy validates types/ranges, rejects public schemas, staging==publish, and reader==loader"
    verification:
      - kind: unit
        ref: "tests/test_publish.py::PublishPolicyValidationTest"
        status: pass
    human_judgment: false
  - id: D3
    description: "Promotion SQL is composed correctly: version()-first, single scoped DROP TABLE IF EXISTS (no wildcard/cascade), two-statement SET SCHEMA + RENAME, canonical catalog-discovered pk/NOT-NULL/index renames, in-transaction reader GRANT, rollback-and-PromotionFailed on error"
    verification:
      - kind: unit
        ref: "tests/test_publish.py::PromotionCompositionTest, PromotionRollbackCompositionTest"
        status: pass
    human_judgment: false
  - id: D4
    description: "The D-68 gate logic hard-stops (PublicationValidationMissing) unless every layer has a PASS audit row, runs no DDL when it fails, and maps an unreadable audit table to AuditPrivilegeDenied"
    requirement: "PUB-01"
    verification:
      - kind: unit
        ref: "tests/test_publish.py::PublicationGateTest"
        status: pass
    human_judgment: false
  - id: D5
    description: "LIVE atomic promotion of a PASS-gated order into vicmap: all layers commit together, an induced failure preserves every prior table, canonical names materialize on the real PG server, and the reader holds SELECT (PUB-01/PUB-02/PUB-03/PUB-04)"
    requirement: "PUB-02"
    verification: []
    human_judgment: true
    rationale: "One-way-door live DB mutation. Requires operator-provisioned vicmap_audit schema, vicmap_reader role + VICMAP_READER_PASSWORD, a staged run, and explicit approval of the checkpoint:decision. Not performed in this code-only run; live tests are written but skip without VICMAP_TEST_POSTGRES_DSN/SUPERUSER_DSN."

# Metrics
duration: 12min
completed: 2026-09-23
status: complete
---

# Phase 4 Plan 04: Transactional Publication into vicmap Summary

**Driver-isolated `publish.py` with a D-68 PASS gate and a catalog-driven, single-transaction atomic promotion (drop-prior / SET SCHEMA / RENAME / canonical-rename / in-transaction reader GRANT), version-agnostic across PostgreSQL 17/18 — code-complete and offline-verified; the one-way-door live promotion is deferred to the operator.**

## Performance

- **Duration:** ~12 min
- **Started:** 2026-09-23T04:32:53Z
- **Completed:** 2026-09-23T04:44:32Z
- **Tasks:** 2 of 2 code tasks (the leading `checkpoint:decision` and the live promotion are deferred to the operator)
- **Files modified:** 3 (2 created, 1 modified)

## Accomplishments

- Added `vicmap_acquire/publish.py` — the second and only other driver-permitted module (D-41 extended) — with `PublishPolicy`, `promote_order`, `assert_all_layers_validated`, and the closed `PublishFailure` hierarchy.
- `promote_order` runs the whole order's promotion inside one connection's single transaction: `SELECT version()` first (Open Q1), then per layer a single scoped `DROP TABLE IF EXISTS vicmap.{target}` (no wildcard, no cascade — D-71/Pitfall 4/PROHIB-10), the two-statement `SET SCHEMA` + `RENAME` metadata move (D-66), canonical renames of the pk/NOT-NULL/index objects discovered from the catalog (D-67/Pattern 1), and an in-transaction `GRANT SELECT` to the reader (D-73); one `commit()` or a full `rollback()` and `PromotionFailed`.
- Name discovery is version-agnostic: `pg_constraint` with `contype IN ('p','n')` and the NOT NULL column resolved from `conkey[1]` via `pg_attribute` (Pitfall 2 — a no-op on PG17, a canonical rename on PG18, no version branch); indexes via `pg_indexes` joined to `pg_index`/`pg_attribute`, excluding the PK's backing index.
- `assert_all_layers_validated` implements the D-68 gate exactly (SELECT PASS rows for the run+digest; required set must be a subset), hard-stops with `PublicationValidationMissing` before any DDL, and maps an unreadable audit table to `AuditPrivilegeDenied`.
- Widened `DriverImportPolicyTest`'s exemption to the closed `{staging.py, publish.py}` set **in the same commit** that added `publish.py`'s `import psycopg` (Pitfall 5) — the previously-green test stays green.

## Task Commits

Each task was committed atomically:

1. **Task 1 (tracer): Promote one validated layer into vicmap end-to-end** - `04ab670` (feat)
2. **Task 2: All-or-nothing, previous-preserving, gate-hardened promotion** - `0b36cdc` (feat)

_The leading `checkpoint:decision` was not executed (see Deferred). The tracer feedback gate (which normally re-verifies end-to-end) could not run live; only offline composition/assertion verification was performed._

## Files Created/Modified

- `vicmap_acquire/publish.py` - The publication boundary: `PublishPolicy`, `_connect`, the D-68 gate, `promote_order`, catalog-discovery helpers, and the closed `PublishFailure` hierarchy.
- `tests/test_publish.py` - Offline policy-validation, SQL-composition, rollback, and gate tests (all run); live single-layer/multi-layer/rollback tests that skip cleanly without a DSN.
- `tests/test_staging.py` - `DriverImportPolicyTest` exemption widened to `{staging.py, publish.py}`.

## Offline Verification (performed this run)

All commands run via `nix develop path:. -c ...`:

- `python -m unittest tests.test_staging.DriverImportPolicyTest -v` → **OK** (2 tests; exemption widened, publish.py not flagged).
- Task 1 publish-contract inline check → **`publish contract ok`** (version()-first, catalog discovery, scoped drop, no cascade drop, closed codes).
- Task 2 atomicity+gate inline check → **`atomicity+gate contract ok`** (gate present, contype 'n' + conkey/pg_attribute discovery, rollback + commit).
- `python -m unittest tests.test_publish -v` → **OK, 28 tests, 3 skipped** (the 3 live-DB tests skip without a DSN; the offline gate/composition/policy tests all run and pass).
- Combined `tests.test_publish tests.test_staging.DriverImportPolicyTest` → **OK, 30 tests, 3 skipped**.
- Regression: `tests.test_staging tests.test_evidence` → **OK** (no regressions from the exemption change).

## Decisions Made

- **Sibling module (research option B)** over growing `staging.py`, keeping Phase 3/Phase 4 concerns separate while the driver-isolation guarantee still holds and is still tested.
- **Uniform canonical index naming** `{target}_{column}_idx` (so the GiST geom index → `{target}_geom_idx`), with the indexed column resolved authoritatively from the catalog rather than parsing `indexdef` text.
- **`pg_indexes` as the index-discovery entry point** joined to `pg_index`/`pg_attribute` — satisfies the "discover from the catalog" contract and resolves each index's column without string derivation.
- **Connection-failure mapping:** `_connect` maps any driver connect/setup error to the closed `PromotionFailed` (publish has no separate connection-failed code); the gate maps a refused audit read to the shared `AuditPrivilegeDenied` (04-01 code).

## Deviations from Plan

None - plan executed exactly as written, within the code-only boundary set by this run.

One in-task correction worth noting (not a plan deviation): the Task 1 `<verify>` regex `DROP\s+TABLE[^;]*\bCASCADE\b` is case-sensitive and `[^;]` spans newlines, so an early draft's docstring prose ("no ``CASCADE``") tripped it as a false positive. Reworded the two prose mentions to lowercase "cascade"/"cascade modifier" (the composed SQL never contained CASCADE); the check then passed. No behavior change.

## Issues Encountered

- The devshell prints an opnix error resolving `VICMAP_READER_PASSWORD` (`op://nixos-services/vicmap_reader_credentials/password` → itemNotFound). This is the **anticipated D-74 operator-setup gap** (the reader secret 1Password item does not exist yet), not a test failure — all offline tests pass regardless because they never materialize that secret. Documented under Deferred below.

## DEFERRED — live / operator (one-way door)

This was a **code-only run**. The following were intentionally NOT performed and are deferred to the operator, exactly as the run mandate requires.

### The one-way-door decision the operator must approve (verbatim from 04-04-PLAN.md Task 0)

> **Decision:** Before writing promotion code, confirm the published-table contract: promotion is a metadata move (ALTER TABLE SET SCHEMA + RENAME, no row copy), the live table keeps the canonical name from the manifest's `target_table` (e.g. `vmadd_address`) with canonical index/constraint names (`{table}_pkey`, `{table}_geom_idx`, `{table}_geom_not_null`, `{table}_{col}_idx`), a single live generation is kept (the prior `vicmap.{table}` is dropped in the same transaction, D-71), and the reader is granted SELECT in that same transaction (D-73).
>
> **Options:** (1) Proceed exactly as specified by D-66/D-67/D-71/D-73 (recommended — the locked decision set). (2) Adjust the canonical naming scheme or retention (would revise D-67/D-71 and must be re-agreed before coding).
>
> **Default:** Proceed as specified by the locked decisions.
>
> **Resume-signal:** Operator confirms the published-table contract — reply "proceed" to continue, or state the adjustment to re-agree before coding.

The code was written against option 1 (the locked, default contract). If the operator instead chooses option 2, the canonical-naming/retention code in `_promote_layer` must be revised before the live promotion.

### What is deferred and why

- **The `checkpoint:decision` itself** — not auto-approvable; a one-way published-table contract binding every downstream QGIS project/saved query. Operator must explicitly approve.
- **The live atomic promotion / any live DB mutation** — `promote_order` was never run against the live server; no `vicmap.*` table was created, dropped, renamed, or granted.
- **The live proofs of PUB-01/PUB-02/PUB-03/PUB-04** — the multi-layer commit-together, the induced-failure rollback, and the reader-grant behavior are covered by live tests in `tests/test_publish.py` that **skip** without a test DSN (never fail); they must be run against the live DB.

### Exact resume steps (operator)

1. **Provision the reader secret + roles/schema** (still outstanding — see Issues): create the 1Password item `op://nixos-services/vicmap_reader_credentials/password`, then run `db/provision_vicmap_loader.sql` as superuser (creates `vicmap_audit` schema + `staging_validation`, grants the loader SELECT/INSERT, creates the `vicmap_reader` LOGIN role with `USAGE ON SCHEMA vicmap`). Confirm `VICMAP_READER_PASSWORD` resolves in the devshell.
2. **Stage a validated run** (04-03): run `stage_order.py` so `vicmap_audit.staging_validation` holds a PASS row per layer for the run's `(run_ts, manifest_digest)`.
3. **Approve the one-way-door decision** above (reply "proceed").
4. **Perform the live promotion** by wiring `publish.promote_order(manifest, policy, password, run_timestamp, manifest_digest)` into the publish flow (the `publish_order.py` CLI is a later plan, 04-05/04-06) — or, to prove this plan's slice directly, run the live tests with the DSNs set: `VICMAP_TEST_POSTGRES_DSN=... VICMAP_TEST_POSTGRES_SUPERUSER_DSN=... nix develop path:. -c python -m unittest tests.test_publish -v` (the 3 currently-skipped `Live*` tests will exercise the real promotion once their fixtures are completed against the provisioned schema/role).

## Known Stubs

- `tests/test_publish.py::LivePromoteOneLayerTest`, `LiveMultiLayerPromotionTest`, `LivePromotionRollbackTest` — the live fixture bodies are `skipTest`-guarded placeholders (they require the operator-provisioned schema/role/staged run described above). They skip cleanly offline and must be fleshed out and run against the live DB during the operator's promotion. Logged to WINDOWS.md as unrun-verify entries.

## Next Phase Readiness

- `publish.promote_order` and the D-68 gate are ready to be driven by the `publish_order.py` CLI (D-77) and to feed the EVID-01 summary (`PromotionResult` surfaces the live `version()` and the published table list).
- **Blocker for the live milestone proof:** operator setup (reader secret + provisioning script run) plus approval of the one-way-door decision, then the live promotion + reader verification (04-05/04-06).

## Self-Check: PASSED

---
*Phase: 04-transactional-publication-and-access*
*Completed: 2026-09-23*
