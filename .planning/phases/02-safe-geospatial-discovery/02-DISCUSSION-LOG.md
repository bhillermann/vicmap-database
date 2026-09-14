# Phase 2: Safe Geospatial Discovery - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-09-14
**Phase:** 02-safe-geospatial-discovery
**Areas discussed:** Target table naming, Extraction safety & run directory, Manifest contract, Discovery scope & failures

**Grounding:** before questioning, the real Phase 1 artifact (`artifacts/Order_OK0VUZ.zip`) was inspected — 46 members, one `VMADD.gdb` containing a single `ADDRESS` layer (4,222,035 Point features, EPSG:7899). Every option below was written against that actual delivery rather than a hypothetical one.

---

## Target table naming

### Q1 — What should the published table for layer `ADDRESS` in `VMADD.gdb` be called?

| Option | Description | Selected |
|--------|-------------|----------|
| vmadd_address | `{gdb_stem}_{layer}` — deterministic from the delivery, keeps Vicmap's product grouping, collision-resistant | ✓ |
| address (bare layer name) | Simplest, but generic in a shared schema and collides with any future ADDRESS layer | |
| vicmap_address | Reads well, but depends on parsing the metadata PDF filename — weaker source | |

**User's choice:** vmadd_address

### Q2 — Policy when a name cannot be normalized cleanly?

| Option | Description | Selected |
|--------|-------------|----------|
| Strict charset, hard-stop on overflow | `[a-z0-9_]` only; illegal chars, leading digit, reserved word, or >63 bytes is a closed failure | ✓ |
| Strict charset, truncate with hash | Keeps deliveries flowing, but yields unpredictable names that don't round-trip | |
| Permissive — quote whatever arrives | Preserves source names, but conflicts with the PROJECT.md snake_case constraint | |

**User's choice:** Strict charset, hard-stop on overflow

### Q3 — Does a collision mean within-delivery duplicates, or an existing `vicmap` table?

| Option | Description | Selected |
|--------|-------------|----------|
| Within-delivery only | Existing table is the expected refresh; Phase 2 never contacts the database | ✓ |
| Within-delivery, plus warn on likely overwrite | Same boundary, extra manifest evidence | |
| Also check the live database | Strongest preflight, but crosses into Phase 3's boundary | |

**User's choice:** Within-delivery only

### Q4 — Should duplicate CRS/format variants of the same layer hard-stop?

| Option | Description | Selected |
|--------|-------------|----------|
| Yes — hard stop, fix by configuration | Genuine ambiguity the operator resolves by narrowing the order or configuring a preference | ✓ |
| Configured preference, silently pick one | Keeps runs flowing, but the manifest reflects an unseen choice | |
| Put the variant in the table name | No collision possible, but names carry packaging noise and break if Vicmap restructures folders | |

**User's choice:** Yes — hard stop, fix by configuration
**Notes:** Today's order delivers exactly one variant, so the strict choice costs nothing now.

---

## Extraction safety & run directory

### Q1 — Where does the run directory live, and what happens to it afterwards?

| Option | Description | Selected |
|--------|-------------|----------|
| runs/{order}/{timestamp}/, kept | Sibling of artifacts/, git-ignored, nothing auto-deleted, failed runs stay inspectable | ✓ |
| Temp dir, deleted on exit | Cleanest disk use, but Phase 3 loses its input and failures destroy their own evidence | |
| runs/{order}/{timestamp}/, auto-pruned | Bounds disk growth, but adds destructive behaviour to a non-mutating phase | |

**User's choice:** runs/{order}/{timestamp}/, kept
**Notes:** User's own words — "kept for now. Add auto-prune as a backlog item." Auto-prune recorded as a deferred idea rather than folded into scope.

### Q2 — Which extraction guards, and how strict?

| Option | Description | Selected |
|--------|-------------|----------|
| Configured ceilings, all fail-closed | Structural rejection plus configurable byte/count/ratio ceilings; mirrors DownloadPolicy | ✓ |
| Structural guards only | Simpler, but a zip bomb surfaces as a disk-full OS error rather than a safe reason code | |
| Structural guards, skip unsafe members | Maximises completion, but GEO-01 asks for rejection and risks an incomplete manifest | |

**User's choice:** Configured ceilings, all fail-closed

### Q3 — How should non-geospatial members be treated?

| Option | Description | Selected |
|--------|-------------|----------|
| Extract and record as unclassified | Manifest fully accounts for the archive; new member types surface as evidence | ✓ |
| Extract, ignore silently | Simplest, but the manifest can't prove it accounted for the whole archive | |
| Reject unrecognized members | Would fail on today's entirely legitimate delivery | |

**User's choice:** Extract and record as unclassified

### Q4 — How does Phase 2 bind extraction back to Phase 1 provenance?

| Option | Description | Selected |
|--------|-------------|----------|
| Re-verify checksum before extracting | Makes Phase 2 independently safe rather than trusting artifacts/ was untouched | ✓ |
| Record the checksum, don't re-verify | Faster, but asserts a checksum for bytes Phase 2 never verified | |
| Hash after extraction instead | Per-file integrity, but breaks the chain back to the authenticated message | |

**User's choice:** Re-verify checksum before extracting

---

## Manifest contract

### Q1 — What form does the immutable import manifest take?

| Option | Description | Selected |
|--------|-------------|----------|
| JSON file in the run dir + typed object | Clean in-process Phase 3 contract plus a durable, checksummed, reviewable artifact | ✓ |
| Typed in-process object only | Simplest, but nothing to review, diff, or attach to the Phase 4 run summary | |
| JSON file only | Maximum decoupling, but loses types on the round-trip and forces re-validation | |

**User's choice:** JSON file in the run dir + typed object

### Q2 — Does the operator approve the manifest before Phase 3?

| Option | Description | Selected |
|--------|-------------|----------|
| Automatic — every layer selected | Follows D-11's precedent; compatible with the unattended systemd goal | ✓ |
| Explicit approval gate | Strongest reading of "visible before loading", but contradicts unattended operation | |
| Configured layer allowlist | Consistent with Phase 1's posture, but reintroduces manual mappings PROJECT.md excluded | |

**User's choice:** Automatic — every layer selected

### Q3 — How does the manifest reconcile with Phase 1's redaction discipline?

| Option | Description | Selected |
|--------|-------------|----------|
| Full detail in file, redacted on screen | Redaction governs what is displayed and logged, not what the pipeline knows | ✓ |
| Redact in the file too | Consistent everywhere, but Phase 3 couldn't locate its own datasets | |
| Full detail everywhere | Easiest to debug, but abandons the discipline five gap-closure plans established | |

**User's choice:** Full detail in file, redacted on screen

### Q4 — What identifier ties the manifest into the Phase 4 run summary chain?

| Option | Description | Selected |
|--------|-------------|----------|
| Order ID + UTC run timestamp | The run directory name; human-readable, already unique, nothing new to invent | ✓ |
| Generated run UUID | Guaranteed unique and a natural audit primary key, but opaque and duplicative | |
| Artifact SHA-256 as run identity | Ties identity to content, but two re-runs become indistinguishable | |

**User's choice:** Order ID + UTC run timestamp

---

## Discovery scope & failures

### Q1 — Which geospatial reader gets added to `flake.nix`?

| Option | Description | Selected |
|--------|-------------|----------|
| pyogrio | Thin modern GDAL binding, native OpenFileGDB, metadata without materializing features | ✓ |
| osgeo.ogr | Most complete, but C-style API and error reporting resist the typed-failure style | |
| fiona | Mature and Pythonic, but heavier and upstream focus has shifted to pyogrio | |

**User's choice:** pyogrio
**Notes:** GDAL 3.12.4 is on the operator's profile but nothing importable is in the dev shell — no osgeo, pyogrio, or fiona.

### Q2 — What counts as a supported format?

| Option | Description | Selected |
|--------|-------------|----------|
| Configured allowlist, starting FileGDB-only | Mirrors Phase 1's single-entry allowlists; widening is a config change | ✓ |
| Anything GDAL can open | Maximum coverage, but could ingest formats never validated downstream | |
| Fixed list of four, hard-coded | Broader proof, but three of four would ship unexercised | |

**User's choice:** Configured allowlist, starting FileGDB-only

### Q3 — What should discovery do with a geometry-less table?

| Option | Description | Selected |
|--------|-------------|----------|
| Discover and record, don't select | Honours GEO-02 without expanding what gets published | |
| Discover and select like any layer | Most complete import; needs a separate downstream path through every spatial check | ✓ |
| Hard-stop on any non-spatial table | Maximally strict, but breaks on an ordinary lookup table | |

**User's choice:** Discover and select like any layer
**Notes:** The tradeoff was stated when the option was offered — Phases 3 and 4 are currently specified around geometry columns, SRIDs, and spatial validation, so this creates a real branch the planner must design for. Flagged in CONTEXT.md under D-35.

### Q4 — What exactly trips GEO-05's "unreadable" hard stop?

| Option | Description | Selected |
|--------|-------------|----------|
| Can't open, or missing required metadata | Stop condition is exactly "the manifest would be incomplete or wrong"; empty is legitimate | |
| Can't open only | Fewer false stops, but lets an incomplete manifest reach staging | |
| Can't open, missing metadata, or empty | Also catches a truncated delivery, at the cost of stopping on a genuinely empty snapshot | ✓ |

**User's choice:** Can't open, missing metadata, or empty
**Notes:** The strictest of the three. The tradeoff — that a legitimately empty layer will stop the run — was stated in the option text and accepted.

### Q5 — How exact does the feature count need to be?

| Option | Description | Selected |
|--------|-------------|----------|
| Exact always, forced scan if needed | Count is Phase 3's row-count baseline, so an estimate would make that check meaningless | ✓ |
| Exact where cheap, flagged estimate otherwise | Avoids full scans, but Phase 3 inherits a baseline that might not be a real number | |
| Exact always, hard-stop if unavailable | Fast and honest, but rejects formats for a performance characteristic | |

**User's choice:** Exact always, forced scan if needed
**Notes:** OpenFileGDB answers from the header — `ADDRESS` reports 4,222,035 with no scan, so today's path is free.

### Q6 — How is geometry type determined and recorded?

| Option | Description | Selected |
|--------|-------------|----------|
| Declared type; hard-stop if unusable | Consistent with the fail-closed line drawn elsewhere; avoids scanning 4.2M geometries | ✓ |
| Declared type, scan to confirm | Strongest guarantee, but a full geometry read of every layer on every run | |
| Declared type, fall back to GEOMETRY | Never stops, but gives up the type safety that makes published tables good to query | |

**User's choice:** Declared type; hard-stop if unusable

### Q7 — What CRS does the manifest record, and does Phase 2 reproject?

| Option | Description | Selected |
|--------|-------------|----------|
| EPSG required, no reprojection | Keeps discovery strictly read-only and defers a genuinely separate concern | ✓ |
| EPSG required, reproject to a target CRS | Nicer downstream, but reprojection is a transformation belonging to another phase | |
| Record WKT, allow unresolved EPSG | Never stops, but pushes the failure into the phase already touching the database | |

**User's choice:** EPSG required, no reprojection

### Q8 — How much field detail does the manifest capture?

| Option | Description | Selected |
|--------|-------------|----------|
| Full schema, incl. FID and geom columns | Phase 3 issues CREATE TABLE from this; String(10) vs String(80) is load-bearing | ✓ |
| Name and type only | Smaller, but widths and FID/geometry identities must be rediscovered at load time | |
| Full schema plus normalized column names | Consistent with table naming, but expands mapping scope and adds a second collision class | |

**User's choice:** Full schema, incl. FID and geom columns
**Notes:** By declining the third option the user kept column-name normalization out of Phase 2. Recorded in CONTEXT.md as "Open for Phase 3".

---

## Claude's Discretion

Captured in CONTEXT.md under `### Claude's Discretion`:

- `manifest.json` schema, field names, and whether it carries a schema version
- Safe default values for the D-26 extraction ceilings (calibrated against today's 46-member, ~975 MB, 4.2× delivery)
- UTC timestamp format in the run directory name
- Whether extraction is staged through a temp directory and renamed, mirroring Phase 1's atomic artifact publication
- New `Stage` / `ReasonCode` members in `evidence.py` and how the manifest renders as a redacted success event
- Module layout — inside `vicmap_acquire/` or a sibling package

## Deferred Ideas

- **Auto-pruning old run directories** — configurable retention beyond a keep-count. Requested by the user as a backlog item during Q1 of the extraction area, explicitly not folded into Phase 2.
- **Reprojection to a single target CRS** — a data transformation belonging with staging or its own phase.
- **Column-name normalization and collision handling** — deliberately left to Phase 3.
- **Widening the format allowlist** — shapefile, GeoPackage, MapInfo TAB, DXF, once a real delivery needs them.
