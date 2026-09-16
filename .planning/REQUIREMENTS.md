# Requirements: Vicmap Database

**Defined:** 2026-09-01
**Core Value:** Vicmap updates must reach the correct PostGIS layers automatically without exposing users to partial, invalid, or duplicate data loads.

## v0.1 Requirements

### Mail Acquisition

- [x] **MAIL-01**: Operator can authenticate with Microsoft Graph and confirm access to the configured automation mailbox without exposing credentials or message bodies.
- [x] **MAIL-02**: Operator can retrieve a bounded set of Inbox messages and identify ready-order candidates using configured sender and message markers.
- [x] **MAIL-03**: Operator can deterministically select exactly one ready-order message and see its redacted identity.
- [x] **MAIL-04**: Operator can download one artifact only from an approved HTTPS host, with redirect, timeout, and size limits enforced.
- [x] **MAIL-05**: Operator can see the downloaded artifact's byte count and checksum.

### Geospatial Discovery

- [x] **GEO-01**: Operator can unpack the order archive into an isolated run directory without permitting path traversal, unsafe links, or writes outside that directory.
- [ ] **GEO-02**: Operator can see every supported geospatial dataset and layer discovered in the unpacked order.
- [ ] **GEO-03**: Operator can see each layer's fields, feature count, geometry type, and source CRS.
- [ ] **GEO-04**: Operator can see the deterministic source-layer-to-table-name mapping before any database mutation.
- [ ] **GEO-05**: Processing stops before database mutation if datasets are unreadable or normalized table names collide.

### PostGIS Staging

- [ ] **DB-01**: Operator can connect to the configured local PostGIS database on port `5432` and verify its non-secret identity and PostGIS version.
- [ ] **DB-02**: Operator can verify that the loader has the required transaction, schema, and table privileges before loading.
- [ ] **DB-03**: Operator can load every selected layer into uniquely named staging tables without creating or modifying tables in `public`.
- [ ] **DB-04**: Operator can see blocking validation results for row counts, geometry columns, geometry types, SRIDs, validity, and extents.
- [ ] **DB-05**: A failed load or validation leaves existing production tables unchanged.

### Publication and Access

- [ ] **PUB-01**: Operator can publish only fully validated staging tables into the dedicated `vicmap` schema.
- [ ] **PUB-02**: All layers from the selected order become visible together through a short transactional publication step, with no partial order publication.
- [ ] **PUB-03**: Publication preserves the previous usable production tables if promotion fails.
- [ ] **PUB-04**: A configured reader role receives schema `USAGE` and table `SELECT` privileges without receiving write privileges.
- [ ] **PUB-05**: Operator can verify table discovery, row access, and a representative spatial query while acting as the non-owner reader role.

### Legacy Cleanup

- [ ] **CLN-01**: Operator can produce a read-only inventory of suspected abandoned WFS tables, including qualified name, owner, size, row estimate, geometry metadata, and dependencies.
- [ ] **CLN-02**: No legacy table can be deleted unless its exact schema-qualified name appears in an explicitly approved cleanup list.
- [ ] **CLN-03**: Operator can review a dry run after the database identity, target identity, and dependencies have been revalidated.
- [ ] **CLN-04**: Operator can delete only the approved exact targets without wildcards or `CASCADE`.
- [ ] **CLN-05**: Legitimate GIS tables and all unapproved tables remain unchanged.

### Proof Evidence

- [ ] **EVID-01**: Operator receives a redacted summary connecting the selected message, artifact checksum, discovered layers, staging validation, published tables, and reader query.
- [ ] **EVID-02**: Any failed stage returns a non-zero result and clearly identifies the failed boundary without exposing secrets.

## Future Requirements

### Operational Hardening

- **OPS-01**: Operator can inspect durable Postgres audit records for messages, orders, artifacts, layers, and load outcomes.
- **OPS-02**: Reprocessing and overlapping invocations cannot duplicate completed work or publish conflicting loads.
- **OPS-03**: Interrupted downloads and loads can retry or resume under an explicit recovery policy.
- **OPS-04**: Operator can detect unexpected source schema, CRS, geometry, count, or extent drift between deliveries.
- **OPS-05**: The pipeline runs daily under systemd with structured journal events and failure notification.

### Extended Scope

- **EXT-01**: Operator can configure additional vendors or geospatial delivery formats.
- **EXT-02**: Operator can use an evidence-based incremental synchronization strategy when complete snapshot replacement is impractical.
- **EXT-03**: Operator can apply an automated retention and cleanup policy backed by reliable ownership metadata and recovery controls.

## Out of Scope

| Feature | Reason |
|---------|--------|
| Unattended daily execution | Safe repetition requires durable audit state, idempotency, locking, retries, and recovery controls not needed for the v0.1 proof. |
| Mailbox folders or read flags as workflow state | Mutable mailbox metadata cannot represent artifact- and layer-level outcomes reliably. |
| Processing all matching historical messages | v0.1 proves one explicitly selected real delivery and does not yet provide replay protection. |
| Loading directly into production | Exposes partial data and risks destroying the previous usable snapshot. |
| Publishing into `public` | Risks collisions with legitimate GIS tables and obscures ownership boundaries. |
| Automatic or cascading legacy-table deletion | Names and catalog metadata cannot prove abandonment; deletion requires exact explicit approval. |
| Incremental feature upserts | Stable source keys, deletion semantics, and schema-evolution behavior are not yet established. |
| General-purpose geospatial ETL framework or management UI | The actual Vicmap delivery contract should be proven before adding abstractions or interface scope. |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| MAIL-01 | Phase 1 | Complete |
| MAIL-02 | Phase 1 | Complete |
| MAIL-03 | Phase 1 | Complete |
| MAIL-04 | Phase 1 | Complete |
| MAIL-05 | Phase 1 | Complete |
| GEO-01 | Phase 2 | Complete |
| GEO-02 | Phase 2 | Gaps Found |
| GEO-03 | Phase 2 | Gaps Found |
| GEO-04 | Phase 2 | Gaps Found |
| GEO-05 | Phase 2 | Gaps Found |
| DB-01 | Phase 3 | Pending |
| DB-02 | Phase 3 | Pending |
| DB-03 | Phase 3 | Pending |
| DB-04 | Phase 3 | Pending |
| DB-05 | Phase 3 | Pending |
| PUB-01 | Phase 4 | Pending |
| PUB-02 | Phase 4 | Pending |
| PUB-03 | Phase 4 | Pending |
| PUB-04 | Phase 4 | Pending |
| PUB-05 | Phase 4 | Pending |
| EVID-01 | Phase 4 | Pending |
| EVID-02 | Phase 4 | Pending |
| CLN-01 | Phase 5 | Pending |
| CLN-02 | Phase 5 | Pending |
| CLN-03 | Phase 5 | Pending |
| CLN-04 | Phase 5 | Pending |
| CLN-05 | Phase 5 | Pending |

**Coverage:**

- v0.1 requirements: 27 total
- Mapped to phases: 27
- Unmapped: 0

---
*Requirements defined: 2026-09-01*
*Last updated: 2026-09-01 after v0.1 roadmap creation*
