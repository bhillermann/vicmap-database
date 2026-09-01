# Pitfalls Research

**Domain:** Email-triggered geospatial snapshot ingestion into PostGIS
**Researched:** 2026-09-01
**Confidence:** HIGH for PostgreSQL, PostGIS, Python archive, and GDAL behavior; MEDIUM for the exact Vicmap email/archive contract until a real delivery is inspected

## Critical Pitfalls

### Pitfall 1: Treating a mailbox message or visible link text as trusted input

**What goes wrong:**
An attacker or forwarded/spoofed message resembling a Vicmap ready notice causes the pipeline to disclose network access, download attacker-controlled content, or log secrets. HTML anchor text can name a trusted site while its actual target is elsewhere; redirects can also leave an initially allowed host.

**Why it happens:**
The mailbox is mistaken for a trust boundary. Code checks only subject text or the convenient `from` field and then lets a general-purpose HTTP client follow any URL and redirects. Application `Mail.Read` is also broader than it sounds: absent tenant-side restriction, it reads all mailboxes.

**How to avoid:**
Use the smallest Graph application permission and tenant-side mailbox restriction available. Fetch an explicit, minimal property set, avoid logging bodies/tokens, and identify a ready message with a fixture-backed parser. Require an exact configured sender identity/domain and expected message pattern, but also treat the extracted URL as independently untrusted: allowlist HTTPS scheme, exact hostname and expected path shape; reject embedded credentials, non-default ports, IP literals, fragments, and local/private/link-local destinations; revalidate every redirect hop and final URL. Apply connect/read timeouts and a strict byte limit. Store the artifact outside the repository with owner-only permissions and compute a checksum before extraction.

**Warning signs:**
Tests use only a hand-written happy-path email; the downloader accepts `http:`, arbitrary hosts, or automatic redirects; logs contain message bodies or signed URLs; Graph consent shows access to every mailbox; source identity is inferred only from subject/body text.

**Phase to address:**
Phase 1 — trusted Graph message discovery and bounded artifact download. This gate must precede archive handling.

---

### Pitfall 2: Extracting the order archive as if it were ordinary local files

**What goes wrong:**
Path traversal, absolute paths, symlinks, duplicate names, device-like entries, or a decompression bomb writes outside the workspace or exhausts disk/memory. A partially extracted directory is later mistaken for a complete order.

**Why it happens:**
`extractall()` looks like a complete safety policy. Python explicitly warns that untrusted archives must be inspected first; filename normalization alone does not enforce member-count, expanded-size, compression-ratio, link, or partial-extraction policy.

**How to avoid:**
Download to a newly created per-run directory, verify the archive format, then inspect every member before writing. Reject absolute paths, `..`, NULs, path collisions after normalization/case-folding, non-regular files (especially symlinks), excessive nesting, too many members, excessive total uncompressed bytes, and implausible compression ratios. Resolve each candidate output path and prove it remains beneath the extraction root. Stream extraction with byte accounting into a temporary directory and publish/rename the directory only after full success; clean failed temporary output. Never recurse into nested archives for v0.1.

**Warning signs:**
A direct `extractall()` call; no advertised-size budget; extraction occurs in the checkout or a shared persistent directory; a rerun reuses an old directory; the reader scans whatever files happen to remain after an exception.

**Phase to address:**
Phase 2 — safe archive inspection, extraction, and artifact inventory.

---

### Pitfall 3: Mistaking “OGR can open it” for a valid spatial data contract

**What goes wrong:**
Layers load with unknown or wrong CRS, swapped axes, mixed/incompatible geometry types, invalid geometries, truncated/coerced fields, unexpected nullability, or duplicate normalized names. The database is queryable but spatially wrong.

**Why it happens:**
Geodatabases contain richer metadata than a file extension conveys. GDAL 3 follows authority axis order by default for CRS objects, which can differ from traditional GIS longitude/easting-first assumptions. PostGIS does not automatically validate geometry on load, and a successful driver read says nothing about expected extents or semantics.

**How to avoid:**
Inventory datasource driver, layer name, feature count, geometry fields/types, field names/types/nullability, CRS WKT and authority/SRID, and extent before loading. Fail closed on absent/ambiguous CRS for spatial layers. Choose and document whether source CRS is preserved or transformed; never assign an SRID without an actual transformation. Assert expected Victorian coordinate bounds after any transformation and explicitly test axis order. Detect collisions after deterministic lowercase `snake_case` normalization and the PostgreSQL 63-byte identifier limit. In staging, compare source and loaded counts, geometry type/SRID, null geometry count, and `ST_IsValid` results; do not silently `ST_MakeValid`, drop Z/M dimensions, or coerce types for the proof.

**Warning signs:**
SRID 0; all extents near `(0,0)`, latitude values in X, or coordinates outside Victoria; loader warnings about laundering/truncating names or geometry promotion; source and target feature counts differ; multiple source names map to the same target identifier; only the first layer is inspected.

**Phase to address:**
Phase 2 — geospatial discovery contract; Phase 3 — staging validation must repeat the checks against PostGIS.

---

### Pitfall 4: Building SQL from discovered layer names unsafely or ambiguously

**What goes wrong:**
A layer name becomes SQL injection, resolves to the wrong schema through `search_path`, collides after truncation, or overwrites an unrelated table. Parameters cannot be used for identifiers, so naïve placeholder use fails and string interpolation is tempting.

**Why it happens:**
Source layer names are treated as trusted identifiers. PostgreSQL folds unquoted names to lowercase, truncates identifiers to 63 bytes by default, and permits same-named objects in different schemas.

**How to avoid:**
Separate identifier policy from SQL value binding. Normalize once with a conservative allowlist; reject blank, reserved-prefix, duplicate, and post-truncation collisions. Maintain the source-to-target mapping in the run report. Always schema-qualify every created, queried, renamed, and dropped object. Compose identifiers through the database driver's identifier API (or PostgreSQL `%I`/`quote_ident`), never string concatenation. Pin a secure `search_path` for loader sessions and scope the loader role so it cannot create/drop in `public`.

**Warning signs:**
F-strings or `.format()` around DDL; `DROP TABLE {name}`; unqualified table references; `vicmap` appears in `search_path` while ordinary users have `CREATE` there; generated names are silently shortened; normalization lacks collision tests.

**Phase to address:**
Phase 3 — database boundary, naming policy, and staging loader.

---

### Pitfall 5: Calling a long load “atomic” because the last statement is transactional

**What goes wrong:**
Readers are blocked longer than expected, production disappears briefly, grants/indexes/comments are lost, dependent views break, or a failure leaves old/staging/backup tables in confusing states. Concurrent runs can publish out of order.

**Why it happens:**
Bulk loading and validation occur on the production name, or the whole load is held in one huge transaction. `DROP TABLE`, `TRUNCATE`, and many `ALTER TABLE` forms take `ACCESS EXCLUSIVE`, which conflicts even with ordinary reads. Renaming a replacement table also changes object identity: dependencies and privileges attached to the old table do not magically move to the new object.

**How to avoid:**
Load and index an isolated, uniquely named staging table without holding production locks. Validate it completely, then acquire a per-layer advisory lock and use a short transaction with `lock_timeout` and `statement_timeout` to publish according to an explicit contract. Decide before implementation whether stable object identity/dependencies matter: a rename swap gives a new table object; stable views or an in-place strategy have different lock/rollback tradeoffs. Recreate/verify grants, ownership, comments, constraints, spatial indexes, and statistics on the published object. Preserve the last known-good table until post-publish verification succeeds, and define deterministic cleanup/recovery names.

**Warning signs:**
The production table is truncated before validation; no lock timeout; publication DDL sits in the same transaction as bulk insert; two invocations can run together; tests check rows but not grants/indexes/dependencies; a renamed table still has staging ownership or names.

**Phase to address:**
Phase 3 — staging load; Phase 4 — atomic promotion and rollback verification.

---

### Pitfall 6: Proving access as the loader rather than as the user

**What goes wrong:**
The privileged loader can query production, but intended GIS users cannot resolve the schema/table, lack `SELECT`, or cannot use referenced sequences/types. Alternatively, users receive `CREATE` or write privileges they do not need.

**Why it happens:**
Schema `USAGE` and table privileges are distinct. Replacement tables do not necessarily inherit old grants, and default privileges apply only to objects subsequently created by the role whose defaults were altered.

**How to avoid:**
Define separate owner/loader and read-only roles. Grant intended users/role `USAGE` on `vicmap` and `SELECT` on its production tables, with no `CREATE` on the schema. Configure default privileges for the actual table-creating role or apply grants during every promotion. Run the acceptance query using the real consumer role and schema-qualified names; verify `information_schema.role_table_grants`/catalog ACLs after promotion.

**Warning signs:**
Acceptance is run as database owner; `GRANT SELECT ON ALL TABLES` works once but new promoted tables fail; users rely on `public` search path; `PUBLIC` has `CREATE` on `vicmap`.

**Phase to address:**
Phase 4 — publication and consumer-access acceptance.

---

### Pitfall 7: “Cleanup” based on names, age, or memory

**What goes wrong:**
Legitimate GIS tables in `public`, dependent views, or tables from another application are dropped while removing abandoned WFS artifacts. `CASCADE` magnifies one mistaken classification.

**Why it happens:**
The abandoned attempt and legitimate data share a database/schema, provenance is incomplete, and stale-looking names are not proof of ownership. A generated inventory is treated as authorization.

**How to avoid:**
Make cleanup a separate, two-step workflow: read-only inventory first, then an immutable explicit approval manifest containing database, schema, exact table name, object identity/type, evidence, and ideally a captured definition/count/size/dependencies. Query catalogs for ownership, privileges, comments, indexes, constraints, foreign keys, views/materialized views, and other dependencies. Refuse system schemas, the new `vicmap` schema, wildcard/pattern targets, changed objects, and `CASCADE`. Before deletion, reconnect to the expected database/host/port, re-resolve each exact target, compare it to the approved snapshot, show the final list, and require a fresh explicit approval. Prefer a recoverable quarantine/rename or backup when feasible. Execute only approved exact schema-qualified identifiers and produce an audit report.

**Warning signs:**
The tool proposes `DROP ... CASCADE`; candidates are selected by prefix alone; a command accepts comma-separated arbitrary SQL; there is no dependency report or database fingerprint; inventory and deletion happen in one invocation; loader credentials can drop any `public` table.

**Phase to address:**
Phase 5 — abandoned WFS inventory and separately approved cleanup, after the import proof is complete.

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Hard-code the one observed email subject/HTML layout | Fast real-order proof | Invisible breakage on template change; easy false match | Only with a saved redacted fixture, explicit failure on mismatch, and sender/URL trust checks |
| Process only the newest matching message | Avoids ledger design | Reruns and ordering are ambiguous | Acceptable for v0.1 only when selection is printed, operator-confirmed, and no mailbox state is mutated |
| Preserve source CRS rather than standardize | Avoids risky reprojection | Consumers must handle heterogeneous SRIDs | Acceptable if every published layer exposes a known SRID and passes extent checks |
| Skip durable audit/idempotency | Smaller MVP | Duplicate processing and weak provenance | Acceptable for one manually invoked proof if unique work directories/checksums and a run report exist |
| Use one loader/database-owner role | Less setup | Cannot prove least privilege; cleanup blast radius | Never for cleanup; temporarily tolerable for connection diagnosis only, not final acceptance |
| Drop old production immediately after rename | Saves disk | No fast rollback | Not acceptable for the first real publication |

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| Microsoft Graph | Assuming message IDs never change | Use immutable IDs where feasible or record `internetMessageId`; Graph documents that default IDs change when messages move |
| Microsoft Graph | Listing messages without explicit paging/property selection | Bound/paginate deliberately and select only fields needed for classification |
| Email → HTTP | Trusting the sender check as authorization for any embedded URL | Independently validate decoded URL and every redirect/final destination |
| HTTP → archive | Loading the entire response into memory | Stream to a bounded temporary file, count bytes, checksum, then inspect |
| GDAL/OGR | Assuming every geodatabase layer has one obvious geometry/CRS | Inventory all geometry fields, types, CRS, fields, counts, and extents |
| GDAL → PostGIS | Letting driver defaults silently launder names/types | Specify naming/type policy and compare source/target metadata |
| PostgreSQL | Assuming “localhost:5432” identifies the intended DB | Validate host, port, database, server version, PostGIS availability, and a deployment fingerprint before DDL |
| PostgreSQL | Assuming rename carries consumer permissions/dependencies to replacement data | Explicitly choose object-identity strategy and re-verify ACLs/dependencies after promotion |

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Materializing Graph bodies/results unnecessarily | Slow mailbox reads, large logs/memory | Server-side filtering where supported, explicit `$select`, bounded paging | Large or old mailbox |
| Unbounded archive expansion | Disk exhaustion despite small download | Cap compressed bytes, member count, per-member and total expanded bytes | A malformed/malicious archive, or unexpectedly large delivery |
| Reading whole geospatial layers into Python memory | OOM and long pauses | Use OGR/streamed batches or database-native COPY path | Layers larger than available RAM; likely real cadastral/transport snapshots |
| Per-feature inserts | Hours-long loads, excessive round trips | Bulk/COPY-oriented loading with measured batches | Tens of thousands of features and above |
| Geometry validation only after publish | Long lock/rollback window | Validate staging before the short promotion transaction | Any nontrivial layer |
| Building indexes during the publish lock | Reader outage | Build indexes on staging before promotion | Large tables or active GIS clients |

## Security Mistakes

| Mistake | Risk | Prevention |
|---------|------|------------|
| Repository-local, world-readable Graph token | Credential disclosure | Move outside checkout, mode `0600`, ignore paths, rotate exposed token |
| Broad Graph application permission | Tenant-wide mailbox exposure | Minimum permission plus tenant mailbox access restriction |
| Logging body, signed URL, token, or DSN password | Durable secret/data leakage | Structured allowlisted fields and redaction |
| DNS/redirect-blind downloader | SSRF or unexpected external download | Exact host/scheme/path policy, redirect-hop validation, network timeouts/limits |
| Blind archive extraction | Filesystem overwrite/resource exhaustion | Preflight all members and extract into an isolated bounded directory |
| Dynamic unquoted identifiers | SQL injection/wrong-object DDL | Conservative normalization, collision rejection, driver identifier composition |
| Owner/superuser used for ingestion and cleanup | Database-wide blast radius | Separate least-privilege loader, publisher, reader; exceptional cleanup role only after approval |
| Writable schema in loader `search_path` | Object-shadowing/code execution risk | Schema-qualify, pin secure path, revoke unneeded `CREATE` |

## UX Pitfalls

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| “Success” means process exit 0 | Users find missing/wrong layers later | Report message/order/artifact, layer mapping, counts, SRIDs, validation, published names, and consumer-role query result |
| Silent name normalization | Users cannot find expected tables | Produce a source-layer → `vicmap.table` mapping |
| Cleanup proposal without evidence | Approval is unsafe and stressful | Show exact qualified names, owner, counts, sizes, dependencies, evidence, and recoverability |
| Requiring users to alter `search_path` blindly | Name collisions and inconsistent access | Document schema-qualified queries first; offer a deliberately configured role path only if needed |

## “Looks Done But Isn't” Checklist

- [ ] **Graph login:** Authentication alone is insufficient — verify the configured mailbox is read with the intended least privilege and output is redacted.
- [ ] **Ready email:** A matching subject is insufficient — verify sender identity, exact parsed link target, redirects, and operator-visible selection.
- [ ] **Download:** HTTP 200 is insufficient — verify byte bounds, archive signature/openability, checksum, and isolated storage.
- [ ] **Extraction:** Files appearing is insufficient — verify all members passed path/type/size policy and extraction completed atomically.
- [ ] **Geospatial read:** Driver open is insufficient — verify every layer's schema, count, geometry type, CRS/SRID, extent, and name mapping.
- [ ] **PostGIS connection:** TCP connection is insufficient — verify exact database identity, PostGIS extension/version, privileges, and dedicated schema.
- [ ] **Staging load:** Rows present is insufficient — compare counts, CRS, geometry validity/nulls, fields, indexes, and constraints.
- [ ] **Promotion:** Rename success is insufficient — verify short locks, rollback object, object dependencies, owner, grants, indexes, and statistics.
- [ ] **User access:** Owner query success is insufficient — query a representative production layer as the real read-only consumer role.
- [ ] **Cleanup:** Candidate list is insufficient — require exact approved manifest, dependency recheck, no `CASCADE`, and post-action audit.

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Untrusted/incorrect artifact downloaded | LOW | Quarantine/delete the per-run workspace, revoke exposed signed URL/token if applicable, record checksum/headers, tighten trust policy, rerun |
| Unsafe archive escaped workspace | HIGH | Stop processing, inspect filesystem modifications and credentials, restore affected files, rotate exposed secrets, add adversarial extraction tests |
| Wrong CRS/type published | MEDIUM | Keep users on last-known-good/rollback table, unpublish replacement, correct explicit transform/schema policy, reload and revalidate extents/counts |
| Promotion blocked readers | MEDIUM | Cancel/rollback publisher, retain production, identify blocking sessions, shorten transaction and set lock timeout before retry |
| Grants lost on replacement | LOW | Restore owner/schema usage/table select; fix creating-role default privileges or promotion grant step; test as consumer |
| Wrong table approved for cleanup but not dropped | LOW | Revoke approval and regenerate inventory |
| Wrong table dropped | HIGH | Restore from backup/quarantine/PITR, rebuild dependencies and grants, validate consumers; never rely on `CASCADE` reconstruction |

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| Email/link trust and bounded download | Phase 1: Graph and artifact acquisition | Spoofed sender, deceptive link, forbidden redirect, oversized response, and redaction tests all fail safely |
| Unsafe archive extraction | Phase 2: Archive/geospatial discovery | Traversal, absolute path, symlink, duplicate, too-many-files, and expansion-bomb fixtures are rejected without external writes |
| CRS/schema/geometry drift | Phase 2 discovery + Phase 3 staging | Inventory and source/target assertions cover every layer; bounds and `ST_IsValid` checks pass |
| Identifier injection/collision | Phase 3: PostGIS staging | Hostile/reserved/long/colliding layer-name tests; catalog proves no `public` objects touched |
| Non-atomic or blocking promotion | Phase 4: Publication | Forced failure preserves old production; concurrent reader/run tests; locks bounded; rollback succeeds |
| Missing consumer access | Phase 4: Publication | Real read-only role can `SELECT`; cannot create/write; grants survive a second promotion |
| Destructive WFS cleanup | Phase 5: Inventory and approved cleanup | Dry-run exact manifest; dependency/change recheck; explicit second approval; no wildcard/`CASCADE`; legitimate tables unchanged |

## Sources

- [Microsoft Graph message resource](https://learn.microsoft.com/en-us/graph/api/resources/message?view=graph-rest-1.0) — message identifiers, sender/from distinction, headers, and selectable properties
- [Microsoft Graph Get message](https://learn.microsoft.com/en-us/graph/api/message-get?view=graph-rest-1.0) — application access and permission choices
- [Microsoft Graph permissions reference](https://learn.microsoft.com/en-us/graph/permissions-reference) — breadth of `Mail.Read` and mailbox access restriction guidance
- [Python `zipfile` documentation](https://docs.python.org/3/library/zipfile.html) — explicit warning to inspect untrusted archives before extraction
- [GDAL `ogrinfo` documentation](https://gdal.org/en/stable/programs/ogrinfo.html) — layer schema, feature count, geometry, CRS, and extent inspection
- [GDAL CRS and transformation tutorial](https://gdal.org/en/stable/tutorials/osr_api_tut.html) and [OGR SRS API](https://gdal.org/en/stable/api/ogr_srs_api.html) — CRS representation, transformation, and GDAL 3 axis-order behavior
- [PostgreSQL schemas documentation](https://www.postgresql.org/docs/current/ddl-schemas.html) — qualification, `search_path` trust, schema `USAGE`/`CREATE`
- [PostgreSQL lexical structure](https://www.postgresql.org/docs/current/sql-syntax-lexical.html) — identifier quoting, folding, and 63-byte default limit
- [PostgreSQL explicit locking](https://www.postgresql.org/docs/17/explicit-locking.html) — `ACCESS EXCLUSIVE` behavior for destructive/promotion DDL
- [PostGIS `ST_IsValid`](https://postgis.net/docs/ST_IsValid.html) and [data management guidance](https://postgis.net/docs/en/using_postgis_dbmanagement.html) — validation semantics and the fact validity is not enforced automatically on load
- [PostGIS `Find_SRID`](https://postgis.net/docs/Find_SRID.html) — checking registered geometry SRID

---
*Pitfalls research for: v0.1 End-to-End Vicmap Import Proof*
*Researched: 2026-09-01*
