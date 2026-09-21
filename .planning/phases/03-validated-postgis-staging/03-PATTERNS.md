# Phase 3: Validated PostGIS Staging - Pattern Map

**Mapped:** 2026-09-21
**Files analyzed:** 8 (new/modified)
**Analogs found:** 8 / 8

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|-----------------|---------------|
| `vicmap_acquire/staging.py` (new) | service/orchestrator | subprocess + request-response (DB) | `vicmap_acquire/discovery.py` | role-match (Policy dataclass + typed exception hierarchy + subprocess pattern) |
| `vicmap_acquire/staging.py::StagingPolicy` (dataclass in same file) | config | CRUD-adjacent (validated config) | `vicmap_acquire/download.py::DownloadPolicy` | exact (frozen dataclass, per-field validators) |
| `vicmap_acquire/staging.py` ogr2ogr invocation | service | subprocess/streaming | `vicmap_acquire/discovery.py` `_probe_layer` / `ogrinfo` subprocess call | exact (subprocess.run, capture_output, closed exception on nonzero exit) |
| `vicmap_acquire/staging.py` psycopg preflight/validation queries | service | request-response (DB) | none in codebase (first DB driver use) — closest analog is `discovery.py`'s subprocess-and-parse shape | role-match only — no analog |
| `vicmap_acquire/evidence.py` (extended: new Stage/ReasonCode members) | model/enum | event-driven | `vicmap_acquire/evidence.py` itself (existing `Stage`/`ReasonCode`/`_FAILURE_POLICY`) | exact (extend existing enums/mapping in place) |
| `vicmap_acquire/naming.py` (staging-suffix reuse, no modification expected) | utility | transform | `vicmap_acquire/naming.py` (unchanged, consumed as-is) | exact — reuse, not a new pattern |
| `read_mailbox.py` (extended: `[database]` section loader/validator) | config loader | request-response (TOML→dataclass) | `read_mailbox.py::load_discovery_config` / `validate_discovery_policy` | exact |
| `db/provision_vicmap_loader.sql` (new) | migration/config | batch (DDL, operator-run) | none existing — first SQL file in repo; use CONTEXT.md's D-60 skeleton verbatim | no analog |
| `tests/test_staging.py` (new) | test | event-driven / live-DB integration | `tests/test_naming.py::PostgresKeywordOracleTest` | exact (skip-not-fail live-DB pattern) |
| `flake.nix` (modified: add `psycopg`, vendor grid `.tif` via `fetchurl`) | config | build | `flake.nix` existing `packages = with pkgs; [...]` list and `python-o365` `fetchFromGitHub` vendoring precedent | exact |
| `vicmap.toml` (modified: new `[database]` section) | config | CRUD-adjacent | existing `[mailbox]`/`[download]`/`[extraction]`/`[discovery]` sections | exact |

## Pattern Assignments

### `vicmap_acquire/staging.py` (new module — service/orchestrator, subprocess + DB request-response)

**Analogs:** `vicmap_acquire/download.py` (policy dataclass + typed failure hierarchy), `vicmap_acquire/discovery.py` (subprocess invocation + total exception collapse), `vicmap_acquire/naming.py` (module docstring convention establishing dependency direction and no-I/O guarantees where applicable).

**Module docstring / dependency-direction convention** (`vicmap_acquire/discovery.py` lines 1-16):
```python
"""pyogrio + ogrinfo layer discovery and profiling (D-33..D-40).
...
Enumeration (``find_datasets``) is driven by a closed extension-to-driver
map (D-34): a recognized-but-unlisted format is a named ``UnsupportedFormat``
failure, never a silent skip...
"""
```
Copy this shape: open `staging.py` with a docstring naming the decisions it implements (D-41..D-64), and state explicitly which modules it may/may not import (it is the first module allowed to import `psycopg`; per `tests/test_manifest.py:837`'s forbidden-import list, confirm that policy test's scope doesn't also reach `staging.py` before assuming that's fine).

**Frozen policy dataclass pattern** (`vicmap_acquire/download.py`, `DownloadPolicy`-equivalent shape — see also `discovery.py` line 90 `@dataclass(frozen=True)`):
```python
def _positive_integer(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError("discovery policy values must be positive integers")
    return value

@dataclass(frozen=True)
class DiscoveryPolicy:
    ...
```
Copy this exact idiom for `StagingPolicy`: frozen dataclass, one private `_positive_integer`/`_bounded_integer`-style validator per numeric field, boolean-guard-before-int-check (`isinstance(value, bool)` checked first since `bool` is an `int` subclass in Python).

**Typed closed-failure hierarchy** (`vicmap_acquire/download.py` lines 33-77):
```python
class DownloadFailure(RuntimeError):
    """A closed download failure carrying no remote or local source text."""
    code = "download_http_failed"
    def __init__(self) -> None:
        super().__init__(self.code)

class DownloadUrlRejected(DownloadFailure):
    code = "download_url_rejected"
...
DownloadError = DownloadFailure  # back-compat alias pattern, if needed
```
Copy this exact idiom for `staging.py`: a base `StagingFailure(RuntimeError)` carrying only `.code`, with one subclass per D-43/D-56/D-59 failure mode (e.g. `PreflightPrivilegeDenied`, `LoadSubprocessFailed`, `ValidationRowCountMismatch`, `ValidationGeometryTypeChanged`, `ValidationSridMismatch`). No interpolated driver/stderr text ever reaches the exception message — matches D-43's "one fixed internal failure with no interpolation" rule, with the *file path* to the full stderr named separately in the SafeFailure fields, not the exception text itself.

**Subprocess invocation + total exception collapse** (mirrors `discovery.py`'s `ogrinfo` subprocess call — same file, `subprocess` import at line 21, and the closed-failure-on-any-driver-error rule stated in the module docstring lines 8-9): use `subprocess.run(command, capture_output=True, text=True, timeout=..., env={**os.environ, "PGPASSWORD": password})` exactly as RESEARCH.md's Pattern 1 shows, and map a nonzero `returncode` to one fixed `ReasonCode` (never branch on stderr content) — this is the same "unexpected exceptions map to one fixed internal failure with no interpolation" rule CONTEXT.md's Established Patterns section states and `discovery.py`/`download.py` already both follow.

---

### `vicmap_acquire/evidence.py` (extended — model/enum, event-driven)

**Analog:** itself — extend, do not fork.

**Stage enum extension point** (`vicmap_acquire/evidence.py` lines 37-51):
```python
class Stage(str, Enum):
    CONFIGURATION = "configuration"
    ...
    MANIFEST = "manifest"
    # NEW for Phase 3, appended, existing members untouched:
    # DB_PREFLIGHT = "db_preflight"
    # DB_LOAD = "db_load"
    # DB_VALIDATION = "db_validation"
```

**ReasonCode enum + `_FAILURE_POLICY` mapping extension point** (lines 53-87 and the `_FAILURE_POLICY = MappingProxyType({...})` block starting line 89):
```python
class ReasonCode(str, Enum):
    ...
    MANIFEST_WRITE_FAILED = "manifest_write_failed"
    # NEW: DB_CONNECTION_FAILED, DB_PRIVILEGE_DENIED, DB_LOAD_FAILED,
    # DB_ROW_COUNT_MISMATCH, DB_SRID_MISMATCH, DB_GEOMETRY_TYPE_MISMATCH,
    # DB_GEOMETRY_TYPE_CHANGED_ON_REPAIR

_FAILURE_POLICY = MappingProxyType({
    ReasonCode.CONFIG_INVALID: (Stage.CONFIGURATION, "review_non_secret_configuration"),
    ...
    # NEW entries pairing each new ReasonCode with its Stage + remediation hint string
})
```
Every new `ReasonCode` **must** get a `_FAILURE_POLICY` entry — `SafeFailure.__init__` (line 505) does a bare dict lookup `_FAILURE_POLICY[reason]` with no default, so a missing entry is a `KeyError` at first use, not a graceful failure. This is load-bearing: copy the pattern exactly, add both enum member and policy entry in the same change.

**`SafeFailure`/`SuccessEvent`/`ProgressEvent` shape** (lines 316, 453, 493) — no new event *classes* are expected; Phase 3 failures use the existing `SafeFailure(reason, ...)` constructor with whatever combination of `order_id`/`message_fingerprint`/`path_fingerprint` fits (e.g., a `target_table` fingerprint would need a new optional field on `SafeFailure` if CONTEXT.md's "target table" naming requirement isn't already covered by an existing fingerprint field — check before adding a new constructor parameter).

---

### `read_mailbox.py` (extended — config loader, request-response TOML→dataclass)

**Analog:** `load_discovery_config` / `validate_discovery_policy` (lines 361-399, 735-790).

**Complete-key-set fail-closed pattern** (lines 752-755):
```python
extraction = raw["extraction"]
discovery = raw["discovery"]
if not isinstance(extraction, dict) or set(extraction) != _EXTRACTION_KEYS:
    raise AcquisitionFailure("config_invalid")
if not isinstance(discovery, dict) or set(discovery) != _DISCOVERY_KEYS:
    raise AcquisitionFailure("config_invalid")
```
Copy exactly for a new `_DATABASE_KEYS` frozenset and `raw["database"]` — set equality (not subset) rejects both missing and unexpected extra keys, keeping the "one file is the whole non-secret policy" rule (D-58) enforced structurally.

**Per-field bounded/positive integer validation** (lines 332-338, 380-390):
```python
_bounded_integer(config.lookback_days, 1, 3660)
_bounded_integer(config.max_bytes, 1, 10 * 1024**4)
...
_positive_bounded_integer(config.max_total_bytes, 1, 10 * 1024**4)
_positive_bounded_integer(config.max_member_bytes, 1, 10 * 1024**4)
if config.max_member_bytes > config.max_total_bytes:
    raise AcquisitionFailure("config_invalid")
```
Apply the same shape to the new `[database]` fields: `connect_timeout_seconds`, `statement_timeout_seconds`, `lock_timeout_seconds`, `gt` (transaction group size), `port` (bounded 1-65535), `target_srid` (bounded to a sane EPSG range or checked against a resolvable-CRS call), and a cross-field check analogous to `max_member_bytes > max_total_bytes` if any two `[database]` fields have an ordering constraint.

**Flat allowlist config field** (D-64's `index_columns`) — mirror `supported_formats` (lines 392-398):
```python
if (
    not isinstance(config.supported_formats, tuple)
    or not config.supported_formats
):
    raise AcquisitionFailure("config_invalid")
for fmt in config.supported_formats:
    if not isinstance(fmt, str) or fmt not in _RECOGNIZED_DISCOVERY_FORMATS:
        raise AcquisitionFailure("config_invalid")
```
For `index_columns`, drop the "must be in a recognized closed set" clause (there's no fixed universe of column names to check against, unlike `supported_formats`) — just require a non-empty tuple of non-blank strings, matching `allowed_senders`/`allowed_hosts`'s open-ended-string-list shape instead.

**Delegation pattern** (`load_discovery_config` reusing `load_config`, lines 747-748):
```python
acquisition_config = load_config(path)
try:
    raw = tomllib.loads(path.read_text(encoding="utf-8"))
    ...
```
A new `load_database_config(path)` should similarly call `load_discovery_config(path)` first (or `load_config`, depending on which fields it needs) rather than re-parsing independently, then layer only its own `[database]`-specific TOML shape work on top, delegating all semantics to a new `validate_database_policy`.

---

### `db/provision_vicmap_loader.sql` (new — migration, batch DDL)

**No analog** — first SQL file in the repository. Use CONTEXT.md's D-60 skeleton verbatim as the starting point (already gives the exact `CREATE ROLE`/`CREATE SCHEMA AUTHORIZATION` shape and the explicit comment documenting why no `GRANT ... ON SCHEMA public` line exists). Follow the project's existing comment-density convention (module docstrings elsewhere explain *why*, not just *what* — see `naming.py` lines 1-8, `discovery.py` lines 1-16) by keeping the "run once, by hand, as superuser; not invoked by any Phase 3 code path" comment at the top.

---

### `tests/test_staging.py` (new — test, live-DB integration, skip-not-fail)

**Analog:** `tests/test_naming.py::PostgresKeywordOracleTest` (lines 219-280).

**Driver-import guard + DSN override + connection-failure skip** (lines 232-262):
```python
_DSN_ENV_VAR = "VICMAP_TEST_POSTGRES_DSN"
_CONNECT_TIMEOUT_SECONDS = 2

def _connect(self):
    try:
        import psycopg as _driver  # psycopg3, preferred if present
    except ImportError:
        try:
            import psycopg2 as _driver  # type: ignore[no-redef]
        except ImportError:
            self.skipTest(
                "no PostgreSQL driver (psycopg or psycopg2) installed -- "
                "IN-01 oracle check skipped, not failed"
            )
    dsn = os.environ.get(self._DSN_ENV_VAR)
    try:
        if dsn:
            connection = _driver.connect(dsn, connect_timeout=self._CONNECT_TIMEOUT_SECONDS)
        else:
            connection = _driver.connect(dbname="postgres", connect_timeout=self._CONNECT_TIMEOUT_SECONDS)
    except Exception as exc:  # noqa: BLE001 -- any connect failure just skips
        self.skipTest(f"no reachable PostgreSQL server for IN-01 oracle check: {exc}")
    return connection
```
Copy this verbatim as the base fixture/mixin for every `test_staging.py` test class (`ConnectionIdentityTest`, `PrivilegePreflightTest`, `LoadIntegrationTest`, `ValidationTest`, `ProductionIsolationTest`) — same env var, same timeout, same driver-import fallback chain, same skip-not-fail semantics. RESEARCH.md's Wave 0 Gaps section already names this requirement explicitly ("none of this phase's tests may require a reachable PostgreSQL server or `psycopg` installation to pass in CI").

**Non-live unit test** for command construction (`LoadCommandConstructionTest`, per RESEARCH.md's test map) has no direct analog needing a live connection — mock `subprocess.run` the way `tests/test_download.py` or `tests/test_extraction.py` likely mock `requests`/`zipfile` calls (check either file for the project's `unittest.mock.patch` idiom before writing this one).

---

### `flake.nix` (modified — config, build)

**Analog:** existing `packages = with pkgs; [...]` list and the `python-o365` vendoring precedent (grep result: `packages = with pkgs; [` starts near line 59; `gdal` entry at line 62; `opnixEnvConfig` block at line 20).

**Package list addition:**
```nix
packages = with pkgs; [
  git
  buildOpnix
  gdal  # provides the ogrinfo/ogr2ogr CLI tools -- python3Packages.pyogrio
  (python3.withPackages (ps: [
    python-o365
    ps.html5lib
    ps.pyogrio
    ps.pyproj
    ps.psycopg   # NEW: Phase 3's preflight/validation driver
  ]))
];
```
**Secret wiring precedent** (`opnixEnvConfig` block, line 20-24) — the database password should join this same block exactly as `O365_AUTH_SECRET` does:
```nix
opnixEnvConfig = {
  ...
  { name = "O365_AUTH_SECRET"; reference = "op://nixos-services/o365_app_credentials/password"; }
  # NEW: { name = "VICMAP_DB_PASSWORD"; reference = "op://<vault>/<item>/password"; }
};
```
**Grid-file vendoring** — no exact analog for `fetchurl` in this flake yet (RESEARCH.md's Pitfall 1 recommends `pkgs.fetchurl` for the ICSM grid `.tif`), but the *pattern* of vendoring an external asset by pinned hash already exists for `python-o365` via `fetchFromGitHub` — follow that same "pin by hash, vendor into the Nix store, no runtime network fetch" philosophy for the grid file.

---

### `vicmap.toml` (modified — config)

**Analog:** existing `[mailbox]`/`[download]`/`[extraction]`/`[discovery]` sections (structure confirmed via `read_mailbox.py`'s key-set constants).

**New `[database]` section** — use RESEARCH.md's Code Examples block verbatim as the starting shape:
```toml
[database]
host = "127.0.0.1"
port = 5432
dbname = "vicmap"
user = "vicmap_loader"
staging_schema = "vicmap_staging"
publish_schema = "vicmap"
target_srid = 7899
index_columns = ["pfi"]
gt = 20000
connect_timeout_seconds = 10
statement_timeout_seconds = 3600
lock_timeout_seconds = 30
```
Password deliberately absent (D-58) — same convention as the existing sections never storing `O365_AUTH_SECRET` inline.

## Shared Patterns

### Typed closed-failure hierarchy with `.code`
**Source:** `vicmap_acquire/download.py` lines 33-77, `vicmap_acquire/discovery.py` lines 47-81, `vicmap_acquire/naming.py` lines 16-31
**Apply to:** `staging.py`'s entire exception hierarchy
```python
class DownloadFailure(RuntimeError):
    code = "download_http_failed"
    def __init__(self) -> None:
        super().__init__(self.code)
```
No source-controlled or driver-controlled text ever reaches the exception message — only a fixed `.code` string. `staging.py` must follow this for every `ogr2ogr`/`psycopg` failure it surfaces.

### Frozen policy dataclass + per-field validator function
**Source:** `vicmap_acquire/discovery.py` line 90 (`@dataclass(frozen=True)`), `_positive_integer` at line 84
**Apply to:** `StagingPolicy` in `staging.py`
One private validator per constraint shape (`_positive_integer`, `_bounded_integer`, a new `_positive_bounded_integer` if not already shared), called from `validate_database_policy` in `read_mailbox.py`-analog fashion, never inline in the dataclass `__post_init__` — validation is a separate function so a directly constructed config still gets checked (see `naming.py`'s and `discovery.py`'s consistent separation of construction from validation).

### `Stage`/`ReasonCode`/`_FAILURE_POLICY` triple, extended in place
**Source:** `vicmap_acquire/evidence.py` lines 37-87 and 89+
**Apply to:** every new failure this phase introduces (preflight, load, validation)
Every new `ReasonCode` member requires a matching `_FAILURE_POLICY` entry in the same change — no default fallback exists, so an omission is a `KeyError` at runtime rather than a lint error.

### Complete-key-set, fail-closed TOML section loading
**Source:** `read_mailbox.py` lines 752-755, 361-399
**Apply to:** the new `[database]` section
`set(raw_section) != _EXPECTED_KEYS` (exact equality, not subset) rejects both a missing key and a stray extra key, keeping "one file is the whole non-secret policy" true by construction.

### Skip-not-fail live-database test fixture
**Source:** `tests/test_naming.py::PostgresKeywordOracleTest` lines 219-280
**Apply to:** every test class in the new `tests/test_staging.py`
Driver-import guarded (`psycopg` then `psycopg2` fallback), `VICMAP_TEST_POSTGRES_DSN` env override, any connection exception skips (never fails) the test. This is the single most load-bearing shared pattern for this phase's test suite per RESEARCH.md's explicit Wave 0 gap callout.

### Subprocess invocation, closed on any nonzero exit
**Source:** `vicmap_acquire/discovery.py`'s `ogrinfo` subprocess call (module docstring lines 1-16 describing the total-exception-collapse contract)
**Apply to:** `staging.py`'s `ogr2ogr` invocation (D-41/D-42/D-43)
`subprocess.run(..., capture_output=True, text=True, timeout=...)`, non-zero return code maps to exactly one fixed `ReasonCode` — never branch on stderr content for control flow, only capture it to the D-43 diagnostic file.

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `vicmap_acquire/staging.py` psycopg preflight/validation query functions | service | request-response (DB) | This is the project's first genuine database driver usage outside of an optional test oracle — `tests/test_naming.py`'s `PostgresKeywordOracleTest` is the only prior `psycopg` usage anywhere in the codebase, and it is test-only, read-only, and single-query. No production module has ever opened a `psycopg` connection, run a multi-statement transaction, or used `psycopg.sql.Identifier` composition. RESEARCH.md's Architecture Pattern 2 and 3 code examples are the best available reference and should be treated as the primary source for this part of `staging.py`, not a codebase analog. |
| `db/provision_vicmap_loader.sql` | migration | batch DDL | First SQL file in the repository; use CONTEXT.md's D-60 skeleton directly. |

## Metadata

**Analog search scope:** `vicmap_acquire/*.py`, `read_mailbox.py`, `flake.nix`, `vicmap.toml`, `tests/test_naming.py`, `tests/test_manifest.py` (grep only, for the forbidden-import policy line)
**Files scanned:** `evidence.py`, `download.py`, `discovery.py`, `naming.py`, `manifest.py` (structure only), `read_mailbox.py`, `flake.nix`, `tests/test_naming.py`
**Pattern extraction date:** 2026-09-21
**Tracked-source verification:** all analog paths above are ordinary repo files under `vicmap_acquire/`, `tests/`, and repo root — none live under a `.gsd/capabilities/` mirror or any other gitignored install path; no substitution was needed.
