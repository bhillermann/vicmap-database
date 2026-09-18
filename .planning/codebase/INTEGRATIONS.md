# External Integrations

**Analysis Date:** 2026-09-18

## APIs & External Services

**Microsoft Graph / Office 365:**
- Microsoft Graph API - Mailbox access for order notifications
  - SDK/Client: O365 2.1
  - Auth: OAuth 2.0 with MSAL (Microsoft Authentication Library)
  - Credentials: `O365_AUTH_ID` (client ID), `O365_AUTH_SECRET` (client secret), `TENANT_ID`
  - Endpoint: https://graph.microsoft.com/v1.0/
  - Usage: Message retrieval from monitored mailbox (`automations@vegetationlink.com.au`)
  - Implementation: `vicmap_acquire/graph.py` (GraphMailbox class)

**DataShare API (Victoria Maps):**
- Email notifications from DataShare service
  - Provider: `noreply@datashare.maps.vic.gov.au`
  - Format: Email messages with download links and provenance metadata
  - Configuration: Monitored via O365 mailbox integration
  - Parsing: `vicmap_acquire/candidates.py` (email validation and extraction)

## Data Storage

**Databases:**
- Not used - this is a stateless acquisition tool

**File Storage:**
- AWS S3 (ap-southeast-2 region)
  - Connection: HTTPS to `s3.ap-southeast-2.amazonaws.com`
  - Bucket: `cl-isd-prd-datashare-s3-delivery`
  - Access: Temporary signed URLs provided in email notifications (no permanent credentials)
  - Download client: requests library with stream processing
  - Implementation: `vicmap_acquire/download.py` (download_artifact function)
  - Configuration: `vicmap.toml` sections `[download]`
    - `allowed_hosts`: ["s3.ap-southeast-2.amazonaws.com"]
    - `allowed_url_prefixes`: ["https://s3.ap-southeast-2.amazonaws.com/cl-isd-prd-datashare-s3-delivery/"]
    - `max_bytes`: 10 GB per artifact
    - `connect_timeout_seconds`: 10
    - `read_timeout_seconds`: 60
    - `max_redirects`: 5

**Local File Storage:**
- Artifact directory: `artifacts/` - Downloaded ZIP files and provenance sidecars
- Run directory: `runs/` - Extracted geospatial datasets organized by order ID
- Configuration: `vicmap.toml` sections `[download]` and `[extraction]`

**Caching:**
- Not used - single-pass acquisition with no caching layer

## Authentication & Identity

**Auth Provider:**
- Microsoft Entra (Azure AD) - OAuth 2.0 authorization code flow
  - Implementation: `vicmap_acquire/graph.py` (GraphMailbox uses O365.Account with MemoryTokenBackend)
  - Token storage: In-memory only (no persistent token cache)
  - Scopes: Mail.Read (implicit in O365 SDK)

**Email Signing & Origin Verification:**
- DKIM (DomainKeys Identified Mail) - Email signature validation
- DMARC (Domain-based Message Authentication, Reporting and Conformance) - Domain authentication
- SPF (Sender Policy Framework) - IP validation (checked via Authentication-Results header)
- CompAuth - Microsoft Entra-specific authentication header
- Implementation: `vicmap_acquire/origin.py` (verify_authenticated_origin function)
- Configuration: `vicmap.toml` `[mailbox]` `required_authentication_results`: ["dkim", "dmarc", "compauth"]

## Monitoring & Observability

**Error Tracking:**
- Not integrated - errors surface through exit codes and exception messages

**Logs:**
- Standard output/stderr via Python logging module
- Logging configuration: `vicmap_acquire/graph.py` (_suppress_provider_logging function disables verbose dependency logging)
- Log suppression: O365, msal, requests, urllib3 loggers set to CRITICAL+1

## CI/CD & Deployment

**Hosting:**
- Not a deployed service - CLI utility for local/scheduled acquisition

**CI Pipeline:**
- Not configured - manual test execution via `python -m unittest discover`

## Environment Configuration

**Required env vars:**
- `O365_AUTH_ID` - Microsoft Entra application (client) ID
- `O365_AUTH_SECRET` - Client secret for application authentication
- `TENANT_ID` - Microsoft Entra tenant ID for multi-tenant OAuth resolution
- `OPNIX_ENV_TOKEN_FILE` - Path to opnix token file for secrets retrieval (defaults to `$HOME/.config/opnix/token`)

**Secrets location:**
- 1Password vault (accessed via opnix)
  - `op://nixos-services/o365_app_credentials/username` → `O365_AUTH_ID`
  - `op://nixos-services/o365_app_credentials/password` → `O365_AUTH_SECRET`
  - `op://nixos-services/o365_app_credentials/tenant_id` → `TENANT_ID`
- Configuration: `flake.nix` lines 13-18 (opnixEnvConfig)

## Webhooks & Callbacks

**Incoming:**
- None - system polls mailbox via O365 API

**Outgoing:**
- None - system reads only, does not write to external services

## Email Protocol Details

**Mailbox Monitoring:**
- Protocol: HTTP REST via Microsoft Graph API (not IMAP/POP3)
- Folder: Inbox (configurable via `vicmap.toml` `[mailbox]` `folder`)
- Lookback: 15 days configurable via `lookback_days` parameter
- Filtering: 
  - Allowed senders: ["noreply@datashare.maps.vic.gov.au"]
  - Allowed order IDs: ["OK0VUZ"] (configurable via `allowed_order_ids`)
  - Sender authentication required: DKIM, DMARC, CompAuth (configurable)

## Geospatial Data Services

**OGR/GDAL Drivers:**
- ogrinfo command-line tool - Layer discovery and metadata extraction
- Timeout: 60 seconds per operation (configurable via `vicmap.toml` `[discovery]` `ogrinfo_timeout_seconds`)
- Implementation: `vicmap_acquire/discovery.py` (subprocess calls to system ogrinfo)
- Supported formats: OpenFileGDB, ESRI Shapefile, GPKG, MapInfo File, DXF (extension-to-driver map in `discovery.py`)

---

*Integration audit: 2026-09-18*
