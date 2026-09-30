# Roadmap: Vicmap Database

## Milestones

- ✅ **v0.1 End-to-End Vicmap Import Proof** — Phases 1–5, 05.1 (shipped 2026-09-30) — [archive](milestones/v0.1-ROADMAP.md)

## Phases

<details>
<summary>✅ v0.1 End-to-End Vicmap Import Proof (Phases 1–5, 05.1) — SHIPPED 2026-09-30</summary>

- [x] Phase 1: Trusted Graph Acquisition (14/14 plans) — completed 2026-09-23
- [x] Phase 2: Safe Geospatial Discovery (9/9 plans) — completed 2026-09-17
- [x] Phase 3: Validated PostGIS Staging (6/6 plans) — completed 2026-09-22
- [x] Phase 4: Transactional Publication and Access (6/6 plans) — completed 2026-09-25
- [x] Phase 5: Approved Legacy Cleanup (0/0 plans, satisfied by manual cleanup) — completed 2026-09-28
- [x] Phase 05.1: Address tech debt: publish resume path (#16) (INSERTED, 5/5 plans) — completed 2026-09-29

</details>

## Backlog

### Phase 999.1: Force ICSM grid selection for GDA94↔GDA2020 transforms (BACKLOG)

**Goal:** Staging transforms between GDA2020 and GDA94 Vicgrid use the vendored ICSM conformal+distortion grid (`+proj=hgridshift au_icsm_GDA94_GDA2020_conformal_and_distortion.tif`) rather than the grid-free Helmert 7-parameter transform.
**Source:** WINDOWS.md #2 and #7 (Phase 03, open). The two items are one defect: #2 recorded that the grid is not picked, and #7 confirmed why.
**Evidence:** With `ONLY_BEST=YES ALLOW_BALLPARK=NO`, ogr2ogr picks the Helmert transform because PROJ's accuracy metadata rates it at 0.01 m and the grid at 0.05 m. On a real ADDRESS point the two results differ by about 2 mm. See 03-01-SUMMARY.md Deviations item 3 and 03-06-SUMMARY.md.
**Open question:** Do consumers need grid-accurate coordinates? If they don't, close as accepted.
**Candidate fix:** Pass an explicit `-ct` pipeline, or a stricter operation filter, in `vicmap_acquire/staging.py`, and prove grid selection with a live transform of a known point.
**Plans:** 0 plans

Plans:
- [ ] TBD (promote with /gsd-review-backlog when ready)

### Phase 999.2: Provisioning script creates or checks the vicmap database (BACKLOG)

**Goal:** `db/provision_vicmap_loader.sql` works on a fresh server where the `vicmap` database does not exist yet, or fails early with a clear precondition message.
**Source:** WINDOWS.md #4 (Phase 03, open).
**Evidence:** The script's first statement is `CREATE ROLE`, not `CREATE DATABASE`. The operator's first provisioning run failed with `FATAL: database vicmap does not exist`, and a superuser had to run `CREATE DATABASE` by hand. See 03-04-SUMMARY.md.
**Constraint:** `CREATE DATABASE` cannot run inside a transaction block or against the target database itself. A fix probably needs a separate bootstrap step (a psql `\gexec` guard or a separate script) run against `postgres`.
**Plans:** 0 plans

Plans:
- [ ] TBD (promote with /gsd-review-backlog when ready)
