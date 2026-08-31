# Repository Structure

**Analysis date:** 2026-08-31
**Refreshed:** 2026-08-31

## Directory Layout

```text
vicmap-database/
├── read_mailbox.py       # Current Python entry point and complete application logic
├── flake.nix            # Nix development shell, O365 package, and opnix environment setup
├── flake.lock           # Locked Nix input revisions
├── .envrc               # direnv activation and opnix token-file location
├── token/               # O365 SDK filesystem token location
│   └── my_token.txt
├── my_token.txt         # Unreferenced root-level token-named file
├── .config/op/          # Operator-local 1Password CLI state
├── .direnv/             # Generated direnv/Nix environment state
└── .planning/           # GSD planning and codebase-analysis artifacts
    └── codebase/       # Generated architecture and structure maps
```

## Key Locations

- `read_mailbox.py` is the only source file and owns configuration reads, authentication, mailbox selection, message retrieval, and output.
- `flake.nix` is the dependency and developer-environment authority; add runtime Python dependencies to its `python3.withPackages` environment or its custom package definitions.
- `flake.lock` records the resolved versions of nixpkgs, flake-parts, opnix, and their transitive flake inputs.
- `.envrc` is developer-shell glue and should remain small; application configuration does not belong there.
- `token/` is runtime credential state, not source code or durable project data.
- `.config/` and `.direnv/` are machine-generated/local directories and should not contain repository-owned implementation.
- `.planning/codebase/` is documentation output and has no runtime role.

## Naming and Organization

The sole Python filename uses lower-case snake_case, matching standard Python module naming.
Python variables are mostly upper-case for configuration constants and lower-case for runtime objects.
There is no Python package namespace, so module ownership and public/private API conventions have not yet been established.
Nix attributes use conventional camelCase names such as `buildOpnix`, while the custom `python-o365` binding follows Nix package-style hyphenation.
Environment variables use upper-case snake case: `O365_AUTH_ID`, `O365_AUTH_SECRET`, `TENANT_ID`, and `OPNIX_ENV_TOKEN_FILE`.

## Where to Add New Code

Create an importable Python package before adding further integration logic; use a repository-specific package directory rather than accumulating behavior in `read_mailbox.py`.
Place Graph/mailbox access in an integration module, Vicmap message and attachment interpretation in domain-focused modules, and PostGIS operations in a database adapter module.
Keep a thin executable entry point that composes those modules and handles process exit status.
Add tests under a top-level `tests/` directory, mirroring package module names and using fakes at Graph and PostGIS boundaries.
Add database schema changes under a dedicated migration directory once PostGIS persistence exists; no migration convention exists yet.
Add operational commands or scheduling definitions in an explicit deployment/operations directory only when a deployment mechanism is selected.
Update `flake.nix` whenever new Python tooling or runtime libraries are required, and refresh `flake.lock` only through normal Nix lock operations.

## Files and Directories Requiring Special Treatment

Treat `token/my_token.txt`, `my_token.txt`, and `.config/op/config` as local or credential-adjacent state; do not build features that depend on committing their contents.
Treat `.direnv/` as disposable generated output and never edit its internal files by hand.
Treat `flake.lock` as generated but version-worthy dependency state; do not hand-edit it.
Treat `.planning/` as workflow metadata and documentation, isolated from application imports and runtime paths.
The repository currently has no tracked files and no ignore file, so add ignore rules before credentials, token caches, bytecode, test caches, or local environments can be accidentally staged.

## Current Structural Gaps

There is no `README`, package metadata, application configuration file, test tree, migrations tree, CI directory, container definition, or deployment directory.
There is no PostGIS schema or connection code despite the flake description naming a Vicmap-to-PostGIS refresh.
There is no attachment storage, processing workspace, or data-output directory.
Do not infer undocumented directories as established conventions; introduce each boundary deliberately and document it when implementation begins.

---

*Structure analysis refreshed 2026-08-31.*
