---
status: complete
phase: 04-transactional-publication-and-access
source: [04-01-SUMMARY.md, 04-02-SUMMARY.md, 04-03-SUMMARY.md, 04-04-SUMMARY.md, 04-05-SUMMARY.md, 04-06-SUMMARY.md]
started: 2026-09-24T00:00:00Z
updated: 2026-09-25T00:00:00Z
---

## Current Test

[testing complete]

## Tests

### 1. Cold Start Smoke Test
expected: Kill any running service. Clear ephemeral state (temp DBs, caches, lock files). Start from scratch — `nix develop path:. -c python -m unittest discover -s tests` passes cold, and `db/provision_vicmap_loader.sql` applies cleanly on a fresh database without errors.
result: pass
note: "No long-running service exists (individual one-CLI-per-phase scripts), so the 'kill service / clear state' framing is N/A. The applicable cold-start clause was run this session from a clean nix develop shell: `python -m unittest discover -s tests` → 619 OK, 43 skipped, exit 0, including live database_identity connections to PostgreSQL at 127.0.0.1:5432. The provisioning-SQL-applies-cleanly clause was proven live in test 3 (schemas + roles present, least-privilege boundaries hold)."


### 2. Reader-role config loads from vicmap.toml
expected: `load_database_config` reads a vicmap.toml carrying the reader-role name and returns a DatabaseRunConfig whose `reader_user` is a validated PostgreSQL identifier (D-72).
result: pass

### 3. Provisioning script creates audit schema and reader role
expected: `db/provision_vicmap_loader.sql`, run once by a superuser, creates the `vicmap_audit` schema and `staging_validation` table (loader granted SELECT+INSERT only, not schema CREATE) and the `vicmap_reader` LOGIN role with USAGE ON SCHEMA vicmap and no write privilege (D-70/D-72).
result: pass
note: "Confirmed live from a vicmap_loader connection to PostgreSQL 17.5 at 127.0.0.1:5432: schemas vicmap/vicmap_staging/vicmap_audit present, vicmap_audit.staging_validation exists, vicmap_loader and vicmap_reader both LOGIN, loader INSERT=true UPDATE=false, reader USAGE=true CREATE=false. Least-privilege boundaries hold."

### 4. VICMAP_READER_PASSWORD resolves via opnix
expected: flake.nix injects VICMAP_READER_PASSWORD via opnix from the 1Password reference `op://nixos-services/vicmap_reader_credentials/password` — never from vicmap.toml or argv (D-74/D-58). Entering the dev shell resolves the secret.
result: pass

### 5. Audit rows persist durably against the live database
expected: `record_validation` writes one PASS row per layer into the real `vicmap_audit.staging_validation`, keyed by (run_ts, manifest_digest, target_table), reads back correctly, is idempotent on a repeated call, writes NULL for non-spatial fields on a non-spatial layer, and raises AuditPrivilegeDenied when the role lacks INSERT.
result: pass
note: "Operator confirmed pass. Recorded honestly: the only AuditValidationRecordTest run pasted into this session reported skipped=4 (VICMAP_TEST_POSTGRES_SUPERUSER_DSN unresolved). This session did not witness the four tests executing green. Corroborating live evidence that does exist: vicmap_audit.staging_validation is present and already holds 1 row, and loader INSERT=true/UPDATE=false."

### 6. Live atomic promotion into vicmap
expected: A PASS-gated order promotes into `vicmap` — all layers commit together, an induced failure preserves every prior table (full rollback), canonical pk/NOT-NULL/index names materialize on the real PG server, and the reader holds SELECT (PUB-01/PUB-02/PUB-03/PUB-04).
result: pass
note: "Live run 2026-09-24 (runs/OK0VUZ/20260924T083137Z): promoted vicmap.vmadd_address on PostgreSQL 17.5 — 4,222,035 rows, POINT, SRID 7899, layer_count 1. Reader holds SELECT (tables_discovered 1). Exit 0 inferred: summary.json written at successful pipeline end, no EVID-02 failure line. Success path proven live. Live induced-failure rollback NOT exercised; rollback-and-PromotionFailed proven by automated test 18. Canonical pk/index/NOT-NULL names not re-queried from the live catalog post-run; composition proven by automated test 18 — optional live confirmation in Gaps."

### 7. Live reader access proof
expected: From a real `vicmap_reader` login on the live server — table discovery, a GiST-exercising spatial query bounded by Victoria's WGS84 extent returning rows, and a real INSERT denied with InsufficientPrivilege. A writable reader-equivalent role trips ReaderWriteNotDenied.
result: pass
note: "Reader-verify ran inside the live publish_order.py run: reader discovered 1 table (vmadd_address), GiST spatial query returned 10 rows, real INSERT denied (reader_write_denied=true). Writable-role ReaderWriteNotDenied trip NOT induced live; proven by automated test 22 — optional live proof in Gaps."

### 8. Live end-to-end publish_order.py run
expected: `publish_order.py` run against a real, fully-provisioned order completes the whole pipeline (load-config → gate+promote → reader-verify → summary), exits 0, and writes a redacted summary.json carrying only safe scalars.
result: pass
note: "Full pipeline ran end-to-end for OK0VUZ; summary.json at runs/OK0VUZ/20260924T083137Z/summary.json holds only safe scalars (artifact/manifest sha256, message_fingerprint, order_id, layer_count, published_tables, reader block, server_version, staging_validation) — no secrets, no DSNs. Exit 0 inferred from summary.json presence + absence of EVID-02 line."

### 9. Stage.DB_PUBLISH / PUB_PROMOTION_FAILED closed vocabulary
expected: Stage.DB_PUBLISH and ReasonCode.PUB_PROMOTION_FAILED exist, map through _FAILURE_POLICY, and render as one closed SafeFailure JSON line naming stage/reason/hint with no other key
result: pass
source: automated
coverage_id: 04-01-D1

### 10. Audit/reader-verify stages and reason codes
expected: DB_AUDIT/DB_READER_VERIFY stages and the six audit-gate/reader-verification reason codes exist, every stage is reachable, SafeFailure constructs for each, and READER_WRITE_NOT_DENIED carries the urgent revoke hint (never retry)
result: pass
source: automated
coverage_id: 04-01-D2

### 11. SuccessEvent.publication_summary redaction
expected: SuccessEvent.publication_summary builds a redacted event from safe scalars only and rejects each malformed field with ValueError and no partial event
result: pass
source: automated
coverage_id: 04-01-D3

### 12. validate_database_policy rejects bad reader_user
expected: validate_database_policy rejects a missing, malformed, or public reader_user before any connection is opened, failing closed with config_invalid
result: pass
source: automated
coverage_id: 04-02-D2

### 13. manifest_digest sidecar read
expected: manifest.manifest_digest(run_directory) returns the same 64-hex digest read_manifest verified, raising ManifestUnreadable on a missing or malformed sidecar (never reading manifest.json itself)
result: pass
source: automated
coverage_id: 04-03-D1

### 14. record_validation SQL composition and closed failures
expected: record_validation composes vicmap_audit.staging_validation via sql.Identifier plus bind parameters only, and exposes AuditPrivilegeDenied/AuditRecordFailed with the exact reserved codes
result: pass
source: automated
coverage_id: 04-03-D2

### 15. stage_order.py audit back-fill ordering
expected: stage_order.py calls record_validation once per manifest layer only after run_staging returns without raising; a failed run leaves the audit table untouched and exits non-zero
result: pass
source: automated
coverage_id: 04-03-D4

### 16. publish.py driver isolation
expected: publish.py is a driver-isolated module and the DriverImportPolicyTest exemption is the closed {staging.py, publish.py} set
result: pass
source: automated
coverage_id: 04-04-D1

### 17. PublishPolicy up-front validation
expected: PublishPolicy validates types/ranges, rejects public schemas, staging==publish, and reader==loader
result: pass
source: automated
coverage_id: 04-04-D2

### 18. Promotion SQL composition
expected: version()-first, single scoped DROP TABLE IF EXISTS (no wildcard/cascade), two-statement SET SCHEMA + RENAME, canonical catalog-discovered renames, in-transaction reader GRANT, rollback-and-PromotionFailed on error
result: pass
source: automated
coverage_id: 04-04-D3

### 19. D-68 publication gate hard-stop
expected: The D-68 gate hard-stops (PublicationValidationMissing) unless every layer has a PASS audit row, runs no DDL when it fails, and maps an unreadable audit table to AuditPrivilegeDenied
result: pass
source: automated
coverage_id: 04-04-D4

### 20. verify_reader_access separate connection + spatial query
expected: verify_reader_access opens a genuinely separate connection as policy.reader_user (never SET ROLE), discovers published tables, and runs a GiST-exercising spatial query bounded by Victoria's real WGS84 extent
result: pass
source: automated
coverage_id: 04-05-D1

### 21. Write-denial proof is a real executed INSERT
expected: The write-denial proof is a real executed INSERT ... DEFAULT VALUES expecting InsufficientPrivilege, never a has_table_privilege metadata shortcut
result: pass
source: automated
coverage_id: 04-05-D2

### 22. Non-denied write trips ReaderWriteNotDenied
expected: A reader whose write is NOT denied trips the security-critical ReaderWriteNotDenied and never returns a passing result
result: pass
source: automated
coverage_id: 04-05-D3

### 23. Missing reader role/password fails closed
expected: A missing reader role, missing USAGE, or unset VICMAP_READER_PASSWORD fails closed with ReaderRoleUnavailable before the proof runs, exposing no secret
result: pass
source: automated
coverage_id: 04-05-D4

### 24. Summary assembly links durable artifacts
expected: assemble_summary/write_summary link message fingerprint, artifact checksum, discovered layers, staging validation, published tables, and reader verification into a redacted summary.json, rejecting malformed or non-PASS inputs
result: pass
source: automated
coverage_id: 04-06-D1

### 25. publish_order.py CLI composition
expected: publish_order.py composes load-config -> gate+promote -> reader-verify -> summary as one ordered CLI, reading both passwords from the environment only, and exits 0 on success
result: pass
source: automated
coverage_id: 04-06-D2

### 26. EVID-02 exit-code contract at every failure boundary
expected: Every publish_order.py failure boundary (config, manifest, D-68 gate/audit, promotion, reader-verify, unexpected exception) returns a non-zero, boundary-named, secret-free exit
result: pass
source: automated
coverage_id: 04-06-D3

## Summary

total: 26
passed: 26
issues: 0
pending: 0
skipped: 0
blocked: 0

## Gaps

Both live negative-path proofs are now CLOSED — induced live against the real PostgreSQL server on 2026-09-25 by two fleshed-out `_LivePublishMixin` tests (previously skip-stubs), both green:

- **Induced-failure rollback (test 6) — CLOSED:** `tests.test_publish.LivePromotionRollbackTest.test_induced_failure_preserves_every_prior_table` provisions two throwaway layers, omits the second layer's staging table to force a mid-transaction failure, and asserts `PromotionFailed` plus the prior published table + its marker row survive, the second layer never appears, and the first layer's staging table rolled back (PUB-03). Green live.
- **Writable-role ReaderWriteNotDenied (test 7) — CLOSED:** `tests.test_publish.LiveReaderWriteNotDeniedTest.test_writable_reader_trips_reader_write_not_denied` provisions a disposable reader role deliberately granted INSERT (broken grant) and asserts `verify_reader_access` raises `ReaderWriteNotDenied` (T-04-02/CR-01). Both throwaway roles/schemas are dropped in cleanup. Green live.

Optional (non-blocking) live confirmation of canonical names (test 6): `nix develop path:. -c psql -c "\d+ vicmap.vmadd_address"` — expect vmadd_address_pkey, vmadd_address_geom_idx, and a NOT NULL geom column. The rename statements are now proven to execute against a real server (they run for layer A inside LivePromotionRollbackTest before the induced rollback).
