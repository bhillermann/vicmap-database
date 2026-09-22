<!-- refreshed: 2026-09-22 -->
# Architecture

**Analysis Date:** 2026-09-22

## System Overview

The Vicmap Database acquisition system is a three-phase pipeline that retrieves geospatial map data from a trusted email source, extracts and catalogs layers from the artifact, and loads them into a PostGIS database. Each phase is independent but sequentially ordered, with typed failure boundaries and closed event reporting at every stage.

```text
┌──────────────────────────────────────────────────────────────────────────┐
│                         Phase 1: Acquisition                              │
│              Graph → Candidate → Download → Verify                        │
│                   (read_mailbox.py)                                       │
└─────────────────────────┬──────────────────────────────────────────────────┘
                          │ Download artifact
                          │ (Order_{id}.zip)
                          ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                         Phase 2: Discovery                                │
│        Extract → Discover → Name → Build → Write Manifest                │
│                   (discover_order.py)                                     │
└─────────────────────────┬──────────────────────────────────────────────────┘
                          │ Manifest + extracted
                          │ geospatial files
                          ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                         Phase 3: Staging                                  │
│        Connect → Preflight → Load → Validate → Publish                   │
│                   (stage_order.py)                                        │
└──────────────────────────────────────────────────────────────────────────┘
                          │
                          ▼
                   PostGIS Database
```

## Component Responsibilities

| Component | Responsibility | File |
|-----------|----------------|------|
| **Acquisition** | Graph mailbox → candidate selection → artifact download → verification | `read_mailbox.py` |
| **Graph Adapter** | Microsoft Graph OAuth + mailbox metadata iteration | `vicmap_acquire/graph.py` |
| **Candidate Recognition** | Email header parsing, HTML visibility analysis, authentication verification | `vicmap_acquire/candidates.py` |
| **Origin Verification** | Authenticated sender validation via SPF/DKIM/DMARC headers | `vicmap_acquire/origin.py` |
| **Artifact Download** | Streaming HTTP download with SSRF protection and integrity verification | `vicmap_acquire/download.py` |
| **Extraction** | Archive member extraction with traversal/compression safety checks | `vicmap_acquire/extraction.py` |
| **Discovery** | GIS layer profiling via pyogrio + ogrinfo subprocess | `vicmap_acquire/discovery.py` |
| **Naming** | Deterministic PostgreSQL target table name generation + collision detection | `vicmap_acquire/naming.py` |
| **Manifest** | Frozen import contract and `manifest.json` persistence | `vicmap_acquire/manifest.py` |
| **Staging** | Database connection, privilege verification, ogr2ogr load, row validation | `vicmap_acquire/staging.py` |
| **Evidence** | Closed, redaction-safe JSON Lines event reporting | `vicmap_acquire/evidence.py` |

## Pattern Overview

**Overall:** Fail-closed orchestration with ordered pipelines and typed error boundaries

**Key Characteristics:**
- Every phase composes stages in strict order; no stage begins before the previous succeeds
- Typed exception hierarchies map to closed `ReasonCode` enums, never raw driver/subprocess text
- Event reporting routes through `_EmitOnce` guards that guarantee exactly-once delivery and isolation
- Redaction-safe event streams (JSON Lines) expose only project-controlled values, never filesystem/driver/SQL text
- Configuration is frozen and validated once at startup per `AcquisitionConfig`, `DiscoveryRunConfig`, `DatabaseRunConfig`
- Every boundary module (graph, download, extraction, discovery, staging) is driver/subprocess-isolated

## Layers

**Configuration & Orchestration:**
- Purpose: Parse `vicmap.toml`, validate policy, route events through guards
- Location: `read_mailbox.py`, `discover_order.py`, `stage_order.py` (root entry points)
- Contains: Policy dataclasses, CLI argument parsing, main orchestration functions
- Depends on: All acquire modules, validation functions
- Used by: Command-line invocation

**Event & Data Model:**
- Purpose: Define closed failure codes, redaction-safe event payloads, manifest schema
- Location: `vicmap_acquire/evidence.py`, `vicmap_acquire/manifest.py`
- Contains: `Stage`, `ReasonCode`, `SuccessEvent`, `SafeFailure`, `ImportManifest`
- Depends on: Nothing (leaf modules)
- Used by: All other modules for structured reporting

**External Boundaries:**

*Graph/Mailbox Boundary:*
- Purpose: Abstract Microsoft Graph API and MIME parsing
- Location: `vicmap_acquire/graph.py`, `vicmap_acquire/candidates.py`, `vicmap_acquire/origin.py`
- Contains: Graph connection management, candidate extraction, authentication verification
- Depends on: O365 SDK, html5lib, email parser
- Used by: Acquisition orchestration

*Download Boundary:*
- Purpose: Stream artifact over HTTPS with SSRF/redirect/size protections
- Location: `vicmap_acquire/download.py`
- Contains: Streaming download, URL validation, redirect chain inspection, artifact checksumming
- Depends on: requests, stdlib urllib
- Used by: Acquisition orchestration

*Extraction Boundary:*
- Purpose: Safely unzip artifacts with member/compression guards
- Location: `vicmap_acquire/extraction.py`
- Contains: ZIP iteration, traversal detection, size enforcement, member profiling
- Depends on: stdlib zipfile
- Used by: Discovery orchestration

**Processing Layers:**

*Discovery:*
- Purpose: Profile GIS layers in extracted archives
- Location: `vicmap_acquire/discovery.py`
- Contains: pyogrio dataset enumeration, ogrinfo JSON subprocess parsing
- Depends on: pyogrio, pyproj, subprocess
- Used by: Discovery orchestration

*Naming:*
- Purpose: Map source layer names to PostgreSQL identifiers
- Location: `vicmap_acquire/naming.py`
- Contains: Keyword filtering, length bounding, collision detection
- Depends on: Nothing (leaf module, no I/O)
- Used by: Discovery orchestration

*Staging:*
- Purpose: Database connection, privilege verification, layer loading
- Location: `vicmap_acquire/staging.py`
- Contains: psycopg connection management, ogr2ogr subprocess invocation, row validation
- Depends on: psycopg, subprocess
- Used by: Staging orchestration (Phase 3)

## Data Flow

### Phase 1: Acquisition Path

1. **Startup** (`read_mailbox.py:main()`) — Parse `vicmap.toml`, load `AcquisitionConfig` (`read_mailbox.py:763`)
2. **Validation** (`read_mailbox.py:285`) — Validate policy: credentials available, bounds sensible, allowlists non-empty
3. **Graph Auth** (`vicmap_acquire/graph.py:GraphMailbox.__init__`) — Create O365 account with tenant credentials
4. **Mailbox Scan** (`read_mailbox.py:513`) — Iterate messages from cutoff date via `graph.iter_metadata()` (`vicmap_acquire/graph.py`)
5. **Candidate Recognition** (`vicmap_acquire/candidates.py:recognize_candidate()`) — For each message:
   - Fetch MIME via Graph (`graph.get_mime_content()`)
   - Parse email headers + HTML body
   - Build `Candidate` record (order ID, sender, URL)
6. **Candidate Selection** (`vicmap_acquire/candidates.py:select_candidate()`) — Choose one from list (fail if 0 or >1)
7. **Download** (`vicmap_acquire/download.py:download_artifact()`) — Stream artifact URL with:
   - URL allowlist check
   - Redirect chain inspection (reject disallowed hosts)
   - Streaming size enforcement
   - SHA256 integrity check
8. **Write Provenance** (`vicmap_acquire/download.py:write_provenance_sidecar()`) — Write `.provenance.json` alongside artifact
9. **Emit Success** (`read_mailbox.py:580`) — Emit redacted `SuccessEvent` records via guard

### Phase 2: Discovery Path

1. **Startup** (`discover_order.py:main()`) — Parse `vicmap.toml`, load `DiscoveryRunConfig` + `ExtractionPolicy`/`DiscoveryPolicy`
2. **Read Provenance** (`vicmap_acquire/download.py:read_provenance_sidecar()`) — Load `.provenance.json` to verify SHA256/byte count
3. **Verify Artifact** (`vicmap_acquire/extraction.py:verify_artifact()`) — SHA256 check on-disk artifact
4. **Extract Archive** (`vicmap_acquire/extraction.py:extract_artifact()`) — Unzip with:
   - Member size bounds
   - Total size enforcement
   - Compression ratio ceiling
   - Traversal detection (reject `..` paths)
5. **Discover Layers** (`vicmap_acquire/discovery.py:discover_layers()`) — For each extracted dataset:
   - Call `pyogrio.read_info()` for bulk metadata
   - Call `ogrinfo -json -al -so` for field details
   - Validate geometry type + CRS
6. **Assign Names** (`discover_order.py:assign_target_table_names()`) — Map source layer names via `vicmap_acquire/naming.py:normalize_target_table_name()`
7. **Build Manifest** (`vicmap_acquire/manifest.py:build_manifest()`) — Construct frozen `ImportManifest` record
8. **Write Manifest** (`vicmap_acquire/manifest.py:write_manifest()`) — Persist `manifest.json` + compute SHA256 digest
9. **Emit Success** (`discover_order.py:180`) — Emit redacted `SuccessEvent` records with layer count, manifest digest

### Phase 3: Staging Path

1. **Startup** (`stage_order.py:main()`) — Parse `vicmap.toml`, load `DatabaseRunConfig`
2. **Create Connection** (`vicmap_acquire/staging.py:read_database_identity()`) — Connect via psycopg with password from env (`VICMAP_DB_PASSWORD`)
3. **Preflight** (`vicmap_acquire/staging.py:preflight_staging_privileges()`) — Prove loader can write to staging schema (rolled-back CREATE)
4. **Read Manifest** (`vicmap_acquire/manifest.py:read_manifest()`) — Load `manifest.json` from run directory
5. **For Each Layer:**
   - Invoke `ogr2ogr -f PostgreSQL ... layer` (`vicmap_acquire/staging.py:run_staging()`)
   - Verify row count matches extracted file
   - Capture stderr to diagnostic file on failure
6. **Emit Success** (`stage_order.py:135`) — Emit redacted `SuccessEvent` with row count

**State Management:**
- No global mutable state in modules; all state is parameter-passed or closure-captured
- `GraphMailbox` holds a live O365 account in its instance (recreated per run)
- psycopg connection in `StagingPolicy` is live only during `run_staging()` execution
- Manifest is immutable frozen dataclass (`@dataclass(frozen=True)`)

## Key Abstractions

**SuccessEvent & SafeFailure:**
- Purpose: Redacted structured events for operator output and audit trails
- Examples: `SuccessEvent.candidate_selected()`, `SafeFailure(ReasonCode.DOWNLOAD_TIMEOUT, order_id="OK0VUZ")`
- Pattern: Frozen dataclass with regex-validated fields; rendered as JSON Lines via `render_success()`/`render_failure()`

**Candidate:**
- Purpose: Recognized email message containing order metadata and artifact URL
- Examples: `Candidate(order_id="OK0VUZ", artifact_url="https://...", sender="noreply@...", received_datetime_utc=...)`
- Pattern: Frozen dataclass, only constructed after full MIME header + HTML parse validation

**ImportManifest:**
- Purpose: Frozen contract representing a discovered order's layers + companion files
- Examples: `ImportManifest(order_id="OK0VUZ", layers=(ManifestLayer(...), ...), run_timestamp="20260921T123456Z")`
- Pattern: Frozen dataclass with SHA256 digest written to `manifest.json` for auditability

**LayerProfile:**
- Purpose: Discovered GIS layer with field schema + geometry/CRS info
- Examples: `LayerProfile(source_name="roads", field_count=12, geometry_type="LineString", crs_srid=7899)`
- Pattern: Frozen dataclass, immutable product of discovery phase

**Closed Exception Hierarchy:**
- Purpose: Ensure typed failures map to `ReasonCode` enums, never driver/subprocess text
- Examples: `CandidateError`, `DownloadError`, `ArchiveFailure`, `DiscoveryFailure`, `StagingFailure`
- Pattern: Each boundary module defines its own base exception, re-raised up to orchestration guard

## Entry Points

**Phase 1 Orchestration:**
- Location: `read_mailbox.py:main()` (CLI) → `read_mailbox.py:run_acquisition()` (core)
- Triggers: `python read_mailbox.py --config vicmap.toml`
- Responsibilities: Load config, authenticate with Graph, scan mailbox, download artifact, emit provenance

**Phase 2 Orchestration:**
- Location: `discover_order.py:main()` (CLI) → `discover_order.py:run_discovery()` (core)
- Triggers: `python discover_order.py --config vicmap.toml`
- Responsibilities: Extract archive, discover layers, normalize names, write manifest

**Phase 3 Orchestration:**
- Location: `stage_order.py:main()` (CLI) → indirect (no separate function, inline in main)
- Triggers: `python stage_order.py --config vicmap.toml [--preflight-only]`
- Responsibilities: Connect database, prove privilege, load layers, validate row counts

## Architectural Constraints

- **Driver Isolation:** Only `vicmap_acquire/staging.py` imports psycopg (D-41); all other modules stay driver-free
- **Leaf Modules:** `vicmap_acquire/naming.py` imports nothing (proven by import test); `vicmap_acquire/origin.py` has no I/O
- **No Global State:** Module-level singletons forbidden; factories passed to orchestration functions
- **Circular Imports:** Prevented by strict dependency direction: leaf modules (evidence, naming, origin) → processing layers (discovery, extraction) → boundaries (graph, download) → orchestration (read_mailbox)
- **Event Ordering:** `_EmitOnce` guards guarantee exactly one emission per event; a failed emission aborts the run
- **Configuration Immutability:** Policy objects created once at startup, frozen (frozen dataclasses) throughout execution
- **Single Credential:** Only password reaches as env var; no credential in config files (D-58)

## Anti-Patterns

### Raw Exception Text in Closed Failures

**What happens:** A module catches a driver/subprocess exception and re-raises it with `str(e)` in the message

**Why it's wrong:** Sensitive data (SQL, connection strings, file paths) leaks into event streams; violates closed failure contract

**Do this instead:** Define a typed exception (e.g., `class StagingFailure(RuntimeError): code = "..."`), catch the raw exception internally, and raise the typed version with only `.code` attribute (`vicmap_acquire/staging.py:15-25`)

### Skipping Guard Wrapping

**What happens:** An orchestration path emits events directly to `event_sink` instead of wrapping with `_EmitOnce`

**Why it's wrong:** A faulty sink can turn a closed failure into an unhandled exception; no audit trail if emission fails

**Do this instead:** Route all events through `_EmitOnce` guard constructed once per run (`read_mailbox.py:194-225`, `discover_order.py:124`)

### Loose Validation of External Input

**What happens:** Code assumes a validated field value without re-checking in the boundary

**Why it's wrong:** Loose assumptions can inject hostile values into SQL, filesystem paths, or subprocess arguments

**Do this instead:** Re-validate at the boundary with regex patterns (e.g., `evidence.py:_HOST`, `evidence.py:_ORDER_ID`, `staging.py:_IDENTIFIER`; WR-06 validates hostname in evidence.py before read_mailbox.py hands it to staging)

## Error Handling

**Strategy:** Fail-closed with typed boundaries. Every module boundary (graph, download, extraction, discovery, naming, staging) defines its own exception base, which orchestration catches and maps to `ReasonCode`.

**Patterns:**

- **Boundary Catch:** `read_mailbox.py:630-639` catches `GraphError`, `CandidateError`, `DownloadError`, maps `.code` to failure reason, emits via guard
- **Guard Isolation:** `_EmitOnce.emit_failure()` catches rendering exceptions and marks guard failed, so a broken JSON emission is visible
- **Unopened Resources:** Early validation prevents resource creation (e.g., `verify_artifact` checks SHA256 before creating run directory in `vicmap_acquire/extraction.py:verify_artifact()`)
- **Atomic Publish:** Only final filesystem operation commits state (`vicmap_acquire/extraction.py:extract_artifact()` renames `.tmp-` dir only on all-members-extracted success)

## Cross-Cutting Concerns

**Logging:** Project disables dependency logs (O365, msal, requests, urllib3) via `_suppress_dependency_logs()` in `read_mailbox.py:246`; all events route through JSON Lines event sink for audit

**Validation:** Every input validated at module boundary via regex (hostname, order ID, identifier, target table); validation functions in `evidence.py` and boundary modules re-checked before use (WR-06)

**Authentication:** Graph OAuth via O365 SDK (tenant-wide credentials); database via psycopg password from env; mailbox headers re-validated via `Authentication-Results` MIME header parsing in `vicmap_acquire/origin.py`

---

*Architecture analysis: 2026-09-22*
