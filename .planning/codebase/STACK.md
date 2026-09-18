# Technology Stack

**Analysis Date:** 2026-09-18

## Languages

**Primary:**
- Python 3 - Complete acquisition pipeline, CLI orchestration, geospatial processing, and testing

## Runtime

**Environment:**
- Python 3.14.7 (via Nix flakes)

**Package Manager:**
- Nix flakes only — no pip, `requirements.txt`, or `pyproject.toml` in this repo. Python
  dependencies are declared in `flake.nix` via `python3.withPackages`.
- Lockfile: `flake.lock` pins the reproducible environment

## Frameworks

**Core:**
- O365 2.1 - Microsoft Graph API client for Office 365 mailbox access and OAuth integration
- requests - HTTP client for artifact downloads and API calls
- GDAL/OGR - Geospatial vector data reading and processing

**Geospatial:**
- pyogrio - Python bindings for OGR for layer discovery and metadata extraction (`vicmap_acquire/discovery.py`)
- pyproj - Coordinate system transformations and projections (`vicmap_acquire/discovery.py`)

**Data Processing:**
- beautifulsoup4 - HTML parsing for email content validation
- html5lib - HTML5 parser for email origin verification (`vicmap_acquire/candidates.py`)
- python-dateutil - Date/time parsing and manipulation

**Authentication:**
- msal (Microsoft Authentication Library) - OAuth 2.0 token acquisition for O365
- requests-oauthlib - OAuth support in requests library
- O365.utils.token.MemoryTokenBackend - In-memory OAuth token storage (`vicmap_acquire/graph.py`)

**Testing:**
- unittest (Python standard library) - Test framework for all test modules (`tests/test_*.py`)

**Build/Dev:**
- Nix Flakes - Declarative development environment and dependency management (`flake.nix`)
- direnv - Automatic environment activation via `.envrc`

## Key Dependencies

**Critical:**
- O365 2.1 - Provides authenticated access to Office 365 mailbox; blocks entire acquisition pipeline if unavailable. Dependencies: requests, requests-oauthlib, msal, tzlocal, tzdata, beautifulsoup4, python-dateutil
- requests - HTTP client for downloading artifacts from AWS S3 and handling redirects/timeouts
- pyogrio - Vector data discovery without materializing full datasets; critical for layer enumeration in `vicmap_acquire/discovery.py`
- pyproj - Coordinate system metadata extraction from geospatial datasets

**Infrastructure:**
- GDAL - System-level library providing OGR tools (ogrinfo CLI) and spatial data driver support
- tzdata - Timezone database for date normalization across UTC contexts

## Configuration

**Environment:**
- Configuration file: `vicmap.toml` - TOML-based configuration for mailbox, download policy, extraction policy, and discovery settings
- Environment variables: `O365_AUTH_ID`, `O365_AUTH_SECRET`, `TENANT_ID` - Microsoft entra credentials for OAuth, managed via opnix secrets integration
- Secrets management: opnix (`flake.nix` lines 13-18) - External secrets provider pulling from 1Password vaults
- Token file: `.config/opnix/token` - opnix authentication token for secrets retrieval

**Build:**
- `flake.nix` - Nix flakes manifest defining Python environment, dependencies, shell hooks, and secrets configuration
- `flake.lock` - Nix flakes lockfile ensuring reproducible builds

## Platform Requirements

**Development:**
- Nix (with flakes support enabled)
- direnv (optional, enabled via `.envrc`)
- Git (for version control)
- 1Password CLI or opnix token access (for secrets)

**Runtime:**
- Python 3.x
- GDAL system library (liboct, libproj)
- Network access to Microsoft Graph API (graph.microsoft.com)
- Network access to AWS S3 (s3.ap-southeast-2.amazonaws.com)

**Testing:**
- Python unittest runner (built-in)
- Test fixtures stored in `tests/fixtures/`

---

*Stack analysis: 2026-09-18*
