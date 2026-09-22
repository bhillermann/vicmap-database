# Technology Stack

**Analysis Date:** 2026-09-22

## Languages

**Primary:**
- Python 3.x - All core application logic and CLI entry points

**Configuration/Data:**
- TOML - Configuration files (`vicmap.toml`)
- JSON - Data formats (provenance sidecars, discovery results)
- SQL - Database schemas and queries (PostgreSQL)

## Runtime

**Environment:**
- Python 3 (via nixpkgs)
- Linux x86_64, Linux aarch64, macOS x86_64, macOS aarch64 (via Nix multi-platform support)

**Package Manager:**
- Nix Flakes - Development environment and dependency management
- Lockfile: `flake.lock` (present)

## Frameworks & Core Libraries

**Geographic Data Processing:**
- `pyogrio` [version managed by nixpkgs] - Reading/writing geographic file formats (Shapefile, GeoPackage, GeoJSON, OpenFileGDB)
- `pyproj` [version managed by nixpkgs] - Cartographic projection transformations
- `PROJ` [9.8.1+] - Projection library with vendored ICSM GDA94<->GDA2020 grid

**Database:**
- `psycopg` [3.3.4] - PostgreSQL connection and query execution
- PostgreSQL client tools - CLI (`psql`) for administrative tasks

**Authentication & Office Integration:**
- `python-o365` [2.1] - Microsoft 365/Exchange API client (built locally in flake)
- `msal` [dependency of python-o365] - Microsoft Authentication Library
- `requests-oauthlib` [dependency of python-o365] - OAuth 1/2 support

**HTTP & Data Handling:**
- `requests` [version via nixpkgs] - HTTP client for S3 downloads
- `html5lib` [version via nixpkgs] - HTML parsing (used by python-o365)
- `beautifulsoup4` [dependency of python-o365] - HTML/XML parsing
- `python-dateutil` [dependency of python-o365] - Date parsing utilities
- `tzdata`, `tzlocal` [dependencies of python-o365] - Timezone handling

**Archive Handling:**
- `zipfile` [stdlib] - ZIP archive extraction

**Command-Line & CLI:**
- `argparse` [stdlib] - CLI argument parsing

**Archive/Compression:**
- `GDAL`/`ogr2ogr` [via nixpkgs] - Geographic data format conversion and loading CLI tools

## Key Dependencies

**Critical (directly imported):**
- `psycopg` - PostgreSQL access; only module permitted to import a PostgreSQL driver (enforced via test policy)
- `pyogrio` - Geographic format discovery and reading
- `pyproj` - CRS resolution and coordinate transformations
- `python-o365` - Microsoft 365 mailbox integration
- `requests` - HTTP downloads from AWS S3
- `PROJ` - Cartographic transformation engine with vendor-specific grids

**Supporting:**
- `html5lib` - Office document parsing
- `GDAL/ogr2ogr` - CLI for geographic data loading into PostGIS
- `tzdata` - Timezone database for datetime handling

## Configuration

**Environment Variables (Required at Runtime):**
- `O365_AUTH_ID` - Microsoft 365 application client ID (from opnix/1Password)
- `O365_AUTH_SECRET` - Microsoft 365 application client secret (from opnix/1Password)
- `TENANT_ID` - Microsoft 365 tenant ID (from opnix/1Password)
- `VICMAP_DB_PASSWORD` - PostgreSQL `vicmap_loader` user password (from opnix/1Password)
- `OPNIX_ENV_TOKEN_FILE` - Path to opnix token for secrets management (default: `$HOME/.config/opnix/token`)

**Configuration Files:**
- `vicmap.toml` - Single source of truth for all operational policies:
  - `[mailbox]` - Email source (address, folder, sender allowlist, order ID filters, authentication requirements)
  - `[download]` - S3 download policy (allowed hosts, size limits, timeouts, fingerprint length)
  - `[extraction]` - Archive extraction limits (total/member size, compression ratio)
  - `[discovery]` - Geographic format discovery (supported formats, timeout)
  - `[database]` - PostgreSQL connection and schema configuration (host, port, schema names, target SRID, index configuration)

**Build/Dev Configuration:**
- `flake.nix` - Nix development environment and dependency declarations
- `.envrc` - direnv configuration pointing to Nix flake and opnix token file

## Secrets Management

**Secrets Provider:**
- 1Password - via opnix integration
- Secrets are injected as environment variables only, never stored in configuration files or versioned code
- `opnix` tool retrieves secrets from 1Password item references at shell startup

**Development Shell Setup:**
- Shell hook in `flake.nix` runs `opnix env` to populate `O365_AUTH_ID`, `O365_AUTH_SECRET`, `TENANT_ID`, and `VICMAP_DB_PASSWORD`
- Token file path: `$HOME/.config/opnix/token`

## PROJ Data & Geographic Grids

**Special Handling:**
- Vendored ICSM GDA94<->GDA2020 transformation grid via `pkgs.fetchurl` with pinned hash
- Single merged `PROJ_DATA` directory (`projDataDir` in `flake.nix`) containing both `proj.db` and the vendored grid
- `PROJ_DATA` environment variable explicitly set in shell hook (required for pyproj to locate grid files)
- PROJ 9.8.1 does not support colon-joined `PROJ_DATA` lists; only single directory works

## Platform Requirements

**Development:**
- Nix package manager with Flakes support
- direnv (for `.envrc` integration)
- 1Password account access + opnix token
- Supported architectures: x86_64-linux, aarch64-linux, aarch64-darwin, x86_64-darwin

**Production/Runtime:**
- Python 3
- PostgreSQL 11+ (for PostGIS)
- Network access to:
  - Microsoft 365 Graph API (`login.microsoft.com`, `graph.microsoft.com`)
  - AWS S3 (`s3.ap-southeast-2.amazonaws.com`)
- PostGIS-enabled database schema

## Testing Framework

**Test Runner:**
- `unittest` [stdlib] - Standard library test framework
- `unittest.mock` - Mocking framework (MagicMock, Mock, patch)
- No external test framework (pytest/pytest not used)

**Test Execution:**
- Standard Python unittest discovery: `python -m unittest discover`
- Tests skip gracefully when optional dependencies unavailable (e.g., psycopg when PostgreSQL unreachable)

---

*Stack analysis: 2026-09-22*
