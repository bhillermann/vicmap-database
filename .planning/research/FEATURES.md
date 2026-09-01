# Feature Research

**Domain:** Email-triggered geospatial snapshot ingestion into PostGIS
**Researched:** 2026-09-01
**Confidence:** HIGH for the v0.1 boundary; MEDIUM for the exact Vicmap email/link contract until a real ready-order message and archive are inspected

## Executive Recommendation

Milestone v0.1 should be a deliberately narrow, operator-run proof: select one real ready-order message, download exactly one artifact into a fresh run directory, inventory its geospatial contents, load every selected spatial layer into isolated staging tables, validate the load, and publish the tables in the dedicated `vicmap` schema. The proof is complete only when a non-owner database role can run a spatial query against a published table.

The proof must still preserve three safety boundaries. It must never follow a link from an untrusted sender, never create or replace a table outside `vicmap`, and never delete an existing table without presenting its fully qualified name for explicit approval. These are not production-hardening extras: they prevent an exploratory run from damaging the live mailbox host or database.

Do not build scheduling, a durable delivery ledger, incremental synchronization, notification email, or generalized recovery in v0.1. Capture enough evidence (message ID, source URL host, archive path/checksum, layer inventory, row counts, CRS, target names, and final query result) to make the one-run outcome reviewable; turn that evidence into durable state in a later milestone.

## Feature Landscape

### Table Stakes (Required v0.1 Proof Behavior)

| Feature | Why Expected | Complexity | Required behavior in v0.1 |
|---------|--------------|------------|----------------------------|
| Explicit Graph authentication and mailbox access check | A successful token acquisition is not proof that the intended mailbox and folder are readable | MEDIUM | Use application credentials, open only `automations@vegetationlink.com.au` Inbox, perform one bounded message query, fail clearly if authentication or mailbox access fails, and log only allowlisted metadata |
| Deterministic ready-message selection | A proof must show which message caused the import and avoid accidentally choosing a confirmation or unrelated email | MEDIUM | Filter on configured trusted sender plus ready-message markers; show message ID, sender, subject, and received time; require exactly one selected message (or explicit operator selection when multiple match) |
| Trusted-link extraction | Email is an input boundary, not automatic authorization to access arbitrary URLs | MEDIUM | Extract candidate HTTPS links from the selected message, allow only configured sender identities and expected download host(s), reject credentials in URLs, redirects to unapproved hosts, and ambiguous multiple candidates |
| Bounded artifact download | A partial HTML error page or unbounded response must not be treated as an order archive | MEDIUM | Use timeouts, redirect/host checks, a maximum byte limit, a fresh destination, status/content checks, and compute a checksum; do not overwrite an existing artifact silently |
| Safe, isolated unpack | Archives can contain traversal paths, symlinks, nested archives, or unexpected file types | MEDIUM | Extract to a run-specific directory only after validating member paths; reject members escaping the root and report unexpected content; retain the original archive for inspection |
| Geospatial dataset and layer inventory | “Archive unpacked” does not prove the delivered data is readable | MEDIUM | Open each supported dataset with the chosen geospatial driver; enumerate dataset, layer, geometry type, feature count, fields, and source CRS; fail on unreadable spatial datasets rather than silently skipping them |
| Deterministic target naming and collision detection | Automatic discovery is safe only if source names map predictably and uniquely to PostgreSQL identifiers | MEDIUM | Normalize to lowercase `snake_case`, validate identifier length/characters, show source-to-target mapping, and stop if two source layers normalize to the same table name |
| Explicit PostGIS connection preflight | A TCP connection alone does not prove the target database, PostGIS extension, or required privileges are available | LOW | Connect via configured host/port/database/role; display non-secret server identity and PostGIS version; verify transaction, schema-create/use, and table-create capabilities before loading |
| Isolated staging load | Users must not observe a half-loaded production table | HIGH | Load into uniquely named staging tables in a loader-owned staging namespace or temporary run namespace; never load directly into `public` or the final `vicmap.<table>` name |
| Spatial and count validation | A loader can report success while producing empty, invalidly typed, or wrongly referenced data | MEDIUM | For each staging table verify expected row count, geometry column presence, non-null/empty geometry statistics, geometry type compatibility, SRID/CRS, readable extent, and representative queryability; record warnings separately from blocking failures |
| Transactional publication into `vicmap` | The core value requires a complete table to become visible, not a partially copied one | HIGH | Create the dedicated schema, replace/rename only fully validated staging tables inside a transaction, preserve the existing production table if validation or publication fails, and use schema-qualified SQL throughout |
| Reader access verification | Owner access is not evidence that intended GIS users can use the data | MEDIUM | Grant a named reader role `USAGE` on `vicmap` and `SELECT` on published tables, set appropriate default privileges for later tables, and run a representative `SELECT`/spatial query as that role |
| Existing-table inventory and approval-gated cleanup | The database contains legitimate `public` GIS tables and abandoned WFS tables that cannot be distinguished safely by guesswork | MEDIUM | Produce a read-only inventory with fully qualified name, owner, size, row estimate, geometry metadata, and likely provenance; accept an explicit list of exact names; re-resolve and display that list before any drop; never use wildcard or `CASCADE` cleanup |
| End-to-end evidence summary | A one-off proof needs objective evidence that each boundary worked | LOW | Emit a final redacted summary connecting selected message → artifact checksum → discovered layers → staging validation → published tables → reader query; return non-zero on any failed stage |

### Differentiators (Useful, Mostly After v0.1)

| Feature | Value Proposition | Complexity | Timing |
|---------|-------------------|------------|--------|
| Automatic multi-layer discovery | New or renamed layers can be imported without maintaining a brittle order-to-table manifest | HIGH | Demonstrate deterministic discovery in v0.1; harden compatibility and policy later |
| Validated snapshot publication | Users keep the previous complete dataset until a replacement has passed spatial checks | HIGH | Core differentiator and required v0.1 behavior |
| End-to-end provenance | A table can be traced back to message, order, artifact checksum, source dataset, and load outcome | HIGH | Emit a run report in v0.1; add durable Postgres audit records later |
| Schema isolation from existing GIS assets | Vicmap data is discoverable while legitimate `public` assets remain outside the loader's mutation scope | LOW | Required v0.1 behavior |
| Approval-gated legacy cleanup | Operators get useful cleanup assistance without letting heuristics destroy production data | MEDIUM | Inventory and exact-name approval in v0.1; richer lineage detection later |
| Failure-resumable processing | Large downloads/loads can restart without repeating completed work | HIGH | Defer until real artifact sizes and failure modes are measured |
| Data-quality drift detection | Alerts when fields, geometry types, CRS, counts, or extents change unexpectedly between deliveries | HIGH | Add after at least two real snapshots provide a baseline |

### Anti-Features (Commonly Requested, Often Problematic)

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| Daily unattended scheduling in v0.1 | Makes the proof feel automated | Repeats immature mailbox, download, and destructive database behavior before its contracts are known | Run an explicit operator command; schedule only after idempotency, locking, retry policy, and audit state exist |
| Mailbox folders or read/unread flags as workflow state | Visually simple and requires no database state | Flags are mutable, folder moves can fail, and they cannot represent artifact or layer-level outcomes | Record evidence in the proof report, then add a durable Postgres ledger keyed by immutable message/artifact identifiers |
| Process every matching historical email | Demonstrates throughput | Multiplies ambiguity and can replay stale orders into production | Select one real ready email explicitly; add ordered backlog processing after idempotency exists |
| Follow any link in a recognized-looking email | Avoids vendor-specific parsing | Enables phishing/SSRF-style behavior and arbitrary downloads if a mailbox or sender is spoofed/compromised | Require trusted sender and expected HTTPS host, validate redirect targets, and fail closed on ambiguity |
| Load directly into production tables | Fewer SQL operations and less disk use | Exposes partial data and can destroy the prior usable snapshot on failure | Load isolated staging, validate, then publish transactionally |
| Publish into `public` | Existing users already search there | Risks collisions and accidental mutation of legitimate GIS tables; obscures ownership | Publish only to `vicmap` and grant reader access explicitly |
| Guess and delete abandoned WFS tables automatically | Quickly recovers storage and reduces clutter | Table names and metadata are insufficient proof of ownership; `CASCADE` can remove dependencies | Generate inventory, obtain exact-name approval, re-check identity/dependencies, then use non-cascading drops |
| Incremental feature upserts | Appears efficient for large datasets | Requires stable source keys, delete semantics, and schema-evolution rules not yet demonstrated | Treat each order layer as a complete snapshot and replace validated tables atomically |
| Silently transform unknown CRS | Makes mixed inputs appear uniform | A wrong or inferred source CRS produces plausible but spatially incorrect output | Require declared/recognized CRS; preserve it for the proof or apply only an explicitly configured transformation |
| General-purpose geospatial ETL framework | Promises reuse for every vendor and format | Expands configuration and testing before the real Vicmap contract is known | Support the actual delivered format first behind narrow dataset/layer interfaces |
| Logging full messages, URLs, or credentials | Convenient debugging | Mail bodies and signed download URLs may be sensitive and can leak into shell history/journal | Log allowlisted metadata, redact URL query strings, and keep secrets outside the checkout |

## Feature Dependencies

```text
[Graph credentials + mailbox authorization]
    └──requires──> [Bounded message retrieval]
                       └──requires──> [Trusted ready-message selection]
                                          └──requires──> [Approved-link extraction]
                                                             └──requires──> [Bounded download]
                                                                                └──requires──> [Safe unpack]
                                                                                                   └──requires──> [Dataset/layer inventory]

[PostGIS connection + privilege preflight]
    └──requires──> [Dedicated schema and isolated staging]
                       └──requires──> [Deterministic target mapping]
                                          └──requires──> [Staging load]
                                                             └──requires──> [Spatial/count validation]
                                                                                └──requires──> [Transactional publication]
                                                                                                   └──requires──> [Reader grants and query verification]

[Existing-table inventory] ──requires──> [Exact operator-approved drop list]
[Exact operator-approved drop list] ──conflicts──> [Heuristic or cascading deletion]
[Durable provenance ledger] ──enhances──> [Repeatable/idempotent processing]
[Scheduling] ──requires──> [Idempotency + locking + retries + durable audit]
```

### Dependency Notes

- **Ready-message selection requires bounded retrieval:** the program must make paging and selection behavior explicit; Microsoft Graph returns paged results and callers must follow the complete `@odata.nextLink` rather than inventing offsets.
- **Link extraction requires sender and host trust:** selecting by subject text alone does not establish that an external URL is safe to follow.
- **Layer loading requires inventory and collision detection:** target tables cannot be chosen safely until every source layer has been enumerated and the full normalized mapping is known.
- **Publication requires staging validation:** transactionality protects the catalog change, but cannot establish that the incoming spatial content is correct.
- **Reader verification requires both schema and table privileges:** PostgreSQL requires schema `USAGE` as well as object privileges such as table `SELECT`.
- **Cleanup is independent of import success:** discovering likely WFS leftovers does not prove ownership. Keep cleanup as a separately approved operation so it cannot become an implicit prerequisite or rollback action for the import.
- **Scheduling requires production controls:** without a durable ledger and run lock, repeated polling can replay messages or overlap loads.

## MVP Definition

### Launch With (v0.1)

- [ ] **Authenticate and read one bounded Inbox result set** — proves Graph application access to the intended mailbox without dumping message content.
- [ ] **Select one trusted real ready-order message** — makes the proof input explicit and reviewable.
- [ ] **Download one approved artifact and unpack it safely** — proves the delivery handoff while bounding filesystem and network risk.
- [ ] **Inventory and read all selected geospatial layers** — establishes actual driver compatibility, field/geometry metadata, CRS, and scale.
- [ ] **Connect to the real local PostGIS service on port 5432** — verifies database identity, PostGIS availability, and loader privileges.
- [ ] **Load into isolated staging and validate** — proves rows and spatial metadata survive ingestion without touching production early.
- [ ] **Publish validated tables only into `vicmap`** — delivers the milestone's user-visible dataset while preserving `public`.
- [ ] **Query the published tables as a reader role** — verifies practical access, not merely loader-owner access.
- [ ] **Inventory suspected WFS leftovers and gate exact drops on approval** — supports cleanup without coupling destructive action to import.
- [ ] **Produce a redacted evidence summary** — makes pass/fail and the source-to-table mapping auditable for this proof.

### Add After Validation (v0.2–v0.x)

- [ ] **Durable Postgres delivery/load ledger** — add before processing multiple or recurring messages; key message, order, artifact checksum, layers, and outcomes.
- [ ] **Idempotent replay and concurrency lock** — add before scheduling or allowing overlapping invocations.
- [ ] **Retry/backoff and resumable downloads/loads** — add after observed Graph, vendor-host, and dataset-size behavior informs sensible policies.
- [ ] **Schema and data-drift gates** — add after a second snapshot establishes comparison semantics and acceptable variation.
- [ ] **Failure-only notifications and structured journald events** — add when runs become unattended.
- [ ] **Automated daily systemd execution** — add last, after safe repetition, credentials, logging, and recovery are proven.
- [ ] **Previous-version retention/rollback policy** — add when actual table sizes and recovery-time needs are known.
- [ ] **Automated tests with Graph/download fakes and disposable PostGIS integration tests** — introduce alongside each component; require a full suite before unattended use.

### Future Consideration (v1+)

- [ ] **Incremental or change-only loading** — consider only if snapshot load duration/storage remains unacceptable and stable source keys plus delete semantics are documented.
- [ ] **Multiple mailboxes/vendors/formats** — defer until the real Vicmap pipeline is stable and abstractions are supported by evidence.
- [ ] **Self-service order management UI** — unnecessary for an operator-run ingestion service until workflow volume justifies it.
- [ ] **Automated retention and cleanup** — defer until ownership metadata and backup/restore policy can make deletion reliably recoverable.

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| Graph auth + bounded mailbox read | HIGH | MEDIUM | P1 |
| Trusted ready-message and link selection | HIGH | MEDIUM | P1 |
| Bounded download + safe unpack | HIGH | MEDIUM | P1 |
| Geospatial inventory/read proof | HIGH | MEDIUM | P1 |
| PostGIS connection/privilege preflight | HIGH | LOW | P1 |
| Deterministic target mapping | HIGH | MEDIUM | P1 |
| Isolated staging + validation | HIGH | HIGH | P1 |
| Transactional `vicmap` publication | HIGH | HIGH | P1 |
| Reader-role access verification | HIGH | MEDIUM | P1 |
| Approval-gated legacy inventory/cleanup | MEDIUM | MEDIUM | P1 (safety requirement) |
| Redacted evidence summary | MEDIUM | LOW | P1 |
| Durable audit ledger/idempotency | HIGH | HIGH | P2 (required before automation) |
| Drift detection | HIGH | HIGH | P2 |
| Scheduling and notifications | MEDIUM | MEDIUM | P2 |
| Incremental synchronization | LOW for current snapshot contract | HIGH | P3 |
| General-purpose ETL/UI | LOW | HIGH | P3 |

**Priority key:**

- P1: Must have for the v0.1 proof
- P2: Production-hardening required before unattended recurring use
- P3: Defer until evidence shows a need

## Alternative Approach Analysis

These are alternatives rather than direct commercial competitors; the comparison is intended to sharpen the feature boundary.

| Capability | Manual desktop GIS import | WFS synchronization | Generic managed ETL | Recommended pipeline |
|------------|---------------------------|---------------------|----------------------|----------------------|
| Delivery trigger | Operator finds/downloads email | Poll service endpoint | Connector schedule/event | Select trusted Vicmap ready email |
| Large complete dataset | Repetitive and operator-bound | Prior attempt was too slow in this environment | Depends on connector/format support and cost | Download vendor snapshot once, then bulk-read locally |
| Layer discovery | Visual/operator choice | Service-layer enumeration | Connector mapping/configuration | Enumerate delivered datasets/layers deterministically |
| Publication safety | Varies by operator procedure | Usually per-feature or per-batch updates | Product-specific | Validate isolated staging, then transactionally publish |
| Existing `public` protection | Relies on operator care | Target mapping dependent | Configuration dependent | Hard boundary: loader manages only `vicmap` |
| Provenance | Manual notes | Endpoint/request logs | Platform run metadata | Source message/artifact/layer/table evidence, durable ledger later |
| Local control | High but manual | High | Lower; external service dependency | High, reproducible Nix/Python/PostGIS stack |

The recommended approach is preferable for this milestone because the authoritative delivery is already a complete order archive, the earlier WFS approach was operationally too slow, and the main risk is safe publication into an existing database—not continuous feature-level synchronization.

## Acceptance Shape for the v0.1 Proof

The demonstration should produce concrete evidence for this chain:

1. The configured application authenticates and reads a bounded set of messages from the intended Inbox.
2. Exactly one trusted ready-order message is selected and its redacted identity is shown.
3. Exactly one approved HTTPS download completes with byte count and checksum, then safely extracts into an isolated directory.
4. Every selected spatial layer is opened and reported with source name, target name, count, geometry type, and CRS.
5. The loader connects to the intended local database and confirms PostGIS and required privileges.
6. Each layer loads into staging and passes blocking validation.
7. One transaction publishes the validated tables under schema-qualified `vicmap.*` names; no `public` table is created, renamed, replaced, or dropped.
8. A non-owner reader role successfully lists and queries the published tables, including a representative geometry query.
9. Suspected abandoned WFS tables are reported separately. No table is dropped until the operator supplies and reconfirms exact fully qualified names.
10. A failed stage exits non-zero and leaves the previous production tables intact.

## Sources

- [Microsoft Graph: List messages](https://learn.microsoft.com/en-us/graph/api/user-list-messages?view=graph-rest-1.0) — application mailbox access, least-privilege permissions, `$select`/`$top`, paging, and `@odata.nextLink` behavior.
- [Microsoft Graph permissions reference](https://learn.microsoft.com/en-us/graph/permissions-reference) — `Mail.ReadBasic.All` excludes message bodies and attachments; reading ready-message content or download links may therefore require `Mail.Read`, scoped to the target mailbox by tenant policy where available.
- [Microsoft Graph mail API overview](https://learn.microsoft.com/en-us/graph/api/resources/mail-api-overview?view=graph-rest-1.0) — application access to organization mailboxes and shared-mailbox support.
- [GDAL: ogr2ogr](https://gdal.org/en/stable/programs/ogr2ogr.html) — official bulk vector conversion/loading interface, layer selection, overwrite/update modes, geometry typing, CRS transformation, transactions, and PostgreSQL destination support.
- [GDAL: OpenFileGDB driver](https://gdal.org/en/stable/drivers/vector/openfilegdb.html) — official File Geodatabase read/write capabilities and driver constraints.
- [GDAL: PostgreSQL/PostGIS driver](https://gdal.org/en/stable/drivers/vector/pg.html) — PostgreSQL connection, schema/layer creation, geometry, and bulk-load behavior.
- [PostgreSQL: Schemas](https://www.postgresql.org/docs/current/ddl-schemas.html) — schema-qualified object isolation, `USAGE`/`CREATE`, secure `search_path` guidance, and separate schemas for shared applications.
- [PostgreSQL: Privileges](https://www.postgresql.org/docs/current/ddl-priv.html) — object ownership and `CONNECT`, schema `USAGE`, table `SELECT`, and other grant semantics.
- [PostgreSQL: Transaction isolation](https://www.postgresql.org/docs/current/transaction-iso.html) — transaction visibility semantics supporting publish-after-validation behavior.
- [PostGIS: Database management](https://postgis.net/docs/en/using_postgis_dbmanagement.html) — geometry metadata, geometry types, SRIDs, and `spatial_ref_sys` behavior.
- [Python: `zipfile` extraction warning](https://docs.python.org/3/library/zipfile.html#zipfile.ZipFile.extractall) — archive members must be validated to prevent traversal outside the extraction directory.

---
*Feature research for: v0.1 End-to-End Vicmap Import Proof*
*Researched: 2026-09-01*
