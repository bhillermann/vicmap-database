# Phase 2: Safe Geospatial Discovery - Research

**Researched:** 2026-09-14
**Domain:** Safe zip extraction, GDAL/OGR metadata introspection (pyogrio), CRS→EPSG resolution (pyproj), PostgreSQL identifier constraints, immutable manifest design
**Confidence:** HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Target Table Naming**
- **D-21:** Target table name is `{gdb_stem}_{layer}` normalized — the delivery's layer `ADDRESS` inside `VMADD.gdb` publishes as `vmadd_address`. The geodatabase basename carries Vicmap's own product grouping (VMADD = Vicmap Address) and is read deterministically from the delivery itself, not from the metadata PDF filename. — **Reversibility:** one-way.
- **D-22:** Normalization is strict: lowercase, allow only `[a-z0-9_]`, collapse runs of separators to a single `_`. Any character outside that set, a leading digit, a PostgreSQL reserved word, or a result exceeding 63 bytes is a typed closed failure that stops the run before any database work. No silent truncation and no hash suffixes.
- **D-23:** A collision means two source layers **in the same delivery** normalizing to the same target name. That is the GEO-05 hard stop. An existing table of the same name in `vicmap` is *not* a collision — Phase 2 never contacts the database to check.
- **D-24:** If a delivery ships the same logical layer in multiple CRS folders or multiple formats, both variants normalize to the same target name and the run hard-stops as a D-23 collision. Discovery never silently picks a variant, and CRS/format never appears in the table name.

**Extraction Safety and Run Directory**
- **D-25:** Extraction target is `runs/{order_id}/{utc_timestamp}/`, a sibling of `artifacts/` and git-ignored the same way. One directory per run. Nothing is auto-deleted. An interrupted or failed run leaves an inspectable directory behind on purpose.
- **D-26:** Extraction is fail-closed on every guard. Reject before writing any member: absolute paths, `..` traversal, symlinks and hardlinks, non-regular members, and any member whose resolved path escapes the run directory. Plus configurable ceilings in `vicmap.toml` for total uncompressed bytes, per-member bytes, member count, and compression ratio. Breaching any one is a typed closed failure — never a skip-and-continue.
- **D-27:** Non-geospatial members (`Creative Commons Licence.html`, `VICMAP_ADDRESS_<uuid>.pdf`) are extracted like any other member and recorded in the manifest as **unclassified companion files** with name, size, and checksum. Never treated as datasets.
- **D-28:** Before extracting, Phase 2 re-verifies the artifact's SHA-256 and byte count against the values Phase 1 reported, taking them as required input, and refuses to extract on any mismatch. The verified checksum becomes the manifest's provenance anchor.

**Manifest Contract**
- **D-29:** The manifest is both a frozen typed object (the API Phase 3 consumes in-process) and a `manifest.json` written into the run directory with its own SHA-256 recorded alongside it. — **Reversibility:** costly.
- **D-30:** Every discovered, supported layer is selected automatically. No interactive approval gate, no per-layer allowlist. A configured per-layer allowlist is explicitly rejected.
- **D-31:** `manifest.json` holds full detail — complete filesystem paths, real layer names, full field lists, extents. It is a git-ignored local working file. Operator-facing output stays redacted in the Phase 1 style: order ID, counts, target table names, and path fingerprints only.
- **D-32:** Run identity is `{order_id}` + UTC run timestamp — the run directory name — recorded in the manifest alongside the artifact SHA-256 and the Phase 1 message fingerprint. No new UUID is minted; the artifact checksum is explicitly *not* the run identity.

**Discovery Scope and Failure Boundaries**
- **D-33:** Use **pyogrio** as the geospatial reader, added to `flake.nix`. It reads OpenFileGDB natively and exposes layer lists, field schemas, geometry types, CRS, and feature counts without materializing features. `osgeo.ogr` and `fiona` were both considered and rejected.
- **D-34:** Supported formats come from a configured `supported_formats` allowlist in `vicmap.toml`, initially `["OpenFileGDB"]` only. Encountering an unlisted format is a typed closed failure naming the format.
- **D-35:** Geometry-less tables inside a geodatabase are discovered **and selected** like any other layer, loading into PostGIS as plain non-spatial tables. Flagged consequence: Phases 3/4 need a non-spatial branch.
- **D-36:** GEO-05's hard stop trips on three conditions: unopenable dataset/layer; missing anything GEO-03 promises; **and a layer with zero features**. An empty layer is treated as evidence of a truncated delivery.
- **D-37:** Feature counts are exact, always. Take the driver's cheap header count where offered (OpenFileGDB does) and fall back to a full feature scan where not. Never an estimate.
- **D-38:** Geometry type is taken from the layer's declaration, including Z/M dimensionality, recorded as-is. A driver declaring `Unknown`/generic geometry is a typed closed failure. No full geometry scan, no falling back to untyped `GEOMETRY`.
- **D-39:** The manifest records the source WKT plus a resolved EPSG code, hard-stopping if no EPSG can be resolved. Phase 2 never reprojects.
- **D-40:** Field capture is the full schema: name, OGR type, width/precision, and nullability for every field, plus the FID column name and geometry column name.

### Claude's Discretion
- Exact `manifest.json` schema and field names, and whether it carries a schema version.
- Safe default values for the D-26 ceilings. Calibration point: 46 members, ~975 MB uncompressed from 233 MB, ratio ≈ 4.2×.
- The UTC timestamp format used in the run directory name, provided it sorts lexicographically and is filesystem-safe.
- Whether extraction goes to a temporary directory and is renamed into place, or writes directly into the run directory.
- New `Stage` and `ReasonCode` values in `vicmap_acquire/evidence.py` for extraction/discovery failure modes, and how the manifest renders as a redacted success event.
- Module layout — discovery in `vicmap_acquire/` or a sibling package.

### Deferred Ideas (OUT OF SCOPE)
- Auto-pruning old run directories.
- Reprojection to a single target CRS.
- Column-name normalization and collision handling (explicitly deferred to Phase 3).
- Widening the format allowlist beyond `OpenFileGDB`.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| GEO-01 | Operator can unpack the order archive into an isolated run directory without permitting path traversal, unsafe links, or writes outside that directory. | See "Safe Archive Extraction" (Architecture Patterns, Common Pitfalls) — verified `zipfile` does NOT reject unsafe members by default (it silently strips them), so manual member-by-member validation before any write is mandatory. Ceiling calibration numbers verified against the real 233 MB delivery. |
| GEO-02 | Operator can see every supported geospatial dataset and layer discovered in the unpacked order. | See "pyogrio API Surface" — `pyogrio.list_layers()` verified against the real `VMADD.gdb`, returns exactly `[['ADDRESS', 'Point']]`; verified behavior for a geometry-less table (returns `None` for the type slot). |
| GEO-03 | Operator can see each layer's fields, feature count, geometry type, and source CRS. | See "pyogrio API Surface" and "The Field Width/Precision Gap" — `pyogrio.read_info()` verified to supply feature count, geometry type, and CRS directly, but does **not** supply field width/precision/nullability; `ogrinfo -json` verified to supply exactly those three as a byte-exact supplement. |
| GEO-04 | Operator can see the deterministic source-layer-to-table-name mapping before any database mutation. | See "Manifest Contract" and "PostgreSQL Identifier Constraints" — reserved-word category nuance verified against the official PostgreSQL keyword appendix; 63-byte `NAMEDATALEN` limit is byte-exact but the charset is ASCII-only so `len(name)` suffices. |
| GEO-05 | Processing stops before database mutation if datasets are unreadable or normalized table names collide. | See "Common Pitfalls" — `geometry_type is None` (legitimate non-spatial layer) vs `geometry_type == "Unknown"` (D-38 hard stop) verified as two genuinely distinct, easily confused pyogrio return values. |
</phase_requirements>

## Summary

Phase 2 is a pure, database-free extraction-and-discovery step that turns a verified zip archive into an immutable manifest. The two hardest technical questions — "can pyogrio alone deliver everything D-33/D-37/D-38/D-39/D-40 need?" and "does Python's `zipfile` give safe extraction for free?" — were answered this session by building a throwaway Nix shell with `pyogrio` 0.13.0 and `pyproj` 3.7.2 (both confirmed present in `nixpkgs-unstable` and importable under Python 3.14.7, the flake's current interpreter) and running it directly against the real Phase 1 artifact (`artifacts/Order_OK0VUZ.zip`, 233,089,097 bytes, extracted to a scratch directory). The answer to both questions is a qualified **no**: `zipfile.extractall()` silently sanitizes `..`/absolute-path components rather than rejecting them (verified by reading the CPython 3.14 stdlib source), so D-26's "typed closed failure, never skip-and-continue" posture requires hand-rolled member validation before any write — the same posture `download.py` already takes for HTTP redirects. And `pyogrio.read_info()` does not expose field width, precision, or nullability (confirmed both by its documented return-dict keys and by disassembling the compiled extension's OGR C-API calls) — but GDAL's own `ogrinfo -json` CLI, added to the flake as `pkgs.gdal` alongside `pkgs.python3.pkgs.pyogrio`/`pyproj`, supplies exactly the missing three fields, verified byte-for-byte against the real `ADDRESS` layer's known field widths (`PFI` → 10, `EZI_ADDRESS` → 80).

A second class of finding is about exact-string fragility: pyogrio's `geometry_type` string for a 3D point is `'Point Z'` (with a space) — different from `ogrinfo`'s text-mode output (`'3D Point'`) and its own JSON-mode output (`'PointZ'`, no space). Any D-38 hard-stop check or Z/M-dimensionality branch must match against pyogrio's own string, not GDAL's other two spellings. Separately, `geometry_type is None` (Python `None`) is pyogrio's signal for a legitimate geometry-less table (D-35's selected non-spatial path) and must never be confused with `geometry_type == "Unknown"` (a string, D-38's hard stop) — both were independently verified against a synthetic `OpenFileGDB` built for this session.

Finally, a genuine cross-phase integration gap was found and must be surfaced to the planner: D-32 requires the manifest to record "the Phase 1 message fingerprint," but nothing in the current `vicmap_acquire`/`read_mailbox.py` code persists that fingerprint anywhere durable — it is only ever rendered to stdout inside `run_acquisition`'s local scope and then discarded. Phase 2 cannot read a value that was never written down.

**Primary recommendation:** Use `pyogrio.list_layers()` + `pyogrio.read_info()` for the bulk discovery pass (layers, feature counts, geometry type, CRS, capabilities), shell out to `ogrinfo -json` (from a new `pkgs.gdal` flake dependency) for the field width/precision/nullability that pyogrio's Python API does not expose, resolve CRS→EPSG with `pyproj.CRS.from_user_input(info["crs"]).to_epsg()`, and hand-roll zip member validation (reject-before-write) rather than trusting `zipfile.extractall()`'s silent-sanitization default.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Artifact checksum re-verification (D-28) | CLI / Orchestration (`read_mailbox.py`-style entry point) | Local Filesystem | Must happen before any extraction; pure comparison against Phase 1's reported values, no I/O beyond a hash of the existing artifact file. |
| Safe archive extraction (D-26) | Discovery Library (new `vicmap_acquire` module) | Local Filesystem (`runs/` tree) | Mirrors `download.py`'s streaming-with-ceiling pattern; the run directory is the write boundary being defended. |
| Layer/dataset enumeration and profiling (D-33/D-37/D-38/D-39/D-40) | Discovery Library | External process (GDAL `ogrinfo` CLI, invoked read-only) | pyogrio owns the primary read path; `ogrinfo -json` is a narrow, read-only supplemental subprocess for the one schema gap pyogrio's Python API leaves. |
| Target table naming and collision detection (D-21–D-24) | Discovery Library | — | Pure string/set logic, no I/O; explicitly never touches the database (D-23). |
| Manifest construction and persistence (D-29/D-31/D-32) | Discovery Library | Local Filesystem (`manifest.json` + sidecar) | Frozen in-process object is the Phase 3 API; the JSON file is the durable, hashable artifact. |
| Redacted operator evidence rendering | CLI / Orchestration | `vicmap_acquire/evidence.py` (extended) | Follows the exact `SuccessEvent`/`SafeFailure`/`_EmitOnce` pattern Phase 1 established; no new output mechanism. |
| Database connection, staging, publication | *(out of scope — Phase 3/4)* | — | Explicitly excluded from Phase 2 by the phase boundary; included here only to make the boundary visible. |

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `pyogrio` | 0.13.0 [VERIFIED: `nix eval github:NixOS/nixpkgs/nixos-unstable#python3.pkgs.pyogrio.version` → `0.13.0`, and confirmed importable/runnable against the real `VMADD.gdb` in a throwaway `nix-shell` this session] | Vectorized OGR-based layer listing, schema/CRS/feature-count introspection without materializing features (D-33). | Locked decision D-33; upstream geopandas project, actively maintained, GDAL-native OpenFileGDB support. |
| `pyproj` | 3.7.2 [VERIFIED: `nix eval github:NixOS/nixpkgs/nixos-unstable#python3.pkgs.pyproj.version` → `3.7.2`, confirmed `pyproj.CRS.from_user_input("EPSG:7899").to_epsg()` returns `7899` in a throwaway `nix-shell` this session] | Resolve a source CRS string/WKT to an integer EPSG code for D-39; provides the closed failure surface (`to_epsg()` returning `None`) for the hard-stop case. | The standard Python PROJ binding; already a transitive dependency of `pyogrio`/`gdal` in nixpkgs, so adding it explicitly costs nothing extra at the store level. |
| GDAL CLI (`pkgs.gdal`, providing `ogrinfo`) | 3.13.3 [VERIFIED: `nix build github:NixOS/nixpkgs/nixos-unstable#gdal` then `ls result/bin/` → contains `ogrinfo`, `ogr2ogr`, etc; version confirmed via `nix eval ...#gdal.version` → `3.13.3`] | Supplies field `width`/`precision`/`nullable` via `ogrinfo -json -al -so <path>`, which `pyogrio.read_info()` does not expose (see "The Field Width/Precision Gap" below). Also serves as the differential-oracle CLI for validation. | `pyogrio`'s compiled extension links GDAL at build time but does **not** propagate the `ogrinfo` binary at runtime (confirmed: `pyogrio`'s `propagatedBuildInputs` lists only `certifi`, `numpy`, `packaging`, `python3` — no `gdal`), so `pkgs.gdal` must be added to the devShell **separately** to get the CLI tools in `PATH`. |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `zipfile` (stdlib) | Python 3.14.7 [VERIFIED: `python3 --version` inside `nix develop path:. -c` this session] | Archive member enumeration (`infolist()`) and per-member streamed extraction. | Always — no new dependency needed, but **never** call `.extractall()` or `.extract()` directly without a pre-write validation pass (see Common Pitfalls). |
| `hashlib` (stdlib) | — | SHA-256 for D-28's artifact re-verification, D-27's companion-file checksums, and D-29's `manifest.json` sidecar digest. | Reuse the exact incremental-digest idiom already in `download.py` (`digest.update(chunk)` inside the same streamed-read loop that enforces the byte ceiling). |
| `json` (stdlib) | — | Canonical `manifest.json` serialization. | Reuse the exact idiom already in `evidence.py`: `json.dumps(payload, sort_keys=True, separators=(",", ":"))` [VERIFIED: `vicmap_acquire/evidence.py:363` — `stream.write(json.dumps(dict(event), sort_keys=True, separators=(",", ":")))`]. This is the one place in the existing codebase that already solves "deterministic/reproducible JSON for hashing," so Phase 2 should not invent a second convention. |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| pyogrio + `ogrinfo -json` subprocess | `osgeo.ogr` (GDAL Python bindings) for everything, including field width/precision | Rejected by D-33 for its C-style API and error-reporting style; also would give the *only* correct field-width answer through the Python bindings themselves rather than a subprocess, but at the cost of reintroducing the exact API surface D-33 rejected. Recorded here so the planner does not need to re-litigate it. |
| pyogrio + `ogrinfo -json` subprocess | `fiona` | Rejected by D-33 (weight, upstream focus shifted to pyogrio). |
| Hand-rolled zip member validation | Trusting `zipfile.extractall()`'s built-in path normalization | Verified insufficient for D-26: normalization *silently strips* dangerous components rather than rejecting the member, which is a "skip-and-continue," the exact failure mode D-26 forbids. |
| PostgreSQL reserved-word check as a hardcoded frozenset | Runtime `SELECT word FROM pg_get_keywords()` query | Phase 2 explicitly never opens a database connection (D-23's "Phase 2 never contacts the database"); the check must be a static, version-pinned list embedded in code. |

**Installation (flake.nix, `perSystem.packages`):**
```nix
packages = with pkgs; [
  git
  buildOpnix
  gdal  # provides ogrinfo/ogr2ogr CLI — NOT propagated by python3Packages.pyogrio
  (python3.withPackages (ps: [ python-o365 ps.html5lib ps.pyogrio ps.pyproj ]))
];
```

**Version verification:** Ran directly against `nixpkgs-unstable` (the flake's pinned input) via `nix eval` and a throwaway `nix-shell`/`nix build` this session — see per-package `[VERIFIED]` tags above. No PyPI/`pip` check was possible (`pip`/`pip3` are not installed in this environment; the project's only installation path is Nix), so registry cross-verification for the Package Legitimacy Audit below used the automated seam's PyPI lookup instead.

## Package Legitimacy Audit

| Package | Registry | Age | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|-----|-----------|-------------|---------|-------------|
| `pyogrio` | PyPI | latest release 2026-06-26 | unknown (seam could not retrieve a download count) | none returned by seam | `SUS` (`unknown-downloads`, `no-repository`) | Flagged — see note below |
| `pyproj` | PyPI | latest release 2026-09-05 | unknown (seam could not retrieve a download count) | `https://github.com/pyproj4/pyproj` | `SUS` (`too-new`, `unknown-downloads`) | Flagged — see note below |

**Packages removed due to `[SLOP]` verdict:** none.
**Packages flagged as suspicious `[SUS]`:** `pyogrio`, `pyproj` — the planner **must** add a `checkpoint:human-verify` task before either is added to `flake.nix`.

**Mitigating context the planner should weigh at that checkpoint (not a substitute for it):** Both packages were independently found in `nixpkgs-unstable`'s curated `python3Packages` set [VERIFIED via `nix eval`], both built and ran correctly from `cache.nixos.org`/`cache.numtide.com` binary caches in a throwaway shell this session, `pyproj`'s GitHub source repo (`pyproj4/pyproj`) is a well-known, long-running project that the seam itself found, and `pyogrio` is the primary vectorized-I/O library maintained under the `geopandas` GitHub organization. The seam's `SUS` reasons here (`unknown-downloads`, `too-new`, `no-repository`) look like artifacts of its PyPI metadata lookup rather than genuine slopsquat signals — a mature package's *latest point release* will always look "too new" by a recency heuristic, and the "no-repository" signal for `pyogrio` reflects a lookup gap, not an absent repo (its repo is `github.com/geopandas/pyogrio`, confirmed by this session's WebSearch results). None of this overrides the protocol: both packages are still `[ASSUMED]` until the operator's `checkpoint:human-verify` closes it, and the flake addition should cite `github.com/geopandas/pyogrio` and `github.com/pyproj4/pyproj` explicitly in that checkpoint.

## Architecture Patterns

### System Architecture Diagram

```
 artifacts/Order_{id}.zip (Phase 1 output, git-ignored)
            │
            ▼
 [1] Artifact re-verification (D-28)
     sha256(existing file) == Phase-1-reported sha256?
     byte_count == Phase-1-reported byte_count?
            │  no ──► SafeFailure(ARTIFACT_CHECKSUM_MISMATCH) [typed closed failure]
            │  yes
            ▼
 [2] Safe extraction (D-25/D-26)
     runs/{order_id}/.tmp-{utc_ts}/   (write here first)
       for each ZipInfo member (BEFORE any write):
         reject: absolute path / ".." component / drive-letter root
         reject: symlink or hardlink (external_attr Unix mode bits)
         reject: non-regular member (not S_IFREG / S_IFDIR)
         reject: resolved path escaping the temp run directory
         reject: declared or streamed bytes breaching per-member/
                 total/count/ratio ceilings from vicmap.toml
       stream each accepted member with a running SHA-256 (D-27)
            │  any guard trips ──► SafeFailure(ARCHIVE_*), temp dir left for inspection
            │  all members accepted
            ▼
     rename runs/{order_id}/.tmp-{utc_ts}/ → runs/{order_id}/{utc_ts}/   (atomic publish)
            │
            ▼
 [3] Format & layer discovery (D-33/D-34)
     pyogrio.list_layers(dataset_path) for each candidate dataset
       unlisted driver/format ──► SafeFailure(UNSUPPORTED_FORMAT)
            │
            ▼
 [4] Per-layer profiling (D-35–D-40)
     pyogrio.read_info(dataset, layer=name)
       ── feature_count, geometry_type, crs, fid_column, geometry_name, capabilities
     ogrinfo -json -al -so dataset  (subprocess, read-only)
       ── per-field width / precision / nullable  (the pyogrio gap)
     pyproj.CRS.from_user_input(info["crs"]).to_epsg()
       ── resolved EPSG code
     Hard-stop checks (any one fires SafeFailure, stops before manifest write):
       - layer fails to open                       → LAYER_UNREADABLE
       - features == 0                              → LAYER_EMPTY (D-36)
       - geometry_type == "Unknown"                  → GEOMETRY_TYPE_UNRESOLVED (D-38)
       - to_epsg() is None (only for spatial layers)  → CRS_UNRESOLVED (D-39)
       - any GEO-03 field missing                    → LAYER_SCHEMA_INCOMPLETE
            │
            ▼
 [5] Target table naming (D-21–D-24)
     normalize("{gdb_stem}_{layer}") for every discovered layer
       invalid charset / leading digit / reserved word / >63 bytes → TABLE_NAME_INVALID
       two layers normalize to the same name                        → TABLE_NAME_COLLISION
            │
            ▼
 [6] Manifest construction (D-29/D-31/D-32)
     frozen in-process ImportManifest object (Phase 3's API)
            │                       │
            ▼                       ▼
     manifest.json (full detail)   manifest.json.sha256 (sidecar digest)
     git-ignored, in run directory
            │
            ▼
 [7] Redacted operator evidence (SuccessEvent-style, stdout)
     order ID, layer/table-name pairs, counts, path fingerprints only
```

### Recommended Project Structure

```
vicmap_acquire/
├── __init__.py          # unchanged — no side effects on import
├── evidence.py          # extended: new Stage/ReasonCode members for extraction+discovery
├── candidates.py        # unchanged (Phase 1)
├── download.py          # unchanged (Phase 1) — DownloadResult is Phase 2's input contract
├── graph.py             # unchanged (Phase 1)
├── origin.py            # unchanged (Phase 1)
├── extraction.py        # NEW — D-25/D-26/D-27/D-28: safe zip extraction, ExtractionPolicy
├── discovery.py         # NEW — D-33..D-40: pyogrio + ogrinfo layer profiling
├── naming.py            # NEW — D-21..D-24: normalization, collision detection
└── manifest.py          # NEW — D-29/D-31/D-32: frozen manifest type + JSON serialization
```

Rationale for splitting into four new modules rather than one: `download.py` (609 lines) and `evidence.py` (376 lines) are the existing size precedents for "one policy/one concern per module" in this codebase; a single `discovery.py` covering extraction+profiling+naming+manifest would likely exceed 1500+ lines and mix concerns that have genuinely different failure vocabularies (archive safety vs. schema introspection vs. pure string normalization vs. serialization). This is a **recommendation**, not a locked decision — CONTEXT.md leaves module layout to Claude's discretion.

### Pattern 1: Reject-Before-Write Member Validation

**What:** Validate every `zipfile.ZipInfo` member against all D-26 guards *before* opening any output file handle for it — never call `ZipFile.extractall()` or `ZipFile.extract()` and rely on their built-in path handling.
**When to use:** Every extraction pass, no exceptions.
**Example:**
```python
# Verified this session by reading zipfile.py's ZipFile._extract_member
# source directly (Python 3.14.7, nix develop path:. shell) — CPython's own
# extractall() strips ".."/absolute-path components rather than rejecting
# the member. That is a silent rewrite, not a typed closed failure, so D-26
# requires this hand-rolled pass to run first.
import os
import stat
import zipfile

_S_IFMT_REGULAR = {stat.S_IFREG, stat.S_IFDIR}

def _reject_unsafe_member(info: zipfile.ZipInfo, run_dir_resolved: "Path") -> None:
    name = info.filename
    if name.startswith("/") or name.startswith("\\"):
        raise ArchiveTraversalRejected()
    parts = name.replace("\\", "/").split("/")
    if any(part in ("..",) for part in parts) or any(":" in part for part in parts):
        raise ArchiveTraversalRejected()

    # external_attr's upper 16 bits are only meaningful when the archive was
    # written on a Unix system (create_system == 3); Windows-authored zips
    # carry only DOS attribute bits there.
    if info.create_system == 3:
        unix_mode = (info.external_attr >> 16) & 0o170000
        if unix_mode == stat.S_IFLNK:
            raise ArchiveUnsafeMemberRejected()  # symlink
        if unix_mode not in (0, stat.S_IFREG, stat.S_IFDIR):
            raise ArchiveUnsafeMemberRejected()  # device/FIFO/socket/etc.

    if info.flag_bits & 0x1:
        raise ArchiveUnsafeMemberRejected()  # encrypted member — never expected

    resolved = (run_dir_resolved / "/".join(parts)).resolve()
    if run_dir_resolved not in resolved.parents and resolved != run_dir_resolved:
        raise ArchiveTraversalRejected()
```

### Pattern 2: Streamed Extraction with Byte-Ceiling Enforcement (mirrors `download.py`)

**What:** Reuse the exact chunked-read-with-running-counter idiom `download_artifact` already uses for `DownloadTooLarge`, applied per zip member and cumulatively across the archive.
**When to use:** Every member write, so a member whose *actual* decompressed byte stream exceeds either its own declared `file_size` or the configured per-member/total ceiling is caught while streaming — not just from trusting the central-directory-declared `file_size` up front (declared and actual can, in principle, diverge; the ceiling must be enforced against the bytes actually produced by decompression, exactly as `download.py`'s ceiling is enforced against bytes actually received off the socket, not the `Content-Length` header alone).
**Example:**
```python
# Source: vicmap_acquire/download.py:549-579 (read this session) — the
# existing chunked-write-with-digest-and-ceiling loop this pattern mirrors:
#   for chunk in response.iter_content(chunk_size=1024 * 1024):
#       ...
#       next_count = received + len(chunk)
#       if next_count > policy.max_bytes:
#           raise DownloadTooLarge()
#       written = output.write(chunk)
#       ...
#       digest.update(chunk)
#       received = next_count
with zip_file.open(member, "r") as source, open(target_path, "wb") as target:
    member_received = 0
    digest = hashlib.sha256()
    while chunk := source.read(1024 * 1024):
        member_received += len(chunk)
        if member_received > policy.max_member_bytes:
            raise ArchiveCeilingExceeded()
        total_received += len(chunk)
        if total_received > policy.max_total_bytes:
            raise ArchiveCeilingExceeded()
        target.write(chunk)
        digest.update(chunk)
    if member.compress_size and member_received / member.compress_size > policy.max_compression_ratio:
        raise ArchiveCeilingExceeded()
```

### Pattern 3: pyogrio + `ogrinfo -json` Combined Layer Profile

**What:** `pyogrio.read_info()` for the fast/bulk metadata pyogrio does expose; a single `ogrinfo -json -al -so` subprocess call per dataset for the field width/precision/nullable pyogrio does not expose. `-so` (summary-only) avoids the full-geometry scan, keeping the call as cheap as pyogrio's own header-count path.
**When to use:** Once per discovered dataset (not per layer — `ogrinfo -al` already enumerates every layer's fields in one process invocation).
**Example — verified output shape, run against the real `VMADD.gdb` this session:**
```python
# pyogrio.read_info() output for the real ADDRESS layer (verified this
# session, values exactly as returned):
#   {'layer_name': 'ADDRESS', 'crs': 'EPSG:7899', 'fields': array([...]),
#    'geometry_type': 'Point', 'features': 4222035, 'fid_column': 'OBJECTID',
#    'geometry_name': 'SHAPE', 'driver': 'OpenFileGDB',
#    'capabilities': {'fast_feature_count': True, ...}}
import json
import subprocess

def read_field_schema(dataset_path: str) -> dict[str, list[dict]]:
    """Return {layer_name: [{"name", "type", "width"?, "precision"?, "nullable"}]}."""
    result = subprocess.run(
        ["ogrinfo", "-json", "-al", "-so", dataset_path],
        capture_output=True, text=True, timeout=60, check=True,
    )
    payload = json.loads(result.stdout)
    return {layer["name"]: layer["fields"] for layer in payload["layers"]}

# Verified this session against the real ADDRESS layer:
#   {'name': 'PFI', 'type': 'String', 'width': 10, 'nullable': True, 'uniqueConstraint': False}
#   {'name': 'EZI_ADDRESS', 'type': 'String', 'width': 80, 'nullable': True, 'uniqueConstraint': False}
#   {'name': 'UFI', 'type': 'Integer', 'nullable': True, 'uniqueConstraint': False}   # no width key
```

### Pattern 4: CRS → EPSG Resolution with an Explicit Failure Boundary

**What:** `pyogrio`'s own `crs` field is already `"EPSG:<code>"` when GDAL can identify an exact authority match, and the full WKT string otherwise (both forms verified this session). Feed either form into `pyproj.CRS.from_user_input(...).to_epsg()`; treat `None` as D-39's hard stop.
**Example:**
```python
import pyproj

def resolve_epsg(crs_field: str | None) -> int:
    if crs_field is None:
        raise CrsUnresolved()  # geometry-less layer should never reach this call
    epsg = pyproj.CRS.from_user_input(crs_field).to_epsg()
    if epsg is None:
        raise CrsUnresolved()  # D-39 hard stop — verified: a LOCAL_CS with no
                                # authority match returns to_epsg() == None,
                                # even at min_confidence=20
    return epsg
```

### Anti-Patterns to Avoid

- **Calling `ZipFile.extractall()` "for convenience" and trusting its defaults:** verified this session (direct read of CPython 3.14's `zipfile.py`) that `_extract_member` *silently strips* `..`/drive-letter/root components rather than raising — this is a silent rewrite, precisely the "skip-and-continue" behavior D-26 forbids. Always pre-validate every member's raw `filename` yourself.
- **Assuming `geometry_type == "Unknown"` and `geometry_type is None` mean the same thing:** verified this session that pyogrio returns Python `None` for a genuinely geometry-less table (D-35's legitimate non-spatial path) and the *string* `"Unknown"` for a driver's generic/unresolvable geometry declaration (D-38's hard stop). Conflating these either wrongly hard-stops a valid lookup table or wrongly accepts an unusable geometry declaration.
- **Assuming every field will carry a `width`:** verified this session against both the real `ADDRESS` layer and a synthetic OpenFileGDB that `ogrinfo -json`'s field entries only include a `"width"` key for `String` fields — `Integer`, `Real`, and `DateTime` fields in OpenFileGDB never carry it (confirmed even when the source data was explicitly `CAST` to `numeric(10,3)`, which *does* produce a `precision` key on Shapefile's DBF-backed field but produced none at all on OpenFileGDB). A schema validator that requires `width`/`precision` on every field will hard-stop on a perfectly valid delivery.
- **Matching geometry-type strings against the wrong tool's vocabulary:** verified this session that the *same* 3D-point layer is described as `'Point Z'` by `pyogrio.read_info()`, `'PointZ'` by `ogrinfo -json`, and `'3D Point'` by `ogrinfo`'s plain-text mode — three different spellings from the same underlying GDAL install. Any D-38 string match must be against whichever tool actually produced the value in that code path.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| OGR field type / geometry type / CRS enumeration | A custom `.gdb` binary-format parser | `pyogrio.read_info()` / `list_layers()` | D-33; verified working against the real delivery this session; GDAL's OpenFileGDB driver already handles Esri's undocumented on-disk format correctly. |
| Field width/precision/nullability | Parsing `ogrinfo`'s human-readable text output with regex | `ogrinfo -json` structured output | Verified this session that `-json` gives a stable, parseable dict shape (`{"name", "type", "width"?, "precision"?, "nullable"}`) whereas the text mode's `Real (10.3)` / `String (0.0)` formatting is meant for humans, not machines. |
| CRS string → EPSG code mapping | Regex-matching `AUTHORITY["EPSG","7899"]` out of raw WKT | `pyproj.CRS.from_user_input(...).to_epsg()` | pyproj already handles WKT1/WKT2/PROJJSON/`AUTHORITY:CODE`-string inputs uniformly and gives an explicit `None` failure signal; a regex breaks the moment a driver emits WKT2 without a trailing `ID[...]` node or uses a different authority. |
| PostgreSQL reserved-word detection | A short hand-typed list of "common" reserved words (`select`, `table`, `from`, ...) | The **complete** PostgreSQL keyword-appendix list, both the `Reserved` and `Reserved (can be function or type)` categories | Verified via the official docs [CITED: postgresql.org/docs/current/sql-keywords-appendix.html] that PostgreSQL's own classification has *four* categories, and **two** of them (not just the one literally labeled "reserved") block unquoted use as a table name. A hand-typed shortlist reliably misses words like `binary`, `concurrently`, `cross`, or `current_schema` that fall in the second, easy-to-miss category. |
| Zip-bomb / traversal defense | Assuming Python 3.12's `tarfile` PEP 706 `filter="data"` protection also applies to `zipfile` | Hand-rolled member validation (Pattern 1/2 above) | Verified via the PEP 706 discussion itself [CITED: peps.python.org/pep-0706, discuss.python.org/t/pep-706-filter-for-tarfile-extractall/23903] that the filter mechanism is `tarfile`-only; the PEP's own rationale explicitly says filters "would probably not help" `zipfile` security because `zipfile` has no equivalent hook at all. |

**Key insight:** every "don't hand-roll" item above is really the same lesson from a different angle: GDAL/OGR and PostgreSQL both already encode decades of edge-case handling (obscure geometry subtypes, locale-dependent keyword lists, Esri's undocumented FileGDB internals) that a from-scratch reimplementation would silently get wrong on inputs this codebase hasn't seen yet. The one place hand-rolling is *correct* — zip member validation — is precisely the one place no standard library or well-known package offers a "safe extract" button for `zipfile` at all.

## Common Pitfalls

### Pitfall 1: Trusting `zipfile`'s Default Extraction as "Safe Enough"
**What goes wrong:** A traversal or absolute-path member is silently rewritten into something harmless-looking instead of the run failing closed, masking a malformed or malicious delivery instead of stopping the pipeline (violates D-26's explicit "never a skip-and-continue").
**Why it happens:** `ZipFile.extractall()`/`.extract()` do real, working path sanitization (confirmed by reading the source this session) — it just isn't the sanitization D-26 asks for. It's easy to assume "the stdlib handles this" because it partially does.
**How to avoid:** Validate every `ZipInfo.filename` and `external_attr`/`flag_bits` against the guard list in Pattern 1 *before* calling anything that writes bytes; never call `extractall()`/`extract()` in production code.
**Warning signs:** A test asserting "an archive with a `../../etc/passwd` member extracts successfully to a sanitized path inside the run directory" — that is the exact bug this pitfall describes, disguised as passing behavior.

### Pitfall 2: The `create_system` Byte Determines Whether `external_attr` Means Anything
**What goes wrong:** Symlink detection via `(external_attr >> 16) & 0o170000 == stat.S_IFLNK` silently never fires for archives authored on Windows, because `external_attr`'s upper 16 bits only carry Unix mode bits when `ZipInfo.create_system == 3`.
**Why it happens:** The zip format stores `external_attr`'s meaning per-entry, tagged by the authoring OS; most zip-safety code examples online assume Unix-authored archives.
**How to avoid:** Check `info.create_system == 3` before interpreting the upper 16 bits of `external_attr` as Unix mode bits (Pattern 1 does this). On `create_system != 3`, symlink/hardlink attacks are structurally impossible via that vector (Windows zips can't encode a Unix symlink bit), but non-regular-member and traversal checks still apply unconditionally.
**Warning signs:** A symlink-rejection test only ever constructs its fixture zip with `zipfile.ZipInfo` defaults (which set `create_system` based on the *test-running* platform) — this can accidentally validate the wrong branch depending on CI OS.

### Pitfall 3: `read_info()`'s `geometry_type` Vocabulary Is Driver- and Tool-Dependent
**What goes wrong:** A D-38 hard-stop check written against `"Unknown"` (correct, pyogrio's own vocabulary) accidentally gets copy-pasted into a debug/manual `ogrinfo`-based cross-check as `"3D Point"` or `"PointZ"` and the two tools silently disagree.
**Why it happens:** Verified this session: the *same* GDAL install reports the same geometry through three different string spellings depending on entry point (`pyogrio.read_info()` → `'Point Z'`; `ogrinfo -json` → `'PointZ'`; `ogrinfo` plain text → `'3D Point'`).
**How to avoid:** Never compare geometry-type strings across tools. If a differential-oracle test cross-checks pyogrio's discovery output against `ogrinfo`, normalize both sides to a shared vocabulary (e.g., strip whitespace and casefold, or compare only the base type + a separately-extracted Z/M boolean) rather than comparing raw strings.
**Warning signs:** A cross-check test that only ever exercises 2D geometries will never catch this; it only surfaces once a Z/M-dimensioned layer appears in a real delivery.

### Pitfall 4: Field Width Absence Is Normal, Not an Error
**What goes wrong:** A schema-completeness check (part of D-36's "missing anything GEO-03 promises") that requires every field entry to have a non-null `width` will hard-stop on every valid `Integer`/`Real`/`DateTime` field in an OpenFileGDB delivery, because none of them carry a `width` key at all.
**Why it happens:** DBF-backed formats (Shapefile) genuinely store width/precision per numeric field; OpenFileGDB's binary format does not need to (fixed-size doubles/int32s), so GDAL has nothing to report.
**How to avoid:** Treat `width`/`precision` as present-when-applicable, not required-for-every-field. D-36's "missing anything GEO-03 promises" should be read as "the field's *name*, *type*, and *nullability* must always be present; width/precision are captured when the driver supplies them."
**Warning signs:** Discovery hard-stops on the real `ADDRESS` layer itself — that layer's own `UFI` (Integer) and `SOURCE_VERIFIED` (DateTime) fields carry no width, verified this session.

### Pitfall 5: The Phase 1 → Phase 2 Message-Fingerprint Handoff Does Not Currently Exist
**What goes wrong:** D-32 requires the manifest to record "the Phase 1 message fingerprint" alongside the artifact SHA-256, but nothing in the current codebase persists that value anywhere Phase 2 could read it after Phase 1's process has exited.
**Why it happens:** Verified this session by reading `read_mailbox.py` end-to-end and grepping the whole package for `message_fingerprint`/`provenance`/`.json`: the fingerprint is constructed inside `run_acquisition`'s local scope, passed only into `SuccessEvent.candidate_selected(...)`, and rendered to stdout by `render_event`/`render_success` — never returned from `run_acquisition` (whose return type is `DownloadResult`, which has no message-related field) and never written to any file.
**How to avoid:** This must be resolved as part of Phase 2's planning, not silently assumed away. See "Open Questions" below for the two concrete resolution paths.
**Warning signs:** A plan that writes `manifest_data["phase1_message_fingerprint"] = <some placeholder>` without a task that actually sources that value from somewhere durable is masking this gap rather than resolving it.

## Code Examples

### Verified pyogrio Output for the Real Delivery (`VMADD.gdb`/`ADDRESS`)
```python
# Ran this session via: nix-shell (pkgs.python3.withPackages (ps: [ps.pyogrio ps.pyproj]))
# against artifacts/Order_OK0VUZ.zip, extracted to a scratch directory.
import pyogrio

pyogrio.list_layers("gda2020_vicgrid/filegdb/whole_of_dataset/victoria/VMADD.gdb")
# -> array([['ADDRESS', 'Point']], dtype=object)

info = pyogrio.read_info(
    "gda2020_vicgrid/filegdb/whole_of_dataset/victoria/VMADD.gdb", layer="ADDRESS"
)
# info["crs"]            -> 'EPSG:7899'
# info["geometry_type"]  -> 'Point'
# info["features"]       -> 4222035
# info["fid_column"]     -> 'OBJECTID'
# info["geometry_name"]  -> 'SHAPE'
# info["driver"]         -> 'OpenFileGDB'
# info["capabilities"]   -> {'random_read': True, 'fast_set_next_by_index': True,
#                             'fast_spatial_filter': True, 'fast_feature_count': True,
#                             'fast_total_bounds': True}
# info["total_bounds"]   -> (2126780.196697009, 2259755.3506347165,
#                            2934322.982014683, 2826389.7540394757)
```
These four numbers (`4222035` features, `EPSG:7899`, `'Point'`, the exact bounds tuple) match CONTEXT.md's specifics section exactly, cross-confirming both this session's methodology and CONTEXT.md's own ground-truth numbers.

### Verified `ogrinfo -json` Field Schema for the Same Layer
```json
{
  "name": "PFI", "type": "String", "width": 10, "nullable": true, "uniqueConstraint": false
}
```
```json
{
  "name": "EZI_ADDRESS", "type": "String", "width": 80, "nullable": true, "uniqueConstraint": false
}
```
```json
{
  "name": "UFI", "type": "Integer", "nullable": true, "uniqueConstraint": false
}
```
(`UFI` has no `"width"` key — see Pitfall 4.) Full field list has 40 attribute fields (`ogrinfo -json` `fields` array length verified this session); `featureCount` in the same JSON payload independently reports `4222035`, matching pyogrio's count exactly.

### Verified Zip Archive Shape (Real Delivery)
```python
# import zipfile; zf = zipfile.ZipFile("artifacts/Order_OK0VUZ.zip")
# Verified this session:
#   len(zf.infolist())                         -> 46
#   sum(i.file_size for i in zf.infolist())     -> 974603864   (uncompressed)
#   sum(i.compress_size for i in zf.infolist()) -> 233078083   (compressed)
#   overall ratio                               -> ~4.1814x
#   largest single member (a00000009.gdbtable)  -> 902311023 bytes uncompressed,
#                                                   ratio ~4.261x
#   every member's mode                         -> 0o100666 (S_IFREG, no symlinks,
#                                                   no traversal, no absolute paths)
```
This is the calibration data for the D-26 ceiling defaults recommended below.

### Canonical JSON Serialization for `manifest.json` (reuse the existing idiom)
```python
# Source: vicmap_acquire/evidence.py:360-364 (read this session) — the
# existing, only precedent for "deterministic JSON for hashing" in this repo:
#   def _render(event, expected_type, stream):
#       ...
#       stream.write(json.dumps(dict(event), sort_keys=True, separators=(",", ":")))
#       stream.write("\n")
import hashlib
import json

def write_manifest(payload: dict, manifest_path, sidecar_path) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    manifest_path.write_text(canonical + "\n", encoding="utf-8")
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    sidecar_path.write_text(digest + "\n", encoding="utf-8")  # e.g. manifest.json.sha256
    return digest
```
Note: a file cannot embed its own hash, so D-29's "with its own SHA-256 recorded alongside it" is satisfied literally — as a sidecar file, not a self-referential field inside `manifest.json`.

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|---------------|--------|
| `osgeo.ogr`/`fiona` for vectorized GDAL access in Python | `pyogrio` | Ongoing since ~2022; geopandas itself now defaults to pyogrio as its I/O engine | Faster, array-oriented reads and a cleaner metadata-only API (`read_info`), at the cost of not exposing every low-level OGR field-defn attribute (see the width/precision gap this research found). |
| `tarfile.extractall()` without a filter | `tarfile.extractall(filter="data")` (Python 3.12+, default in 3.14) | PEP 706, default flipped in 3.14 [CITED: peps.python.org/pep-0706] | Not directly applicable here — the real delivery is a `.zip`, and `zipfile` never received an equivalent filter argument, which is exactly why D-26 requires hand-rolled validation. |

**Deprecated/outdated:**
- Treating `zipfile.extractall()`'s built-in `..`/absolute-path stripping as sufficient "safe extraction": it is real behavior, verified this session, but it fails D-26's "typed closed failure, never skip-and-continue" bar because it silently rewrites rather than rejects.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Recommended D-26 ceiling defaults (max_total_uncompressed_bytes, max_member_uncompressed_bytes, max_member_count, max_compression_ratio) — see below | Architecture Patterns / Standard Stack | If set too tight, a legitimately larger future delivery hard-stops unnecessarily; if too loose, the ceiling stops protecting against a real zip bomb. These are explicitly "Claude's discretion" defaults per CONTEXT.md, calibrated off one real delivery. |
| A2 | Recommended UTC run-directory timestamp format `YYYYMMDDTHHMMSSZ` (e.g. `20260914T064512Z`) | Architecture Patterns | Cosmetic only — any lexicographically-sortable, filesystem-safe format satisfies CONTEXT.md's stated constraint; this is one reasonable choice among several. |
| A3 | Recommended module split (`extraction.py`/`discovery.py`/`naming.py`/`manifest.py`) | Recommended Project Structure | Purely organizational; CONTEXT.md explicitly leaves this to discretion. Wrong choice costs a refactor, not correctness. |
| A4 | Proposed new `Stage`/`ReasonCode` enum member names (`ARTIFACT_VERIFY`, `EXTRACTION`, `DISCOVERY`, `MANIFEST` stages; `ARTIFACT_CHECKSUM_MISMATCH`, `ARCHIVE_TRAVERSAL_REJECTED`, etc.) | Common Pitfalls / Architecture Patterns | Naming only, not behavior; must still satisfy `reason_stage_vocabulary()`'s completeness contract once added, but the exact spelling is free to change during planning/execution. |
| A5 | `pyogrio`/`pyproj` `[SUS]` package-legitimacy verdicts are metadata-lookup artifacts rather than genuine slopsquat risk | Package Legitimacy Audit | If wrong, a supply-chain-compromised package could be added to `flake.nix`; this is exactly why the protocol still requires a `checkpoint:human-verify` regardless of this session's mitigating context — the assumption does not skip that gate. |
| A6 | `pyogrio`'s `geometry_type` string for ZM-dimensioned geometries follows the same `'<Base> Z'`/`'<Base> M'`/`'<Base> ZM'` pattern verified for `'Point Z'` | Common Pitfalls (Pitfall 3) | Only the `Z` case was directly tested this session (no `M`- or `ZM`-dimensioned fixture was built); if the pattern differs for `M`/`ZM`, a D-38 string-based hard-stop check written from this pattern could either over- or under-match on an `M`-dimensioned delivery. Low real-world risk since Vicmap deliveries are XY/XYZ, not measured geometries, but flagged for completeness. |

## Open Questions (RESOLVED)

*Both questions were closed during the `/gsd-plan-phase 02` run that consumed this research. Markers below record how.*

1. **RESOLVED — How does the manifest obtain "the Phase 1 message fingerprint" (D-32)?**
   > **Resolution:** the operator chose option (a). Phase 1's artifact publication now writes a durable `artifacts/Order_{id}.provenance.json` sidecar (`order_id`, `message_fingerprint`, `sha256`, `byte_count`) using `download.py`'s existing atomic publish idiom, and Phase 2 reads it as required input. Implemented by `02-02-PLAN.md` Task 1 (sidecar write, plus a `--provenance-only` backfill mode) and wired as a precondition in `02-02` Task 2 / `02-06` Task 3.
   - What we know: verified this session that `run_acquisition` computes this fingerprint locally and only ever renders it to stdout; it is never returned or persisted to a file.
   - What's unclear: whether the intended fix is (a) a small Phase-2-scoped amendment to `read_mailbox.py`/`vicmap_acquire` that writes a durable sidecar (e.g. `artifacts/Order_{id}.provenance.json` containing `{order_id, message_fingerprint, sha256, byte_count}`) at the moment Phase 1 publishes the artifact, or (b) something else the operator intends that this research did not anticipate.
   - Recommendation: the plan should include an explicit task that either (a) extends `DownloadResult`/`run_acquisition` to persist this value durably (smallest, most consistent-with-existing-patterns fix — mirrors the same atomic-publish idiom `_publish_artifact` already uses), or confirms with the operator that D-32 should be read as "record it if available, omit if not" for this first delivery. Do not let a plan silently invent a fingerprint value or skip the field without flagging it.

2. **RESOLVED (for planning) — Does `ogrinfo`'s JSON schema reliably include `"precision"` for every driver/type combination that matters, or only for DBF-backed (Shapefile) numeric fields?**
   - What we know: verified this session that Shapefile's `Real` fields report both `width` and `precision`; OpenFileGDB's `Real`/`Integer` fields report neither, even when explicitly cast to a specific numeric(width,precision) during test-fixture creation.
   - What's unclear: whether this is because OpenFileGDB genuinely has no precision concept for these types (most likely, since it stores native IEEE-754 doubles/int32s) or because the specific `ogr2ogr -sql CAST(...)` test performed this session failed to apply the cast as intended.
   - **Resolution:** accepted as resolved for planning purposes; Pitfall 4's guidance (do not require width/precision universally) is what the plans build against, with the re-check carried forward as a flagged follow-up for a future delivery rather than a blocker.
   - Recommendation: treat this as resolved for planning purposes (Pitfall 4 already captures the practical guidance: don't require width/precision universally), but flag it so the executor validates against a second real Vicmap delivery if/when one becomes available, in case a future dataset ships a driver/type combination not seen in this session's testing.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|--------------|-----------|---------|----------|
| `pyogrio` (Python, via Nix) | D-33 discovery | ✗ (not yet in `flake.nix`) | 0.13.0 available in `nixpkgs-unstable` [VERIFIED] | none — must be added to `flake.nix`; this is exactly what D-33 already calls for |
| `pyproj` (Python, via Nix) | D-39 CRS resolution | ✗ (not yet in `flake.nix`) | 3.7.2 available in `nixpkgs-unstable` [VERIFIED] | none — must be added to `flake.nix` |
| GDAL CLI (`ogrinfo`) via `pkgs.gdal` | Field width/precision/nullable supplement (Pattern 3), differential-oracle testing | ✗ in the flake devShell (present at `/home/brendon/.nix-profile/bin/ogrinfo`, GDAL 3.12.4, on the **operator's ambient profile only** — not reproducible for anyone else running `nix develop`) | 3.13.3 available in `nixpkgs-unstable` as `pkgs.gdal` [VERIFIED — built and confirmed `result/bin/ogrinfo` exists] | none acceptable long-term — the devShell must not silently depend on the operator's ambient profile; add `pkgs.gdal` explicitly |
| `python3` (Nix-provided interpreter) | Everything | ✓ | 3.14.7 [VERIFIED] | — |
| PostgreSQL client / server | none this phase | n/a | — | Phase 2 explicitly never opens a database connection (D-23); no dependency to audit here. |

**Missing dependencies with no fallback:**
- `pyogrio`, `pyproj`, and `pkgs.gdal` (for `ogrinfo`) must all be added to `flake.nix`'s devShell before any Phase 2 code can run inside `nix develop`. This is a Wave 0 blocker for the plan, not optional polish.

**Missing dependencies with fallback:**
- None — the GDAL CLI reachable today only via the operator's ambient profile is exactly the kind of hidden, non-reproducible dependency `flake.nix`'s whole purpose is to eliminate; it must be added explicitly rather than relied upon.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | Python stdlib `unittest` [VERIFIED: `tests/__init__.py`, `01-*-PLAN.md`/`01-*-SUMMARY.md` files, and `tests/test_download.py`'s `import unittest` — all read this session] |
| Config file | none — `unittest discover` with default conventions |
| Quick run command | `nix develop path:. -c python -m unittest tests.test_<new_module> -v` |
| Full suite command | `nix develop path:. -c python -m unittest discover -s tests -p 'test_*.py' -v` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|---------------------|-------------|
| GEO-01 | Traversal/`..`/absolute-path/symlink/hardlink/non-regular member rejected before any write; ceiling breaches rejected while streaming, not just from declared metadata | unit, synthetic in-memory zip fixtures (`zipfile.ZipFile(io.BytesIO(), "w")`) | `nix develop path:. -c python -m unittest tests.test_extraction -v` | ❌ Wave 0 |
| GEO-02 | Every layer in a dataset is discovered; unsupported format is a named typed failure; a geometry-less table is discovered and selected, not skipped | unit, tiny synthetic OpenFileGDB fixtures built via `ogr2ogr` (proven this session — a few-row GDB is a handful of KB) | `nix develop path:. -c python -m unittest tests.test_discovery -v` | ❌ Wave 0 |
| GEO-03 | Fields (name/type/width/precision/nullable), exact feature count, geometry type (incl. Z/M), and resolved EPSG are all captured correctly, including the width-absence case (Pitfall 4) and the `None`-vs-`"Unknown"` geometry distinction (Pitfall 3) | unit + **differential oracle** against `ogrinfo -json` (see below) | `nix develop path:. -c python -m unittest tests.test_discovery tests.test_discovery_differential -v` | ❌ Wave 0 |
| GEO-04 | `{gdb_stem}_{layer}` normalization is deterministic and visible before any DB work; reserved-word/charset/length/leading-digit checks are correct against the *actual* PostgreSQL keyword categories (not a hand-typed shortlist — see Don't Hand-Roll) | unit, pure function, no fixtures needed | `nix develop path:. -c python -m unittest tests.test_naming -v` | ❌ Wave 0 |
| GEO-05 | Unreadable dataset, empty layer, unresolved geometry type, unresolved CRS, and same-delivery name collision all hard-stop **before** `manifest.json` is written | unit, both the individual guard functions and an end-to-end "manifest never gets written" assertion | `nix develop path:. -c python -m unittest tests.test_discovery tests.test_naming tests.test_manifest -v` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `nix develop path:. -c python -m unittest <touched test modules> -v`
- **Per wave merge:** `nix develop path:. -c python -m unittest discover -s tests -p 'test_*.py' -v`
- **Phase gate:** Full suite green before `/gsd-verify-work`, plus one opt-in live check against the real `artifacts/Order_OK0VUZ.zip` (see below), mirroring Phase 1's `01-11`/`01-13`/`01-14`-style opt-in live-proof pattern.

### Wave 0 Gaps
- [ ] `tests/test_extraction.py` — GEO-01, built entirely on synthetic in-memory zip fixtures (traversal, symlink, hardlink, non-regular member, ceiling breach — declared-metadata and streamed-bytes variants both, per the "declared vs. actual" pitfall noted in Pattern 2).
- [ ] `tests/test_discovery.py` — GEO-02/GEO-03, built on tiny synthetic OpenFileGDB fixtures generated via `ogr2ogr` (the exact recipe proven this session: a small CSV with a `WKT` column, `ogr2ogr -f OpenFileGDB out.gdb in.csv -oo GEOM_POSSIBLE_NAMES=WKT -nlt POINT -a_srs EPSG:xxxx`, and `-nlt NONE -oo GEOM_POSSIBLE_NAMES=DISABLE` for a geometry-less table). Fixtures should be pre-generated and checked into `tests/fixtures/` as small binary blobs, since `ogr2ogr` will not necessarily be on every future test-runner's `PATH` unless `pkgs.gdal` is in the devShell (which it now needs to be anyway, per Environment Availability).
- [ ] `tests/test_discovery_differential.py` — an **independent-oracle** test in the style of `tests/test_html_visibility_differential.py` [pattern verified this session; also matches the MEMORY.md guidance "hand-written tests share the code's blind spot; use an independent oracle for parsing/visibility logic"]: run the Phase 2 discovery module against the same fixture (or, opt-in, the real `VMADD.gdb`) and independently invoke `ogrinfo -json` directly in the test, asserting the two agree on feature count, field names/types, and (after vocabulary normalization per Pitfall 3) geometry type and EPSG — without importing any of the implementation's own parsing helpers, exactly as the HTML-visibility differential test never imports `_walk_visible` from `candidates.py`.
- [ ] `tests/test_naming.py` — GEO-04, pure-function tests against a real, version-pinned PostgreSQL reserved-word snapshot (both "Reserved" and "Reserved (can be function or type)" categories per the Don't Hand-Roll finding), including at least one word from each category that a hand-typed shortlist would plausibly miss (e.g. `binary`, `concurrently`).
- [ ] `tests/test_manifest.py` — GEO-05's "hard-stop before manifest write" property, plus the `manifest.json` sidecar-hash round-trip (write, re-hash, compare).
- [ ] Framework install: none — `unittest` is stdlib; no new test dependency needed.
- [ ] Opt-in live check (not part of the deterministic suite, mirrors Phase 1's `OPNIX_ENV_DISABLE=1`-gated live tests): run full discovery against `artifacts/Order_OK0VUZ.zip` when present on disk, and assert the exact verified values from this research (`4222035` features, `EPSG:7899`, `'Point'`, target table `vmadd_address`) — this is the same file this session used to derive those numbers, so it doubles as a regression fixture for "did a future pyogrio/GDAL upgrade change these answers."

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|----------------|---------|-------------------|
| V12 Files and Resources [CITED: github.com/OWASP/ASVS v4.0.3, `0x20-V12-Files-Resources.md`] | yes | 12.3-style path-traversal control: validate every archive member's path against the extraction root before any write (Pattern 1); reject, never sanitize-and-continue. |
| V5 Input Validation | yes | `vicmap.toml`'s new extraction/discovery section(s) follow the exact closed-set, explicitly-validated-key pattern `_MAILBOX_KEYS`/`_DOWNLOAD_KEYS` already establish in `read_mailbox.py` [VERIFIED: `read_mailbox.py:42-61`, `444-451`]. |
| V6 Cryptography | yes (narrow) | SHA-256 via stdlib `hashlib` only, reusing the exact incremental-digest idiom already in `download.py` — never a hand-rolled hash or a weaker algorithm for the D-28/D-29 provenance chain. |
| V2 Authentication / V3 Session Management | no | Phase 2 opens no network connection and no database session; out of scope by the phase boundary itself. |
| V4 Access Control | no | No database, no roles, no privilege boundary in this phase (deferred to Phase 3/4's `DB-02`/`PUB-04`). |

### Known Threat Patterns for This Phase's Stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|----------------------|
| Zip Slip (path traversal via crafted member names) | Tampering | Pattern 1's reject-before-write validation; verified this session that `zipfile`'s own defaults only *mitigate*, not *reject*, this. |
| Zip bomb (extreme compression ratio / member count / total size) | Denial of Service | Pattern 2's streamed byte-ceiling enforcement against actual decompressed bytes, not just declared central-directory metadata; ceilings calibrated against the real delivery's ~4.2× ratio with generous headroom (see A1). |
| Symlink/hardlink member pointing outside the run directory | Tampering / Information Disclosure | Reject any non-regular member outright (Pattern 1); do not attempt to resolve-and-allow symlinks that happen to stay inside the run directory — D-26 says reject symlinks unconditionally. |
| Table-name collision or invalid identifier reaching `CREATE TABLE` in a later phase | Tampering (of the target schema) | GEO-05's hard stop before any manifest is written, using the full PostgreSQL reserved-word categorization (Don't Hand-Roll) rather than a partial list. |
| Untrusted CRS/geometry metadata silently coerced into a guessed value | Tampering (of published spatial data's correctness) | D-38/D-39's explicit hard-stops on `"Unknown"` geometry and unresolved EPSG — no guessing, no default SRID. |

## Sources

### Primary (HIGH confidence — verified this session against the real delivery and/or read source directly)
- `nix eval`/`nix build` against `github:NixOS/nixpkgs/nixos-unstable` — confirmed `pyogrio` 0.13.0, `pyproj` 3.7.2, `gdal` 3.13.3 (with `bin/ogrinfo`), and `python3` 3.14.7 all resolve and build.
- A throwaway `nix-shell` running `pyogrio.list_layers()`/`read_info()` and `pyproj.CRS.from_user_input(...).to_epsg()` directly against the real `artifacts/Order_OK0VUZ.zip` (extracted to a scratch directory this session).
- `ogrinfo -json -al -so` run directly against the same real `VMADD.gdb`, and against several synthetic fixtures built this session with `ogr2ogr` (3D point GPKG, geometry-less GPKG/OpenFileGDB table, Shapefile with an explicit `numeric(10,3)` cast).
- Direct reads this session: `vicmap_acquire/evidence.py`, `vicmap_acquire/download.py`, `vicmap_acquire/candidates.py`, `vicmap_acquire/origin.py` (header), `vicmap_acquire/__init__.py`, `read_mailbox.py` (complete), `vicmap.toml`, `flake.nix`, `tests/__init__.py`, `tests/test_html_visibility_differential.py` (first 60 lines), CPython 3.14.7's `zipfile.py` (`ZipFile._extract_member` source via `inspect.getsource`), and strings-inspection of pyogrio's compiled `_io` extension.
- `.planning/phases/02-safe-geospatial-discovery/02-CONTEXT.md`, `.planning/REQUIREMENTS.md`, `.planning/STATE.md`, `.planning/config.json`.

### Secondary (MEDIUM confidence — official docs, cross-checked)
- [PostgreSQL 18 documentation, "Appendix C. SQL Key Words"](https://www.postgresql.org/docs/current/sql-keywords-appendix.html) — reserved-word category definitions.
- [PostgreSQL documentation, "4.1. Lexical Structure"](https://www.postgresql.org/docs/current/sql-syntax-lexical.html) — `NAMEDATALEN`/63-byte identifier limit.
- [PEP 706 – Filter for tarfile.extractall](https://peps.python.org/pep-0706/) and its [discuss.python.org thread](https://discuss.python.org/t/pep-706-filter-for-tarfile-extractall/23903) — confirms the filter mechanism is `tarfile`-only and explicitly does not extend to `zipfile`.
- [OWASP ASVS v4.0.3, "0x20-V12-Files-Resources.md"](https://github.com/OWASP/ASVS/blob/v4.0.3/4.0/en/0x20-V12-Files-Resources.md) — file/resource-handling ASVS category.

### Tertiary (LOW confidence — WebSearch summaries, not independently re-verified beyond the above)
- General GDAL geometry-type-naming background (`" Z"`/`" M"`/`"ZM"` suffix conventions) — the `Point`/`Point Z` cases were independently verified this session; the general `M`/`ZM` pattern was not (see Assumption A6).

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — pyogrio/pyproj/gdal versions and behavior all directly verified against the real delivery this session, not taken from training data.
- Architecture: HIGH — extraction and discovery patterns are directly grounded in existing, already-verified `download.py`/`evidence.py` idioms, extended with this session's own falsification testing of `zipfile` and pyogrio.
- Pitfalls: HIGH — every pitfall in this document was independently reproduced (not just recalled) against either the real delivery or a purpose-built synthetic fixture this session.

**Research date:** 2026-09-14
**Valid until:** 30 days (stable stdlib/PostgreSQL behavior) but re-verify `pyogrio`/`pyproj`/`gdal` versions at planning time if more than ~2 weeks elapse before Phase 2 executes, since `nixpkgs-unstable` moves quickly and today's exact versions are a moving target, not a pin.
