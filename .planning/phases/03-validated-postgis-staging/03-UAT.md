---
status: testing
phase: 03-validated-postgis-staging
source: [03-VERIFICATION.md]
started: 2026-09-21T09:40:00Z
updated: 2026-09-21T09:40:00Z
---

## Current Test

number: 1
name: DB-02 privilege preflight fails closed on a role lacking privilege
expected: |
  Each negative condition causes `preflight_staging_privileges` to raise its
  named exception and leave nothing behind (the probe is rolled back):
    - a role lacking CREATE on `vicmap_staging`
    - a role holding CREATE on `public`
    - a superuser role
    - an SRID not registered in `spatial_ref_sys`
awaiting: user response

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

Option A — provision a throwaway test-only superuser DSN so the five skipped
methods actually run:

```
export VICMAP_TEST_POSTGRES_SUPERUSER_DSN="host=127.0.0.1 port=5432 dbname=vicmap user=<superuser> password=<value>"
export VICMAP_TEST_POSTGRES_DSN="host=127.0.0.1 port=5432 dbname=vicmap user=vicmap_loader password=$VICMAP_DB_PASSWORD"
nix develop --command python -m unittest tests.test_staging.PrivilegePreflightTest -v
```

Expect 5 passes and 0 skips. Do not write either password to a file, and do not
pass either as a command argument — `ps` can read argv.

Option B — manually verify at least one negative case: create a throwaway role
without CREATE on `vicmap_staging`, point `preflight_staging_privileges` at it,
and confirm it raises rather than proceeding.

result: [pending]

## Summary

total: 1
passed: 0
issues: 0
pending: 1
skipped: 0
blocked: 0

## Gaps
