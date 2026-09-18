# Codebase Structure

**Analysis Date:** 2026-09-18

## Directory Layout

```
vicmap-database/
├── vicmap_acquire/              # Core acquisition/discovery library (Python package)
│   ├── __init__.py              # Package marker (no exports on import)
│   ├── candidates.py            # Mail candidate recognition & origin verification
│   ├── discovery.py             # Geospatial layer discovery via pyogrio/ogrinfo
│   ├── download.py              # Streaming artifact downloader & provenance sidecar
│   ├── evidence.py              # Closed JSON Lines event types & emission
│   ├── extraction.py            # Archive extraction & atomic filesystem publication
│   ├── graph.py                 # Microsoft Graph OAuth & mailbox API
│   ├── manifest.py              # Frozen manifest dataclass & JSON serialization
│   ├── naming.py                # Target-table normalization & collision detection
│   └── origin.py                # DKIM/DMARC/CompAuth verdict verification
├── tests/                       # Test suite
│   ├── __init__.py              # Test package marker
│   ├── fixtures/                # Test data & fixture builders
│   │   ├── __init__.py
│   │   ├── build_fixtures.py    # Code to generate test fixtures
│   │   ├── Order_TRACER1.zip    # Sample archived dataset for tracer tests
│   │   ├── point_z_gdb.zip      # Fixture: point geometry with Z dimension
│   │   └── geometryless_gdb.zip # Fixture: no geometry in dataset
│   ├── test_candidates.py       # Candidate recognition & HTML visibility tests
│   ├── test_discovery.py        # Layer discovery & profiling tests
│   ├── test_discovery_config.py # Discovery configuration validation tests
│   ├── test_discovery_differential.py # Oracle testing vs real drivers
│   ├── test_discovery_tracer.py # Tracer injection for discovery flow
│   ├── test_download.py         # Download manager & SSRF tests
│   ├── test_evidence.py         # Event emission & SafeFailure tests
│   ├── test_extraction.py       # Archive extraction & validation tests
│   ├── test_graph.py            # Graph API adapter tests
│   ├── test_html_visibility_differential.py # HTML parser oracle testing
│   ├── test_manifest.py         # Manifest building & serialization tests
│   ├── test_naming.py           # Table naming & collision detection tests
│   ├── test_origin.py           # Origin verification tests
│   ├── test_provenance.py       # Provenance sidecar I/O tests
│   └── test_repository_policy.py # Repository policy validation tests
├── artifacts/                   # Output directory for downloaded artifacts & sidecars (git-ignored)
│   ├── Order_OK0VUZ.zip         # Downloaded artifact
│   └── Order_OK0VUZ.provenance.json # Provenance sidecar (SHA256, byte count, fingerprint)
├── runs/                        # Output directory for extracted archives (git-ignored)
├── read_mailbox.py              # Phase 1 orchestration: acquisition CLI & run_acquisition
├── discover_order.py            # Phase 2 orchestration: discovery CLI & run_discovery
├── vicmap.toml                  # Configuration file (mailbox, download, extraction, discovery policies)
├── flake.nix                    # Nix development environment (Python 3, gdal, O365 SDK, pyogrio, html5lib)
├── .envrc                       # direnv integration for flake.nix
└── .planning/                   # GSD project management (phase planning, design docs, codebase maps)
    └── codebase/
        ├── ARCHITECTURE.md      # This file: system design, layers, data flow, entry points
        └── STRUCTURE.md         # (This section) directory layout, file locations, conventions
```

## Directory Purposes

**vicmap_acquire/**
- Purpose: Core Python package implementing acquisition (Phase 1) and discovery (Phase 2) logic
- Contains: Modules for email, download, archive, layer discovery, naming, events, and configuration
- Key files: All `*.py` modules are importable by both `read_mailbox.py` and `discover_order.py`

**tests/**
- Purpose: Comprehensive test suite covering all modules and integration scenarios
- Contains: Unit tests, integration tests, differential oracle tests, fixtures
- Key files: One test file per module (test_*.py); fixtures in subdirectory

**tests/fixtures/**
- Purpose: Test data and builders for reproducible test scenarios
- Contains: Zip archives with sample geodatabases, fixture builders
- Generated: `build_fixtures.py` creates fixtures; checked into git for reproducibility

**artifacts/**
- Purpose: Output directory for Phase 1 (downloaded artifacts and provenance sidecars)
- Generated: `read_mailbox.py` writes here
- Committed: No (git-ignored; content varies per run)

**runs/**
- Purpose: Output directory for Phase 2 (extracted archives and manifests)
- Generated: `discover_order.py` writes here
- Committed: No (git-ignored; content varies per run)

## Key File Locations

**Entry Points:**
- `read_mailbox.py`: Phase 1 CLI and run_acquisition orchestration
- `discover_order.py`: Phase 2 CLI and run_discovery orchestration

**Configuration:**
- `vicmap.toml`: TOML policy file (mailbox, download, extraction, discovery sections)
- `flake.nix`: Nix development environment with Python 3, GDAL (ogrinfo), O365 SDK, dependencies

**Core Logic:**
- `vicmap_acquire/graph.py`: Microsoft Graph authentication & mailbox scanning
- `vicmap_acquire/candidates.py`: Mail candidate recognition (HTML/text parsing, URL extraction)
- `vicmap_acquire/download.py`: Streaming artifact download with SSRF protection
- `vicmap_acquire/extraction.py`: Archive extraction with member validation
- `vicmap_acquire/discovery.py`: Geospatial layer discovery (pyogrio + ogrinfo)
- `vicmap_acquire/naming.py`: Target-table name normalization & collision detection
- `vicmap_acquire/manifest.py`: Manifest dataclass & JSON serialization
- `vicmap_acquire/evidence.py`: Event types & closed-failure reporting
- `vicmap_acquire/origin.py`: DKIM/DMARC/CompAuth verdict verification

**Testing:**
- `tests/test_*.py`: One unit/integration test file per module
- `tests/fixtures/`: Zip archives (sample geodatabases) and builders
- `tests/fixtures/build_fixtures.py`: Code to generate test data

## Naming Conventions

**Files:**
- Module files: `snake_case.py` (e.g., `discovery.py`, `candidates.py`)
- Entry points: `snake_case_descriptive.py` (e.g., `read_mailbox.py`, `discover_order.py`)
- Test files: `test_${module_name}.py` (e.g., `test_discovery.py`)
- Config files: `UPPERCASE.toml`, `UPPERCASE.nix` (e.g., `vicmap.toml`, `flake.nix`)

**Directories:**
- Package: `snake_case` (e.g., `vicmap_acquire`)
- Test package: `tests`
- Output: Lowercase (e.g., `artifacts`, `runs`)
- Planning: Uppercase (e.g., `.planning`)

**Python Classes:**
- Exceptions: `PascalCaseDescriptive` (e.g., `ArchiveFailure`, `NamingFailure`)
- Dataclasses: `PascalCaseNoun` (e.g., `ImportManifest`, `LayerProfile`, `ExtractionPolicy`)
- Enums: `PascalCaseNoun` (e.g., `ReasonCode`, `Stage`)

**Python Functions:**
- Public: `snake_case` (e.g., `discover_layers`, `verify_artifact`)
- Private (module-level): `_snake_case` (e.g., `_fsync_directory`, `_reject_unsafe_member`)
- Test helpers: `test_$description` (e.g., `test_verify_artifact_rejects_hash_mismatch`)

## Where to Add New Code

**New Module (same tier as discovery/extraction):**
- Location: `vicmap_acquire/module_name.py`
- Responsibilities: Single concern (e.g., one phase, one external API, one data type)
- Imports: Leaf-ward only (import from lower-tier modules, never upward)
- Exceptions: Define a base failure class (e.g., `ModuleFailure`)
- Tests: Create `tests/test_module_name.py` with same structure as existing tests

**New Function/Entrypoint:**
- Phase 1 additions: Add to `read_mailbox.py` (e.g., new CLI flags, new orchestration steps)
- Phase 2 additions: Add to `discover_order.py` (e.g., new output formats)
- Shared logic: Extract to `vicmap_acquire/` module if used by both phases

**New Configuration Option:**
- Location: `vicmap.toml` [section_name] with key
- Validation: Add to corresponding `validate_*_policy` function in `read_mailbox.py`
- Usage: Add field to `ExtractionPolicy` / `DiscoveryPolicy` / `DownloadPolicy` dataclass
- Tests: Add test cases to `tests/test_*_config.py`

**New Test Fixture:**
- Location: `tests/fixtures/` with descriptive name
- Creation: Add builder logic to `tests/fixtures/build_fixtures.py`
- Usage: Import and use in `tests/test_*.py` via `open(FIXTURE_PATH, 'rb')`

## Special Directories

**artifacts/ (Output):**
- Purpose: Phase 1 output directory
- Generated: By `download_artifact()` in `download.py`
- Content: `Order_${order_id}.zip` (artifact) + `Order_${order_id}.provenance.json` (sidecar)
- Committed: No (git-ignored)
- Fsync: Yes (directory entry fsync'd to ensure durability)

**runs/ (Output):**
- Purpose: Phase 2 output directory
- Generated: By `extract_artifact()` in `extraction.py` and `write_manifest()` in `manifest.py`
- Content: `${run_id}/` subdirectories with extracted members + `manifest.json`
- Committed: No (git-ignored)
- Fsync: Yes (directory entry fsync'd at extraction complete)

**.tmp-* (Temporary, Debugging):**
- Purpose: Staging directories during extraction; left behind on failure for operator inspection
- Generated: By `extract_artifact()` in `extraction.py`
- Content: Partial or complete archive members depending on failure point
- Cleanup: Manual (operator reviews and deletes)
- Fsync: No (only final directory is fsync'd)

**tests/fixtures/ (Test Data):**
- Purpose: Reproducible test inputs (zip archives with sample geodatabases)
- Content: `Order_TRACER1.zip`, `point_z_gdb.zip`, `geometryless_gdb.zip`
- Generated: Once via `build_fixtures.py`, committed to git
- Consistency: Builders allow regeneration if needed (though git commit is canonical)

## Import Structure

**Strict Layering (Leaf-Ward Dependencies):**

```
read_mailbox.py
├── vicmap_acquire.graph
├── vicmap_acquire.candidates
│   ├── vicmap_acquire.graph
│   └── vicmap_acquire.origin
├── vicmap_acquire.download
├── vicmap_acquire.evidence
└── vicmap_acquire.origin

discover_order.py
├── read_mailbox (load_discovery_config, _EmitOnce)
├── vicmap_acquire.discovery
├── vicmap_acquire.extraction
├── vicmap_acquire.manifest
├── vicmap_acquire.naming
└── vicmap_acquire.evidence
```

**No Circular Imports:**
- `graph.py` does not import from candidates, download, or discovery
- `download.py` does not import from extraction, discovery, or manifest
- `discovery.py` does not import from extraction or manifest
- `naming.py` imports only from discovery (LayerProfile)
- `manifest.py` imports only from discovery (LayerProfile, FieldProfile)

**Export Pattern:**
- `__init__.py` is empty; imports must be explicit (e.g., `from vicmap_acquire.discovery import discover_layers`)
- No wildcard imports (`from module import *`)
- All public APIs documented in module docstrings

## Configuration File Structure

**vicmap.toml Sections:**

```toml
[mailbox]              # Phase 1: Graph & mailbox scanning
address = "..."        # Mailbox email address
folder = "Inbox"       # Folder to scan (hardcoded as "Inbox")
allowed_senders = [...] # Sender domain allowlist
allowed_order_ids = [...] # Order ID allowlist
lookback_days = 15     # How far back to scan
required_authentication_results = [...] # DKIM/DMARC/etc
allow_order_id_mismatch = false # Strict order ID matching

[download]             # Phase 1: Download manager
allowed_hosts = [...]  # SSRF allowlist (hostname only)
max_bytes = ...        # Max artifact size
connect_timeout_seconds = 10
read_timeout_seconds = 60
progress_interval_seconds = 5
max_redirects = 5
fingerprint_hex_chars = 16
output_dir = "artifacts"
allowed_url_prefixes = [...] # Exact prefix allowlist for URLs

[extraction]           # Phase 2: Archive extraction
run_dir = "runs"       # Output directory
max_total_bytes = ...  # Total extraction size limit
max_member_bytes = ... # Per-member size limit
max_member_count = ... # Max members in archive
max_compression_ratio = 200 # Compression bomb protection

[discovery]            # Phase 2: Layer discovery
supported_formats = ["OpenFileGDB"] # Format allowlist
ogrinfo_timeout_seconds = 60 # Subprocess timeout
```

---

*Structure analysis: 2026-09-18*
