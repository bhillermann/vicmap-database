---
phase: 04-transactional-publication-and-access
verified: 2026-09-30T00:00:00Z
status: passed
score: 5/5 roadmap success criteria verified (0 present-behavior-unverified)
behavior_unverified: 0
overrides_applied: 0
re_verification:
  previous_status: passed
  previous_score: 5/5
  gaps_closed: []
  gaps_remaining: []
  regressions: []
  trigger: "Phase 05.1 (publish resume path, WINDOWS.md #16) substantially rewrote vicmap_acquire/publish.py, publish_order.py, db/provision_vicmap_loader.sql, vicmap_acquire/evidence.py and the four test modules this phase's must-haves live in, adding classify-before-DDL, promote_or_resume, and a per-layer vicmap_audit.publication marker written inside the promotion transaction. This re-run confirms Phase 4's own PUB-01..05/EVID-01/EVID-02 contract still holds under that rewrite, independent of Phase 05.1's own (separately verified, separately signed-off) resume-path goal."
covered_files:
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
covered_digest: "v2:sha256:3134dc22658d421ccafba5e8d1824063f2f49c3f50383b37d288388fc1cc4f4e"
---

# Phase 4: Transactional Publication and Access Verification Report (Re-Verification)

**Phase Goal:** The complete validated order becomes queryable in `vicmap` as one atomic publication that retains the last usable version on failure.
**Verified:** 2026-09-30 (re-verified at HEAD, post-Phase-05.1)
**Status:** passed
**Re-verification:** Yes — the prior `04-VERIFICATION.md` (status `passed`, 5/5, verified 2026-09-25) went stale because Phase 05.1 rewrote the shared `publish.py`/`publish_order.py`/`evidence.py`/provisioning-SQL modules this phase's must-haves live in, to add a publish-resume path (WINDOWS.md #16). This re-run independently re-derives every Phase 4 truth against the current code and re-executes the live negative-path tests; it does not re-verify Phase 05.1's own resume-path goal (separately verified in `05.1-VERIFICATION.md`, human-signed-off in `05.1-UAT.md`).

## Goal Achievement

### Observable Truths (Roadmap Success Criteria)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Only fully validated staging tables can be promoted, and every published target is schema-qualified under `vicmap`. | ✓ VERIFIED | `assert_all_layers_validated` (publish.py:425-472) still hard-stops on any missing/non-PASS row before any DDL, on its own read-only `_connect_for_audit_read` connection, raising `PublicationValidationMissing`/`AuditPrivilegeDenied`/`AuditReadFailed` — never `PromotionFailed` (D-90's boundary confinement, new in 05.1, does not weaken the gate). Every DDL/DML target is still composed via `sql.Identifier(policy.publish_schema, target)` (`_promote_layer`, publish.py:813-891). `promote_or_resume` (publish.py:1044-1092) calls this same gate unconditionally on every invocation, whether the run will promote or resume (D-89). Live: `vicmap.vmadd_address` (4,222,035 rows, re-counted live in this session: `SELECT count(*)` = 4222035) still exists, promoted from the original 2026-09-24 run. Tests: `PublicationGateTest`, `PromotionSqlCompositionTest`, all green (re-run in this session as part of the 226-test phase-module suite). |
| 2 | All order layers become visible together in one short transaction; an induced promotion failure exposes no partial order and preserves the previous usable tables. | ✓ VERIFIED | `_promote_in_transaction` (publish.py:944-999) is unchanged in structure from the original phase: one `_connect`, one cursor, every layer's `_promote_layer` + (new in 05.1) its durable `_record_publication` marker insert inside the same loop, one `connection.commit()` on success, `connection.rollback()` + re-raise on any exception (`PromotionFailed` for a non-`PublishFailure`, or the original `PublishFailure` unchanged). Marker-write failure (a duplicate key or a missing catalog row) rolls back the whole transaction exactly like a DDL failure — the marker was deliberately designed with no `ON CONFLICT`, so a misclassification cannot silently commit a partial promotion. Live-reproduced in this session: `LiveMultiLayerPromotionTest.test_all_layers_commit_together` (3 layers, asserts a single shared `pg_class.xmin` across all three — PASS) and `LivePromotionRollbackTest.test_induced_failure_preserves_every_prior_table` (forces a mid-transaction failure on a second layer, asserts the prior published table + its marker row survive unchanged and the second layer never appears — PASS), both re-run live against the real PostgreSQL server in this verification, not taken from SUMMARY.md. Offline: `PromotionRollbackCompositionTest.test_failure_rolls_back_and_raises_promotion_failed` still green. |
| 3 | The configured reader role can discover tables, select rows, and run a representative spatial query, but cannot write to published tables. | ✓ VERIFIED | `verify_reader_access` (publish.py:1136-1249) is unchanged from the original phase: fresh `psycopg.connect()` as `reader_user` (no `SET ROLE`), `information_schema.tables` discovery, a GiST-exercising query over Victoria's real WGS84 extent, and a real zero-row `INSERT ... SELECT ... WHERE false` write attempt that must raise `InsufficientPrivilege`; any other outcome (including a row-level `IntegrityError`) raises the security-critical `ReaderWriteNotDenied` and never returns a passing result. Live-reconfirmed in this session: `has_table_privilege` on the live server returns `t\|f` for reader USAGE/CREATE on schema `vicmap`; `LiveReaderWriteDenialTest.test_insufficient_privilege_path_returns_write_denied_true` re-run live and green. |
| 4 | A redacted run summary links the selected message, artifact checksum, discovered layers, staging validation, published tables, and reader verification. | ✓ VERIFIED | `assemble_summary`/`write_summary` (publish.py:1334-1591) still re-read durable artifacts (provenance sidecar, manifest.json, `vicmap_audit` rows) rather than threading an in-memory record, and still round-trip the six EVID-01 link facts through `SuccessEvent.publication_summary`. 05.1 added two new redacted fields (`"promotion"`: `performed`/`resumed`, `"published_at"`) without touching the original six; both are re-validated through the same closed scalar helpers (`evidence._require_utc_timestamp`, etc.) before the dict is returned. Live artifact `runs/OK0VUZ/20260924T083137Z/summary.json` (predates 05.1's new fields, from the original run) re-inspected directly in this session — still contains `message_fingerprint`, `artifact_sha256`, `manifest_sha256`, `layer_count`, `staging_validation`, `published_tables`, and a `reader` block, no path/password/DSN/raw message id. |
| 5 | Any stage failure returns a non-zero result identifying the failed boundary without exposing secrets. | ✓ VERIFIED | `publish_order.py`'s exception ladder (lines 206-239) is structurally unchanged: `AcquisitionFailure`/`ManifestFailure`/`(PublishFailure, StagingFailure)`/catch-all each map to `SafeFailure(reason, order_id=order_id)` and return 1; success returns 0. 05.1 closed the exact gap this truth's original evidence flagged as an open, disclosed limitation (WINDOWS.md #16): a post-commit failure no longer strands the run or gets misreported as `pub_promotion_failed` — `promote_or_resume`'s classify-before-DDL step now detects an already-published generation and resumes instead of re-entering promotion, and failure-boundary confinement (D-90/D-91/D-92) reserves `pub_promotion_failed` for the promotion transaction alone, giving `db_audit_read_failed`/`pub_generation_superseded`/`pub_generation_ambiguous`/`pub_summary_failed` to every other boundary. `.planning/WINDOWS.md` entry #16 is `status: "fixed"` (resolved 2026-09-29), independently confirmed by the live `LivePublishOrderResumeTest` suite (part of Phase 05.1's own separately-verified and human-signed-off scope — `05.1-VERIFICATION.md`, `05.1-UAT.md`: 4/4 UAT items passed, including the three PROHIB items governing this exact mechanism). This truth is now stronger than at original Phase 4 completion, not weaker. |

**Score:** 5/5 roadmap success criteria verified (0 present-behavior-unverified). All 7 requirement IDs (PUB-01..05, EVID-01, EVID-02) have direct code + live + test evidence, re-derived independently in this session against the post-05.1 codebase.

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `vicmap_acquire/publish.py` | `PublishPolicy`, `promote_order`, `assert_all_layers_validated`, `verify_reader_access`, `assemble_summary`, `write_summary` — plus 05.1's `promote_or_resume`, `classify_publication_state`, `classify_layer`, `order_verdict`, `_record_publication` | ✓ VERIFIED | All original exports present and structurally unchanged (`grep -n "^def \|^class "` confirms 40 top-level defs/classes, read in full); the 05.1 additions are layered around the original functions, not substituted for them — `promote_order` still exists with its exact historical signature (T-04-06 compatibility, publish.py:1001-1042) and is still the function `_promote_in_transaction` implements atomicity for. |
| `vicmap_acquire/evidence.py` | Phase-4 `Stage`/`ReasonCode` members, `SuccessEvent.publication_summary` | ✓ VERIFIED | Vocabulary grew from 20/54 (original phase-4 baseline) to 21 stages / 58 reason codes (05.1 added `PUBLICATION_SUMMARY` stage and 4 reason codes) — independently re-probed in this session (`len(Stage)==21`, `len(ReasonCode)==58`); all original Phase-4 members still present. |
| `vicmap.toml` + `read_mailbox.py` | `reader_user` config key, validated, distinct from loader | ✓ VERIFIED | Unchanged; `vicmap.toml`'s `reader_user = "vicmap_reader"` still present, `validate_database_policy` still rejects `reader_user == user`. |
| `db/provision_vicmap_loader.sql` | `vicmap_audit` schema/table (loader append-only), `vicmap_reader` LOGIN role, USAGE-only grant | ✓ VERIFIED | Original `vicmap_audit.staging_validation` block unchanged; 05.1 added a second table (`vicmap_audit.publication`, SELECT+INSERT only, no UPDATE/DELETE — same append-only shape). Live-reconfirmed in this session: `has_table_privilege('vicmap_loader','vicmap_audit.publication', ...)` = `t\|t\|f\|f` (SELECT/INSERT/UPDATE/DELETE); reader `has_schema_privilege('vicmap_reader','vicmap', ...)` = `t\|f` (USAGE/CREATE). |
| `flake.nix` | `VICMAP_READER_PASSWORD` injected via opnix | ✓ VERIFIED | Unchanged; confirmed present in this session's environment (`VICMAP_READER_PASSWORD` resolved, non-empty). |
| `vicmap_acquire/staging.py` (`record_validation`) | Durable PASS-row back-fill keyed by (run_ts, manifest_digest, target_table) | ✓ VERIFIED | Unchanged; still the exact table `assert_all_layers_validated`/`classify_publication_state` read from. |
| `publish_order.py` | Fourth CLI entry: load-config -> gate+promote(or resume) -> reader-verify -> summary, EVID-02 exit contract | ✓ VERIFIED | Composition now calls `publish.promote_or_resume` (the D-83 seam) in place of `promote_order` at the one call site, but the surrounding pipeline (reader-verify, validation re-read, summary assemble/write, exception ladder) is unchanged in shape and order. |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|----|--------|---------|
| `reader_user` (config) | `vicmap_reader` role (SQL) | Name equality | ✓ WIRED | Unchanged; re-confirmed by name and by live grant query in this session. |
| `staging.record_validation` | `vicmap_audit.staging_validation` | INSERT via `sql.Identifier`/binds | ✓ WIRED | Unchanged. |
| `publish.assert_all_layers_validated` | `vicmap_audit.staging_validation` | SELECT keyed by (run_ts, manifest_digest) | ✓ WIRED | Unchanged; still runs on every `promote_or_resume` invocation (D-89), including a resumed run. |
| `publish_order.py` | `publish.promote_or_resume` / `verify_reader_access` / `assemble_summary` / `write_summary` | Direct calls, ordered | ✓ WIRED | Confirmed at publish_order.py:155-200 (same linear order the original phase established, `promote_order` swapped for `promote_or_resume` at the one call site). |
| `evidence.py` ReasonCodes | `publish.py`/`staging.py` exception `.code` strings | String equality | ✓ WIRED | Cross-checked for both the original Phase-4 codes and 05.1's four additions (`AuditReadFailed`→`db_audit_read_failed`, `PublicationAmbiguous`→`pub_generation_ambiguous`, `PublicationSuperseded`→`pub_generation_superseded`, `PublicationSummaryFailed`→`pub_summary_failed`); all equal their `ReasonCode.value` counterparts. |
| `_promote_in_transaction` | `vicmap_audit.publication` | `_record_publication`, inside the same cursor/transaction as `_promote_layer` (D-79) | ✓ WIRED (new in 05.1, does not weaken PUB-02/03) | Confirmed at publish.py:966-982: the marker INSERT runs in the same per-layer loop, inside the same connection, before the loop's single `connection.commit()`. A marker-write failure rolls back exactly like a DDL failure (no separate commit boundary was introduced). |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|---------------------|--------|
| `summary.json` | `published_tables`, `staging_validation`, `reader` | Re-read from `PromotionResult`, `vicmap_audit` SELECT, `ReaderVerification` (not threaded in-memory) | Yes — live file inspected directly in this session, real row count (4,222,035) | FLOWING |
| `vicmap.vmadd_address` | rows | Live PostGIS table, promoted from `vicmap_staging` | Yes — re-counted live in this session: `SELECT count(*) FROM vicmap.vmadd_address` = 4222035 | FLOWING |
| `summary["promotion"]`/`summary["published_at"]` (05.1 addition, not an original Phase-4 field but traced for regression safety) | On a resumed run | `promotion_result_from_records`, reading only durable `vicmap_audit.publication` rows via `classify_publication_state` | Yes — never a live `SELECT version()` on the re-run's own connection (per Phase 05.1's own Level-4 trace, independently spot-checked here by reading `promotion_result_from_records`, publish.py:710-747) | FLOWING |

Note: `vicmap.vmadd_address` itself has no `vicmap_audit.publication` marker row (`SELECT * FROM vicmap_audit.publication WHERE target_table='vmadd_address'` returns 0 rows), because it was promoted on 2026-09-24, before Phase 05.1 introduced the marker table. This is expected and not a gap: a re-run of `publish_order.py` for this exact order today would classify it `UNPROVEN` (no marker, no staging table) and fail closed as `PublicationAmbiguous` rather than misinferring resumability from the table's mere existence — exactly the D-88 "never infer from staging-absence alone" guarantee 05.1 added. It does not affect any of the five roadmap truths above, all of which are independently proven either by the live table's row count (truth 1/4) or by fresh live-induced test fixtures (truths 2/3), not by this pre-existing production table's marker state.

### Behavioral Spot-Checks (re-executed independently in this session, not taken from SUMMARY.md)

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Live single-transaction, shared-xmin promotion (PUB-02) | `python -m unittest tests.test_publish.LiveMultiLayerPromotionTest -v` | `test_all_layers_commit_together ... ok` | ✓ PASS |
| Live induced-failure rollback preserves prior tables (PUB-03) | `python -m unittest tests.test_publish.LivePromotionRollbackTest -v` | `test_induced_failure_preserves_every_prior_table ... ok` | ✓ PASS |
| Live reader write-denial (PUB-04) | `python -m unittest tests.test_publish.LiveReaderWriteDenialTest -v` | `test_insufficient_privilege_path_returns_write_denied_true ... ok` | ✓ PASS |
| Live full CLI run exits 0, writes summary.json | `python -m unittest tests.test_publish.LivePublishOrderFullRunTest -v` | `test_full_run_exits_zero_and_writes_summary_json ... ok` | ✓ PASS |
| Phase-4-scoped offline+live suite (regression) | `python -m unittest tests.test_evidence tests.test_publish tests.test_publish_order tests.test_staging.DriverImportPolicyTest` | `Ran 226 tests ... OK` | ✓ PASS |
| Vocabulary totals (regression) | `python -c "from vicmap_acquire import evidence as e; print(len(e.Stage), len(e.ReasonCode))"` | `21 58` | ✓ PASS |
| Live loader grants on new marker table | `psql ... has_table_privilege('vicmap_loader','vicmap_audit.publication', 'SELECT'/'INSERT'/'UPDATE'/'DELETE')` | `t\|t\|f\|f` | ✓ PASS |
| Live reader schema grant | `psql ... has_schema_privilege('vicmap_reader','vicmap','USAGE'/'CREATE')` | `t\|f` | ✓ PASS |
| Live production row count (regression) | `psql ... SELECT count(*) FROM vicmap.vmadd_address` | `4222035` | ✓ PASS |
| No debt markers in phase-modified files | `grep -n -E "TBD|FIXME|XXX|TODO|HACK|PLACEHOLDER"` across all 8 shared/impl files | no matches (the two "placeholder" hits in `provision_vicmap_loader.sql` are intentional operator-facing password-substitution instructions, not code debt) | ✓ PASS |

The full workspace suite (`python -m unittest discover -s tests`) was not re-run a second time in this session — the operator-supplied evidence of `704 tests OK, 0 skipped` (matching the count independently re-confirmed by `05.1-VERIFICATION.md` in its own session) is accepted per the re-verification evidence-gate; this verification instead ran the four specific live test classes covering Phase 4's own truths (above) plus the phase-scoped 226-test module suite, both fresh in this session.

### Probe Execution

Not applicable — no `scripts/*/tests/probe-*.sh` convention in this project; this phase's live proof mechanism is the CLI + unittest live-DB test classes, already covered above.

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|--------------|--------|----------|
| PUB-01 | 04-02, 04-03, 04-04 | Publish only fully validated staging tables into `vicmap` | ✓ SATISFIED | `assert_all_layers_validated` gate, now run unconditionally by `promote_or_resume` on every invocation (D-89); live promotion of `vmadd_address` still gated on a PASS row. |
| PUB-02 | 04-04 | All layers visible together via one short transaction, no partial publication | ✓ SATISFIED | Single-transaction `_promote_in_transaction`; live shared-xmin test (`LiveMultiLayerPromotionTest`) re-run green this session. |
| PUB-03 | 04-04 | Publication preserves previous usable tables if promotion fails | ✓ SATISFIED | `PromotionRollbackCompositionTest` (offline) + `LivePromotionRollbackTest` (live, re-run green this session); scoped single-target `DROP TABLE IF EXISTS` unchanged. |
| PUB-04 | 04-02, 04-04, 04-05 | Reader role gets schema USAGE + table SELECT, no write | ✓ SATISFIED | Provisioning SQL unchanged for the reader role; in-transaction `GRANT SELECT` unchanged; live write-denial re-run green this session; live grants re-queried this session (`t\|f` schema-level). |
| PUB-05 | 04-05 | Reader can discover tables, read rows, run spatial query as non-owner | ✓ SATISFIED | `verify_reader_access` unchanged; live full-run test re-run green this session. |
| EVID-01 | 04-01, 04-06 | Redacted summary connecting message, checksum, layers, validation, published tables, reader query | ✓ SATISFIED | Live `summary.json` (original run, predates 05.1's new optional fields) re-inspected directly; all six original link facts present, no secrets; `assemble_summary`'s redaction contract unchanged for these six fields. |
| EVID-02 | 04-01, 04-06 | Every failed stage returns non-zero, names the boundary, no secrets | ✓ SATISFIED (strengthened) | 05.1 closed the one previously-disclosed limitation (retry-after-partial-failure misreported as `pub_promotion_failed`, WINDOWS.md #16) without altering the exception ladder's shape; `publish_order.py`'s ladder still returns 1 on every failure path with the correctly narrowed reason code. |

No orphaned requirements: `.planning/REQUIREMENTS.md`'s Traceability table maps exactly PUB-01..05, EVID-01, EVID-02 to Phase 4, all now shown `[x]` Complete — the prior verification's "stale checklist" advisory has been resolved (REQUIREMENTS.md was updated after phase completion).

### Anti-Patterns Found

None. No `TBD`/`FIXME`/`XXX`/`TODO`/`HACK`/`PLACEHOLDER` markers in any of the shared/impl files this phase's must-haves depend on (`vicmap_acquire/publish.py`, `vicmap_acquire/evidence.py`, `publish_order.py`, `db/provision_vicmap_loader.sql`, `tests/test_publish.py`, `tests/test_publish_order.py`, `tests/test_staging.py`, `tests/test_evidence.py`). The two "placeholder" hits in `db/provision_vicmap_loader.sql` remain the same intentional by-hand operator instructions noted in the original verification.

### Deviations / Advisories (disclosed, non-blocking)

1. **WINDOWS.md #16 — now closed.** The original verification's sole disclosed advisory (no resume path after a committed promotion, stranding a post-commit failure and misreporting it as `pub_promotion_failed`) is now `status: "fixed"` (resolved 2026-09-29 in Phase 05.1), independently confirmed here by re-running the four live test classes covering Phase 4's own truths and by reading `promote_or_resume`'s classify-before-DDL logic directly. This advisory is retired, not carried forward.
2. **04-VALIDATION.md — now filled in.** The original verification's second advisory (an unfilled validation template) is resolved: `04-VALIDATION.md` now shows `status: validated`, `nyquist_compliant: true`, a completed per-task verification map, and two validation audit entries (`Ran 621 tests ... OK`, 0 skipped, all `Live*` classes executed). This advisory is retired, not carried forward.
3. **`vicmap.vmadd_address` predates the publication marker table (informational only).** See the Data-Flow Trace note above — the live production table has no `vicmap_audit.publication` row because it was promoted before 05.1 introduced that table. Not a gap against any of the five roadmap truths; flagged for awareness only, since a future re-run of this exact order would need an operator to resolve the resulting `AMBIGUOUS` classification (a Phase 05.1 concern, not a Phase 4 regression).

### Human Verification Required

None. All five roadmap truths and all seven requirement IDs were re-derived from source code read directly in this session, corroborated by live tests re-executed against the real PostgreSQL server in this session (not taken from SUMMARY.md or prior VERIFICATION.md claims), and cross-checked against Phase 05.1's own separately-verified, human-signed-off resume-path evidence (`05.1-VERIFICATION.md`, `05.1-UAT.md` — 4/4 UAT items passed, including PROHIB-11/12/13 governing exactly the marker-provenance and fail-closed-DDL guarantees this phase's PUB-02/03 truths depend on for correctness under the rewrite).

### Gaps Summary

No gaps. All 5 roadmap success criteria and all 7 requirement IDs (PUB-01..05, EVID-01, EVID-02) remain backed by source-code inspection, passing automated tests (offline behavioral tests plus live-induced negative/rollback paths, all re-executed independently in this session), and the same genuine, directly-inspected live production artifact from the original phase (`runs/OK0VUZ/20260924T083137Z/summary.json`, `vicmap.vmadd_address` with 4,222,035 rows, re-counted live in this session). The phase goal — "the complete validated order becomes queryable in `vicmap` as one atomic publication that retains the last usable version on failure" — remains achieved under the Phase 05.1 rewrite; Phase 05.1 strengthened truth 5 (EVID-02) without weakening any of the other four, and the shared-code changes introduced no regression in PUB-02's single-transaction atomicity or PUB-03's rollback preservation, both re-proven live in this session.

Status is `passed`: the digest staleness that triggered this re-verification has been resolved by re-deriving every truth against the current code and re-running the live tests fresh; no prior human sign-off has been downgraded.

---

_Verified: 2026-09-30 (re-verified at HEAD, post-Phase-05.1)_
_Verifier: Claude (gsd-verifier)_
