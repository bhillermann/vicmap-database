---
status: passed
phase: 03-validated-postgis-staging
source: [03-VERIFICATION.md]
started: 2026-09-21T09:40:00Z
updated: 2026-09-22T00:00:00Z
---

## Current Test

none — all tests complete

## Completed Test

number: 1
name: DB-02 privilege preflight fails closed on a role lacking privilege
expected: |
  Each negative condition causes `preflight_staging_privileges` to raise its
  named exception and leave nothing behind (the probe is rolled back):
    - a role lacking CREATE on `vicmap_staging`
    - a role holding CREATE on `public`
    - a superuser role
    - an SRID not registered in `spatial_ref_sys`
result: passed 2026-09-22

## Tests

### 1. DB-02 privilege preflight fails closed on a role lacking privilege

expected: Each of the four negative conditions raises its named exception from
`preflight_staging_privileges`, and the rolled-back probe leaves no object behind.

Why this is outstanding: `preflight_staging_privileges` exists, is correctly
wired as the first step before any load, and its PASS path has been
live-demonstrated twice — an unmocked `run_staging` call against the real
`vicmap_loader` role in `ProductionIsolationTest`, and the operator's manual
`stage_order.py --preflight-only` run cross-checked with `psql`. But the four
FAIL-CLOSED branches, which are the actual mechanism that would catch an
under-privileged role, have never executed anywhere — not live, not in CI.

The only test that manipulates real ACLs to exercise them is
`PrivilegePreflightTest` (5 methods), which permanently skips for want of a
`VICMAP_TEST_POSTGRES_SUPERUSER_DSN` that has never been set. See WINDOWS.md #6.

Presence plus wiring plus a demonstrated pass path is not proof that the
negative branches fail closed. This phase has already been bitten three times by
verification that looked green and proved nothing.

How to close it, either way:

Option A (agreed method) — supply the superuser DSN per-shell, by reference,
and let it die with the shell:

```
export VICMAP_TEST_POSTGRES_SUPERUSER_DSN="host=127.0.0.1 port=5432 dbname=vicmap user=$(op read op://nixos-services/postgis/username) password=$(op read op://nixos-services/postgis/password)"
nix develop --command python -m unittest tests.test_staging.PrivilegePreflightTest -v
unset VICMAP_TEST_POSTGRES_SUPERUSER_DSN
```

Expect 5 passes and 0 skips.

Credential handling — the rule is that no literal secret ever appears in text
you type; an `op://` reference is fine anywhere:
  - The command above puts only `op://` paths in `~/.zsh_history`, never values.
  - `$VICMAP_DB_PASSWORD` is likewise a reference, already resolved by the
    devshell, so `VICMAP_TEST_POSTGRES_DSN` needs no special handling.
  - `export` itself is NOT the exposure. An env var is readable via
    `/proc/<pid>/environ` only by you and root — the same trust boundary as the
    file the secret already lives in. The two channels that genuinely leak are
    argv (any process can read it via `ps`) and the history file on disk.
  - `histignorespace` is set in this shell, so a leading space keeps a command
    out of history. Use it as a second layer, never as the fix.

DELIBERATELY NOT DONE: this reference is not added to `flake.nix`'s
`opnixEnvConfig`. That config feeds every `nix develop`, so a superuser entry
there would hand superuser access to every process in the devshell — directly
contradicting D-59/DB-05, the invariant this phase exists to establish. The
elevated credential stays scoped to the one shell that runs this test.

Option B — manually verify at least one negative case: create a throwaway role
without CREATE on `vicmap_staging`, point `preflight_staging_privileges` at it,
and confirm it raises rather than proceeding.

result: PASSED 2026-09-22

Operator supplied VICMAP_TEST_POSTGRES_SUPERUSER_DSN per-shell via `op read`
references and ran the five methods. All five passed, zero skips, zero errors:

  test_fail_path_create_on_public ................................ ok
  test_fail_path_no_create_on_staging_schema ..................... ok
  test_fail_path_superuser ....................................... ok
  test_fail_path_unknown_srid .................................... ok
  test_pass_path_proves_capability_and_leaves_nothing_behind ..... ok
  Ran 5 tests in 0.416s -- OK

All four fail-closed branches of `preflight_staging_privileges` have now
executed and raised as designed. This is their first execution ever.

Teardown verified independently against the live catalogue after the run: no
`staging_preflight%` role and no `staging_preflight%` schema remain, and
`public` holds only PostGIS's own `geography_columns`, `geometry_columns`,
`spatial_ref_sys`. The rolled-back probe leaves nothing behind, as claimed.

Defect found and fixed to get here (ba3ef2b): the fixture's `CREATE ROLE {}
LOGIN PASSWORD %s` used a bind parameter, which PostgreSQL rejects in a utility
statement. All five methods errored on `syntax error at or near "$1"` the first
time they were ever run. Same defect class as 616d50a in `staging._connect`;
uncaught because this fixture had executed zero times.

## Summary

total: 1
passed: 1
issues: 0
pending: 0
skipped: 0
blocked: 0

## Gaps

None. All human verification items pass.
