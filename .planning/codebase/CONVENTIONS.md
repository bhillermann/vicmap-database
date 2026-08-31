# Coding Conventions

**Analysis date:** 2026-08-31

## Repository Shape

- The current implementation is a single top-level Python script, `read_mailbox.py`.
- Development dependencies and environment assembly live in `flake.nix`; shell activation lives in `.envrc`.
- There is no Python package directory, application entry-point wrapper, project metadata, formatter configuration, or linter configuration.
- All visible project files are currently untracked, and the repository has no commits or tracked-file history from which to infer broader conventions.
- Secret-bearing artifacts exist at `my_token.txt` and `token/my_token.txt`; code and documentation must not treat these as source files or examples.

## Python Style and Naming

- `read_mailbox.py` uses uppercase snake case for module-level configuration values: `MSAPPID`, `MSAPPSECRET`, `TENANT_ID`, `SCOPES`, `CREDENTIALS`, and `TOKEN_BACKEND`.
- Runtime objects use lowercase names such as `account`, `mailbox`, `inbox`, `count`, and `message`.
- Naming is inconsistent around Microsoft environment variables: code reads `O365_AUTH_ID`, `O365_AUTH_SECRET`, and `TENANT_ID`, while the validation error names `MS_APP_ID`, `MS_APP_SECRET`, and `MS_TENANT_ID`.
- New environment-variable references should use the exact names declared in `flake.nix`: `O365_AUTH_ID`, `O365_AUTH_SECRET`, and `TENANT_ID`.
- Assignment spacing is inconsistent (`inbox=...` versus `account = ...`); follow standard spaces around assignment operators when extending the script.
- Strings use both single and double quotes without an established semantic distinction.
- Collection literals and function calls generally include trailing commas when written across multiple lines.

## Imports and Dependencies

- Third-party imports from `O365` appear before the standard-library `os` import in `read_mailbox.py`.
- Imports are explicit (`Account`, `FileSystemTokenBackend`) rather than wildcard imports.
- `flake.nix` is the only dependency declaration and supplies Python plus the locally built `O365` package.
- `flake.nix` pins `O365` version `2.1` from GitHub and declares its propagated dependencies directly.
- The Nix derivation disables upstream package checks with `doCheck = false`.
- Keep dependency changes in `flake.nix`; no `requirements.txt`, `pyproject.toml`, or lockfile for Python exists.

## Code Structure and Function Design

- `read_mailbox.py` executes authentication and mailbox access at import time.
- The script defines no functions, classes, `main()` function, or `if __name__ == "__main__"` guard.
- Configuration loading, validation, authentication, mailbox lookup, message retrieval, and output are coupled in one module-level flow.
- The `SCOPES` constant is declared but unused; authentication instead passes the Microsoft Graph `.default` scope inline.
- `count` receives a message query result but is never consumed; a second call to `inbox.get_messages()` drives iteration.
- Any extension should first isolate configuration loading, account creation, and mailbox processing into small functions so callers and tests can avoid import-time network activity.
- Keep external-service objects at integration boundaries; pass them into processing functions instead of resolving them from globals.

## Errors, Logging, and Output

- Missing required configuration raises `ValueError` before the O365 account is created.
- The validation message is assembled with an explicit line-continuation backslash and has mismatched variable names.
- Authentication reports its result with `print()` and message processing prints each message object directly.
- There is no configured `logging` module, log level, structured event format, retry policy, or exception translation.
- Exceptions from token loading, authentication, mailbox lookup, and message enumeration currently propagate unchanged.
- Preserve fail-fast configuration validation, but use accurate variable names and actionable context in future errors.
- Avoid printing credentials, token contents, or entire message objects when adding diagnostics because mailbox objects may contain sensitive data.

## Comments and Documentation

- The only Python comment is a generic O365 guidance note above `CREDENTIALS`; it does not explain a project-specific decision.
- There are no docstrings, README, type annotations, or module-level usage instructions.
- `flake.nix` communicates intent through its flake description and otherwise relies on descriptive attribute names.
- Add comments only for non-obvious service or security constraints; express routine flow through named functions.
- Public helpers should gain concise docstrings once the script is decomposed into reusable units.

## Nix and Shell Conventions

- `flake.nix` uses two-space indentation at outer levels, with some extra blank space and uneven indentation around `let`/`in`.
- Nix attribute names are descriptive; the hyphenated local package name `python-o365` follows Nix naming norms.
- The development shell supports Linux and Darwin on both x86-64 and ARM64.
- Secrets are injected during `shellHook` through `opnix env`, with a configurable `OPNIX_ENV_TOKEN_FILE`.
- `.envrc` exports the token-file path and activates the flake through direnv.
- Keep secret resolution in environment setup and keep literal secret/token values out of source-controlled configuration.

---

**Refreshed:** 2026-08-31
