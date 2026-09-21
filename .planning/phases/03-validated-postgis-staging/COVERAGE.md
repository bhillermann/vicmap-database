# API Coverage — Phase 3 (Validated PostGIS Staging)

No external API integration: Phase 3 talks only to a local, operator-provisioned
PostgreSQL/PostGIS server (`[database].host = 127.0.0.1`, port `5432`, D-58) through the
`psycopg` driver and the pinned GDAL `ogr2ogr` CLI — there is no third-party network API, SDK,
or vendor service with a capability surface to enumerate or subtract from.

## Why no matrix applies

A capability matrix exists to make *subtraction* from a vendor's published surface an explicit,
reviewable decision. PostgreSQL and PostGIS are not a vendor surface this phase integrates a
slice of; they are the storage engine the whole project targets, reached over a local socket
with ordinary SQL. There is no enumerable list of endpoints, scopes, or SDK methods for which
`INTEGRATE` / `OPT-OUT` would be a meaningful decision.

| Boundary | Kind | In this phase |
|---|---|---|
| `runs/{order}/{ts}/manifest.json` | Local filesystem read | The frozen Phase 2 → Phase 3 handoff (D-29). Internal object, not a published API. |
| `ogr2ogr -f PostgreSQL` | Local subprocess → local DB | The bulk load path (D-41). A pinned CLI from the flake, not a service. |
| `psycopg` → PostgreSQL/PostGIS on `127.0.0.1:5432` | Local database connection | Identity (DB-01), privilege preflight (DB-02), validation (DB-04), post-load DDL (D-62/63/64). Operator-provisioned, not a vendor service. |
| `cdn.proj.org` | External HTTPS host | **Build time only, and only if the vendored-grid option is chosen** (03-01 Task 2). Fetched once by Nix by pinned SHA-256, never contacted at load time. Explicitly rejected as a *runtime* dependency — see 03-01's decision checkpoint. |
| Microsoft Graph / artifact HTTPS host | External APIs | **Phase 1 only.** Phase 3 never contacts them. |
| Reader-role grants, published `vicmap` tables | — | **Phase 4 only.** Phase 3 writes nothing outside `vicmap_staging`. |

## Related

- Phase 1's real capability matrix: `.planning/phases/01-trusted-graph-acquisition/COVERAGE.md`
  (Microsoft Graph + the artifact HTTPS host).
- Phase 2's declaration: `.planning/phases/02-safe-geospatial-discovery/COVERAGE.md`, which
  already recorded that "PostGIS / PostgreSQL — Phase 3 and 4 only".

---
*Declared: 2026-09-21 during Phase 3 planning*
