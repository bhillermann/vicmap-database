# Phase 3: Validated PostGIS Staging - Context

**Gathered:** 2026-09-21
**Status:** Ready for planning

<domain>
## Phase Boundary

Open the live PostGIS connection, report its non-secret identity, and prove the loader holds the privileges it needs. Load every manifest layer into isolated, uniquely named staging tables in a dedicated `vicmap_staging` schema, reprojecting to one configured target SRID. Run blocking validation over the staging tables, build indexes and constraints, and leave every existing production table untouched.

No publication into `vicmap`, no reader grants, no run summary — those are Phase 4. Mailbox access, download, extraction, discovery, and the manifest remain Phases 1 and 2 and are not repeated here. Legacy `public` table cleanup is Phase 5.

</domain>

<decisions>
## Implementation Decisions

### Loader Mechanism

- **D-41:** The loader is `ogr2ogr` invoked as a subprocess, one invocation per layer, with `--config PG_USE_COPY YES`. GDAL runs C++ end to end from geodatabase read to `COPY` buffer with no Python in the per-row path. A `pyogrio` + `psycopg3` `COPY BINARY` loader was considered and rejected: binary `COPY` saves roughly 100 MB of hex encoding across 4.2M point rows, which does not outrun the cost of materializing Arrow batches and re-serializing every row in Python. `gdal` is already a pinned `flake.nix` devShell dependency, so no new tooling is required. — **Reversibility:** costly — the DDL, type mapping, column naming, and index creation are all delegated to GDAL; replacing the loader means reimplementing every one of them in project code.
- **D-42:** Layers load sequentially in the manifest's deterministic order. A failure stops the run at a named layer. Parallel invocation was rejected: concurrent `COPY` into one database competes for I/O and WAL, interleaved stderr defeats per-layer diagnosis, and the proof delivery carries one layer.
- **D-43:** `ogr2ogr` failures surface as an exit code mapped to a typed closed reason code with the target table and a remediation hint, in the Phase 1 and 2 style. The complete unredacted stderr is written to the run directory beside the manifest, and the operator message names that file. Rationale: D-17 through D-20 exist to protect output that *travels* — journald and the failure email PROJECT.md plans. A local diagnostic file does not travel, and the same operating-system user already has filesystem access, so suppressing it there buys nothing.
- **D-44:** The database password never appears on the `ogr2ogr` command line. Command-line arguments are visible to other users via `ps`, and GDAL echoes connection strings in some error messages. With the password supplied out of band, D-43's stderr file contains no secret.

### Target Schema and Naming

- **D-45:** D-22's strict normalization governs **table names only**. Column names are whatever GDAL's `LAUNDER` produces, which defaults to `YES` and lowercases and launders field names — this is why the operator's existing shapefile imports have only ever needed a lowercase change. The column-level reserved-word, collision, and carve-out hard stops discussed earlier in this session were explicitly dropped. Consequence accepted knowingly: a future delivery with a field named `ORDER`, or two fields laundering to the same name, fails as a raw PostgreSQL error mid-load rather than as a clean stop before it. — **Reversibility:** one-way — column names are the published contract every QGIS project and saved query binds to; changing the rule after Phase 4 publishes requires renaming live columns.
- **D-46:** The geometry column is `geom` and the FID column is `gid`, via `-lco GEOMETRY_NAME=geom -lco FID=gid`. This is the PostGIS house style and costs two flags under D-41. GDAL's defaults (`wkb_geometry`, `ogc_fid`) were rejected as a worse published contract. — **Reversibility:** one-way — same published-contract reasoning as D-45.
- **D-47:** Staging tables live in a dedicated `vicmap_staging` schema, entirely outside `vicmap`. DB-03's no-tables-in-`public` requirement is then satisfied structurally rather than by naming convention, and a reader granted only `vicmap` cannot see half-loaded data even accidentally.
- **D-48:** Staging table names carry D-32's run timestamp — `vicmap_staging.vmadd_address_20260918t041500z`. Two runs over the same order coexist without collision and the name itself says which run produced it. This follows D-32's reasoning that re-runs over an unchanged artifact must stay distinguishable.

### Reprojection — supersedes D-39

- **D-49:** **D-39 is superseded.** `vicmap.toml` carries a configured `target_srid` (initially `7899`) and every layer is reprojected to it with `-t_srs`. Verified during this discussion: when source and target CRS match, `ogr2ogr -t_srs` produces byte-identical coordinates — no transform occurs, so today's delivery is unaffected. The gain is a single-SRID estate: a mixed-CRS delivery (D-24's `gda94_vicgrid` vs `gda2020_vicgrid` case) no longer produces tables in different SRIDs, and no cross-table spatial query needs `ST_Transform`. D-39's "record native CRS" was a deferral, not a finding. Phase 2's hard stop on an unresolvable EPSG stays — it is the transform's required input. — **Reversibility:** one-way — the SRID is baked into every published geometry column and into every downstream project once Phase 4 publishes.
- **D-50:** `proj-data` joins `flake.nix`. Measured during this discussion: `proj-9.8.1/share/proj` contains `proj.db` and 15 other entries and **zero** `.tif` or `.gsb` grid files, so a GDA94 VicGrid to GDA2020 VicGrid transform currently falls back to the grid-free conformal method. That fallback moved a Victorian test point +0.536 m easting and +1.461 m northing, and PROJ issued no warning. ICSM's NTv2 grid adds a distortion component worth up to roughly 0.1–0.3 m in parts of Victoria.
- **D-51:** Coordinate transformation fails closed: `OGR_CT_ONLY_BEST=YES` and `OGR_CT_ALLOW_BALLPARK=NO`. PROJ errors at transform time when the best operation's grid is unavailable, instead of silently degrading to a Helmert or ballpark operation. This applies the same fail-closed posture D-26 and D-34 already take, to accuracy rather than to resources. Both options were confirmed present in the installed GDAL 3.13.2.

### Column Types

- **D-52:** GDAL's OGR-to-PostgreSQL type mapping is accepted as-is. `PRECISION` defaults to `YES`, so `String(10)` becomes `varchar(10)` and the widths D-40 captured survive into the table. No `COLUMN_TYPES` overrides — a per-field type mapping is exactly the manual mapping PROJECT.md puts out of scope.

### Validation (DB-04)

- **D-53:** Validation runs against the **staging table in PostGIS, after reprojection** — not against the source file. It therefore validates what Phase 4 will actually publish, including anything D-49's transform changed.
- **D-54:** Validity is a full `ST_IsValid` scan over every row, and invalid geometries are **repaired with `ST_MakeValid`** rather than blocking the run. The repaired count is reported. Note for the planner: `ADDRESS` is a Point layer and points are valid by definition, so the check is O(1) per row and the cost is the sequential scan; validity becomes genuinely expensive only when a polygon layer arrives.
- **D-55:** A repair that changes the geometry type is a hard stop. `ST_MakeValid` can return a MultiPolygon or GeometryCollection where D-38 declared a Polygon, which a typed geometry column rejects. Ordinary noise is repaired quietly; a structural surprise still reaches the operator. `ST_CollectionExtract` salvage was rejected — it discards geometry silently.
- **D-56:** Three checks block the run when they disagree with the manifest: **row count** must equal D-37's exact feature count (this is the check that catches `ogr2ogr` dropping or duplicating features, and D-37 made the count exact precisely to serve as this baseline); **SRID** must equal the configured `target_srid`; **geometry type** must match D-38's declaration including Z and M dimensionality. **Extent is reported but does not block** — no sanity envelope is configured.
- **D-57:** Two validation profiles, selected by the manifest's existing `spatial` boolean. A spatial layer runs every check. A non-spatial layer (D-35's lookup tables and relationship classes) runs the row-count check only, and the geometry, SRID, and extent checks are recorded as **not applicable** — never as passed. This closes the branch D-35 flagged for this phase without weakening anything for spatial layers, and keeps the audit record Phase 4 composes truthful.

### Connection and Privileges

- **D-58:** Non-secret connection fields — host, port, dbname, user, and the two schema names — live in `vicmap.toml` alongside every other policy value. The password comes from 1Password through opnix, exactly as `O365_AUTH_SECRET` already does. This preserves Phase 2's rule that one file is the whole non-secret policy, while the secret stays out of the repository.
- **D-59:** The loader connects as a dedicated `vicmap_loader` role, not a superuser. It owns `vicmap_staging` and `vicmap` and holds exactly the privileges DB-02 preflights. DB-03's no-tables-in-`public` guarantee then holds because the role genuinely cannot write there, not because the code avoids it.
- **D-60:** The operator provisions the role and both schemas once, by hand, from a documented SQL script run as superuser. Phase 3's DB-02 preflight verifies the role, both schemas, and every required privilege, and stops with a closed failure naming what is missing. The pipeline never needs superuser, and provisioning stays a deliberate reviewable act. A versioned migration mechanism was rejected as its own phase.
- **D-61:** DB-01 prints host, port, dbname, connected role, server version, and PostGIS version — all six in clear. Every one is non-secret and already in `vicmap.toml` or trivially discoverable by anyone who can reach the server. Fingerprinting the host was rejected: DB-01 exists so the operator can confirm which database was reached, and a fingerprint defeats exactly that.

### Indexes and Constraints

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

### Superseded During This Discussion

Recorded so downstream agents do not act on the earlier answers:

- **Phase 2's D-39 is superseded by D-49.** Phase 2 recorded native CRS and forbade reprojection; Phase 3 reprojects to a configured target SRID. D-39's EPSG-resolution hard stop survives unchanged.
- **Column-level D-22 enforcement was proposed and then dropped.** Early in this discussion the operator chose normalized column names with hard stops on reserved words, collisions, and `geom`/`gid` clashes. On learning that GDAL's `LAUNDER` already produces those names and that keeping both would require post-load verification, the operator chose `ogr2ogr` alone. D-45 is the surviving decision; the column hard stops do not exist. D-46's `geom` and `gid` were separately reconfirmed and do survive.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project Scope and Requirements
- `.planning/PROJECT.md` — The constraints binding this phase: PostgreSQL with PostGIS as the target, lowercase `snake_case` normalization in a configured schema, publication through staging and atomic replacement, and the explicit out-of-scope entries for manual mappings and incremental upserts.
- `.planning/REQUIREMENTS.md` — Defines `DB-01` through `DB-05`.
- `.planning/ROADMAP.md` — Defines the fixed Phase 3 boundary and its five success criteria, plus the Phase 4 criteria that constrain what staging must hand over.

### Prior Phase Decisions (binding)
- `.planning/phases/02-safe-geospatial-discovery/02-CONTEXT.md` — Phase 2's `D-21` through `D-40`. Specifically binding here: D-21/D-22 (target table naming, now table-only per D-45), D-29/D-31 (the manifest contract and the redaction rule), D-32 (run identity, consumed by D-48), D-35 (the geometry-less branch this phase closes in D-57), D-37 (exact feature count, the D-56 baseline), D-38 (declared geometry type), D-40 (full field schema), and D-39 (superseded by D-49).
- `.planning/phases/01-trusted-graph-acquisition/01-CONTEXT.md` — Phase 1's `D-01` through `D-20`. Binding here: D-11 (act automatically after selection), D-17–D-20 (redacted evidence and safe failure reporting, scoped by D-43 to travelling output), and the fail-closed allowlist posture D-51 and D-64 both follow.

### Source Files (read these, not the maps)
- `vicmap_acquire/manifest.py` — `ImportManifest`, `ManifestLayer`, `CompanionFile`. The frozen object is this phase's input.
- `vicmap_acquire/discovery.py` — `LayerProfile` and `FieldProfile`. `LayerProfile.spatial` is the boolean D-57 branches on; `feature_count`, `geometry_type`, `epsg`, and `fields` drive D-52 and D-56.
- `vicmap_acquire/evidence.py` — `Stage`, `ReasonCode`, `fingerprint()`, `SuccessEvent` / `ProgressEvent` / `SafeFailure`, and the `_EmitOnce` guard. Phase 3's evidence extends this vocabulary.
- `vicmap_acquire/naming.py` — D-21/D-22 normalization and the live-verified 101-word PostgreSQL keyword set. Still authoritative for table names under D-45.
- `read_mailbox.py` — `load_config`, `load_discovery_config`, `validate_acquisition_policy`, `validate_discovery_policy`. The database section follows the same complete-key-set, fail-closed pattern.
- `vicmap.toml` — Existing `[mailbox]`, `[download]`, `[extraction]`, `[discovery]` sections. Phase 3 adds its own in the same flat, explicitly validated shape.
- `flake.nix` — `gdal` is already in the devShell (line 62), so `ogr2ogr` is pinned. D-50 adds `proj-data`.

### External Documentation
- GDAL PostgreSQL driver — `drivers/vector/pg.html` in the GDAL docs. The layer creation options this phase depends on (`LAUNDER`, `GEOMETRY_NAME`, `FID`, `SCHEMA`, `PRECISION`, `SPATIAL_INDEX`, `NONE_AS_UNKNOWN`, `COLUMN_TYPES`) were read from the live driver via `ogrinfo --format PostgreSQL` on GDAL 3.13.2 during this discussion; their defaults are recorded in `<specifics>` below.

### Codebase Maps (treat as stale where they concern this phase)
- `.planning/codebase/CONCERNS.md` — Correctly identifies the missing database layer, but its suggestions predate this discussion. Its connection-pooling recommendation does not apply: D-41 uses `ogr2ogr` subprocesses, not a pooled Python driver.
- `.planning/codebase/INTEGRATIONS.md` — States "Databases: Not used - this is a stateless acquisition tool". True at the time of writing, false from this phase onward.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `vicmap_acquire/evidence.py` (545 lines): `Stage` and `ReasonCode` already carry 13 stages and 34 reason codes across Phases 1 and 2. Phase 3's preflight, load, and validation failures extend this enum vocabulary rather than introducing a second output mechanism. `_EmitOnce` and the `fingerprint_hex_chars` threading are established behaviour to preserve.
- `vicmap_acquire/download.py` (758 lines): `DownloadPolicy` is the pattern the database policy dataclass should mirror — frozen, per-field validators, a typed failure hierarchy, configurable ceilings.
- `vicmap_acquire/naming.py` (199 lines): Pure, leaf-ward, no I/O, and its `ast` self-check proves it cannot import a database driver. D-45 keeps it authoritative for table names; the staging suffix in D-48 must still satisfy its 63-byte and charset rules.
- `read_mailbox.py` `load_discovery_config` / `validate_discovery_policy`: The established shape for adding a new `vicmap.toml` section with a complete required key set that fails closed on absence.
- `tests/test_naming.py`'s `PostgresKeywordOracleTest`: Already contains a working optional live-PostgreSQL connection pattern — driver import guarded, `VICMAP_TEST_POSTGRES_DSN` env override, skips cleanly when unreachable. Phase 3's live database tests can reuse this exact skip-not-fail structure.

### Established Patterns
- Every boundary is a frozen policy dataclass validated up front; one validator function is the single configuration contract shared by loader and runner.
- Failures are typed closed failures mapped to a fixed `ReasonCode`; unexpected exceptions map to one fixed internal failure with no interpolation. D-43 scopes this rule to travelling output and permits a full local diagnostic file.
- `None` is reserved for ordinary non-matches; malformed, ambiguous, or mismatched states get their own typed failures.
- Importing the package performs no authentication, network, or filesystem work.
- Allowlists start with a single entry and widen by config change (`allowed_senders`, `allowed_order_ids`, `allowed_hosts`, `supported_formats`). D-64's `index_columns` follows this shape.
- Independent-oracle testing where hand-written assertions would share the implementation's blind spot — `test_html_visibility_differential.py`, `test_discovery_differential.py`, and the live `pg_get_keywords()` check.

### Integration Points
- Phase 3 consumes the frozen `ImportManifest` and the run directory that `manifest.json` names. It must not re-open the mailbox or re-extract the archive.
- Phase 3 produces validated, indexed staging tables in `vicmap_staging` plus a per-layer validation record. Phase 4 promotes from these and, per D-65, is the event that authorizes dropping them.
- `tests/test_manifest.py:837` enforces a forbidden-import list (`psycopg`, `psycopg2`, `sqlalchemy`, `asyncpg`, `pg8000`) for the manifest module. Phase 3's database module is the first legitimate place a driver may appear; that policy test's scope must be checked rather than broadened blindly.
- `flake.nix` already pins `gdal` in the devShell. D-50 adds `proj-data`; verify the correct nixpkgs attribute and that `PROJ_DATA` resolves inside `nix develop`.
- `.gitignore` already covers `artifacts/` and `runs/` with unanchored patterns. D-43's stderr file lands inside `runs/`, so it is already ignored.

</code_context>

<specifics>
## Specific Ideas

Ground truth measured during this discussion. The planner and researcher should treat these as verified, not assumed.

**Environment:**
- GDAL **3.13.2** "Iowa City" at `/nix/store/1s8y110s9kac2v59vsin6q1i7g18zsnl-gdal-3.13.2`, already in the devShell.
- PROJ **9.8.1**. Its `share/proj` holds `proj.db` and 15 other entries — **no** `.tif` or `.gsb` grid files. This is what D-50 fixes.
- Port 5432 is open on the local host. No PostgreSQL driver is in `flake.nix` yet.

**GDAL PostgreSQL driver defaults, read from the live driver:**

| Option | Default | Bearing on this phase |
|---|---|---|
| `LAUNDER` | `YES` | D-45 — why existing imports only ever needed lowercasing |
| `PRECISION` | `YES` | D-52 — `String(10)` becomes `varchar(10)` |
| `SPATIAL_INDEX` | `GIST` | D-62 overrides to `NONE` |
| `GEOMETRY_NAME` | `wkb_geometry` | D-46 overrides to `geom` |
| `FID` | `ogc_fid` | D-46 overrides to `gid` |
| `NONE_AS_UNKNOWN` | `NO` | D-57 — non-spatial layers stay non-spatial tables |

`ONLY_BEST` and `ALLOW_BALLPARK` are both present as coordinate-transformation options in this GDAL build, backing D-51.

**Reprojection measurements:**
- `-t_srs EPSG:7899` against a source already in EPSG:7899 produced **byte-identical** coordinates to a control run with no `-t_srs`. No transform occurs when CRS matches.
- EPSG:3111 (GDA94 VicGrid) forced to EPSG:7899 with no grids installed shifted a test point **+0.536 m easting, +1.461 m northing** — roughly 1.56 m — using the grid-free conformal fallback, with no warning emitted.

**Expected proof-delivery outcome:** `VMADD.gdb`/`ADDRESS` → `vicmap_staging.vmadd_address_{run_timestamp}`, 4,222,035 Point features, `geom geometry(Point, 7899) NOT NULL`, `gid` primary key, GiST index built after validation, no reprojection performed. Phase 4 publishes it as `vicmap.vmadd_address`.

**Verification aid:** `ogrinfo` from the same pinned GDAL is available as an independent oracle for cross-checking layer counts, geometry types, and CRS against what the loader reports.

</specifics>

<deferred>
## Deferred Ideas

- **Failed-staging retention sweep (D-65).** The operator chose: staging tables are dropped after Phase 4's promotion commits, and staging tables left by a *failed* run are auto-dropped after a configurable number of days set in `vicmap.toml`. The drop-on-promotion half belongs to Phase 4, since only Phase 4 knows promotion succeeded. The age-based sweep is a destructive unattended action and is recorded here for the roadmap rather than built in Phase 3 — Phase 3 creates staging tables and never deletes one.
- **Extent sanity envelope.** A configured Victoria-shaped bounding box that a staging extent must fall inside, catching a transform that lands data offshore. Considered and explicitly not made blocking in D-56; extent is reported only.
- **Auto-pruning old run directories.** Carried forward unchanged from Phase 2's deferred list. Disk grows ~975 MB per run and is pruned manually.
- **Widening the format allowlist.** Carried forward unchanged from Phase 2. Shapefile, GeoPackage, MapInfo TAB, and DXF remain unsupported until a real delivery needs them.
- **Connection pooling.** `CONCERNS.md` recommends it for Phase 3. Not applicable under D-41 — `ogr2ogr` subprocesses manage their own connections, and the validation queries are few and sequential. Revisit only if a Python driver path returns.

</deferred>

---

*Phase: 03-validated-postgis-staging*
*Context gathered: 2026-09-21*
