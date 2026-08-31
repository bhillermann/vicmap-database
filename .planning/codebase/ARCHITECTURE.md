# Architecture

**Analysis date:** 2026-08-31
**Refreshed:** 2026-08-31

## Architectural Pattern

The repository is currently a single-script integration prototype, not yet a layered Vicmap-to-PostGIS application.
Runtime behavior is concentrated in `read_mailbox.py`; environment construction and secret injection are defined in `flake.nix` and `.envrc`.
The effective pattern is procedural orchestration over the third-party `O365` SDK, with configuration supplied through process environment variables.
There is no application package, service layer, domain model, persistence adapter, command-line interface, or test suite at present.

## Layers and Components

- Environment layer: `flake.nix` builds the development shell, pins the O365 Python dependency, and configures opnix references for Microsoft credentials.
- Shell activation layer: `.envrc` points opnix at the user's token location and activates the Nix flake through direnv.
- Integration layer: `read_mailbox.py` creates the O365 token backend and account, authenticates against Microsoft Graph, selects a mailbox and Inbox, and enumerates messages.
- Local credential state: `token/my_token.txt` is the configured O365 SDK token target; `my_token.txt` at repository root is not referenced by the script.
- Tool-local state: `.config/op/config` and `.direnv/` are generated/operator-specific directories rather than application components.
- Planning state: `.planning/` contains project-analysis artifacts and is separate from the runtime system.

## Entry Points

The only executable application entry point is top-level module execution of `read_mailbox.py`.
Importing `read_mailbox.py` also executes authentication and mailbox reads because the script has no `main()` boundary or `if __name__ == "__main__"` guard.
The development entry point is `nix develop`, normally activated by direnv from `.envrc`.
There is no packaged console script, scheduler definition, web endpoint, worker process, or database migration entry point.

## Data Flow

1. `.envrc` activates the shell described by `flake.nix`.
2. The `flake.nix` shell hook invokes opnix and exports `O365_AUTH_ID`, `O365_AUTH_SECRET`, and `TENANT_ID` from 1Password references.
3. `read_mailbox.py` reads those values from the process environment and constructs an O365 client-credentials account.
4. The O365 SDK reads or writes authentication material through `token/my_token.txt`.
5. The script addresses `automations@vegetationlink.com.au`, obtains its `Inbox`, requests messages, and prints message objects to standard output.
6. No attachment download, Vicmap parsing, transformation, PostGIS connection, database load, checkpoint, or update-state flow currently exists.

## Abstractions and Boundaries

The `O365.Account`, `O365.FileSystemTokenBackend`, mailbox, folder, and message objects are third-party abstractions used directly by the entry point.
Environment variables are the only configuration abstraction; mailbox address, folder name, token path, message limit, and Graph scope are hard-coded.
There are no repository-owned interfaces isolating Graph access, filesystem token storage, message selection, or database output.
Keep future external-system details behind explicit adapters instead of extending top-level orchestration in `read_mailbox.py`.
Keep message interpretation and Vicmap-specific rules independent of O365 objects so they can be tested without Graph credentials.

## Error Handling

Startup validates that all three required environment variables are present and raises `ValueError` when any are missing.
The error text names `MS_APP_ID`, `MS_APP_SECRET`, and `MS_TENANT_ID`, which do not match the actual environment names read by the code.
Authentication reports its boolean result with `print`, but does not explicitly stop when authentication fails.
Graph, mailbox, folder, token-file, pagination, and rate-limit errors are not caught or translated; SDK exceptions escape the process.
There is no structured logging, retry policy, timeout policy, partial-progress tracking, or cleanup boundary.
Add error handling at integration boundaries and preserve non-zero process exits for unrecoverable failures.

## Cross-Cutting Concerns

Secrets are injected at shell activation by opnix, while `read_mailbox.py` consumes only environment values and does not embed credential literals.
Token files and tool-local configuration are present inside the working tree; repository hygiene must prevent credential-bearing state from entering version control.
Dependency reproducibility is provided by `flake.lock` and the pinned O365 source/hash in `flake.nix`.
Observability is currently limited to authentication and message-object printing; sensitive message content may therefore reach terminal logs.
Configuration, logging redaction, idempotency, retries, and testability should become shared infrastructure before the integration grows.
No automated tests, formatter, linter, type checker, CI workflow, or production deployment definition is currently present.

---

*Architecture analysis refreshed 2026-08-31.*
