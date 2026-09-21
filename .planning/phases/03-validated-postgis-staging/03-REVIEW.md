---
phase: 03-validated-postgis-staging
reviewed: 2026-09-21T00:00:00Z
depth: standard
files_reviewed: 12
files_reviewed_list:
  - db/provision_vicmap_loader.sql
  - flake.nix
  - read_mailbox.py
  - stage_order.py
  - tests/test_discovery_config.py
  - tests/test_evidence.py
  - tests/test_graph.py
  - tests/test_manifest.py
  - tests/test_staging.py
  - vicmap.toml
  - vicmap_acquire/evidence.py
  - vicmap_acquire/manifest.py
  - vicmap_acquire/staging.py
findings:
  critical: 0
  warning: 6
  info: 2
  total: 8
status: issues_found
---

# Phase 03: Code Review Report

**Reviewed:** 2026-09-21T00:00:00Z
**Depth:** standard
**Files Reviewed:** 12
**Status:** issues_found

## Summary

Reviewed the full validated-PostGIS-staging boundary: `vicmap_acquire/staging.py`
(connect/preflight/load/validate/DDL), `vicmap_acquire/evidence.py` and
`vicmap_acquire/manifest.py` (closed evidence contract and digest-verified
manifest), `read_mailbox.py`/`stage_order.py` (config loading and CLI
orchestration), the provisioning SQL, the Nix flake, and `vicmap.toml`,
cross-checked against the test suite.

The credential invariant (D-44) holds under direct inspection: the password
enters the process only via `VICMAP_DB_PASSWORD`, is passed to `psycopg` as a
keyword argument (never interpolated into SQL or argv) and to `ogr2ogr` only
via the child process's `PGPASSWORD` environment variable, and every closed
`StagingFailure` subclass deliberately carries no driver/subprocess/SQL text.
The stderr diagnostics file written by `load_layer` cannot carry a credential
because the connection string it's built from never contains one. SQL
identifiers (schema/table/column names) are composed via
`psycopg.sql.Identifier`/`sql.Literal` almost everywhere, with one deliberate,
narrowly-scoped exception noted below. DB-05's runtime proof
(`preflight_staging_privileges`'s rolled-back `CREATE`) and D-56/D-57's
blocking validation queries are implemented as claimed, and the tests exercise
the specific defects the project's own history flagged (the `-ct_opt` GDAL
flag regression, the `GeometryType()` Z-suffix quirk).

No finding below rises to Critical: nothing found permits injection, leaks the
credential, or silently accepts a row-count/SRID/geometry-type mismatch. The
Warnings are mostly about DDL-naming robustness, misleading failure
diagnostics, and defense-in-depth gaps in redaction-safety validators that
happen not to be reachable with untrusted input today but are one refactor
away from being reachable.

## Warnings

### WR-01: `apply_post_validation_ddl`'s return value — the only record of what DDL was actually applied — is discarded

**File:** `vicmap_acquire/staging.py:1140-1146`
**Issue:** `apply_post_validation_ddl` computes and returns a tuple of the
constraint/index names it created, and its docstring goes to considerable
length explaining why that's useful (`"Returns the constraint and index names
this call created, in creation order"`). Its only production caller,
`run_staging`, calls it and discards the return value entirely:
```python
apply_post_validation_ddl(
    validation=validation,
    manifest_layer=layer,
    staging_table=staging_table,
    policy=policy,
    password=password,
)
```
No `SuccessEvent` in `evidence.py` carries a "created objects" field either,
so this information is computed, then thrown away, on every run. An operator
reading the JSON Lines event stream has no way to learn which constraints or
indexes were actually applied to a given staging table versus already present
from `ogr2ogr`'s own load.
**Fix:** Capture the return value in `run_staging` and either fold it into
`SuccessEvent.staging_layer_validated` (as an additional field) or emit a new
event carrying `staging_table` and the created-object tuple.

### WR-02: DDL identifier names derived from an already-maximal-length staging table name are never checked against PostgreSQL's 63-byte identifier limit

**File:** `vicmap_acquire/staging.py:957-963, 994-1005, 1010-1015, 1023-1029, 1033-1042`
**Issue:** `staging_table_name` (staging.py:263-277) permits a result up to
`_MAX_STAGING_NAME_BYTES = 63` bytes — PostgreSQL's own NAMEDATALEN-1 limit.
`apply_post_validation_ddl` then builds several *further* identifiers by
string-concatenating onto that already-63-byte-capable name, with no bound
check at all:
```python
created.append(f"{staging_table}_pkey")
...
created.append(f"{staging_table}_geom_typed")
...
created.append(f"{staging_table}_geom_not_null")
...
gist_index_name = f"{staging_table}_geom_gist"
...
index_name = f"{staging_table}_{column}_idx"
```
`gist_index_name` and `index_name` are passed to `sql.Identifier(...)` and
actually used in `CREATE INDEX` statements. PostgreSQL does not error on an
over-63-byte identifier; it silently truncates it. For a `staging_table` name
near the 63-byte ceiling (realistic for Vicmap's longer layer names combined
with a 16-character run-timestamp suffix), the real on-disk index name will
differ from the name reported in `created`, and two independently valid
staging tables whose generated index names truncate to the same 63 bytes will
collide, causing a spurious `StagingDdlFailed` on an otherwise fully valid
load.
**Fix:** Bound the composed identifier (e.g. truncate/hash the suffix
deterministically, or reserve headroom in `_MAX_STAGING_NAME_BYTES` for the
longest suffix `apply_post_validation_ddl` ever appends) so every identifier
this module composes is provably within PostgreSQL's identifier limit before
it's sent to the server.

### WR-03: `validate_layer` maps unrelated validation-query/repair-query database errors onto `LoadFailed`, pointing the operator at a diagnostics file that was never written

**File:** `vicmap_acquire/staging.py:758-763, 837-849`
**Issue:** `LoadFailed` is documented (staging.py:213-219) as specifically the
exception `load_layer` raises on a non-zero `ogr2ogr` exit, whose
`diagnostics_file` attribute names the stderr file `load_layer` already wrote.
`validate_layer` reuses this exact exception for two unrelated failure modes
that have nothing to do with `ogr2ogr`:
```python
try:
    with connection.cursor() as cursor:
        cursor.execute(query)
        row = cursor.fetchone()
except Exception:
    raise LoadFailed() from None          # line ~762: the validation SELECT itself failed
...
try:
    with connection.cursor() as cursor:
        cursor.execute(repair_statement)
        repaired_count = cursor.rowcount
    ...
except Exception:
    raise LoadFailed() from None          # line ~848: the repair UPDATE/recheck failed
```
Both paths surface as `ReasonCode.DB_LOAD_FAILED`, `Stage.DB_LOAD`, and the
hint `"review_the_named_loader_diagnostic_file"` (evidence.py:286-289) — but
no diagnostics file exists for either failure, since only `load_layer` ever
calls `diagnostics_path`/writes one. An operator following this hint will
look for a file that was never created.
**Fix:** Introduce a distinct closed exception (e.g. `ValidationQueryFailed`)
mapped to `Stage.DB_VALIDATION` with a hint that doesn't reference a
diagnostics file, and raise that instead of `LoadFailed` from both of these
`except Exception` blocks.

### WR-04: The geometry-type modifier in the typed-column `ALTER` is composed as raw SQL text, not through `sql.Identifier`/`sql.Literal`, with no local re-validation

**File:** `vicmap_acquire/staging.py:994-1005`
**Issue:**
```python
cursor.execute(
    sql.SQL(
        "ALTER TABLE {table} ALTER COLUMN geom "
        "TYPE geometry({type}, {srid}) USING geom"
    ).format(
        table=table_ref,
        type=sql.SQL(declared_type),
        srid=sql.Literal(policy.target_srid),
    )
)
```
`declared_type` is inserted via `sql.SQL(declared_type)` — literal, unescaped
text — rather than any quoting primitive (`sql.Identifier` can't be used here
because PostGIS's type-modifier syntax rejects a quoted identifier). This is
safe *today* only because `declared_type` is guaranteed by
`_split_declared_geometry_type` (staging.py:581-600), a different function
entirely, to be drawn from a small closed vocabulary (7 base names × 4 ZM
suffixes) before it ever reaches `normalize_declared_geometry_type` and this
call site. `apply_post_validation_ddl` itself performs no defensive
re-validation of `declared_type` before using it in raw SQL — the task
description for this phase explicitly calls out that "one real bug in this
phase was already caused by using a bind parameter where PostgreSQL requires
a literal, so the composition code is known to be delicate," and this is the
one place in the reviewed files where composition falls back to raw text
rather than a `psycopg.sql` quoting primitive.
**Fix:** Add a local assertion in `apply_post_validation_ddl` (e.g.
`assert declared_type in _VALID_TYPED_COLUMN_NAMES`, built once from
`_BASE_GEOMETRY_NAMES` × `_ZM_SUFFIX_FLAGS`) immediately before the `sql.SQL(declared_type)`
call, so the safety of this composition doesn't depend silently on an
invariant enforced only in a separate function.

### WR-05: `stage_order.py` drops `order_id` from the rendered failure event for `AcquisitionFailure`, inconsistently with the two sibling exception handlers

**File:** `stage_order.py:145-175`
**Issue:** The three failure branches in `main()` are inconsistent about
including `order_id`, even though it is known locally by the time any of them
can fire (it's assigned at line 89, before the password check that is the
most common source of an `AcquisitionFailure` here):
```python
except read_mailbox.AcquisitionFailure as error:
    try:
        render_failure(error.failure)                 # no order_id
    ...
except staging.StagingFailure as error:
    try:
        render_failure(
            SafeFailure(
                _reason_for(error.code),
                order_id=order_id,                     # order_id included
                staging_table=getattr(error, "staging_table", None),
                diagnostics_file=getattr(error, "diagnostics_file", None),
            )
        )
    ...
except ManifestFailure as error:
    try:
        render_failure(SafeFailure(_reason_for(error.code), order_id=order_id))  # order_id included
```
`error.failure` for `AcquisitionFailure` was already constructed inside
`AcquisitionFailure.__init__` (read_mailbox.py:169-173) with no `order_id`
parameter available to it, so the rendered event for e.g. a missing
`VICMAP_DB_PASSWORD` — which happens strictly after `order_id` is already
known — carries no `order_id`, unlike a manifest or staging failure at the
same point in the run.
**Fix:** Rebuild the failure with `order_id` in the `AcquisitionFailure`
branch too: `SafeFailure(error.failure.reason, order_id=order_id)`.

### WR-06: `evidence.py`'s redaction-safety identifier regexes are looser than the validators actually gating the values they receive

**File:** `vicmap_acquire/evidence.py:21, 384`
**Issue:** Two regexes used to gate values rendered "in clear" in the JSON
Lines event stream are looser than the config-level validators that, today,
happen to be the only source of the values passed to them:
```python
_HOST = re.compile(r"[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?")          # line 21 -- no length bound, no DNS label structure
...
_TARGET_TABLE = re.compile(r"[a-z][a-z0-9_]*")                    # line 384 -- no length bound at all
```
Compare `staging.py`'s own `_HOSTNAME` (staging.py:48-51) and
`read_mailbox.py`'s `_HOSTNAME` (read_mailbox.py:93-96), both of which bound
total length to 253 characters and enforce per-label DNS structure, and
`staging.py`'s `_identifier` (staging.py:85-88), which bounds identifiers to
63 bytes matching PostgreSQL's own limit. `_require_target_table` gates
`dbname`, `role`, `target_table`, and `staging_table` across every
`SuccessEvent`/`SafeFailure` constructor that takes them
(`database_identity`, `staging_table_loaded`, `staging_layer_validated`,
`manifest_completed`, `SafeFailure.__init__`) — an unbounded regex there
means an arbitrarily long value would be accepted and written into the event
stream if any future caller ever passes something not already validated
upstream (today, every call site does happen to pass an already-validated
value). This is a defense-in-depth gap specifically in the module whose
stated job is being the last safety net before operator-facing output.
**Fix:** Bound `_TARGET_TABLE` to PostgreSQL's 63-byte identifier limit
(mirroring `staging._identifier`) and give `_HOST` the same length bound and
DNS-label structure as `staging._HOSTNAME`/`read_mailbox._HOSTNAME`.

## Info

### IN-01: `normalize_declared_geometry_type`'s exact-tokenization assumption about `LayerProfile.geometry_type` is unverified within the reviewed files

**File:** `vicmap_acquire/staging.py:581-624`
**Issue:** `_split_declared_geometry_type` assumes `LayerProfile.geometry_type`
is always either a single token (`"Point"`) or two space-separated tokens
(`"Point Z"`). The docstring presents this as fact about pyogrio's output
format, but the module that actually produces `geometry_type`
(`vicmap_acquire/discovery.py`) is outside this phase's file list and wasn't
reviewed here. Given this same phase's history of two behavioral surprises
found only by live-server testing (the `--config OGR_CT_*` no-op, and
PostGIS's `GeometryType()` Z-suffix quirk), an unverified assumption about a
third external API's exact string shape is worth flagging explicitly, even
though the failure mode here (`GeometryTypeMismatch`, a closed, blocking
failure) is safe by construction.
**Fix:** If not already covered elsewhere, add a differential-oracle test
(comparable to `Ogr2ogrFlagOracleTest`/`ValidationOgrinfoOracleTest` in
`tests/test_staging.py`) that runs `pyogrio`/`ogrinfo` against a real GDB
fixture with a Z/M/ZM geometry and asserts the exact `geometry_type` string
shape `discovery.py` records.

### IN-02: The provisioning script's placeholder password will run as-is if not edited first

**File:** `db/provision_vicmap_loader.sql:16-18`
**Issue:**
```sql
CREATE ROLE vicmap_loader LOGIN PASSWORD 'REPLACE_WITH_1PASSWORD_VALUE';
```
The comment immediately above correctly warns the operator to replace this
before running the script, but nothing in the script enforces that — run
verbatim, it provisions a real, usable login role with a fixed, publicly
visible (in this repository) password string.
**Fix:** Low-cost hardening: use an obviously-invalid placeholder that fails
to parse (e.g. `'<REPLACE_WITH_1PASSWORD_VALUE>'` is still valid SQL text, so
consider `\set` + `:'password'` psql-variable substitution instead, which
errors out if the variable was never set) so an unedited run fails loudly
rather than succeeding with a known credential.

---

_Reviewed: 2026-09-21T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
