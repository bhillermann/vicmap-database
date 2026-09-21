# Phase 3: Validated PostGIS Staging - Research

**Researched:** 2026-09-21
**Domain:** GDAL/OGR subprocess loading into PostgreSQL/PostGIS, privilege preflight, blocking spatial validation
**Confidence:** HIGH (stack and mechanics live-verified against the pinned toolchain this session); MEDIUM on two open items flagged below

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-41:** The loader is `ogr2ogr` invoked as a subprocess, one invocation per layer, with `--config PG_USE_COPY YES`. GDAL runs C++ end to end from geodatabase read to `COPY` buffer with no Python in the per-row path. A `pyogrio` + `psycopg3` `COPY BINARY` loader was considered and rejected: binary `COPY` saves roughly 100 MB of hex encoding across 4.2M point rows, which does not outrun the cost of materializing Arrow batches and re-serializing every row in Python. `gdal` is already a pinned `flake.nix` devShell dependency, so no new tooling is required. — **Reversibility:** costly — the DDL, type mapping, column naming, and index creation are all delegated to GDAL; replacing the loader means reimplementing every one of them in project code.
- **D-42:** Layers load sequentially in the manifest's deterministic order. A failure stops the run at a named layer. Parallel invocation was rejected: concurrent `COPY` into one database competes for I/O and WAL, interleaved stderr defeats per-layer diagnosis, and the proof delivery carries one layer.
- **D-43:** `ogr2ogr` failures surface as an exit code mapped to a typed closed reason code with the target table and a remediation hint, in the Phase 1 and 2 style. The complete unredacted stderr is written to the run directory beside the manifest, and the operator message names that file. Rationale: D-17 through D-20 exist to protect output that *travels* — journald and the failure email PROJECT.md plans. A local diagnostic file does not travel, and the same operating-system user already has filesystem access, so suppressing it there buys nothing.
- **D-44:** The database password never appears on the `ogr2ogr` command line. Command-line arguments are visible to other users via `ps`, and GDAL echoes connection strings in some error messages. With the password supplied out of band, D-43's stderr file contains no secret.
- **D-45:** D-22's strict normalization governs **table names only**. Column names are whatever GDAL's `LAUNDER` produces, which defaults to `YES` and lowercases and launders field names — this is why the operator's existing shapefile imports have only ever needed a lowercase change. The column-level reserved-word, collision, and carve-out hard stops discussed earlier in this session were explicitly dropped. Consequence accepted knowingly: a future delivery with a field named `ORDER`, or two fields laundering to the same name, fails as a raw PostgreSQL error mid-load rather than as a clean stop before it. — **Reversibility:** one-way — column names are the published contract every QGIS project and saved query binds to; changing the rule after Phase 4 publishes requires renaming live columns.
- **D-46:** The geometry column is `geom` and the FID column is `gid`, via `-lco GEOMETRY_NAME=geom -lco FID=gid`. This is the PostGIS house style and costs two flags under D-41. GDAL's defaults (`wkb_geometry`, `ogc_fid`) were rejected as a worse published contract. — **Reversibility:** one-way — same published-contract reasoning as D-45.
- **D-47:** Staging tables live in a dedicated `vicmap_staging` schema, entirely outside `vicmap`. DB-03's no-tables-in-`public` requirement is then satisfied structurally rather than by naming convention, and a reader granted only `vicmap` cannot see half-loaded data even accidentally.
- **D-48:** Staging table names carry D-32's run timestamp — `vicmap_staging.vmadd_address_20260918t041500z`. Two runs over the same order coexist without collision and the name itself says which run produced it. This follows D-32's reasoning that re-runs over an unchanged artifact must stay distinguishable.
- **D-49:** **D-39 is superseded.** `vicmap.toml` carries a configured `target_srid` (initially `7899`) and every layer is reprojected to it with `-t_srs`. Verified during this discussion: when source and target CRS match, `ogr2ogr -t_srs` produces byte-identical coordinates — no transform occurs, so today's delivery is unaffected. The gain is a single-SRID estate: a mixed-CRS delivery (D-24's `gda94_vicgrid` vs `gda2020_vicgrid` case) no longer produces tables in different SRIDs, and no cross-table spatial query needs `ST_Transform`. D-39's "record native CRS" was a deferral, not a finding. Phase 2's hard stop on an unresolvable EPSG stays — it is the transform's required input. — **Reversibility:** one-way — the SRID is baked into every published geometry column and into every downstream project once Phase 4 publishes.
- **D-50:** `proj-data` joins `flake.nix`. Measured during this discussion: `proj-9.8.1/share/proj` contains `proj.db` and 15 other entries and **zero** `.tif` or `.gsb` grid files, so a GDA94 VicGrid to GDA2020 VicGrid transform currently falls back to the grid-free conformal method. That fallback moved a Victorian test point +0.536 m easting and +1.461 m northing, and PROJ issued no warning. ICSM's NTv2 grid adds a distortion component worth up to roughly 0.1–0.3 m in parts of Victoria. **See Common Pitfall 1 below: `proj-data` is not a real nixpkgs attribute at the pinned revision — the mechanism needs to change even though the goal does not.**
- **D-51:** Coordinate transformation fails closed: `OGR_CT_ONLY_BEST=YES` and `OGR_CT_ALLOW_BALLPARK=NO`. PROJ errors at transform time when the best operation's grid is unavailable, instead of silently degrading to a Helmert or ballpark operation. This applies the same fail-closed posture D-26 and D-34 already take, to accuracy rather than to resources. Both options were confirmed present in the installed GDAL 3.13.2.
- **D-52:** GDAL's OGR-to-PostgreSQL type mapping is accepted as-is. `PRECISION` defaults to `YES`, so `String(10)` becomes `varchar(10)` and the widths D-40 captured survive into the table. No `COLUMN_TYPES` overrides — a per-field type mapping is exactly the manual mapping PROJECT.md puts out of scope.
- **D-53:** Validation runs against the **staging table in PostGIS, after reprojection** — not against the source file. It therefore validates what Phase 4 will actually publish, including anything D-49's transform changed.
- **D-54:** Validity is a full `ST_IsValid` scan over every row, and invalid geometries are **repaired with `ST_MakeValid`** rather than blocking the run. The repaired count is reported. Note for the planner: `ADDRESS` is a Point layer and points are valid by definition, so the check is O(1) per row and the cost is the sequential scan; validity becomes genuinely expensive only when a polygon layer arrives.
- **D-55:** A repair that changes the geometry type is a hard stop. `ST_MakeValid` can return a MultiPolygon or GeometryCollection where D-38 declared a Polygon, which a typed geometry column rejects. Ordinary noise is repaired quietly; a structural surprise still reaches the operator. `ST_CollectionExtract` salvage was rejected — it discards geometry silently.
- **D-56:** Three checks block the run when they disagree with the manifest: **row count** must equal D-37's exact feature count (this is the check that catches `ogr2ogr` dropping or duplicating features, and D-37 made the count exact precisely to serve as this baseline); **SRID** must equal the configured `target_srid`; **geometry type** must match D-38's declaration including Z and M dimensionality. **Extent is reported but does not block** — no sanity envelope is configured.
- **D-57:** Two validation profiles, selected by the manifest's existing `spatial` boolean. A spatial layer runs every check. A non-spatial layer (D-35's lookup tables and relationship classes) runs the row-count check only, and the geometry, SRID, and extent checks are recorded as **not applicable** — never as passed. This closes the branch D-35 flagged for this phase without weakening anything for spatial layers, and keeps the audit record Phase 4 composes truthful.
- **D-58:** Non-secret connection fields — host, port, dbname, user, and the two schema names — live in `vicmap.toml` alongside every other policy value. The password comes from 1Password through opnix, exactly as `O365_AUTH_SECRET` already does. This preserves Phase 2's rule that one file is the whole non-secret policy, while the secret stays out of the repository.
- **D-59:** The loader connects as a dedicated `vicmap_loader` role, not a superuser. It owns `vicmap_staging` and `vicmap` and holds exactly the privileges DB-02 preflights. DB-03's no-tables-in-`public` guarantee then holds because the role genuinely cannot write there, not because the code avoids it.
- **D-60:** The operator provisions the role and both schemas once, by hand, from a documented SQL script run as superuser. Phase 3's DB-02 preflight verifies the role, both schemas, and every required privilege, and stops with a closed failure naming what is missing. The pipeline never needs superuser, and provisioning stays a deliberate reviewable act. A versioned migration mechanism was rejected as its own phase.
- **D-61:** DB-01 prints host, port, dbname, connected role, server version, and PostGIS version — all six in clear. Every one is non-secret and already in `vicmap.toml` or trivially discoverable by anyone who can reach the server. Fingerprinting the host was rejected: DB-01 exists so the operator can confirm which database was reached, and a fingerprint defeats exactly that.
- **D-62:** Load with `-lco SPATIAL_INDEX=NONE`, then build the GiST index after validation passes. Building an index once over a populated table beats maintaining it during a 4.2M row `COPY`, and validation's full scans gain nothing from an index. The index exists before Phase 4 promotes.
- **D-63:** Every staging table carries, before promotion: a primary key on `gid` (QGIS needs a unique integer column to load a table as a proper editable layer); a **typed** geometry column with its SRID constraint — `geometry(Point, 7899)` rather than bare `geometry`, which enforces at database level what D-56 asserts and pairs with D-55's type-change hard stop; and `NOT NULL` on the geometry column.
- **D-64:** Secondary btree indexes come from a configured flat `index_columns` allowlist in `vicmap.toml`, initially covering the Vicmap persistent feature identifier. Any staging table containing one of those columns gets the index; a table without them gets nothing and nothing fails. This is the same flat-allowlist shape as `allowed_senders`, `allowed_hosts`, and `supported_formats`. Per-table index mapping was rejected as the manual mapping PROJECT.md puts out of scope.

### Claude's Discretion

- The `-gt` transaction group size, and whether it is fixed or configured in `vicmap.toml`.
- Progress reporting cadence during a multi-minute load, and whether it reuses `evidence.py`'s existing `ProgressEvent`.
- Connection, statement, and lock timeout values for the loader role.
- The exact filename and format of D-43's stderr diagnostic file inside the run directory.
- New `Stage` and `ReasonCode` members in `vicmap_acquire/evidence.py` for preflight, load, and validation failures.
- Module layout — whether the database code lives in `vicmap_acquire/` alongside the existing modules or in a sibling package.
- The exact timestamp spelling appended to staging table names, provided it sorts lexicographically and satisfies D-22's table-name rule.
- Whether the DB-02 privilege preflight uses `has_schema_privilege` / `has_table_privilege` or an explicit probe transaction.
- Whether validation runs inside or outside the load transaction.
- The default retention period for D-65's failed-staging sweep.

### Deferred Ideas (OUT OF SCOPE)

- **Failed-staging retention sweep (D-65).** The operator chose: staging tables are dropped after Phase 4's promotion commits, and staging tables left by a *failed* run are auto-dropped after a configurable number of days set in `vicmap.toml`. The drop-on-promotion half belongs to Phase 4, since only Phase 4 knows promotion succeeded. The age-based sweep is a destructive unattended action and is recorded here for the roadmap rather than built in Phase 3 — Phase 3 creates staging tables and never deletes one.
- **Extent sanity envelope.** A configured Victoria-shaped bounding box that a staging extent must fall inside, catching a transform that lands data offshore. Considered and explicitly not made blocking in D-56; extent is reported only.
- **Auto-pruning old run directories.** Carried forward unchanged from Phase 2's deferred list. Disk grows ~975 MB per run and is pruned manually.
- **Widening the format allowlist.** Carried forward unchanged from Phase 2. Shapefile, GeoPackage, MapInfo TAB, and DXF remain unsupported until a real delivery needs them.
- **Connection pooling.** `CONCERNS.md` recommends it for Phase 3. Not applicable under D-41 — `ogr2ogr` subprocesses manage their own connections, and the validation queries are few and sequential. Revisit only if a Python driver path returns.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| DB-01 | Operator can connect to the configured local PostGIS database on port `5432` and verify its non-secret identity and PostGIS version. | `psycopg` connection + `SELECT version(), PostGIS_Full_Version()` pattern below (Code Examples). Port 5432 reachability and GDAL/PROJ versions independently re-confirmed this session. |
| DB-02 | Operator can verify that the loader has the required transaction, schema, and table privileges before loading. | Common Pitfall 3 (`has_table_privilege` errors on a table that does not exist yet — staging tables are always fresh) drives the recommended explicit-probe-transaction pattern in Code Examples. |
| DB-03 | Operator can load every selected layer into uniquely named staging tables without creating or modifying tables in `public`. | Live-verified GDAL PostgreSQL driver layer-creation options (`SCHEMA`, `GEOMETRY_NAME`, `FID`, `LAUNDER`, `PRECISION`, `SPATIAL_INDEX`) in Standard Stack / Code Examples; D-47's schema-as-boundary approach is structurally enforced by D-59's role grants, researched in Security Domain. |
| DB-04 | Operator can see blocking validation results for row counts, geometry columns, geometry types, SRIDs, validity, and extents. | PostGIS validation query set in Code Examples (`ST_IsValid`, `ST_MakeValid`, `GeometryType`, `ST_SRID`, `ST_Extent`), with `ST_MakeValid`'s documented type-collapse behavior backing D-55's hard stop. |
| DB-05 | A failed load or validation leaves existing production tables unchanged. | Structural guarantee from D-47 (dedicated `vicmap_staging` schema) + D-59 (role cannot write `public`/`vicmap`), not a runtime check — see Architectural Responsibility Map. |
</phase_requirements>

## Summary

Phase 3 adds exactly one new architectural element to a codebase that has so far never touched a database: a PostgreSQL/PostGIS boundary, entered two ways. Bulk loading stays entirely inside GDAL's `ogr2ogr` — a subprocess wrapper, no Python row-by-row work, confirmed against the live GDAL 3.13.2 PostgreSQL driver this session. Everything else that needs to *ask* the database a question before or after that subprocess runs — "does this role have CREATE on this schema," "is this row valid," "what SRID landed" — needs a genuine Python driver for the first time in this project. `psycopg` (3.3.4, confirmed against the flake's pinned `nixpkgs` input) is that driver; it is already referenced, skip-not-fail, in `tests/test_naming.py`'s live-PostgreSQL oracle test, so this phase turns an optional test dependency into a first-class runtime one.

Two findings from this session materially change what CONTEXT.md's decisions can mean in practice. First, `proj-data` — the package D-50 says "joins `flake.nix`" — **does not exist as a nixpkgs attribute** at the pinned revision (`nix eval` confirms `proj`, `proj-datumgrid`, and `proj_7` are the only `proj*` top-level attributes; `proj-datumgrid` builds to a 16 KB `nad2bin` conversion tool, not grid data). D-50's underlying goal — get the ICSM GDA94↔GDA2020 NTv2 grid onto disk so PROJ stops silently ballparking — is still correct and still achievable, just not by that literal package name; see Common Pitfall 1 for the two real mechanisms (vendor the grid via `fetchurl`, or enable PROJ's network grid fetch) with a live-verified pinned URL and SHA-256 for the first option. Second, `has_table_privilege` — one of DB-02's two discretionary preflight mechanisms — **errors rather than returning false when the named table does not exist**, and every staging table is, by design (D-48), one that has never existed before this run. That pushes the preflight decision toward an explicit `CREATE TABLE ... ROLLBACK` probe rather than a declarative privilege check.

**Primary recommendation:** Keep `ogr2ogr` as the sole load path (D-41 stands, confirmed against the live driver), add `psycopg` as the project's first real database driver scoped strictly to preflight and validation queries, fix D-50's grid gap by vendoring `au_icsm_GDA94_GDA2020_conformal_and_distortion.tif` through a pinned `fetchurl` in `flake.nix` rather than a nonexistent `proj-data` package, and implement DB-02 as a rolled-back probe transaction rather than a declarative `has_table_privilege` check.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Connection identity + PostGIS version (DB-01) | Database preflight (Python, `psycopg`) | — | A single read-only `SELECT`; no bulk data path involved. |
| Privilege preflight (DB-02) | Database preflight (Python, `psycopg`) | — | Requires a rolled-back probe transaction (see Common Pitfall 3); `ogr2ogr` has no privilege-inspection mode. |
| Bulk layer load into staging (DB-03) | Subprocess (GDAL `ogr2ogr`, C++) | CLI Orchestrator (Python, invokes + captures exit code/stderr) | D-41 delegates DDL, type mapping, and `COPY` entirely to GDAL; Python's only job is invoking, timing out, and interpreting the exit code. |
| No-mutation-in-`public` guarantee (DB-03, DB-05) | PostgreSQL role/schema grants (`vicmap_loader`, `vicmap_staging`) | — | D-47/D-59 make this a database-enforced structural fact, not application logic — the role genuinely lacks `CREATE` on `public`. |
| Blocking spatial validation (DB-04) | Database preflight (Python, `psycopg`, read/aggregate SQL) | PostGIS staging schema (executes `ST_IsValid`/`ST_MakeValid`/etc. server-side) | Validation queries run server-side for performance (4.2M-row `ST_IsValid` scans); Python only issues the SQL and interprets results, never pulls geometries into the process. |
| Production isolation on failure (DB-05) | PostgreSQL role/schema grants | CLI Orchestrator (never issues a promotion statement) | Structural: Phase 3 code has no code path that writes to `vicmap` or `public` at all — Phase 4 owns promotion. |
| Index/constraint application post-validation (D-62/D-63) | Database preflight (Python, `psycopg`, DDL) | PostGIS staging schema | DDL runs once, after validation passes, against a table already fully populated by the (now-exited) `ogr2ogr` subprocess. |

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `gdal` (CLI: `ogr2ogr`, `ogrinfo`) | 3.13.2 `[VERIFIED: nix eval against flake's pinned nixpkgs input, this session — matches the version already in flake.nix per D-41/D-50]` | Bulk layer load (D-41), all DDL/type mapping/`COPY` | Already pinned in `flake.nix`; the standard OGR/PostgreSQL bridge for exactly this workload (D-41's rejected-alternative analysis already measured the Python-driver path as slower). |
| `psycopg` (psycopg3) | 3.3.4 `[VERIFIED: nix eval --raw against flake.inputs.nixpkgs -> python3Packages.psycopg.version, this session]` | Preflight (DB-01/DB-02) and validation (DB-04) queries; never in the per-row load path | `tests/test_naming.py`'s `PostgresKeywordOracleTest` already imports `psycopg` preferentially (falling back to `psycopg2`) as a skip-not-fail live-DB oracle — this phase is the first to need it as a hard runtime dependency, not just a test one. psycopg3 is the actively developed successor to psycopg2, distributed by nixpkgs' curated `python3Packages` set `[VERIFIED: nix eval, same session]`. |
| `proj` | 9.8.1 `[VERIFIED: nix eval against flake's pinned nixpkgs input, this session — matches D-50's measurement exactly]` | Coordinate transformation backing `-t_srs` | Already pinned; D-49/D-51 depend on its `OGR_CT_ONLY_BEST`/`OGR_CT_ALLOW_BALLPARK` config options, both confirmed present in this exact build. |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `au_icsm_GDA94_GDA2020_conformal_and_distortion.tif` (vendored via `pkgs.fetchurl`, not a package name) | n/a — single grid file, 27,272,664 bytes, SHA-256 `89bb9e5c55a714c8925ddc134bf4c191be8df2607b229a05efb778f5f6166ee0` `[VERIFIED: curl HEAD + full download + sha256sum against https://cdn.proj.org/, this session]` | Closes D-50's actual gap — see Common Pitfall 1 | Add as a `fetchurl` derivation in `flake.nix`, place its output in a directory alongside (or referenced by) `PROJ_DATA`, so `ogr2ogr -t_srs EPSG:7899` can resolve the ICSM NTv2 grid without a network call at load time. |
| `postgresql` (client only, for `psql`) | not currently in `flake.nix` | Lets the operator run D-60's provisioning SQL script by hand | Add if the operator doesn't already have `psql` on the host running `nix develop`; optional, since D-60's script can also be piped through `psycopg` in a one-off script, but `psql` is the conventional tool for a human-run, human-reviewed DDL script. |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `psycopg` (psycopg3) | `psycopg2` | `psycopg2` is legacy-maintenance-mode; `psycopg3` is what the existing test oracle already prefers, and nixpkgs ships a current `python3Packages.psycopg`. No reason to add a second driver. |
| Vendored grid `.tif` via `fetchurl` | `PROJ_NETWORK=ON` (PROJ's built-in on-demand CDN fetch) | Nixpkgs' `proj` derivation lists `curl` as a build input `[VERIFIED: nix eval pkgs.proj.buildInputs, this session]`, so network-mode grid fetching is very likely functional in this build without any flake change. But it makes every load's transform accuracy depend on reaching `cdn.proj.org` at runtime — a new, unreviewed outbound host outside `vicmap.toml`'s `[download].allowed_hosts` allowlist, and a new failure mode (D-51's fail-closed posture would then fail closed on *network* unavailability, not just missing local data, which is a different risk profile than the rest of this project's fully-pinned, no-incidental-network-calls posture). Vendoring keeps the whole pipeline usable offline once `nix develop` has fetched build inputs once, consistent with how `flake.nix` already vendors `python-o365` via `fetchFromGitHub`. |
| Declarative `has_schema_privilege`/`has_table_privilege` preflight | Explicit `BEGIN; CREATE TABLE ...; ROLLBACK;` probe transaction | See Common Pitfall 3 — `has_table_privilege` errors on a nonexistent table, and every staging table is by design nonexistent before this run creates it. The probe transaction also catches quota/tablespace-level failures a declarative check cannot see, and rolls back cleanly, so it never leaves stray state (compatible with DB-05). |

**Installation:** (all via `flake.nix`, not `pip`/`npm` — this project has no PyPI installation path; nixpkgs is the only registry)

```nix
# In flake.nix's perSystem, alongside the existing gdal entry:
packages = with pkgs; [
  git
  buildOpnix
  gdal
  (python3.withPackages (ps: [
    python-o365
    ps.html5lib
    ps.pyogrio
    ps.pyproj
    ps.psycopg   # new: Phase 3's preflight/validation driver
  ]))
  # postgresql  # optional: adds `psql` for D-60's manual provisioning script
];
```

**Version verification:** Ran directly against the flake's own pinned `nixpkgs` input via `nix eval --impure --raw --expr 'let flake = builtins.getFlake (toString ./.); pkgs = import flake.inputs.nixpkgs { system = "x86_64-linux"; }; in pkgs.<attr>.version'` this session (mirrors 02-RESEARCH.md's precedent — `pip`/`pip3` are not installed in this environment; the project's only installation path is Nix). `gdal` (3.13.2) and `proj` (9.8.1) both independently reproduce CONTEXT.md's D-50 measurements exactly, corroborating that session's live findings rather than merely repeating them.

## Package Legitimacy Audit

| Package | Registry | Age | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|-----|-----------|--------------|---------|-------------|
| `psycopg` | PyPI (installed via nixpkgs `python3Packages.psycopg`) | seam reports `publishedAt: 2026-09-18` (a very recent point release) | seam reports `null`/unknown | seam returned `https://psycopg.org/` (not the GitHub URL) | `SUS` (`too-new`, `unknown-downloads`) `[VERIFIED: gsd_run query package-legitimacy check --ecosystem pypi psycopg, this session]` | Flagged — planner must add a `checkpoint:human-verify` task before this is added to `flake.nix`, per protocol. |

**Packages removed due to `[SLOP]` verdict:** none.
**Packages flagged as suspicious `[SUS]`:** `psycopg` — the planner **must** add a `checkpoint:human-verify` task before adding it to `flake.nix`.

**Mitigating context the planner should weigh at that checkpoint (not a substitute for it):** This is the same shape of false positive 02-RESEARCH.md already documented for `pyogrio`/`pyproj` — the seam's `too-new` signal fires on any package's *most recent point release* regardless of the project's actual age, and psycopg3 (the project, not this release) has been in production use since 2020 under the `psycopg`/`psycopg2` GitHub organization. `nixpkgs`'s own curated `python3Packages.psycopg` derivation independently confirms it as a real, buildable package at version 3.3.4 `[VERIFIED: nix eval, this session]`, and `tests/test_naming.py`'s existing `PostgresKeywordOracleTest` already imports it as a preferred optional driver — meaning this exact package name has already survived at least implicit review as a test-only dependency. None of this overrides the protocol: it is still `[ASSUMED]`/`SUS` until the operator's `checkpoint:human-verify` closes it.

## Architecture Patterns

### System Architecture Diagram

```
                     vicmap.toml [database] section
                     (host, port, dbname, user, staging_schema,
                      publish_schema, target_srid, index_columns)
                                    |
                                    v
   ImportManifest (Phase 2, frozen) --> run_staging(manifest, config, credentials)
                                    |
             +----------------------+----------------------+
             |                                              |
             v                                              v
   [1] DB-01/DB-02 preflight                    [3] DB-04 validation (per layer,
       (psycopg, short-lived connection)             after its ogr2ogr call exits 0)
             |                                              ^
             | identity + privilege probe                   |
             | (BEGIN; CREATE TABLE probe; ROLLBACK;)        | psycopg: ST_IsValid,
             v                                               | ST_MakeValid, GeometryType,
   PASS/FAIL --> SafeFailure(Stage.DB_PREFLIGHT, ...)         | ST_SRID, ST_Extent, COUNT(*)
             |                                              |
             | (only on PASS)                               |
             v                                              |
   [2] DB-03 load: for each ManifestLayer, in manifest order:
             |
             +--> subprocess: ogr2ogr -f PostgreSQL PG:"host=... dbname=..."
             |       (PGPASSWORD in subprocess env, never in argv)
             |       -lco SCHEMA=vicmap_staging -lco GEOMETRY_NAME=geom -lco FID=gid
             |       -lco SPATIAL_INDEX=NONE -nln <run-timestamped table name>
             |       -t_srs EPSG:<target_srid>
             |       --config PG_USE_COPY YES
             |       --config OGR_CT_ONLY_BEST YES --config OGR_CT_ALLOW_BALLPARK NO
             |       <source dataset> <layer name>
             |
             |   exit 0 --> table exists in vicmap_staging, unindexed, untyped geometry column
             |   exit 1 --> stderr captured to runs/<run>/db_load_<table>.stderr,
             |              SafeFailure(Stage.DB_LOAD, target_table=<fingerprint or table>, ...)
             |              (all subsequent layers skipped -- D-42)
             v
   [3] DB-04 validation runs against that one table (loop back to top)
             |
             | on PASS (all blocking checks agree with the manifest)
             v
   [4] Post-validation DDL (psycopg): ALTER geometry column to typed geometry(<Type>,<SRID>)
       NOT NULL, ADD PRIMARY KEY (gid), CREATE INDEX ... USING GIST (geom),
       CREATE INDEX for any index_columns hit
             |
             v
   Staging table ready for Phase 4 promotion -- vicmap/public never touched (D-05)
```

### Recommended Project Structure

```
vicmap_acquire/
├── evidence.py        # extended: new Stage/ReasonCode members for preflight/load/validation
├── manifest.py         # unchanged -- Phase 3's frozen input
├── naming.py           # unchanged -- still authoritative for the table-name segment
├── staging.py          # NEW: DB-01/DB-02 preflight, ogr2ogr invocation, DB-04 validation, post-load DDL
└── ...
db/
└── provision_vicmap_loader.sql   # NEW (D-60): documented, operator-run-by-hand superuser script
```

`staging.py` is the natural single new module: it owns the one new external dependency (`psycopg`), the one new subprocess pattern (`ogr2ogr`), and the one new typed-failure vocabulary this phase introduces. This mirrors `discovery.py`'s shape (a `Policy` dataclass, pure functions raising a small closed exception hierarchy, one orchestration entry point) rather than introducing a second package.

### Pattern 1: `ogr2ogr` invocation as a total, closed subprocess call

**What:** Build the full argument list from the frozen `ManifestLayer` + a `StagingPolicy` dataclass, run via `subprocess.run` with `capture_output=True`, a timeout, and an injected `env` carrying `PGPASSWORD` (never the base `os.environ` alone — D-44).
**When to use:** Every DB-03 load, one call per layer, in manifest order (D-42).
**Example:**
```python
# Source: live-verified against ogrinfo --format PostgreSQL, GDAL 3.13.2, this session
import subprocess

def _build_ogr2ogr_command(
    *, dataset_path, layer_name, table_name, staging_schema, target_srid, gt
) -> list[str]:
    return [
        "ogr2ogr",
        "-f", "PostgreSQL",
        f"PG:dbname={dbname} host={host} port={port} user={user}",  # no password
        str(dataset_path), layer_name,
        "-nln", table_name,
        "-lco", f"SCHEMA={staging_schema}",
        "-lco", "GEOMETRY_NAME=geom",
        "-lco", "FID=gid",
        "-lco", "SPATIAL_INDEX=NONE",     # D-62: index built post-validation
        "-lco", "LAUNDER=YES",            # explicit; also the live-verified default
        "-lco", "PRECISION=YES",          # explicit; also the live-verified default
        "-t_srs", f"EPSG:{target_srid}",
        "--config", "PG_USE_COPY", "YES",
        "--config", "OGR_CT_ONLY_BEST", "YES",
        "--config", "OGR_CT_ALLOW_BALLPARK", "NO",
        "-gt", str(gt),
    ]

def _run_ogr2ogr(command: list[str], *, password: str, timeout_seconds: int):
    env = {**os.environ, "PGPASSWORD": password}  # D-44: never in argv
    result = subprocess.run(
        command, capture_output=True, text=True, timeout=timeout_seconds, env=env
    )
    return result  # result.returncode: 0 success, 1 failure (live-verified, this session)
```
Note `-nln` is deliberately the bare table name (no schema dot) — `naming.py`'s `normalize_target_table_name` only ever validates a table-name segment, and GDAL's `EXTRACT_SCHEMA_FROM_LAYER_NAME` option (default `YES`) would otherwise try to split a dotted `-nln` value itself; using `-lco SCHEMA=` for schema placement keeps the two concerns (D-22 normalization vs. D-47 schema boundary) cleanly separated, matching how `naming.py` is scoped today.

### Pattern 2: Privilege preflight as a rolled-back probe transaction (DB-02)

**What:** Rather than a declarative `has_schema_privilege`/`has_table_privilege` check, open one connection as `vicmap_loader`, `BEGIN`, attempt the exact DDL the load path will need (`CREATE TABLE` in `vicmap_staging`, `CREATE TABLE` in `vicmap` for reference — Phase 4's own preflight would separately confirm the latter, but DB-02 as scoped to this phase only needs `vicmap_staging`), then unconditionally `ROLLBACK`.
**When to use:** DB-02, before any `ogr2ogr` subprocess is spawned.
**Example:**
```python
# Source: psycopg3 docs (transaction context manager); has_table_privilege
# behavior confirmed via PostgreSQL mailing-list documentation this session --
# see Common Pitfall 3 for why the declarative check does not fit here.
import psycopg
from psycopg import sql

def preflight_staging_privileges(conn_kwargs: dict, *, staging_schema: str) -> None:
    with psycopg.connect(**conn_kwargs, autocommit=False) as conn:
        with conn.cursor() as cur, conn.transaction():
            probe_table = sql.Identifier(staging_schema, "__db02_privilege_probe")
            try:
                cur.execute(
                    sql.SQL(
                        "CREATE TABLE {} (gid integer PRIMARY KEY, "
                        "geom geometry(Point, 4326) NOT NULL)"
                    ).format(probe_table)
                )
                cur.execute(
                    sql.SQL("CREATE INDEX ON {} USING GIST (geom)").format(probe_table)
                )
            finally:
                conn.rollback()  # DB-05: never commits, leaves nothing behind
```
The `sql.Identifier`/`sql.SQL` composition (not an f-string) is load-bearing: staging table names are derived from GDAL layer names by way of `naming.py`'s normalization, but the *schema* name and any future dynamically-referenced identifiers should never be string-formatted directly into SQL text — see Security Domain.

### Pattern 3: Blocking validation query set (DB-04)

**What:** One `psycopg` connection per layer (or reused across layers), issuing the exact checks D-56/D-57 require.
**When to use:** Immediately after each layer's `ogr2ogr` call exits 0.
**Example:**
```python
# Source: PostGIS docs (postgis.net/docs/ST_MakeValid.html, ST_IsValid.html,
# reference.html#Geometry_Accessors) -- standard, stable PostGIS API.
VALIDATE_SPATIAL_LAYER_SQL = """
WITH invalid AS (
    SELECT gid, ST_MakeValid(geom) AS repaired
    FROM {table}
    WHERE NOT ST_IsValid(geom)
)
SELECT
    (SELECT COUNT(*) FROM {table}) AS row_count,
    (SELECT COUNT(*) FROM invalid) AS repaired_count,
    (SELECT COUNT(*) FROM invalid
        WHERE GeometryType(repaired) <> GeometryType(geom)) AS type_changed_count,
    (SELECT DISTINCT ST_SRID(geom) FROM {table} LIMIT 2) AS srids_seen,
    (SELECT DISTINCT GeometryType(geom) FROM {table} LIMIT 2) AS geometry_types_seen,
    ST_Extent(geom) AS extent
FROM {table};
"""
# type_changed_count > 0 is D-55's hard stop; only apply UPDATE ... SET geom =
# ST_MakeValid(geom) after confirming type_changed_count = 0.
```
For a non-spatial layer (D-57), the equivalent is just `SELECT COUNT(*) FROM {table}` — no `ST_*` calls at all, and the manifest record stores `not_applicable` for the geometry/SRID/extent fields.

### Anti-Patterns to Avoid

- **String-formatting table/schema names into SQL:** Every identifier this phase touches ultimately derives from GDAL/manifest data. Use `psycopg.sql.Identifier`, never `f"SELECT * FROM {table}"`.
- **Reading GDAL's `-progress` terminal output as structured progress:** `-progress` (confirmed via `ogr2ogr --long-usage`, this session) draws a plain terminal progress bar and "only works if input layers have the 'fast feature count' capability" — it is not machine-parseable JSON and should not be scraped. See Common Pitfall 4 for the recommended alternative.
- **Trying to distinguish `ogr2ogr` failure sub-types from its exit code:** confirmed this session that `ogr2ogr` exits `1` uniformly on failure (unreachable database, unreadable source, DDL conflict — all `1`). Don't build a reason-code table keyed on exit code; the existing codebase convention (map to one fixed reason code, no interpolation, point at the local stderr file) already fits this.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| GDAL type → PostgreSQL column type mapping | A per-OGR-type-to-PG-type dictionary | GDAL's built-in mapping (D-52 already locks this) | PROJECT.md puts manual field mapping out of scope; GDAL's mapping is exactly what every existing shapefile import already relies on implicitly. |
| Geometry repair | Hand-written polygon-fixing (buffer-by-zero, etc.) | `ST_MakeValid` (D-54) | PostGIS's own repair function, with documented, well-understood collapse behavior (Architecture Pattern 3) — a hand-rolled buffer(0) trick has known failure modes GEOS's dedicated function avoids. |
| Privilege introspection | Parsing `\dp`/`pg_catalog` output manually | `psycopg` + a probe transaction (Pattern 2) or `has_schema_privilege` | PostgreSQL's own system information functions exist precisely for this; a probe transaction additionally proves capability, not just catalog metadata. |
| Password redaction from subprocess argv | Post-hoc scrubbing of a captured command line before logging | Never put the password in argv at all (D-44) — pass via subprocess `env` | Scrubbing after the fact is a race against every code path that might log/echo `command` before the scrub runs; not putting it there is strictly safer and is what D-44 already decided. |

**Key insight:** This phase's genuinely custom code is thin by design — GDAL owns the load, PostGIS owns validation math, PostgreSQL's own grant system owns the isolation guarantee (DB-05). The Python this phase adds is glue: build a command list, run it, check an exit code, run some SQL, interpret booleans. Resisting the urge to reimplement any of GDAL's or PostGIS's work in Python is the single highest-leverage thing the plan can do.

## Common Pitfalls

### Pitfall 1: `proj-data` is not a real nixpkgs attribute at the pinned revision — D-50 needs a different mechanism

**What goes wrong:** A plan or executor takes D-50's literal wording ("`proj-data` joins `flake.nix`") and tries `pkgs.proj-data` in the `perSystem.packages` list; the flake fails to evaluate.
**Why it happens:** `proj-data` is the name of the *upstream* GitHub project (`OSGeo/PROJ-data`) that publishes the grid files, not a nixpkgs package name `[VERIFIED: nix eval — filtering all of nixpkgs' top-level attribute names for anything matching "proj" returns only proj, proj-datumgrid, proj_7, and several unrelated "-project-" matches; no proj-data, this session]`. The similarly-named `proj-datumgrid` **does** exist, but it builds to a 16.5 KiB output containing only a `nad2bin` grid-format conversion binary, not the grid data itself `[VERIFIED: nix build + find on the resulting store path, this session]`.
**How to avoid:** Two real mechanisms exist (see Alternatives Considered table above for the tradeoff):
  1. **Vendor the specific grid file.** Add a `fetchurl` derivation for `https://cdn.proj.org/au_icsm_GDA94_GDA2020_conformal_and_distortion.tif` (27,272,664 bytes, SHA-256 `89bb9e5c55a714c8925ddc134bf4c191be8df2607b229a05efb778f5f6166ee0`, both `[VERIFIED: curl + sha256sum against the live CDN, this session]`), and point `PROJ_DATA` (PROJ ≥ 9's env var; `PROJ_LIB` is the pre-9 name) at a directory containing both `proj.db` (from the existing `proj` package) and this `.tif`, or set `PROJ_DATA` to a colon-joined list of both directories if PROJ's build supports multiple search paths in this version — verify at plan time.
  2. **Enable PROJ's on-demand network grid fetch** (`PROJ_NETWORK=ON`). The pinned `proj` derivation lists `curl` in its build inputs `[VERIFIED: nix eval, this session]`, which is the standard signal PROJ's CMake build auto-enables `ENABLE_CURL`/network-mode grid access — this was not independently proven to work end-to-end this session (that would require a live transform test with the flag set) and should be spot-checked before the planner picks it. This mechanism introduces `cdn.proj.org` as a new outbound host every load implicitly depends on, outside `vicmap.toml`'s own reviewed `[download].allowed_hosts`.
**Warning signs:** `nix flake check`/`nix develop` failing to evaluate with an "attribute 'proj-data' missing" error, or (if the executor instead just leaves the grid gap unfixed) D-51's `OGR_CT_ONLY_BEST=YES` correctly hard-stopping every load that needs the GDA94→GDA2020 transform, which will look like a total, immediate blocker on the very first live run against a mixed-CRS delivery.

### Pitfall 2: GDAL's PostgreSQL driver may already produce a typed geometry column, making D-63's ALTER redundant or actively harmful

**What goes wrong:** The plan writes an unconditional `ALTER TABLE ... ALTER COLUMN geom TYPE geometry(Point, 7899)` post-load DDL step, but GDAL's PG driver (confirmed via `ogrinfo --format PostgreSQL`, this session: `GEOM_TYPE` layer creation option defaults to `geometry`, not `geography`, and the driver is capable of creating typed geometry columns when a single OGR geometry type is known for the layer) may have already created `geom` as `geometry(Point,7899)` directly, since the source layer's geometry type and the `-t_srs` target SRID are both known before any feature is written.
**Why it happens:** GDAL's exact typed-vs-generic-`geometry` column decision depends on driver internals not fully exercised by the live `ogrinfo --format PostgreSQL` dump (which lists available options, not runtime behavior for a specific load). This needs a one-time empirical check against a real load (e.g. `\d vicmap_staging.<table>` after one real `ogr2ogr` run) before the plan hard-codes an unconditional `ALTER ... TYPE`.
**How to avoid:** Make the post-load DDL idempotent/conditional: check the column's actual type via `information_schema.columns`/`geometry_columns` before attempting to `ALTER` it, or use `ALTER COLUMN ... TYPE geometry(...) USING geom` unconditionally (a no-op cast when the type already matches, per PostgreSQL's `ALTER TYPE` semantics) rather than assuming it is always necessary.
**Warning signs:** An `ALTER TABLE` that fails or behaves unexpectedly against a table that turns out to already have exactly the target typed column.

### Pitfall 3: `has_table_privilege` errors on a table that does not exist yet — every staging table always doesn't

**What goes wrong:** A DB-02 preflight implemented as `SELECT has_table_privilege('vicmap_loader', 'vicmap_staging.vmadd_address_<ts>', 'INSERT')` raises a PostgreSQL error ("relation ... does not exist"), not `false`, because that exact table has never existed before — D-48 guarantees a fresh, run-timestamped name every time.
**Why it happens:** `has_table_privilege` (and, per some server versions/scenarios, `has_schema_privilege` combined with schema-qualified names) is documented to raise rather than return a boolean when the named relation doesn't exist `[CITED: PostgreSQL mailing list discussion of has_table_privilege error semantics for nonexistent tables, corroborated by pgPedia's documentation of the function, this session's WebSearch]`.
**How to avoid:** Check `CREATE` privilege at the *schema* level with `has_schema_privilege('vicmap_loader', 'vicmap_staging', 'CREATE')` (valid pre-creation, since the schema does exist), and/or use the explicit rolled-back probe transaction in Architecture Pattern 2, which proves the actual `CREATE TABLE` + `CREATE INDEX` capability the load path will exercise rather than inferring it from grant metadata.
**Warning signs:** DB-02 preflight throwing an unhandled `psycopg` error (relation does not exist) instead of returning a clean pass/fail on the very first run against a schema that has never held that table name.

### Pitfall 4: `ogr2ogr -progress` is a terminal bar, not a source of structured `ProgressEvent`s

**What goes wrong:** An attempt to reuse `evidence.py`'s `ProgressEvent` machinery for D-03's multi-minute load by parsing `-progress`'s stdout output produces fragile, version-dependent scraping code (progress bars are typically carriage-return-updated ASCII, not line-delimited JSON).
**Why it happens:** `-progress` (confirmed via `ogr2ogr --long-usage`, this session) exists purely for interactive terminal use and explicitly depends on the input layer supporting "fast feature count" — a capability, not a guaranteed structured data stream.
**How to avoid:** Don't parse `-progress` output. If progress reporting is wanted for this phase (it's Claude's Discretion per CONTEXT.md), the two realistic options are: (a) per-layer granularity only — emit a `ProgressEvent`-shaped "layer N of M started"/"layer N of M completed" pair around each `ogr2ogr` subprocess call (cheap, matches D-42's one-layer-at-a-time model, no parsing needed), or (b) a wall-clock heartbeat emitted by the calling Python code while `subprocess.run`/`Popen` blocks (no real byte/row count available, just liveness).
**Warning signs:** Regex-based scraping of subprocess stdout for percentage values; test flakiness tied to terminal width or GDAL version bumping its progress bar format.

## Code Examples

### `vicmap.toml` `[database]` section shape

```toml
# Source: mirrors the existing [mailbox]/[download]/[extraction]/[discovery]
# complete-key-set, fail-closed pattern in read_mailbox.py -- new section,
# same shape.
[database]
host = "127.0.0.1"
port = 5432
dbname = "vicmap"
user = "vicmap_loader"
staging_schema = "vicmap_staging"
publish_schema = "vicmap"
target_srid = 7899
index_columns = ["pfi"]   # D-64's flat allowlist, one-entry start
gt = 20000                 # Claude's discretion: -gt transaction group size
connect_timeout_seconds = 10
statement_timeout_seconds = 3600
lock_timeout_seconds = 30
```
The password is deliberately absent from this table (D-58) — it comes from opnix/1Password at runtime, the same way `O365_AUTH_SECRET` already does in `flake.nix`'s `opnixEnvConfig`.

### D-60 provisioning script skeleton (operator-run, superuser, not executed by the pipeline)

```sql
-- db/provision_vicmap_loader.sql
-- Run once, by hand, as a PostgreSQL superuser. Not invoked by any Phase 3 code path.
CREATE ROLE vicmap_loader LOGIN PASSWORD '<set via 1Password, not committed>';
CREATE SCHEMA IF NOT EXISTS vicmap_staging AUTHORIZATION vicmap_loader;
CREATE SCHEMA IF NOT EXISTS vicmap AUTHORIZATION vicmap_loader;
-- No GRANT ... ON SCHEMA public -- vicmap_loader must never be able to write there (D-59/DB-05).
```

### PostGIS identity/version query (DB-01)

```python
# Source: standard PostGIS/PostgreSQL introspection, stable across versions.
with psycopg.connect(**conn_kwargs) as conn:
    with conn.cursor() as cur:
        cur.execute("SELECT current_database(), current_user, version()")
        dbname, role, server_version = cur.fetchone()
        cur.execute("SELECT PostGIS_Full_Version()")
        (postgis_version,) = cur.fetchone()
# host/port are already known from config (D-61 prints all six non-secret fields).
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|---------------|--------|
| `psycopg2` as the default Python PostgreSQL driver | `psycopg` (psycopg3) | psycopg3 first released 2020, now the actively developed line | This project's own test suite already prefers `psycopg` over `psycopg2` (`tests/test_naming.py`), so this phase should follow that existing preference rather than introducing a second driver. |
| PROJ grid files bundled in the main `proj` source tarball (PROJ < 7) | Grid files split into a separate `PROJ-data` distribution, fetched via `projsync` or PROJ's network mode | PROJ 7 (2020) | Directly explains why the pinned `proj` 9.8.1 build has zero `.tif`/`.gsb` files out of the box (D-50's own measurement) — this is expected PROJ ≥ 7 behavior, not a packaging defect, and nixpkgs simply hasn't re-packaged the grid data under an easily discoverable attribute name. |

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `psycopg` 3.3.4's package-legitimacy `[SUS]` verdict is a metadata-lookup artifact (recency heuristic), not a genuine supply-chain risk | Package Legitimacy Audit | If wrong, a compromised package could be added to `flake.nix`; mitigated by the required `checkpoint:human-verify` gate regardless. |
| A2 | GDAL's PostgreSQL driver may already create a typed `geometry(Type,SRID)` column without needing D-63's `ALTER`, given known geometry type + `-t_srs` | Common Pitfall 2 | If wrong in the other direction (driver never types it), an assumed-idempotent-no-op `ALTER` still runs correctly; if wrong in the direction of the ALTER actively failing against an already-typed column with different internal representation, the plan needs the conditional check described. Low risk either way if the DDL is written idempotently as recommended. |
| A3 | `PROJ_NETWORK=ON` would function against the pinned `proj` 9.8.1 build (curl is a build input) | Common Pitfall 1 / Alternatives Considered | Not independently tested end-to-end this session (would require a live network transform test). If wrong, this alternative to vendoring the grid file is unavailable and vendoring becomes the only option — no impact on the recommended path, since vendoring is already the primary recommendation. |
| A4 | The `-gt` transaction-group-size default GDAL uses without the flag is suitable, or 20000 is a reasonable starting value for a 4.2M-row load | `vicmap.toml` example | Purely a performance tuning value (Claude's Discretion per CONTEXT.md) — wrong value affects load speed and WAL pressure, not correctness. |
| A5 | PROJ's `PROJ_DATA` env var (not `PROJ_LIB`) is the correct variable name for PROJ 9.8.1, and it accepts a directory that must contain `proj.db` alongside any vendored grid `.tif` | Common Pitfall 1 | PROJ renamed `PROJ_LIB` to `PROJ_DATA` in PROJ 9.1; 9.8.1 postdates that rename, but the exact multi-path search behavior for this specific build was not tested this session (only the base `proj-9.8.1/share/proj` directory's contents were inspected, per D-50). If wrong, the flake's `PROJ_DATA` wiring needs a symlink-merge step instead of a colon-joined path list. |

**If this table is empty:** N/A — see rows above.

## Open Questions

1. **Does GDAL's PostgreSQL driver create a typed geometry column automatically when the OGR layer has a single known geometry type and `-t_srs` is set, or does it always create a bare `geometry` column requiring D-63's `ALTER`?**
   - What we know: `GEOM_TYPE` layer creation option defaults to `geometry` (not `geography`); the driver is documented as capable of typed columns.
   - What's unclear: whether "capable of" means "does by default for a known single-type layer" in this exact GDAL 3.13.2 build, without a live load test against the real database.
   - Recommendation: the plan should include a one-time empirical check (`\d vicmap_staging.<table>` or `information_schema.columns` after a real `ADDRESS` load) as an early task, and write the post-load DDL idempotently regardless of the answer (Common Pitfall 2).

2. **Does `PROJ_DATA` in this PROJ 9.8.1 build accept a colon-separated list of directories, or must vendored grid files live alongside `proj.db` in one directory?**
   - What we know: PROJ 9+ uses `PROJ_DATA` (not the pre-9.1 `PROJ_LIB`); the base package's `share/proj` holds `proj.db` and 15 other entries with no grids (D-50).
   - What's unclear: the exact multi-path search semantics for this build; whether `flake.nix`'s `shellHook` needs to symlink-merge the vendored `.tif` into a writable location instead.
   - Recommendation: verify with a throwaway `nix develop` shell setting `PROJ_DATA` to a `:`-joined path (or single merged directory) and running a real GDA94→GDA2020 transform, before finalizing the flake.nix change.

3. **Is `PROJ_NETWORK=ON` actually functional in the pinned `proj` build (does its `curl` build input imply working network grid fetch), and if so, is it disqualified purely on policy grounds (new unreviewed outbound host) or also on reliability grounds?**
   - What we know: `curl` is a build input (this session, `nix eval`).
   - What's unclear: whether `ENABLE_CURL`/network mode was actually compiled in and enabled by default, without an end-to-end live test.
   - Recommendation: not needed for the plan if vendoring (this research's primary recommendation) is adopted; only relevant if the planner or operator prefers the network-fetch mechanism instead.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| `ogr2ogr`/`ogrinfo` (GDAL) | DB-03 load, oracle cross-checks | ✓ `[VERIFIED: which ogr2ogr ogrinfo, this session]` | 3.13.2 | — |
| `proj` (PROJ) | D-49/D-51 reprojection | ✓ `[VERIFIED: nix eval, this session]` | 9.8.1 | — |
| GDA94↔GDA2020 NTv2 grid data | D-50/D-51 accurate reprojection | ✗ — zero `.tif`/`.gsb` files in the base `proj` package `[VERIFIED: D-50's own measurement, corroborated by this session's `nix build`/`find` of `proj-datumgrid`]` | — | Vendor `au_icsm_GDA94_GDA2020_conformal_and_distortion.tif` via `fetchurl` (Common Pitfall 1), or enable `PROJ_NETWORK=ON` (unverified end-to-end this session). |
| PostgreSQL server on port 5432 | DB-01 connection | ✓ `[VERIFIED: /dev/tcp probe, this session — independently reproduces CONTEXT.md's D-58/"specifics" claim]` | not queried (requires a connection, not just a port probe) | — |
| `psycopg` (Python driver) | DB-01/DB-02/DB-04 | ✗ — not yet in `flake.nix`'s Python package list (only referenced optionally by a test) | would be 3.3.4 once added `[VERIFIED: nix eval, this session]` | None needed — this is the one new dependency this phase must add. |
| `psql` (PostgreSQL client CLI) | D-60's manual provisioning script | ✗ — not in `flake.nix` | — | Operator can run the provisioning SQL through any PostgreSQL client they already have, or the flake can add `postgresql` for convenience (optional). |

**Missing dependencies with no fallback:** none — every gap above has a documented fallback or is the phase's own explicit deliverable (adding `psycopg`).

**Missing dependencies with fallback:** GDA94↔GDA2020 grid data (vendor via `fetchurl`, pinned URL/hash already verified above); `psql` client (optional convenience, any PostgreSQL client suffices for a one-off manual script).

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | `unittest` (Python standard library) `[VERIFIED: .planning/codebase/TESTING.md; confirmed by this session's read of tests/test_naming.py's PostgresKeywordOracleTest, which is itself a unittest.TestCase]` |
| Config file | none — direct module execution / `discover` |
| Quick run command | `nix develop path:. -c python -m unittest tests.test_staging -v` (new module, once it exists) |
| Full suite command | `nix develop path:. -c python -m unittest discover -s tests -p 'test_*.py'` `[VERIFIED: 02-VERIFICATION.md's recorded full-suite command, currently 399 tests / 14.676s]` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|--------------------|--------------|
| DB-01 | Connects and reports non-secret identity + PostGIS version | live-DB integration (skip-not-fail) | `nix develop path:. -c python -m unittest tests.test_staging.ConnectionIdentityTest -v` | ❌ Wave 0 |
| DB-02 | Privilege preflight passes for a correctly-provisioned role, fails closed for an under-privileged one | live-DB integration (skip-not-fail) | `nix develop path:. -c python -m unittest tests.test_staging.PrivilegePreflightTest -v` | ❌ Wave 0 |
| DB-03 | Layer loads into a uniquely-named `vicmap_staging` table, never touches `public` | live-DB integration + a mocked-`subprocess` unit test for command construction | `nix develop path:. -c python -m unittest tests.test_staging.LoadCommandConstructionTest tests.test_staging.LoadIntegrationTest -v` | ❌ Wave 0 |
| DB-04 | Blocking validation reports row count/geometry/SRID/validity/extent correctly, including the D-55 type-change hard stop | live-DB integration, ideally against a deliberately-invalid fixture geometry | `nix develop path:. -c python -m unittest tests.test_staging.ValidationTest -v` | ❌ Wave 0 |
| DB-05 | A failed load/validation leaves `vicmap`/`public` provably unchanged | live-DB integration (snapshot row counts in `public`/`vicmap` before and after an induced failure) | `nix develop path:. -c python -m unittest tests.test_staging.ProductionIsolationTest -v` | ❌ Wave 0 |

### Sampling Rate

- **Per task commit:** targeted module run, e.g. `nix develop path:. -c python -m unittest tests.test_staging -v`
- **Per wave merge:** `nix develop path:. -c python -m unittest discover -s tests -p 'test_*.py'`
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps

- [ ] `tests/test_staging.py` — new module covering DB-01 through DB-05, following `tests/test_naming.py`'s `PostgresKeywordOracleTest` skip-not-fail pattern (`VICMAP_TEST_POSTGRES_DSN` env override, driver-import guard, connection-failure guard) for every live-database test in this phase — none of this phase's tests may require a reachable PostgreSQL server or `psycopg` installation to pass in CI.
- [ ] A reusable test fixture/helper for provisioning a throwaway `vicmap_staging`-equivalent schema and a deliberately under-privileged role, so `PrivilegePreflightTest` can exercise both the pass and fail paths without touching a real operator-provisioned database.
- [ ] A small deliberately-invalid-geometry fixture (e.g. a bowtie polygon or a self-intersecting line) loadable via `ogr2ogr`, to exercise D-54/D-55's repair and hard-stop paths — the real `ADDRESS` layer is Points and cannot exercise this by itself (D-54's own note).
- [ ] Framework install: none — `unittest` is stdlib; `psycopg` install is this phase's own `flake.nix` change (Standard Stack).

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-------------------|
| V2 Authentication | No | No end-user authentication in this phase; the database role's own password auth is infrastructure, not an ASVS-scoped application authentication flow. |
| V3 Session Management | No | No session concept in a batch CLI pipeline. |
| V4 Access Control | Yes | `vicmap_loader`'s grants (D-59) are the access-control boundary — a non-superuser role scoped to exactly `vicmap_staging` + `vicmap`, provisioned out-of-band (D-60) rather than by application code, and DB-02 preflights it rather than assuming it. |
| V5 Input Validation | Yes | `naming.py`'s existing table-name normalization (D-45's scope) plus this phase's `psycopg.sql.Identifier`/`sql.SQL` composition for every dynamically-referenced identifier (schema names, table names) in preflight/validation queries — never string-formatted SQL. |
| V6 Cryptography (here: secrets handling) | Yes | The database password is never hand-rolled or stored in the repo — it flows through opnix/1Password exactly as `O365_AUTH_SECRET` already does (D-58), and is supplied to `ogr2ogr` via subprocess `env`, never argv (D-44). |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|-----------------------|
| SQL injection via dynamically-built identifiers (schema/table names derived, however indirectly, from an external delivery's layer names) | Tampering | `psycopg.sql.Identifier`/`sql.SQL` composition for every query in `staging.py` that references a schema- or table-name variable; never f-string/`.format()` raw SQL text (Architecture Pattern 2's example). |
| Credential leakage via process listing (`ps`) or shell history | Information Disclosure | D-44: password supplied via subprocess `env`, never command-line argv; matches the existing project posture that env vars are acceptable where argv is not, since the operating-system user boundary is the accepted trust boundary (same reasoning D-43 already applies to the local stderr diagnostic file). |
| Partial/half-loaded data becoming visible to a reader role | Information Disclosure | D-47's dedicated `vicmap_staging` schema, entirely outside any schema a reader role is ever granted — structural, not a runtime check (this phase does not implement reader grants; that's PUB-04/05 in Phase 4). |
| A failed load leaving a broken but similarly-named table behind that a later run's collision logic doesn't expect | Tampering / Denial of Service (of the pipeline itself) | D-48's run-timestamped table names mean a failed run's leftover table can never collide with a later run's target name; cleanup is explicitly deferred (D-65) rather than attempted inline, keeping DB-05's guarantee simple (nothing in `public`/`vicmap` is ever touched, regardless of what's left in `vicmap_staging`). |

## Sources

### Primary (HIGH confidence)

- `nix eval`/`nix build` against this repository's own pinned `nixpkgs` flake input — `gdal` (3.13.2), `proj` (9.8.1), `python3Packages.psycopg` (3.3.4), and the full `proj*`-matching top-level attribute-name search that found no `proj-data` attribute. All run this session.
- `ogrinfo --format PostgreSQL` and `ogr2ogr --long-usage`/direct failure invocations against the locally installed GDAL 3.13.2 (same binary the project's `flake.nix` pins) — layer creation options, open options, `-gt`/`-progress`/`-nln`/`-t_srs` flag semantics, and exit-code behavior (`0` success / `1` failure, confirmed against two distinct failure scenarios). Run this session.
- `https://cdn.proj.org/` directory listing and a full download + SHA-256 of `au_icsm_GDA94_GDA2020_conformal_and_distortion.tif` (27,272,664 bytes). Run this session.
- This project's own source: `vicmap_acquire/evidence.py`, `manifest.py`, `naming.py`, `discovery.py`, `read_mailbox.py`, `tests/test_naming.py`, `flake.nix`, `vicmap.toml`, `.planning/config.json`, `.gitignore` — all read this session.

### Secondary (MEDIUM confidence)

- GDAL PostgreSQL driver documentation (`gdal.org/en/latest/drivers/vector/pg.html`) — `PG_USE_COPY`, layer creation option descriptions, corroborating the live `ogrinfo` dump.
- PostGIS `ST_MakeValid` documentation (`postgis.net/docs/ST_MakeValid.html`) — return-type/collapse behavior backing D-55.
- PostgreSQL documentation and mailing-list discussion of `has_table_privilege`/`has_schema_privilege` error semantics on nonexistent relations — backing Common Pitfall 3.
- PROJ resource-files documentation and the `OSGeo/PROJ-data` GitHub project description — backing Common Pitfall 1's account of why grid data isn't bundled by default in PROJ ≥ 7.

### Tertiary (LOW confidence)

- General WebSearch results on `PGPASSWORD` security tradeoffs vs. `.pgpass` — informative context for D-44 but not load-bearing, since D-44 is already a locked decision this research supports rather than re-litigates.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — every version number and CLI behavior claim was independently reproduced against the project's own pinned toolchain this session, not taken from training data or CONTEXT.md alone.
- Architecture: HIGH — the load/validate/isolate shape is fully determined by CONTEXT.md's locked decisions; this research's contribution is the concrete mechanics (exact flags, exact query shapes) and the two corrections (Pitfalls 1 and 3).
- Pitfalls: MEDIUM-HIGH — Pitfalls 1, 3, and 4 are independently verified this session; Pitfall 2 (typed-column-by-default behavior) is flagged as needing a live empirical check rather than fully resolved (see Open Question 1).

**Research date:** 2026-09-21
**Valid until:** 30 days for the PostgreSQL/PostGIS/psycopg API surface (stable); re-verify the `proj-data`/grid-vendoring recommendation and the `psycopg` package-legitimacy checkpoint at plan time if this research is reused past that window, since nixpkgs revisions and PyPI release cadence move faster than PostGIS's core API.
