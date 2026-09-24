---
phase: 04-transactional-publication-and-access
verified: 2026-09-25T00:00:00Z
status: human_needed
score: 5/5 roadmap success criteria verified (0 present-behavior-unverified)
behavior_unverified: 0
overrides_applied: 0
covered_files:
  - ".planning/REQUIREMENTS.md"
  - ".planning/phases/04-transactional-publication-and-access/04-01-PLAN.md"
  - ".planning/phases/04-transactional-publication-and-access/04-01-SUMMARY.md"
  - ".planning/phases/04-transactional-publication-and-access/04-02-PLAN.md"
  - ".planning/phases/04-transactional-publication-and-access/04-02-SUMMARY.md"
  - ".planning/phases/04-transactional-publication-and-access/04-03-PLAN.md"
  - ".planning/phases/04-transactional-publication-and-access/04-03-SUMMARY.md"
  - ".planning/phases/04-transactional-publication-and-access/04-04-PLAN.md"
  - ".planning/phases/04-transactional-publication-and-access/04-04-SUMMARY.md"
  - ".planning/phases/04-transactional-publication-and-access/04-05-PLAN.md"
  - ".planning/phases/04-transactional-publication-and-access/04-05-SUMMARY.md"
  - ".planning/phases/04-transactional-publication-and-access/04-06-PLAN.md"
  - ".planning/phases/04-transactional-publication-and-access/04-06-SUMMARY.md"
  - ".planning/phases/04-transactional-publication-and-access/04-RESUME-LIVE.md"
  - ".planning/phases/04-transactional-publication-and-access/04-UAT.md"
  - ".planning/phases/04-transactional-publication-and-access/04-VALIDATION.md"
  - "db/provision_vicmap_loader.sql"
  - "flake.nix"
  - "publish_order.py"
  - "read_mailbox.py"
  - "stage_order.py"
  - "tests/test_evidence.py"
  - "tests/test_manifest.py"
  - "tests/test_publish.py"
  - "tests/test_publish_order.py"
  - "tests/test_staging.py"
  - "vicmap.toml"
  - "vicmap_acquire/evidence.py"
  - "vicmap_acquire/manifest.py"
  - "vicmap_acquire/publish.py"
  - "vicmap_acquire/staging.py"
covered_digest: "v1:sha256:74c8688791c266aaa2a6da4996c893a4212b9fce49d876c6e086994167d47d2b"
human_verification:
  - test: "Induce a mid-transaction promotion failure against a real staged order (e.g. force a rename collision on the second of two layers) and confirm every prior vicmap.* table survives untouched (PUB-03's negative path)."
    expected: "Rollback leaves every previously-published table exactly as it was; the failed run reports pub_promotion_failed; no table is left half-renamed or half-dropped."
    why_human: "The rollback-preserves-prior-tables invariant is proven at the unit level (PromotionRollbackCompositionTest, mocked connection, asserts rollback_count==1/commit_count==1) and the happy path is proven live (OK0VUZ -> vicmap.vmadd_address), but no live negative-path induction against the real PostgreSQL server has been run this session or the prior live session (WINDOWS.md #11, 04-UAT.md Gaps item 1). This needs a live DB and a deliberately broken second layer to observe."
  - test: "Grant a disposable reader-equivalent role INSERT on a published table and confirm verify_reader_access raises ReaderWriteNotDenied against the real server, then immediately revoke."
    expected: "The function raises ReaderWriteNotDenied (never returns a passing ReaderVerification) when a write actually succeeds."
    why_human: "Proven at the unit level with a fake connection (ReaderVerificationTest.test_writable_reader_raises_reader_write_not_denied) and the negative half of the live proof (real write correctly denied for the true vicmap_reader role) is proven live, but the specific broken-grant-model trip has never been induced against a real PostgreSQL server (WINDOWS.md #14, 04-UAT.md Gaps item 2). Security-critical: this is the check that catches a broken grant model."
  - test: "Confirm the canonical constraint/index names on the live-promoted table."
    expected: "`\\d+ vicmap.vmadd_address` shows vmadd_address_pkey, vmadd_address_geom_idx, and a NOT NULL geom column."
    why_human: "The live UAT run promoted vmadd_address successfully but did not re-query the catalog to confirm the canonical rename took effect post-commit; the composition is proven by automated test 18 (offline, mocked cursor) and the promotion completed without error (implying the rename statements executed), but this is optional live confirmation per 04-UAT.md Gaps."
---

# Phase 4: Transactional Publication and Access Verification Report

**Phase Goal:** Atomically publish the order into `vicmap` and prove non-owner access with redacted evidence.
**Verified:** 2026-09-25
**Status:** human_needed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths (Roadmap Success Criteria)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Only fully validated staging tables can be promoted, and every published target is schema-qualified under `vicmap`. | VERIFIED | Code: `assert_all_layers_validated` (publish.py:247) hard-stops on any missing/non-PASS row before any DDL; every DDL/DML target composed via `sql.Identifier(policy.publish_schema, target)` (publish.py:381-437). Live: `vicmap.vmadd_address` (4,222,035 rows) exists post-run (runs/OK0VUZ/20260924T083137Z/summary.json). Test: `PublicationGateTest`, `tests.test_publish.PromotionSqlCompositionTest`, all green. |
| 2 | All order layers become visible together in one short transaction; an induced promotion failure exposes no partial order and preserves the previous usable tables. | VERIFIED | Code: `promote_order` (publish.py:440-496) loops every layer inside one connection/transaction, commits once, rolls back and re-raises `PromotionFailed` on any exception. Behavioral test: `PromotionRollbackCompositionTest.test_failure_rolls_back_and_raises_promotion_failed` induces a mid-loop failure (fails on `GRANT SELECT`) against a recording fake connection and asserts `rollback_count==1` and the final commit never ran (`commit_count==1`, only `_connect`'s setup commit). Live: happy path proven end-to-end (single-layer order). **Live negative-path induction (multi-layer rollback against a real server) was not performed — see Human Verification #1.** |
| 3 | The configured reader role can discover tables, select rows, and run a representative spatial query, but cannot write to published tables. | VERIFIED | Code: `verify_reader_access` (publish.py:540-635) opens a fresh `psycopg.connect()` as `reader_user` (no SET ROLE), discovers via `information_schema.tables`, runs a GiST-exercising query over Victoria's real WGS84 extent, and attempts a real `INSERT ... DEFAULT VALUES` expecting `InsufficientPrivilege`; the not-denied branch raises `ReaderWriteNotDenied` and never returns a pass. Live: reader discovered 1 table, spatial query returned 10 rows, real INSERT denied (`reader_write_denied: true` in summary.json). Behavioral test: `ReaderVerificationTest.test_writable_reader_raises_reader_write_not_denied` proves the not-denied hard-stop with a fake connection whose INSERT succeeds. **The negative (broken-grant) trip was not induced live — see Human Verification #2.** |
| 4 | A redacted run summary links the selected message, artifact checksum, discovered layers, staging validation, published tables, and reader verification. | VERIFIED | Live artifact inspected directly: `runs/OK0VUZ/20260924T083137Z/summary.json` contains `message_fingerprint`, `artifact_sha256`, `manifest_sha256`, `layer_count`, `staging_validation` (per-layer row_count/spatial/srid/geometry_type/repaired_count), `published_tables`, and a `reader` block (tables_discovered, spatial_query_row_count, write_denied). No path, password, DSN, or raw message id present. `assemble_summary`/`write_summary` (publish.py:717-883) re-read durable artifacts (provenance sidecar, manifest.json, vicmap_audit rows) rather than threading an in-memory record (D-76). |
| 5 | Any stage failure returns a non-zero result identifying the failed boundary without exposing secrets. | VERIFIED | `publish_order.py`'s exception ladder (lines ~189-222) maps `AcquisitionFailure`/`ManifestFailure`/`PublishFailure`/`StagingFailure`/catch-all to `SafeFailure(reason, order_id=order_id)` and returns 1 in every branch; success returns 0. `tests/test_publish_order.py` (24 tests, all green) exercises every named failure boundary (config_invalid, manifest, db_audit gate, db_publish, db_reader_verify, internal_failure) and asserts the correct stage/reason and a return of 1. **Caveat (not a truth failure, but a disclosed open limitation):** WINDOWS.md #16 documents that a failure in a *post-commit* step (reader-verify/summary) strands the run with no resume path — a subsequent retry re-enters `promote_order`, hits `UndefinedTable` on the already-consumed staging table, and is misreported as `pub_promotion_failed` rather than the true cause. This affects only the *retry-after-partial-failure* scenario, which falls under OPS-03 ("retry or resume under an explicit recovery policy") — an explicitly deferred Future Requirement, not v0.1 scope. Recorded as an advisory, not a gap against EVID-02's single-run contract. |

**Score:** 5/5 roadmap success criteria verified (0 present-behavior-unverified). All 7 requirement IDs (PUB-01..05, EVID-01, EVID-02) have direct code + live + test evidence.

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `vicmap_acquire/evidence.py` | 3 new Stage members, 7 new ReasonCode members with `_FAILURE_POLICY`, `SuccessEvent.publication_summary` | VERIFIED | 20 stages / 54 reasons total (baseline was larger than plan's estimate; all Phase-4-specific members present and confirmed live via `python -c` probe). `reason_stage_vocabulary()` total over all ReasonCodes. |
| `vicmap.toml` + `read_mailbox.py` | `reader_user` config key, validated, distinct from loader | VERIFIED | `vicmap.toml:48` carries `reader_user = "vicmap_reader"`; `load_database_config` returns it; `validate_database_policy` rejects `reader_user == user` (read_mailbox.py:501-503). |
| `db/provision_vicmap_loader.sql` | `vicmap_audit` schema/table (loader append-only), `vicmap_reader` LOGIN role, USAGE-only grant | VERIFIED | All statements present and structurally correct; live-confirmed (04-UAT.md test 3): loader INSERT=true/UPDATE=false, reader USAGE=true/CREATE=false. |
| `flake.nix` | `VICMAP_READER_PASSWORD` injected via opnix | VERIFIED | `flake.nix:37`, mirrors `VICMAP_DB_PASSWORD` exactly; live-confirmed resolving in devshell (04-UAT.md test 4). |
| `vicmap_acquire/staging.py` (`record_validation`, `manifest_digest`) | Durable PASS-row back-fill keyed by (run_ts, manifest_digest, target_table) | VERIFIED (indirect live proof) | Code present, safe-SQL composed (`sql.Identifier`/bind params), closed failures `AuditPrivilegeDenied`/`AuditRecordFailed`. The dedicated live unit test (`AuditValidationRecordTest`) was not witnessed passing this or the prior session (WINDOWS.md #8) — however, the live promotion gate (`assert_all_layers_validated`) *requires* a PASS row to proceed, and the live run did promote, so `record_validation` functioning correctly is a necessary precondition of the observed live success. |
| `vicmap_acquire/publish.py` | `PublishPolicy`, `promote_order`, `assert_all_layers_validated`, `verify_reader_access`, `assemble_summary`, `write_summary` | VERIFIED | All present, driver-isolated alongside `staging.py` (`DriverImportPolicyTest` exemption widened and green), fully wired, exercised by both offline tests and one live full run. |
| `publish_order.py` | Fourth one-CLI-per-phase entry: load-config -> gate+promote -> reader-verify -> summary, EVID-02 exit contract | VERIFIED | Composition matches the plan exactly; both passwords read from env only; exception ladder mirrors `stage_order.py`'s shape. Live-run exit code 0 inferred from `summary.json` presence + absence of a failure line (not a captured literal `$?`, but a reasonable inference corroborated by 24 passing exit-code unit tests). |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|----|--------|---------|
| `reader_user` (config) | `vicmap_reader` role (SQL) | Name equality | WIRED | `vicmap.toml`'s `reader_user = "vicmap_reader"` equals `db/provision_vicmap_loader.sql`'s `CREATE ROLE vicmap_reader LOGIN`. |
| `staging.record_validation` | `vicmap_audit.staging_validation` | INSERT via `sql.Identifier`/binds | WIRED | Column set matches the table 04-02 provisioned exactly. |
| `publish.assert_all_layers_validated` | `vicmap_audit.staging_validation` | SELECT keyed by (run_ts, manifest_digest) | WIRED | Same table/key as `record_validation`'s write; live-consistent (promotion succeeded only because a PASS row existed). |
| `publish_order.py` | `publish.promote_order` / `verify_reader_access` / `assemble_summary` / `write_summary` | Direct calls, ordered | WIRED | Confirmed by source inspection and the live run producing `summary.json`. |
| `evidence.py` ReasonCodes | `publish.py`/`staging.py` exception `.code` strings | String equality | WIRED | Cross-checked: `PromotionFailed.code == 'pub_promotion_failed'`, `ReaderWriteNotDenied.code == 'reader_write_not_denied'`, etc. — all equal their `ReasonCode.value` counterparts (confirmed via test run and source read). |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|---------------------|--------|
| `summary.json` | `published_tables`, `staging_validation`, `reader` | Re-read from `PromotionResult`, `vicmap_audit` SELECT, `ReaderVerification` (not threaded in-memory) | Yes — live file inspected directly, real row counts (4,222,035) and real checksums | FLOWING |
| `vicmap.vmadd_address` | rows | Live PostGIS table, promoted from `vicmap_staging` | Yes — 4.22M rows confirmed in 04-UAT.md | FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Full offline suite (baseline regression) | `nix develop path:. -c python -m unittest discover -s tests -p 'test_*.py'` | `Ran 619 tests ... OK (skipped=43)` | PASS |
| Phase-4-specific suite | `nix develop path:. -c python -m unittest tests.test_evidence tests.test_publish tests.test_publish_order tests.test_staging.DriverImportPolicyTest -v` | `Ran 144 tests ... OK (skipped=7)` | PASS |
| Live vocabulary probe | `python -c "from vicmap_acquire import evidence as e; ..."` (Stage/ReasonCode/_FAILURE_POLICY checks) | `vocab total ok`, all Phase-4 members present with correct hints | PASS |
| Live config probe | `python -c "... r.load_database_config(...)"` | `reader_user vicmap_reader user vicmap_loader` | PASS |
| Live artifact inspection | `cat runs/OK0VUZ/20260924T083137Z/summary.json` | Redacted JSON with all six EVID-01 facts, no secrets | PASS |

Note: this session cannot reach a live PostgreSQL server (no socket). All "live" evidence above is either (a) a durable file/artifact left by the prior live session's `publish_order.py` run, inspected directly in this session, or (b) claims from `04-UAT.md` corroborated by that durable artifact and by the offline test suite. No live DB re-execution was attempted or needed.

### Probe Execution

Not applicable — no `scripts/*/tests/probe-*.sh` convention in this project; the phase's live proof mechanism is the CLI + UAT process, already covered above.

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|--------------|--------|----------|
| PUB-01 | 04-02, 04-03, 04-04 | Publish only fully validated staging tables into `vicmap` | SATISFIED | `assert_all_layers_validated` gate; live promotion of `vmadd_address` gated on a PASS row. |
| PUB-02 | 04-04 | All layers visible together via one short transaction, no partial publication | SATISFIED | Single-transaction `promote_order`; behavioral rollback test; live single-layer success. |
| PUB-03 | 04-04 | Publication preserves previous usable tables if promotion fails | SATISFIED (unit-proven; live negative path outstanding — Human Verification #1) | `PromotionRollbackCompositionTest`; scoped single-target `DROP TABLE IF EXISTS`. |
| PUB-04 | 04-02, 04-04, 04-05 | Reader role gets schema USAGE + table SELECT, no write | SATISFIED | Provisioning SQL + in-transaction `GRANT SELECT`; live-confirmed write denial. |
| PUB-05 | 04-05 | Reader can discover tables, read rows, run spatial query as non-owner | SATISFIED | `verify_reader_access`; live discovery (1 table) + spatial query (10 rows). |
| EVID-01 | 04-01, 04-06 | Redacted summary connecting message, checksum, layers, validation, published tables, reader query | SATISFIED | Live `summary.json` directly inspected; contains all six linked facts, no secrets. |
| EVID-02 | 04-01, 04-06 | Every failed stage returns non-zero, names the boundary, no secrets | SATISFIED (single-run contract proven; retry-after-partial-failure scenario is an open, disclosed, out-of-v0.1-scope limitation — WINDOWS.md #16) | 24 passing exit-code unit tests in `tests/test_publish_order.py`; live success path exit-0 inferred. |

No orphaned requirements: `.planning/REQUIREMENTS.md`'s Traceability table maps exactly PUB-01..05, EVID-01, EVID-02 to Phase 4, matching the requirement IDs declared across all six plans' frontmatter. **Note:** `.planning/REQUIREMENTS.md` itself still shows these seven items as unchecked `[ ]` / status "Pending" — this is a stale-documentation gap (the checklist was not updated after phase completion), not a functional gap. Flagged for the orchestrator to update as part of phase completion.

### Anti-Patterns Found

None. No `TBD`/`FIXME`/`XXX`/`TODO`/`HACK` markers in any Phase-4-modified file. The two "placeholder" hits in `db/provision_vicmap_loader.sql` are intentional operator instructions ("Replace the placeholder below with the real password before running this script by hand") for a by-hand superuser script that must never carry a committed credential — not a code debt marker.

### Deviations / Advisories (disclosed, non-blocking)

1. **WINDOWS.md #16 (open, deviation):** No resume path after a committed promotion. A failure in a *post-commit* step (reader-verify, read-validations, assemble-summary, write-summary) strands the run: a retry re-enters `promote_order`, hits `UndefinedTable` on the already-consumed staging table, and is misreported as `pub_promotion_failed`. This affects EVID-02's "clearly identifies the failed boundary" guarantee only in the retry-after-partial-failure case. Retry/resume policy is explicitly out of v0.1 scope (Future Requirement OPS-03: "Interrupted downloads and loads can retry or resume under an explicit recovery policy"). Not treated as a phase-blocking gap, but the window is open and should be tracked toward OPS-03.
2. **04-VALIDATION.md is an unfilled template.** Its frontmatter still reads `status: draft`, `nyquist_compliant: false`, and its body retains placeholder tokens (`{pytest 7.x / jest 29.x / vitest / go test / other}`, `REQ-{XX}`, `~04 seconds`) rather than actual Phase-4-specific content. This does not affect the phase's functional goal (the actual test suite is real and passes), but it means the Nyquist validation record was never substantively completed for this phase — worth closing out procedurally.
3. **WINDOWS.md #8-#15 (open, unrun-verify):** The dedicated `Live*` test classes in `tests/test_staging.py`/`tests/test_publish.py` (e.g. `LivePromoteOneLayerTest`, `LiveMultiLayerPromotionTest`, `LivePromotionRollbackTest`, `LiveReaderVerificationTest`, `LiveReaderWriteDenialTest`, `LiveReaderWriteNotDeniedTest`) are unconditional-skip stub placeholders — even with both DSN env vars set, the test body immediately calls `self.skipTest(...)`. These were never fleshed out; the actual live proof instead came from directly invoking `publish_order.py` once against the real order (successful happy path only). This is transparently disclosed in `04-UAT.md`'s own Gaps section and in `04-RESUME-LIVE.md` ("currently skip-guarded placeholders — flesh out from stubs"). Two specific negative-path behaviors (induced rollback, writable-reader trip) were never exercised against a real server — see Human Verification below.

### Human Verification Required

3 items — see frontmatter `human_verification` for full detail. Summary:

1. **Live-induce a mid-transaction promotion failure** and confirm prior tables survive (PUB-03 negative path never run against a real server).
2. **Live-induce a broken reader grant** (grant INSERT to a disposable role) and confirm `ReaderWriteNotDenied` trips (security-critical negative path never run against a real server).
3. **Optional: re-query the live catalog** to confirm canonical constraint/index names on `vicmap.vmadd_address` (composition proven only by mocked test + inferred from a clean promotion).

All three are explicitly flagged as optional/deferred hardening in `04-UAT.md`'s own Gaps section (not hidden), and none block the phase's core PUB-01..05/EVID-01/EVID-02 goal, which is proven by a combination of code inspection, a real end-to-end live run with a directly-inspected `summary.json`, and 763 total passing tests (619 general + 144 Phase-4-focused, overlapping). They are surfaced here because they are genuine gaps in negative-path live proof for security-critical and data-preservation invariants, and the adversarial verification stance requires surfacing rather than silently accepting the offline-only proof as sufficient for a one-way-door production promotion capability.

### Gaps Summary

No BLOCKER-level gaps. All 5 roadmap success criteria and all 7 requirement IDs (PUB-01..05, EVID-01, EVID-02) are backed by a combination of source-code inspection, passing automated tests (offline behavioral tests for negative/rollback paths; live artifact inspection for the happy path), and a genuine, directly-inspected live production artifact (`runs/OK0VUZ/20260924T083137Z/summary.json`, `vicmap.vmadd_address` with 4.22M rows). The phase goal — "Atomically publish the order into `vicmap` and prove non-owner access with redacted evidence" — is achieved.

Status is `human_needed` rather than `passed` solely because two security/data-preservation-critical negative paths (induced rollback, writable-reader trip) have only unit-level (mocked-connection) proof and have never been induced against a real PostgreSQL server, despite being the specific behaviors the phase's own threat model (T-04-01, T-04-02, T-04-04) calls "critical". This is consistent with `04-UAT.md`'s own disclosed Gaps section — this verification does not discover anything hidden, it elevates two already-disclosed optional-hardening items to formal human-verification status per the adversarial verification protocol for security-critical invariants.

---

_Verified: 2026-09-25_
_Verifier: Claude (gsd-verifier)_
