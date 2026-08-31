# Codebase Concerns

**Analysis Date:** 2026-08-31

## Risk Summary

| Severity | Area | Current evidence | Impact |
|---|---|---|---|
| Critical | Credential handling | `token/my_token.txt` exists at mode `0644`, and no `.gitignore` exists | A Graph access token can be read by other local users and is one accidental `git add` away from version history |
| High | Repository integrity | The `main` branch has no commits and every project artifact is untracked | There is no recoverable baseline, review history, or reliable way to distinguish intended files from local state |
| High | Product completeness | `read_mailbox.py` only lists mailbox messages; no Vicmap ingestion or PostGIS code exists | The refresh outcome described by `flake.nix` cannot currently be performed |
| High | Data disclosure | `read_mailbox.py` prints every returned message object to standard output | Mail metadata or content may enter terminals, shell capture, CI logs, or monitoring systems |
| High | Verification | No tests, CI, linting, typing, or Nix checks exist | Authentication and mailbox behavior can regress without detection |
| Medium | Runtime correctness | Message retrieval occurs twice, while the result of the first limited query is unused | The script makes redundant remote calls and the printed set does not honor the stated `limit=500` |
| Medium | Operability | All application work happens at module import time | Imports can authenticate and access production mail, preventing safe reuse and isolated testing |

## Security and Privacy

- `token/my_token.txt` is a populated O365 filesystem token backend stored inside the repository tree. Its mode is `0644`, so it is readable beyond the owner; move runtime tokens outside the checkout and restrict them to owner-only permissions.
- The empty root-level `my_token.txt`, `.config/`, `.direnv/`, `.envrc`, and `token/` are all untracked because there is no `.gitignore`. Add deny rules before establishing the first commit, and explicitly verify the staged file list.
- Do not treat an untracked token as safe: with no commit history or ignore policy, ordinary bulk staging can permanently expose `token/my_token.txt`.
- `read_mailbox.py` prints `message` objects without redaction. Depending on SDK representation, this can disclose senders, subjects, identifiers, timestamps, or content; operational output should use an explicit allowlist of non-sensitive fields.
- `flake.nix` injects `O365_AUTH_SECRET` and related values into the interactive shell environment via `eval "$(opnix env ...)"`. Child processes inherit those values, and any compromise of the shell session gains access to them.
- `.envrc` names a persistent opnix token under `$HOME/.config/opnix/token`; access control and rotation are outside repository enforcement. A documented bootstrap and revocation procedure is absent.
- The account uses application credentials and `https://graph.microsoft.com/.default`, so effective access is determined by tenant-granted application permissions rather than the unused `SCOPES = ['basic', 'mailbox']`. The code contains no least-privilege validation.
- The mailbox resource `automations@vegetationlink.com.au` is hard-coded in `read_mailbox.py`, making accidental production access the default behavior in every environment.

## Correctness and Fragility

- `read_mailbox.py` calls `inbox.get_messages(limit=500)` and stores the lazy/result object in `count`, then ignores it and loops over a second `inbox.get_messages()` call. The second call uses SDK defaults, so the name `count` is misleading and the requested 500-message bound does not govern processing.
- `SCOPES` is declared but never passed to authentication. The actual scope is a separate hard-coded `.default` value, leaving configuration that appears authoritative but has no effect.
- The missing-variable exception says to configure `MS_APP_ID`, `MS_APP_SECRET`, and `MS_TENANT_ID`, while the code actually reads `O365_AUTH_ID`, `O365_AUTH_SECRET`, and `TENANT_ID`. Following the error guidance will not fix startup.
- Configuration validation only distinguishes `None`; empty strings are accepted and fail later inside the SDK with less actionable errors.
- Account construction, token loading, authentication, mailbox lookup, folder lookup, retrieval, and output execute at import time. There is no `main()` guard, dependency boundary, or safe dry-run path.
- `FileSystemTokenBackend(token_path='token', ...)` is relative to the current working directory. Launching the script outside the repository root silently selects a different token location.
- Authentication success is printed but not enforced before mailbox access. The script has no explicit failure path when `authenticate()` returns false or authentication state remains invalid.
- There is no handling for a missing `Inbox`, unavailable mailbox, expired/revoked token, throttling, pagination failure, transient Graph errors, or partial retrieval.
- No timeout, retry/backoff policy, structured error classification, or exit-code contract is owned by the application; behavior depends entirely on SDK defaults.
- The script has no checkpoint, delta-query state, message identity ledger, or idempotency mechanism. Repeated runs enumerate overlapping mail and cannot reliably distinguish new automation requests from already processed ones.

## Missing Core Capabilities

- No code parses mailbox messages or attachments, validates senders, identifies requested Vicmap products, or rejects malformed/untrusted requests.
- No Vicmap source endpoint, download client, checksum verification, archive extraction, schema validation, or provenance record exists.
- No PostgreSQL driver, PostGIS dependency, connection configuration, SQL schema, staging table, transaction, load routine, index creation, or atomic table-swap implementation exists.
- No coordinate reference system validation or transformation tooling is declared, despite spatial data correctness depending on CRS handling.
- No refresh orchestration, scheduler, lock/concurrency control, restart/resume behavior, rollback path, retention policy, or audit trail exists.
- No success/failure notification exists, so an operator cannot distinguish an empty inbox, a partial run, and a successful database refresh.
- `flake.nix` describes a “Vicmap -> PostGIS refresh,” but the current executable stops at printing mailbox messages; this gap should be treated as unimplemented product scope, not technical polish.

## Performance and Scalability

- The duplicate `get_messages()` calls add a full unnecessary Microsoft Graph request path on every run and may double query cost once either result is consumed.
- Printing messages synchronously does not provide batching, backpressure, bounded concurrency, or durable progress; a large mailbox will be slow and noisy.
- The current code does not make pagination behavior explicit. Processing volume therefore depends on O365 SDK defaults and can silently omit messages beyond the first page/result limit.
- A future geospatial refresh has no staging strategy or resource budget. Loading large layers directly into destination tables would risk long locks, excessive disk use, and partial visible state.
- There are no metrics for message count, bytes downloaded, feature count, load duration, database size, retries, or failures, preventing capacity planning and regression detection.

## Dependency and Environment Risks

- `flake.nix` builds O365 `2.1` from a GitHub tag and sets `doCheck = false`; upstream tests are bypassed, so incompatibilities with the selected Python and transitive packages are not detected at build time.
- `nixpkgs` follows `nixos-unstable`. `flake.lock` currently pins a realization, but lock updates can introduce broad runtime changes without any automated compatibility suite.
- The custom O365 derivation manually declares propagated dependencies. Changes in upstream metadata or runtime imports can leave the derivation incomplete until a live execution fails.
- The project declares four CPU/OS targets in `flake.nix`, but there is no CI matrix or smoke-test evidence that the shell and custom package work on any of them.
- The environment is development-only: there is no package output, service definition, container, deployment unit, or production dependency boundary.
- `opnix` is a GitHub flake input that participates directly in secret injection. Its revision is pinned, but there is no documented update/review policy for this privileged dependency.

## Testing and Quality Gaps

- There are zero repository tests and no configured test runner; effective behavior coverage is unmeasured.
- There are no fakes for Graph, synthetic token fixtures, environment validation tests, authentication branch tests, pagination tests, or output-redaction tests.
- There is no opt-in integration test against a dedicated non-production mailbox; running `read_mailbox.py` instead targets the hard-coded production mailbox.
- `flake.nix` exposes no `checks` output, and no CI configuration exists, so even Python syntax is not automatically checked.
- No formatter, linter, type checker, dependency vulnerability scan, or secret scanner is configured.
- There is no README, runbook, configuration example, data contract, or recovery procedure. Operational knowledge exists only implicitly in `flake.nix`, `.envrc`, and `read_mailbox.py`.

## Practical Mitigation Order

1. Protect secrets first: move the token backend outside the checkout, set owner-only permissions, add a strict `.gitignore`, rotate the existing token if it may have been exposed, and inspect staged files before the initial commit.
2. Make mailbox access explicit: introduce validated configuration, a `main()` boundary, injectable O365 collaborators, a non-production default, redacted structured logging, and one bounded/paginated retrieval path.
3. Establish a trustworthy baseline: commit reviewed source-only files, add deterministic unit tests and Nix checks, then add CI and secret scanning.
4. Define the ingestion contract before implementation: accepted senders/message format, attachment/source validation, target layers, CRS rules, database schema, idempotency key, transactional swap, and failure/rollback semantics.
5. Add production controls with the loader: locking, staging-space checks, timeouts, retry/backoff, checkpoints, metrics, audit records, and notifications.

---

**Refreshed:** 2026-08-31
