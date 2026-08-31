# External Integrations

**Analysis Date:** 2026-08-31

## Integration Overview

- Two external services are implemented: 1Password-backed secret retrieval through opnix, and Microsoft 365 mailbox access through the Microsoft Graph API via the O365 Python library.
- A PostGIS refresh is named in the `flake.nix` description, but there is no database driver, connection configuration, SQL, schema, or database call in the current repository.
- No Vicmap endpoint, WFS service, download URL, webhook, queue, scheduler, cloud runtime, or notification integration is configured.

## Microsoft 365 and Microsoft Graph

- `read_mailbox.py` creates an `O365.Account` using application credentials from `O365_AUTH_ID` and `O365_AUTH_SECRET`, with the directory identifier supplied by `TENANT_ID`.
- Authentication uses `auth_flow_type='credentials'`, so this is an app-only/client-credentials integration rather than an interactive delegated-user flow.
- The requested authentication scope is `https://graph.microsoft.com/.default`; effective permissions therefore come from the app registration's pre-consented Microsoft Graph application permissions.
- The script targets the shared/user mailbox resource `automations@vegetationlink.com.au`, opens its `Inbox`, and iterates messages returned by the O365 library.
- `SCOPES = ['basic', 'mailbox']` is declared but unused; the actual call passes the Graph `.default` scope directly.
- The code calls `get_messages(limit=500)` once and discards that result, then calls `get_messages()` again without the limit; planners should treat the first call as redundant rather than as an enforced processing cap.
- Messages are printed as object representations only. Attachments, sender filtering, subject matching, received-time watermarks, pagination policy, idempotency, and downstream processing are not implemented.

## Microsoft Authentication State

- `O365.FileSystemTokenBackend` persists authentication state to `token/my_token.txt`, using a path relative to the process working directory.
- A second root-level `my_token.txt` exists but is not referenced by `read_mailbox.py`; it should not be treated as part of the active token path.
- The active token file is a sensitive local artifact and must not be committed, copied into documentation, or emitted in diagnostic output.
- If `account.is_authenticated` is false, `account.authenticate(...)` runs and prints only its result; the program does not stop explicitly when the result is false.
- App-only access requires tenant admin consent and an application access policy/configuration that permits the target mailbox where applicable.

## 1Password and opnix

- `flake.nix` obtains `O365_AUTH_ID`, `O365_AUTH_SECRET`, and `TENANT_ID` from the 1Password item `nixos-services/o365_app_credentials`.
- The 1Password fields used are `username`, `password`, and `tenant_id`, respectively; these names are an operational contract between the flake and the vault item.
- opnix receives its service token from `OPNIX_ENV_TOKEN_FILE`, defaulting in the shell hook to `$HOME/.config/opnix/token`.
- `.envrc` sets the same token-file location before invoking the flake, coupling local startup to a user-level credential file.
- `OPNIX_ENV_DISABLE` bypasses injection. When it is used, callers must supply all three Microsoft variables by another secure mechanism.
- Secret values are materialized as process environment variables by `eval "$(opnix env ...)"`; avoid shell tracing, environment dumps, and verbose process wrappers around activation.

## Database and Vicmap Boundaries

- PostgreSQL/PostGIS is an intended destination only, inferred from the flake description; no host, port, database name, role, password, SSL mode, schema, extension, or migration mechanism is defined.
- No Python PostgreSQL adapter such as psycopg, asyncpg, or SQLAlchemy is installed.
- No source endpoint or credentials exist for Vicmap data, and no HTTP/WFS client behavior is implemented outside the transitive `requests` dependency used by O365.
- Planning must establish both source acquisition and PostGIS write contracts before treating the repository as a refresh pipeline.

## Failure Handling and Observability

- Startup fails fast with `ValueError` if any of the three Microsoft environment variables is absent, although the error text incorrectly names them as `MS_APP_ID`, `MS_APP_SECRET`, and `MS_TENANT_ID`.
- opnix failures occur during shell activation because the shell hook evaluates its output; there is no project-owned recovery path or structured diagnostic.
- Microsoft authentication, folder lookup, Graph network errors, permission errors, throttling, paging failures, and token-file corruption are not caught in `read_mailbox.py` and therefore terminate through library exceptions.
- There is no timeout, retry/backoff policy, circuit breaker, dead-letter storage, checkpoint, transaction, or resumability logic.
- There is no structured logging or metrics; console output consists of shell activation text, an optional authentication result, and message representations.
- There are no webhooks. Mailbox access is polling performed only when the script is invoked.
- Future integration code should validate configuration names consistently, fail on unsuccessful authentication, bound mailbox queries, record a durable processing watermark, and redact all credential/token material.
- Future PostGIS refresh work should use transactions and staging/swap semantics with explicit cleanup and retry behavior; none of those guarantees are present today.

---
*External integrations analysis refreshed: 2026-08-31*
