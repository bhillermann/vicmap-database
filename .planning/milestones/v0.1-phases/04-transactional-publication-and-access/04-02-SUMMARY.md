---
phase: 04-transactional-publication-and-access
plan: 02
subsystem: database-config-and-provisioning
tags: [reader-role, least-privilege, audit-gate, opnix, provisioning]

# Dependency graph
requires:
  - phase: 04-transactional-publication-and-access
    plan: 01
    provides: the Stage.DB_AUDIT/DB_PUBLISH/DB_READER_VERIFY vocabulary this plan's provisioning targets, referenced by name in the SQL comments and SUMMARY
  - phase: 03-validated-postgis-staging
    provides: "[database] section shape, _PG_IDENTIFIER/_FORBIDDEN_SCHEMA_NAMES validators, and the db/provision_vicmap_loader.sql D-60 by-hand superuser script this plan widens"
provides:
  - "reader_user: str on DatabaseRunConfig -- a validated, reviewable non-secret config value every later Phase 4 plan (04-04 GRANT target, 04-05 reader login) resolves to"
  - "vicmap_audit.staging_validation table contract (run_ts, manifest_digest, target_table, staging_table, verdict, spatial, row_count, srid, geometry_type, repaired_count, recorded_at) -- the single source 04-03's back-fill writer and 04-04's publish gate reader agree on"
  - "vicmap_reader LOGIN role name (provisioning-script-side) that 04-04's per-publish GRANT SELECT and 04-05's reader-login verification both target"
  - VICMAP_READER_PASSWORD opnix wiring (code-complete; the 1Password item itself is operator-deferred)
affects: [04-03, 04-04, 04-05, 04-06]

# Actuals (#2632)
actuals:
  tokens: 3472
  tasks: 3
  commits: 3
plan_head_before: f48e86fdd7c094c9bc61e4f5200ad90a72efe2de

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Config-key widening follows the existing fail-closed shape: _DATABASE_KEYS set equality, _strict_string extraction, then one semantic validator (validate_database_policy) checked for identifier format, forbidden names, and cross-field relationships -- no new pattern introduced."
    - "Provisioning-script structural testing: tests/test_staging.py::ProvisionScriptTest reads db/provision_vicmap_loader.sql as text and asserts the audit table/grants/role exist with regex-checked least-privilege boundaries, without ever connecting to a database -- mirrors the existing offline DatabaseConfigTest shape for a SQL file instead of a TOML file."

key-files:
  created: []
  modified:
    - read_mailbox.py
    - vicmap.toml
    - db/provision_vicmap_loader.sql
    - flake.nix
    - tests/test_staging.py

key-decisions:
  - "reader_user landed as a new key inside the existing [database] section (not a new [reader] section), per CONTEXT.md's explicit Claude's-discretion note -- keeps the reader-role name reviewable alongside the loader's own identifier fields rather than fragmenting the non-secret policy across more sections."
  - "validate_database_policy's identifier loop and _FORBIDDEN_SCHEMA_NAMES check both widened to include reader_user, plus one new explicit reader_user == config.user rejection (T-04-09) -- reuses every existing check exactly rather than duplicating validation logic for the new field."
  - "vicmap_audit schema is CREATE SCHEMA ... AUTHORIZATION CURRENT_USER (owned by whichever superuser runs the script), NOT vicmap_loader -- research Open Question 2's tighter least-privilege model, closing T-04-08: the loader gets SELECT+INSERT on the one table inside it, never CREATE on the schema, so the gate record's shape cannot be silently altered by the pipeline that writes to it."
  - "vicmap_reader is granted USAGE ON SCHEMA vicmap only in this script -- no CREATE, no table privileges. Per-table SELECT is explicitly deferred to 04-04's in-transaction GRANT (D-73), not granted here."
  - "1Password item path chosen as op://nixos-services/vicmap_reader_credentials/password, exactly parallel to vicmap_loader_credentials, keeping the two credential items structurally identical for the operator."

patterns-established:
  - "ProvisionScriptTest (new test class) -- the offline, text-only counterpart to the runtime preflight checks staging.py performs live; future provisioning-script changes should extend this class rather than only updating the paste-in psql comment block."

requirements-completed: []

coverage:
  - id: D1
    description: "load_database_config reads a vicmap.toml carrying the reader-role name and returns a DatabaseRunConfig whose reader_user is a validated PostgreSQL identifier (D-72)"
    requirement: PUB-04
    verification:
      - kind: unit
        ref: "tests/test_staging.py#DatabaseConfigTest.test_happy_path_loads_every_field"
        status: pass
      - kind: automated
        ref: "python -c \"... c.reader_user=='vicmap_reader' ...\" (plan Task 1 verify command)"
        status: pass
    human_judgment: false
  - id: D2
    description: "validate_database_policy rejects a missing, malformed, or public reader_user before any connection is opened, failing closed with config_invalid"
    requirement: PUB-04
    verification:
      - kind: unit
        ref: "tests/test_staging.py#DatabaseConfigTest.test_reader_user_malformed_identifier_rejected"
        status: pass
      - kind: unit
        ref: "tests/test_staging.py#DatabaseConfigTest.test_reader_user_is_public"
        status: pass
      - kind: unit
        ref: "tests/test_staging.py#DatabaseConfigTest.test_reader_user_equals_loader_user"
        status: pass
      - kind: unit
        ref: "tests/test_staging.py#DatabaseConfigTest.test_missing_each_database_key_in_turn"
        status: pass
    human_judgment: false
  - id: D3
    description: "db/provision_vicmap_loader.sql, when run once by a superuser, creates the vicmap_audit schema and staging_validation table (loader granted SELECT+INSERT only, not schema CREATE) and the vicmap_reader LOGIN role with USAGE ON SCHEMA vicmap and no write privilege (D-70/D-72)"
    requirement: PUB-04
    verification:
      - kind: unit
        ref: "tests/test_staging.py#ProvisionScriptTest.test_audit_schema_and_table_created"
        status: pass
      - kind: unit
        ref: "tests/test_staging.py#ProvisionScriptTest.test_loader_granted_select_insert_only_on_audit_table"
        status: pass
      - kind: unit
        ref: "tests/test_staging.py#ProvisionScriptTest.test_reader_role_is_login_with_schema_usage_only"
        status: pass
      - kind: unit
        ref: "tests/test_staging.py#ProvisionScriptTest.test_reader_role_name_matches_configured_reader_user"
        status: pass
      - kind: live
        ref: "psql -f db/provision_vicmap_loader.sql -d vicmap, run once by the operator (deferred -- see below)"
        status: deferred
    human_judgment: false
  - id: D4
    description: "flake.nix injects VICMAP_READER_PASSWORD via opnix from a 1Password reference, never from vicmap.toml or argv (D-74/D-58)"
    requirement: PUB-05
    verification:
      - kind: automated
        ref: "python -c \"... 'VICMAP_READER_PASSWORD' in s and 'op://nixos-services/vicmap_reader_credentials/password' in s ...\" (plan Task 3 verify command)"
        status: pass
      - kind: automated
        ref: "nix develop path:. -c python -c \"print('nix flake evaluates in dev shell')\" (dev shell still evaluates with the item absent)"
        status: pass
      - kind: live
        ref: "opnix successfully resolving VICMAP_READER_PASSWORD at shell entry, requires the 1Password item to exist (deferred -- see below)"
        status: deferred
    human_judgment: false

duration: ~20min
completed: 2026-09-23
status: complete
---

# Phase 04 Plan 02: Reader-Role Config Contract and Provisioning Summary

**Widened `vicmap.toml`'s `[database]` section with a validated `reader_user` key, extended `db/provision_vicmap_loader.sql` with the `vicmap_audit.staging_validation` gate table (superuser-owned, loader append-only) and the `vicmap_reader` LOGIN role (USAGE-only), and wired `VICMAP_READER_PASSWORD` through opnix parallel to `VICMAP_DB_PASSWORD` — 3 tasks, 3 commits, 534 tests green (32 skipped, live-DB only), no live database touched.**

This plan is CODE-ONLY per the operator's explicit instruction: every task's automated `<verify>` command ran and passed without a live PostgreSQL database, superuser access, or 1Password/env secrets. The two genuinely live-dependent facts (running the provisioning script, and opnix successfully resolving the new secret) are deferred to the operator — see "Deferred to Operator / Live" below.

## Performance

- **Duration:** ~20 min
- **Tasks:** 3/3 completed
- **Files modified:** 5 (`read_mailbox.py`, `vicmap.toml`, `db/provision_vicmap_loader.sql`, `flake.nix`, `tests/test_staging.py`)
- **Tests:** 534 in the full `tests` suite (up from 530 baseline: +4 `ProvisionScriptTest` structural tests, +5 `DatabaseConfigTest` reader_user cases, net offset by no removals), all passing, 32 skipped (unchanged — live-DB-only tests, correctly skipping with no `VICMAP_TEST_POSTGRES_DSN`)

## Accomplishments

- `_DATABASE_KEYS`, `DatabaseRunConfig`, `load_database_config`, and `validate_database_policy` all widened to carry and validate `reader_user` — a `[database]` section missing it now fails closed with `config_invalid` (D-72), matching the plan's `key_links` requirement that an existing five-section `vicmap.toml` without the key stops loading until updated.
- `validate_database_policy` rejects `reader_user` that is not a `_PG_IDENTIFIER`, is `public`, or equals the loader (`config.user`) — three new closed-failure cases (T-04-09), each with its own regression test plus a directly-constructed-`DatabaseRunConfig` bypass-the-loader test mirroring the existing `staging_schema`/`publish_schema` pattern.
- `vicmap.toml`'s `[database]` section now ships `reader_user = "vicmap_reader"`; `load_discovery_config` (Phase 1/2 path) reconfirmed unaffected by a new regression test.
- `db/provision_vicmap_loader.sql` extended with: `CREATE SCHEMA IF NOT EXISTS vicmap_audit AUTHORIZATION CURRENT_USER` (superuser-owned, not loader-owned — research Open Question 2's tighter model), `vicmap_audit.staging_validation` with the D-69-required columns and a `(run_ts, manifest_digest, target_table)` primary key, `GRANT USAGE`/`GRANT SELECT, INSERT` to `vicmap_loader` (append-only, no `CREATE`/`UPDATE`/`DELETE`), and `CREATE ROLE vicmap_reader LOGIN PASSWORD 'REPLACE_WITH_1PASSWORD_VALUE'` + `GRANT USAGE ON SCHEMA vicmap TO vicmap_reader` (no `CREATE`, no table privileges — those are 04-04's per-publish grant).
- New `tests/test_staging.py::ProvisionScriptTest` (4 tests) proves the script's structure offline: audit schema/table exist, the loader's grant is exactly `SELECT, INSERT` with no `UPDATE`/`DELETE`, the reader role is `LOGIN` with `USAGE`-only and no `CREATE`/write, and the `CREATE ROLE` name in the SQL literally equals `vicmap.toml`'s configured `reader_user` (the plan's `key_links` requirement, now regression-tested end to end).
- `flake.nix`'s `opnixEnvConfig.vars` gained one entry — `VICMAP_READER_PASSWORD` sourced from `op://nixos-services/vicmap_reader_credentials/password` — placed immediately after `VICMAP_DB_PASSWORD` and commented to match its D-58/D-74 provenance exactly. Confirmed live in this session that the dev shell still evaluates and runs commands even with the 1Password item absent (opnix reports `itemNotFound` on stderr but does not hard-fail shell entry), consistent with this being expected new user-setup work.

## Task Commits

Each task was committed atomically:

1. **Task 1: Thread the reader-role name through the config contract, end-to-end** - `2758cf3` (feat)
2. **Task 2: Provision the vicmap_audit gate table and the least-privilege reader role** - `3b8dc28` (feat)
3. **Task 3: Wire VICMAP_READER_PASSWORD through opnix** - `25c8267` (feat)

**Plan metadata:** commit pending (SUMMARY.md docs commit, made by this executor's `<final_commit>` step)

## Files Created/Modified

- `read_mailbox.py` - `_DATABASE_KEYS` gains `reader_user`; `DatabaseRunConfig` gains a `reader_user: str` field; `load_database_config` extracts it via `_strict_string`; `validate_database_policy` validates it as an identifier, rejects `public`, and rejects equality with `config.user`
- `vicmap.toml` - `[database]` section gains `reader_user = "vicmap_reader"`
- `db/provision_vicmap_loader.sql` - adds the `vicmap_audit` schema, `staging_validation` table, loader `SELECT, INSERT` grant, `vicmap_reader` LOGIN role, and reader `USAGE ON SCHEMA vicmap` grant, plus four new paste-in verification checks in the comment block
- `flake.nix` - adds the `VICMAP_READER_PASSWORD` opnix var entry, parallel to `VICMAP_DB_PASSWORD`
- `tests/test_staging.py` - extends `VALID_TOML`/`_DATABASE_SECTION`/`_DATABASE_KEY_NAMES`/`_valid_kwargs` with `reader_user`; adds 5 new `DatabaseConfigTest` cases (happy path assertion, discovery-loader-unaffected, malformed/public/loader-equal rejections, directly-constructed bypass test); adds the new `ProvisionScriptTest` class (4 tests)

## Decisions Made

- `reader_user` is a new key in the existing `[database]` section, not a new section — CONTEXT.md's explicit discretion note, chosen to keep the reader-role name reviewable alongside the loader's own fields.
- `vicmap_audit` schema ownership follows the tighter least-privilege model from 04-RESEARCH.md's Open Question 2 recommendation: superuser-owned (`AUTHORIZATION CURRENT_USER`), loader granted `SELECT, INSERT` only, not schema `CREATE` — closing T-04-08.
- The exact `vicmap_audit.staging_validation` column set (`run_ts`, `manifest_digest`, `target_table`, `staging_table`, `verdict`, `spatial`, `row_count`, `srid`, `geometry_type`, `repaired_count`, `recorded_at`) matches the plan's Task 2 `<action>` exactly — Claude's discretion per CONTEXT.md, satisfying D-69's minimum (run_ts + digest + per-layer verdict + D-56 metrics) with nothing about mailbox/idempotency/history.
- The 1Password item path `op://nixos-services/vicmap_reader_credentials/password` mirrors `vicmap_loader_credentials` exactly (Claude's discretion per CONTEXT.md).

## Deviations from Plan

None - plan executed exactly as written. Every task's `<action>` and `<verify>` commands ran without modification and passed on the first attempt.

## Issues Encountered

None.

## Deferred to Operator / Live

This plan is code-only per the operator's explicit instruction; the following two operator steps are deferred and were **not** performed by this executor:

1. **Create the `VICMAP_READER_PASSWORD` 1Password item.**
   - **What:** Create `op://nixos-services/vicmap_reader_credentials/password` in the `nixos-services` vault, set to a fresh generated password for the `vicmap_reader` role.
   - **Resume:** After creating the item, re-enter the dev shell (`nix develop`) so opnix injects `VICMAP_READER_PASSWORD`. Confirm with `nix develop path:. -c bash -c 'echo present: ${VICMAP_READER_PASSWORD:+yes}'` (never echo the value itself).

2. **Run `db/provision_vicmap_loader.sql` against the live database as a PostgreSQL superuser.**
   - **What:** Creates the `vicmap_audit` schema + `staging_validation` table, grants the loader `SELECT`+`INSERT` on it, and creates the `vicmap_reader` LOGIN role with `USAGE ON SCHEMA vicmap`. Also sets `vicmap_reader`'s password from the 1Password value created in step 1 (replace the `REPLACE_WITH_1PASSWORD_VALUE` placeholder in the `CREATE ROLE vicmap_reader LOGIN PASSWORD '...'` statement before running, or run `ALTER ROLE vicmap_reader PASSWORD '<value>'` separately — never commit the real value to this file).
   - **Resume:** `psql -f db/provision_vicmap_loader.sql -d vicmap` (run by hand, once, as superuser). Then paste the script's verification comment block into `psql` to confirm the new checks (loader has `INSERT` on `staging_validation` and no `UPDATE`; reader has `USAGE` on `vicmap` and no `CREATE`).

Neither step was attempted, simulated, or partially run against any database in this session. `tests/test_staging.py::ProvisionScriptTest` and `DatabaseConfigTest` prove the code-side contract is correct and internally consistent (the `CREATE ROLE` name literally equals the configured `reader_user`) without requiring either operator step to complete first.

## User Setup Required

See "Deferred to Operator / Live" above — this plan's `user_setup` (from PLAN.md frontmatter) names exactly these two steps: the 1Password item creation and the by-hand superuser provisioning run. No other external service configuration is required by this plan.

## Next Phase Readiness

- `reader_user` is now a validated, reviewable non-secret config value that 04-04's per-publish `GRANT SELECT` and 04-05's reader-login verification will both resolve to by reading `read_mailbox.load_database_config(...).reader_user`.
- `vicmap_audit.staging_validation`'s column contract is fixed and structurally tested — 04-03's Phase 3 back-fill writer and 04-04's publish gate reader can now be built against a stable, agreed shape.
- `db/provision_vicmap_loader.sql` is code-complete for the operator to run once; until they do, no Phase 4 plan requiring a live `vicmap_audit` table or a live `vicmap_reader` login can complete its live verification (04-03's back-fill write, 04-04's gate read, 04-05's reader-login proof) — each of those plans' own `user_setup`/`checkpoint` steps should reference this plan's two deferred operator steps as their prerequisite, not re-derive them.
- `tests/test_staging.py::DriverImportPolicyTest` was reconfirmed passing as part of the full-suite run — this plan touches no driver-importing module (config, SQL, and flake only), consistent with the plan's own `<verification>` requirement.

---
*Phase: 04-transactional-publication-and-access*
*Completed: 2026-09-23*

## Self-Check: PASSED

All 5 modified/touched files (`read_mailbox.py`, `vicmap.toml`, `db/provision_vicmap_loader.sql`, `flake.nix`, `tests/test_staging.py`) and this SUMMARY.md confirmed present on disk. All 3 task commits (`2758cf3`, `3b8dc28`, `25c8267`) confirmed present in `git log`.
