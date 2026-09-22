# External Integrations

**Analysis Date:** 2026-09-22

## APIs & External Services

**Microsoft 365 / Exchange Online:**
- **Service:** Microsoft Graph API (mailbox reading)
- **What it's used for:** Reading incoming acquisition orders from `automations@vegetationlink.com.au` mailbox
- **SDK/Client:** `python-o365` 2.1 (O365 library)
- **Auth:** OAuth 2.0 via Azure AD
  - Client ID: `O365_AUTH_ID` (environment variable, from opnix/1Password)
  - Client Secret: `O365_AUTH_SECRET` (environment variable, from opnix/1Password)
  - Tenant ID: `TENANT_ID` (environment variable, from opnix/1Password)
- **Implementation:** `vicmap_acquire/graph.py` - `GraphMailbox` class wraps O365 SDK with memory-only OAuth token backend
- **Entry points:**
  - `read_mailbox.py` - CLI orchestration for mailbox scanning
  - `vicmap_acquire/graph.py` - Low-level Graph API integration with redaction-aware error handling

**Vicmap DataShare (Imagery/Cadastre Source):**
- **Service:** External order notifications via email from `noreply@datashare.maps.vic.gov.au`
- **What it's used for:** Notifies operator of available geospatial data updates (provides download URL)
- **Auth:** Message authentication via DKIM, DMARC, compauth (verified in email headers)
- **Implementation:** `vicmap_acquire/origin.py` - `OriginPolicy` validates sender domain and authentication results
- **Configuration:** `vicmap.toml` - `[mailbox]` section:
  - `allowed_senders = ["noreply@datashare.maps.vic.gov.au"]`
  - `required_authentication_results = ["dkim", "dmarc", "compauth"]`

## Data Storage

**PostgreSQL Database:**
- **Type:** PostgreSQL 11+ with PostGIS extension
- **Purpose:** Stores staged geographic feature data before publication
- **Connection:** TCP/IP to host `127.0.0.1` (configurable)
- **Connection Details:**
  - Hostname: configurable via `database.host` in `vicmap.toml` (default: `127.0.0.1`)
  - Port: configurable via `database.port` (default: `5432`)
  - Database name: `vicmap`
  - Username: `vicmap_loader`
  - Password: `VICMAP_DB_PASSWORD` environment variable (from opnix/1Password, never in config)
  - Connection timeout: configurable (default: 10 seconds)
  - Statement timeout: configurable (default: 3600 seconds / 1 hour)
- **Client:** `psycopg` 3.3.4
- **Implementation:** `vicmap_acquire/staging.py` - Only module permitted to import PostgreSQL driver
- **Schemas:**
  - `vicmap_staging` - Temporary tables for ingestion verification
  - `vicmap` (publish_schema) - Final published feature data
- **Features:**
  - ogr2ogr integration for geographic feature loading
  - PostGIS geometry columns (`geom` with target SRID 7899 / VicGrid94)
  - Primary index on `pfi` (Parcel Fabric Index)
  - Row validation post-load

**File Storage:**
- **Type:** AWS S3 (object storage)
- **Purpose:** Temporary staging for downloaded geospatial artifacts
- **Endpoint:** `s3.ap-southeast-2.amazonaws.com` (AP Southeast 2 region)
- **Bucket:** `cl-isd-prd-datashare-s3-delivery/` (inferred from allowed URL prefix)
- **Access:** Public HTTPS downloads (no AWS credentials stored; presigned URLs in email)
- **Implementation:** `vicmap_acquire/download.py` - `download_artifact()` function with SSRF mitigation
- **Configuration:** `vicmap.toml` - `[download]` section:
  - `allowed_hosts = ["s3.ap-southeast-2.amazonaws.com"]`
  - `allowed_url_prefixes = ["https://s3.ap-southeast-2.amazonaws.com/cl-isd-prd-datashare-s3-delivery/"]`
  - `max_bytes = 10737418240` (10 GiB total download limit)
- **Local staging:** Downloaded to `artifacts/` directory (configurable)

**Caching:**
- None (stateless HTTP downloads with SHA256 verification)

## Authentication & Identity

**Auth Provider:**
- **Primary:** Microsoft 365 / Azure Active Directory
  - OAuth 2.0 client credentials flow
  - Token managed in-memory (MemoryTokenBackend in python-o365)
  - No persistent token storage

**Email Authentication (Inbound):**
- **Methods:** DKIM, DMARC, compauth (SPF/DMARC composite)
- **Validator:** `vicmap_acquire/origin.py` - Parses email `Authentication-Results` headers
- **Policy:** `vicmap.toml` - `[mailbox]` section declares required methods
- **Implementation:** Mail server authenticates sender; application verifies headers

**Secrets Management:**
- **Provider:** 1Password (via opnix integration)
- **Secrets stored:**
  - O365 application credentials (client ID, secret)
  - O365 tenant ID
  - PostgreSQL loader password
- **Injection:** opnix populates environment variables at shell startup
- **Token location:** `$HOME/.config/opnix/token` (opnix credential file)

## Geographic Data Services

**PROJ (Cartographic Projections):**
- **Purpose:** Coordinate reference system transformations (GDA94 → GDA2020 for VicGrid)
- **Version:** 9.8.1+ (via nixpkgs)
- **Special Configuration:** Vendored ICSM NTv2 grid `au_icsm_GDA94_GDA2020_conformal_and_distortion.tif`
  - Grid fetched at build time via `pkgs.fetchurl` with SHA256 pinning
  - Merged into single `projDataDir` with `proj.db`
  - `PROJ_DATA` environment variable set in shell hook
- **Client:** `pyproj` 3.7.2 (Python binding)
- **Implementation:** `vicmap_acquire/discovery.py` uses `pyproj` for CRS resolution
- **Network:** No runtime network access (grid vendored locally)

**GDAL/OGR (Geographic Data I/O):**
- **Purpose:** Reading/writing multiple geospatial formats
- **CLI Tools:** `ogrinfo` (format discovery), `ogr2ogr` (format conversion and PostgreSQL load)
- **Supported read formats:** OpenFileGDB, ESRI Shapefile, GeoPackage, MapInfo File, DXF
- **Write target:** PostgreSQL PostGIS (via ogr2ogr)
- **Implementation:** 
  - `vicmap_acquire/discovery.py` - Uses `ogrinfo -json` subprocess for layer schema discovery
  - `vicmap_acquire/staging.py` - Invokes `ogr2ogr` to load features into PostGIS
- **Timeout:** configurable (default: 60 seconds for discovery)

**pyogrio:**
- **Purpose:** Pure Python geographic file I/O without subprocess overhead
- **What it does:** Reads layer metadata (feature count, geometry type, CRS) without materializing all features
- **Implementation:** `vicmap_acquire/discovery.py` - `read_info()` for fast schema discovery
- **Version:** Via nixpkgs (pinned)

## Monitoring & Observability

**Error Tracking:**
- None integrated (errors are closed-failure exceptions with machine-readable `.code` attributes)

**Logs:**
- **Approach:** Python stdlib `logging` module
- **Redaction:** Provider logger names (O365, msal, requests, urllib3) set to CRITICAL+1 to suppress sensitive HTTP diagnostics
- **Implementation:** `vicmap_acquire/graph.py` - `_suppress_provider_logging()` function
- **Events:** Application logs structured failure/progress/success events with `ReasonCode` enums

**Event Sinks:**
- Configuration-driven in `read_mailbox.py` via `EventSink` callback
- Can route events to stdout, files, or external systems (not hardcoded)

## CI/CD & Deployment

**Hosting:**
- Not detected (this is a data acquisition CLI tool, not a deployed service)

**CI Pipeline:**
- Not detected (no GitHub Actions, GitLab CI, or CircleCI configuration found)

**Local Development:**
- Nix Flakes for reproducible environment
- direnv for automatic environment activation
- Manual test execution via `python -m unittest discover`

**Provisioning:**
- Database: `db/provision_vicmap_loader.sql` (manual operator-run SQL from dev shell)
- PostGIS must be pre-installed on target PostgreSQL instance

## Webhooks & Callbacks

**Incoming:**
- None (acquisition triggered by operator CLI, not webhooks)

**Outgoing:**
- None (read-only integration; no status callbacks to external systems)

## Environment & Secrets Rotation

**Development Shell Setup:**
```bash
# .envrc triggers:
use flake                                    # Load Nix flake
export OPNIX_ENV_TOKEN_FILE=$HOME/.config/opnix/token
# flake.nix shell hook runs:
opnix env -config-json <config> -token-file $OPNIX_ENV_TOKEN_FILE
# This populates O365_AUTH_ID, O365_AUTH_SECRET, TENANT_ID, VICMAP_DB_PASSWORD
export PROJ_DATA="${projDataDir}"            # Single merged PROJ directory
```

**Required 1Password Setup (per 03-01-USER-SETUP.md):**
- Item: `op://nixos-services/o365_app_credentials/`
  - Fields: `username` (client ID), `password` (client secret), `tenant_id`
- Item: `op://nixos-services/vicmap_loader_credentials/`
  - Fields: `password` (PostgreSQL password)

**No Secrets in Source:**
- `.env` files: Not used
- `vicmap.toml`: No credential keys by design (D-58)
- Version control: Never stores secrets

## Request/Response Flow (Simplified)

1. Operator runs `python read_mailbox.py`
2. opnix populates `O365_AUTH_*` and `TENANT_ID` from 1Password
3. Application authenticates to Microsoft Graph via O365 library
4. Scans `automations@vegetationlink.com.au` Inbox for messages from allowed senders
5. Validates message authentication (DKIM/DMARC/compauth) via email headers
6. Extracts download URL from message body
7. Downloads artifact from S3 via presigned HTTPS URL (size/timeout bounded)
8. Verifies SHA256 checksum against `.provenance.json` sidecar
9. Extracts ZIP to `runs/<run_id>/` directory
10. Discovers geospatial layers via `ogrinfo` + `pyogrio`
11. Stages layers into PostgreSQL `vicmap_staging` schema via `ogr2ogr`
12. Validates row counts and geometry
13. Publishes to `vicmap` (publish_schema) on success

---

*Integration audit: 2026-09-22*
