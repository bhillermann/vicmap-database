---
phase: "3"
slug: "validated-postgis-staging"
# status lifecycle: draft (seeded by plan-phase) → validated (set by validate-phase §6)
# audit-milestone §5.5 distinguishes NOT-VALIDATED (draft) from PARTIAL (validated + nyquist_compliant: false) (#2117)
status: draft
nyquist_compliant: false
wave_0_complete: false
created: "2026-09-21"
---

# Phase 3 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | `unittest` (Python standard library) |
| **Config file** | none — direct module execution / `discover` |
| **Quick run command** | `nix develop path:. -c python -m unittest tests.test_staging -v` |
| **Full suite command** | `nix develop path:. -c python -m unittest discover -s tests -p 'test_*.py'` |
| **Estimated runtime** | ~15 seconds (399 tests / 14.676s recorded at Phase 2 verification) |

---

## Sampling Rate

- **After every task commit:** Run `nix develop path:. -c python -m unittest tests.test_staging -v`
- **After every plan wave:** Run `nix develop path:. -c python -m unittest discover -s tests -p 'test_*.py'`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 20 seconds

---

## Per-Task Verification Map

Task IDs are assigned by the planner. Rows below are seeded per requirement and
are rewritten to task granularity by `/gsd-validate-phase`.

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| TBD | TBD | TBD | DB-01 | — | Connection reports non-secret identity and PostGIS version; no credential is echoed | integration (skip-not-fail) | `nix develop path:. -c python -m unittest tests.test_staging.ConnectionIdentityTest -v` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | DB-02 | — | Privilege preflight passes for a provisioned role and fails closed for an under-privileged one | integration (skip-not-fail) | `nix develop path:. -c python -m unittest tests.test_staging.PrivilegePreflightTest -v` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | DB-03 | — | Layer loads into a uniquely named `vicmap_staging` table; no table created or modified in `public` | unit (mocked `subprocess`) + integration | `nix develop path:. -c python -m unittest tests.test_staging.LoadCommandConstructionTest tests.test_staging.LoadIntegrationTest -v` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | DB-04 | — | Validation reports row count, geometry column/type, SRID, validity, extent; type change is a hard stop | integration | `nix develop path:. -c python -m unittest tests.test_staging.ValidationTest -v` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | DB-05 | — | Induced load/validation failure leaves `public` and `vicmap` row counts unchanged | integration | `nix develop path:. -c python -m unittest tests.test_staging.ProductionIsolationTest -v` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_staging.py` — new module covering DB-01 through DB-05. Follow `tests/test_naming.py`'s `PostgresKeywordOracleTest` skip-not-fail pattern (`VICMAP_TEST_POSTGRES_DSN` env override, driver-import guard, connection-failure guard). No test in this phase may require a reachable PostgreSQL server or an installed `psycopg` to pass.
- [ ] Test fixture/helper provisioning a throwaway staging schema and a deliberately under-privileged role, so `PrivilegePreflightTest` exercises both the pass and the fail path without touching an operator-provisioned database.
- [ ] Deliberately-invalid-geometry fixture (bowtie polygon or self-intersecting line) loadable via `ogr2ogr`, to exercise the repair and hard-stop paths. The real `ADDRESS` layer is Points and cannot exercise this.
- [ ] Framework install: none — `unittest` is stdlib. `psycopg` enters through this phase's own `flake.nix` change.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Live PostGIS service identity and version against the operator's real database | DB-01 | Requires an operator-provisioned server and credentials that cannot exist in CI | Run the connect command against the configured DSN; confirm the printed database name, server version, and PostGIS version, and that no password appears in output or logs |
| End-to-end load of a real Vicmap layer into staging | DB-03, DB-04 | Requires the live delivery artifact and a real PostGIS server | Load one manifest layer; confirm the staging table exists under the staging schema, `public` is untouched, and the validation report lists row count, geometry type, SRID, validity, and extent |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 20s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
