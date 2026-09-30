---
phase: 04-transactional-publication-and-access
plan: 05
subsystem: database
tags: [postgres, postgis, psycopg, gist, spatial-query, reader-role, access-control, security]

# Dependency graph
requires:
  - phase: 04-01
    provides: evidence.py reader-verification Stage/ReasonCode vocabulary (DB_READER_VERIFY, READER_ROLE_UNAVAILABLE, READER_VERIFICATION_FAILED, READER_WRITE_NOT_DENIED)
  - phase: 04-02
    provides: reader_user config key (vicmap.toml) and the vicmap_reader LOGIN role / VICMAP_READER_PASSWORD opnix wiring
  - phase: 04-04
    provides: publish.py's PublishPolicy, PromotionResult.published_tables, and the PublishFailure closed hierarchy this plan extends
provides:
  - verify_reader_access — the PUB-04/PUB-05 D-74 proof, from a genuinely separate reader login (never SET ROLE)
  - ReaderVerification (frozen) — tables_discovered, spatial_query_row_count, write_denied
  - ReaderRoleUnavailable / ReaderVerificationFailed / ReaderWriteNotDenied — the reader-side closed failure hierarchy
affects: [04-06, publish_order.py, EVID-01 summary assembly]

# Actuals (#2632)
actuals:
  tokens: 5270
  tasks: 2
  commits: 2

plan_head_before: a94d1e01a7dae92851b38db358138fd765609caf

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Second, independently-authenticated connection for a role proof (Pattern 3) — never SET ROLE from an existing connection"
    - "Real executed write-denial proof (INSERT ... DEFAULT VALUES expecting InsufficientPrivilege), never a has_table_privilege metadata shortcut"
    - "Security-critical hard-stop: a not-denied write raises rather than downgrading to a warning or a pass"

key-files:
  created: []
  modified:
    - vicmap_acquire/publish.py
    - tests/test_publish.py

key-decisions:
  - "published_tables[0] is the single representative target both the spatial query and the write-denial attempt run against — matches the plan's singular 'representative spatial query' framing and this run's one-layer proof delivery; a future multi-layer reader proof can iterate if ever required"
  - "The Victoria WGS84 extent literals (140.96, -39.2, 150.04, -33.98) are inlined directly in verify_reader_access's SQL text rather than factored into a module constant, so the Task 1 automated verify (which inspects only the function's own source) can assert their presence"
  - "reader_password empty and published_tables empty both fail closed before any connection is attempted (ReaderRoleUnavailable / ReaderVerificationFailed respectively) — no wasted connection, no secret ever touches the network on an already-known-bad call"
  - "Task 1 built the write-attempt with a plain closed failure on the not-denied branch; Task 2 hardened that exact branch to the dedicated, security-critical ReaderWriteNotDenied — two atomic commits mirroring the plan's own task split"

patterns-established:
  - "Recording fake reader connection/cursor (_FakeReaderConnection/_FakeReaderCursor) independent of the promotion-transaction fixture, so the two proofs' offline fixtures never share state"

requirements-completed: []  # PUB-04/PUB-05 are CODE-COMPLETE + offline-verified; live closure is DEFERRED to the operator's live run — see Deferred section

# Coverage
coverage:
  - id: D1
    description: "verify_reader_access opens a genuinely separate connection as policy.reader_user (never SET ROLE), discovers published tables via information_schema.tables, and runs a GiST-exercising spatial query bounded by Victoria's real WGS84 extent (never EPSG:7899's projected-bounds domain)"
    requirement: "PUB-05"
    verification:
      - kind: unit
        ref: "tests/test_publish.py::ReaderVerificationTest (discovery/spatial-query/contract cases) + inline Task 1 verify"
        status: pass
    human_judgment: false
  - id: D2
    description: "The write-denial proof is a real executed INSERT ... DEFAULT VALUES expecting InsufficientPrivilege, never a has_table_privilege metadata shortcut"
    requirement: "PUB-04"
    verification:
      - kind: unit
        ref: "tests/test_publish.py::ReaderVerificationTest.test_discovery_spatial_query_and_write_denial_proof + inline Task 1/2 verify"
        status: pass
    human_judgment: false
  - id: D3
    description: "A reader whose write is NOT denied trips the security-critical ReaderWriteNotDenied and never returns a passing result"
    verification:
      - kind: unit
        ref: "tests/test_publish.py::ReaderVerificationTest.test_writable_reader_raises_reader_write_not_denied"
        status: pass
    human_judgment: false
  - id: D4
    description: "A missing reader role, missing USAGE, or unset VICMAP_READER_PASSWORD fails closed with ReaderRoleUnavailable before the proof runs, exposing no secret"
    verification:
      - kind: unit
        ref: "tests/test_publish.py::ReaderVerificationTest.test_missing_reader_password_fails_closed_before_any_connection, test_reader_connect_failure_is_reader_role_unavailable"
        status: pass
    human_judgment: false
  - id: D5
    description: "LIVE proof of PUB-04/PUB-05: from a real vicmap_reader login on the live server, discovery + GiST spatial query + a real denied write, and a negative case (a writable reader-equivalent role) tripping ReaderWriteNotDenied"
    verification: []
    human_judgment: true
    rationale: "Requires an operator-provisioned vicmap_reader role, resolvable VICMAP_READER_PASSWORD (1Password item does not exist yet), and a completed 04-04 live promotion to have a real published table to prove against. Not performed in this code-only run; live tests are written but skip without VICMAP_TEST_POSTGRES_DSN/SUPERUSER_DSN."

# Metrics
duration: 18min
completed: 2026-09-23
status: complete
---

# Phase 4 Plan 05: Reader Discovery, Spatial Query, and Write-Denial Summary

**`verify_reader_access` proves PUB-04/PUB-05 from a genuinely separate `vicmap_reader` login — table discovery, a Victoria-extent GiST-exercising spatial query, and a real executed write-denial that hard-stops as `ReaderWriteNotDenied` if the grant model is ever broken — code-complete and offline-verified; the live login proof is deferred to the operator.**

## Performance

- **Duration:** ~18 min
- **Started:** 2026-09-23T05:00:00Z (approx.)
- **Completed:** 2026-09-23T05:18:00Z (approx.)
- **Tasks:** 2 of 2
- **Files modified:** 2

## Accomplishments

- Added `ReaderVerification` (frozen: `tables_discovered`, `spatial_query_row_count`, `write_denied`) and `verify_reader_access` to `vicmap_acquire/publish.py`.
- `verify_reader_access` opens a fresh `psycopg.connect()` as `policy.reader_user` with the caller-supplied `reader_password` — never `SET ROLE` from the loader connection (D-74/Pattern 3) — and mirrors `_connect`'s statement/lock timeout setup so no reader query can hang the database.
- Discovery reads `information_schema.tables` scoped to `policy.publish_schema` — a query that itself proves the reader's grants, since ungranted tables are invisible to it (research Code Examples).
- The representative spatial query is `geom && ST_Transform(ST_MakeEnvelope(140.96, -39.2, 150.04, -33.98, 4326), %s)` against `published_tables[0]` — Victoria's real WGS84 extent, `ST_Transform`-ed into `target_srid` at query time, never EPSG:7899's own advertised projected-meters bounds (Pitfall 3).
- The write-denial proof is a real executed `INSERT ... DEFAULT VALUES` (chosen over `UPDATE`: PostgreSQL's ACL check runs at executor startup, before any `NOT NULL` constraint) expecting `InsufficientPrivilege`; no `has_table_privilege` metadata shortcut anywhere in the path.
- If the write is *not* rejected, `verify_reader_access` rolls back and raises the security-critical `ReaderWriteNotDenied` — never a silent pass — because a writable reader means the grant model is broken (T-04-02, Elevation of Privilege).
- `ReaderRoleUnavailable` (missing/unset password, or any connect/auth failure as the reader) and `ReaderVerificationFailed` (discovery/spatial-query failure, or no published table to prove against) both fail closed before or during the proof with no driver text or secret ever surfacing.

## Task Commits

Each task was committed atomically:

1. **Task 1 (tracer): Prove reader discovery + spatial query + write-denial end-to-end** - `4c10fb6` (feat)
2. **Task 2: Make the write-denial security-critical (READER_WRITE_NOT_DENIED)** - `2c09168` (feat)

_Task 1 shipped the write-attempt with a plain closed failure on the not-denied branch (matching its own `<verify>`, which does not check for `ReaderWriteNotDenied`); Task 2 hardened that exact branch into the dedicated, security-critical exception and added the negative fixture/live tests — two genuinely incremental diffs, not a single combined commit split after the fact._

## Files Created/Modified

- `vicmap_acquire/publish.py` - `ReaderVerification`, `_connect_as_reader`, `verify_reader_access`, and the `ReaderRoleUnavailable`/`ReaderVerificationFailed`/`ReaderWriteNotDenied` closed failures.
- `tests/test_publish.py` - `_FakeReaderConnection`/`_FakeReaderCursor` (independent of the promotion-transaction fixture), the offline `ReaderVerificationTest` class (9 cases), extended `ClosedFailureVocabularyTest`, and three new live skip-guarded classes (`LiveReaderVerificationTest`, `LiveReaderWriteDenialTest`, `LiveReaderWriteNotDeniedTest`).

## Offline Verification (performed this run)

All commands run via `nix develop path:. -c ...`:

- Task 1 inline contract check → **`reader verify contract ok`** (discovery + spatial query + Victoria extent + write-denial check present; no `SET ROLE`).
- Task 2 inline contract check → **`write-denial hard-stop ok`** (`ReaderWriteNotDenied` present and a `PublishFailure` subclass; no `has_table_privilege`).
- `python -m unittest tests.test_publish -v` → **OK, 43 tests, 6 skipped** (all 6 skips are live-DB tests; every offline case passes).
- `python -m unittest tests.test_staging.DriverImportPolicyTest -v` → **OK** (publish.py's driver exemption unaffected — this plan touched no new driver-importing module).
- `python -m unittest discover -s tests -t . -p 'test_*.py'` → **OK, 591 tests, skipped=42** (full-suite regression; no other module broke).
- `git status --short` clean after each commit; no unexpected file deletions (`git diff --diff-filter=D`) across the two-commit range.

## Decisions Made

- **`published_tables[0]` as the single representative target** for both the spatial query and the write-denial attempt, matching the plan's singular "representative spatial query" framing and this run's one-layer proof delivery (ADDRESS). A future multi-layer reader proof can iterate over more tables if that ever becomes a requirement; not needed here.
- **Victoria's WGS84 extent literals inlined directly in `verify_reader_access`'s own SQL text**, not factored into a module-level constant — the plan's automated Task 1 `<verify>` inspects only `inspect.getsource(verify_reader_access)`, so a module constant would have been invisible to that check. Discovered this the hard way: an initial draft extracted the envelope to a constant and the `'140.96' in src` assertion failed until inlined.
- **Docstring/comment wording avoids the literal substring `has_table_privilege`** even when describing what the code deliberately does *not* do — the Task 2 automated verify checks the whole function source (including docstrings) for that substring, so an explanatory comment using the forbidden phrase would have false-failed its own compliance check.
- **`reader_password`/`published_tables` emptiness checks run before any connection attempt** — `ReaderRoleUnavailable`/`ReaderVerificationFailed` fire on an already-known-bad call without ever touching the network, consistent with "fails closed... exposing no secret" (must-have).

## Deviations from Plan

None - plan executed exactly as written, within the code-only boundary set by this run.

One in-authoring correction worth noting (not a plan deviation): an early draft's docstring literally quoted the phrase "`has_table_privilege` shortcut" while explaining the anti-pattern being avoided — this tripped the Task 2 automated verify's own `'has_table_privilege' not in src` assertion as a false positive, since it scans the whole function source including prose. Reworded to "grant-metadata-only shortcut" (no behavior change; the code itself never used `has_table_privilege`).

## Issues Encountered

- The devshell prints an opnix error resolving `VICMAP_READER_PASSWORD` (`op://nixos-services/vicmap_reader_credentials/password` → itemNotFound) on every invocation — the same anticipated D-74 operator-setup gap already documented in 04-04-SUMMARY.md. All offline tests pass regardless since none of them materialize that secret; `nix develop` still enters the shell and runs Python despite the opnix warning.
- The full-suite regression run (`unittest discover`) showed some non-`test_publish` live tests actually executing (JSON evidence events observed) rather than skipping, indicating `VICMAP_TEST_POSTGRES_DSN` was set in that invocation's ambient environment for other test modules. Confirmed directly (`echo $VICMAP_TEST_POSTGRES_DSN` inside the devshell) that both `VICMAP_TEST_POSTGRES_DSN` and `VICMAP_TEST_POSTGRES_SUPERUSER_DSN` are in fact unset in this session — `_LivePublishMixin._require_live()` requires both, so every reader-verification live test in this plan skipped cleanly as required by the code-only mandate. No live database was touched by this plan's work.

## DEFERRED — live / operator

This was a **code-only run**. The following were intentionally NOT performed and are deferred to the operator.

### What is deferred and why

- **The live reader-login proof (PUB-04/PUB-05)** — `verify_reader_access` was never run against a real `vicmap_reader` login. It requires: (1) `db/provision_vicmap_loader.sql` run as superuser to create the `vicmap_reader` LOGIN role with `USAGE ON SCHEMA vicmap` (D-72, still outstanding per 04-04-SUMMARY.md); (2) the 1Password item `op://nixos-services/vicmap_reader_credentials/password` created so `VICMAP_READER_PASSWORD` resolves; (3) a completed 04-04 live promotion so `vicmap.vmadd_address` (or another target) actually exists and is `GRANT SELECT`-ed to the reader.
- **The negative write-not-denied proof** — requires deliberately granting `INSERT` to a reader-equivalent test role against a promoted fixture table to prove `verify_reader_access` actually detects a broken grant, not just the happy path. This is itself a temporary, intentional grant-model violation for testing purposes and must be reverted immediately after the proof.
- **Any user_setup/checkpoint step** — none exists in this plan (`autonomous: true`, no `checkpoint:*` tasks); nothing was skipped on that account.

### Exact resume steps (operator)

1. **Complete 04-02/04-04's outstanding provisioning** (if not already done): create the 1Password item for `VICMAP_READER_PASSWORD`, then run `db/provision_vicmap_loader.sql` as superuser (creates `vicmap_reader` LOGIN role with `USAGE ON SCHEMA vicmap`, per D-72). Confirm `VICMAP_READER_PASSWORD` resolves in the devshell (`nix develop path:. -c bash -c 'echo $VICMAP_READER_PASSWORD | wc -c'` should print a non-trivial length, never the value itself).
2. **Complete a live 04-04 promotion** so at least one `vicmap.*` table exists and is granted `SELECT` to the reader (see 04-04-SUMMARY.md's own resume steps 1-4).
3. **Run the live reader-verification tests** with both DSNs set: `VICMAP_TEST_POSTGRES_DSN=... VICMAP_TEST_POSTGRES_SUPERUSER_DSN=... nix develop path:. -c python -m unittest tests.test_publish -v` — the three currently-skipped `LiveReader*` classes must be fleshed out from placeholders into real fixture-driven proofs (they currently only assert `self._require_live()` then `self.skipTest(...)`) before this step can pass.
4. **For the negative proof specifically:** create a throwaway table or reuse a promoted fixture, `GRANT INSERT` to a disposable reader-equivalent test role, call `verify_reader_access` and assert `ReaderWriteNotDenied` is raised, then **immediately revoke** the grant — do not leave a writable reader-equivalent role provisioned after the proof completes.

## Known Stubs

- `tests/test_publish.py::LiveReaderVerificationTest`, `LiveReaderWriteDenialTest`, `LiveReaderWriteNotDeniedTest` — the live fixture bodies are `skipTest`-guarded placeholders (they require the operator-provisioned reader role/secret and a promoted fixture described above). They skip cleanly offline and must be fleshed out and run against the live DB during the operator's verification pass. Logged to `.planning/WINDOWS.md` as unrun-verify entries 12, 13, 14.

## Threat Flags

None — no new network endpoint, auth path, file-access pattern, or schema change outside the plan's own `<threat_model>` was introduced. The reader connection, the write-denial hard-stop, and the redacted failure output were all anticipated by T-04-02/T-04-11/T-04-03/T-04-12 in 04-05-PLAN.md and are mitigated exactly as planned.

## Next Phase Readiness

- `verify_reader_access` is ready to be wired into `publish_order.py` (D-77, a later plan) immediately after a successful `promote_order` call, and its `ReaderVerification` result is ready to feed the EVID-01 summary.
- **Blocker for the live milestone proof:** the same operator provisioning gap 04-04 already identified (reader secret + role) plus a completed live promotion, then the live reader-verification pass described above.

## Self-Check: PASSED

---
*Phase: 04-transactional-publication-and-access*
*Completed: 2026-09-23*
