# Roadmap: Vicmap Database

## Overview

Milestone v0.1 proves one real Vicmap delivery end to end. Work proceeds from trusted acquisition through manifest creation and validated staging to transactional publication and consumer verification. Legacy WFS cleanup remains a separate, final, explicitly approved operation.

## Phases

- [ ] **Phase 1: Trusted Graph Acquisition** — Select one trusted ready-order message and download its bounded, checksummed artifact.
- [ ] **Phase 2: Safe Geospatial Discovery** — Safely unpack the artifact and build a complete, collision-free layer manifest.
- [ ] **Phase 3: Validated PostGIS Staging** — Preflight the live database and load every selected layer into validated isolated staging tables.
- [ ] **Phase 4: Transactional Publication and Access** — Atomically publish the order into `vicmap` and prove non-owner access with redacted evidence.
- [ ] **Phase 5: Approved Legacy Cleanup** — Inventory suspected abandoned WFS tables and delete only exact, revalidated, explicitly approved targets.

### Phase 1: Trusted Graph Acquisition

**Goal:** The operator can obtain exactly one authentic Vicmap order artifact from the automation mailbox without leaking sensitive content or trusting an unsafe download path.

**Depends on:** Nothing (first phase)

**Requirements:** MAIL-01, MAIL-02, MAIL-03, MAIL-04, MAIL-05

**Success Criteria:**

1. The operator authenticates to Microsoft Graph, confirms the configured mailbox, and inspects a bounded Inbox result without credentials or message bodies appearing in output.
2. Configured sender and ready-order markers identify candidates, and the operator deterministically selects exactly one message whose displayed identity is redacted.
3. The selected message yields one artifact through an approved HTTPS host while redirect, timeout, and size limits are enforced.
4. The completed download reports its byte count and checksum for downstream provenance.

**Plans:** TBD

### Phase 2: Safe Geospatial Discovery

**Goal:** The operator can turn the downloaded order into a complete, immutable import manifest before any database mutation.

**Depends on:** Phase 1

**Requirements:** GEO-01, GEO-02, GEO-03, GEO-04, GEO-05

**Success Criteria:**

1. The archive is extracted into an isolated run directory, and traversal paths, unsafe links, or any attempted write outside that directory are rejected.
2. The operator sees every supported dataset and layer in the delivery, including fields, feature count, geometry type, and source CRS.
3. Every source layer has a deterministic target table name visible before loading begins.
4. An unreadable dataset or normalized-name collision stops the run before any database object is changed.

**Plans:** TBD

### Phase 3: Validated PostGIS Staging

**Goal:** Every selected layer is safely loaded and spatially validated in isolated staging while existing production data remains unchanged.

**Depends on:** Phase 2

**Requirements:** DB-01, DB-02, DB-03, DB-04, DB-05

**Success Criteria:**

1. The operator connects to the configured PostGIS service on port `5432` and sees its non-secret database identity and PostGIS version.
2. The loader proves it has the necessary transaction, schema, and table privileges before any load starts.
3. Every selected manifest layer loads into a uniquely named staging table, with no table created or modified in `public`.
4. Blocking validation reports row counts, geometry columns and types, SRIDs, validity, and extents for all staging tables.
5. A failed load or validation leaves all existing production tables unchanged.

**Plans:** TBD

### Phase 4: Transactional Publication and Access

**Goal:** The complete validated order becomes queryable in `vicmap` as one atomic publication that retains the last usable version on failure.

**Depends on:** Phase 3

**Requirements:** PUB-01, PUB-02, PUB-03, PUB-04, PUB-05, EVID-01, EVID-02

**Success Criteria:**

1. Only fully validated staging tables can be promoted, and every published target is schema-qualified under `vicmap`.
2. All order layers become visible together in one short transaction; an induced promotion failure exposes no partial order and preserves the previous usable tables.
3. The configured reader role can discover tables, select rows, and run a representative spatial query, but cannot write to published tables.
4. A redacted run summary links the selected message, artifact checksum, discovered layers, staging validation, published tables, and reader verification.
5. Any stage failure returns a non-zero result identifying the failed boundary without exposing secrets.

**Plans:** TBD

### Phase 5: Approved Legacy Cleanup

**Goal:** Suspected abandoned WFS tables can be reviewed and selectively removed without endangering legitimate GIS data.

**Depends on:** Phase 4

**Requirements:** CLN-01, CLN-02, CLN-03, CLN-04, CLN-05

**Success Criteria:**

1. A read-only inventory lists each suspected WFS table's qualified name, owner, size, row estimate, geometry metadata, and dependencies.
2. A cleanup dry run accepts only exact schema-qualified names from an explicit approval list and revalidates the database, targets, and dependencies.
3. Execution drops only the approved exact targets, using neither wildcards nor `CASCADE`.
4. Post-cleanup verification shows legitimate GIS tables and every unapproved table remain unchanged.

**Plans:** TBD

## Progress

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Trusted Graph Acquisition | 0/TBD | Not started | — |
| 2. Safe Geospatial Discovery | 0/TBD | Not started | — |
| 3. Validated PostGIS Staging | 0/TBD | Not started | — |
| 4. Transactional Publication and Access | 0/TBD | Not started | — |
| 5. Approved Legacy Cleanup | 0/TBD | Not started | — |

---
*Roadmap created: 2026-09-01*
