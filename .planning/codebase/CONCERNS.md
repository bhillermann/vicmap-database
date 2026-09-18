# Codebase Concerns

**Analysis Date:** 2026-09-18

## Tech Debt

**Missing PostGIS Integration (Phase 3 — Not Started):**
- Issue: The entire database layer (Phase 3 and beyond) has not been implemented. The pipeline currently gets from email → archive extraction → layer discovery → manifest, but cannot load data into PostGIS.
- Files: None yet; `vicmap_acquire/` has no database module
- Impact: v0.1 cannot complete its core mission: no tables are loaded, no atomicity/promotion exists, no consumer access is possible
- Fix approach: Implement Phase 3 (Validated PostGIS Staging) with connection pooling, transaction management, and staging table validation before promotion

**Subprocess Timeout Handling in Discovery:**
- Issue: `ogrinfo` subprocess call in `vicmap_acquire/discovery.py:233` has a `timeout_seconds` policy but no graceful handling of slow/hung processes on high-latency or resource-constrained systems
- Files: `vicmap_acquire/discovery.py` (lines 233-244)
- Impact: On a busy system or slow storage, discovery may timeout unexpectedly; timeout is a hard error with no retry/escalation
- Fix approach: Consider implementing exponential backoff or a pre-check for dataset size before invoking ogrinfo

**Extraction Memory Profile Not Validated:**
- Issue: While `extract_artifact` streams output using 1 MiB chunks (preventing memory exhaustion), the pre-validation in `_validate_members` loads the complete `zipfile.infolist()` into memory before extraction begins
- Files: `vicmap_acquire/extraction.py` (lines 318-329)
- Impact: For an archive with millions of entries, `infolist()` could consume significant memory; `max_member_count` policy provides a ceiling (tested at 4000), but real Vicmap orders are unknown
- Fix approach: If future deliveries contain very large member counts, stream infolist inspection instead of materializing the full list

**Hard-Coded Order ID Limit in `discover_order.py`:**
- Issue: Main entry point requires `allowed_order_ids` to contain exactly one order (line 124 in STATE.md decisions document)
- Files: `discover_order.py`
- Impact: Multi-order deliveries cannot be processed in one run; batching or multi-order support deferred to Phase 2-06
- Fix approach: Implement flexible order selection and queueing in Phase 2-06 per ROADMAP.md

## Known Bugs

**Compression Ratio Calibration Thinness:**
- Symptoms: The real 233 MB Vicmap delivery (Order_OK0VUZ) has small OpenFileGDB index files (.gdbtablx/.spx/.atx) that compress at ~139x ratio; `vicmap.toml` currently caps at 200x, leaving only ~1.44x headroom
- Files: `vicmap.toml` (line 26), `tests/test_extraction.py` (ShippedCeilingCalibrationTest)
- Trigger: Future Vicmap delivery with slightly more redundant index files could exceed the 200x ceiling
- Workaround: Increase `max_compression_ratio` if delivery fails with `archive_ceiling_exceeded`; see 02-REVIEW-FIX.md for calibration methodology

**Case-Sensitive Extension Recognition Fixed, but Worth Monitoring:**
- Symptoms: Earlier discovery code did not use `casefold()` on file extensions, risking rejection of `.GDB` vs `.gdb`
- Files: `vicmap_acquire/discovery.py` (line 163, now normalized via `path.suffix.casefold()`)
- Trigger: Already fixed; included for historical context
- Current state: ✓ RESOLVED in Phase 02

## Security Considerations

**Graph Application Scope (Tenant-Wide Exposure):**
- Risk: The O365 application credentials in `flake.nix` / opnix / runtime environment grant `Mail.Read` permission, which is tenant-wide by default and not scoped to a single mailbox. An attacker or misconfiguration could access `automations@vegetationlink.com.au`'s entire mailbox history.
- Files: `vicmap_acquire/graph.py` (lines 80-112, account setup); credentials sourced from environment
- Current mitigation: Operator has explicitly confirmed (2026-09-14) that the tenant mailbox access restriction is in place at the Microsoft Entra level (see STATE.md line 113-114); `read_mailbox.py` restricts mailbox address at runtime (line 146)
- Recommendations: Document tenant-scope restriction as a verified prerequisite; add a live test that confirms `mailbox_address` matches the expected automation mailbox after authentication succeeds

**Email Parser HTML Visibility (WR-01 — RESOLVED):**
- Risk: Previously, malformed/missing DMARC headers could let unsigned messages pass alignment checks
- Files: `vicmap_acquire/origin.py`
- Current state: ✓ RESOLVED in Phase 01; all authentication checks now fail closed on absence

**Repository-Local Secrets (WR-04 — Partially Resolved):**
- Risk: Application credentials and opnix tokens are currently inside the checkout via `flake.nix`/`.direnv` environment setup
- Files: `flake.nix` (credentials injected at runtime), `.direnv` (env loading)
- Current mitigation: Credentials are NOT stored as static files; they are injected at runtime from opnix/1Password
- Recommendations: Before production deployment, rotate any exposed tokens and move credential sourcing outside the checkout entirely (e.g., systemd environment files, process-level secrets management)

**Message Fingerprinting for Redaction (Secure):**
- Risk: If message subjects/bodies are leaked in logs, senders and attachment details are exposed
- Files: `vicmap_acquire/evidence.py` (fingerprint computation, lines 24-34); `read_mailbox.py` (log redaction via SuccessEvent/SafeFailure)
- Current mitigation: ✓ Message identities are fingerprinted (8-64 hex chars configurable), never exposed raw; stdout redaction enforced via evidence.py's SafeFailure/SuccessEvent machinery
- Recommendations: No change needed; already secure per design

## Performance Bottlenecks

**Synchronous Sequential Discovery:**
- Problem: `discover_layers` calls `ogrinfo` once per dataset sequentially; for large Vicmap orders with multiple GDB packages, this is O(n) in dataset count
- Files: `vicmap_acquire/discovery.py` (lines 220-280, single-threaded loop over datasets)
- Cause: Subprocess invocations are blocking; no parallelism implemented
- Improvement path: Implement concurrent subprocess calls (e.g., ThreadPoolExecutor) if multi-dataset orders become common; currently deferred because real Vicmap orders are unknown

**Whole-Infolist Materialization:**
- Problem: `zipfile.infolist()` loads the entire member list into memory before any extraction writes begin
- Files: `vicmap_acquire/extraction.py` (line 325)
- Cause: Python's zipfile API requires the full list for validation before opening file handles
- Improvement path: Not easily parallelizable; acceptable for current scope (Vicmap orders with thousands of members expected to be rare)

**No Connection Pooling for Future PostGIS Loads:**
- Problem: Phase 3 has not been implemented, so no database connection strategy exists yet
- Files: None (Phase 3 not started)
- Cause: Deferred pending architecture design
- Improvement path: When implementing Phase 3, use connection pooling (e.g., psycopg3 with asyncpg or pgbouncer) to avoid per-table connection overhead during multi-layer loads

## Fragile Areas

**Naming Normalization (Now Hardened):**
- Files: `vicmap_acquire/naming.py`, `tests/test_naming.py` (now includes independent Oracle test)
- Why fragile: Reserved keyword list (`_RESERVED_KEYWORDS`) was hand-transcribed from PostgreSQL documentation; a missed keyword or future PostgreSQL update could cause collisions
- Safe modification: Maintain the Oracle test (`PostgresKeywordOracleTest`) which queries live PostgreSQL's `pg_get_keywords()` whenever a server is available; update the keyword list only when Oracle test fails
- Test coverage: ✓ Full coverage with 41 tests including Oracle validation

**Archive Extraction Hardening (Now Complete):**
- Files: `vicmap_acquire/extraction.py` (lines 181-268, validation logic)
- Why fragile: Untrusted ZIP files can exploit extraction via path traversal, symlinks, compression bombs, or duplicate names
- Safe modification: All guards are in `_reject_unsafe_member` and `_validate_members` — any path change must preserve: (a) path traversal rejection (`..`, `/`, `\`), (b) absolute path rejection, (c) symlink rejection on Unix, (d) duplicate-name detection (including case-folding for case-insensitive filesystems), (e) per-member and total-bytes ceilings
- Test coverage: ✓ Comprehensive; `tests/test_extraction.py` covers traversal, symlinks, duplicates, and ceiling violations

**URL Validation in Download (Now Hardened):**
- Files: `vicmap_acquire/download.py` (lines 86-150, URL normalization)
- Why fragile: Attacker-controlled URLs can target internal networks (SSRF) or bypass allowlists via redirects/fragments/ports
- Safe modification: Do NOT relax host allowlist, port restrictions, or redirect validation; `_normalize_url_prefix` and `_normalize_allowed_host` enforce exact HTTPS, no ports, no userinfo — do not weaken these
- Test coverage: ✓ Full; `tests/test_download.py` covers SSRF, redirect rejection, and invalid URL formats

**HTML Visibility Parsing (Now Differential-Oracle-Tested):**
- Files: `vicmap_acquire/origin.py` (email authentication and link extraction)
- Why fragile: Email HTML can have malformed nesting, mismatched tags, or embedded scripts that confuse naive text extraction; previous implementation had void-element and suppression bugs
- Safe modification: The html5lib-based implementation is now proven against a differential oracle (370/2000 fuzz tests); do not switch back to regex-based extraction or simplify nesting rules
- Test coverage: ✓ Differential oracle; `tests/test_html_visibility_differential.py` validates against real html5lib output

## Scaling Limits

**Archive Member Count Ceiling (Conservative):**
- Current capacity: Max 4,000 members per archive (`ExtractionPolicy.max_member_count`)
- Limit: Real Vicmap orders unknown; if a delivery exceeds 4,000 files, extraction will fail with `archive_ceiling_exceeded`
- Scaling path: Increase `max_member_count` in `vicmap.toml` if real deliveries are larger; test extraction with a live order to calibrate

**Compressed-Bytes and Per-Member Ceilings (Tight):**
- Current capacity: `max_total_bytes = 10737418240` (10 GiB), `max_member_bytes = 4294967296` (4 GiB)
- Limit: A delivery larger than 10 GiB will fail; per-member limit at 4 GiB
- Scaling path: These are the binding resource ceilings; increase if real deliveries are larger, but verify available disk/memory first
- Testing: ✓ `ShippedCeilingCalibrationTest` validates against the real 233 MB Order_OK0VUZ

**Database Scaling (Not Yet Evaluated):**
- Current capacity: Unknown (Phase 3 not implemented)
- Limit: Connection pooling, transaction isolation, and lock contention not yet designed
- Scaling path: Phase 3 must include concurrency testing (multiple concurrent readers vs. publish lock) and connection-pool tuning

## Dependencies at Risk

**GDAL/OGR Driver Coverage:**
- Risk: Only OpenFileGDB format is currently allowlisted (`supported_formats` in `vicmap.toml`); if Vicmap switches delivery formats (e.g., to GPKG, Shapefile), discovery will fail with `unsupported_format`
- Impact: Entire pipeline blocks until `vicmap.toml` is updated
- Migration plan: Test and add new drivers to `_EXTENSION_DRIVERS` and `supported_formats` per real deliveries; already architected for single-line widening (see `read_mailbox.py:84-85` comments)

**Python 3.14 Environment (Risk of Dependency Rot):**
- Risk: Project uses Nix-managed dependencies; if upstream packages (O365 SDK, GDAL, psycopg) are not maintained in nixpkgs, environment will rot
- Impact: New development machines won't be able to build the environment; deployments will fail
- Migration plan: Monitor nixpkgs and maintain `flake.lock`; consider pinning to a specific nixpkgs revision for production deployments

**Microsoft O365 SDK Version (2.1.0):**
- Risk: O365 is a third-party community-maintained SDK; breaking changes or deprecations could affect authentication flow
- Impact: Authentication failures on environment updates; Graph API changes not propagated to SDK
- Migration plan: Monitor O365 changelog; if breaking changes occur, migrate to Microsoft's official `msgraph-sdk-python` or call Graph REST directly

## Missing Critical Features

**PostGIS Database Layer (Phase 3):**
- Problem: No database connection, staging table creation, validation, or atomic promotion code exists
- Blocks: Cannot load any data; cannot test consumer access; cannot prove idempotency
- Phase: 3 (not started)

**Atomic Table Swap & Rollback (Phase 4):**
- Problem: No transaction strategy for swapping staging → production; no rollback on validation failure
- Blocks: Readers could see partial/invalid data during load; failed loads are not recoverable
- Phase: 4 (not started); see PITFALLS.md Pitfall 5

**Consumer Access Validation (Phase 4):**
- Problem: No test that proves real database users (not owner/superuser) can query published tables
- Blocks: Grants/ACLs might not be applied correctly; users could have wrong schema-path expectations
- Phase: 4 (not started); see PITFALLS.md Pitfall 6

**WFS Cleanup & Inventory (Phase 5):**
- Problem: No code to inventory, approve, or safely delete abandoned WFS tables
- Blocks: Legacy `public` schema tables from failed WFS attempts will accumulate
- Phase: 5 (not started); see PITFALLS.md Pitfall 7

**Systemd Integration & Daily Scheduling (Phase 5):**
- Problem: No service file, timer configuration, or journald logging integration
- Blocks: Cannot run unattended on a schedule; operator must invoke manually
- Phase: 5 (not started)

**Failure Notification (Phase 5):**
- Problem: No email-on-failure integration; failures are only visible in structured logs
- Blocks: Operations teams won't be alerted to failures unless actively monitoring logs
- Phase: 5 (not started); currently by design (journal-only for success, deferred to Phase 5)

## Test Coverage Gaps

**Database-Specific Validation (Untested):**
- What's not tested: Staging table creation with correct schema/grants; promotion with advisory locks; consumer-role queries; parallel reader safety during promotion
- Files: `vicmap_acquire/` has no `database.py` module; no tests exist
- Risk: Loading will silently succeed but leave data unpublished, with wrong CRS, truncated names, or missing grants
- Priority: HIGH — This is Phase 3's core verification; must be 100% tested before v0.1 proof is complete

**Concurrent Execution (Partially Tested):**
- What's not tested: Two discover_order.py runs for the same order simultaneously; concurrent reader traffic during table swap; promotion lock timeout behavior
- Files: `tests/` has no concurrency fixtures
- Risk: Duplicate data, reader blocking, or race conditions on table rename
- Priority: HIGH — Deferred to Phase 4 (Publication) per PITFALLS.md, but critical for systemd timer safety

**Live PostGIS Integration (Untested):**
- What's not tested: Real PostgreSQL 18.6 + PostGIS; actual CRS transformation; geometry validity checks; spatial indexes on loaded tables
- Files: None; Phase 3 not started
- Risk: Tables load but are spatially invalid, have wrong SRIDs, or lack performance indexes
- Priority: HIGH — v0.1 proof requires this; deferred to Phase 3

**Error Recovery (Partially Tested):**
- What's not tested: Partial extraction rollback on write failure (code exists but untested beyond unit guards); extraction resume after network failure (not implemented); database transaction rollback with old-table retention
- Files: `vicmap_acquire/extraction.py` has guards, but integration tests are missing
- Risk: Failed runs leave `.tmp-` directories or incomplete tables that operators must manually clean
- Priority: MEDIUM — Phase 3 should establish recovery patterns

**Real-World Email Parsing (Single Happy-Path Fixture):**
- What's not tested: Malformed MIME; missing headers; real Vicmap subject line variability; message size edge cases
- Files: `tests/test_origin.py`, `tests/test_candidates.py` use redacted fixed fixtures (02-RESEARCH.md Pattern 1)
- Risk: First live Vicmap message fails with unexpected parse error; hidden until production invocation
- Priority: MEDIUM — Mitigated by operator manual selection and review before discovery (Phase 1 decisions); consider widening fixture library as real messages arrive

**Archive Inspection Against Real Deliveries (Now Exercised):**
- What's tested: Fixed synthetic fixtures (Order_TRACER1.zip, ~12 MB) and the real 233 MB Order_OK0VUZ.zip
- Files: `tests/test_extraction.py` (ShippedCeilingCalibrationTest uses `Order_OK0VUZ.zip`)
- Coverage: ✓ Real delivery extraction is now exercised; compression-ratio and byte-ceiling calibration verified
- Risk: MITIGATED; first production delivery is now part of the test suite

## Architectural Risks

**No Distributed Idempotency (Phase 3+):**
- Problem: Currently, each run generates a unique timestamp-based directory; if the same message is processed twice, duplicate tables are created
- Blocks: Daily systemd retries (Phase 5) need idempotency; message_fingerprint is available but not used for deduplication yet
- Risk: Multiple invocations of discover_order.py with the same artifact create multiple `runs/` directories and manifests; database loads are not guarded against duplication
- Approach: Phase 3 must include an idempotency check (e.g., Postgres audit log or manifest cache) before promoting tables

**No Rollback of Multi-Table Operations (Phase 4):**
- Problem: If layer 5 of 10 fails to load, layers 1-4 are already published; rolling back requires manual cleanup
- Blocks: Atomic all-or-nothing semantics require transaction bracketing or a multi-layer manifest with rollback logic
- Risk: Partial data visibility if a mid-load failure occurs
- Approach: Phase 4 (Publication) must design explicit rollback semantics per PITFALLS.md Pitfall 5

**No Visibility into Loader Privilege Escalation (Phase 3):**
- Problem: Loader role will be created with `CREATE TABLE` on `vicmap` schema; if misconfigurated, it could have unintended privileges
- Blocks: Consumer role cannot be safely tested as non-superuser without the correct loader/reader role separation
- Risk: Cleanup phase (Phase 5) could drop unrelated tables if loader role is overprivileged
- Approach: Phase 3 must include explicit role-creation tests and privilege audits per PITFALLS.md Pitfall 6

## Documentation Gaps

**Phase 3 Database Design Not Yet Documented:**
- Missing: Schema layout, table naming policy, staging vs. production separation, transaction strategy, lock timeout values, indexing policy, grants/role separation
- Impact: Phase 3 planning cannot begin without this design; currently blocks transition from Phase 2 to Phase 3 implementation

**Operational Runbook Missing:**
- Missing: Failure recovery steps, manual table cleanup, credential rotation, upgrade procedures
- Impact: Operations teams lack guidance for incident response; currently deferred to Phase 5

**CRS Transformation Policy Not Finalized:**
- Missing: Decision on whether to preserve source CRS or standardize on one SRID (e.g., EPSG:4283 for Victoria)
- Impact: Consumers won't know what SRIDs to expect; spatial queries may silently fail or return wrong results
- Approach: PITFALLS.md Pitfall 3 calls for this decision before Phase 3 implementation; needs explicit operator input

---

*Concerns audit: 2026-09-18*
