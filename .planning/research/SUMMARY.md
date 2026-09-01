# Project Research Summary

**Project:** Vicmap Database
**Domain:** Email-triggered geospatial snapshot ingestion into PostGIS
**Researched:** 2026-09-01
**Confidence:** HIGH, with delivery-contract and database-environment details requiring live validation

## Executive Summary

Vicmap Database v0.1 should be an operator-run vertical proof, not an unattended service: authenticate to the dedicated Microsoft 365 mailbox, select one trusted ready-order email, safely download and inspect one archive, discover every selected spatial layer, load validated staging tables, publish them transactionally into the dedicated `vicmap` schema, and prove access as a non-owner reader. A synchronous Python pipeline with narrow adapters is the appropriate architecture; queues, scheduling, durable ledgers, retries, and generalized ETL abstractions would add risk before the real delivery contract is known.

Keep the working O365 authentication path, add current Nix-pinned GDAL/OGR and Psycopg 3, and use GDAL for spatial discovery/bulk transfer while Psycopg owns catalog checks, validation, privileges, and short publication transactions. Build a complete run manifest before database mutation. Slow loads and validation belong in collision-resistant staging tables; only validated tables enter a short all-layer promotion transaction.

The main risks are destructive trust assumptions at external boundaries: spoofed email or redirects, unsafe archive extraction, plausible-but-wrong CRS/geometry, ambiguous identifiers, replacement DDL that loses grants or blocks readers, and guessed cleanup of legitimate `public` data. Therefore sender and download-host policy, bounded extraction, spatial metadata checks, schema-qualified identifiers, reader-role acceptance, and exact approval-gated cleanup are v0.1 safety requirements—not deferred production polish.

## Key Findings

### Recommended Stack

Retain the existing Python/Nix base and validated O365 integration. Add GDAL/OGR as the spatial data plane and Psycopg 3 as the database control plane. Invoke `ogrinfo`/`ogr2ogr` through checked argument arrays; avoid loading full datasets into GeoPandas or inserting features one at a time. See [STACK.md](STACK.md).

**Core technologies:**

- Python 3.12+ from pinned nixpkgs — orchestration and testable domain policy.
- O365 2.1.9 — preserve the already-working Graph client-credentials integration.
- GDAL 3.13.x (minimum 3.10) — OpenFileGDB discovery and streamed PostGIS loading.
- Psycopg 3.3.4 with Nix `libpq` — safe SQL composition, catalog inspection, validation, grants, and transactional promotion.
- Existing local PostgreSQL/PostGIS service — inspect its identity and versions; do not replace or upgrade it in v0.1.

### Expected Features

The proof is complete only when evidence connects a selected message to an artifact checksum, discovered layers, validated staging tables, published `vicmap.*` tables, and a successful consumer-role spatial query. See [FEATURES.md](FEATURES.md).

**Must have (table stakes):**

- Bounded Graph mailbox read and deterministic trusted ready-message selection.
- Allowlisted HTTPS link extraction, bounded download, checksum, and safe isolated extraction.
- Complete geospatial inventory, deterministic target naming, and collision rejection.
- PostGIS identity/privilege preflight, isolated staging load, and source/target spatial validation.
- Transactional publication only into `vicmap`, with the previous production snapshot preserved on failure.
- `vicmap_reader`-style access and acceptance testing as a non-owner role.
- Read-only legacy inventory followed by exact-name, separately approved cleanup.
- A redacted end-to-end evidence report and non-zero exit on any failed stage.

**Should have (valuable after the proof):**

- Durable provenance and idempotency ledger.
- Retry/resume behavior, concurrency locking, drift detection, structured journald events, and failure notification.
- Automated recurring execution only after those controls exist.

**Defer (v1+):**

- Incremental feature synchronization, multiple vendors/formats, a management UI, and automatic retention/cleanup.

### Architecture Approach

Use a synchronous functional-core/imperative-adapter design. Pure policy handles message matching, URL acceptance, identifier normalization, manifest construction, and validation decisions. Narrow Graph, HTTP/archive/GDAL, and PostGIS adapters handle effects. Three separate commands should own import, read-only inventory, and approved cleanup; cleanup must never be an implicit import stage. See [ARCHITECTURE.md](ARCHITECTURE.md).

**Major components:**

1. CLI/configuration — validate inputs, create a unique run workspace, and orchestrate explicit stages.
2. Graph adapter and ready-order policy — return repository-owned message/order records, not SDK objects.
3. Downloader, safe unpacker, and GDAL discovery — produce a checksum and complete immutable import manifest.
4. Naming policy and PostGIS loader/validator — create only unique, schema-qualified staging objects.
5. Publisher/access provisioner — perform a short all-layer swap, restore ownership/grants, and test consumer access.
6. Legacy inventory/cleanup — report dependencies and accept only revalidated, exact approved targets.

### Critical Pitfalls

1. **Trusting mailbox content or visible link text** — validate sender, actual URL, every redirect, limits, and redaction independently.
2. **Blind archive extraction** — preflight paths, entry types/counts, expansion sizes, collisions, and containment before atomic extraction.
3. **Equating GDAL readability with spatial correctness** — verify all layers, CRS/SRID, geometry types/validity, counts, extents, and normalized-name collisions.
4. **Unsafe or ambiguous SQL identifiers** — normalize conservatively, reject collisions, schema-qualify everything, and compose identifiers with Psycopg.
5. **Calling a long replacement atomic** — bulk-load and index outside production locks; use bounded locks and a short promotion transaction while retaining the known-good table.
6. **Testing access only as the loader** — separately verify schema `USAGE`, table `SELECT`, absence of write rights, and a real spatial query as the reader role.
7. **Deleting legacy tables by inference** — inventory dependencies, require immutable exact approval, recheck targets, avoid `CASCADE`, and prefer recoverability.

## Implications for Roadmap

The dependency order below should be preserved. Each phase ends with observable evidence and leaves later destructive capability unavailable until prerequisite safety contracts exist.

### Phase 1: Trusted Graph Acquisition

**Rationale:** The real email and URL shapes are the largest early unknown and define every downstream artifact contract.
**Delivers:** Refactored Graph adapter, bounded mailbox read, deterministic message selection, sanitized fixture, trusted URL parser, bounded one-artifact download, and checksum evidence.
**Addresses:** Graph login/read, ready-email discovery, and order download.
**Avoids:** Spoofed-message trust, credential/body leakage, arbitrary redirects, and unbounded downloads.

### Phase 2: Safe Archive and Geospatial Discovery

**Rationale:** The actual archive format, layout, layer set, CRS, and scale must be known before target schema or loading decisions can be finalized.
**Delivers:** Safe isolated extraction, GDAL driver verification, full dataset/layer inventory, deterministic normalized names, collision checks, and an import manifest.
**Uses:** Python `zipfile`, GDAL/OpenFileGDB, `ogrinfo`.
**Avoids:** Traversal/expansion attacks, stale workspace contamination, silent layer omission, and CRS/name ambiguity.

### Phase 3: PostGIS Preflight and Validated Staging

**Rationale:** Publication cannot be designed safely until the live server identity, versions, roles, privileges, and actual loaded metadata are verified.
**Delivers:** Psycopg preflight, isolated `vicmap_staging`/`vicmap` boundaries, least-privilege role contract, GDAL bulk loads, indexes, and blocking count/geometry/SRID/extent validation.
**Uses:** Psycopg 3, `ogr2ogr`, PostgreSQL/PostGIS catalogs.
**Avoids:** Writes to `public`, SQL injection/collisions, per-feature performance failure, and spatially incorrect staging data.

### Phase 4: Transactional Publication and Consumer Access

**Rationale:** Only fully validated staging tables can safely enter the short production-critical section.
**Delivers:** Dependency-aware all-layer promotion, bounded locking, last-known-good retention, ownership/grant restoration, post-publish checks, reader-role spatial acceptance, and the complete run evidence report.
**Addresses:** Staging-to-production migration and user-visible table access.
**Avoids:** Partial visibility, lost ACLs/indexes, broken dependencies, excessive blocking, and owner-only false success.

### Phase 5: Legacy Inventory and Approved Cleanup

**Rationale:** Cleanup is independent of import success and must happen only after the new isolated path works; no catalog heuristic can prove abandonment.
**Delivers:** Dependency-rich read-only inventory, immutable approval manifest, database/object identity revalidation, dry-run output, exact non-cascading cleanup, and post-action audit evidence.
**Avoids:** Accidental removal of legitimate GIS tables and cleanup through overly privileged importer credentials.

### Phase Ordering Rationale

- The first real message determines trusted parsing and download behavior; the downloaded artifact determines extraction and GDAL requirements.
- Complete discovery must precede mutation because normalization collisions and unsupported layers are order-wide blockers.
- Database staging follows manifest creation, while production publication follows complete staging validation.
- Reader access is part of publication acceptance because table replacement changes object identity and can lose grants.
- Legacy cleanup is last and separately gated so it cannot endanger or block the import proof.

### Research Flags

Phases likely needing deeper validation during planning:

- **Phase 1:** Inspect a real ready message for sender identity, link/attachment form, redirect chain, expiry, and Graph paging/ID behavior.
- **Phase 2:** Confirm delivered archive type/layout, GDAL driver compatibility, layer counts, CRS/axis order, and practical extraction limits.
- **Phase 3:** Inspect PostgreSQL/PostGIS versions, database fingerprint, role capabilities, dataset size, and GDAL PostgreSQL driver availability.
- **Phase 4:** Inventory dependencies on any existing `vicmap` targets and choose rollback retention/lock policy from measured table sizes.
- **Phase 5:** Determine abandoned-table provenance and recovery options; classification cannot be automated from names alone.

Phases with standard patterns:

- Safe ZIP extraction, identifier composition, schema qualification, and PostgreSQL privilege checks have established primary-source guidance, though project-specific limits still require configuration.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | Official O365/Psycopg/GDAL/PostgreSQL documentation supports the recommended split; live server and driver versions remain to be checked. |
| Features | HIGH | The proof boundary and safety requirements follow directly from the milestone and known live-data constraints. |
| Architecture | HIGH | Synchronous adapters, manifest-before-mutation, staging validation, and short transactional publication are established patterns. |
| Pitfalls | HIGH | Most risks are documented platform behaviors; the exact email/archive contract remains medium-confidence. |

**Overall confidence:** HIGH for roadmap structure; MEDIUM for integration details until the first real delivery and live database are inspected.

### Gaps to Address

- **Ready-email contract:** Capture a redacted real fixture and determine whether the artifact is an attachment or body link, including redirect/expiry behavior.
- **Archive and data profile:** Confirm format, compression, size, number of datasets/layers, 64-bit object IDs, CRS, geometry families, and empty-layer policy.
- **Database identity:** Record database name, server/PostGIS versions, container endpoint fingerprint, existing roles, permissions, and backup/recovery capability.
- **Publication compatibility:** Determine whether any target names already exist and whether dependent views, foreign keys, grants, or stable object identity constrain rename-based replacement.
- **Consumer role:** Identify the actual users/group role and how they should inherit read access without gaining schema creation rights.
- **Legacy provenance:** Establish evidence and recoverability for suspected WFS tables before asking for deletion approval.
- **Credential hygiene:** Confirm repository-local runtime credentials are removed or protected before treating the proof as a deployment baseline.

## Sources

### Primary (HIGH confidence)

- [Microsoft Graph list messages](https://learn.microsoft.com/en-us/graph/api/user-list-messages?view=graph-rest-1.0) — bounded retrieval, selected fields, paging, and mailbox access.
- [Microsoft Graph message resource](https://learn.microsoft.com/en-us/graph/api/resources/message?view=graph-rest-1.0) — message identity and sender fields.
- [Microsoft Graph permissions](https://learn.microsoft.com/en-us/graph/permissions-reference) — mail permission scope.
- [GDAL OpenFileGDB driver](https://gdal.org/en/stable/drivers/vector/openfilegdb.html) — File Geodatabase support and limitations.
- [GDAL `ogrinfo`](https://gdal.org/en/stable/programs/ogrinfo.html) and [`ogr2ogr`](https://gdal.org/en/stable/programs/ogr2ogr.html) — discovery, conversion, loading, and transaction options.
- [GDAL PostgreSQL/PostGIS driver](https://gdal.org/en/stable/drivers/vector/pg.html) — schema, geometry, transactions, and COPY behavior.
- [Python `zipfile`](https://docs.python.org/3/library/zipfile.html) — extraction trust warning and archive APIs.
- [Psycopg installation documentation](https://www.psycopg.org/psycopg3/docs/basic/install.html) — supported runtime and native build choices.
- [PostgreSQL schemas](https://www.postgresql.org/docs/current/ddl-schemas.html), [privileges](https://www.postgresql.org/docs/current/ddl-priv.html), and [explicit locking](https://www.postgresql.org/docs/current/explicit-locking.html) — isolation, access, and publication-lock behavior.
- [PostGIS `ST_IsValid`](https://postgis.net/docs/ST_IsValid.html) and [database management](https://postgis.net/docs/en/using_postgis_dbmanagement.html) — spatial validation and metadata behavior.

### Secondary (MEDIUM confidence)

- [O365 2.1.9 on PyPI](https://pypi.org/project/o365/) and [python-o365 source](https://github.com/O365/python-o365/blob/master/O365/message.py) — current package compatibility and adapter behavior.
- [Requests on PyPI](https://pypi.org/project/requests/) — proposed streaming HTTP client version; validate against the pinned Nix package.

### Tertiary (LOW confidence)

- None. Project-specific assumptions are recorded as gaps rather than presented as sourced facts.

---
*Research completed: 2026-09-01*
*Ready for roadmap: yes*
