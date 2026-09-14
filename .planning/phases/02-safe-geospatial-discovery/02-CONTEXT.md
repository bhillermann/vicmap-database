# Phase 2: Safe Geospatial Discovery - Context

**Gathered:** 2026-09-14
**Status:** Ready for planning

<domain>
## Phase Boundary

Re-verify the Phase 1 artifact, extract it safely into an isolated per-run directory, discover every supported dataset and layer inside it, profile each layer (fields, exact feature count, geometry type, source CRS), assign a deterministic target table name to each, and emit an immutable import manifest — all before any database connection is opened.

No database connection, no staging tables, no loading, no reprojection, and no publication. Those belong to Phases 3 and 4. Mailbox access and downloading remain Phase 1's and are not repeated here.

</domain>

<decisions>
## Implementation Decisions

### Target Table Naming

- **D-21:** Target table name is `{gdb_stem}_{layer}` normalized — the delivery's layer `ADDRESS` inside `VMADD.gdb` publishes as `vmadd_address`. The geodatabase basename carries Vicmap's own product grouping (VMADD = Vicmap Address) and is read deterministically from the delivery itself, not from the metadata PDF filename. — **Reversibility:** one-way — the name is the published contract every GIS consumer queries; changing it after Phase 4 publishes requires renaming live tables and updating every downstream QGIS project and saved query.
- **D-22:** Normalization is strict: lowercase, allow only `[a-z0-9_]`, collapse runs of separators to a single `_`. Any character outside that set, a leading digit, a PostgreSQL reserved word, or a result exceeding 63 bytes is a typed closed failure that stops the run before any database work. No silent truncation and no hash suffixes — every target name must be predictable from the source name by inspection.
- **D-23:** A collision means two source layers **in the same delivery** normalizing to the same target name. That is the GEO-05 hard stop. An existing table of the same name in `vicmap` is *not* a collision — it is the expected snapshot replace, and Phase 2 never contacts the database to check.
- **D-24:** If a delivery ships the same logical layer in multiple CRS folders (`gda94_vicgrid` and `gda2020_vicgrid`) or multiple formats (`filegdb` and `shp`), both variants normalize to the same target name and the run hard-stops as a D-23 collision. The operator resolves it by narrowing the DataShare order or by adding an explicit configured CRS/format preference to `vicmap.toml`. Discovery never silently picks a variant, and CRS/format never appears in the table name.

### Extraction Safety and Run Directory

- **D-25:** Extraction target is `runs/{order_id}/{utc_timestamp}/`, a sibling of `artifacts/` and git-ignored the same way. One directory per run. Nothing is auto-deleted — Phase 3 reads from it and the operator prunes manually. An interrupted or failed run leaves an inspectable directory behind on purpose.
- **D-26:** Extraction is fail-closed on every guard. Reject before writing any member: absolute paths, `..` traversal, symlinks and hardlinks, non-regular members, and any member whose resolved path escapes the run directory. Plus configurable ceilings in `vicmap.toml` for total uncompressed bytes, per-member bytes, member count, and compression ratio. Breaching any one is a typed closed failure — never a skip-and-continue.
- **D-27:** Non-geospatial members (today: `Creative Commons Licence.html` and `VICMAP_ADDRESS_<uuid>.pdf`) are extracted like any other member and recorded in the manifest as **unclassified companion files** with name, size, and checksum. They are never treated as datasets. The manifest therefore accounts for every member of the archive, so a new member type in a future delivery surfaces as visible evidence rather than vanishing.
- **D-28:** Before extracting, Phase 2 re-verifies the artifact's SHA-256 and byte count against the values Phase 1 reported, taking them as required input, and refuses to extract on any mismatch. The verified checksum becomes the manifest's provenance anchor. Phase 2 does not trust that nothing touched `artifacts/` since Phase 1 ran.

### Manifest Contract

- **D-29:** The manifest is both a frozen typed object (the API Phase 3 consumes in-process) and a `manifest.json` written into the run directory with its own SHA-256 recorded alongside it. The typed object keeps the Phase 3 contract clean; the file makes "immutable" provable and gives the operator something durable to review and diff between runs. — **Reversibility:** costly — `manifest.json` becomes the documented Phase 2→3 handoff and is referenced by the Phase 4 run summary; changing its shape later touches the loader, the summary composer, and any retained manifests.
- **D-30:** Every discovered, supported layer is selected automatically. There is no interactive approval gate and no per-layer allowlist. Phase 2 ends by rendering the manifest as redacted operator evidence. This follows D-11's precedent (Phase 1 downloads automatically after selection rather than requiring a second confirmation) and keeps the pipeline compatible with the unattended daily systemd goal in PROJECT.md. A configured per-layer allowlist is explicitly rejected — PROJECT.md puts manual layer mappings out of scope.
- **D-31:** `manifest.json` holds full detail — complete filesystem paths, real layer names, full field lists, extents. It is a git-ignored local working file that Phase 3 must be able to act on. Operator-facing output stays redacted in the Phase 1 style: order ID, counts, target table names, and path fingerprints only. The redaction rule governs what is *displayed and logged*, not what the pipeline knows internally.
- **D-32:** Run identity is `{order_id}` + UTC run timestamp — the run directory name — recorded in the manifest alongside the artifact SHA-256 and the Phase 1 message fingerprint. No new UUID is minted, and the artifact checksum is explicitly *not* the run identity, because two re-runs over the same unchanged artifact must remain distinguishable in the Phase 4 audit chain.

### Discovery Scope and Failure Boundaries

- **D-33:** Use **pyogrio** as the geospatial reader, added to `flake.nix`. It reads OpenFileGDB natively and exposes layer lists, field schemas, geometry types, CRS, and feature counts without materializing features. `osgeo.ogr` and `fiona` were both considered and rejected — the former for its C-style API and error reporting that resists the typed closed-failure style Phase 1 established, the latter for weight and for upstream focus having shifted toward pyogrio. Note: GDAL 3.12.4 is present on the operator's profile but **not** in the dev shell — no `osgeo`, `pyogrio`, or `fiona` is currently importable.
- **D-34:** Supported formats come from a configured `supported_formats` allowlist in `vicmap.toml`, initially `["OpenFileGDB"]` only — mirroring how Phase 1 started its sender and order-ID allowlists with a single entry each. Encountering an unlisted format in a delivery is a typed closed failure naming the format. Widening is a one-line config change once a real delivery needs it.
- **D-35:** Geometry-less tables inside a geodatabase (lookup tables, relationship classes) are discovered **and selected** like any other layer, loading into PostGIS as plain non-spatial tables.
  > **Flagged consequence for Phases 3 and 4:** those phases are currently specified around geometry columns, SRIDs, and spatial validation. A geometry-less layer needs its own path through staging validation (DB-04's geometry/SRID/validity/extent checks) and through publication. The planner must account for this; it is a real branch, not an edge case to defer.
- **D-36:** GEO-05's hard stop trips on three conditions: a dataset or layer that will not open; a layer missing anything GEO-03 promises (fields, feature count, geometry type where spatial, resolvable CRS); **and a layer with zero features**. The operator chose the strictest reading — an empty layer is treated as evidence of a truncated or half-built delivery rather than a legitimate empty snapshot. This will stop a run on a genuinely empty layer, and that trade was made knowingly.
- **D-37:** Feature counts are exact, always. Take the driver's cheap header count where offered (OpenFileGDB does — `ADDRESS` reports 4,222,035 without a scan) and fall back to a full feature scan where it is not. The manifest never states an estimate, because this count is the row-count baseline Phase 3's staging validation checks against.
- **D-38:** Geometry type is taken from the layer's declaration, including Z/M dimensionality, and recorded as-is. A driver declaring `Unknown`/generic geometry — leaving no single type Phase 3 could build a column from — is a typed closed failure. No full scan of geometries to confirm the declared type, and no falling back to an untyped `GEOMETRY` column.
- **D-39:** The manifest records the source WKT plus a resolved EPSG code, and hard-stops if no EPSG can be resolved — PostGIS needs an integer SRID and the failure belongs here, before the database is touched. **Phase 2 never reprojects.** Layers are recorded in their native CRS (`ADDRESS` → EPSG:7899, GDA2020 / VicGrid); any transform is a separate, explicit, later decision.
- **D-40:** Field capture is the full schema: name, OGR type, width/precision, and nullability for every field, plus the FID column name (`OBJECTID`) and geometry column name (`SHAPE`). Phase 3 issues `CREATE TABLE` from this, so `String(10)` vs `String(80)` is load-bearing detail.

### Claude's Discretion

- Exact `manifest.json` schema and field names, and whether it carries a schema version.
- Safe default values for the D-26 ceilings (total uncompressed bytes, per-member bytes, member count, compression ratio). Today's real delivery is the calibration point: 46 members, ~975 MB uncompressed from 233 MB, ratio ≈ 4.2×.
- The UTC timestamp format used in the run directory name, provided it sorts lexicographically and is filesystem-safe.
- Whether extraction goes to a temporary directory and is renamed into place (mirroring Phase 1's atomic artifact publication) or writes directly into the run directory.
- New `Stage` and `ReasonCode` values in `vicmap_acquire/evidence.py` for the extraction and discovery failure modes, and how the manifest renders as a redacted success event.
- Module layout — whether discovery lives in `vicmap_acquire/` alongside the existing modules or in a sibling package.

### Open for Phase 3

- **Column naming.** D-40 captures source column names verbatim; it does **not** decide whether columns are normalized to snake_case on load, or how a column-name collision would be handled. The operator explicitly chose not to expand Phase 2's mapping responsibility from tables to columns. Phase 3 owns this.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project Scope and Requirements
- `.planning/PROJECT.md` — Milestone goal, trust boundary, and the constraints that bind this phase: lowercase `snake_case` layer normalization in a configured schema, automatic layer discovery (manual order-to-table mappings are out of scope), and complete-snapshot replacement rather than incremental upserts.
- `.planning/REQUIREMENTS.md` — Defines `GEO-01` through `GEO-05` and the explicit out-of-scope list.
- `.planning/ROADMAP.md` — Defines the fixed Phase 2 boundary and its four success criteria, and the Phase 3/4 criteria that constrain what the manifest must carry.

### Prior Phase Decisions (binding)
- `.planning/phases/01-trusted-graph-acquisition/01-CONTEXT.md` — Phase 1's locked decisions `D-01` through `D-20`. Specifically binding here: D-11 (act automatically after selection, no second confirmation), D-17–D-20 (redacted evidence and safe failure reporting), and the fail-closed configuration-allowlist posture that D-24, D-26, and D-34 all follow.
- `.planning/phases/01-trusted-graph-acquisition/01-VERIFICATION.md` — The 21/21 must-have verification record for Phase 1.

### Codebase Maps
- `.planning/codebase/ARCHITECTURE.md`, `CONVENTIONS.md`, `STACK.md`, `TESTING.md` — Written 2026-08-31, **before** Phase 1 was implemented. Treat as stale: `vicmap_acquire/` and its ~6,900 lines of module and test code did not exist when these were produced. Read the source, not these maps, for current patterns.

No external specs or ADRs were referenced during discussion.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `vicmap_acquire/evidence.py` (376 lines): `Stage` and `ReasonCode` enums, `fingerprint()`, `mask_sender()`, `remediation_hint()`, the `_SafeEvent` mapping base, and `SuccessEvent` / `ProgressEvent` / `SafeFailure` with their `render_*` functions. Phase 2's extraction and discovery evidence extends these rather than introducing a second output mechanism. The `_EmitOnce` guard and the `fingerprint_hex_chars` threading are established behaviour to preserve.
- `vicmap_acquire/download.py` (609 lines): `DownloadPolicy` is the pattern D-26's extraction policy should mirror — a frozen dataclass with per-field validators, a typed `DownloadFailure` exception hierarchy, and configurable ceilings. `DownloadResult` carries the byte count and SHA-256 that D-28 re-verifies. `_publish_artifact` / `_fsync_directory` show the established atomic-write idiom.
- `vicmap.toml`: Existing `[mailbox]` and `[download]` sections. Phase 2 adds its own section(s) in the same shape — flat, explicitly validated keys with allowlists carrying a single initial entry.
- `flake.nix`: The pinned `python3.withPackages` list (currently `python-o365`, `html5lib`) and `propagatedBuildInputs` are where `pyogrio` is added (D-33). Extend rather than relying on the ambient GDAL already on the operator's profile.
- `tests/` (~5,000 lines across 7 files): Established pytest conventions, including `test_html_visibility_differential.py`'s differential-oracle approach for parsing logic.

### Established Patterns
- Every boundary is a frozen policy dataclass validated up front; `validate_acquisition_policy` is the single configuration contract shared by `load_config` and the runner.
- Failures are typed closed failures mapped to a fixed `ReasonCode`; unexpected exceptions map to one fixed internal failure with no interpolation. Raw exception text never reaches output.
- `None` is reserved for ordinary non-matches; malformed, ambiguous, or mismatched states get their own typed failures.
- Importing the package performs no authentication, network, or filesystem work — `vicmap_acquire/__init__.py` exports nothing and documents this.
- Artifact output is constrained to the recognized `artifacts/` name and `.gitignore` uses an unanchored pattern so nested output roots are provably ignored. D-25's `runs/` directory needs equivalent treatment.

### Integration Points
- Phase 2 consumes `DownloadResult`'s final path, byte count, and SHA-256 (D-28) and the Phase 1 message fingerprint (D-32) — a manifest provenance block, not a new mailbox path.
- Phase 2 produces the frozen manifest object plus `manifest.json` (D-29) as the sole Phase 3 input. Phase 3 opens the database; Phase 2 must not.
- New extraction/discovery `Stage` and `ReasonCode` members extend `evidence.py`'s existing vocabulary, keeping `reason_stage_vocabulary()` complete.
- `.gitignore` needs a `runs/` pattern with the same unanchored treatment `artifacts/` received.

</code_context>

<specifics>
## Specific Ideas

Ground truth from the real Phase 1 artifact (`artifacts/Order_OK0VUZ.zip`, 233,089,097 bytes), inspected during this discussion — the planner and researcher should treat these as the concrete calibration case:

- **Archive shape:** 46 members, no nested archives, ~974,603,864 bytes uncompressed (ratio ≈ 4.2×).
- **Layout:** one Esri File Geodatabase at `gda2020_vicgrid/filegdb/whole_of_dataset/victoria/VMADD.gdb`. The path encodes CRS (`gda2020_vicgrid`), format (`filegdb`), coverage (`whole_of_dataset`), and region (`victoria`) — this is the structure D-24's variant collision would arise from.
- **Companion files:** `Creative Commons Licence.html` and `VICMAP_ADDRESS_b9e9146d-8378-5c37-b6cd-63e3a8d05d02.pdf` at the archive root (D-27's unclassified members).
- **The single layer:** `ADDRESS` — Point geometry, **4,222,035 features**, FID column `OBJECTID`, geometry column `SHAPE`, CRS `PROJCRS["GDA2020 / Vicgrid"]` resolving to **EPSG:7899**, extent `(2126780.196697, 2259755.350635) - (2934322.982015, 2826389.754039)`.
- **Field examples:** `UFI Integer(0.0)`, `PFI String(10.0)`, `PROPERTY_PFI String(10.0)`, `EZI_ADDRESS String(80.0)`, `SOURCE String(3.0)`, `SOURCE_VERIFIED DateTime`, `IS_PRIMARY String(1.0)`, `PROPERTY_STATUS String(1.0)`.
- **Expected target:** `vicmap.vmadd_address` under D-21.
- **Verification aid:** GDAL 3.12.4 "Chicoutimi" `ogrinfo` is available on the operator's profile and opens this geodatabase with the `OpenFileGDB` driver — useful as an independent oracle for checking that pyogrio-based discovery reports the same layers, counts, types, and CRS.

</specifics>

<deferred>
## Deferred Ideas

- **Auto-pruning old run directories.** Configurable retention that deletes `runs/{order}/{timestamp}/` directories beyond a keep-count at the start of each run. Explicitly deferred to the backlog during this discussion: it adds destructive behaviour to a phase whose entire premise is that nothing is mutated yet. Disk growth is ~975 MB per run and is managed manually for now.
- **Reprojection to a single target CRS.** Defining one target SRID in config so every published table shares it (D-39 records native CRS only). Reprojection is a data transformation and belongs with staging or its own phase, not with read-only discovery.
- **Column-name normalization and collision handling.** Applying snake_case normalization to field names as well as table names. Deliberately left out of Phase 2's mapping responsibility; see "Open for Phase 3" above.
- **Widening the format allowlist.** Shapefile, GeoPackage, MapInfo TAB, and DXF support (D-34 starts at `OpenFileGDB` only). Adding a format is a config change plus whatever driver-specific handling a real delivery proves is needed — not speculative code now.

</deferred>

---

*Phase: 02-safe-geospatial-discovery*
*Context gathered: 2026-09-14*
