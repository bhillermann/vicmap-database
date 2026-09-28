# Phase 5: Approved Legacy Cleanup — Close-out

**Status:** Complete — satisfied by manual cleanup
**Closed:** 2026-09-28
**Decision by:** bhillermann@vegetationlink.com.au (interactive, `/gsd-discuss-phase 5`)

## Outcome

Phase 5 delivers a tool to inventory and selectively delete abandoned WFS-attempt
tables (CLN-01–CLN-05). The operator had already removed those tables manually
before this phase was planned. A live read-only catalog inspection confirms no
abandoned WFS tables remain, so the phase goal is already achieved and no
inventory/deletion tooling is built.

## Verified database state

Read-only inspection on 2026-09-28 as `vicmap_loader` against the `vicmap`
database (PostgreSQL 17.5, PostGIS 3.5.2, `127.0.0.1:5432`). Every relation
classified by `pg_depend` extension membership:

| Schema | Object | Type | Owner | Origin |
|--------|--------|------|-------|--------|
| public | spatial_ref_sys | table | gisuser | `postgis` extension — required system object |
| public | geometry_columns | view | gisuser | `postgis` extension — required system object |
| public | geography_columns | view | gisuser | `postgis` extension — required system object |
| vicmap | vmadd_address | table | vicmap_loader | This project — Phase 4 published output (~4.22M rows) |
| vicmap_audit | staging_validation | table | gisuser | This project — Phase 4 validation record |

Schemas `vicmap`, `vicmap_staging` (empty), and `vicmap_audit` exist as project output.

**Conclusion:** The only objects not created by this project are the three
PostGIS extension objects, which are required infrastructure, not WFS leftovers.
No abandoned WFS-attempt table exists. The two remaining `vicmap*` tables are
legitimate pipeline output that CLN-05 requires be left unchanged. They were
retained by explicit operator choice; dropping them is outside Phase 5 scope.

## Requirement disposition

| Requirement | Disposition |
|-------------|-------------|
| CLN-01 read-only WFS inventory | Satisfied — catalog inspection shows no WFS tables; no standing inventory tool needed |
| CLN-02 exact-name approval list | Satisfied vacuously — no deletion targets exist |
| CLN-03 revalidated dry run | Satisfied vacuously — no deletion targets exist |
| CLN-04 exact-target drop, no wildcard/CASCADE | Satisfied vacuously — no deletion performed by the pipeline |
| CLN-05 legitimate/unapproved tables unchanged | Satisfied — legitimate `vicmap*` and PostGIS system objects untouched |

## Deferred

- A reusable approval-gated cleanup tool (CLN-01–CLN-05 as code) remains
  available as future operational tooling if a later delivery reintroduces
  legacy tables. Not built for v0.1 because there is nothing to clean.

---
*Phase: 05-approved-legacy-cleanup*
*Closed: 2026-09-28 — manual cleanup, verified live*
