# Technology Stack

**Analysis Date:** 2026-08-31

## Current Maturity

- The repository is an uncommitted initial scaffold: `git` has a `main` branch but no commits, and every current project file is untracked.
- The only application code is `read_mailbox.py`; no Vicmap download, archive extraction, spatial transformation, PostgreSQL connection, PostGIS schema, or refresh/swap workflow is implemented yet.
- Treat the PostGIS refresh wording in `flake.nix` as intended project direction, not evidence of an existing database implementation.

## Languages and Runtime

- Python is the application language. `read_mailbox.py` uses Python 3 syntax and standard-library `os` environment access.
- Nix is the environment and dependency definition language. `flake.nix` defines the development shell and `flake.lock` pins its inputs.
- Shell is used only for environment bootstrap: `.envrc` selects the flake, and the `shellHook` in `flake.nix` evaluates environment assignments produced by `opnix env`.
- JSON appears as generated configuration/state in `flake.lock` and the local token backend; it is not an application data model.

## Runtime and Frameworks

- Python is supplied by `python3.withPackages` in `flake.nix`; there is no separate `pyproject.toml`, `requirements.txt`, virtualenv, package module, or console entry point.
- The sole application-level framework/library is `O365` version 2.1, built directly from the `O365/python-o365` GitHub tag in `flake.nix`.
- The O365 package is built as a PEP 517 project using `setuptools`; upstream package checks are disabled with `doCheck = false`.
- `read_mailbox.py` uses `O365.Account` and `O365.FileSystemTokenBackend` directly rather than wrapping them behind project-owned service modules.

## Dependency Inventory

- Direct Nix inputs are `nixpkgs` (`nixos-unstable`), `hercules-ci/flake-parts`, and `brizzbuzz/opnix`; exact revisions and hashes are recorded in `flake.lock`.
- The custom O365 derivation propagates `requests`, `requests-oauthlib`, `msal`, `tzlocal`, `tzdata`, `beautifulsoup4`, and `python-dateutil`.
- Development-shell tools are `git`, `opnix`, and Python with the custom O365 package.
- No PostgreSQL client, PostGIS tooling, GDAL/OGR, GeoPandas, HTTP download CLI, archive utility, scheduler, test runner, linter, or formatter is declared.
- There is no dependency separation between development, test, and production because only a development shell exists.

## Configuration and Secrets

- `flake.nix` declares three runtime variables: `O365_AUTH_ID`, `O365_AUTH_SECRET`, and `TENANT_ID`.
- Those variables map to 1Password references under `op://nixos-services/o365_app_credentials/...` and are emitted in shell format by opnix.
- `.envrc` points `OPNIX_ENV_TOKEN_FILE` at `$HOME/.config/opnix/token` and invokes `use flake`, requiring direnv plus nix-direnv-compatible behavior.
- The shell hook can skip secret injection when `OPNIX_ENV_DISABLE` is non-empty and can override the opnix token path through `OPNIX_ENV_TOKEN_FILE`.
- Local files `my_token.txt`, `token/my_token.txt`, and `.config/op/config` are runtime credentials/configuration artifacts, not source dependencies; they must remain excluded from version control and logs.
- There is no checked-in `.gitignore`, example configuration, typed settings layer, or startup validation beyond the three-variable check in `read_mailbox.py`.

## Supported Platforms

- The flake declares `x86_64-linux`, `aarch64-linux`, `aarch64-darwin`, and `x86_64-darwin` systems.
- Nix with flakes is therefore the reproducible platform prerequisite; direnv is optional for automatic activation but currently assumed by `.envrc`.
- Access to the configured 1Password vault/item and a valid opnix service token is required for the default shell hook.
- Network access to GitHub/Nix caches is required to realize the development shell, and Microsoft endpoints are required when running the mailbox script.
- Cross-platform declaration does not prove runtime testing: the repository contains no CI workflow or platform-specific test evidence.

## Build, Test, and Operations

- Enter the intended environment with `nix develop`; `.envrc` provides the automatic equivalent where direnv is installed and allowed.
- Run the current program as `python read_mailbox.py` from the repository root so the relative `token/` backend resolves predictably.
- There are no automated tests, fixtures, static analysis settings, build artifact, deployment manifest, container, service unit, or scheduled-job configuration.
- Future implementation should extend `flake.nix` for every native/runtime dependency and add project-owned packaging and tests rather than relying on ambient tools.
- Future database work must explicitly declare PostgreSQL/PostGIS versions and geospatial tooling because neither exists in the current stack.

---
*Technology stack analysis refreshed: 2026-08-31*
