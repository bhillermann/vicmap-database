# Phase 3: Validated PostGIS Staging - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-09-21
**Phase:** 03-validated-postgis-staging
**Areas discussed:** Column naming, Load mechanism, Staging location + lifecycle, OGR to PostgreSQL types, Validation depth, Connection + role, Geometry-less layer path, Indexes + constraints

---

## Column naming

**Note:** This entire area was superseded later in the session by the Load mechanism decision. Recorded here because the reasoning shaped D-45 and D-46.

### Source field names to PostgreSQL column names

| Option | Description | Selected |
|--------|-------------|----------|
| Normalize via D-22 rule | Reuse `naming.py`'s normalizer; `EZI_ADDRESS` becomes `ezi_address` | ✓ |
| Keep verbatim, always quoted | Column stays `EZI_ADDRESS`; every query must double-quote | |
| Normalize, geometry and FID exempt | Fields normalize but `SHAPE`/`OBJECTID` get conventional names | |

### Invalid or colliding column name

| Option | Description | Selected |
|--------|-------------|----------|
| Hard stop, same as D-22/D-23 | Typed closed failure before any table is created | ✓ |
| Hard stop on collision, allow quoted reserved words | Mixed quoting across columns | |
| Deterministic disambiguation suffix | `name_2`, `name_3` by field order | |

### Geometry and FID column names

| Option | Description | Selected |
|--------|-------------|----------|
| Confirm `shape` and `objectid` | One rule, no exceptions; table mirrors source | |
| Geometry becomes `geom` | PostGIS community convention, one carve-out | |
| Geometry `geom` and FID `gid` | Full PostGIS/shp2pgsql house style | ✓ |

### Source field named GEOM or GID

| Option | Description | Selected |
|--------|-------------|----------|
| Hard stop — treat as a collision | Carve-out names reserved; identical failure mode | ✓ |
| Attribute wins, geometry gets `geom_1` | Geometry column name becomes unpredictable | |
| Fall back to `shape`/`objectid` for that layer | Two conventions coexist in one schema | |

**Notes:** All four answers except the `geom`/`gid` choice were dropped once the operator chose `ogr2ogr` alone. See the Load mechanism entry below.

---

## Load mechanism

**Clarification requested by operator:** *"to date I have just used ogr2ogr to import shapefiles into postgis layers and this has worked well... What is the real throughput/batching trade off between option 1 and option 2? I have not had to rename any fields post import, just change to lower case."*

Claude's initial framing had claimed ogr2ogr "decides your column names for you" and implied pyogrio was the faster path. Both were checked against the live driver and corrected:

- `ogrinfo --format PostgreSQL` on GDAL 3.13.2 showed `LAUNDER` defaults to `YES` — the reason the operator's existing imports only ever needed lowercasing. `GEOMETRY_NAME`, `FID`, `SCHEMA`, `PRECISION`, and `SPATIAL_INDEX` are all controllable via `-lco`.
- Both candidate paths end at a `COPY` stream. ogr2ogr runs C++ end to end with no Python in the per-row path, so it is likely the faster of the two. Binary `COPY` saves roughly 100 MB of hex encoding over 4.2M point rows, which does not outrun Python serialization overhead.

### Loader

| Option | Description | Selected |
|--------|-------------|----------|
| ogr2ogr + verify names in project code | Compute expected names, run ogr2ogr, diff `information_schema` after | |
| pyogrio + psycopg3 `COPY BINARY` | Full control of DDL, types and names in project code | |
| ogr2ogr alone, trust `LAUNDER` | Fewest moving parts, closest to current practice | ✓ |

### Fate of the D-22 column hard stops

Claude flagged that this answer contradicted the Column naming decisions, since `LAUNDER` leaves the column hard stops nowhere to run.

| Option | Description | Selected |
|--------|-------------|----------|
| Pre-flight check on the manifest | Pure function applies D-22 before any database work | |
| Drop them — `LAUNDER` is the contract | D-22 governs table names only | ✓ |
| Keep `geom`/`gid` flags only | Keep house style, drop validation | |

### Geometry and FID names under the new approach

| Option | Description | Selected |
|--------|-------------|----------|
| Keep `geom` and `gid` | Two `-lco` flags, no validation code | ✓ |
| GDAL defaults `wkb_geometry` / `ogc_fid` | Purest reading of "LAUNDER is the contract" | |

### Failure reporting

**Clarification requested by operator:** *"stderr needs to be logged somewhere for troubleshooting... Realistically, the only access would be by the user the tool is running as, plus root. Is there any point suppressing the raw output when the same user will have access to logging?"*

Claude agreed the point was sound, and reframed: the Phase 1 redaction rule protects output that *travels* — journald and the planned failure email — not a local file the same user can already read. The one genuine secret in ogr2ogr stderr is the DSN password, which belongs out of the command line regardless (command-line arguments are visible via `ps`).

| Option | Description | Selected |
|--------|-------------|----------|
| Full stderr to run directory, closed code on travelling surface | No suppression locally, redaction only where output leaves the machine | ✓ |
| Full stderr everywhere including journald | Nothing hidden; raw GDAL text would start leaving the machine | |
| Full stderr to run directory and stdout, closed code to journald | Interactive and scheduled runs produce different output | |

### Multi-layer execution

| Option | Description | Selected |
|--------|-------------|----------|
| Sequentially, in manifest order | Failure maps to a named layer | ✓ |
| Sequential, continue past failure | Partial staging set complicates Phase 4 | |
| Parallel, bounded workers | I/O and WAL contention, interleaved stderr | |

**Notes:** `gdal` was confirmed already pinned in the `flake.nix` devShell (line 62), so ogr2ogr needs no flake change.

---

## Staging location + lifecycle

### Where staging tables live

| Option | Description | Selected |
|--------|-------------|----------|
| Dedicated `vicmap_staging` schema | DB-03 satisfied structurally, not by convention | ✓ |
| Uniquely suffixed tables inside `vicmap` | Cheapest promotion; readers see staging tables | |
| PostgreSQL temporary tables | Strongest isolation; nothing survives to inspect | |

### Uniqueness of the staging table name

| Option | Description | Selected |
|--------|-------------|----------|
| Run identity in the table name | `vmadd_address_20260918t041500z`, follows D-32 | ✓ |
| Run identity in a per-run schema | One `DROP SCHEMA CASCADE` cleanup; more `search_path` handling | |
| Plain target name, one run at a time | Concurrent runs corrupt each other | |

### Lifecycle after a run

| Option | Description | Selected |
|--------|-------------|----------|
| Never auto-dropped, operator prunes | Matches D-25's leave-it-behind precedent | |
| Dropped on success, kept on failure | Bounded disk, failures preserved | ✓ |
| Dropped at start of next run | Destructive step runs unattended | |

**User's choice:** *"Dropped on success, kept on failure. Failures auto-dropped after x days. x Configurable in toml file."*

### Whose success triggers the drop

Claude flagged that Phase 3 cannot drop on its own success without destroying Phase 4's input.

| Option | Description | Selected |
|--------|-------------|----------|
| After Phase 4 promotion succeeds | Promotion is the only event proving staging is spent | ✓ |
| After Phase 3 validation passes | Phase 4 would have to re-load from the geodatabase | |
| Never inside a run — sweep only | Two retention knobs, always holds one run's data | |

---

## OGR to PostgreSQL types

### Type mapping

| Option | Description | Selected |
|--------|-------------|----------|
| Accept GDAL's mapping as-is | `PRECISION=YES` keeps D-40's widths | ✓ |
| Force `text` via `PRECISION=NO` | Immune to width growth; loses declared width | |
| Override via `COLUMN_TYPES` | Per-field mapping, out of scope per PROJECT.md | |

### Reprojection

**Clarification requested by operator:** *"I'm starting to doubt the necessity of D-39. What do I lose by just letting gdal determine the SRID from the source and add -t_srs EPSG:7899 to the ogr2ogr command? Will it perform a reprojection if the source srs is the same as the target?... What am I missing here?"*

Claude tested rather than asserted:

| Test | Result |
|---|---|
| `-t_srs EPSG:7899` on a source already in 7899 | Byte-identical to control — no transform occurs |
| EPSG:3111 forced to EPSG:7899, no grids | +0.536 m easting, +1.461 m northing, no warning |
| `proj-9.8.1/share/proj` contents | `proj.db` + 15 entries, zero `.tif`/`.gsb` grid files |

The operator's instinct was confirmed sound; the gap identified was accuracy, not correctness. Without ICSM's NTv2 grid, PROJ silently uses the grid-free conformal method, losing a distortion component worth up to roughly 0.1–0.3 m in parts of Victoria.

| Option | Description | Selected |
|--------|-------------|----------|
| Configured target SRID + PROJ grids in the flake | Single-CRS estate, accuracy gap closed | ✓ |
| Configured target SRID, no grids | First GDA94 delivery degrades silently | |
| Keep D-39, record native CRS | Mixed-CRS delivery yields mixed SRIDs | |

### Silent transform degradation

| Option | Description | Selected |
|--------|-------------|----------|
| `ONLY_BEST=YES` and `ALLOW_BALLPARK=NO` | Missing grid becomes a typed closed failure | ✓ |
| `ONLY_BEST=YES`, allow ballpark | Least accurate class stays permitted | |
| Accept PROJ defaults | Exactly the silent degradation measured above | |

---

## Validation depth

**Clarification requested by operator:** *"Is the scan on the imported table in postgis or on the file?"*

Claude confirmed: the staging table in PostGIS, after reprojection — so it validates what Phase 4 will publish. Also noted that `ADDRESS` is a Point layer, so `ST_IsValid` is O(1) per row and the cost is the sequential scan; validity becomes expensive only for polygon layers.

### Validity check depth

| Option | Description | Selected |
|--------|-------------|----------|
| Full scan, any invalid is a hard stop | Matches D-36's strictest-reading precedent | |
| Full scan, configurable threshold | Same scan, threshold in config | |
| Full scan, repair with `ST_MakeValid` | Nothing blocks; source data is altered | ✓ |

### `ST_MakeValid` returning a different geometry type

| Option | Description | Selected |
|--------|-------------|----------|
| Hard stop if repaired type differs | Quiet fix for noise, structural surprise still escalates | ✓ |
| `ST_CollectionExtract` largest component | Geometry discarded silently | |
| Repair and accept any type | Column loses its type constraint | |

### Which DB-04 checks block

| Option | Description | Selected |
|--------|-------------|----------|
| Row count equals manifest feature count | Catches dropped or duplicated features | ✓ |
| SRID equals configured target | Catches a transform that did nothing | ✓ |
| Geometry type matches manifest | Catches driver declaration mismatch | ✓ |
| Extent inside a configured envelope | Catches offshore or wrong-hemisphere data | |

**Notes:** Extent is reported but does not block.

---

## Connection + role

### Connection details

| Option | Description | Selected |
|--------|-------------|----------|
| Non-secret fields in `vicmap.toml`, password via opnix | Preserves the one-policy-file rule | ✓ |
| PostgreSQL service file | Standard practice; splits policy across files | |
| Full DSN from opnix | Host and dbname invisible to config readers | |

### Loader role

| Option | Description | Selected |
|--------|-------------|----------|
| Dedicated `vicmap_loader`, not superuser | DB-03 holds because the role cannot, not because code avoids | ✓ |
| Existing superuser or owner | DB-02 preflight becomes ceremonial | |
| Loader owns staging only | Phase 4 promotion needs a second identity | |

### Provisioning

| Option | Description | Selected |
|--------|-------------|----------|
| Operator provisions once, Phase 3 verifies fail-closed | Pipeline never needs superuser | ✓ |
| Phase 3 creates schemas if missing | Needs database-level CREATE | |
| Migration step in the repository | Introduces a mechanism the project lacks | |

### DB-01 identity output

| Option | Description | Selected |
|--------|-------------|----------|
| host, port, dbname, role, server version, PostGIS version | All non-secret; catches a wrong-server mistake | ✓ |
| Same, host fingerprinted | Hides the most useful field | |
| dbname and versions only | Does not say which host was reached | |

---

## Geometry-less layer path

| Option | Description | Selected |
|--------|-------------|----------|
| Two profiles selected by the manifest `spatial` flag | Geometry checks recorded as not applicable, never passed | ✓ |
| One profile, geometry checks pass vacuously | Audit record would contain a false statement | |
| Hard stop on any geometry-less layer | Reverses D-35 | |

---

## Indexes + constraints

### GiST index timing

| Option | Description | Selected |
|--------|-------------|----------|
| Defer — `SPATIAL_INDEX=NONE`, build after validation | Build once over a populated table | ✓ |
| Keep the default, built during load | Index maintained during a 4.2M row COPY | |
| Defer to Phase 4 | Published table briefly unindexed | |

### What else staging carries

| Option | Description | Selected |
|--------|-------------|----------|
| Primary key on `gid` | QGIS needs a unique integer column | ✓ |
| Typed geometry column with SRID constraint | Enforces D-56 at database level | ✓ |
| `NOT NULL` on the geometry column | Catches empty geometries | ✓ |
| Index on the Vicmap PFI identifier | Joins Vicmap layers to each other | ✓ |

### PFI index configuration

| Option | Description | Selected |
|--------|-------------|----------|
| Configured flat list of column names | Same shape as every other allowlist | ✓ |
| Per-table index configuration | Manual mapping, out of scope | |
| Convention — every column ending in `_pfi` | Indexes foreign keys whether queried or not | |

---

## Claude's Discretion

- `-gt` transaction group size, fixed or configured
- Progress reporting cadence during a multi-minute load
- Connection, statement, and lock timeout values
- Filename and format of the stderr diagnostic file
- New `Stage` and `ReasonCode` members in `evidence.py`
- Module layout for the database code
- Timestamp spelling in staging table names
- Whether the privilege preflight uses `has_*_privilege` or a probe transaction
- Whether validation runs inside or outside the load transaction
- Default retention period for the failed-staging sweep

## Deferred Ideas

- Failed-staging retention sweep — the drop-on-promotion half is Phase 4; the age-based sweep is destructive and unattended, recorded for the roadmap
- Extent sanity envelope — considered, explicitly not made blocking
- Auto-pruning old run directories — carried forward from Phase 2
- Widening the format allowlist — carried forward from Phase 2
- Connection pooling — not applicable under the ogr2ogr subprocess approach
