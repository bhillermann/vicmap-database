---
phase: 03-validated-postgis-staging
plan: 02
subsystem: config
tags: [toml, dataclass, postgis, schema-policy, config-contract]

requires:
  - phase: 03-validated-postgis-staging
    provides: "03-01's flake.nix devshell (psycopg importable, no code dependency for this plan)"
provides:
  - "vicmap.toml's fifth [database] section -- host, port, dbname, user, both schema names, target_srid, index_columns, gt, and three timeout budgets"
  - "read_mailbox.DatabaseRunConfig, load_database_config(path), and validate_database_policy(config) -- the single semantic contract"
  - "tests/test_staging.py -- the Phase 3 test module, seeded with DatabaseConfigTest"
affects: [03-03, 03-04, 03-05, 03-06]

actuals:
  tokens: 5393
  tasks: 2
  commits: 2
  plan_head_before: 1e8f74f

tech-stack:
  added: []
  patterns:
    - "load_database_config delegates to load_discovery_config for every inherited Phase 1/2 check, then does its own [database] shape work before calling validate_database_policy -- the same three-layer delegation chain load_discovery_config already uses over load_config"
    - "_PG_IDENTIFIER + _FORBIDDEN_SCHEMA_NAMES enforce SQL-identifier and public-schema exclusion in policy, independent of and prior to naming.py's own leaf-module identifier rules"

key-files:
  created:
    - tests/test_staging.py
  modified:
    - vicmap.toml
    - read_mailbox.py
    - tests/test_graph.py
    - tests/test_discovery_config.py

key-decisions:
  - "load_config's top-level section-set check widened from four to exactly five names (mailbox, download, extraction, discovery, database) -- a stray sixth section still fails closed, matching the plan's exact-set requirement."
  - "host validation accepts ipaddress.ip_address() OR the existing _HOSTNAME dotted-name pattern, deliberately rejecting a bare 'localhost' (no dot) -- the loopback must be named by address, matching the plan's explicit design choice."
  - "port and target_srid extraction/validation both use _bounded_integer (matching the plan's literal spec); gt and the three timeout fields use _positive_bounded_integer -- following the existing extraction/validate naming split already established by max_total_bytes vs validate_discovery_policy."

patterns-established:
  - "DatabaseRunConfig carries zero secret fields by construction -- _DATABASE_KEYS has no password-shaped key, so a [database] table with one is rejected by set equality before any semantic check runs."

requirements-completed: [DB-01, DB-02, DB-05]

coverage:
  - id: D1
    description: "vicmap.toml carries a complete, reviewable [database] section with no credential key, and read_mailbox enforces it as the fifth required section"
    requirement: "DB-01"
    verification:
      - kind: unit
        ref: "tests/test_staging.py#DatabaseConfigTest.test_happy_path_loads_every_field"
        status: pass
      - kind: unit
        ref: "tests/test_staging.py#DatabaseConfigTest.test_no_credential_shaped_key_in_the_shipped_database_table"
        status: pass
      - kind: unit
        ref: "tests/test_discovery_config.py#LoadDiscoveryConfigValidTest.test_real_repository_vicmap_toml_loads_the_settled_phase_2_defaults"
        status: pass
    human_judgment: false
  - id: D2
    description: "A missing, incomplete, or semantically invalid [database] section (missing/extra key, forbidden schema name, out-of-range value, lock exceeding statement timeout) fails closed as config_invalid before any connection is attempted, and a directly constructed DatabaseRunConfig cannot bypass validate_database_policy"
    requirement: "DB-05"
    verification:
      - kind: unit
        ref: "tests/test_staging.py#DatabaseConfigTest (18 test cases, 0 skipped)"
        status: pass
    human_judgment: false
  - id: D3
    description: "The existing Phase 1/2 test suite and the real repository vicmap.toml continue to load unchanged after the five-section widening"
    verification:
      - kind: unit
        ref: "nix develop path:. -c python -m unittest discover -s tests -p 'test_*.py' -> Ran 419 tests, OK (skipped=1)"
        status: pass
    human_judgment: false

duration: ~20min
completed: 2026-09-21
status: complete
---

# Phase 3 Plan 2: Database Policy Contract Summary

**Added `vicmap.toml`'s fifth `[database]` section and `read_mailbox.DatabaseRunConfig`/`load_database_config`/`validate_database_policy` as the single fail-closed contract for the connection target, schema names, target SRID, index allowlist, and loader timeouts -- carrying no credential key.**

## Performance

- **Duration:** ~20 min
- **Tasks:** 2
- **Files modified:** 5 (1 created, 4 modified)

## Accomplishments

- `vicmap.toml` is again the whole non-secret policy, now five sections wide, with `[database]` carrying exactly the twelve specified keys and initial values, and a comment recording that no credential key exists here by design (D-58).
- `read_mailbox.load_config`'s top-level section-set check widened from an exact four-name set to an exact five-name set; a file with a stray sixth section, or missing any of the five, still fails closed as `config_invalid`.
- Added `DatabaseRunConfig` (frozen dataclass, exactly the fields this plan's `<interfaces>` block specifies), `load_database_config(path)`, and `validate_database_policy(config)` to `read_mailbox.py`, mirroring the existing `DiscoveryRunConfig`/`load_discovery_config`/`validate_discovery_policy` shape exactly.
- `validate_database_policy` enforces D-47/DB-03 in policy: `staging_schema`/`publish_schema` can never equal `public` and can never equal each other, independent of what the database role's grants allow.
- Created `tests/test_staging.py` -- the Phase 3 test module -- seeded with `DatabaseConfigTest` (18 test cases), proving every rejection rule fails closed with no PostgreSQL server and no driver import, and zero skips.
- Confirmed the full existing test suite (401 -> 419 tests) still passes after both changes.

## Task Commits

Each task was committed atomically:

1. **Task 1: Add the [database] section and make the policy contract five sections wide** - `360831f` (feat)
2. **Task 2: Create the Phase 3 test module with the fail-closed configuration contract** - `11aa7f5` (test)

**Plan metadata:** committed together with this SUMMARY (see below).

## Files Created/Modified

- `vicmap.toml` - added the fifth `[database]` section (12 keys, no credential)
- `read_mailbox.py` - added `_DATABASE_KEYS`, `_PG_IDENTIFIER`, `_FORBIDDEN_SCHEMA_NAMES`, `DatabaseRunConfig`, `validate_database_policy`, `load_database_config`; widened the five-section check; added `import ipaddress`
- `tests/test_graph.py` - appended the `[database]` table to the positive `VALID_TOML` fixture
- `tests/test_discovery_config.py` - appended the `[database]` table to the positive `VALID_TOML` fixture; `TWO_SECTION_TOML` left byte-unchanged
- `tests/test_staging.py` - new Phase 3 test module; `DatabaseConfigTest` (18 cases)

## Decisions Made

- Widened `load_config`'s exact top-level section-set check to five names rather than relaxing it to a subset check -- set equality stays exact, so a stray sixth section (e.g. a future Phase 4 `[publish]` section added prematurely) still fails closed.
- `host` validation accepts either `ipaddress.ip_address()` or the existing dotted-hostname `_HOSTNAME` pattern; a bare `localhost` is deliberately rejected (no dot) per the plan's explicit instruction to name the loopback by address.
- Followed the codebase's existing `_bounded_integer` (shape extraction / plan-specified checks) vs `_positive_bounded_integer` (semantic validation of "must be positive and bounded" fields) naming split exactly as the plan specified per-field, rather than picking one function for all numeric checks.

## Deviations from Plan

None - plan executed exactly as written. All acceptance criteria and verification commands passed on the first implementation pass with no fix-up commits required.

## Issues Encountered

None. The `op://nixos-services/vicmap_loader_credentials/password` opnix `itemNotFound` warning (carried over from 03-01, unresolved until the operator creates the 1Password item) prints to stderr on every `nix develop` invocation but does not affect exit codes or test results -- verified explicitly during this plan's verification runs.

## User Setup Required

None - no external service configuration required by this plan.

## Next Phase Readiness

- `read_mailbox.load_database_config('vicmap.toml')` returns a fully validated `DatabaseRunConfig` that 03-04's `staging.py` can consume directly for connection, schema, SRID, and index policy.
- `DatabaseRunConfig` deliberately carries no password field; 03-04 must read `VICMAP_DB_PASSWORD` from the environment separately, as this plan's `<interfaces>` block specifies.
- Carried-forward blocker (unrelated to this plan, from 03-01): 03-04/03-06 must still verify that `ogr2ogr -t_srs EPSG:7899` actually uses the vendored ICSM grid rather than a grid-free Helmert transform under `OGR_CT_ONLY_BEST=YES`/`OGR_CT_ALLOW_BALLPARK=NO`.
- Carried-forward blocker (unrelated to this plan, from 03-01): the operator must still create the `op://nixos-services/vicmap_loader_credentials/password` 1Password item before any code that reads `VICMAP_DB_PASSWORD` (03-04 onward) can run end to end.

---
*Phase: 03-validated-postgis-staging*
*Completed: 2026-09-21*

## Self-Check: PASSED
- FOUND: vicmap.toml [database] section
- FOUND: read_mailbox.py DatabaseRunConfig/load_database_config/validate_database_policy
- FOUND: tests/test_staging.py
- FOUND: commit 360831f
- FOUND: commit 11aa7f5
