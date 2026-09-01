# Stack Research

**Domain:** Email-triggered File Geodatabase to PostGIS import proof
**Researched:** 2026-09-01
**Confidence:** HIGH for client-side stack; MEDIUM for server compatibility until the existing OCI database versions and delivered archive format are inspected

## Recommended Stack

### Core Technologies

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| Python | Nixpkgs-pinned Python 3.12+ (minimum 3.10) | Pipeline orchestration, message interpretation, download handling, validation, and SQL control | Preserves the existing implementation and reproducible Nix environment. Python 3.10 is the common minimum for current O365 2.1.9 and Psycopg 3.3.4; do not introduce a second runtime. |
| O365 | 2.1.9 | Microsoft Graph application authentication and mailbox/message access | The authentication prototype already works through this API. Upgrade the hand-built 2.1 derivation to the current 2.1.9 patch release rather than replacing a validated integration during an end-to-end proof. |
| GDAL/OGR | 3.13.2, or the exact 3.13.x package pinned by nixpkgs; minimum 3.10 | Discover File Geodatabase layers, inspect metadata, and stream them into PostGIS staging | `OpenFileGDB` is built into GDAL, reads `.gdb` directories and `.gdb.zip`, and does not need Esri's proprietary SDK. GDAL 3.10+ is important because support for 64-bit FileGDB OBJECTIDs began there. The PostgreSQL driver writes PostGIS geometry and creates GiST indexes by default. |
| Psycopg | 3.3.4 with the Nix-built C implementation and `libpq` | Database connectivity, catalog inventory, schema/privilege setup, staging validation, and transactional publication | Psycopg 3 is the current adapter for new Python/PostgreSQL applications. Its connection context and safe SQL composition suit explicit transactional DDL, while `ogr2ogr` handles the bulk spatial transfer. |
| Existing PostgreSQL + PostGIS OCI service | Inspect at runtime; do not upgrade in v0.1 | Destination database on localhost:5432 | The database already exists and contains legitimate production data. The proof should verify `server_version`, `postgis_full_version()`, connectivity, and privileges, then adapt to it rather than changing the server image. GDAL 3.9+ supports PostgreSQL 9+ and PostGIS 2+, but supported server releases are strongly preferred. |

### Supporting Libraries

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| Requests | 2.34.2, declared directly | Stream an HTTPS order artifact to a temporary file with redirects, timeouts, TLS verification, and bounded memory | Use only when the ready message contains an ordinary HTTPS link that is not downloaded through O365/Graph. It is currently merely transitive and should become an explicit dependency if imported by project code. |
| Python `zipfile`, `pathlib`, `tempfile`, `hashlib` | Standard library from selected Python | Inspect/extract ZIP safely, isolate work directories, and compute artifact checksums | Prefer for a confirmed ZIP delivery. Validate every member path before extraction, reject symlinks/special files, and impose file-count/uncompressed-size limits. |
| Python `subprocess` | Standard library | Invoke `ogrinfo`/`ogr2ogr` with checked exit status | Use a small project-owned wrapper with argument arrays, captured diagnostics, and no shell. This keeps GDAL's proven CLI as the data plane and Python/Psycopg as the control plane. |
| pytest | Current nixpkgs-pinned 8.x/9.x compatible with selected Python | Tests for email matching, URL extraction, archive safety, name normalization, SQL planning, and command construction | Add immediately even for the proof; unit tests can cover destructive boundaries without touching the real mailbox or database. Integration tests against the local OCI service should be opt-in. |

### Development Tools

| Tool | Purpose | Notes |
|------|---------|-------|
| `ogrinfo` | Prove a delivered dataset opens; list layers, geometry types, feature counts, extents, and CRS | Ship from the same GDAL derivation as `ogr2ogr`; begin by recording `ogrinfo --version` and driver availability. |
| `ogr2ogr` | Bulk-load each discovered layer into uniquely named staging tables | Target a dedicated `vicmap` schema via an explicit qualified `-nln`; never use `-overwrite` against a production table. Set deterministic geometry/FID names and use `FID64=TRUE` where source identifiers require it. |
| `psql` | Manual connectivity, catalog, PostGIS-version, and grants verification | Add the nixpkgs PostgreSQL client matching or newer than the server major where practical. Never place passwords in command arguments; use libpq environment/service configuration. |
| `ruff` | Fast linting and formatting | Optional but low-cost once the prototype becomes modules. It does not affect the runtime architecture. |

## Installation

Extend `flake.nix`; do not use `pip install` or ambient host binaries. Conceptually the shell needs:

```nix
packages = with pkgs; [
  gdal
  postgresql
  (python3.withPackages (ps: with ps; [
    python-o365   # update custom derivation to 2.1.9, or use nixpkgs when equal
    psycopg
    requests
    pytest
    ruff
  ]))
];
```

Use nixpkgs' GDAL, PostgreSQL/libpq, and Psycopg builds so native libraries come from one pinned closure. Confirm actual resolved versions with `gdalinfo --version`, `psql --version`, and a short Python import check after changing the flake. Avoid `psycopg[binary]` inside Nix: the Nix-built extension linked to the closure's `libpq` is the maintainable deployment form recommended by Psycopg's installation guidance.

## Integration Points

| Boundary | Recommended contract |
|----------|----------------------|
| Microsoft mailbox | Keep `O365.Account(..., auth_flow_type="credentials", tenant_id=...)`; query the configured mailbox and select a real ready-order message. Treat sender/subject parsing as project code, not an O365 concern. |
| Artifact download | Prefer the authenticated O365/Graph attachment API if the archive is attached. For a body URL, allow only HTTPS and expected hosts, then use a streaming Requests session with connect/read timeouts and a maximum size. |
| Archive | Download to a `tempfile` path, hash it, inspect the central directory, safely extract, then locate `.gdb` directories. Retain neither secrets nor uncontrolled filenames in logs. |
| Geospatial inspection | Use `ogrinfo -json` where available for machine-readable layer discovery; validate every layer has a usable CRS/geometry contract before loading. Normalize destination identifiers in Python and quote them with Psycopg's `sql.Identifier`. |
| Spatial bulk load | Load source layers only to collision-resistant staging names (for example `vicmap.__stage_<normalized>_<runid>`) with `ogr2ogr`. Treat the GDAL process exit status as necessary but not sufficient; validate row count, geometry column, SRID, invalid/empty geometry policy, and indexes in SQL. |
| Publication | Use Psycopg for one explicit transaction that locks the target name, renames the prior production table aside (when present), promotes the validated staging table, applies ownership/grants/default privileges, and commits. Drop the prior table only after successful promotion or retain it temporarily for rollback. |
| Abandoned WFS cleanup | Inventory catalog objects read-only and emit fully qualified candidates. Generate SQL only after the user approves an exact list; never infer deletion from naming alone and never scan/delete legitimate `public` GIS tables automatically. |

## Alternatives Considered

| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|-------------------------|
| O365 2.1.9 | Microsoft Graph Python SDK | Choose the official Graph SDK in a later milestone if O365 cannot expose the specific attachment/link behavior or Graph paging metadata needed. Switching now adds migration risk without improving the already validated login. |
| GDAL CLI + Psycopg control plane | GeoPandas + pyogrio + SQLAlchemy | Use GeoPandas for in-memory transformations or dataframe analytics. It is unnecessary for a faithful snapshot copy and risks materializing very large layers in RAM. |
| Direct `ogr2ogr` staging load | Python feature-by-feature inserts/COPY | Use custom COPY only when source-to-target field transformation cannot be expressed with OGR options/SQL. It greatly increases geometry serialization and type-mapping code. |
| Standard-library ZIP extraction | libarchive/7-Zip | Add a Nix-pinned extractor only after a real delivery proves the artifact is not ZIP or uses an unsupported compression method. |
| Handwritten, small SQL bootstrap | Alembic | Add Alembic when durable audit tables and an evolving application schema arrive. v0.1 needs only a small, reviewable schema/grant transaction. |

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| WFS as the bulk source | The prior attempt was abandoned because full synchronization was too slow; it also discards the order-delivery boundary this milestone must prove. | Downloaded Vicmap order archive plus GDAL/OpenFileGDB. |
| Esri FileGDB SDK / proprietary GDAL `FileGDB` driver | Adds proprietary native packaging and licensing complexity; GDAL's built-in `OpenFileGDB` already reads the target format and is more robust against corrupt databases. | Built-in `OpenFileGDB`. |
| GeoPandas as the loader | Whole-layer dataframe materialization creates avoidable memory pressure and duplicates GDAL/PostGIS type handling. | `ogrinfo`/`ogr2ogr` for data; Psycopg for control SQL. |
| SQLAlchemy | No ORM/domain model is required, and it does not improve GDAL bulk loading or transactional DDL clarity for this proof. | Psycopg 3 directly. |
| Psycopg connection pools or async stack | This is a single-run, sequential proof. Pooling and async lifecycle add failure modes without throughput benefit. | One synchronous Psycopg connection/transaction at a time. |
| `ogr2ogr -overwrite` on production names | It deletes/recreates the output layer and can expose absence/partial state or destroy a legitimate collision. | Unique staging table, validation, then transactional promotion. |
| Automatic cleanup by prefix, age, owner, or schema guess | The database contains both abandoned WFS output and legitimate GIS tables; heuristics cannot establish ownership safely. | Read-only inventory followed by exact user-approved fully qualified names. |
| Shell command strings containing database passwords | Credentials can leak through process listings, logs, history, or quoting errors. | libpq environment variables or a protected service/pass file; `subprocess` argument arrays. |
| Unbounded `extractall()` of emailed content | Email delivery is not proof that archive paths and expansion sizes are safe. ZIP entries can escape the destination or exhaust disk. | Preflight member paths, types, counts, and expanded sizes before controlled extraction. |

## Stack Patterns by Variant

**If the real order is a `.gdb.zip` with one top-level `.gdb`:**
- First try GDAL's direct OpenFileGDB ZIP support for inspection.
- Still extract into a private temporary directory for the v0.1 evidence trail unless direct reading is demonstrably complete for every delivered layer.

**If the archive contains multiple `.gdb` datasets or multiple layers:**
- Discover them all and create one staging/production table per normalized layer name.
- Fail closed on normalization collisions instead of suffixing silently.

**If the existing PostGIS server is unsupported or missing the extension:**
- Stop after reporting exact `version()` and `postgis_full_version()` results.
- Do not replace/recreate the OCI container as part of this milestone without separate approval.

**If a source layer lacks a usable CRS or mixes geometry types:**
- Stop that layer before publication and report the metadata.
- Do not invent an SRID or coerce geometry types merely to complete the demo.

## Version Compatibility

| Package A | Compatible With | Notes |
|-----------|-----------------|-------|
| O365 2.1.9 | Python >=3.10 | Current PyPI metadata lists Python 3.10-3.13 classifiers; validate under the exact nixpkgs Python before removing the custom build. |
| Psycopg 3.3.4 | Python 3.10-3.14; PostgreSQL 10-18 officially tested by the 3.3 docs | The existing server version must be queried. Use the Nix C build with matching `libpq`, not a bundled wheel. |
| GDAL 3.13.x | PostgreSQL >=9 and PostGIS >=2 for its PostgreSQL driver | Server-side compatibility is broad, but supported PostgreSQL/PostGIS releases are preferable. OpenFileGDB 64-bit OBJECTID reading requires GDAL >=3.10 and remains incomplete for sparse IDs; inspect warnings. |
| GDAL PostgreSQL driver | `libpq` from the same Nix closure | Ensure the nixpkgs GDAL output includes the PostgreSQL driver (`ogrinfo --formats`) before implementing loads. |
| `ogr2ogr -overwrite` + schema options | Not the publication mechanism | GDAL documents a schema/overwrite caveat; use an explicit qualified `-nln` for staging and Psycopg transactional renames for publication. |

## Sources

- [O365 2.1.9 on PyPI](https://pypi.org/project/o365/) — current release, Python requirement, and release history
- [Psycopg 3.3.4 on PyPI](https://pypi.org/project/psycopg/) — current stable adapter/version and supported Python metadata
- [Psycopg installation documentation](https://www.psycopg.org/psycopg3/docs/basic/install.html) — C versus binary versus pure-Python builds, supported Python/PostgreSQL versions
- [Psycopg COPY documentation](https://www.psycopg.org/psycopg3/docs/basic/copy.html) — available bulk-copy API if custom transformation later becomes necessary
- [GDAL OpenFileGDB driver](https://gdal.org/en/stable/drivers/vector/openfilegdb.html) — `.gdb`/`.gdb.zip` capabilities, built-in status, OBJECTID caveat, and direct PostGIS example
- [GDAL PostgreSQL/PostGIS driver](https://gdal.org/en/stable/drivers/vector/pg.html) — compatibility, schemas, transactions, geometry, FID64, and spatial-index behavior
- [GDAL advanced PostgreSQL driver information](https://gdal.org/en/stable/drivers/vector/pg_advanced.html) — qualified schema/table targeting
- [GDAL `ogr2ogr` reference](https://gdal.org/en/stable/programs/ogr2ogr.html) — overwrite semantics and transactional loading options
- [GDAL release archive](https://gdal.org/en/stable/download_past.html) — current 3.13.2 release date/version
- [Requests 2.34.2 on PyPI](https://pypi.org/project/requests/) — current release and streaming/timeout/TLS capabilities
- [Python `zipfile` documentation](https://docs.python.org/3/library/zipfile.html) — archive path-traversal warning and sanitization responsibilities
- [PostgreSQL schema documentation](https://www.postgresql.org/docs/current/ddl-schemas.html) — schema isolation, `USAGE`, and object privilege requirements

---
*Stack research for: Vicmap Database v0.1 End-to-End Import Proof*
*Researched: 2026-09-01*
