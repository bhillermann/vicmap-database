# Codebase Structure

**Analysis Date:** 2026-09-22

## Directory Layout

```
/home/brendon/Development/vicmap-database/
├── vicmap_acquire/                    # Core acquisition package
│   ├── __init__.py                    # Package marker
│   ├── evidence.py                    # Event schemas + redaction
│   ├── graph.py                       # Microsoft Graph adapter
│   ├── candidates.py                  # Email candidate extraction
│   ├── origin.py                      # Authenticated sender verification
│   ├── download.py                    # SSRF-safe artifact downloader
│   ├── extraction.py                  # Archive safety + member extraction
│   ├── discovery.py                   # GIS layer profiling
│   ├── naming.py                      # PostgreSQL identifier normalization
│   ├── manifest.py                    # Manifest schema + persistence
│   └── staging.py                     # PostGIS database loader
├── tests/                              # Test suite
│   ├── __init__.py                    # Package marker
│   ├── fixtures/                      # Test data + builders
│   ├── test_*.py                      # Test modules (1:1 with acquire)
│   └── test_*_differential.py         # Oracle-based differential tests
├── read_mailbox.py                    # Phase 1: Acquisition orchestration
├── discover_order.py                  # Phase 2: Discovery orchestration
├── stage_order.py                     # Phase 3: Staging orchestration
├── vicmap.toml                        # Configuration (1 order only)
├── flake.nix                          # Nix environment
├── .envrc                             # direnv integration
├── artifacts/                         # Downloaded ZIP files (gitignored)
├── runs/                              # Extracted layers (gitignored)
│   └── {order_id}/
│       └── {timestamp}/
│           ├── manifest.json
│           ├── data.gdb/
│           ├── data.shp/
│           └── ...
├── db/                                # Database (SQLite in dev, PostgreSQL in prod)
├── token/                             # OAuth token storage (gitignored)
├── .planning/                         # GSD planning docs
│   ├── codebase/                      # Architecture reference
│   ├── research/                      # Pre-implementation research
│   └── ...
└── .gsd/                              # GSD operational state
```

## Directory Purposes

**`vicmap_acquire/`:**
- Purpose: Core package with typed, fail-closed module boundaries
- Contains: One module per architectural layer
- Key files: `evidence.py` (event schemas), `staging.py` (database boundary)

**`tests/`:**
- Purpose: Comprehensive test suite with 1:1 module coverage + differential oracles
- Contains: Unit tests for each module, integration tests for orchestration
- Key files: `test_staging.py` (95KB, largest), `test_manifest.py`, `test_evidence.py`
- Patterns: Standard pytest, fixtures via `tests/fixtures/build_fixtures.py`, differential oracles in `test_*_differential.py` files

**Root entry points:**
- `read_mailbox.py` — Phase 1 CLI + orchestration (acquisition)
- `discover_order.py` — Phase 2 CLI + orchestration (discovery)
- `stage_order.py` — Phase 3 CLI + orchestration (staging)

**`vicmap.toml`:**
- Purpose: Single configuration file for all three phases (only one order ID allowed)
- Sections: `[mailbox]`, `[download]`, `[extraction]`, `[discovery]`, `[database]`
- Note: Database password comes from `VICMAP_DB_PASSWORD` env var, never from config (D-58)

**`artifacts/`:**
- Purpose: Downloaded ZIP files (`Order_{order_id}.zip` + `.provenance.json` sidecar)
- Generated: By Phase 1 (`read_mailbox.py`)
- Committed: No (gitignored)

**`runs/`:**
- Purpose: Extracted layers + `manifest.json` organized by order ID and timestamp
- Directory pattern: `runs/{order_id}/{timestamp}/`
- Generated: By Phase 2 (`discover_order.py`)
- Committed: No (gitignored)

## Key File Locations

**Entry Points:**
- `read_mailbox.py` — Phase 1 acquisition CLI
- `discover_order.py` — Phase 2 discovery CLI
- `stage_order.py` — Phase 3 staging CLI

**Configuration:**
- `vicmap.toml` — Single config file, sourced by all CLIs
- `.envrc` — direnv configuration for shell environment

**Core Logic:**
- `vicmap_acquire/evidence.py` — Event schemas, redaction, validation
- `vicmap_acquire/graph.py` — Graph API adapter
- `vicmap_acquire/candidates.py` — Email parsing + candidate extraction
- `vicmap_acquire/origin.py` — Authentication header validation
- `vicmap_acquire/download.py` — Streaming download + SSRF protection
- `vicmap_acquire/extraction.py` — Safe archive extraction
- `vicmap_acquire/discovery.py` — GIS layer profiling
- `vicmap_acquire/naming.py` — PostgreSQL identifier normalization
- `vicmap_acquire/manifest.py` — Manifest schema + JSON persistence
- `vicmap_acquire/staging.py` — Database connection + ogr2ogr loading

**Testing:**
- `tests/test_evidence.py` — Event schema + redaction tests
- `tests/test_staging.py` — Database loading + privilege validation (95KB)
- `tests/test_manifest.py` — Manifest persistence + digest (56KB)
- `tests/test_candidates.py` — Email parsing + candidate recognition (38KB)
- `tests/test_discovery.py` — Layer profiling
- `tests/test_extraction.py` — Archive safety + member extraction
- `tests/test_download.py` — Download + SSRF/redirect validation
- `tests/test_graph.py` — Graph adapter + metadata iteration
- `tests/test_*_differential.py` — Oracle-based validation tests

## Naming Conventions

**Files:**
- Modules: `lowercase_with_underscores.py` (e.g., `vicmap_acquire/candidates.py`)
- Entry points: `verb_noun.py` (e.g., `read_mailbox.py`, `discover_order.py`, `stage_order.py`)
- Tests: `test_<module>.py` paired with source (e.g., `test_candidates.py` for `candidates.py`)
- Configuration: `vicmap.toml` (single, order-ID specific)

**Directories:**
- Package: `lowercase_with_underscores` (e.g., `vicmap_acquire/`)
- Generated outputs: `lowercase_plural` (e.g., `artifacts/`, `runs/`)
- Testing: `tests/` with `fixtures/` subdirectory

**Python Names:**
- Classes: `PascalCase` (e.g., `ImportManifest`, `SuccessEvent`, `SafeFailure`, `GraphMailbox`)
- Exceptions: `PascalCase` with suffix (e.g., `CandidateError`, `DownloadFailure`, `ArchiveFailure`)
- Functions: `snake_case` (e.g., `verify_artifact`, `discover_layers`, `assign_target_table_names`)
- Constants: `UPPER_SNAKE_CASE` (e.g., `_EXTENSION_DRIVERS`, `MANIFEST_SCHEMA_VERSION`, `PASSWORD_ENV_VAR`)
- Private: Prefix with `_` (e.g., `_EmitOnce`, `_require_fingerprint`, `_is_dataset_member`)

## Where to Add New Code

**New Feature (e.g., add support for new GIS format):**
- Primary code: `vicmap_acquire/discovery.py` (update `_EXTENSION_DRIVERS` dict)
- Processing: `vicmap_acquire/discovery.py:find_datasets()` to add format recognition
- Tests: `tests/test_discovery.py` with new format fixture
- No other modules need changes

**New Validation (e.g., add hostname deny-list):**
- Validation logic: `vicmap_acquire/evidence.py` (add regex pattern + validator function)
- Integration: `vicmap_acquire/staging.py` (re-validate before database use, matching D-41 pattern)
- Re-validation example: WR-06 added `_HOST` regex in both `evidence.py` and `staging.py`
- Tests: `tests/test_evidence.py` + `tests/test_staging.py`

**New Boundary Module (e.g., add cloud storage support):**
- Location: `vicmap_acquire/cloud_storage.py`
- Requirements:
  - No driver imports shared with other boundary modules
  - Define typed exception base (e.g., `CloudStorageFailure`)
  - Every public function returns typed result or raises typed exception
  - No raw driver/API text in exceptions (map to `.code` only)
- Integration: Update orchestration (e.g., `read_mailbox.py:run_acquisition()`) to call new boundary
- Tests: `tests/test_cloud_storage.py` with full error path coverage

**New Entry Point (e.g., add Phase 4 publication step):**
- CLI file: `publish_order.py` (follows `read_mailbox.py`/`discover_order.py` pattern)
- Configuration section: Add `[publication]` to `vicmap.toml`
- Orchestration function: `run_publication(config, *, event_sink)` (matches `run_discovery` signature)
- Config loader: `load_publication_config()` in `read_mailbox.py` (add to `_parse_config()`)
- Tests: `tests/test_publication.py` with orchestration integration test

**New Test Type (e.g., add differential oracle test):**
- Location: `tests/test_<module>_differential.py`
- Pattern: Import independent oracle (e.g., system GIS tool), compare results to our implementation
- Example: `tests/test_html_visibility_differential.py` uses browser engine to validate HTML visibility logic
- No fixtures in differential test; use real data from `tests/fixtures/`

## Special Directories

**`artifacts/`:**
- Purpose: Downloaded ZIP files + provenance sidecars
- Generated: By Phase 1 (`vicmap_acquire/download.py:download_artifact()`)
- Committed: No (in `.gitignore`)
- Retention: Manual cleanup; typically kept for audit trail

**`runs/`:**
- Purpose: Extracted members + `manifest.json` per order/timestamp
- Generated: By Phase 2 (`vicmap_acquire/extraction.py:extract_artifact()`)
- Committed: No (in `.gitignore`)
- Structure: `runs/{order_id}/{YYYYMMDDTHHMMSSZ}/`
- Retention: Referenced by Phase 3; retained for manifest replay

**`.gsd/`:**
- Purpose: GSD operational state (dispatch isolation, state files)
- Generated: By GSD orchestration tools
- Committed: No (in `.gitignore`)

**`.planning/`:**
- Purpose: GSD planning docs + research
- Subdirectories:
  - `codebase/` — Architecture/structure docs (this set)
  - `research/` — Pre-implementation investigation (ARCHITECTURE.md, STACK.md, etc.)
- Committed: Yes (architecture reference)

**`db/`:**
- Purpose: SQLite database for local development (not production)
- Generated: By test suite during setup
- Committed: No (in `.gitignore`)

**`token/`:**
- Purpose: OAuth token cache for Graph API
- Generated: By O365 SDK via `MemoryTokenBackend` (no file persistence in this config)
- Committed: No (in `.gitignore`)

---

*Structure analysis: 2026-09-22*
