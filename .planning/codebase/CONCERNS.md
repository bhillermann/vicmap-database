<!-- refreshed: 2026-09-22 -->
# Codebase Concerns

**Analysis Date:** 2026-09-22

## Tech Debt

**SQL Injection Prevention in Identifier Composition:**
- Issue: Database identifiers composed from configuration or user input require careful validation before insertion into raw SQL. Multiple recent fixes (WR-02, WR-04) addressed underbounded regexes and missing type assertions.
- Files: `vicmap_acquire/staging.py`, `vicmap_acquire/evidence.py`
- Impact: Unbounded identifiers can exceed PostgreSQL's 63-byte NAMEDATALEN limit, silently truncating and creating collisions; unvalidated type declarations bypass parametrized queries.
- Fix approach: Continue enforcing closed vocabularies for declared geometry types, maintain byte-bounded identifiers with content-hash suffixes for collision prevention, and re-validate input before every raw-SQL composition point.

**Large Complex Module (staging.py):**
- Issue: `vicmap_acquire/staging.py` contains 1240 lines with 25 functions managing database connection, privilege verification, layer loading, validation, and DDL application in a single file.
- Files: `vicmap_acquire/staging.py`
- Impact: High cognitive load for modifications; multiple concerns (connection lifecycle, validation state machine, DDL generation) tightly coupled.
- Fix approach: Break into smaller, single-responsibility modules if the file grows beyond 1500 lines or requires frequent concurrent edits. Current complexity is manageable given the closed error model and test coverage.

**Evidence Module Validation Patterns:**
- Issue: `vicmap_acquire/evidence.py` carries 871 lines of regex-based validation for safe scalar fields (hostname, identifiers, JSON). Recent fix (WR-06) found unbounded hostname/table-name patterns that could accept unbounded input, creating redaction boundary violations.
- Files: `vicmap_acquire/evidence.py`
- Impact: Operator-facing event streams could leak unsanitized input if validation patterns are too permissive, defeating the closed-evidence design.
- Fix approach: Every regex with a natural bound (hostname DNS limit 253 chars, PostgreSQL identifier 63 bytes) must encode that bound explicitly. Add a comment citing the bound and its source. Consider periodic audit against staging.py patterns.

---

## Known Bugs

**Grid vs. Helmert Transform Selection in ogr2ogr (WINDOWS.md #2, #7 - OPEN):**
- Symptoms: Spatial coordinates transformed from GDA94 Vicgrid to GDA2020 (or vice versa) via ogr2ogr with `-ct_opt ONLY_BEST=YES -ct_opt ALLOW_BALLPARK=NO` flags select the grid-free Helmert 7-parameter transform (`+proj=helmert`) instead of the vendored ICSM grid (`+proj=hgridshift au_icsm_GDA94_GDA2020_conformal_and_distortion.tif`), resulting in ~2mm accuracy loss at some points.
- Files: `vicmap_acquire/staging.py` (lines 510-525 set GDAL transform options), `flake.nix` (PROJ data path configuration), `db/provision_vicmap_loader.sql`
- Trigger: Run `stage_order.py` with a layer containing GDA94 source SRID (7899) and target SRID 3111 (GDA2020 Vicgrid); verify via `pyproj.datadir.set_data_dir()` + transforming a known point coordinate.
- Workaround: No current mitigation. PROJ's internal accuracy metadata (0.01m for Helmert, 0.05m for grid) ranks Helmert as 'best' regardless of PROJ_DATA resolution, and `ONLY_BEST=YES` enforces that ranking.
- Root cause: PROJ library's accuracy declarations, not a code defect. Fix requires either forcing grid selection via explicit `-ct` pipeline string (future phase) or tightening the operation filter to reject ballpark transforms.

**Provisioning Script Assumes Existing Database (WINDOWS.md #4 - OPEN):**
- Symptoms: Running `db/provision_vicmap_loader.sql` as the first step fails with `FATAL: database vicmap does not exist` instead of creating the database. Operator must manually execute `CREATE DATABASE vicmap;` as superuser first.
- Files: `db/provision_vicmap_loader.sql`
- Trigger: Fresh PostgreSQL instance; run the script as-is against a server with no `vicmap` database.
- Workaround: Manually create the database before running the script, or use a PostgreSQL admin tool.
- Root cause: The script's first statement is `CREATE ROLE`, not `CREATE DATABASE`. Adding `CREATE DATABASE` changes the script's prerequisites (who can run it, when), an operator-level decision beyond this codebase phase's scope (documented in WINDOWS.md).

**Placeholder Config Value in vicmap.toml (WINDOWS.md #1 - OPEN):**
- Symptoms: `allowed_url_prefixes` in `[download]` section contains placeholder `"https://s3.ap-southeast-2.amazonaws.com/cl-isd-prd-datashare-s3-delivery/"` — this is the production value and is correct, but the Phase 01 plan left it deliberately fail-closed pending operator confirmation.
- Files: `vicmap.toml` (line 19)
- Impact: Minimal — the value is now verified against the real delivery and is the correct production prefix.
- Fix approach: This is a checkpoint, not a bug. No code change needed; documented in phase history as confirmed 2026-09-14.

---

## Security Considerations

**Redaction Boundary Enforcement:**
- Risk: Evidence module's regex patterns must reject unbounded input; a permissive pattern could let raw SQL, error messages, or file paths leak into JSON Lines output, where the operator or log aggregator might process it without sanitization.
- Files: `vicmap_acquire/evidence.py` (all `_require_*` validators and regex definitions)
- Current mitigation: Every scalar field validated against a closed regex; recent fix (WR-06) bounded hostname and table-name patterns to their natural limits. `_EmitOnce` guards prevent a failed sink from retrying and leaking details.
- Recommendations: 
  - Before adding new fields to event classes, explicitly decide the safe scalar bound (length, character set) and cite the source.
  - Add a periodic audit (every phase) comparing `evidence.py` bounds against corresponding bounds in `staging.py`, `discovery.py`, and `manifest.py`.
  - Document why certain fields are fingerprinted vs. rendered in clear (e.g., `database_identity.host` is clear, but `download_target.path_fingerprint` is hashed).

**SQL Injection via Identifier Composition:**
- Risk: If a declared geometry type (e.g., `POINT Z`) is not validated against a closed list before being used in a `CREATE TABLE` or `ALTER TABLE` statement, attacker-supplied input could modify the SQL command.
- Files: `vicmap_acquire/staging.py` (lines 652-683: `normalize_declared_geometry_type`, lines 744-757: `build_repair_statement`, lines 949-1120: `apply_post_validation_ddl`)
- Current mitigation: Fix WR-04 adds an explicit assertion checking `declared_type` membership against a 28-name closed vocabulary immediately before use in `apply_post_validation_ddl`.
- Recommendations: Ensure every raw-SQL composition point that uses a value from a previous function re-asserts that value's invariant (e.g., "this field is already in the closed list") rather than relying silently on a different function's validation.

**Subprocess Invocation with ogr2ogr:**
- Risk: `subprocess.run()` invokes ogr2ogr with a complex argument list including file paths, table names, and schema names. If any component is not properly quoted or escaped, command injection could occur.
- Files: `vicmap_acquire/staging.py` (lines 489-541: `build_ogr2ogr_command`, lines 552-627: `load_layer`)
- Current mitigation: The command is built as a list of strings, not a shell command, so shell metacharacters in file paths or identifiers are passed literally. Identifiers are validated against closed patterns and quoted as SQL identifiers. File paths are `Path` objects, not string interpolation.
- Recommendations: Continue avoiding `shell=True`. If the ogr2ogr invocation changes, trace each argument to confirm it is either a constant, a validated identifier, or a Path object.

**Environment Variable Leakage:**
- Risk: Database password passed via `PGPASSWORD` environment variable is visible to all processes running as the same user (via `/proc/[pid]/environ` on Linux). If a subprocess or helper tool is spawned in the same environment, it inherits the password.
- Files: `vicmap_acquire/staging.py` (line 584: `env={**os.environ, "PGPASSWORD": password}`)
- Current mitigation: The password is passed only to the specific `subprocess.run()` call for ogr2ogr; the entire process environment is not modified. Cleartext password appears in the subprocess's own env, but that is unavoidable with command-line tools that do not support stdin or conninfo strings.
- Recommendations: Document that `VICMAP_DB_PASSWORD` (the source of the password parameter) is read from the environment only once, at process start, and is never written to config files, logs, or event streams. Operators should ensure the container/host/script that runs the acquisition tool uses a secure secret management system (e.g., OS credential store, opnix) rather than exporting `VICMAP_DB_PASSWORD` in shell session state.

---

## Performance Bottlenecks

**Sequential Layer Loading:**
- Problem: `run_staging()` loads manifest layers sequentially in a loop (lines 1169-1238), one `ogr2ogr` subprocess per layer, waiting for completion before starting the next. On a large manifest with many layers, total runtime is the sum of all per-layer times.
- Files: `vicmap_acquire/staging.py` (lines 1128-1240)
- Cause: Explicit design choice documented in the function docstring ("One `ogr2ogr` invocation at a time -- sequentially, with no concurrent execution framework"). Simplifies error handling (first failure stops the run) and resource management (no unbounded subprocess count).
- Improvement path: If loading becomes a bottleneck, implement a bounded task queue or thread pool with a small concurrency limit (e.g., 2-4 parallel loads). This requires careful error handling to ensure the first load failure stops all pending tasks gracefully, and would need regression testing to confirm no race conditions in database writes.

**Validation Query on Large Spatial Tables:**
- Problem: `validate_layer()` runs a single complex SQL query (built by `build_validation_query()`) that selects row count, null-geometry count, invalid-geometry count, distinct SRIDs, distinct geometry types, extent, and Z/M flags in one pass. On a very large table (millions of rows), this query could be I/O-intensive.
- Files: `vicmap_acquire/staging.py` (lines 701-743: `build_validation_query`, lines 780-928: `validate_layer`)
- Cause: Design trade-off: one query minimizes the number of table scans and reduces total query time vs. multiple focused queries.
- Improvement path: Monitor real query execution times on production manifests. If validation exceeds a threshold (e.g., >30 seconds), consider splitting into separate queries or adding covering indexes on the staging table before validation begins. Current design is acceptable for validation purposes (accuracy matters more than speed) and the queried staging tables are temporary anyway.

**ogr2ogr Subprocess Diagnostics Capture:**
- Problem: stderr output from the ogr2ogr subprocess is captured to a file on every load (line 579: `stderr=diagnostics_path(...)`). On large files or verbose ogr2ogr output, the file could grow large and I/O for writing it could slow the overall load.
- Files: `vicmap_acquire/staging.py` (lines 543-627)
- Cause: Design choice to capture diagnostics for debugging failed loads; necessary for post-mortem analysis when load_layer raises LoadFailed.
- Improvement path: Only write diagnostics file on error (use `PIPE` initially, then write only if returncode != 0). Current approach is acceptable for proof-of-concept; optimize if diagnostics file sizes become problematic in production runs.

---

## Fragile Areas

**validate_layer Function Logic:**
- Files: `vicmap_acquire/staging.py` (lines 780-928)
- Why fragile: Contains a six-step validation state machine (row count → null geometry → SRID → geometry type → repair → extent) with multiple conditional branches and exception types. Any change to the order, condition, or exception mapping could break invariants (e.g., row count must be checked before geometry type, because a mismatch means the table is wrong regardless of geometry state).
- Safe modification: Add new validation steps by appending to the numbered list (step 7, 8, ...), not by inserting. Update docstrings and comments to reflect the new order. Add corresponding test cases in `ValidationTest` class.
- Test coverage: `tests/test_staging.py` has 20+ tests for `validate_layer` variants (spatial, non-spatial, repair, mismatches); add new tests for any new step before committing.

**apply_post_validation_ddl Function:**
- Files: `vicmap_acquire/staging.py` (lines 949-1120)
- Why fragile: Builds and executes four separate DDL statements (PRIMARY KEY, typed geometry column, NOT NULL constraint, GiST index, btree indexes) in a single transaction. If any statement fails partway through (e.g., primary key creation fails after the ALTER TYPE succeeds), the whole transaction rolls back, but the order of operations is important for idempotency and readability.
- Safe modification: Test any changes against an existing staging table (re-run apply_post_validation_ddl against the same table twice) to confirm idempotency. Ensure new DDL statements are added inside the same transaction block.
- Test coverage: `tests/test_staging.py` has 10+ tests for post-validation DDL variants; always run them after changes.

**Evidence Regex Patterns:**
- Files: `vicmap_acquire/evidence.py` (all regex definitions and `_require_*` validators)
- Why fragile: Adding a new event type or field requires adding a corresponding validator regex. If the regex is too permissive or missing a bound, the new field could leak unsanitized data into the event stream. If the regex is too strict, legitimate values could be rejected.
- Safe modification: New fields must define a safe-scalar bound (max length, allowed characters) with a comment citing the source (e.g., "PostgreSQL 63-byte limit" or "DNS 253-byte limit"). Test the regex against real examples from the actual data source.
- Test coverage: `tests/test_evidence.py` has 50+ tests for validators and event construction; add test cases for any new field before committing.

**Discovery Module with ogrinfo Subprocess:**
- Files: `vicmap_acquire/discovery.py` (lines 220-250: `discover_layers`)
- Why fragile: Invokes `ogrinfo` subprocess with a timeout and parses JSON output. If ogrinfo output format changes (across GDAL versions), JSON parsing could fail. If the subprocess times out, determining whether it was the dataset itself or the timeout logic is difficult.
- Safe modification: Maintain compatibility with GDAL versions documented in `flake.nix`. Add a version check or capture `ogrinfo --version` output in diagnostics if behavior diverges. Any change to timeout handling should be tested against both fast (in-memory) and slow (network) datasets.
- Test coverage: `tests/test_discovery.py` and `test_discovery_differential.py` have differential oracle tests; use real datasets to verify changes.

---

## Scaling Limits

**Manifest Layer Count:**
- Current capacity: Tested with 100+ layers; `run_staging()` iterates sequentially, so doubling layer count doubles runtime.
- Limit: No hard limit; limited by total runtime tolerance (if sequential loading exceeds 1 hour per order, operators may cancel). For the Vicmap delivery (1-3 layers typically), not a concern.
- Scaling path: If manifests grow to 1000+ layers, implement parallel loading (see Performance Bottlenecks section).

**PostGIS Staging Table Size:**
- Current capacity: Tested with tables > 1 million rows; `validate_layer` query completes in seconds; staging tables are temporary and are dropped after publication.
- Limit: PostgreSQL backend can handle billions of rows; the practical limit is disk space and query time. Storage is not a concern since staging tables are temporary.
- Scaling path: Monitor query execution plans for validate_layer on very large tables; add covering indexes if sequential scans become problematic.

**Connection Pool:**
- Current capacity: One connection per function call (read_database_identity, preflight_staging_privileges, load_layer, validate_layer, apply_post_validation_ddl); connections are opened and closed sequentially.
- Limit: Database server max_connections (default ~100). With sequential execution, this is never a bottleneck.
- Scaling path: If parallel loading is implemented, use a bounded connection pool (psycopg.ConnectionPool) with a small limit (e.g., 5-10) to avoid exhausting the server's capacity.

**ogr2ogr Subprocess Memory:**
- Current capacity: Tested with archive members up to 4 GB; ogr2ogr's memory usage depends on the dataset format and layer complexity.
- Limit: Host RAM available to the ogr2ogr subprocess. No explicit bound is set in the acquisition tool.
- Scaling path: If datasets exceed available RAM, ogr2ogr will fail with an out-of-memory error (raised as LoadFailed). Monitor host memory during load and adjust `max_member_bytes` in `vicmap.toml` if needed.

---

## Dependencies at Risk

**psycopg 3.3.4 PostgreSQL Driver:**
- Risk: Phase 03 introduced psycopg as the required PostgreSQL driver. Major version changes (4.x, 5.x) could introduce breaking changes in connection strings, SQL parameter syntax, or exception types.
- Impact: Loading phase would fail to work with newer driver versions without code updates.
- Current mitigation: `flake.nix` pins psycopg to 3.3.4; nixpkgs updates are controlled.
- Migration plan: Monitor psycopg releases for major version announcements. When psycopg 4.x is released, review breaking changes and plan a migration phase if needed. Current code uses standard psycopg patterns (connect, cursor, execute) that are likely stable across minor versions.

**GDAL/ogr2ogr Binary Dependency:**
- Risk: ogr2ogr is a system binary invoked via subprocess. GDAL version changes (3.x, 4.x) could change argument syntax, default behavior, or output format.
- Impact: ogr2ogr invocation or stderr parsing could fail with newer GDAL versions.
- Current mitigation: `flake.nix` pins GDAL to a specific version; test suite includes `test_only_best_and_allow_ballpark_flags_are_recognized_by_the_real_binary` to detect breaking changes.
- Migration plan: When upgrading GDAL, run the flag-recognition test first. If it fails, review the new GDAL documentation and update the argument list in `build_ogr2ogr_command()`.

**PROJ Library for Coordinate Transforms:**
- Risk: PROJ 9.x introduced significant changes to grid handling and accuracy metadata. A future PROJ release could change how grids are discovered, ranked, or applied.
- Impact: Grid vs. Helmert selection issue (WINDOWS.md #7) could worsen or change unexpectedly with PROJ updates.
- Current mitigation: None — the grid selection issue is known and documented. `flake.nix` pins PROJ version.
- Migration plan: Monitor PROJ release notes. If a release promises improved grid selection or accuracy, test it against the known GDA94/GDA2020 transform to determine if it resolves WINDOWS.md #7. If grid selection remains an issue, implement an explicit fix in the acquisition code (force grid selection via `-ct` pipeline) in a future phase.

**pyogrio Python Geospatial I/O:**
- Risk: Phase 02 uses pyogrio to read layer metadata via `read_info()`. Version changes could alter the returned data structure or add new exceptions.
- Impact: Discovery metadata extraction could break or miss new layer fields.
- Current mitigation: `flake.nix` pins pyogrio; `tests/test_discovery.py` includes regression tests against real and synthetic datasets.
- Migration plan: Periodically run the discovery differential tests (especially `test_discovery_differential.py`) after updating pyogrio. If output changes, review and update the parsing logic in `discover_layers()`.

---

## Missing Critical Features

**Superuser Privilege Testing (WINDOWS.md #6 - OPEN):**
- Problem: PrivilegePreflightTest class has 5 test methods that verify privilege preflight behavior (pass path, 4 fail paths for missing staging schema create, public schema create, superuser role, unknown SRID). These tests skip without the `VICMAP_TEST_POSTGRES_SUPERUSER_DSN` environment variable, which was never configured during Phase 03.
- Blocks: Automated verification of DB-02 privilege preflight rules; currently verified only via live manual testing (stage_order.py --preflight-only).
- Gap: No automated regression test for privilege preflight; future changes to privilege validation logic could introduce subtle regressions.
- Fix: Configure VICMAP_TEST_POSTGRES_SUPERUSER_DSN in the test environment, or set up a separate project-provisioned test-only superuser role (documented like VICMAP_DB_PASSWORD). This is an environment/operator setup task, not a code change.

**GDA94/GDA2020 Grid-Accurate Coordinate Transform (WINDOWS.md #2, #7 - OPEN):**
- Problem: Grid-free Helmert transform is selected instead of vendored ICSM grid, leading to ~2mm accuracy loss. No mechanism in the current acquisition code forces grid selection.
- Blocks: Coordinates transformed to GDA2020 Vicgrid are ~2mm off; if application logic depends on sub-meter accuracy, this is unacceptable.
- Gap: No workaround in code; operator acceptance is documented in phase sign-off (2026-09-21). Fix requires changes to GDAL invocation or PROJ pipeline configuration, outside the scope of Phase 03.
- Fix: Implement explicit `-ct` pipeline string in `build_ogr2ogr_command()` to force grid selection, or upgrade to PROJ 10.x if it improves grid accuracy metadata. Document the chosen approach in a future phase plan.

**Database Schema and Role Provisioning Script:**
- Problem: `db/provision_vicmap_loader.sql` is incomplete (missing CREATE DATABASE) and requires manual operator steps before use.
- Blocks: Provisioning a fresh PostgreSQL instance for the acquisition tool requires out-of-band manual steps.
- Gap: No automated provisioning script or Terraform module to set up the entire database, schemas, and roles.
- Fix: Create an optional Phase 04 plan to provide a complete provisioning guide or automation. For now, document the manual steps in WINDOWS.md and require operator confirmation before running the script.

---

## Test Coverage Gaps

**Privilege Preflight Verification (tests/test_staging.py):**
- What's not tested: The five PrivilegePreflightTest methods (pass path, 4 fail paths) skip without VICMAP_TEST_POSTGRES_SUPERUSER_DSN configured. DB-02's full contract is not automatically verified.
- Files: `tests/test_staging.py` (lines 941-1127: PrivilegePreflightTest)
- Risk: A regression in privilege validation (e.g., accidentally allowing superuser to write to staging schema, or rejecting a valid non-superuser role) could go undetected until live testing.
- Priority: High — privilege checks are security-critical. Should be run as part of CI/CD if possible, or documented as a required manual pre-deployment check.
- Recommendation: Set up VICMAP_TEST_POSTGRES_SUPERUSER_DSN in the test environment or use a Docker PostgreSQL fixture that provides both ordinary and superuser connections.

**Live Delivery Regression Tests (tests/test_discovery.py, test_extraction.py, test_manifest.py):**
- What's not tested: Tests marked with `@unittest.skipUnless(REAL_ARTIFACT.is_file(), ...)` skip if `artifacts/Order_OK0VUZ.zip` is not present. End-to-end integration with the real order artifact is conditional.
- Files: `tests/test_manifest.py` (line 1119), `tests/test_discovery_config.py` (line 402), `tests/test_extraction.py` (lines 581, 667)
- Risk: Unit tests can pass, but real artifact unpacking or manifest creation could still fail due to unexpected data in the real ZIP, OGR metadata, or layer schemas.
- Priority: Medium — live tests caught multiple issues during Phase 02 (e.g., correct ADDRESS schema has 61 fields, not 40). Should be run nightly or pre-release.
- Recommendation: Store artifacts in a dedicated CI/CD artifact cache and populate them at test time. Ensure the real Order_OK0VUZ artifacts are available in the CI environment.

**Geometric Repair Edge Cases (tests/test_staging.py):**
- What's not tested: `validate_layer()` can repair invalid geometries via `ST_MakeValid()`. Test coverage includes "repair-preserving-type" and "repair-changing-type" cases, but edge cases like self-intersecting polygons, overlapping holes, or topology violations are not explicitly tested.
- Files: `tests/test_staging.py` (lines 1281-1330, 1332-1360)
- Risk: A geometry edge case could fail to repair or repair to an unexpected type, causing the validation to raise or pass when it should do the opposite.
- Priority: Low — the real Vicmap ADDRESS dataset has been tested against these functions and repairs succeeded. Regression unlikely unless geometry source changes.
- Recommendation: If geometry repair logic changes, add fixture geometries for known edge cases (self-intersecting, holes, etc.) and test repair outcomes.

**CLI Argument Parsing (discover_order.py, stage_order.py):**
- What's not tested: The top-level entry-point scripts (discover_order.py, stage_order.py) parse command-line arguments, load configuration, and orchestrate the acquisition phases. Unit tests focus on module functions, not CLI orchestration.
- Files: `discover_order.py`, `stage_order.py`
- Risk: A typo in argument parsing or configuration loading could go undetected in unit tests.
- Priority: Low — these scripts are tested via live manual execution during each phase. Automated CLI tests could be added if they become complex.
- Recommendation: Consider adding pytest fixtures that simulate argparse inputs and configuration files, or use hypothesis-based property testing for config validation.

---

*Concerns audit: 2026-09-22*
