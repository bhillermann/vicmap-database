<!-- refreshed: 2026-09-18 -->
# Architecture

**Analysis Date:** 2026-09-18

## System Overview

The vicmap-database system acquires and processes geospatial data from a trusted email source through two distinct phases:
- **Phase 1 (Acquisition)**: Authenticates user, scans mailbox for trusted candidates, downloads artifact, verifies integrity
- **Phase 2 (Discovery)**: Extracts archive, discovers geospatial layers, normalizes table names, publishes manifest

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│                             Phase 1: Acquisition                             │
│  read_mailbox.py → run_acquisition()                                         │
├──────────────┬────────────────┬──────────────┬──────────────┬───────────────┤
│   Graph API  │  Candidates    │  Download    │  Artifact    │   Evidence    │
│              │  Recognition   │  Manager     │  Verification│   Emitter     │
└──────────────┴────────────────┴──────────────┴──────────────┴───────────────┘
         │
         ▼  Artifact + Provenance Sidecar
┌─────────────────────────────────────────────────────────────────────────────┐
│                             Phase 2: Discovery                               │
│  discover_order.py → run_discovery()                                         │
├──────────────┬────────────────┬──────────────┬──────────────┬───────────────┤
│  Extraction  │  Discovery     │   Naming     │   Manifest   │   Evidence    │
│  Manager     │  (pyogrio)     │  Normalizer  │  Builder     │   Emitter     │
└──────────────┴────────────────┴──────────────┴──────────────┴───────────────┘
         │
         ▼  Manifest + Companion Files
     PostGIS Ingestion (Phase 3)
```

## Component Responsibilities

| Component | Responsibility | File |
|-----------|----------------|------|
| Graph Adapter | Microsoft Graph OAuth authentication & mailbox scanning | `vicmap_acquire/graph.py` |
| Candidate Recognition | Identify trusted mail candidates with authenticated origins | `vicmap_acquire/candidates.py` |
| Download Manager | SSRF-resistant streaming artifact download with byte limits | `vicmap_acquire/download.py` |
| Artifact Verification | Pre-extraction SHA256 & byte-count validation | `vicmap_acquire/extraction.py` |
| Archive Extraction | Atomic zip extraction with member validation & fsync | `vicmap_acquire/extraction.py` |
| Layer Discovery | pyogrio/ogrinfo profiling of geospatial datasets | `vicmap_acquire/discovery.py` |
| Table Naming | Deterministic target-table normalization & collision detection | `vicmap_acquire/naming.py` |
| Manifest Builder | Frozen dataclass serialization to manifest.json | `vicmap_acquire/manifest.py` |
| Evidence Emitter | Closed JSON Lines event emission with _EmitOnce guard | `vicmap_acquire/evidence.py` |
| Origin Verifier | Authentication-verdict validation (DKIM/DMARC/etc) | `vicmap_acquire/origin.py` |
| Configuration Loader | TOML parsing & policy validation | `read_mailbox.py` |

## Pattern Overview

**Overall:** Multi-stage pipeline with ordered typed-failure composition and guarded event emission

**Key Characteristics:**
- **No import cycles**: Dependency direction strictly adheres to leaf-ward layering
- **Closed exceptions**: Every failure class carries no untrusted text (no subprocess/driver/archive output)
- **Atomic publication**: Only fsync'd filesystem operations serve as commit points
- **Single-emit events**: `_EmitOnce` guard ensures failures never multiply
- **Frozen dataclasses**: All public data structures are immutable (`frozen=True`)
- **TOML-driven policy**: All non-secret parameters reviewable in `vicmap.toml`

## Layers

**Graph & Authentication:**
- Purpose: Establish trusted OAuth session with Microsoft Graph, retrieve authenticated mailbox messages
- Location: `vicmap_acquire/graph.py`
- Contains: Graph account initialization, MIME message retrieval, connection management
- Depends on: O365 SDK, environment credentials
- Used by: `read_mailbox.run_acquisition`

**Candidate Recognition & Origin Verification:**
- Purpose: Parse mail candidates, extract download links, verify authentication verdicts (DKIM/DMARC/CompAuth)
- Location: `vicmap_acquire/candidates.py`, `vicmap_acquire/origin.py`
- Contains: HTML/text URL parsing with html5lib tree-construction, email header authentication parsing
- Depends on: html5lib, email.parser, Graph messages
- Used by: `read_mailbox.run_acquisition` for candidate filtering

**Download & Artifact Integrity:**
- Purpose: Stream artifact bytes with SSRF protection, byte limits, timeout enforcement; persist provenance sidecar
- Location: `vicmap_acquire/download.py`
- Contains: URL validation against closed allowlist, streaming loop with progress events, SHA256 streaming, atomic file publication
- Depends on: requests, pathlib, hashlib
- Used by: `read_mailbox.run_acquisition` (Phase 1 output)

**Extraction & Archive Validation:**
- Purpose: Extract zip members with directory-escape prevention, member-count limits, compression-ratio verification
- Location: `vicmap_acquire/extraction.py`
- Contains: Zip member enumeration, unsafe-path rejection, fsync directory publication
- Depends on: zipfile, pathlib
- Used by: `discover_order.run_discovery` (Phase 2 input)

**Layer Discovery:**
- Purpose: Enumerate and profile geospatial datasets using pyogrio + ogrinfo subprocess
- Location: `vicmap_acquire/discovery.py`
- Contains: Extension→driver mapping, pyogrio.read_info() calls, ogrinfo -json subprocess coordination
- Depends on: pyogrio, pyproj, subprocess
- Used by: `discover_order.run_discovery` to populate layers

**Table Naming & Collision Detection:**
- Purpose: Deterministic target-table name normalization, keyword avoidance, collision detection
- Location: `vicmap_acquire/naming.py`
- Contains: PostgreSQL reserved-keyword snapshot (transcribed 2026-09-16), casefold normalization, name conflict detection
- Depends on: re module only
- Used by: `discover_order.run_discovery` to assign targets

**Manifest & Evidence:**
- Purpose: Freeze discovery results into JSON structures; emit safe, disclosure-minimal events
- Location: `vicmap_acquire/manifest.py`, `vicmap_acquire/evidence.py`
- Contains: ImportManifest dataclass with schema versioning, SuccessEvent/SafeFailure JSON serialization
- Depends on: json, dataclasses, hashlib
- Used by: Both acquisition and discovery phases for output/reporting

## Data Flow

### Phase 1: Acquisition (read_mailbox.py)

1. **Configuration Loading** (`read_mailbox.load_config`) — reads `vicmap.toml`, validates all policy constraints
2. **Credential Retrieval** — reads `O365_AUTH_ID`, `O365_AUTH_SECRET`, `TENANT_ID` from environment
3. **Graph Authentication** (`graph.py:GraphMailbox.__init__`) — establishes OAuth session via O365 SDK
4. **Mailbox Scan** (`graph.py:scan_mailbox`) — retrieves MIME messages matching sender/date criteria
5. **Candidate Recognition** (`candidates.py:recognize_candidate`) — for each message:
   - Parses HTML body via html5lib tree construction
   - Extracts visible URLs from DOM
   - Identifies archive download link
   - Extracts order ID from subject/URL
6. **Candidate Selection** (`candidates.py:select_candidate`) — picks single candidate, fails if none or multiple
7. **Origin Verification** (`origin.py:verify_authenticated_origin`) — validates DKIM/DMARC/CompAuth headers
8. **Download** (`download.py:download_artifact`) — streams bytes with:
   - SSRF rejection of disallowed hosts
   - Byte-limit enforcement (per-chunk + cumulative)
   - Timeout on stalled reads
   - SHA256 streaming hash
   - Atomic temp→final publication
9. **Provenance Sidecar Write** (`download.py:write_provenance_sidecar`) — persists order ID, SHA256, byte count, message fingerprint
10. **Event Emission** — guard-protected SuccessEvent for each stage; any failure emits SafeFailure once

**State Management:**
- No mutable process state; Graph/HTTP sessions managed as context
- `_EmitOnce` guard tracks: whether sink has failed, whether failure already emitted
- Atomic publication ensures only fsync'd files survive process crash

### Phase 2: Discovery (discover_order.py)

1. **Configuration Loading** (`read_mailbox.load_discovery_config`) — reads Phase 2 policy from `vicmap.toml`
2. **Provenance Sidecar Reading** (`download.py:read_provenance_sidecar`) — validates artifact identity
3. **Artifact Verification** (`extraction.py:verify_artifact`) — SHA256 + byte-count check
4. **Archive Extraction** (`extraction.py:extract_artifact`) — unzips to `.tmp-` directory with:
   - Member path validation (rejects `..`, symlinks)
   - Cumulative byte-count + member-count limits
   - Compression-ratio verification (stored ÷ compressed, max 200×)
   - Fsync publication to final run directory
5. **Layer Discovery** (`discovery.py:discover_layers`) — for each `.gdb` directory:
   - Calls pyogrio.read_info() for feature count, geometry type, CRS, field list
   - Runs ogrinfo -json -al -so subprocess for field precision/nullability/width
   - Returns LayerProfile with complete metadata
6. **Table Naming** (`naming.py:assign_target_table_names`) — maps each source layer to:
   - Deterministic target name: `{source_name_normalized}_{layer_index}`
   - PostgreSQL keyword conflict detection
   - Multi-layer collision detection
7. **Manifest Building** (`manifest.py:build_manifest`) — freezes:
   - All discovered layers with their target tables
   - Companion files (non-.gdb members)
   - Artifact/run identifiers
   - SHA256 of manifest itself
8. **Manifest Write** (`manifest.py:write_manifest`) — JSON serialization + fsync
9. **Event Emission** — guard-protected SuccessEvent for each stage

**State Management:**
- No mutable state; all intermediate values are immutable dataclasses
- Extraction leaves `.tmp-` directories on early failures for debugging
- Manifest written before final SuccessEvent, so even if event sink fails, manifest is durable

## Key Abstractions

**DiscoveryConfig:**
- Purpose: Encapsulate all non-secret Phase 2 policy (paths, byte limits, format allowlist, timeouts)
- Examples: `discover_order.py:DiscoveryConfig`
- Pattern: Frozen dataclass, validated on construction

**LayerProfile:**
- Purpose: Represent pyogrio discovery results for one geospatial layer
- Examples: `discovery.py:LayerProfile` with feature_count, geometry_type, crs, fields
- Pattern: Frozen dataclass with optional field list from ogrinfo

**ImportManifest:**
- Purpose: Immutable Phase 2 output contract for Phase 3 ingestion
- Examples: `manifest.py:ImportManifest` with layers, artifact identity, run timestamp
- Pattern: Frozen dataclass, serialized to manifest.json

**Closed Exception Hierarchy:**
- Purpose: Typed failures with no untrusted detail leakage
- Examples: `ArchiveFailure`, `DiscoveryFailure`, `NamingFailure`, `ManifestFailure`
- Pattern: Each exception has a `code` attribute; no untrusted text in message

## Entry Points

**read_mailbox.main():**
- Location: `read_mailbox.py:main`
- Triggers: CLI invocation with `--config` (default: `vicmap.toml`)
- Responsibilities: Parse TOML, validate policy, initialize Graph session, orchestrate Phase 1 via `run_acquisition`, handle exit codes

**discover_order.main():**
- Location: `discover_order.py:main`
- Triggers: CLI invocation with `--config` (default: `vicmap.toml`)
- Responsibilities: Parse TOML, read provenance sidecar, build ExtractionPolicy/DiscoveryPolicy, orchestrate Phase 2 via `run_discovery`, handle exit codes

**run_acquisition():**
- Location: `read_mailbox.py:run_acquisition`
- Triggers: Called by Phase 1 main after config validation
- Responsibilities: Compose graph → candidates → download → artifact → evidence pipeline; guard all emissions

**run_discovery():**
- Location: `discover_order.py:run_discovery`
- Triggers: Called by Phase 2 main after provenance validation
- Responsibilities: Compose verify → extract → discover → name → build → write → render pipeline; guard all emissions

## Architectural Constraints

- **Threading:** Single-threaded, synchronous pipeline (no workers, no async/await)
- **Global state:** None; Graph/HTTP sessions are context-local, immediately closed after use
- **Circular imports:** None by design; dependency graph is acyclic (graph → candidates → download; discovery → naming → manifest)
- **File atomicity:** Only fsync'd final-directory entries are commit points; partial writes left in `.tmp-` for inspection
- **Event ordering:** Deterministic; events emitted in pipeline order and never reordered by the guard
- **Configuration mutability:** vicmap.toml is read-only at runtime; no in-process policy changes

## Anti-Patterns

### Subprocess Text Exposure

**What happens:** Layer discovery combines pyogrio.read_info() with ogrinfo subprocess; ogrinfo output could carry driver errors or invalid SQL
**Why it's wrong:** Operator-facing events would leak untrusted detail; subprocess failures become opaque
**Do this instead:** `discovery.py` wraps ogrinfo in a subprocess call with timeout; any exception (timeout, non-zero exit, JSON parse error) collapses to `DiscoveryFailure` with no subprocess text exposed

### Silent Format Rejection

**What happens:** A recognized extension (e.g., `.shp`) is skipped silently because the format isn't in the allowlist
**Why it's wrong:** Operator can't distinguish "format not supported" from "no datasets found"
**Do this instead:** `discovery.py:find_datasets` checks the extension-to-driver map; if recognized but not allowed, raises named `UnsupportedFormat` failure

### Implicit Member Validation Bypass

**What happens:** Archive extraction walks members with no path validation; a crafted zip could escape the extraction root via `../` sequences or symlinks
**Why it's wrong:** Data confidentiality and system integrity compromised
**Do this instead:** `extraction.py:_reject_unsafe_member` resolves each member path and asserts it remains under extraction root; symlinks are rejected outright

### Unbounded Event Retries

**What happens:** Event sink fails (e.g., render_success raises); orchestration code retries the emission
**Why it's wrong:** Faulty sink can turn a closed failure (already emitted once) into multiple events, confusing operators
**Do this instead:** `_EmitOnce` guard allows sink to fail exactly once; subsequent calls to emit() are no-ops; if guard.failed is true at exit, the pipeline raises RunDiscoveryReportingFailed (or AcquisitionFailure) without retrying the sink

### Hardcoded Byte Limits

**What happens:** Byte limits are defined in code, not configuration
**Why it's wrong:** Operators can't adjust limits without redeploying
**Do this instead:** All byte limits live in DownloadPolicy/ExtractionPolicy dataclasses, which are populated from vicmap.toml; no ceiling value is hardcoded in code (except regex patterns)

## Error Handling

**Strategy:** Typed closed exceptions at layer boundaries; guard-protected single-emission of events; pipeline fails fast without swallowing intermediate exceptions

**Patterns:**

1. **Per-layer failure class:** Each module (graph, download, extraction, etc) defines its own failure base class (e.g., `DownloadFailure`, `ArchiveFailure`)
2. **Code attribute:** Every failure has a `code` attribute (e.g., "download_url_rejected", "archive_unreadable") for event reporting
3. **No subprocess text:** Subprocess/driver output is never interpolated into exception messages
4. **Guard-protected emission:** `_EmitOnce` ensures failures are emitted exactly once; the sink cannot turn a failure into multiple events
5. **Re-raise unchanged:** Orchestration code catches typed exceptions, emits events, then re-raises unchanged

## Cross-Cutting Concerns

**Logging:** 
- Dependency loggers (O365, msal, requests, urllib3) are silenced at CRITICAL+1
- Application doesn't use logging module; all output is via guarded event emission

**Validation:**
- Configuration validation in `read_mailbox.validate_acquisition_policy` (policy checks before any work)
- URL validation in `download.py:validate_https_target` (allowlist + scheme checks)
- Member path validation in `extraction.py:_reject_unsafe_member` (resolves and asserts within root)
- Naming validation in `naming.py:assign_target_table_names` (keyword checks + collision detection)

**Authentication:**
- O365 OAuth tokens are memory-only (MemoryTokenBackend); no token persistence to disk
- DKIM/DMARC/CompAuth verdicts verified from email headers by trusted mail infrastructure
- No custom cryptography; relies on email protocol headers and O365 SDK

---

*Architecture analysis: 2026-09-18*
