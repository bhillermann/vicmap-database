# Roadmap: Vicmap Database

## Overview

Milestone v0.1 proves one real Vicmap delivery end to end. Work proceeds from trusted acquisition through manifest creation and validated staging to transactional publication and consumer verification. Legacy WFS cleanup remains a separate, final, explicitly approved operation.

## Phases

- [x] **Phase 1: Trusted Graph Acquisition** — Select one trusted ready-order message and download its bounded, checksummed artifact.
- [x] **Phase 2: Safe Geospatial Discovery** — Safely unpack the artifact and build a complete, collision-free layer manifest. (completed 2026-09-17)
- [x] **Phase 3: Validated PostGIS Staging** — Preflight the live database and load every selected layer into validated isolated staging tables. (completed 2026-09-22)
- [x] **Phase 4: Transactional Publication and Access** — Atomically publish the order into `vicmap` and prove non-owner access with redacted evidence. (completed 2026-09-25)
- [x] **Phase 5: Approved Legacy Cleanup** — Inventory suspected abandoned WFS tables and delete only exact, revalidated, explicitly approved targets. (completed 2026-09-28)

### Phase 1: Trusted Graph Acquisition

**Goal:** The operator can obtain exactly one authentic Vicmap order artifact from the automation mailbox without leaking sensitive content or trusting an unsafe download path.

**Depends on:** Nothing (first phase)

**Requirements:** MAIL-01, MAIL-02, MAIL-03, MAIL-04, MAIL-05

**Success Criteria:**

1. The operator authenticates to Microsoft Graph, confirms the configured mailbox, and inspects a bounded Inbox result without credentials or message bodies appearing in output.
2. Configured sender and ready-order markers identify candidates, and the operator deterministically selects exactly one message whose displayed identity is redacted.
3. The selected message yields one artifact through an approved HTTPS host while redirect, timeout, and size limits are enforced.
4. The completed download reports its byte count and checksum for downstream provenance.

**Plans:** 14/14 plans complete

**Status:** Complete — verified 2026-09-14, 21/21 must-haves (`01-VERIFICATION.md`)

Plans:

- [x] 01-14-PLAN.md

- [x] 01-13-PLAN.md

- [x] 01-12-PLAN.md

**Wave 1**

- [x] 01-01-PLAN.md — Prove one safe end-to-end Graph-to-artifact tracer and configuration boundary.

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 01-02-PLAN.md — Harden memory-only Graph authentication, mailbox access, and complete metadata pagination.
- [x] 01-03-PLAN.md — Enforce exact ready-order recognition and deterministic newest-message selection.
- [x] 01-04-PLAN.md — Enforce approved HTTPS redirects, timeouts, byte ceilings, hashing, and atomic finalization.

**Wave 3** *(blocked on Wave 2 completion)*

- [x] 01-05-PLAN.md — Compose closed redacted evidence and record one controlled live acquisition.

*Gap closure — created after `gsd-verify-work` recorded `gaps_found` (15/21 must-haves).*

**Gap-closure Wave 1**

- [x] 01-06-PLAN.md — Prove authenticated message origin and authorized bucket/path target end to end.

**Gap-closure Wave 2** *(blocked on Gap-closure Wave 1)*

- [x] 01-07-PLAN.md — Collect archive URLs only from rendered HTML context and close the MAIL-02/MAIL-03 edge gaps.
- [x] 01-08-PLAN.md — Define the publication commit point and authorize every redirect hop against the URL prefix.
- [x] 01-09-PLAN.md — Unify the policy validator and fingerprint contract and guard evidence delivery.
- [x] 01-10-PLAN.md — Retrieve MIME in one request and add runtime read-only enforcement evidence.

**Gap-closure Wave 3** *(blocked on Gap-closure Wave 2)*

- [x] 01-11-PLAN.md — Record one connected live proof and disposition every declared prohibition.

### Phase 2: Safe Geospatial Discovery

**Goal:** The operator can turn the downloaded order into a complete, immutable import manifest before any database mutation.

**Depends on:** Phase 1

**Requirements:** GEO-01, GEO-02, GEO-03, GEO-04, GEO-05

**Success Criteria:**

1. The archive is extracted into an isolated run directory, and traversal paths, unsafe links, or any attempted write outside that directory are rejected.
2. The operator sees every supported dataset and layer in the delivery, including fields, feature count, geometry type, and source CRS.
3. Every source layer has a deterministic target table name visible before loading begins.
4. An unreadable dataset or normalized-name collision stops the run before any database object is changed.

**Plans:** 9/9 plans complete

Plans:

**Wave 1**

- [x] 02-01-PLAN.md — Make the geospatial toolchain reproducible and prove one artifact-to-manifest path end to end.

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 02-02-PLAN.md — Persist the Phase 1 provenance sidecar and make Phase 2 policy reviewable in `vicmap.toml`.
- [x] 02-03-PLAN.md — Make archive extraction fail closed on every guard and ceiling.
- [x] 02-04-PLAN.md — Profile every layer completely and confirm it against an independent `ogrinfo` oracle.
- [x] 02-05-PLAN.md — Make every target table name deterministic and same-delivery collisions a hard stop.

**Wave 3** *(blocked on Wave 2 completion)*

- [x] 02-06-PLAN.md — Settle the immutable manifest contract, prove every hard stop lands before it is written, and record one live proof.

*Gap closure — created after `gsd-verify-work` recorded `gaps_found` (3/6 must-haves; GEO-01 and GEO-05 blocked).*

**Gap-closure Wave 1**

- [x] 02-07-PLAN.md — Make the shipped `vicmap.toml` able to process the real delivery, proven end to end, and recognize dataset extensions in any letter case.
- [x] 02-08-PLAN.md — Key the extraction aliasing guard on destination identity so recorded provenance can never describe a file that is not on disk.

**Gap-closure Wave 2** *(blocked on Gap-closure Wave 1)*

- [x] 02-09-PLAN.md — Roll back a partially published manifest so a hard stop leaves nothing behind and a retry can proceed.

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

**Plans:** 6/6 plans complete

Plans:

**Wave 1**

- [x] 03-01-PLAN.md — Gate the `psycopg` supply chain, correct D-50's missing `proj-data`, and put the driver, `psql`, the reprojection grid, and the password secret in the dev shell.
- [x] 03-02-PLAN.md — Add the `[database]` section, widen the policy contract to five sections, and make every database rule fail closed in one validator.
- [x] 03-03-PLAN.md — Extend the closed evidence vocabulary with the database boundary and add a digest-verified reader for Phase 2's frozen manifest.

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 03-04-PLAN.md — Prove one manifest layer reaches a named staging table end to end, then make the privilege preflight prove capability.

**Wave 3** *(blocked on Wave 2 completion)*

- [x] 03-05-PLAN.md — Make DB-04 validation blocking and complete: two profiles, three manifest checks, a counted repair, and two repair hard stops.

**Wave 4** *(blocked on Wave 3 completion)*

- [x] 03-06-PLAN.md — Constrain and index every validated table, run layers sequentially with named diagnostics, and prove production is untouched on failure.

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

**Plans:** 6/6 plans complete

Plans:

**Wave 1**

- [x] 04-01-PLAN.md — Extend the closed evidence vocabulary for the publication, audit-gate, and reader-verification boundaries (3 stages, 7 reason codes, the redacted publication_summary event).
- [x] 04-02-PLAN.md — Add the reader-role config contract and provision the vicmap_audit gate table + least-privilege reader role + reader secret.

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 04-03-PLAN.md — Back-fill Phase 3 so it persists a durable PASS validation record per layer for the publish gate to trust.

**Wave 3** *(blocked on Wave 2 completion)*

- [x] 04-04-PLAN.md — Add publish.py and promote every validated layer into vicmap as one atomic, previous-preserving transaction with catalog-discovered canonical names and an in-transaction reader grant.

**Wave 4** *(blocked on Wave 3 completion)*

- [x] 04-05-PLAN.md — Prove reader access (PUB-05) from a real reader login: discovery, a GiST-exercising spatial query, and a security-critical denied write.

**Wave 5** *(blocked on Wave 4 completion)*

- [x] 04-06-PLAN.md — Assemble the redacted EVID-01 summary from durable artifacts and add publish_order.py with the EVID-02 exit-code contract.

### Phase 5: Approved Legacy Cleanup

**Goal:** Suspected abandoned WFS tables can be reviewed and selectively removed without endangering legitimate GIS data.

**Depends on:** Phase 4

**Requirements:** CLN-01, CLN-02, CLN-03, CLN-04, CLN-05

**Success Criteria:**

1. A read-only inventory lists each suspected WFS table's qualified name, owner, size, row estimate, geometry metadata, and dependencies.
2. A cleanup dry run accepts only exact schema-qualified names from an explicit approval list and revalidates the database, targets, and dependencies.
3. Execution drops only the approved exact targets, using neither wildcards nor `CASCADE`.
4. Post-cleanup verification shows legitimate GIS tables and every unapproved table remain unchanged.

**Plans:** 0/0 plans complete

**Status:** Complete — satisfied by operator manual cleanup; live catalog inspection 2026-09-28 confirmed no abandoned WFS tables remain (`05-VERIFICATION.md`, `05-CLOSEOUT.md`). No deletion tooling built.

## Progress

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Trusted Graph Acquisition | 14/14 | Complete    | 2026-09-23 |
| 2. Safe Geospatial Discovery | 9/9 | Complete    | 2026-09-17 |
| 3. Validated PostGIS Staging | 6/6 | Complete    | 2026-09-22 |
| 4. Transactional Publication and Access | 6/6 | Complete    | 2026-09-25 |
| 5. Approved Legacy Cleanup | 0/0 | Complete    | 2026-09-28 |

---
*Roadmap created: 2026-09-01*

### Phase 05.1: Address tech debt: publish resume path (#16) (INSERTED)

**Goal:** A publish run that failed after its promotion committed can be re-run to completion, and each failure is reported at its true boundary instead of being stranded and misreported as `pub_promotion_failed` (WINDOWS.md #16).

**Depends on:** Phase 5

**Requirements:** None mapped. This is v0.1 tech debt. It advances OPS-03 for the publish stage only and closes the retry case left open under EVID-02.

**Success Criteria:**

1. Re-running publish for a `(run_ts, manifest_digest)` whose promotion already committed detects the published generation and skips promotion, rather than re-entering `_promote_layer` and failing with `UndefinedTable` on the consumed staging table.
2. The resumed run completes the post-commit steps (`verify_reader_access`, `read_layer_validations`, `assemble_summary`, `write_summary`), writes the EVID-01 `summary.json`, and exits 0.
3. A failure in a post-commit step reports that step's own boundary (e.g. `db_reader_verify`), and `pub_promotion_failed` is reserved for real promotion failures.
4. An ambiguous state (published tables from a different run or digest, or a partial promotion) fails closed with a named reason and issues no `DROP`.
5. Tests cover the retry-after-post-commit-failure path, and WINDOWS.md #16 is marked fixed with evidence.

**Plans:** 1/5 plans executed

Plans:

**Wave 1**

- [x] 05.1-01-PLAN.md — Tracer: write a per-layer `vicmap_audit.publication` marker inside the promotion transaction, classify before any DDL, and resume a committed promotion via `promote_or_resume`, proven live by reproducing the 2026-09-24 incident; register the closed resume vocabulary.

**Wave 2** *(blocked on Wave 1 completion)*

- [ ] 05.1-02-PLAN.md — Fail closed with no DDL on every non-resumable state: superseded, unproven (including the pre-fix `vicmap.vmadd_address`), conflicted, mixed, and empty orders.

**Wave 3** *(blocked on Wave 2 completion)*

- [ ] 05.1-03-PLAN.md — Make a resumed run visible (`publication_resumed` event, `promotion`/`published_at` summary fields), make a re-run after success an idempotent resume, and write `summary.json` atomically behind a `pub_summary_failed` boundary.

**Wave 4** *(blocked on Wave 3 completion)*

- [ ] 05.1-04-PLAN.md — Report every `vicmap_audit` read failure as `db_audit_read_failed`, pre-check the marker grant, and pin `pub_promotion_failed` to the promotion transaction.

**Wave 5** *(blocked on Wave 4 completion)*

- [ ] 05.1-05-PLAN.md — Operator re-provisions the marker table, verify live grants and the full live suite, probe the legacy table read-only, and mark WINDOWS.md #16 fixed.
