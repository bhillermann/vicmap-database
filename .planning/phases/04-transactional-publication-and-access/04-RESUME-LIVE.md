# Phase 4 — Live Resume Checklist

**Status:** Code-complete + offline-verified (619 tests OK, 43 skipped). Live boundary deferred to operator.
**Created:** 2026-09-23 (autonomous code-only run)

All six plans' source and offline tests are committed on `main`. What remains is everything that needs a live PostgreSQL/PostGIS server, superuser rights, the 1Password reader secret, or the one-way-door promotion decision. Work top to bottom.

## 1. Operator setup (one-time)

1. **Create the reader secret in 1Password:** item `op://nixos-services/vicmap_reader_credentials/password` (vault `nixos-services`). This backs `VICMAP_READER_PASSWORD` via the flake.nix opnix wiring (04-02). Until it exists, the devshell prints `itemNotFound` on that var (expected, non-fatal).
2. **Run the provisioning SQL as superuser** against the `vicmap` database:
   `psql -f db/provision_vicmap_loader.sql -d vicmap`
   Creates the `vicmap_audit` schema + `vicmap_audit.staging_validation` gate table, grants the loader `SELECT, INSERT` (no CREATE), and creates the `vicmap_reader` LOGIN role with `USAGE ON SCHEMA vicmap` (D-72). Set the reader role's password from the 1Password value (never commit it). Then paste the script's trailing verification comment block into `psql`.
3. **Confirm both secrets resolve** (never prints the values):
   `nix develop path:. -c bash -c 'echo present: ${VICMAP_DB_PASSWORD:+yes} ${VICMAP_READER_PASSWORD:+yes}'`

## 2. Populate the audit gate (needs live DB)

4. **Re-run a validated staging run** so a PASS row exists for each layer 04-04's gate reads:
   `nix develop path:. -c python stage_order.py` (against the real VMADD.gdb / ADDRESS delivery — this is the Phase 3 staging path; 04-03 now writes one PASS row per validated layer into `vicmap_audit.staging_validation`).

## 3. One-way-door decision (approve before promotion)

5. **Confirm the published-table contract** (D-66/D-67/D-71/D-73): promotion is a metadata move (`SET SCHEMA` + `RENAME`, no row copy); the live table keeps the manifest `target_table` name (e.g. `vmadd_address`) with canonical names `{table}_pkey`, `{table}_geom_idx`, `{table}_geom_not_null`, `{table}_{col}_idx`; a single live generation (prior `vicmap.{table}` dropped in the same transaction, D-71); reader `GRANT SELECT` in that same transaction (D-73).
   - Option 1 (recommended, and what the code implements): proceed as specified.
   - Option 2: adjust naming/retention — revises D-67/D-71 and must be re-agreed before the naming code is changed.

## 4. Live promotion + verification

6. **Promote:** `nix develop path:. -c python publish_order.py` → expect exit 0, `summary.json` written, one redacted `publication_summary` event. A failure returns non-zero with one boundary-named, secret-free line (EVID-02).
7. **Run the live test classes** (currently skip-guarded placeholders — flesh out from stubs):
   `VICMAP_TEST_POSTGRES_DSN=<dsn> VICMAP_TEST_POSTGRES_SUPERUSER_DSN=<superuser-dsn> nix develop path:. -c python -m unittest tests.test_publish tests.test_publish_order -v`
   Covers: `AuditValidationRecordTest`, `LiveReaderVerificationTest`, `LiveReaderWriteDenialTest`, `LiveReaderWriteNotDeniedTest`, `LivePublishOrderFullRunTest`. Tracked in `.planning/WINDOWS.md` (unrun-verify entries #8, #12–15). For the write-not-denied negative proof: grant `INSERT` to a disposable reader-equivalent role, assert `ReaderWriteNotDenied` is raised, then immediately revoke — never leave a writable reader-equivalent role provisioned.

## 5. Formal phase verification

8. Once the live promotion + reader tests are green, run `/gsd-verify-work 4` (goal-backward verification against the now-live behavior) to produce `04-VERIFICATION.md`, then mark Phase 4 complete. Only then does Phase 5 (Approved Legacy Cleanup, which operates on the live `vicmap` DB after publication) become executable.

## Requirement status at hand-off

| Req | Code | Offline test | Live proof |
|-----|------|--------------|-----------|
| PUB-01..05 | ✓ | ✓ (static/composition) | deferred (§4) |
| EVID-01, EVID-02 | ✓ | ✓ | deferred (§4) |

Nothing in this phase touched a live database during the autonomous run.
